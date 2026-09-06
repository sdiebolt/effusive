function freezeBtn = resolveFreezeButton(cachedHandle)
% Resolve the hidden VSX Freeze button used by the napari stub GUI.
%
% Parameters
% ----------
% cachedHandle : matlab.ui.control.UIControl or []
%     Previously resolved button handle, if available.
%
% Returns
% -------
% freezeBtn : matlab.ui.control.UIControl or []
%     Valid handle to the hidden Freeze button, or empty when unavailable.

    freezeBtn = cachedHandle;
    if ~isempty(freezeBtn) && isgraphics(freezeBtn)
        return;
    end

    freezeBtn = [];

    if evalin('base', 'exist(''cfFreezeButtonHandle'', ''var'')')
        candidate = evalin('base', 'cfFreezeButtonHandle');
        if ~isempty(candidate) && isgraphics(candidate)
            freezeBtn = candidate;
        end
    end

    if isempty(freezeBtn)
        freezeBtn = findobj('String', 'Freeze');
    end

    if ~isempty(freezeBtn)
        assignin('base', 'cfFreezeButtonHandle', freezeBtn(1));
        freezeBtn = freezeBtn(1);
    end
end
