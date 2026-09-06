function processRuntimeControl()
% Decode napari commands and apply hardware/storage mutations each frame.
%
% Notes
% -----
% This is Process(3) in the Verasonics event sequence, running after
% processRFEnsembleBlock but before publishProcessedFrame and the
% returnToMatlab sync event.
%
% `storeEchoFrameOutput` is read at the TOP of this callback -- before any
% mutation -- because it reflects the value that `echoframe_mex` used in the
% current processRFEnsembleBlock call.  It is written back at the END with
% the new effective value, so the NEXT frame picks it up (1-frame delay).
%
% Base workspace variables (read):
%
% - `storeEchoFrameOutput` (logical): current save-to-disk flag used by MEX.
% - `FrameRuntimeState` (struct): inter-callback bus; PDI used for z-stack,
%   publishRfSnapshot set here on rising edge of show_rf.
% - `ExperimentSpec` (struct): needed by effusive.echoframe.configureEchoFrameStorageSpecs on storage re-init.
% - `storageConfigApplied` (struct): last applied storage configuration.
% - `StorageSpec` (struct): EchoFrame storage specification.
% - `svdUpdateFlag` (logical): guard against re-arming SVD on same frame.
% - `freeze` (double): current freeze state for change-detection.
% - `freezeResumedByNapari` (logical): ack flag after napari unfreeze.
% - `experimentControlOwner` (char): 'manual' or 'zstack'.
% - `Info` (struct): EchoFrame acquisition info; motor handle lives here.
% - Various VSX hardware structs when aperture/TGC updates are needed.
%
% Base workspace variables (written):
%
% - `storeEchoFrameOutput`: updated to effective value at end of callback.
% - `FrameRuntimeState`: publishRfSnapshot may be set; written back.
% - `storageConfigApplied`: updated when storage configuration changes.
% - `StorageSpec`: updated on save-flag or crop-induced storage re-init.
% - `vsExit` (double): set to 1 on vsExit command.
% - `freeze` (double): updated on freeze/unfreeze command.
% - `freezeResumedByNapari` (logical): reset after ack.
% - `svdThreshold`, `svdUpdateFlag`, `PDISpec`: updated on SVD command.
% - `updateCropping`, `ReconSpec`, `PDISpec`: updated on crop command.
% - `TX`, `TransmitSpec`: updated on TX aperture command.
% - `Receive`, `ReceiveSpec`: updated on RX aperture command.
% - `TGC`, `ReceiveSpec`: updated on TGC command.
% - `Info`, `experimentControlOwner`: updated by z-stack state machine.

    persistent sharedMemoryCmd sharedMemoryStack sharedMemoryAck freezeBtn
    persistent lastShowRfFlag zStackState
    persistent lastFreezeReqId lastSaveReqId lastSvdReqId
    persistent lastVoltageReqId lastTxApertureReqId lastRxApertureReqId
    persistent lastTgcReqId lastCropReqId lastStackReqId
    persistent lastSaveRejectMessage

    if isempty(lastShowRfFlag)
        lastShowRfFlag = logical(false);
    end

    if isempty(lastFreezeReqId),     lastFreezeReqId = uint32(0); end
    if isempty(lastSaveReqId),       lastSaveReqId = uint32(0); end
    if isempty(lastSvdReqId),        lastSvdReqId = uint32(0); end
    if isempty(lastVoltageReqId),    lastVoltageReqId = uint32(0); end
    if isempty(lastTxApertureReqId), lastTxApertureReqId = uint32(0); end
    if isempty(lastRxApertureReqId), lastRxApertureReqId = uint32(0); end
    if isempty(lastTgcReqId),        lastTgcReqId = uint32(0); end
    if isempty(lastCropReqId),       lastCropReqId = uint32(0); end
    if isempty(lastStackReqId),      lastStackReqId = uint32(0); end
    if isempty(lastSaveRejectMessage), lastSaveRejectMessage = ''; end

    if isempty(zStackState)
        zStackState = cfDefaultZStackState();
    end

    if isempty(sharedMemoryCmd)
        sharedMemoryCmd = py.multiprocessing.shared_memory.SharedMemory( ...
            name=evalin('base', 'sharedMemoryNameCmd'), create=false ...
        );
        sharedMemoryStack = py.multiprocessing.shared_memory.SharedMemory( ...
            name=evalin('base', 'sharedMemoryNameStack'), create=false ...
        );
        sharedMemoryAck = py.multiprocessing.shared_memory.SharedMemory( ...
            name=evalin('base', 'sharedMemoryNameAck'), create=false ...
        );
        cfWriteStackStatus(sharedMemoryStack, zStackState);
    end

    % Read storeEchoFrameOutput first (1-frame delay invariant).
    storeEchoFrameOutput = evalin('base', 'storeEchoFrameOutput');

    FrameRuntimeState = evalin('base', 'FrameRuntimeState');
    ExperimentSpec    = evalin('base', 'ExperimentSpec');
    freezeResumedByNapari = evalin('base', 'freezeResumedByNapari');
    svdUpdateFlag     = evalin('base', 'svdUpdateFlag');

    % Decode command packet.
    cmd = uint8(py.array.array('B', sharedMemoryCmd.buf));
    % cmd layout (CMD_FORMAT "<BBBBhBxfBBhhBBBxhhhhBBBBBxhhhhhhhhBBBxiiiiiiIIIIIIIII"):
    %   [1]     vsExit              [2]     freeze
    %   [3]     save_to_disk        [4]     svd_update_flag
    %   [5:6]   svd_threshold       [7]     voltage_update_flag
    %   [8]     pad                 [9:12]  voltage_v (float32)
    %   [13]    tx_aperture_update  [14]    rx_aperture_update
    %   [15:16] tx_aperture (int16) [17:18] rx_aperture (int16)
    %   [19]    show_rf             [20]    crop_update_flag
    %   [21]    crop_reset_flag     [22]    pad
    %   [23:24] roi_top (int16)     [25:26] roi_bottom (int16)
    %   [27:28] roi_left (int16)    [29:30] roi_right (int16)
    %   [31]    save_rf             [32]    save_rf_time_tag
    %   [33]    save_bf             [34]    save_pdi
    %   [35]    tgc_update_flag     [36]    pad
    %   [37:38] tgc_point_1  ...  [51:52] tgc_point_8
    %   [53]    stack_start_flag    [54]    stack_abort_flag
    %   [55]    stack_use_dummy_motor
    %   [57:60] stack_start_um      [61:64] stack_step_um
    %   [65:68] stack_n_slices      [69:72] stack_npdi_per_slice
    %   [73:76] stack_settle_ms     [77:80] stack_jog_um
    vsExit_cmd              = logical(cmd(1));
    freeze                  = logical(cmd(2));
    save_to_disk_cmd        = logical(cmd(3));
    svd_threshold_cmd       = single(typecast(cmd(5:6), 'int16')) * single(0.01);
    voltage_v_cmd           = double(typecast(cmd(9:12), 'single'));
    tx_aperture_cmd         = double(typecast(cmd(15:16), 'int16'));
    rx_aperture_cmd         = double(typecast(cmd(17:18), 'int16'));
    show_rf_cmd             = logical(cmd(19));
    crop_update_cmd         = logical(cmd(20));
    crop_reset_cmd          = logical(cmd(21));
    roi_top_cmd             = int32(typecast(cmd(23:24), 'int16'));
    roi_bottom_cmd          = int32(typecast(cmd(25:26), 'int16'));
    roi_left_cmd            = int32(typecast(cmd(27:28), 'int16'));
    roi_right_cmd           = int32(typecast(cmd(29:30), 'int16'));
    save_rf_cmd             = logical(cmd(31));
    save_rf_time_tag_cmd    = logical(cmd(32));
    save_bf_cmd             = logical(cmd(33));
    save_pdi_cmd            = logical(cmd(34));
    tgc_control_points_cmd  = double([ ...
        typecast(cmd(37:38), 'int16'), ...
        typecast(cmd(39:40), 'int16'), ...
        typecast(cmd(41:42), 'int16'), ...
        typecast(cmd(43:44), 'int16'), ...
        typecast(cmd(45:46), 'int16'), ...
        typecast(cmd(47:48), 'int16'), ...
        typecast(cmd(49:50), 'int16'), ...
        typecast(cmd(51:52), 'int16') ...
    ]);
    stack_start_flag_cmd     = logical(cmd(53));
    stack_abort_flag_cmd     = logical(cmd(54));
    stack_use_dummy_cmd      = logical(cmd(55));
    stack_start_um_cmd       = int32(typecast(cmd(57:60), 'int32'));
    stack_step_um_cmd        = int32(typecast(cmd(61:64), 'int32'));
    stack_n_slices_cmd       = int32(typecast(cmd(65:68), 'int32'));
    stack_npdi_per_slice_cmd = int32(typecast(cmd(69:72), 'int32'));
    stack_settle_ms_cmd      = int32(typecast(cmd(73:76), 'int32'));
    stack_jog_um_cmd         = int32(typecast(cmd(77:80), 'int32'));
    freeze_req_id_cmd        = typecast(cmd(81:84), 'uint32');
    save_req_id_cmd          = typecast(cmd(85:88), 'uint32');
    svd_req_id_cmd           = typecast(cmd(89:92), 'uint32');
    voltage_req_id_cmd       = typecast(cmd(93:96), 'uint32');
    tx_aperture_req_id_cmd   = typecast(cmd(97:100), 'uint32');
    rx_aperture_req_id_cmd   = typecast(cmd(101:104), 'uint32');
    tgc_req_id_cmd           = typecast(cmd(105:108), 'uint32');
    crop_req_id_cmd          = typecast(cmd(109:112), 'uint32');
    stack_req_id_cmd         = typecast(cmd(113:116), 'uint32');

    % --- vsExit ---
    if vsExit_cmd
        if zStackState.isActive
            Info = evalin('base', 'Info');
            [Info, zStackState] = cfTerminateZStack( ...
                Info, zStackState, sharedMemoryStack, int16(7), 'VSX exit requested.', true ...
            );
            assignin('base', 'Info', Info);
            assignin('base', 'experimentControlOwner', 'manual');
        end
        effusive.util.logMessage('vsExit received; stopping VSX.');
        assignin('base', 'vsExit', 1);
        assignin('base', 'FrameRuntimeState', FrameRuntimeState);
        return;
    end

    % --- freeze/unfreeze ---
    current_freeze = evalin('base', 'freeze');
    freeze_double = double(freeze);
    if freezeResumedByNapari && ~freeze_double
        effusive.util.logMessage('Resume received; resuming acquisition.');
        freezeResumedByNapari = 0;
        assignin('base', 'freezeResumedByNapari', freezeResumedByNapari);
    end
    freezeReqChanged = freeze_req_id_cmd ~= lastFreezeReqId;
    if freezeReqChanged && freeze_double ~= current_freeze
        freezeBtn = effusive.napari.setFrozenState(logical(freeze_double), freezeBtn, false);
        if freeze_double
            effusive.util.logMessage('Freeze received; pausing acquisition.');
        else
            effusive.util.logMessage('Unfreeze received; resuming acquisition.');
        end
    end
    if freezeReqChanged
        lastFreezeReqId = freeze_req_id_cmd;
        cfWriteAckId(sharedMemoryAck, 1, freeze_req_id_cmd);
    end

    % --- voltage update ---
    voltageReqChanged = voltage_req_id_cmd ~= lastVoltageReqId;
    if voltageReqChanged
        effusive.util.logMessage('Voltage -> %.2f V', voltage_v_cmd);
        setTpcProfileHighVoltage(voltage_v_cmd, 1);
        lastVoltageReqId = voltage_req_id_cmd;
        cfWriteAckId(sharedMemoryAck, 4, voltage_req_id_cmd);
    end

    % --- TX aperture update ---
    txApertureReqChanged = tx_aperture_req_id_cmd ~= lastTxApertureReqId;
    if txApertureReqChanged
        effusive.util.logMessage('TX aperture -> %d%%', tx_aperture_cmd);
        TX           = evalin('base', 'TX');
        TransmitSpec = evalin('base', 'TransmitSpec');
        new_apod     = effusive.sequences.calculateApertureApodization(numel(TX(1).Apod), tx_aperture_cmd, 0.1);
        for iTX = 1:numel(TX)
            TX(iTX).Apod = new_apod;
        end
        TransmitSpec.aperturePercentage = tx_aperture_cmd;
        TransmitSpec.apodization        = new_apod;
        assignin('base', 'TX',           TX);
        assignin('base', 'TransmitSpec', TransmitSpec);
        effusive.sequences.addUpdateAndRunCommand('TX');
        lastTxApertureReqId = tx_aperture_req_id_cmd;
        cfWriteAckId(sharedMemoryAck, 5, tx_aperture_req_id_cmd);
    end

    % --- RX aperture update ---
    rxApertureReqChanged = rx_aperture_req_id_cmd ~= lastRxApertureReqId;
    if rxApertureReqChanged
        effusive.util.logMessage('RX aperture -> %d%%', rx_aperture_cmd);
        Receive     = evalin('base', 'Receive');
        ReceiveSpec = evalin('base', 'ReceiveSpec');
        new_apod    = effusive.sequences.calculateApertureApodization(numel(Receive(1).Apod), rx_aperture_cmd, 0.2);
        for iRcv = 1:numel(Receive)
            Receive(iRcv).Apod = new_apod;
        end
        ReceiveSpec.aperturePercentage = rx_aperture_cmd;
        ReceiveSpec.apodization        = new_apod;
        assignin('base', 'Receive',     Receive);
        assignin('base', 'ReceiveSpec', ReceiveSpec);
        effusive.sequences.addUpdateAndRunCommand('Receive');
        lastRxApertureReqId = rx_aperture_req_id_cmd;
        cfWriteAckId(sharedMemoryAck, 6, rx_aperture_req_id_cmd);
    end

    % --- TGC update ---
    tgcReqChanged = tgc_req_id_cmd ~= lastTgcReqId;
    if tgcReqChanged
        effusive.util.logMessage('TGC -> [%s]', num2str(tgc_control_points_cmd));
        TGC         = evalin('base', 'TGC');
        % `computeTGCWaveform` reads `Trans.frequency` from caller workspace.
        Trans       = evalin('base', 'Trans'); %#ok<NASGU>
        ReceiveSpec = evalin('base', 'ReceiveSpec');
        TGC(1).CntrlPts = tgc_control_points_cmd;
        TGC(1).Waveform = computeTGCWaveform(TGC(1));
        ReceiveSpec.tgcControlPoints = tgc_control_points_cmd;
        if all(tgc_control_points_cmd == tgc_control_points_cmd(1))
            ReceiveSpec.tgcGain = tgc_control_points_cmd(1);
        else
            ReceiveSpec.tgcGain = nan;
        end
        assignin('base', 'TGC',         TGC);
        assignin('base', 'ReceiveSpec', ReceiveSpec);
        effusive.sequences.addUpdateAndRunCommand('TGC');
        lastTgcReqId = tgc_req_id_cmd;
        cfWriteAckId(sharedMemoryAck, 7, tgc_req_id_cmd);
    end

    % --- RF snapshot: rising edge -> flag publishProcessedFrame ---
    if show_rf_cmd && ~lastShowRfFlag && FrameRuntimeState.frameReady
        FrameRuntimeState.publishRfSnapshot = true;
    end
    lastShowRfFlag = show_rf_cmd;

    % --- Crop: apply new ROI ---
    cropReqChanged = crop_req_id_cmd ~= lastCropReqId;
    if cropReqChanged && crop_update_cmd
        effusive.util.logMessage('Applying crop ROI: rows %d-%d, cols %d-%d', ...
            roi_top_cmd, roi_bottom_cmd, roi_left_cmd, roi_right_cmd);
        ReconSpec = evalin('base', 'ReconSpec');
        PDISpec   = evalin('base', 'PDISpec');
        ReconSpec.croppingROI = [roi_top_cmd; roi_bottom_cmd; roi_left_cmd; roi_right_cmd];
        ReconSpec.cropBF      = logical(true);
        PDISpec.cropPDI       = logical(true);
        assignin('base', 'ReconSpec',      ReconSpec);
        assignin('base', 'PDISpec',        PDISpec);
        assignin('base', 'updateCropping', 1);
    end

    % --- Crop: reset to full FOV ---
    if cropReqChanged && crop_reset_cmd
        effusive.util.logMessage('Resetting crop to full FOV.');
        ReconSpec = evalin('base', 'ReconSpec');
        PDISpec   = evalin('base', 'PDISpec');
        nz_full   = int32(numel(ReconSpec.zAxis));
        nx_full   = int32(numel(ReconSpec.xAxis));
        ReconSpec.croppingROI = [int32(0); nz_full - int32(1); int32(0); nx_full - int32(1)];
        ReconSpec.cropBF      = logical(false);
        PDISpec.cropPDI       = logical(false);
        assignin('base', 'ReconSpec',      ReconSpec);
        assignin('base', 'PDISpec',        PDISpec);
        assignin('base', 'updateCropping', 1);
    end
    if cropReqChanged
        lastCropReqId = crop_req_id_cmd;
        cfWriteAckId(sharedMemoryAck, 8, crop_req_id_cmd);
    end

    % --- SVD threshold update ---
    svdReqChanged = svd_req_id_cmd ~= lastSvdReqId;
    if svdReqChanged && ~svdUpdateFlag
        svdThreshold = svd_threshold_cmd;
        svdUpdateFlag = 1;
        PDISpec = evalin('base', 'PDISpec');
        PDISpec.threshold = svdThreshold;
        assignin('base', 'svdThreshold',  svdThreshold);
        assignin('base', 'svdUpdateFlag', svdUpdateFlag);
        assignin('base', 'PDISpec',       PDISpec);
    end
    if svdReqChanged
        lastSvdReqId = svd_req_id_cmd;
        cfWriteAckId(sharedMemoryAck, 3, svd_req_id_cmd);
    end

    % --- Z-stack jog and state machine (only on normal processed frames) ---
    stackReqChanged = stack_req_id_cmd ~= lastStackReqId;
    stackStartReq = stackReqChanged && stack_start_flag_cmd;
    stackAbortReq = stackReqChanged && stack_abort_flag_cmd;

    if FrameRuntimeState.frameReady
        experimentControlOwner = evalin('base', 'experimentControlOwner');
        Info = evalin('base', 'Info');
        [Info, zStackState, experimentControlOwner] = cfHandleStackJogRequest( ...
            Info, zStackState, experimentControlOwner, sharedMemoryStack, ...
            stack_use_dummy_cmd, stack_jog_um_cmd ...
        );
        [Info, zStackState, experimentControlOwner] = cfRunZStackStateMachine( ...
            FrameRuntimeState.PDI, ...
            FrameRuntimeState.Bmode, ...
            Info, ...
            zStackState, ...
            experimentControlOwner, ...
            sharedMemoryStack, ...
            stackStartReq, ...
            stackAbortReq, ...
            stack_use_dummy_cmd, ...
            stack_start_um_cmd, ...
            stack_step_um_cmd, ...
            stack_n_slices_cmd, ...
            stack_npdi_per_slice_cmd, ...
            stack_settle_ms_cmd ...
        );
        assignin('base', 'Info', Info);
        assignin('base', 'experimentControlOwner', experimentControlOwner);
        cfWriteStackStatus(sharedMemoryStack, zStackState);
    end
    if stackReqChanged
        lastStackReqId = stack_req_id_cmd;
        cfWriteAckId(sharedMemoryAck, 9, stack_req_id_cmd);
    end

    % --- Storage configuration update ---
    StorageSpec           = evalin('base', 'StorageSpec');
    BidsSpec              = evalin('base', 'BidsSpec');
    storageConfigApplied  = evalin('base', 'storageConfigApplied');
    effectiveSaveToDisk   = save_to_disk_cmd;
    requestedStorageConfig = effusive.control.requestedStorageConfig( ...
        effectiveSaveToDisk, save_rf_cmd, save_rf_time_tag_cmd, save_bf_cmd, save_pdi_cmd ...
    );

    if requestedStorageConfig.initialized && ~storageConfigApplied.initialized
        [StorageSpec, BidsSpec, bidsReady, bidsMessage] = cfPrepareStorageSpecForSave( ...
            StorageSpec, BidsSpec ...
        );
        assignin('base', 'StorageSpec', StorageSpec);
        assignin('base', 'BidsSpec', BidsSpec);
        if ~bidsReady
            if ~strcmp(lastSaveRejectMessage, bidsMessage)
                effusive.util.logMessage('Saving request rejected: %s', bidsMessage);
                lastSaveRejectMessage = bidsMessage;
            end
            requestedStorageConfig.initialized = false;
        else
            lastSaveRejectMessage = '';
        end
    end

    StorageSpec.saveBF        = requestedStorageConfig.saveBF;
    StorageSpec.savePDI       = requestedStorageConfig.savePDI;
    StorageSpec.saveRFTimeTag = requestedStorageConfig.saveRFTimeTag;
    StorageSpec.saveRF        = requestedStorageConfig.saveRF;
    assignin('base', 'StorageSpec', StorageSpec);

    saveReqChanged = save_req_id_cmd ~= lastSaveReqId;
    if ~effectiveSaveToDisk
        lastSaveRejectMessage = '';
    end
    if ~isequal(storageConfigApplied, requestedStorageConfig)
        ReconSpec    = evalin('base', 'ReconSpec');
        PDISpec      = evalin('base', 'PDISpec');
        ReceiveSpec  = evalin('base', 'ReceiveSpec');
        TransmitSpec = evalin('base', 'TransmitSpec');
        ProbeSpec    = evalin('base', 'ProbeSpec');
        if requestedStorageConfig.initialized
            try
                effusive.util.logMessage( ...
                    'Re-initializing storage -> %s', StorageSpec.experimentStoragePath ...
                );
                effusive.rf.reinitEchoFrameStorage( ...
                    're-init storage', true, StorageSpec, ReceiveSpec, ReconSpec, PDISpec, ...
                    ExperimentSpec, TransmitSpec, ProbeSpec ...
                );
                % configureEchoFrameStorageSpecs (called inside reinitEchoFrameStorage)
                % mutates StorageSpec.experimentStoragePath in the base workspace.
                StorageSpec = evalin('base', 'StorageSpec');
                effusive.util.logMessage( ...
                    'Storage prepared -> %s', StorageSpec.experimentStoragePath ...
                );
            catch ME
                effusive.util.logMessage( ...
                    'Storage re-init failed for %s: %s', StorageSpec.experimentStoragePath, ME.message ...
                );
                requestedStorageConfig = storageConfigApplied;
                StorageSpec.saveBF = storageConfigApplied.saveBF;
                StorageSpec.savePDI = storageConfigApplied.savePDI;
                StorageSpec.saveRFTimeTag = storageConfigApplied.saveRFTimeTag;
                StorageSpec.saveRF = storageConfigApplied.saveRF;
                assignin('base', 'StorageSpec', StorageSpec);
            end
        else
            BidsRuntimeState = evalin('base', 'BidsRuntimeState');
            if BidsRuntimeState.saveActive && ~BidsRuntimeState.summaryWritten
                try
                    cfWriteBidsSummaryFiles(StorageSpec, BidsSpec, BidsRuntimeState);
                    BidsRuntimeState.summaryWritten = true;
                catch ME
                    effusive.util.logMessage('Could not update BIDS summary files: %s', ME.message);
                end
            end
            effusive.rf.reinitEchoFrameStorage( ...
                're-init storage', false, StorageSpec, ReceiveSpec, ReconSpec, PDISpec, ...
                ExperimentSpec, TransmitSpec, ProbeSpec ...
            );
            StorageSpec.experimentStoragePath = '';
            assignin('base', 'StorageSpec', StorageSpec);
            BidsRuntimeState.saveActive = false;
            BidsRuntimeState.acqTime = '';
            assignin('base', 'BidsRuntimeState', BidsRuntimeState);
        end
        assignin('base', 'storageConfigApplied', requestedStorageConfig);
    end
    if saveReqChanged
        lastSaveReqId = save_req_id_cmd;
        cfWriteAckId(sharedMemoryAck, 2, save_req_id_cmd);
    end

    if requestedStorageConfig.initialized ~= storageConfigApplied.initialized
        effusive.sequences.setTriggerOutEnabled(requestedStorageConfig.initialized);
    end

    if requestedStorageConfig.initialized ~= storeEchoFrameOutput
        storeEchoFrameOutput = requestedStorageConfig.initialized;
        assignin('base', 'storeEchoFrameOutput', storeEchoFrameOutput);
        if storeEchoFrameOutput
            effusive.util.logMessage( ...
                'Saving enabled -> %s', StorageSpec.experimentStoragePath ...
            );
        else
            effusive.util.logMessage('Saving disabled.');
        end
    end

    assignin('base', 'FrameRuntimeState', FrameRuntimeState);
