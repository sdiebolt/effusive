function TW = configureTransmitWaveform(transmitFrequency, pulseLength)
% Configure the Verasonics transmit waveform structure.
%
% Parameters
% ----------
% transmitFrequency : double
%     Transmit frequency [Hz].
% pulseLength : int
%     Pulse length in half cycles.
%
% Returns
% -------
% TW : struct
%     Verasonics transmit waveform structure.
arguments
    transmitFrequency (1, 1) double
    pulseLength (1, 1) double
end
    TW = struct();
    TW(1).type = 'parametric';
    TW(1).Parameters = [transmitFrequency*1e-6, 0.67, pulseLength, 1];
end
