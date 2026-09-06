function TPC = configureTPC(initialTransmitVoltage)
    % Configure the transmit power controller (TPC) Verasonics structure.
    %
    % Parameters
    % ----------
    % initialTransmitVoltage : double
    %     Initial transmit voltage at startup.
    %
    % Returns
    % -------
    % struct
    %     Transmit power controller Verasonics structure.
    arguments
        initialTransmitVoltage (1, 1) double
    end
    TPC = struct();
    TPC(1).hv = initialTransmitVoltage;
end
