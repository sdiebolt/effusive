function TransmitSpec = configureTransmitSpec( ...
    numElements, txrxFrameRate, transmitPulseLength, aperturePercentage, ...
    planewaveOpeningAngle, c0 ...
)
% Configure the EchoFrame transmit specification struct.
%
% Parameters
% ----------
% numElements : int
%     Number of transducer elements.
% txrxFrameRate : float
%     TX/RX frame rate [Hz].
%
%     !!! danger
%         This parameter affects acoustic safety. Do not change without
%         understanding the acoustic safety implications.
%
% transmitPulseLength : int
%     Transmit pulse length [half cycles].
%
%     !!! danger
%         This parameter affects acoustic safety. Do not change without
%         understanding the acoustic safety implications.
%
% aperturePercentage : float
%     Transmit aperture percentage (0-100).
%
%     !!! danger
%         This parameter affects acoustic safety. Do not change without
%         understanding the acoustic safety implications.
%
% planewaveOpeningAngle : float
%     Total steering angle range for plane waves [degrees].
%
%     !!! danger
%         This parameter affects acoustic safety. Do not change without
%         understanding the acoustic safety implications.
%
% c0 : float
%     Speed of sound [m/s].
%
% Returns
% -------
% TransmitSpec : struct
%     EchoFrame transmit specification.
arguments
    numElements (1,1) double
    txrxFrameRate (1,1) double
    transmitPulseLength (1,1) double
    aperturePercentage (1,1) double
    planewaveOpeningAngle (1,1) double
    c0 (1,1) double
end
    TransmitSpec = struct( ...
        txrxFrameRate=txrxFrameRate, ...
        transmitPulseLength=transmitPulseLength, ...
        aperturePercentage=aperturePercentage, ...
        planewaveOpeningAngle=planewaveOpeningAngle, ...
        c0=c0, ...
        apodization=effusive.sequences.calculateApertureApodization(numElements, aperturePercentage, 0.1) ...
    );
end
