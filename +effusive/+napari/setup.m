function setup()
% Initialize Effusive for napari-driven acquisition.
%
% Called synchronously from the Python `matlab_worker.py` subprocess
% after shared memory segments have been created by the napari viewer.
% Returns after all setup is complete.  The worker then calls `VSX()`,
% which blocks for the duration of the acquisition session.
%
% Notes
% -----
% Base workspace variables (set by `matlab_worker.py` before this
% function is called):
%
% - `EFFUSIVE_PATH` (char): Path to the Effusive repo root.
% - `probeName` (char): Probe identifier. One of `'L22-14v'`,
%   `'L35-16vX'`, or `'MiniProbe'`.
% - `transmitFrequency` (double): Transmit frequency [MHz].
% - `storagePath` (char): Root directory for saved session folders.
% - `sessionId` (char): Session identifier shared with the viewer log.
% - `voltage` (double): Initial transmit voltage [V].
% - `transmitAperturePercentage` (double): Initial TX aperture [%].
% - `receiveAperturePercentage` (double): Initial RX aperture [%].
% - `txrxFrameRate` (double): Acquisition frame rate [Hz].
% - `transmitPulseLength` (double): Pulse length [half cycles].
% - `nTransmissions` (double): Number of compounded angles.
% - `nRepeats` (double): Ensemble size.
% - `planewaveOpeningAngle` (double): Total steering angle range [deg].
% - `desiredEndDepthMm` (double): Imaging depth [mm].
% - `speedOfSound` (double): Speed of sound [m/s].
% - `beamformerType` (char): EchoFrame beamformer, `'Fourier'` or `'DAS'`.
% - `dasFNumberAuto` (logical): Compute DAS receive f-number from probe metadata.
% - `dasFNumber` (double): Manual DAS receive f-number.
% - `tgcGain` (double): Initial TGC gain.
% - `tgcControlPoints` (double): Initial Verasonics TGC control points.
% - `simulateMode` (double): `0` for real hardware, `1` for Media
%   simulation, `2` for `RcvData` playback simulation.
% - `rcvDataMatFile` (char, optional): MAT file containing `RcvData`
%   used when `simulateMode = 2`.
% - `sharedMemoryNameMeta` (char): Shared memory name for the cf_meta
%   segment.
% - `sharedMemoryNameBmode` (char): Shared memory name for the cf_bmode
%   segment.
% - `sharedMemoryNamePdi` (char): Shared memory name for the cf_pdi
%   segment.
% - `sharedMemoryNameCmd` (char): Shared memory name for the cf_cmd
%   segment.
% - `sharedMemoryNameStack` (char): Shared memory name for the cf_stack
%   segment.
% - `sharedMemoryNameRf` (char): Shared memory name for the cf_rf
%   segment.
% - `sharedMemoryNameAck` (char): Shared memory name for the cf_ack
%   segment.
%
% After `effusive.napari.setup` returns, the cf_meta segment
% contains:
%
% - `frame_counter` (uint64): `0` -- incremented by
%   `publishProcessedFrame` during acquisition.
% - `nz` (int32): Image height in pixels.
% - `nx` (int32): Image width in pixels.
% - `z_start_mm` (float32): Depth-axis start [mm].
% - `z_end_mm` (float32): Depth-axis end [mm].
% - `x_start_mm` (float32): Lateral-axis start [mm].
% - `x_end_mm` (float32): Lateral-axis end [mm].
% - `runtime_flags` (uint32): Runtime bitmask where bit 0 indicates save
%   active and bit 1 indicates freeze active.
% - `ensemble_time_s` (float64): Hardware time tag of the current ensemble
%   in seconds since counter reset; `0` in simulate mode.
%
% After `effusive.napari.setup` returns, the base workspace also
% contains `FrameRuntimeState` (struct), the inter-callback data bus used
% by `processRFEnsembleBlock`, `processRuntimeControl`, and
% `publishProcessedFrame`. All fields are empty/false at startup and
% populated on the first processed frame.

    %% Read Python-provided parameters from base workspace.
    EFFUSIVE_PATH            = evalin('base', 'EFFUSIVE_PATH');
    probeName                   = evalin('base', 'probeName');
    transmitFrequency           = evalin('base', 'transmitFrequency');
    storagePath                 = evalin('base', 'storagePath');
    sessionId                   = evalin('base', 'sessionId');
    bidsSubject                 = evalin('base', 'bidsSubject');
    bidsSession                 = evalin('base', 'bidsSession');
    bidsTask                    = evalin('base', 'bidsTask');
    bidsAcq                     = evalin('base', 'bidsAcq');
    bidsProc                    = evalin('base', 'bidsProc');
    bidsRun                     = evalin('base', 'bidsRun');
    voltage                     = evalin('base', 'voltage');
    transmitAperturePercentage  = evalin('base', 'transmitAperturePercentage');
    receiveAperturePercentage   = evalin('base', 'receiveAperturePercentage');
    txrxFrameRate               = evalin('base', 'txrxFrameRate');
    transmitPulseLength         = evalin('base', 'transmitPulseLength');
    nTransmissions              = evalin('base', 'nTransmissions');
    nRepeats                    = evalin('base', 'nRepeats');
    opening_angle               = evalin('base', 'planewaveOpeningAngle');
    desiredEndDepthMm           = evalin('base', 'desiredEndDepthMm');
    if evalin('base', 'exist(''speedOfSound'', ''var'') == 1')
        speedOfSound = double(evalin('base', 'speedOfSound'));
    else
        speedOfSound = 1510;
    end
    if evalin('base', 'exist(''beamformerType'', ''var'') == 1')
        beamformerType = char(evalin('base', 'beamformerType'));
    else
        beamformerType = 'Fourier';
    end
    if evalin('base', 'exist(''dasFNumberAuto'', ''var'') == 1')
        dasFNumberAuto = logical(evalin('base', 'dasFNumberAuto'));
    else
        dasFNumberAuto = false;
    end
    if evalin('base', 'exist(''dasFNumber'', ''var'') == 1')
        dasFNumber = double(evalin('base', 'dasFNumber'));
    else
        dasFNumber = 0.71;
    end
    tgcGain                     = evalin('base', 'tgcGain');
    tgcControlPoints            = evalin('base', 'tgcControlPoints');
    simulateMode                = evalin('base', 'simulateMode');
    if evalin('base', 'exist(''rcvDataMatFile'', ''var'') == 1')
        rcvDataMatFile = evalin('base', 'rcvDataMatFile');
    else
        rcvDataMatFile = '';
    end

    %% Add Effusive path.
    addpath(genpath(EFFUSIVE_PATH));

    %% Storage spec.
    initialStorageConfig = cfReadInitialStorageConfig(evalin('base', 'sharedMemoryNameCmd'));
    if isempty(sessionId)
        sessionId = char(datetime('now', 'Format', 'yyyy-MM-dd_HHmmss'));
    end
    sessionPath = fullfile( ...
        storagePath, 'effusive_runtime', sessionId ...
    );
    fileStem = '';
    try
        sessionLabel = char(string(bidsSession));
        if isempty(strtrim(sessionLabel))
            sessionLabel = char(datetime('today', 'Format', 'yyyyMMdd'));
        end
        effusive.bids.buildDataDirectory( ...
            storagePath, bidsSubject, sessionLabel, 'fusi' ...
        );
        resolvedRun = double(bidsRun);
        fileStem = effusive.bids.buildStem( ...
            bidsSubject, sessionLabel, resolvedRun, bidsTask, bidsAcq, bidsProc, true ...
        );
        bidsSession = sessionLabel;
    catch ME
        effusive.util.logMessage( ...
            'BIDS manual storage preview unavailable during setup: %s', ...
            ME.message ...
        );
    end
    if ~isfolder(sessionPath)
        mkdir(sessionPath);
    end
    StorageSpec.storageRootPath      = storagePath;
    StorageSpec.folderStoragePath     = sessionPath;
    StorageSpec.filePath              = sessionPath;
    StorageSpec.fileStem              = fileStem;
    StorageSpec.bfFilename            = '';
    StorageSpec.pdiFilename           = '';
    StorageSpec.rfFilename            = '';
    StorageSpec.rfTimeTagFilename     = '';
    StorageSpec.parameterFilename     = '';
    if ~isempty(fileStem)
        StorageSpec.bfFilename = sprintf('%s_iq', fileStem);
        StorageSpec.pdiFilename = sprintf('%s_pwd', fileStem);
        StorageSpec.rfFilename = sprintf('%s_rf', fileStem);
        StorageSpec.rfTimeTagFilename = sprintf('%s_rftimestamps', fileStem);
        StorageSpec.parameterFilename = sprintf('%s_seq.mat', fileStem);
    end
    StorageSpec.experimentStoragePath = '';

    BidsSpec = struct( ...
        'subject', char(string(bidsSubject)), ...
        'session', char(string(bidsSession)), ...
        'task', char(string(bidsTask)), ...
        'acq', char(string(bidsAcq)), ...
        'proc', char(string(bidsProc)), ...
        'run', double(bidsRun) ...
    );
    StorageSpec.saveRF                = initialStorageConfig.saveRF;
    StorageSpec.saveBF                = initialStorageConfig.saveBF;
    StorageSpec.savePDI               = initialStorageConfig.savePDI;
    StorageSpec.saveRFTimeTag         = initialStorageConfig.saveRFTimeTag;
    StorageSpec.preallocateFullFile   = false;

    %% Info struct.
    Info.acquisitionsToTimeline = 20;
    Info.vsxCallTimer           = tic;
    Info.data_counter           = 0;
    Info.save_end_flag          = 0;
    Info.number_of_pdi          = 0;
    Info.processCounter         = 0;
    Info.frame_counter          = 1;
    Info.npdi_per_slice         = 5;
    Info.islice_in_stack        = 0;
    Info.registration_stack     = 0;
    Info.motorHandle            = [];
    Info.verasonics_file_name   = fullfile( ...
        sessionPath, sprintf('vsx_effusive_%s', sessionId) ...
    );

    ExperimentSpec.updateExperiment = false;

    %% Configure probe sequence.
    effusive.util.logMessage('Configuring probe: %s', probeName);
    samplingMode = cfDefaultSamplingMode(probeName);
    sequence = effusive.sequences.configurePowerDopplerSequence( ...
        probeName, ...
        txrxFrameRate=txrxFrameRate, ...
        transmitPulseLength=transmitPulseLength, ...
        transmitFrequency=transmitFrequency, ...
        transmitAperturePercentage=transmitAperturePercentage, ...
        receiveAperturePercentage=receiveAperturePercentage, ...
        desiredEndDepthMm=desiredEndDepthMm, ...
        nTransmissions=nTransmissions, ...
        nRepeats=nRepeats, ...
        planewaveOpeningAngle=opening_angle, ...
        samplingMode=samplingMode, ...
        tgcGain=tgcGain, ...
        tgcControlPoints=tgcControlPoints, ...
        initialTransmitVoltage=voltage, ...
        c0=speedOfSound);

    % Verasonics sequence structs.
    Trans = sequence.Trans;
    Resource = sequence.Resource;
    Resource.Parameters.simulateMode = double(simulateMode);
    Resource.Parameters.GUI = 'effusive.napari.stubGui';
    if Resource.Parameters.simulateMode == 1
        if ~isfield(Resource, 'System') || isempty(Resource.System)
            Resource.System = struct();
        end
        % Keep simulation independent of hardware while preserving normal
        % transfer/update behavior used by waitForTransferComplete.
        Resource.System.Product = 'SoftwareOnly';
    end
    TX = sequence.TX;
    TW = sequence.TW;
    Receive = sequence.Receive;
    TGC = sequence.TGC;
    SeqControl = sequence.SeqControl;
    Event = sequence.Event;
    Process = sequence.Process;
    RcvProfile = sequence.RcvProfile;
    TPC = sequence.TPC;

    % EchoFrame specs structs.
    ProbeSpec = sequence.ProbeSpec;
    TransmitSpec = sequence.TransmitSpec;
    ReceiveSpec = sequence.ReceiveSpec;
    ReconSpec = sequence.ReconSpec;

    if Resource.Parameters.simulateMode == 2
        [Resource, ReceiveSpec, Receive] = cfConfigureRcvDataPlayback( ...
            Resource, Trans, ReceiveSpec, Receive, rcvDataMatFile ...
        );
    end

    triggerOutEventIndex = sequence.triggerOutEventIndex;

    %% Control variables (read by processRFEnsembleBlock and processRuntimeControl).
    storeEchoFrameOutput = initialStorageConfig.initialized;
    svdUpdateFlag = 0;
    % Fractional threshold (0-1), matches PDISpec.threshold.
    svdThreshold = single(0.40); 
    updateCropping = 0;
    freeze               = 0; % freeze flag for VSX acquisition control
    freezeResumedByNapari = 0; % resume ack flag emitted on first frame after unfreeze

    %% Translate Verasonics structs to EchoFrame structs.
    [ProbeSpec, TransmitSpec, ReceiveSpec] = effusive.echoframe.translateVsxToEchoFrameStructs( ...
        Resource, Trans, TX, Receive, ProbeSpec, TransmitSpec, ReceiveSpec ...
    );

    %% Cropping parameters.
    ReconSpec.cropBF         = logical(false);
    ReconSpec.croppingROI    = [0; 128; 0; 128];

    %% Initialize EchoFrame image reconstruction.
    effusive.util.logMessage('Initializing image reconstruction...');
    ReconSpec.method = beamformerType;
    ReconSpec.beamformerType = beamformerType;
    ReconSpec.dasFNumberAuto = dasFNumberAuto;
    ReconSpec.dasFNumber = dasFNumber;
    ReconSpec.bfDataType          = 'complex single';
    ReconSpec.filterFrequencies   = logical(false);
    ReconSpec.nDims               = 2;
    ReconSpec.getBF               = logical(true);
    ReconSpec.getPDI              = logical(true);
    ReconSpec.nBuffers            = 2;
    [ProbeSpec, ReceiveSpec, ReconSpec] = effusive.echoframe.initializeImageReconstruction( ...
        ProbeSpec, TransmitSpec, ReceiveSpec, ReconSpec ...
    );

    %% PDI parameters.
    PDISpec.ensembleSize = ReceiveSpec.nRepeats;
    PDISpec.threshold    = single(0.4);
    PDISpec.shiftSize    = ReceiveSpec.nRepeats;
    PDISpec.cropPDI      = logical(false);
    PDISpec.svdMethod    = 'Covariance';

    %% Validate EchoFrame inputs.
    [ ...
        ProbeSpec, ...
        TransmitSpec, ...
        ReceiveSpec, ...
        ReconSpec, ...
        PDISpec ...
    ] = effusive.echoframe.validateEchoFrameStructs( ...
        ProbeSpec, TransmitSpec, ReceiveSpec, ReconSpec, PDISpec ...
    );

    rfSamplesPerFrame = double(ReceiveSpec.nSamples) ...
        * double(ReceiveSpec.nTransmissions) ...
        * double(ReceiveSpec.nRepeats) ...
        * double(Resource.Parameters.numRcvChannels);
    effusive.util.logMessage( ...
        ['EchoFrame init: probe=%s fc=%.3f MHz nSamples=%d nTx=%d ' ...
         'nRepeats=%d channels=%d rowsPerFrame=%d recon=[%d x %d] ' ...
         'rfSamples/frame=%.3g'], ...
        probeName, ...
        double(Trans.frequency), ...
        int32(ReceiveSpec.nSamples), ...
        int32(ReceiveSpec.nTransmissions), ...
        int32(ReceiveSpec.nRepeats), ...
        int32(Resource.Parameters.numRcvChannels), ...
        int32(Resource.RcvBuffer(1).rowsPerFrame), ...
        int32(numel(ReconSpec.zAxis)), ...
        int32(numel(ReconSpec.xAxis)), ...
        rfSamplesPerFrame ...
    );

    %% Initialize EchoFrame MEX.
    if initialStorageConfig.initialized
        [BFStorageSpec, PDIStorageSpec, RFTimeTagStorageSpec, RFStorageSpec] = effusive.echoframe.configureEchoFrameStorageSpecs( ...
            'init', ...
            StorageSpec, ...
            ReceiveSpec, ...
            ReconSpec, ...
            PDISpec, ...
            ExperimentSpec, ...
            TransmitSpec, ...
            ProbeSpec ...
        );
        % effusive.echoframe.configureEchoFrameStorageSpecs modifies StorageSpec internally and assigns it back to the base
        % workspace.
        StorageSpec = evalin('base', 'StorageSpec');
        effusive.util.logMessage( ...
            'Storage path: %s', StorageSpec.experimentStoragePath ...
        );
        echoframe_mex( ...
            'init', ...
            ReceiveSpec, ...
            ReconSpec, ...
            PDISpec, ...
            BFStorageSpec, ...
            PDIStorageSpec, ...
            RFTimeTagStorageSpec, ...
            RFStorageSpec ...
        );
    else
        effusive.util.logMessage('Storage disabled at startup.');
        echoframe_mex('init', ReceiveSpec, ReconSpec, PDISpec);
    end

    %% Write image geometry to cf_meta shared memory segment.
    % Determine output image size from ReconSpec z/x axes.
    % After cropping ROI: rows = croppingROI(2)-croppingROI(1), cols = (4)-(3)
    % If not cropping, use full z/x axis lengths.
    nz_full = numel(ReconSpec.zAxis);
    nx_full = numel(ReconSpec.xAxis);
    nz_out  = int32(nz_full);
    nx_out  = int32(nx_full);

    % zAxis and xAxis units: assumed to be in mm already.
    z_start_mm = single(ReconSpec.zAxis(1));
    z_end_mm   = single(ReconSpec.zAxis(end));
    x_start_mm = single(ReconSpec.xAxis(1));
    x_end_mm   = single(ReconSpec.xAxis(end));

    if isfield(ReconSpec, 'dasFNumber')
        effectiveDasFNumber = single(ReconSpec.dasFNumber);
    else
        effectiveDasFNumber = single(NaN);
    end
    cfMetaWrite( ...
        evalin('base', 'sharedMemoryNameMeta'), ...
        nz_out, ...
        nx_out, ...
        z_start_mm, ...
        z_end_mm, ...
        x_start_mm, ...
        x_end_mm, ...
        effusive.napari.metaRuntimeFlags(storeEchoFrameOutput, logical(false)), ...
        effectiveDasFNumber ...
    );
    effusive.util.logMessage('cf_meta written: nz=%d nx=%d z=[%.1f, %.1f] x=[%.1f, %.1f] mm', ...
        nz_out, nx_out, z_start_mm, z_end_mm, x_start_mm, x_end_mm);

    %% Assign all base workspace variables required by VSX and callbacks.
    assignin('base', 'StorageSpec',              StorageSpec);
    assignin('base', 'BidsSpec',                 BidsSpec);
    assignin('base', 'Info',                     Info);
    assignin('base', 'ExperimentSpec',           ExperimentSpec);
    assignin('base', 'Resource',                 Resource);
    assignin('base', 'Trans',                    Trans);
    assignin('base', 'TX',                       TX);
    assignin('base', 'TW',                       TW);
    assignin('base', 'Receive',                  Receive);
    assignin('base', 'TGC',                      TGC);
    assignin('base', 'SeqControl',               SeqControl);
    assignin('base', 'Event',                    Event);
    assignin('base', 'Process',                  Process);
    assignin('base', 'RcvProfile',               RcvProfile);
    assignin('base', 'TPC',                      TPC);
    assignin('base', 'ProbeSpec',                ProbeSpec);
    assignin('base', 'TransmitSpec',             TransmitSpec);
    assignin('base', 'ReceiveSpec',              ReceiveSpec);
    assignin('base', 'ReconSpec',                ReconSpec);
    assignin('base', 'PDISpec',                  PDISpec);
    assignin('base', 'storageConfigApplied',     initialStorageConfig);
    assignin('base', 'storeEchoFrameOutput',     storeEchoFrameOutput);
    assignin('base', 'svdUpdateFlag',            svdUpdateFlag);
    assignin('base', 'svdThreshold',             svdThreshold);
    assignin('base', 'updateCropping',           updateCropping);
    assignin('base', 'freeze',                   freeze);
    assignin('base', 'freezeResumedByNapari',    freezeResumedByNapari);
    assignin('base', 'cfFreezeButtonHandle',     []);
    % Register freeze timer callback so VSX can check for unfreeze and stop
    % commands while acquisition is paused (uses "pull" technology vs VSX GUI's "push").
    assignin('base', 'Mcr_FreezeTimerFunction',  'effusive.napari.freezeCheck');
    assignin('base', 'triggerOutEventIndex',     triggerOutEventIndex);
    assignin('base', 'experimentControlOwner',   'manual');
    FrameRuntimeState = struct( ...
        'PDI',                    single([]), ...
        'Bmode',                  single([]), ...
        'RF',                     int16([]), ...
        'ensemble_time_s',        double(0), ...
        'publishRfSnapshot',      false, ...
        'frameReady',             false, ...
        't_frame_start_tic',      uint64(0), ...
        't_last_publish_end_tic', uint64(0), ...
        't_vsx_wait_s',           double(0) ...
    );
    BidsRuntimeState = struct( ...
        'saveActive', false, ...
        'acqTime', '', ...
        'summaryWritten', false ...
    );
    assignin('base', 'FrameRuntimeState',        FrameRuntimeState);
    assignin('base', 'BidsRuntimeState',         BidsRuntimeState);

    %% Save base workspace MAT file required by VSX startup
    % setup is a function, so plain save() would only capture local
    % variables. evalin runs save() in the base workspace, which contains
    % all the variables written via assignin above.
    % filename must also be in the base workspace so VSX can read it on startup.
    filename = Info.verasonics_file_name;
    assignin('base', 'filename', filename);
    evalin('base', 'save(filename)');
    effusive.util.logMessage('Saved base workspace to %s.mat', filename);
    close all
    effusive.util.logMessage('Setup complete. VSX can now be started.');
end


function [Resource, ReceiveSpec, Receive] = cfConfigureRcvDataPlayback(Resource, Trans, ReceiveSpec, Receive, rcvDataMatFile)
% Configure simulation mode 2 playback from `RcvData`.

    % Base workspace variables.
    hasRcvDataInBase = evalin('base', 'exist(''RcvData'', ''var'') == 1');

    rcvDataMatFile = char(string(rcvDataMatFile));
    rcvDataMatFile = strtrim(rcvDataMatFile);

    if ~isempty(rcvDataMatFile)
        if ~isfile(rcvDataMatFile)
            error('rcvDataMatFile not found: %s', rcvDataMatFile);
        end
        loadedData = load(rcvDataMatFile, 'RcvData');
        if ~isfield(loadedData, 'RcvData')
            error('MAT file %s does not contain RcvData.', rcvDataMatFile);
        end
        RcvData = loadedData.RcvData;
        assignin('base', 'RcvData', RcvData);
        effusive.util.logMessage('Loaded RcvData from %s.', rcvDataMatFile);
    elseif hasRcvDataInBase
        RcvData = evalin('base', 'RcvData');
        effusive.util.logMessage('Using preloaded RcvData from base workspace.');
    else
        error(['simulateMode=2 requires RcvData. Provide rcvDataMatFile ' ...
               'or preload RcvData in the base workspace.']);
    end

    if ~iscell(RcvData)
        RcvData = {RcvData};
        assignin('base', 'RcvData', RcvData);
    end

    if isempty(RcvData) || isempty(RcvData{1})
        error('RcvData must be a non-empty array or cell array.');
    end

    playbackData = RcvData{1};
    if ~isa(playbackData, 'int16')
        error('RcvData{1} must be int16 for Verasonics receive-buffer playback.');
    end
    if ndims(playbackData) > 3
        error('RcvData{1} must be 2-D or 3-D [rows, channels, frames].');
    end

    nRows = double(size(playbackData, 1));
    nChannels = double(size(playbackData, 2));
    nFrames = double(size(playbackData, 3));

    expectedChannels = double(Resource.Parameters.numRcvChannels);
    if nChannels ~= expectedChannels
        error('RcvData channel count (%d) does not match numRcvChannels (%d).', ...
            int32(nChannels), int32(expectedChannels));
    end

    if nFrames < double(ReceiveSpec.nBuffers)
        error(['RcvData has %d frame(s), but the sequence expects at least %d. ' ...
               'Increase RcvData frames or reduce ReceiveSpec.nBuffers.'], ...
            int32(nFrames), int32(ReceiveSpec.nBuffers));
    end

    transmissionsPerFrame = double(ReceiveSpec.nTransmissions) ...
        * double(ReceiveSpec.nRepeats);
    if mod(nRows, transmissionsPerFrame) ~= 0
        error(['RcvData rowsPerFrame (%d) is not divisible by nTransmissions*nRepeats ' ...
               '(%d). Check playback settings.'], ...
            int32(nRows), int32(transmissionsPerFrame));
    end

    ReceiveSpec.nSamples = nRows / transmissionsPerFrame;
    ReceiveSpec.nSamplesIQ = ReceiveSpec.nSamples / 2;

    wvc0 = (Trans.frequency * 1e6 / Resource.Parameters.speedOfSound) ...
        * ReceiveSpec.samples_per_wavelength;
    ReceiveSpec.actualEndDepthMm = (ReceiveSpec.nSamples / wvc0 * 1e3) / 2 ...
        + ReceiveSpec.startDepthMm;
    ReceiveSpec.endDepthWavelengths = ReceiveSpec.actualEndDepthMm * 1e-3 ...
        * Trans.frequency * 1e6 / Resource.Parameters.speedOfSound;

    Resource.RcvBuffer(1).datatype = 'int16';
    Resource.RcvBuffer(1).rowsPerFrame = nRows;
    Resource.RcvBuffer(1).colsPerFrame = nChannels;
    Resource.RcvBuffer(1).numFrames = nFrames;

    endDepth = ReceiveSpec.lensOffset + ReceiveSpec.endDepthWavelengths;
    for iReceive = 1:numel(Receive)
        Receive(iReceive).callMediaFunc = 0;
        Receive(iReceive).endDepth = endDepth;
    end

    effusive.util.logMessage( ...
        ['Configured simulateMode=2 playback: rowsPerFrame=%d channels=%d ' ...
         'frames=%d nSamples=%d.'], ...
        int32(nRows), int32(nChannels), int32(nFrames), int32(ReceiveSpec.nSamples) ...
    );
end


function storageConfig = cfReadInitialStorageConfig(sharedMemoryNameCmd)
% Read the initial save configuration from the napari command channel.
%
% Parameters
% ----------
% sharedMemoryNameCmd : char
%     Shared-memory segment name for the napari command channel.
%
% Returns
% -------
% storageConfig : struct
%     Effective startup save configuration with `saveRF`,
%     `saveRFTimeTag`, `saveBF`, `savePDI`, and `initialized` fields.
%
% Notes
% -----
% The master save flag gates all per-modality save flags so startup mirrors
% the UI state exactly and does not initialize storage when saving is off.

    sharedMemoryCmd = py.multiprocessing.shared_memory.SharedMemory( ...
        name=sharedMemoryNameCmd, create=false ...
    );
    cmd = uint8(py.array.array('B', sharedMemoryCmd.buf));
    sharedMemoryCmd.close();

    saveMaster = logical(cmd(3));
    storageConfig = effusive.control.requestedStorageConfig( ...
        saveMaster, logical(cmd(31)), logical(cmd(32)), logical(cmd(33)), logical(cmd(34)) ...
    );
end


function cfMetaWrite(sharedMemoryName, nz, nx, zStartMm, zEndMm, xStartMm, xEndMm, runtimeFlags, dasFNumber)
% Write image geometry fields to the cf_meta shared memory segment.
% Writes the setup-owned bytes of the 48-byte cf_meta segment (little-endian);
% bytes 36:44 (`ensemble_time_s`, float64) stay zero-initialized here and
% are populated per frame by `publishProcessedFrame`.
%
% ```
% [0:8]   uint64  frame_counter  (keep at 0, incremented by publishProcessedFrame)
% [8:12]  int32   nz
% [12:16] int32   nx
% [16:20] float32 z_start_mm
% [20:24] float32 z_end_mm
% [24:28] float32 x_start_mm
% [28:32] float32 x_end_mm
% [32:36] uint32  runtime_flags (bit 0 = save active, bit 1 = freeze active)
% [36:44] float64 ensemble_time_s (zero here; set by publishProcessedFrame)
% [44:48] float32 das_f_number
% ```

    sharedMemoryMeta = py.multiprocessing.shared_memory.SharedMemory( ...
        name=sharedMemoryName, create=false ...
    );

    metaBytes = [ ...
        typecast(uint64(0),          'uint8'), ...  % frame_counter (8 bytes)
        typecast(int32(nz),          'uint8'), ...  % nz            (4 bytes)
        typecast(int32(nx),          'uint8'), ...  % nx            (4 bytes)
        typecast(single(zStartMm),   'uint8'), ...  % z_start_mm    (4 bytes)
        typecast(single(zEndMm),     'uint8'), ...  % z_end_mm      (4 bytes)
        typecast(single(xStartMm),   'uint8'), ...  % x_start_mm    (4 bytes)
        typecast(single(xEndMm),     'uint8'), ...  % x_end_mm      (4 bytes)
        typecast(uint32(runtimeFlags), 'uint8'), ... % runtime_flags (4 bytes)
        typecast(double(0),          'uint8'), ...  % ensemble_time_s (8 bytes)
        typecast(single(dasFNumber), 'uint8') ... % das_f_number (4 bytes)
    ];

    src = py.numpy.frombuffer(py.bytes(metaBytes), py.numpy.uint8);
    % On Windows, shared memory is page-aligned (4096 bytes) but we only need 36. Create
    % a view of exactly the right size to avoid shape mismatch.
    metaBuf = py.numpy.ndarray( ...
        py.tuple({int32(numel(metaBytes))}), ...
        dtype=py.numpy.uint8, buffer=sharedMemoryMeta.buf ...
    );
    py.numpy.copyto(metaBuf, src);
    % Release numpy views and force Python GC before closing (avoids BufferError: MATLAB
    % may hold internal refs to the numpy arrays even after explicit assignment to
    % py.None, so gc.collect() is required).
    metaBuf = py.None;  %#ok<NASGU>
    src = py.None;  %#ok<NASGU>
    py.gc.collect();
    sharedMemoryMeta.close();
end


function samplingMode = cfDefaultSamplingMode(probeName)
% Select probe-specific default sampling mode.
    if strcmp(probeName, 'L35-16vX')
        samplingMode = 'BS67BW';
    else
        samplingMode = 'BS100BW';
    end
end
