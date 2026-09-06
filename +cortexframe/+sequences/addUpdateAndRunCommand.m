function addUpdateAndRunCommand(structure)
% Update a structure in the runAcq environment.
%
% When updating a VSX structure (e.g., `Events`) in an external process
% function, it then needs to be updated in the runAcq environment via a
% control command. This function handles this update by automatically
% adding a new `update&Run` command to the `Control` structure.
%
% Parameters
% ----------
% structure : char
%     Name of the Verasonics structure to update. Must be one of:
%     `'Resource'`, `'Trans'`, `'Media'`, `'SFormat'`,
%     `'PData'`, `'TW'`, `'TX'`, `'Receive'`, `'TGC'`,
%     `'Recon'`, `'Process'`, `'SeqControl'`, or `'Event'`.
arguments
    structure { ...
        mustBeMember( ...
            structure, ...
            {'Resource', 'Trans', 'Media', 'SFormat', 'PData', 'TW', ...
            'TX', 'Receive', 'TGC', 'Recon', 'Process', 'SeqControl', ...
            'Event'} ...
        ) ...
    }
end
    Control = evalin('base', 'Control');
    % VSX sets Control to `Control.Command = [];` by default. If we don't
    % remove this empty command, runAcq won't read the control commands.
    if isempty(Control(1).Command)
        newControlIndex = 1;
    else
        newControlIndex = length(Control) + 1;
    end
    Control(newControlIndex).Command = 'update&Run';
    Control(newControlIndex).Parameters = {structure};
    assignin('base', 'Control', Control);
end