end


function cfWriteAckId(sharedMemoryAck, ackFieldIndexOneBased, requestId)
% Write one 4-byte request-id field into the ack segment.

    if isempty(sharedMemoryAck)
        return;
    end

    ackBytes = uint8(py.array.array('B', sharedMemoryAck.buf));
    startByte = int32((ackFieldIndexOneBased - 1) * 4 + 1);
    stopByte = startByte + int32(3);
    ackBytes(startByte:stopByte) = typecast(uint32(requestId), 'uint8');

    src = py.numpy.frombuffer(py.bytes(ackBytes), py.numpy.uint8);
    dst = py.numpy.frombuffer(sharedMemoryAck.buf, py.numpy.uint8, int64(numel(ackBytes)));
    py.numpy.copyto(dst, src);
end


function [StorageSpec, BidsSpec, ok, message] = cfPrepareStorageSpecForSave(StorageSpec, BidsSpec)
    ok = true;
    message = '';

    % Merge live per-recording metadata from the Python-written sidecar.
    % Python writes this file just before setting save_to_disk=1, so it
    % carries subject/session/task/acq/proc/run values the user may have
    % changed since VSX launched without requiring a new session.
    if evalin('base', 'exist(''effusiveBidsMetaPath'', ''var'') == 1')
        sidecarPath = char(string(evalin('base', 'effusiveBidsMetaPath')));
    else
        sidecarPath = '';
    end
    sidecar = struct();
    if ~isempty(sidecarPath) && isfile(sidecarPath)
        try
            sidecar = jsondecode(fileread(sidecarPath));
            if isfield(sidecar, 'subject'), BidsSpec.subject = char(string(sidecar.subject)); end
            if isfield(sidecar, 'session'), BidsSpec.session = char(string(sidecar.session)); end
            if isfield(sidecar, 'task'),     BidsSpec.task      = char(string(sidecar.task));     end
            if isfield(sidecar, 'acq'),      BidsSpec.acq       = char(string(sidecar.acq));      end
            if isfield(sidecar, 'proc'),     BidsSpec.proc      = char(string(sidecar.proc));     end
            if isfield(sidecar, 'run'), BidsSpec.run = double(sidecar.run); end
        catch
            sidecar = struct();
        end
    end

    taskRaw = '';
    if isfield(BidsSpec, 'task'), taskRaw = BidsSpec.task; end
    acqRaw = '';
    if isfield(BidsSpec, 'acq'), acqRaw = BidsSpec.acq; end
    procRaw = '';
    if isfield(BidsSpec, 'proc'), procRaw = BidsSpec.proc; end

    try
        subject = effusive.bids.validateLabel(BidsSpec.subject, 'Subject', true);
        session = effusive.bids.validateLabel(BidsSpec.session, 'Session', true);
        task = effusive.bids.validateLabel(taskRaw, 'Task', true);
        acq = effusive.bids.validateLabel(acqRaw, 'Acquisition', false);
        proc = effusive.bids.validateLabel(procRaw, 'Processing', false);
        requireTask = true;

        dataDir = effusive.bids.buildDataDirectory( ...
            StorageSpec.storageRootPath, subject, session, 'fusi' ...
        );
        if ~isfolder(dataDir)
            mkdir(dataDir);
        end

        if ~isfinite(BidsSpec.run) || BidsSpec.run < 1 || floor(BidsSpec.run) ~= BidsSpec.run
            error('Run must be a positive integer.');
        end
        runIndex = double(BidsSpec.run);
        fileStem = effusive.bids.buildStem( ...
            subject, session, runIndex, task, acq, proc, requireTask ...
        );
        collisionPath = cfFirstRecordingCollision(dataDir, fileStem);
        if ~isempty(collisionPath)
            error('Run collision for stem %s at %s.', fileStem, collisionPath);
        end
        BidsSpec.subject = subject;
        BidsSpec.session = session;
        BidsSpec.task = task;
        BidsSpec.acq = acq;
        BidsSpec.proc = proc;

        StorageSpec.folderStoragePath = dataDir;
        StorageSpec.filePath = dataDir;
        StorageSpec.fileStem = fileStem;
        StorageSpec.bfFilename = sprintf('%s_iq', fileStem);
        StorageSpec.pdiFilename = sprintf('%s_pwd', fileStem);
        StorageSpec.rfFilename = sprintf('%s_rf', fileStem);
        StorageSpec.rfTimeTagFilename = sprintf('%s_rftimestamps', fileStem);
        StorageSpec.parameterFilename = sprintf('%s_seq.mat', fileStem);
        StorageSpec.experimentStoragePath = dataDir;
    catch ME
        ok = false;
        message = ME.message;
    end
