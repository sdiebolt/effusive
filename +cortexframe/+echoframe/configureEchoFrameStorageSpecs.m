function [BFStorageSpec, PDIStorageSpec, RFTimeTagStorageSpec, RFStorageSpec] = configureEchoFrameStorageSpecs( ...
    command, ...
    StorageSpec, ...
    ReceiveSpec, ...
    ReconSpec, ...
    PDISpec, ...
    ExperimentSpec, ...
    TransmitSpec, ...
    ProbeSpec...
)
% Initialize storage specifications for EchoFrame outputs.
%
% Parameters
% ----------
% command : char
%     Storage command (`'init'` or `'re-init'`).
% StorageSpec : struct
%     Storage configuration from CortexFrame runtime.
% ReceiveSpec : struct
%     EchoFrame receive specification.
% ReconSpec : struct
%     EchoFrame reconstruction specification.
% PDISpec : struct
%     EchoFrame PDI specification.
% ExperimentSpec : struct
%     Experiment metadata specification.
% TransmitSpec : struct
%     EchoFrame transmit specification.
% ProbeSpec : struct
%     EchoFrame probe specification.
%
% Returns
% -------
% BFStorageSpec : struct
%     Beamformed data storage specification.
% PDIStorageSpec : struct
%     PDI data storage specification.
% RFTimeTagStorageSpec : struct
%     RF time-tag storage specification.
% RFStorageSpec : struct
%     Raw RF storage specification.

    if ~isfield(StorageSpec, 'experimentStoragePath') || isempty(StorageSpec.experimentStoragePath)
        StorageSpec.experimentStoragePath = StorageSpec.folderStoragePath;
    end
    if ~isfolder(StorageSpec.experimentStoragePath)
        mkdir(StorageSpec.experimentStoragePath);
    end

    BFStorageSpec.crop = ReconSpec.cropBF;
    if BFStorageSpec.crop
        bfDataSize = uint64((ReconSpec.croppingROI(2) - ReconSpec.croppingROI(1) + 1) ...
            * (ReconSpec.croppingROI(4) - ReconSpec.croppingROI(3) + 1) ...
            * ReceiveSpec.nRepeats);
    else
        bfDataSize = uint64(ReconSpec.nz * ReconSpec.nx * ReceiveSpec.nRepeats);
    end
    bfDataSizeBytes = bfDataSize * 8;

    PDIStorageSpec.crop = PDISpec.cropPDI;
    if PDIStorageSpec.crop
        pdiDataSize = uint64( ...
            (ReconSpec.croppingROI(2) - ReconSpec.croppingROI(1) + 1) ...
            * (ReconSpec.croppingROI(4) - ReconSpec.croppingROI(3) + 1) ...
        );
    else
        pdiDataSize = uint64( ...
            (ReconSpec.nz * ReconSpec.nx) ...
            * max(0, floor((ReceiveSpec.nRepeats - PDISpec.ensembleSize) / PDISpec.shiftSize) + 1) ...
        );
    end
    pdiDataSizeBytes = pdiDataSize * 4;

    RFTimeTagStorageSpec.crop = logical(false);
    rfTimeTagDataSize = uint64(ReceiveSpec.nRepeats * ReceiveSpec.nTransmissions);
    rfTimeTagDataSizeBytes = rfTimeTagDataSize * 8;

    rfDataSize = uint64(0);
    rfDataSizeBytes = uint64(0);
    if StorageSpec.saveRF
        rfDataSize = [ ...
            ReceiveSpec.nSamples, ...
            ReceiveSpec.nTransmissions, ...
            ReceiveSpec.nRepeats, ...
            ReceiveSpec.nChannels ...
        ];
        rfDataSize = uint64(prod(rfDataSize));
        rfDataSizeBytes = rfDataSize * 2;
    end

    sharedMaxNumberBuffers = resolveSharedMaxNumberBuffers( ...
        StorageSpec, ...
        ExperimentSpec, ...
        bfDataSizeBytes, ...
        pdiDataSizeBytes, ...
        rfTimeTagDataSizeBytes, ...
        rfDataSizeBytes ...
    );

    BFStorageSpec.save = StorageSpec.saveBF;
    BFStorageSpec.maxNumberBuffers = sharedMaxNumberBuffers;
    BFStorageSpec.numberOfBuffers = int32(4);
    BFStorageSpec.dataType = ReconSpec.bfDataType;
    bfFilename = resolveStorageFilename(StorageSpec, 'bfFilename', '_iq', 'bf_acq');
    BFStorageSpec.filepath = fullfile(StorageSpec.experimentStoragePath, bfFilename);
    BFStorageSpec.bufferSize = uint64(bfDataSize);
    BFStorageSpec.preallocateFullFile = StorageSpec.preallocateFullFile;

    PDIStorageSpec.save = StorageSpec.savePDI;
    PDIStorageSpec.maxNumberBuffers = sharedMaxNumberBuffers;
    PDIStorageSpec.numberOfBuffers = int32(4);
    PDIStorageSpec.dataType = 'single';
    pdiFilename = resolveStorageFilename(StorageSpec, 'pdiFilename', '_pwd', 'pdi_acq');
    PDIStorageSpec.filepath = fullfile(StorageSpec.experimentStoragePath, pdiFilename);
    PDIStorageSpec.bufferSize = uint64(pdiDataSize);
    PDIStorageSpec.preallocateFullFile = StorageSpec.preallocateFullFile;

    RFTimeTagStorageSpec.save = StorageSpec.saveRFTimeTag;
    RFTimeTagStorageSpec.maxNumberBuffers = sharedMaxNumberBuffers;
    RFTimeTagStorageSpec.numberOfBuffers = int32(4);
    RFTimeTagStorageSpec.dataType = 'double';
    rfTimeTagFilename = resolveStorageFilename(StorageSpec, 'rfTimeTagFilename', '_rftimestamps', 'rfTimeTag_acq');
    RFTimeTagStorageSpec.filepath = fullfile(StorageSpec.experimentStoragePath, rfTimeTagFilename);
    RFTimeTagStorageSpec.bufferSize = uint64(rfTimeTagDataSize);
    RFTimeTagStorageSpec.preallocateFullFile = StorageSpec.preallocateFullFile;

    rfFilename = resolveStorageFilename(StorageSpec, 'rfFilename', '_rf', 'rf_acq');
    RFStorageSpec = struct( ...
        save=logical(StorageSpec.saveRF), ...
        maxNumberBuffers=sharedMaxNumberBuffers, ...
        numberOfBuffers=int32(16), ...
        dataType='int16', ...
        crop=logical(false), ...
        filepath=fullfile(StorageSpec.experimentStoragePath, rfFilename), ...
        bufferSize=uint64(rfDataSize), ...
        preallocateFullFile=logical(StorageSpec.preallocateFullFile) ...
    );

    if BFStorageSpec.save || PDIStorageSpec.save || RFTimeTagStorageSpec.save || RFStorageSpec.save
        parameterBasename = resolveStorageFilename(StorageSpec, 'parameterFilename', '_seq.mat', 'ScanParameters.mat');
        parameterFilename = fullfile(StorageSpec.experimentStoragePath, parameterBasename);
        save( ...
            parameterFilename, ...
            'ReceiveSpec', ...
            'ReconSpec', ...
            'PDISpec', ...
            'ExperimentSpec', ...
            'TransmitSpec', ...
            'ProbeSpec', ...
            '-v7.3' ...
        );
    end

    assignin('base', 'StorageSpec', StorageSpec);
