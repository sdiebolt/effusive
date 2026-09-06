function outputPaths = exportZStack(stackVolume, bmodeVolume, zStackState)
% Export the completed z-stack as NIfTI files plus JSON metadata.
%
% Parameters
% ----------
% stackVolume : single
%     PDI stack volume with dimensions [nz, nx, nSlices], where nz and nx
%     reflect the (possibly cropped) output size.
% bmodeVolume : single
%     B-mode stack volume with the same dimensions as stackVolume.
% zStackState : struct
%     Runtime z-stack state containing slice positions and acquisition settings.
%
% Returns
% -------
% outputPaths : struct
%     Paths to the exported PDI NIfTI, B-mode NIfTI, and JSON sidecar.
    arguments
        stackVolume (:, :, :) single
        bmodeVolume (:, :, :) single
        zStackState (1, 1) struct
    end

    % Base workspace variables.
    StorageSpec = evalin('base', 'StorageSpec');
    ReconSpec = evalin('base', 'ReconSpec');
    ProbeSpec = evalin('base', 'ProbeSpec');
    BidsSpec = evalin('base', 'BidsSpec');
    BidsSpec = cfMergeLiveBidsMeta(BidsSpec);
    simulateMode = evalin('base', 'simulateMode');
    sessionId = char(string(evalin('base', 'sessionId')));
    probeName = char(string(evalin('base', 'probeName')));

    [outputDir, fileStem, bidsSubject, bidsSession] = cfResolveZStackOutputPath( ...
        StorageSpec, BidsSpec ...
    );
    if ~isfolder(outputDir)
        mkdir(outputDir);
    end

    pdiPath   = fullfile(outputDir, [fileStem '_pwd.nii']);
    bmodePath = fullfile(outputDir, [fileStem '_bmode.nii']);
    pwdJsonPath   = fullfile(outputDir, [fileStem '_pwd.json']);
    bmodeJsonPath = fullfile(outputDir, [fileStem '_bmode.json']);

    cropRoi = int32(ReconSpec.croppingROI(:));
    zIdx = double(cropRoi(1)) + 1 : double(cropRoi(2)) + 1;
    xIdx = double(cropRoi(3)) + 1 : double(cropRoi(4)) + 1;
    % stackVolume is already at the (possibly cropped) size produced by
    % echoframe_mex — do not re-index it with full-frame coordinates.

    if exist('niftiwrite', 'file') ~= 2
        error('Cannot export z-stack: niftiwrite is not available in this MATLAB version.');
    end

    if numel(ReconSpec.zAxis) > 1
        dzMm = abs(double(ReconSpec.zAxis(2) - ReconSpec.zAxis(1)));
    else
        dzMm = nan;
    end
    if numel(ReconSpec.xAxis) > 1
        dxMm = abs(double(ReconSpec.xAxis(2) - ReconSpec.xAxis(1)));
    else
        dxMm = nan;
    end
    if numel(zStackState.positionsMm) > 1
        dyMm = abs(double(zStackState.positionsMm(2) - zStackState.positionsMm(1)));
    else
        dyMm = 0.0;
    end

    dxMm_pix = dxMm;
    dzMm_pix = dzMm;
    dyMm_pix = dyMm;
    if isnan(dxMm_pix) || dxMm_pix <= 0, dxMm_pix = 1.0; end
    if isnan(dzMm_pix) || dzMm_pix <= 0, dzMm_pix = 1.0; end
    if isnan(dyMm_pix) || dyMm_pix <= 0, dyMm_pix = 1.0; end

    % ConfUSIus convention: NIfTI axis order is (x, y, z) = (lateral, depth, stack).
    % ConfUSIus reads this back as (z, y, x) = (nSlices, nz, nx), matching napari.
    % Write with default header first, then patch pixel dimensions via niftiinfo
    % to avoid the struct-vs-NIfTI1Info incompatibility in niftiwrite.
    pdiVol = permute(stackVolume, [2, 1, 3]);  % [nx, nz, nSlices]
    niftiwrite(pdiVol, pdiPath, 'Compressed', false);
    pdiMeta = niftiinfo(pdiPath);
    pdiMeta.PixelDimensions = [dxMm_pix, dzMm_pix, dyMm_pix];
    niftiwrite(pdiVol, pdiPath, pdiMeta, 'Compressed', false);

    bmodeVol = permute(bmodeVolume, [2, 1, 3]);  % [nx, nz, nSlices]
    niftiwrite(bmodeVol, bmodePath, 'Compressed', false);
    bmodeMeta = niftiinfo(bmodePath);
    bmodeMeta.PixelDimensions = [dxMm_pix, dzMm_pix, dyMm_pix];
    niftiwrite(bmodeVol, bmodePath, bmodeMeta, 'Compressed', false);

    metadata = struct();
    metadata.SessionId = sessionId;
    metadata.OutputLabel = sessionId;
    metadata.ProbeName = probeName;
    if isfield(ProbeSpec, 'name')
        metadata.ProbeName = char(string(ProbeSpec.name));
    end
    metadata.StackPositionsUm = double(zStackState.positionsUm(:))';
    metadata.StartPositionUm = double(zStackState.positionsUm(1));
    if numel(zStackState.positionsUm) > 1
        metadata.StepSizeUm = double(zStackState.positionsUm(2) - zStackState.positionsUm(1));
    else
        metadata.StepSizeUm = 0;
    end
    metadata.NumberOfSlices = double(zStackState.nSlices);
    metadata.FramesPerSlice = double(zStackState.npdiPerSlice);
    metadata.SettleTimeMs = double(zStackState.settleMs);
    metadata.CropRoi = double(cropRoi(:))';
    metadata.SimulationMode = double(simulateMode);
    metadata.DummyMotor = strcmp(zStackState.motorBackendKind, 'dummy');
    metadata.MotorBackend = zStackState.motorBackendKind;
    metadata.Timestamp = char(datetime('now', 'Format', 'yyyy-MM-dd''T''HH:mm:ss'));
    % NIfTI axis order is (x, y, z) = (lateral, depth, stack); spacing follows suit.
    metadata.VoxelSpacingMm = [dxMm, dzMm, dyMm];
    metadata.ZAxisMm = double(ReconSpec.zAxis(zIdx));
    metadata.XAxisMm = double(ReconSpec.xAxis(xIdx));
    metadata.PdiPath = pdiPath;
    metadata.BmodePath = bmodePath;
    metadata.BidsSubject = bidsSubject;
    metadata.BidsSession = bidsSession;
    metadata.BidsStem = fileStem;

    jsonText = jsonencode(metadata, 'PrettyPrint', true);
    cfWriteJson(pwdJsonPath, jsonText);
    if ~isempty(bmodeJsonPath)
        cfWriteJson(bmodeJsonPath, jsonText);
    end

    acqTime = char(datetime('now', 'TimeZone', 'local', 'Format', 'yyyy-MM-dd''T''HH:mm:ssXXX'));
    cortexframe.bids.upsertSessionsRow( ...
        StorageSpec.storageRootPath, bidsSubject, bidsSession, acqTime ...
    );
    cortexframe.bids.appendScansRows( ...
        StorageSpec.storageRootPath, ...
        bidsSubject, ...
        bidsSession, ...
        { ...
            fullfile('angio', [fileStem '_pwd.nii']), ...
            fullfile('angio', [fileStem '_bmode.nii']) ...
        }, ...
        acqTime ...
    );

    outputPaths = struct( ...
        'pdiPath', pdiPath, ...
        'bmodePath', bmodePath, ...
        'pwdJsonPath', pwdJsonPath, ...
        'bmodeJsonPath', bmodeJsonPath ...
    );