end


function collisionPath = cfFirstRecordingCollision(dataDir, fileStem)
    collisionPath = '';
    if ~isfolder(dataDir)
        return;
    end

    candidatePaths = { ...
        fullfile(dataDir, sprintf('%s_iq', fileStem)), ...
        fullfile(dataDir, sprintf('%s_pwd', fileStem)), ...
        fullfile(dataDir, sprintf('%s_rf', fileStem)), ...
        fullfile(dataDir, sprintf('%s_rftimestamps', fileStem)), ...
        fullfile(dataDir, sprintf('%s_seq.mat', fileStem)) ...
    };
    for iPath = 1:numel(candidatePaths)
        if exist(candidatePaths{iPath}, 'file')
            collisionPath = candidatePaths{iPath};
            return;
        end
    end
end


function cfWriteBidsSummaryFiles(StorageSpec, BidsSpec, BidsRuntimeState)
    subject = BidsSpec.subject;
    session = BidsSpec.session;

    storageDir = char(string(StorageSpec.filePath));
    relativePaths = {};

    datatypeDir = storageDir;
    [sessionDir, datatype] = fileparts(datatypeDir);
    stemPattern = [char(string(StorageSpec.fileStem)) '*'];
    entries = dir(fullfile(datatypeDir, stemPattern));
    for iEntry = 1:numel(entries)
        if entries(iEntry).isdir
            continue;
        end
        relativePaths{end + 1} = fullfile(datatype, entries(iEntry).name); %#ok<AGROW>
    end

    [~, sessionFolder] = fileparts(sessionDir);
    if ~startsWith(sessionFolder, 'ses-')
        error('Could not infer BIDS session directory from %s.', storageDir);
    end
    if isempty(relativePaths)
        effusive.util.logMessage('No BIDS output files found yet for summary tables.');
        return;
    end

    effusive.bids.upsertSessionsRow( ...
        StorageSpec.storageRootPath, subject, session, BidsRuntimeState.acqTime ...
    );
    effusive.bids.appendScansRows( ...
        StorageSpec.storageRootPath, subject, session, relativePaths, BidsRuntimeState.acqTime ...
    );
