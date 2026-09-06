function freezeCheck(~, ~)
% Freeze timer callback for napari-driven acquisition.
%
% Parameters
% ----------
% ~
%     Unused timer object argument supplied by VSX.
% ~
%     Unused timer-event argument supplied by VSX.
%
% Notes
% -----
% VSX calls this function periodically (every 0.25s) while acquisition is
% frozen. It reads freeze/exit commands from shared memory and updates base
% workspace state so acquisition can resume or exit without requiring a
% manual GUI interaction first.
%
% This callback is registered with VSX via `Mcr_FreezeTimerFunction`.

    persistent sharedMemoryCmd freezeBtn

    if isempty(sharedMemoryCmd)
        try
            sharedMemoryNameCmd = evalin('base', 'sharedMemoryNameCmd');
            sharedMemoryCmd = py.multiprocessing.shared_memory.SharedMemory( ...
                name=sharedMemoryNameCmd, create=false ...
            );
            cortexframe.util.logMessage('Freeze control shared memory opened successfully.');
        catch ME
            cortexframe.util.logMessage('Freeze control shared memory failed to open: %s', ME.message);
            return
        end
    end
    
    try
        % Read command bytes from cf_cmd.
        cmd = uint8(py.array.array('B', sharedMemoryCmd.buf));
        vsExit_cmd = logical(cmd(1));
        freeze_cmd = logical(cmd(2));

        % VSX base workspace state.
        current_freeze = evalin('base', 'freeze');

        if vsExit_cmd
            assignin('base', 'vsExit', 1);
            freezeBtn = cortexframe.napari.setFrozenState(false, freezeBtn, false);
            cortexframe.util.logMessage('Stop received while frozen; releasing freeze and setting vsExit=1.');
            return
        end

        % If napari requests unfreeze (freeze_cmd=0) and we're frozen, unfreeze.
        if ~freeze_cmd && current_freeze
            freezeBtn = cortexframe.napari.setFrozenState(false, freezeBtn, true);
            cortexframe.util.logMessage('Unfreeze command processed in freezeCheck.');
        end
    catch ME
        cortexframe.util.logMessage('Freeze control read error: %s', ME.message);
    end
end


