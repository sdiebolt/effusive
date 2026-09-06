function stopMotion(motorBackend)
% Best-effort motor stop helper.
%
% Parameters
% ----------
% motorBackend : struct
%     Backend descriptor returned by `effusive.motor.createBackend`.
    arguments
        motorBackend (1, 1) struct
    end

    if ~isfield(motorBackend, 'kind') || ~strcmp(motorBackend.kind, 'real')
        return;
    end

    motorHandle = motorBackend.handle;
    if ismethod(motorHandle, 'stopMotor')
        stopMotor(motorHandle);
        return;
    end
    if ismethod(motorHandle, 'stop')
        stop(motorHandle);
        return;
    end
    if ismethod(motorHandle, 'emergencyStop')
        emergencyStop(motorHandle);
    end
end