end


function zStackState = cfDefaultZStackState()
    zStackState = struct( ...
        'isActive', false, ...
        'errorFlag', false, ...
        'statusCode', int16(0), ...
        'currentSliceZeroBased', int32(-1), ...
        'totalSlices', int32(0), ...
        'targetPositionUm', int32(0), ...
        'sliceIndex', int32(0), ...
        'framesInSlice', int32(0), ...
        'nSlices', int32(0), ...
        'npdiPerSlice', int32(0), ...
        'settleMs', int32(0), ...
        'motorBackendKind', '', ...
        'positionsUm', int32([]), ...
        'positionsMm', double([]), ...
        'sliceAccumulator', single([]), ...
        'stackVolume', single([]), ...
        'bmodeAccumulator', single([]), ...
        'bmodeVolume', single([]) ...
    );
end


function cfWriteStackStatus(sharedMemoryStack, zStackState)
% Write z-stack status to shared memory.
%
% Skips the write when idle and unchanged from the last write (this is
% called on every frameReady frame), since a static idle status has no new
% information for the viewer.

    persistent lastWritten stackBuf

    if isempty(sharedMemoryStack)
        return;
    end

    fieldsChanged = isempty(lastWritten) ...
        || lastWritten.isActive ~= zStackState.isActive ...
        || lastWritten.errorFlag ~= zStackState.errorFlag ...
        || lastWritten.statusCode ~= zStackState.statusCode ...
        || lastWritten.currentSliceZeroBased ~= zStackState.currentSliceZeroBased ...
        || lastWritten.totalSlices ~= zStackState.totalSlices ...
        || lastWritten.targetPositionUm ~= zStackState.targetPositionUm;
    if ~zStackState.isActive && ~fieldsChanged
        return;
    end

    if isempty(stackBuf)
        stackBuf = py.numpy.ndarray( ...
            py.tuple({int32(16)}), dtype=py.numpy.uint8, buffer=sharedMemoryStack.buf ...
        );
    end

    stackBytes = [ ...
        uint8(zStackState.isActive), ...
        uint8(zStackState.errorFlag), ...
        typecast(int16(zStackState.statusCode), 'uint8'), ...
        typecast(int32(zStackState.currentSliceZeroBased), 'uint8'), ...
        typecast(int32(zStackState.totalSlices), 'uint8'), ...
        typecast(int32(zStackState.targetPositionUm), 'uint8') ...
    ];
    srcStack = py.numpy.frombuffer(py.bytes(uint8(stackBytes)), py.numpy.uint8);
    py.numpy.copyto(stackBuf, srcStack);

    lastWritten = struct( ...
        'isActive', zStackState.isActive, ...
        'errorFlag', zStackState.errorFlag, ...
        'statusCode', zStackState.statusCode, ...
        'currentSliceZeroBased', zStackState.currentSliceZeroBased, ...
        'totalSlices', zStackState.totalSlices, ...
        'targetPositionUm', zStackState.targetPositionUm ...
    );
