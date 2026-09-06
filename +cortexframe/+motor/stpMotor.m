classdef stpMotor < handle
% Minimal non-GUI motor controller for CortexFrame z-stack acquisition.
%
% This class wraps the subset of the Zaber serial protocol needed by the
% MATLAB z-stack state machine (`moveTo`, `home`, `stopMotor`, and
% `getCurrentPositionMm`). It uses MATLAB's modern `serialport` transport.

    properties (Constant, Access = private)
        MM_PER_STEP = 0.047625e-3;
        BAUD_RATE = 9600;
    end

    properties (SetAccess = private)
        portName (1, :) char
        transport
    end

    methods
        function motor = stpMotor(portName)
            arguments
                portName (1, :) char
            end

            motor.portName = strtrim(portName);
            if isempty(motor.portName)
                error('Motor port name cannot be empty.');
            end

            motor.transport = serialport(motor.portName, motor.BAUD_RATE, 'Timeout', 15);

        end

        function moveTo(motor, positionMm)
            arguments
                motor (1, 1) cortexframe.motor.stpMotor
                positionMm (1, 1) double
            end

            targetSteps = motor.mmToSteps(positionMm);
            moveCommand = motor.dataToCommand(uint8(1), uint8(20), targetSteps);
            motor.writeCommand(moveCommand);
        end

        function stopMotor(motor)
            stopCommand = motor.dataToCommand(uint8(1), uint8(23), int32(0));
            motor.writeCommand(stopCommand);
        end

        function resetOrigin(motor)
            resetCommand = motor.dataToCommand(uint8(1), uint8(45), int32(0));
            motor.writeCommand(resetCommand);
        end

        function positionMm = getCurrentPositionMm(motor)
            reply = motor.requestReply(uint8(1), uint8(60), int32(0), uint8(60));
            steps = typecast(uint8(reply(3:6)), 'int32');
            positionMm = double(steps) * motor.MM_PER_STEP;
        end

        function home(motor)
            homeCommand = motor.dataToCommand(uint8(1), uint8(1), int32(0));
            motor.writeCommand(homeCommand);
        end

        function delete(motor)
            if isempty(motor.transport)
                return;
            end
            try
                clear motor.transport;
            catch
            end
        end
    end

    methods (Access = private)
        function writeCommand(motor, commandBytes)
            write(motor.transport, commandBytes, 'uint8');
        end

        function steps = mmToSteps(motor, positionMm)
            steps = int32(round(positionMm / motor.MM_PER_STEP));
        end

        function reply = requestReply(motor, deviceId, commandId, payload, expectedCommandId)
            motor.flushInputBuffer();
            command = motor.dataToCommand(deviceId, commandId, payload);
            motor.writeCommand(command);

            deadline = tic;
            sawReply = false;
            lastCommandId = uint8(0);
            while toc(deadline) < 5
                reply = motor.readReply(6);
                if numel(reply) ~= 6
                    continue;
                end
                if reply(1) ~= deviceId
                    continue;
                end
                sawReply = true;
                lastCommandId = reply(2);
                if reply(2) == 255
                    error('Motor reported out-of-range command while reading current position.');
                end
                if reply(2) == expectedCommandId
                    return;
                end
            end

            if ~sawReply
                error('Timed out while reading motor position: no valid 6-byte reply received.');
            end
            error('Timed out while reading motor position: last command id was %d.', lastCommandId);
        end

        function reply = readReply(motor, nBytes)
            reply = read(motor.transport, nBytes, 'uint8');
            reply = uint8(reply(:)).';
        end

        function flushInputBuffer(motor)
            flush(motor.transport);
        end

        function command = dataToCommand(~, deviceId, commandId, payload)
            payloadBytes = typecast(int32(payload), 'uint8');
            command = zeros(1, 6, 'uint8');
            command(1) = deviceId;
            command(2) = commandId;
            command(3:6) = payloadBytes;
        end
    end
end
