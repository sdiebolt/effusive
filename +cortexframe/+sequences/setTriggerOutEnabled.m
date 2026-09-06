function didUpdate = setTriggerOutEnabled(enabled)
% Enable or disable trigger-out on the trigger-out events.
%
% Parameters
% ----------
% enabled : logical
%     Desired trigger-out state for each buffer trigger-out event.
%
% Returns
% -------
% didUpdate : logical
%     True when the Event structure was changed and queued for update.
    arguments
        enabled (1, 1) logical
    end

    % Verasonics base workspace variables.
    Event = evalin('base', 'Event');
    SeqControl = evalin('base', 'SeqControl');

    % CortexFrame base workspace variables.
    triggerOutEventIndex = evalin('base', 'triggerOutEventIndex');

    desiredSeqControl = 0;
    if enabled
        desiredSeqControl = -1;
        for SeqControlIndex = 1:length(SeqControl)
            if strcmp(SeqControl(SeqControlIndex).command, 'triggerOut')
                desiredSeqControl = SeqControlIndex;
                break
            end
        end

        if desiredSeqControl == -1
            error([ ...
                'Could not find a "triggerOut" sequence ', ...
                'control command in SeqControl.' ...
            ])
        end
    end

    didUpdate = false;
    for eventIndex = reshape(triggerOutEventIndex, 1, [])
        if Event(eventIndex).seqControl ~= desiredSeqControl
            Event(eventIndex).seqControl = desiredSeqControl;
            didUpdate = true;
        end
    end

    if didUpdate
        assignin('base', 'Event', Event);
        cortexframe.sequences.addUpdateAndRunCommand('Event');
    end
end