end


function [Info, zStackState, experimentControlOwner] = cfRunZStackStateMachine( ...
    PDI, Bmode, Info, zStackState, experimentControlOwner, sharedMemoryStack, ...
    stackStartFlag, stackAbortFlag, stackUseDummyMotor, ...
    stackStartUm, stackStepUm, stackNSlices, stackNpdiPerSlice, stackSettleMs)

    if ~zStackState.isActive && stackAbortFlag
        effusive.util.logMessage('Ignoring z-stack abort: no active stack.');
        return;
    end

    if ~zStackState.isActive && stackStartFlag
        if ~strcmp(experimentControlOwner, 'manual')
            effusive.util.logMessage( ...
                'Ignoring z-stack start: control owned by %s.', experimentControlOwner ...
            );
            return;
        end
        if stackStepUm == 0
            effusive.util.logMessage('Z-stack start rejected: step size must be non-zero.');
            return;
        end
        if stackNSlices <= 0
            effusive.util.logMessage('Z-stack start rejected: number of slices must be positive.');
            return;
        end
        if stackNpdiPerSlice <= 0
            effusive.util.logMessage('Z-stack start rejected: frames per slice must be positive.');
            return;
        end
        if stackSettleMs < 0
            effusive.util.logMessage('Z-stack start rejected: settle time must be non-negative.');
            return;
        end

        zStackState = cfDefaultZStackState();
        zStackState.statusCode = int16(1);
        zStackState.totalSlices = int32(stackNSlices);
        zStackState.nSlices = int32(stackNSlices);
        zStackState.npdiPerSlice = int32(stackNpdiPerSlice);
        zStackState.settleMs = int32(stackSettleMs);
        zStackState.positionsUm = stackStartUm + stackStepUm * int32(0:double(stackNSlices - 1));
        zStackState.positionsMm = double(zStackState.positionsUm) / 1000.0;
        zStackState.sliceAccumulator = zeros( ...
            size(PDI, 1), size(PDI, 2), double(stackNpdiPerSlice), 'single' ...
        );
        zStackState.stackVolume = zeros( ...
            size(PDI, 1), size(PDI, 2), double(stackNSlices), 'single' ...
        );
        zStackState.bmodeAccumulator = zeros( ...
            size(Bmode, 1), size(Bmode, 2), double(stackNpdiPerSlice), 'single' ...
        );
        zStackState.bmodeVolume = zeros( ...
            size(Bmode, 1), size(Bmode, 2), double(stackNSlices), 'single' ...
        );
        zStackState.sliceIndex = int32(1);
        zStackState.currentSliceZeroBased = int32(0);

        cfWriteStackStatus(sharedMemoryStack, zStackState);
        effusive.util.logMessage('Z-stack ownership claimed.');
        experimentControlOwner = 'zstack';

        try
            Info = cfEnsureMotorBackend(Info, stackUseDummyMotor, 'Z-stack');
            zStackState.motorBackendKind = Info.motorHandle.kind;
            zStackState.isActive = true;
            [Info, zStackState] = cfMoveToZStackSlice( ...
                Info, zStackState, sharedMemoryStack, int32(1) ...
            );
            return;
        catch stackError
            [Info, zStackState] = cfTerminateZStack( ...
                Info, zStackState, sharedMemoryStack, int16(8), stackError.message, false ...
            );
            experimentControlOwner = 'manual';
            return;
        end
    end

    if ~zStackState.isActive
        return;
    end

    if stackAbortFlag
        [Info, zStackState] = cfTerminateZStack( ...
            Info, zStackState, sharedMemoryStack, int16(7), 'Z-stack abort requested.', true ...
        );
        experimentControlOwner = 'manual';
        return;
    end

    try
        zStackState.framesInSlice = zStackState.framesInSlice + int32(1);
        zStackState.sliceAccumulator(:, :, zStackState.framesInSlice) = single(PDI);
        zStackState.bmodeAccumulator(:, :, zStackState.framesInSlice) = single(Bmode);

        if zStackState.framesInSlice < zStackState.npdiPerSlice
            zStackState.statusCode = int16(4);
            return;
        end

        zStackState.statusCode = int16(5);
        cfWriteStackStatus(sharedMemoryStack, zStackState);
        zStackState.stackVolume(:, :, zStackState.sliceIndex) = mean( ...
            zStackState.sliceAccumulator(:, :, 1:zStackState.npdiPerSlice), 3 ...
        );
        zStackState.bmodeVolume(:, :, zStackState.sliceIndex) = mean( ...
            zStackState.bmodeAccumulator(:, :, 1:zStackState.npdiPerSlice), 3 ...
        );
        effusive.util.logMessage( ...
            'Z-stack slice %d/%d complete at %.3f mm.', ...
            zStackState.sliceIndex, zStackState.nSlices, ...
            zStackState.positionsMm(zStackState.sliceIndex) ...
        );
        zStackState.framesInSlice = int32(0);

        if zStackState.sliceIndex >= zStackState.nSlices
            zStackState.statusCode = int16(6);
            cfWriteStackStatus(sharedMemoryStack, zStackState);
            outputPaths = effusive.util.exportZStack( ...
                zStackState.stackVolume, zStackState.bmodeVolume, zStackState ...
            );
            zStackState.isActive = false;
            zStackState.currentSliceZeroBased = int32(-1);
            zStackState.totalSlices = int32(0);
            zStackState.targetPositionUm = int32(0);
            % Keep completion status latched until next stack start so napari
            % can reliably observe terminal completion and issue the standard
            % UI pause command on the Python side.
            cfWriteStackStatus(sharedMemoryStack, zStackState);
            experimentControlOwner = 'manual';
            effusive.util.logMessage('Z-stack acquisition completed.');
            effusive.util.logMessage('Z-stack completion latched; viewer will request pause.');
            effusive.util.logMessage('Z-stack PDI NIfTI exported -> %s', outputPaths.pdiPath);
            effusive.util.logMessage('Z-stack B-mode NIfTI exported -> %s', outputPaths.bmodePath);
            effusive.util.logMessage('Z-stack JSON sidecar exported -> %s', outputPaths.pwdJsonPath);
            if ~isempty(outputPaths.bmodeJsonPath)
                effusive.util.logMessage('Z-stack JSON sidecar exported -> %s', outputPaths.bmodeJsonPath);
            end
            effusive.util.logMessage('Z-stack ownership released.');
            return;
        end

        zStackState.sliceIndex = zStackState.sliceIndex + int32(1);
        zStackState.currentSliceZeroBased = zStackState.sliceIndex - int32(1);
        zStackState.sliceAccumulator(:, :, :) = single(0);
        zStackState.bmodeAccumulator(:, :, :) = single(0);
        [Info, zStackState] = cfMoveToZStackSlice( ...
            Info, zStackState, sharedMemoryStack, zStackState.sliceIndex ...
        );
    catch stackError
        [Info, zStackState] = cfTerminateZStack( ...
            Info, zStackState, sharedMemoryStack, int16(8), stackError.message, false ...
        );
        experimentControlOwner = 'manual';
    end
