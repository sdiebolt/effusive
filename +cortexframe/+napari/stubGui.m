function stubGui()
% VSX GUI stub for napari-driven acquisition.
%
% VSX requires a function whose name matches `Resource.Parameters.GUI`.
% That function must create a MATLAB figure tagged `'UI'`.  This stub
% creates an invisible figure to satisfy VSX without opening any MATLAB
% controls; all acquisition control is driven from the napari dock widget.
%
% Notes
% -----
% `hv2GUIprofile` is normally set by `vsx_gui` when it builds the second HV slider.
% `TXEventCheck` reads it unconditionally, so this stub writes `0` to the base workspace
% (same default as `vsx_gui.m`).
% A hidden freeze togglebutton is created so VSX has a UI element to wait on
% when freeze is activated (via napari). freezeCheck will toggle this button
% to unfreeze.

    f = figure(Tag='UI', Name='CortexFrame', Visible='off');

    % Create hidden freeze togglebutton for VSX freeze wait loop.
    % VSX uses: waitfor(findobj('String','Freeze'),'Value',0)
    uicontrol(f, ...
        Style='togglebutton', ...
        String='Freeze', ...
        Value=0, ...
        Visible='off', ...
        Position=[10 10 60 20] ...
    );
    freezeBtnHandle = findobj(f, 'String', 'Freeze');
    assignin('base', 'cfFreezeButtonHandle', freezeBtnHandle);

    % hv2GUIprofile is normally set by vsx_gui when it builds the second HV slider.
    % TXEventCheck reads it unconditionally, so we must provide a value. 0 means "no
    % second HV slider" (same default as vsx_gui.m).
    assignin('base', 'hv2GUIprofile', 0);
end