end


function cfWriteJson(path, jsonText)
    fileId = fopen(path, 'w');
    if fileId == -1
        error('Cannot export z-stack metadata JSON: %s', path);
    end
    cleaner = onCleanup(@() fclose(fileId)); %#ok<NASGU>
    fwrite(fileId, jsonText, 'char');
end


function BidsSpec = cfMergeLiveBidsMeta(BidsSpec)
    sidecarPath = '';
    if evalin('base', 'exist(''cortexframeBidsMetaPath'', ''var'') == 1')
        sidecarPath = char(string(evalin('base', 'cortexframeBidsMetaPath')));
    end
    if isempty(sidecarPath) || ~isfile(sidecarPath)
        return;
    end

    try
        sidecar = jsondecode(fileread(sidecarPath));
        if isfield(sidecar, 'task'), BidsSpec.task = char(string(sidecar.task)); end
        if isfield(sidecar, 'acq'), BidsSpec.acq = char(string(sidecar.acq)); end
        if isfield(sidecar, 'proc'), BidsSpec.proc = char(string(sidecar.proc)); end
        if isfield(sidecar, 'run'), BidsSpec.run = double(sidecar.run); end
    catch
    end
end


function [outputDir, fileStem, subject, session] = cfResolveZStackOutputPath(StorageSpec, BidsSpec)
    subject = cortexframe.bids.validateLabel(BidsSpec.subject, 'Subject', true);
    session = cortexframe.bids.validateLabel(BidsSpec.session, 'Session', true);
    taskRaw = '';
    if isfield(BidsSpec, 'task'), taskRaw = BidsSpec.task; end
    acqRaw = '';
    if isfield(BidsSpec, 'acq'), acqRaw = BidsSpec.acq; end
    procRaw = '';
    if isfield(BidsSpec, 'proc'), procRaw = BidsSpec.proc; end
    task = cortexframe.bids.validateLabel(taskRaw, 'Task', false);
    acq = cortexframe.bids.validateLabel(acqRaw, 'Acquisition', false);
    proc = cortexframe.bids.validateLabel(procRaw, 'Processing', false);
    outputDir = cortexframe.bids.buildDataDirectory( ...
        StorageSpec.storageRootPath, subject, session, 'angio' ...
    );
    runIndex = 1;
    if isfield(BidsSpec, 'run'), runIndex = double(BidsSpec.run); end
    fileStem = cortexframe.bids.buildStem( ...
        subject, session, runIndex, task, acq, proc, false ...
    );
end


function tf = cfStemExists(dataDir, fileStem)
    if ~isfolder(dataDir)
        tf = false;
        return;
    end
    matches = dir(fullfile(dataDir, [fileStem '*']));
    tf = ~isempty(matches);
end