end


function [Info, zStackState] = cfMoveToZStackSlice( ...
    Info, zStackState, sharedMemoryStack, sliceIndex)

    zStackState.statusCode = int16(2);
    zStackState.targetPositionUm = zStackState.positionsUm(sliceIndex);
    cfWriteStackStatus(sharedMemoryStack, zStackState);
    effusive.util.logMessage( ...
        'Z-stack moving to slice %d/%d -> %.3f mm.', ...
        sliceIndex, zStackState.nSlices, zStackState.positionsMm(sliceIndex) ...
    );
    Info.motorHandle = effusive.motor.moveToPosition( ...
        Info.motorHandle, zStackState.positionsMm(sliceIndex) ...
    );
    zStackState.statusCode = int16(3);
    cfWriteStackStatus(sharedMemoryStack, zStackState);
    if zStackState.settleMs > 0
        effusive.util.logMessage('Z-stack settling for %d ms.', zStackState.settleMs);
        pause(double(zStackState.settleMs) / 1000.0);
    end
    zStackState.statusCode = int16(4);
    zStackState.framesInSlice = int32(0);
    cfWriteStackStatus(sharedMemoryStack, zStackState);
end


function [Info, zStackState, experimentControlOwner] = cfHandleStackJogRequest( ...
    Info, zStackState, experimentControlOwner, sharedMemoryStack, ...
    stackUseDummyMotor, stackJogUm)

    if stackJogUm == 0
        return;
    end
    if zStackState.isActive
        effusive.util.logMessage('Ignoring stack jog: z-stack is currently active.');
        return;
    end
    if ~strcmp(experimentControlOwner, 'manual')
        effusive.util.logMessage( ...
            'Ignoring stack jog: control owned by %s.', experimentControlOwner ...
        );
        return;
    end

    try
        Info = cfEnsureMotorBackend(Info, stackUseDummyMotor, 'Stack jog');
        if ~isfield(Info.motorHandle, 'currentPositionMm') || isnan(Info.motorHandle.currentPositionMm)
            Info.motorHandle.currentPositionMm = 0.0;
        end
        targetPositionMm = Info.motorHandle.currentPositionMm + double(stackJogUm) / 1000.0;
        Info.motorHandle = effusive.motor.moveToPosition(Info.motorHandle, targetPositionMm);
        zStackState.targetPositionUm = int32(round(targetPositionMm * 1000.0));
        cfWriteStackStatus(sharedMemoryStack, zStackState);
        effusive.util.logMessage('Stack jog move -> %.3f mm (delta %.3f mm).', ...
            targetPositionMm, double(stackJogUm) / 1000.0);
    catch jogError
        effusive.util.logMessage('Stack jog error: %s', jogError.message);
        zStackState.errorFlag = true;
        zStackState.statusCode = int16(8);
        zStackState.currentSliceZeroBased = int32(-1);
        zStackState.totalSlices = int32(0);
        zStackState.targetPositionUm = int32(0);
        cfWriteStackStatus(sharedMemoryStack, zStackState);
    end
