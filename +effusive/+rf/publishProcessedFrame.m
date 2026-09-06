function publishProcessedFrame()
% Write processed frame data to shared memory and emit periodic timing reports.
%
% Notes
% -----
% This is Process(4) in the Verasonics event sequence, running after
% processRuntimeControl and before the returnToMatlab sync event.  It is
% skipped silently when FrameRuntimeState.frameReady is false (e.g. the
% svdUpdateFlag branch ran in processRFEnsembleBlock).
%
% Timing is measured across three quantities per frame (accumulated over
% TIMING_PRINT_INTERVAL frames):
%
% - VSX acq loop: time from end of previous publishProcessedFrame to start
%   of processRFEnsembleBlock (i.e. time spent in hardware acquisition).
%   Set by processRFEnsembleBlock into FrameRuntimeState.t_vsx_wait_s.
% - Callback:     toc(FrameRuntimeState.t_frame_start_tic) measured here at
%   end of publish -- covers RF proc + control + publish.
% - Total period: VSX + callback; reciprocal gives FPS.
%
% Base workspace variables (read):
%
% - `FrameRuntimeState` (struct): Bmode, PDI (raw, un-normalized -- the
%   napari viewer log-compresses each to dB relative to its own per-frame
%   peak), RF (raw ensemble, sliced into an RF snapshot only when
%   publishRfSnapshot is true), ensemble_time_s, publishRfSnapshot,
%   frameReady, t_frame_start_tic, t_vsx_wait_s.
% - `storeEchoFrameOutput` (logical): current save state for runtime flags.
% - Shared memory names (char): read once on first call.
%
% Base workspace variables (written):
%
% - `FrameRuntimeState`: publishRfSnapshot reset to false after RF write;
%   t_last_publish_end_tic updated at end of each call.

    persistent sharedMemoryBmode sharedMemoryPdi sharedMemoryMeta sharedMemoryRf
    persistent bmodeBuffer pdiBuffer nz_img nx_img
    persistent rf_counter_persist
    persistent timing_frame_count timing_total timing_vsx_wait
    TIMING_PRINT_INTERVAL = 200;

    if isempty(rf_counter_persist)
        rf_counter_persist = uint64(0);
    end

    if isempty(timing_frame_count)
        timing_frame_count = uint64(0);
        timing_total       = 0;
        timing_vsx_wait    = 0;
    end

    FrameRuntimeState = evalin('base', 'FrameRuntimeState');

    if ~FrameRuntimeState.frameReady
        return;
    end

    % Open shared memory handles lazily on first displayable frame.
    if isempty(sharedMemoryBmode)
        sharedMemoryBmode = py.multiprocessing.shared_memory.SharedMemory( ...
            name=evalin('base', 'sharedMemoryNameBmode'), create=false ...
        );
        sharedMemoryPdi = py.multiprocessing.shared_memory.SharedMemory( ...
            name=evalin('base', 'sharedMemoryNamePdi'), create=false ...
        );
        sharedMemoryMeta = py.multiprocessing.shared_memory.SharedMemory( ...
            name=evalin('base', 'sharedMemoryNameMeta'), create=false ...
        );
        sharedMemoryRf = py.multiprocessing.shared_memory.SharedMemory( ...
            name=evalin('base', 'sharedMemoryNameRf'), create=false ...
        );
        [nz_img, nx_img] = size(FrameRuntimeState.Bmode);
        n_pixels  = int32(nz_img) * int32(nx_img);
        bmodeBuffer = py.numpy.frombuffer(sharedMemoryBmode.buf, py.numpy.float32, n_pixels);
        pdiBuffer   = py.numpy.frombuffer(sharedMemoryPdi.buf,   py.numpy.float32, n_pixels);
    else
        % Re-create buffer views if image dimensions changed (e.g. after crop).
        [nz_new, nx_new] = size(FrameRuntimeState.Bmode);
        if nz_new ~= nz_img || nx_new ~= nx_img
            nz_img = nz_new;
            nx_img = nx_new;
            n_pixels    = int32(nz_img) * int32(nx_img);
            bmodeBuffer = py.numpy.frombuffer(sharedMemoryBmode.buf, py.numpy.float32, n_pixels);
            pdiBuffer   = py.numpy.frombuffer(sharedMemoryPdi.buf,   py.numpy.float32, n_pixels);
        end
    end

    % Write raw Bmode image (napari log-compresses to dB on its own tick).
    flat_bmode = typecast(reshape(FrameRuntimeState.Bmode.', 1, []), 'uint8');
    src_bmode  = py.numpy.frombuffer(py.bytes(flat_bmode), py.numpy.float32);
    py.numpy.copyto(bmodeBuffer, src_bmode);

    % Write raw PDI image (napari log-compresses to dB on its own tick).
    flat_pdi = typecast(reshape(FrameRuntimeState.PDI.', 1, []), 'uint8');
    src_pdi  = py.numpy.frombuffer(py.bytes(flat_pdi), py.numpy.float32);
    py.numpy.copyto(pdiBuffer, src_pdi);

    % Write RF snapshot when flagged by processRuntimeControl.
    if FrameRuntimeState.publishRfSnapshot
        effusive.util.logMessage('Writing RF snapshot to sharedMemoryRf.');
        rfSlice = cfSelectRfSnapshotSlice(FrameRuntimeState.RF);
        [nsamples_rf, ncols_rf] = size(rfSlice);
        rf_counter_persist = rf_counter_persist + uint64(1);
        header_bytes = [ ...
            typecast(rf_counter_persist, 'uint8'), ...
            typecast(int32(nsamples_rf), 'uint8'), ...
            typecast(int32(ncols_rf),    'uint8') ...
        ];
        flat_rf   = typecast(reshape(rfSlice.', 1, []), 'uint8');
        all_bytes = [header_bytes, flat_rf];
        n_all     = int64(numel(all_bytes));
        src_rf    = py.numpy.frombuffer(py.bytes(all_bytes), py.numpy.uint8);
        buf_rf    = py.numpy.frombuffer(sharedMemoryRf.buf, py.numpy.uint8, n_all);
        py.numpy.copyto(buf_rf, src_rf);
        buf_rf = py.None; %#ok<NASGU>
        src_rf = py.None; %#ok<NASGU>
        FrameRuntimeState.publishRfSnapshot = false;
    end

    % Update cf_meta: frame counter (bytes 1:8), runtime flags (33:36),
    % ensemble time tag (37:44).
    storeEchoFrameOutput = evalin('base', 'storeEchoFrameOutput');
    freezeActive         = logical(evalin('base', 'freeze'));
    BidsRuntimeState     = evalin('base', 'BidsRuntimeState');
    if storeEchoFrameOutput && ~BidsRuntimeState.saveActive
        BidsRuntimeState.saveActive = true;
        BidsRuntimeState.summaryWritten = false;
        BidsRuntimeState.acqTime = char(datetime('now', 'TimeZone', 'local', 'Format', 'yyyy-MM-dd''T''HH:mm:ssXXX'));
        assignin('base', 'BidsRuntimeState', BidsRuntimeState);
    end
    meta_raw  = uint8(py.array.array('B', sharedMemoryMeta.buf));
    frame_ctr = typecast(meta_raw(1:8), 'uint64') + uint64(1);
    new_meta  = meta_raw;
    new_meta(1:8)   = typecast(frame_ctr, 'uint8');
    new_meta(33:36) = typecast( ...
        effusive.napari.metaRuntimeFlags(storeEchoFrameOutput, freezeActive), 'uint8' ...
    );
    new_meta(37:44) = typecast(double(FrameRuntimeState.ensemble_time_s), 'uint8');
    src_meta  = py.numpy.frombuffer(py.bytes(new_meta), py.numpy.uint8);
    % On Windows, shared memory is page-aligned (4096 bytes) but we only need 44.
    meta_buf  = py.numpy.ndarray( ...
        py.tuple({int32(numel(new_meta))}), ...
        dtype=py.numpy.uint8, buffer=sharedMemoryMeta.buf ...
    );
    py.numpy.copyto(meta_buf, src_meta);

    % Accumulate timing and print summary periodically.
    timing_total      = timing_total      + toc(FrameRuntimeState.t_frame_start_tic);
    timing_vsx_wait   = timing_vsx_wait   + FrameRuntimeState.t_vsx_wait_s;
    timing_frame_count = timing_frame_count + uint64(1);
    if timing_frame_count >= uint64(TIMING_PRINT_INTERVAL)
        N = double(timing_frame_count);
        timing_period = timing_vsx_wait + timing_total;
        effusive.util.logMessage('Timing over %d frames (mean per frame):', N);
        effusive.util.logMessage('  VSX acq loop: %6.1f ms', timing_vsx_wait / N * 1e3);
        effusive.util.logMessage('  callback:     %6.1f ms', timing_total     / N * 1e3);
        effusive.util.logMessage('  total period: %6.1f ms  (~%.2f fps)', ...
            timing_period / N * 1e3, N / timing_period);
        timing_frame_count = uint64(0);
        timing_total       = 0;
        timing_vsx_wait    = 0;
    end

    FrameRuntimeState.t_last_publish_end_tic = tic;
    assignin('base', 'FrameRuntimeState', FrameRuntimeState);
end


function rfSlice = cfSelectRfSnapshotSlice(RF)
% Select one TX/repeat RF block for snapshot display.

    maxSnapshotSamples = 1024;
    maxSnapshotChannels = 512;

    ReceiveSpec = evalin('base', 'ReceiveSpec');
    Trans = evalin('base', 'Trans');

    nSamples = double(ReceiveSpec.nSamples);
    nTransmissions = double(ReceiveSpec.nTransmissions);
    nRepeats = double(ReceiveSpec.nRepeats);

    if nSamples <= 0 || nTransmissions <= 0 || nRepeats <= 0
        rfSlice = RF(1:min(end, maxSnapshotSamples), 1:min(size(RF, 2), maxSnapshotChannels));
        return;
    end

    txMid = ceil(nTransmissions / 2);
    repeatIndex = 1;
    acqIndex = (repeatIndex - 1) * nTransmissions + txMid;

    rowStart = (acqIndex - 1) * nSamples + 1;
    rowEnd = acqIndex * nSamples;

    if rowStart < 1 || rowEnd > size(RF, 1)
        rfSlice = RF(1:min(end, maxSnapshotSamples), 1:min(size(RF, 2), maxSnapshotChannels));
        return;
    end

    rfBlock = RF(rowStart:rowEnd, 1:min(size(RF, 2), maxSnapshotChannels));

    % Reorder channels from system order to transducer element order.
    connectorMap = [];
    if isfield(Trans, 'ConnectorES') && ~isempty(Trans.ConnectorES)
        connectorMap = double(Trans.ConnectorES(:)');
    end
    if ~isempty(connectorMap)
        valid = connectorMap >= 1 & connectorMap <= size(rfBlock, 2);
        if any(valid)
            rfBlock = rfBlock(:, connectorMap(valid));
        end
    end

    isIQ = false;
    if isfield(ReceiveSpec, 'isIQ')
        isIQ = logical(ReceiveSpec.isIQ);
    end

    if isIQ && mod(size(rfBlock, 1), 2) == 0 && size(rfBlock, 1) >= 2
        iPart = single(rfBlock(1:2:end, :));
        qPart = single(rfBlock(2:2:end, :));
        iqMagnitude = abs(complex(iPart, qPart));
        iqMagnitude = min(iqMagnitude, single(intmax('int16')));
        rfSlice = int16(round(iqMagnitude));
    else
        rfSlice = rfBlock;
    end

    rfSlice = rfSlice(1:min(size(rfSlice, 1), maxSnapshotSamples), :);
end
