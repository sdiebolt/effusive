function upsertSessionsRow(storageRootPath, subject, session, acqTime)
% Create or update the subject-level `_sessions.tsv` row.
%
% Parameters
% ----------
% storageRootPath : char | string
%     Dataset root directory.
% subject : char | string
%     Subject label without the `sub-` prefix.
% session : char | string
%     Session label without the `ses-` prefix.
% acqTime : char | string
%     ISO 8601 acquisition start timestamp.
    arguments
        storageRootPath
        subject
        session
        acqTime
    end

    subjectLabel = effusive.bids.validateLabel(subject, 'Subject', true);
    sessionLabel = effusive.bids.validateLabel(session, 'Session', true);
    acqTimeText = char(string(acqTime));

    subjectDir = fullfile(char(string(storageRootPath)), sprintf('sub-%s', subjectLabel));
    if ~isfolder(subjectDir)
        mkdir(subjectDir);
    end
    sessionsPath = fullfile(subjectDir, sprintf('sub-%s_sessions.tsv', subjectLabel));

    header = sprintf('session_id\tacq_time\n');
    newRow = sprintf('ses-%s\t%s\n', sessionLabel, acqTimeText);

    if ~isfile(sessionsPath)
        localWriteText(sessionsPath, [header, newRow]);
        return;
    end

    rawText = fileread(sessionsPath);
    lines = regexp(rawText, '\r\n|\n|\r', 'split');
    if ~isempty(lines) && isempty(lines{end})
        lines(end) = [];
    end
    if isempty(lines)
        lines = {strtrim(header)};
    end

    targetId = sprintf('ses-%s', sessionLabel);
    replaced = false;
    for iLine = 2:numel(lines)
        cols = split(string(lines{iLine}), sprintf('\t'));
        if ~isempty(cols) && strcmp(char(cols(1)), targetId)
            lines{iLine} = strtrim(newRow);
            replaced = true;
            break;
        end
    end
    if ~replaced
        lines{end + 1} = strtrim(newRow); %#ok<AGROW>
    end
    localWriteText(sessionsPath, sprintf('%s\n', strjoin(lines, newline)));
end


function localWriteText(path, text)
    fileId = fopen(path, 'w');
    if fileId == -1
        error('Could not write file: %s', path);
    end
    cleaner = onCleanup(@() fclose(fileId)); %#ok<NASGU>
    fwrite(fileId, text, 'char');
end