end


function [Info, zStackState] = cfTerminateZStack( ...
    Info, zStackState, sharedMemoryStack, statusCode, reason, doFullReset)
% Stop the z-stack motor, reset stack state, and log the outcome.
%
% Parameters
% ----------
% statusCode : int16
%     Terminal status code (7 = aborting, 8 = error).
% reason : char
%     Message logged for the termination.
% doFullReset : logical
%     `true` for a user/VSX-requested abort: announces `statusCode` before
%     stopping the motor, then resets to `cfDefaultZStackState()`. `false`
%     for a state-machine failure: skips the pre-stop announcement, sets
%     `errorFlag` and `statusCode` directly, and leaves the rest of
%     `zStackState` (accumulators, volumes) untouched for inspection.

    if doFullReset
        zStackState.statusCode = statusCode;
        cfWriteStackStatus(sharedMemoryStack, zStackState);
        effusive.util.logMessage('%s', reason);
    else
        effusive.util.logMessage('Z-stack error: %s', reason);
    end

    if isfield(Info, 'motorHandle') && ~isempty(Info.motorHandle)
        try
            effusive.motor.stopMotion(Info.motorHandle);
        catch stopError
            effusive.util.logMessage( ...
                'Warning: z-stack motor stop failed: %s', stopError.message ...
            );
        end
    end

    if doFullReset
        zStackState = cfDefaultZStackState();
        cfWriteStackStatus(sharedMemoryStack, zStackState);
        effusive.util.logMessage('Z-stack ownership released.');
    else
        zStackState.isActive = false;
        zStackState.errorFlag = true;
        zStackState.statusCode = statusCode;
        zStackState.currentSliceZeroBased = int32(-1);
        zStackState.totalSlices = int32(0);
        zStackState.targetPositionUm = int32(0);
        cfWriteStackStatus(sharedMemoryStack, zStackState);
        effusive.util.logMessage('Z-stack ownership released after error.');
    end
end


function Info = cfEnsureMotorBackend(Info, useDummyMotor, contextLabel)
% Create the motor backend if missing or of the wrong kind.
%
% Parameters
% ----------
% useDummyMotor : logical
%     `true` selects the dummy backend, `false` the real motor.
% contextLabel : char
%     Prefix for the log message identifying the caller (e.g. `'Z-stack'`
%     or `'Stack jog'`).

    requestedBackendKind = 'real';
    if useDummyMotor
        requestedBackendKind = 'dummy';
    end
    if ~isfield(Info, 'motorHandle') || isempty(Info.motorHandle) ...
            || ~isfield(Info.motorHandle, 'kind') ...
            || ~strcmp(Info.motorHandle.kind, requestedBackendKind)
        Info.motorHandle = effusive.motor.createBackend(useDummyMotor);
        effusive.util.logMessage('%s motor backend -> %s.', contextLabel, Info.motorHandle.kind);
    end
end