end

function sharedMaxNumberBuffers = resolveSharedMaxNumberBuffers( ...
    StorageSpec, ...
    ExperimentSpec, ...
    bfDataSizeBytes, ...
    pdiDataSizeBytes, ...
    rfTimeTagDataSizeBytes, ...
    rfDataSizeBytes ...
)
% Derive one shared max-buffer budget so all active outputs fit together.
%
% Parameters
% ----------
% StorageSpec : struct
%     Storage configuration from CortexFrame runtime.
% ExperimentSpec : struct
%     Experiment metadata specification. Must contain
%     `numberOfPDIsExperiment` when full-file preallocation is enabled.
% bfDataSizeBytes : uint64
%     Beamformed output size in bytes for one stored buffer.
% pdiDataSizeBytes : uint64
%     Power Doppler output size in bytes for one stored buffer.
% rfTimeTagDataSizeBytes : uint64
%     RF time-tag output size in bytes for one stored buffer.
% rfDataSizeBytes : uint64
%     Raw RF output size in bytes for one stored buffer.
%
% Returns
% -------
% sharedMaxNumberBuffers : int32
%     Common buffer limit applied to all active output streams.

    if StorageSpec.preallocateFullFile
        if ~isfield(ExperimentSpec, 'numberOfPDIsExperiment') || isempty(ExperimentSpec.numberOfPDIsExperiment)
            error( ...
                'configureEchoFrameStorageSpecs:MissingNumberOfPDIsExperiment', ...
                ['ExperimentSpec.numberOfPDIsExperiment is required when ' ...
                 'StorageSpec.preallocateFullFile is true.'] ...
            );
        end
        sharedMaxNumberBuffers = int32(ExperimentSpec.numberOfPDIsExperiment);
        return;
    end

    totalBytesPerBuffer = 0;
    if StorageSpec.saveBF
        totalBytesPerBuffer = totalBytesPerBuffer + double(bfDataSizeBytes);
    end
    if StorageSpec.savePDI
        totalBytesPerBuffer = totalBytesPerBuffer + double(pdiDataSizeBytes);
    end
    if StorageSpec.saveRFTimeTag
        totalBytesPerBuffer = totalBytesPerBuffer + double(rfTimeTagDataSizeBytes);
    end
    if StorageSpec.saveRF
        totalBytesPerBuffer = totalBytesPerBuffer + double(rfDataSizeBytes);
    end

    if totalBytesPerBuffer <= 0
        sharedMaxNumberBuffers = int32(0);
        return;
    end

    diskReserveBytes = 10 * 1024^3;
    [freeBytes, writeBudgetBytes] = resolveWriteBudgetBytes( ...
        StorageSpec.experimentStoragePath, ...
        diskReserveBytes ...
    );

    sharedMaxNumberBuffers = int32(floor(writeBudgetBytes / totalBytesPerBuffer));
    if sharedMaxNumberBuffers < 1
        error( ...
            'configureEchoFrameStorageSpecs:InsufficientDiskSpace', ...
            ['Not enough free disk space under %s to store one frame across ' ...
             'the active outputs while reserving %.1f GiB. Free: %.2f GiB.'], ...
            StorageSpec.experimentStoragePath, ...
            diskReserveBytes / 1024^3, ...
            freeBytes / 1024^3 ...
        );
    end
