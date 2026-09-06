function storageConfig = requestedStorageConfig(saveMaster, saveRF, saveRFTimeTag, saveBF, savePDI)
% Build the effective storage configuration from the UI command flags.
%
% Parameters
% ----------
% saveMaster : logical
%     Master save-to-disk flag from the napari command channel.
% saveRF : logical
%     Raw RF save flag.
% saveRFTimeTag : logical
%     RF timestamp save flag.
% saveBF : logical
%     Beamformed IQ save flag.
% savePDI : logical
%     Power Doppler save flag.
%
% Returns
% -------
% storageConfig : struct
%     Effective save configuration with per-modality flags and an `initialized` field
%     indicating whether any storage backend is needed.

    storageConfig = struct( ...
        saveRF=logical(saveMaster) && logical(saveRF), ...
        saveRFTimeTag=logical(saveMaster) && logical(saveRFTimeTag), ...
        saveBF=logical(saveMaster) && logical(saveBF), ...
        savePDI=logical(saveMaster) && logical(savePDI) ...
    );
    storageConfig.initialized = ...
        storageConfig.saveRF ...
        || storageConfig.saveRFTimeTag ...
        || storageConfig.saveBF ...
        || storageConfig.savePDI;
end
