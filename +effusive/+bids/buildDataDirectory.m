function dataDir = buildDataDirectory(storageRootPath, subject, session, datatype)
% Build the BIDS-like datatype directory for one recording family.
%
% Parameters
% ----------
% storageRootPath : char | string
%     Root storage directory.
% subject : char | string
%     Subject label without the `sub-` prefix.
% session : char | string
%     Session label without the `ses-` prefix.
% datatype : char | string
%     Datatype folder name, typically `fusi` or `angio`.
%
% Returns
% -------
% dataDir : char
%     Full datatype directory path.
    arguments
        storageRootPath
        subject
        session
        datatype
    end

    subjectLabel = effusive.bids.validateLabel(subject, 'Subject', true);
    sessionLabel = effusive.bids.validateLabel(session, 'Session', true);
    dataTypeLabel = char(string(datatype));
    dataDir = fullfile( ...
        char(string(storageRootPath)), ...
        sprintf('sub-%s', subjectLabel), ...
        sprintf('ses-%s', sessionLabel), ...
        dataTypeLabel ...
    );
end
