function fileStem = buildStem(subject, session, runIndex, task, acq, proc, requireTask)
% Build a BIDS-like filename stem without suffix or extension.
%
% Parameters
% ----------
% subject : char | string
%     Subject label without the `sub-` prefix.
% session : char | string
%     Session label without the `ses-` prefix.
% runIndex : double
%     Positive run index.
% task : char | string
%     Task label without the `task-` prefix.
% acq : char | string
%     Acquisition label without the `acq-` prefix.
% proc : char | string
%     Processing label without the `proc-` prefix.
% requireTask : logical, default: true
%     Whether the task label must be present.
%
% Returns
% -------
% fileStem : char
%     Filename stem up to, but not including, the suffix.
    arguments
        subject
        session
        runIndex (1, 1) double {mustBePositive, mustBeInteger}
        task = ''
        acq = ''
        proc = ''
        requireTask (1, 1) logical = true
    end

    subjectLabel = cortexframe.bids.validateLabel(subject, 'Subject', true);
    sessionLabel = cortexframe.bids.validateLabel(session, 'Session', true);
    taskLabel = cortexframe.bids.validateLabel(task, 'Task', requireTask);
    acqLabel = cortexframe.bids.validateLabel(acq, 'Acquisition', false);
    procLabel = cortexframe.bids.validateLabel(proc, 'Processing', false);

    parts = { ...
        sprintf('sub-%s', subjectLabel), ...
        sprintf('ses-%s', sessionLabel) ...
    };
    if ~isempty(taskLabel)
        parts{end + 1} = sprintf('task-%s', taskLabel);
    end
    if ~isempty(acqLabel)
        parts{end + 1} = sprintf('acq-%s', acqLabel);
    end
    if ~isempty(procLabel)
        parts{end + 1} = sprintf('proc-%s', procLabel);
    end
    parts{end + 1} = sprintf('run-%02d', runIndex);

    fileStem = strjoin(parts, '_');
end
