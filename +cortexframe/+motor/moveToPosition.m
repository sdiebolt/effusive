function motorBackend = moveToPosition(motorBackend, targetPositionMm)
% Move the motor backend to an absolute position.
%
% Parameters
% ----------
% motorBackend : struct
%     Backend descriptor returned by `cortexframe.motor.createBackend`.
% targetPositionMm : double
%     Absolute target position in millimeters.
%
% Returns
% -------
% motorBackend : struct
%     Updated backend descriptor.
    arguments
        motorBackend (1, 1) struct
        targetPositionMm (1, 1) double
    end

    minPositionMm = -inf;
    maxPositionMm = inf;
    if isfield(motorBackend, 'minPositionMm')
        minPositionMm = motorBackend.minPositionMm;
    end
    if isfield(motorBackend, 'maxPositionMm')
        maxPositionMm = motorBackend.maxPositionMm;
    end
    if targetPositionMm < minPositionMm || targetPositionMm > maxPositionMm
        error('Requested motor position %.6f mm outside configured limits [%.6f, %.6f] mm.', ...
            targetPositionMm, minPositionMm, maxPositionMm);
    end

    switch motorBackend.kind
        case 'dummy'
            motorBackend.currentPositionMm = targetPositionMm;
        case 'real'
            motorBackend.handle.moveTo(targetPositionMm);
            motorBackend.currentPositionMm = targetPositionMm;
        otherwise
            error('Unsupported motor backend kind: %s', motorBackend.kind);
    end
end
