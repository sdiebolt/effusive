function processRFEnsembleBlock(RF)
% Process an ensemble block of RF data and populate FrameRuntimeState.
%
% Parameters
% ----------
% RF : int16
%     Array of raw RF data as passed by the Verasonics receive buffer.
%
% Notes
% -----
% This is Process(2) in the Verasonics event sequence.  It handles four
% exclusive processing branches (SVD update, crop re-init, experiment
% re-init, and normal processing) and writes the results into the
% `FrameRuntimeState` base workspace struct for downstream callbacks.
%
% Base workspace variables (read):
%
% - `ExperimentSpec` (struct): updateExperiment flag checked every frame.
% - `storeEchoFrameOutput` (logical): controls whether echoframe_mex saves.
% - `svdThreshold` (single): current SVD rejection threshold.
% - `svdUpdateFlag` (logical): set by processRuntimeControl; reset here.
% - `updateCropping` (logical): set by processRuntimeControl; reset here.
% - `ReconSpec` (struct): reconstruction spec; read in re-init branches.
% - `StorageSpec` (struct): storage spec; read in re-init branches.
% - `ReceiveSpec` (struct): receive spec; read in re-init branches.
% - `PDISpec` (struct): PDI spec; read in re-init branches.
% - `TransmitSpec` (struct): transmit spec; read in re-init branches.
% - `ProbeSpec` (struct): probe spec; read in re-init branches.
% - `storageConfigApplied` (struct): determines re-init path in branches.
% - `FrameRuntimeState` (struct): read for timing fields; written back.
%
% Base workspace variables (written):
%
% - `svdUpdateFlag`: reset to 0 after SVD branch.
% - `updateCropping`: reset to 0 after crop branch.
% - `ExperimentSpec`: updateExperiment reset to false after experiment branch.
% - `FrameRuntimeState`: updated every frame with processing results and
%   timing fields.

    persistent isVDAS

    if isempty(isVDAS)
        isVDAS = logical(evalin('base', 'VDAS'));
    end

    % Measure VSX inter-frame wait (time since previous publishProcessedFrame).
    FrameRuntimeState = evalin('base', 'FrameRuntimeState');
    if FrameRuntimeState.t_last_publish_end_tic ~= uint64(0)
        FrameRuntimeState.t_vsx_wait_s = toc(FrameRuntimeState.t_last_publish_end_tic);
    end
    FrameRuntimeState.t_frame_start_tic = tic;
    FrameRuntimeState.frameReady = false;

    ExperimentSpec       = evalin('base', 'ExperimentSpec');
    storeEchoFrameOutput = evalin('base', 'storeEchoFrameOutput');
    svdThreshold         = single(evalin('base', 'svdThreshold'));
    svdUpdateFlag        = evalin('base', 'svdUpdateFlag');
    updateCropping       = evalin('base', 'updateCropping');

    if svdUpdateFlag
        echoframe_mex( ...
            'updatePDIthreshold&process', RF, storeEchoFrameOutput, svdThreshold ...
        );
        effusive.util.logMessage('SVD threshold -> %.0f%%.', 100 * double(svdThreshold));
        assignin('base', 'svdUpdateFlag', 0);

    elseif updateCropping
        effusive.util.logMessage('Updating cropping in the MEX.');
        StorageSpec          = evalin('base', 'StorageSpec');
        ReceiveSpec          = evalin('base', 'ReceiveSpec');
        ReconSpec            = evalin('base', 'ReconSpec');
        PDISpec              = evalin('base', 'PDISpec');
        TransmitSpec         = evalin('base', 'TransmitSpec');
        ProbeSpec            = evalin('base', 'ProbeSpec');
        storageConfigApplied = evalin('base', 'storageConfigApplied');
        effusive.rf.reinitEchoFrameStorage( ...
            're-init storage', storageConfigApplied.initialized, StorageSpec, ...
            ReceiveSpec, ReconSpec, PDISpec, ExperimentSpec, TransmitSpec, ProbeSpec ...
        );
        [PDI, Bmode] = echoframe_mex('process', RF, storeEchoFrameOutput);
        assignin('base', 'updateCropping', 0);
        FrameRuntimeState = cfPopulateFrame(FrameRuntimeState, RF, PDI, Bmode, isVDAS);

    elseif ExperimentSpec.updateExperiment
        effusive.util.logMessage('New experiment initialized.');
        StorageSpec          = evalin('base', 'StorageSpec');
        ReceiveSpec          = evalin('base', 'ReceiveSpec');
        ReconSpec            = evalin('base', 'ReconSpec');
        PDISpec              = evalin('base', 'PDISpec');
        TransmitSpec         = evalin('base', 'TransmitSpec');
        ProbeSpec            = evalin('base', 'ProbeSpec');
        storageConfigApplied = evalin('base', 'storageConfigApplied');
        effusive.rf.reinitEchoFrameStorage( ...
            're-init experiment', storageConfigApplied.initialized, StorageSpec, ...
            ReceiveSpec, ReconSpec, PDISpec, ExperimentSpec, TransmitSpec, ProbeSpec ...
        );
        [PDI, Bmode] = echoframe_mex('process', RF, storeEchoFrameOutput);
        ExperimentSpec.updateExperiment = false;
        assignin('base', 'ExperimentSpec', ExperimentSpec);
        FrameRuntimeState = cfPopulateFrame(FrameRuntimeState, RF, PDI, Bmode, isVDAS);

    else
        [PDI, Bmode] = echoframe_mex('process', RF, storeEchoFrameOutput);
        FrameRuntimeState = cfPopulateFrame(FrameRuntimeState, RF, PDI, Bmode, isVDAS);
    end

    assignin('base', 'FrameRuntimeState', FrameRuntimeState);
end


function FrameRuntimeState = cfPopulateFrame(FrameRuntimeState, RF, PDI, Bmode, isVDAS)
% Fill FrameRuntimeState from a frame that produced PDI and Bmode outputs.
%
% PDI and Bmode are stored raw (not log-compressed or normalized); the
% napari viewer log-compresses each to dB relative to its own per-frame
% peak on its decoupled polling tick, keeping that work off the
% VSX-blocking callback chain.

    FrameRuntimeState.PDI      = single(PDI);
    FrameRuntimeState.Bmode    = single(Bmode);
    % Keep a reference to the raw ensemble; publishProcessedFrame slices it
    % into an RF snapshot only when the viewer requests one (rare, user-
    % triggered), instead of on every frame.
    FrameRuntimeState.RF = RF;

    if isVDAS
        W1 = double(RF(1, 1));
        W2 = double(RF(2, 1));
        if W1 < 0, W1 = W1 + 65536; end
        if W2 < 0, W2 = W2 + 65536; end
        FrameRuntimeState.ensemble_time_s = (W1 + 65536 * W2) / 4e4;
    else
        FrameRuntimeState.ensemble_time_s = double(0);
    end

    FrameRuntimeState.frameReady = true;
end
