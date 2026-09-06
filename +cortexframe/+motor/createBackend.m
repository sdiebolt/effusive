function motorBackend = createBackend(useDummyMotor)
% Create the requested motor backend.
%
% Parameters
% ----------
% useDummyMotor : logical
%     Whether to create the dummy backend instead of a real motor backend.
%
% Returns
% -------
% motorBackend : struct
%     Motor backend descriptor with fields used by the z-stack runtime.
%
% Raises
% ------
% error
%     If the requested backend cannot be created.
    arguments
        useDummyMotor (1, 1) logical
    end

    if useDummyMotor
        motorBackend = struct( ...
            'kind', 'dummy', ...
            'currentPositionMm', 0.0, ...
            'minPositionMm', -inf, ...
            'maxPositionMm', inf, ...
            'handle', [] ...
        );
        return;
    end

    if evalin('base', 'exist(''stackMotorPort'', ''var'') == 1')
        motorPort = char(string(evalin('base', 'stackMotorPort')));
    else
        motorPort = char(string(getenv('CORTEXFRAME_STACK_MOTOR_PORT')));
    end
    motorPort = strtrim(motorPort);
    if isempty(motorPort)
        autoPort = '';
        if exist('serialportlist', 'file') == 2
            availablePorts = serialportlist("available");
            if numel(availablePorts) == 1
                autoPort = char(availablePorts(1));
                cortexframe.util.logMessage('Auto-selected stack motor port: %s', autoPort);
            elseif numel(availablePorts) > 1
                error([ ...
                    'Real motor backend requested, but no motor port was configured. ', ...
                    'Multiple serial ports are available (%s). Set stackMotorPort or ', ...
                    'CORTEXFRAME_STACK_MOTOR_PORT.' ...
                ], strjoin(cellstr(availablePorts), ', '));
            end
        end

        if isempty(autoPort)
            error([ ...
                'Real motor backend requested, but no motor port was configured. ', ...
                'Set base workspace variable stackMotorPort or environment variable ', ...
                'CORTEXFRAME_STACK_MOTOR_PORT.' ...
            ]);
        end
        motorPort = autoPort;
    end

    minPositionMm = cfParseOptionalMotorLimit('stackMotorMinMm', 'CORTEXFRAME_STACK_MOTOR_MIN_MM');
    maxPositionMm = cfParseOptionalMotorLimit('stackMotorMaxMm', 'CORTEXFRAME_STACK_MOTOR_MAX_MM');
    if minPositionMm > maxPositionMm
        error('Invalid stack motor limits: min %.6f mm is greater than max %.6f mm.', ...
            minPositionMm, maxPositionMm);
    end

    motorHandle = cortexframe.motor.stpMotor(motorPort);
    currentPositionMm = motorHandle.getCurrentPositionMm();

    motorBackend = struct( ...
        'kind', 'real', ...
        'currentPositionMm', currentPositionMm, ...
        'minPositionMm', minPositionMm, ...
        'maxPositionMm', maxPositionMm, ...
        'handle', motorHandle, ...
        'port', motorPort ...
    );
end


function valueMm = cfParseOptionalMotorLimit(baseVariableName, envVariableName)
    if evalin('base', sprintf('exist(''%s'', ''var'') == 1', baseVariableName))
        rawValue = evalin('base', baseVariableName);
    else
        rawValue = getenv(envVariableName);
    end

    if isempty(rawValue)
        if contains(lower(baseVariableName), 'min')
            valueMm = -inf;
        else
            valueMm = inf;
        end
        return;
    end

    if ischar(rawValue) || (isstring(rawValue) && isscalar(rawValue))
        valueMm = str2double(rawValue);
    else
        valueMm = double(rawValue);
    end
    if ~isscalar(valueMm) || ~isfinite(valueMm)
        error('Invalid motor limit for %s/%s. Expected a finite scalar millimeter value.', ...
            baseVariableName, envVariableName);
    end
end
