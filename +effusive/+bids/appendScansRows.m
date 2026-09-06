function appendScansRows(storageRootPath, subject, session, relativePaths, acqTime)
% Append rows to the session-level `_scans.tsv` file.
%
% Parameters
% ----------
% storageRootPath : char | string
%     Dataset root directory.
% subject : char | string
%     Subject label without the `sub-` prefix.
% session : char | string
%     Session label without the `ses-` prefix.
% relativePaths : cell
%     Relative file paths, usually below the session directory.
% acqTime : char | string
%     ISO 8601 acquisition start timestamp.
    arguments
        storageRootPath
        subject
        session
        relativePaths (1, :) cell
        acqTime
    end

    subjectLabel = effusive.bids.validateLabel(subject, 'Subject', true);
    sessionLabel = effusive.bids.validateLabel(session, 'Session', true);
    acqTimeText = char(string(acqTime));

    sessionDir = fullfile( ...
        char(string(storageRootPath)), ...
        sprintf('sub-%s', subjectLabel), ...
        sprintf('ses-%s', sessionLabel) ...
    );
    if ~isfolder(sessionDir)
        mkdir(sessionDir);
    end
    scansPath = fullfile( ...
        sessionDir, sprintf('sub-%s_ses-%s_scans.tsv', subjectLabel, sessionLabel) ...
    );

    existing = containers.Map('KeyType', 'char', 'ValueType', 'logical');
    lines = {'filename	acq_time'};
    if isfile(scansPath)
        rawText = fileread(scansPath);
        loadedLines = regexp(rawText, '\r\n|\n|\r', 'split');
        if ~isempty(loadedLines) && isempty(loadedLines{end})
            loadedLines(end) = [];
        end
        if ~isempty(loadedLines)
            lines = loadedLines;
            for iLine = 2:numel(loadedLines)
                cols = split(string(loadedLines{iLine}), sprintf('\t'));
                if ~isempty(cols)
                    existing(char(cols(1))) = true;
                end
            end
        end
    end

    for iPath = 1:numel(relativePaths)
        relPath = char(string(relativePaths{iPath}));
        if existing.isKey(relPath)
            continue;
        end
        lines{end + 1} = sprintf('%s	%s', relPath, acqTimeText); %#ok<AGROW>
        existing(relPath) = true;
    end

    localWriteText(scansPath, sprintf('%s\n', strjoin(lines, newline)));
end


function localWriteText(path, text)
    fileId = fopen(path, 'w');
    if fileId == -1
        error('Could not write file: %s', path);
    end
    cleaner = onCleanup(@() fclose(fileId)); %#ok<NASGU>
    fwrite(fileId, text, 'char');
end
