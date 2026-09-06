function freezeBtn = setFrozenState(frozen, cachedHandle, resumeAck)
% Synchronize the VSX freeze latch between base state and the hidden UI control.
%
% Parameters
% ----------
% frozen : logical
%     Whether acquisition should be frozen in VSX.
% cachedHandle : matlab.ui.control.UIControl or []
%     Previously resolved hidden Freeze button handle, if available.
% resumeAck : logical
%     Whether this transition should mark `freezeResumedByNapari` so the
%     next runtime-control callback can emit a one-time resume acknowledgement.
%
% Returns
% -------
% freezeBtn : matlab.ui.control.UIControl or []
%     Resolved hidden Freeze button handle, if available.
%
% Notes
% -----
% VSX enters its hardware pause path when the base-workspace `freeze`
% variable becomes `1`. While paused, VSX waits on the hidden `Freeze`
% togglebutton value to return to `0`. Both latches must therefore stay in
% sync for manual pause, timer-driven resume, and MATLAB-originated
% auto-freeze paths such as z-stack completion.

    arguments
        frozen (1, 1) logical
        cachedHandle = []
        resumeAck (1, 1) logical = false
    end

    freezeBtn = cortexframe.napari.resolveFreezeButton(cachedHandle);

    assignin('base', 'freeze', double(frozen));
    assignin('base', 'freezeResumedByNapari', resumeAck);

    if ~isempty(freezeBtn)
        set(freezeBtn, 'Value', double(frozen));
    end
end
