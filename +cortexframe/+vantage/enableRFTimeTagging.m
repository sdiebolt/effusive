function enableRFTimeTagging 
% Enable RF time tagging and reset time tags.
%
% Notes
% -----
% Use this as an external process function before the steady-state event
% loop. It enables RF time tagging once per MATLAB function lifetime.
%
% Base workspace variables:
%
% - `VDAS` (logical, read): Verasonics flag indicating whether real
%   hardware is active; time tagging is skipped in simulate mode.
    import com.verasonics.hal.hardware.*

    persistent enableTimeTag

    % RF time tagging has to be enabled only once, when VSX is running.
    if isempty(enableTimeTag)
        if evalin('base', 'VDAS')
            rc = Hardware.enableAcquisitionTimeTagging(true);
            if ~rc
                error( ...
                    ['Error enabling RF time tagging. ', ...
                    'Is VSX running?'] ...
                )
            else
                cortexframe.util.logMessage('Time tagging enabled.');
            end

            % Reset RF time tag.
            Hardware.setTimeTaggingAttributes(false, true);
        end

        enableTimeTag = 1;
    end
end