end

function filename = resolveStorageFilename(StorageSpec, fieldName, fileSuffix, defaultName)
% Resolve one storage basename, preferring explicit config over BIDS stem.
%
% Parameters
% ----------
% StorageSpec : struct
%     Storage configuration from CortexFrame runtime.
% fieldName : char
%     Field containing an explicit basename override.
% fileSuffix : char
%     Suffix appended to `StorageSpec.fileStem` when available.
% defaultName : char
%     Fallback basename when no explicit override or stem exists.
%
% Returns
% -------
% filename : char
%     Basename passed to EchoFrame storage.

    if isfield(StorageSpec, fieldName) && ~isempty(StorageSpec.(fieldName))
        filename = char(string(StorageSpec.(fieldName)));
        return;
    end

    if isfield(StorageSpec, 'fileStem') && ~isempty(StorageSpec.fileStem)
        filename = sprintf('%s%s', char(string(StorageSpec.fileStem)), fileSuffix);
        return;
    end

    filename = defaultName;
end

function [freeBytes, writeBudgetBytes] = resolveWriteBudgetBytes(storagePath, diskReserveBytes)
% Resolve writable disk budget for the destination filesystem.
%
% Parameters
% ----------
% storagePath : char
%     Destination path used to query filesystem free space.
% diskReserveBytes : double
%     Safety margin kept free on disk.
%
% Returns
% -------
% freeBytes : double
%     Usable free space reported by the filesystem.
% writeBudgetBytes : double
%     Remaining writable budget after subtracting the safety margin.

    fileInfo = java.io.File(storagePath);
    freeBytes = double(fileInfo.getUsableSpace());
    writeBudgetBytes = max(0, freeBytes - double(diskReserveBytes));
end
