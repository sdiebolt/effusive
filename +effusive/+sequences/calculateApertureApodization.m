function apodization = calculateApertureApodization(numElements, aperturePercentage, taperRatio)
% Calculate a Tukey-windowed aperture apodization vector.
%
% Parameters
% ----------
% numElements : int
%     Total number of transducer elements.
% aperturePercentage : float
%     Active aperture as a percentage of total elements (0-100).
% taperRatio : float
%     Tukey window taper ratio passed to `tukeywin`. Transmit and receive
%     apertures traditionally use different tapers (e.g. `0.1` and `0.2`).
%
% Returns
% -------
% apodization : double (1, numElements)
%     Per-element apodization weights. Inactive elements are zero.
arguments
    numElements (1,1) double
    aperturePercentage (1,1) double
    taperRatio (1,1) double
end
    nOff = round(numElements * (100 - aperturePercentage) / 100);
    nOff = nOff + rem(nOff, 2);
    nOn = numElements - nOff;

    apodization = zeros(1, numElements);
    apodization(nOff/2 + 1 : end - nOff/2) = tukeywin(nOn, taperRatio);
    % Verasonics ignores weights below 0.2 due to a known firmware bug.
    apodization(apodization <= 0.2) = 0;
end
