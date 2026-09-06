function ReconSpec = prepareFourierBeamforming(ProbeSpec, TransmitSpec, ReceiveSpec, ReconSpec)
% Build Fourier beamforming lookup tables for EchoFrame reconstruction.
%
% Parameters
% ----------
% ProbeSpec : struct
%     EchoFrame probe specification.
% TransmitSpec : struct
%     EchoFrame transmit specification.
% ReceiveSpec : struct
%     EchoFrame receive specification.
% ReconSpec : struct
%     EchoFrame reconstruction specification.
%
% Returns
% -------
% ReconSpec : struct
%     Reconstruction specification with Fourier lookup fields populated.

    switch ReceiveSpec.sampling_mode
        case 'BS50BW'
            nZ = single(ReceiveSpec.nSamples * round(4 / ReceiveSpec.samples_per_wavelength));
            dZ = ReconSpec.c0 / ReceiveSpec.Fs_base;
            frequencyAxis = fftshift(-0.5:1 / nZ:0.5 - 1 / nZ) * ReceiveSpec.Fs_base;
        case 'BS67BW'
            nZ = single(ReceiveSpec.nSamples * 2);
            dZ = ReconSpec.c0 / (ReceiveSpec.Fs_base * 2);
            frequencyAxis = fftshift(-0.5:1 / nZ:0.5 - 1 / nZ) * ReceiveSpec.Fs_base * 2;
        case 'BS100BW'
            nZ = single(ReceiveSpec.nSamples * round(4 / ReceiveSpec.samples_per_wavelength));
            dZ = ReconSpec.c0 / ReceiveSpec.Fs_base;
            frequencyAxis = fftshift(-0.5:1 / nZ:0.5 - 1 / nZ) * ReceiveSpec.Fs_base;
        case 'NS200BW'
            nZ = single(ReceiveSpec.nSamples * round(4 / ReceiveSpec.samples_per_wavelength));
            dZ = ReconSpec.c0 / ReceiveSpec.Fs_base;
            frequencyAxis = fftshift(-0.5:1 / nZ:0.5 - 1 / nZ) * ReceiveSpec.Fs_base;
        otherwise
            error('Unsupported sampling mode: %s.', ReceiveSpec.sampling_mode);
    end

    switch ReconSpec.nDims
        case 2
            nX = single(ReceiveSpec.nChannels);
            dX = single(ProbeSpec.pitchX);
            kxVector = (-0.5:1 / nX:0.5 - 1 / nX) * 2 * pi / dX;
            kzVector = (-0.5:1 / nZ:0.5 - 1 / nZ) * 4 * pi / dZ;
            maxK = max(abs([kxVector kzVector]));
            kxVector = single(fftshift(kxVector ./ maxK));
            kzVector = single(fftshift(kzVector ./ maxK));
        case 3
            nX = ReceiveSpec.nChannels;
            dX = ProbeSpec.pitchX;
            nY = ReconSpec.nElementsY;
            dY = ProbeSpec.pitchY;
            kxVector = (-0.5:1 / nX:0.5 - 1 / nX) * 2 * pi / dX;
            kyVector = (-0.5:1 / nY:0.5 - 1 / nY) * 2 * pi / dY;
            kzVector = (-0.5:1 / nZ:0.5 - 1 / nZ) * 4 * pi / dZ;
            maxK = max(abs([kxVector kyVector kzVector]));
            kxVector = single(fftshift(kxVector ./ maxK));
            kyVector = single(fftshift(kyVector ./ maxK));
            kzVector = single(fftshift(kzVector ./ maxK));
        otherwise
            error('Unsupported ReconSpec.nDims: %d.', ReconSpec.nDims);
    end
    gamma = 2 / nZ;

    switch ReceiveSpec.sampling_mode
        case 'BS50BW'
            lowerBound = ceil(nZ / 4 - nZ / 16) + 1;
            upperBound = floor(nZ / 4 + nZ / 16);
            kzVector = fftshift(kzVector(lowerBound:upperBound));
            frequencyAxis = fftshift(frequencyAxis(lowerBound:upperBound));
            freqMapping = fftshift(1:nZ / 8);
        case 'BS67BW'
            lowerBound = nZ / 2;
            upperBound = lowerBound + nZ / 4 - 1;
            kzVector = fftshift(kzVector(lowerBound:upperBound));
            frequencyAxis = frequencyAxis(lowerBound:upperBound);
            freqMapping = 1:nZ / 4;
        case 'BS100BW'
            lowerBound = ceil(nZ / 4 - nZ / 8) + 1;
            upperBound = floor(nZ / 4 + nZ / 8);
            kzVector = fftshift(kzVector(lowerBound:upperBound));
            frequencyAxis = fftshift(frequencyAxis(lowerBound:upperBound));
            freqMapping = fftshift(1:nZ / 4);
        case 'NS200BW'
            lowerBound = 1;
            upperBound = nZ / 2;
            kzVector = fftshift(kzVector(lowerBound:upperBound));
            frequencyAxis = frequencyAxis(lowerBound:upperBound);
            freqMapping = 1:nZ / 2;
    end

    switch ReconSpec.nDims
        case 2
            [kZ, kX] = ndgrid(kzVector, kxVector);
            spectrumWeighting = tukeywin(length(kzVector), 0.2) * tukeywin(length(kxVector), 0.2)';
            spectrumWeighting = fftshift(spectrumWeighting);
        case 3
            [kZ, kY, kX] = ndgrid(kzVector, kyVector, kxVector);
    end

    switch ReconSpec.nDims
        case 2
            delayIndices = ones(length(kzVector), length(kxVector), ReceiveSpec.nTransmissions, 'single');
            weights = ones(length(kzVector), length(kxVector), ReceiveSpec.nTransmissions, 'single');
            for iTransmission = 1:ReceiveSpec.nTransmissions
                theta = TransmitSpec.steerX(iTransmission);
                k = (kZ.^2 + kX.^2) ./ (2 * kZ * cosd(theta) + 2 * kX * sind(theta));
                mask = abs(k) < abs(kZ) * 2;
                k = (k * 2) .* mask;
                k(isnan(k(:))) = 0;
                kOffset = floor(k ./ gamma - 1 / 2);
                kk = mod(kOffset + 1, nZ) + 1;
                indices = kk - lowerBound + 1;
                arg = (k ./ gamma - floor(k ./ gamma - 1 / 2));
                phaseWeights = exp(-1i * pi .* arg);
                spectrumWeightingNew = ((kZ * 2 * cosd(theta)) .* (kX * sind(theta))) < 0.01;
                phaseWeights = phaseWeights .* (spectrumWeighting .* spectrumWeightingNew);
                phaseWeights(isnan(phaseWeights(:))) = 0;
                indices(isnan(indices(:))) = 0;
                badHigh = indices(:) > ReceiveSpec.nSamplesIQ;
                badLow = indices(:) < 1;
                indices(badHigh) = 1;
                indices(badLow) = 1;
                indices = freqMapping(indices);
                delayIndices(:, :, iTransmission) = indices;
                weights(:, :, iTransmission) = phaseWeights;
            end
        case 3
            delayIndices = ones(length(kzVector), length(kyVector), length(kxVector), ReceiveSpec.nTransmissions, 'single');
            weights = ones(length(kzVector), length(kyVector), length(kxVector), ReceiveSpec.nTransmissions, 'single');
            for iTransmission = 1:ReceiveSpec.nTransmissions
                theta = ReceiveSpec.planewave_transmit_angles(iTransmission);
                k = (kZ.^2 + kY.^2 + kX.^2) ./ (2 * kZ * cosd(theta) + 2 * kY * sind(theta) + 2 * kX * sind(theta));
                mask = abs(k) < abs(kZ) * 2;
                k = (k * 2) .* mask;
                k(isnan(k(:))) = 0;
                kOffset = floor(k ./ gamma - 1 / 2);
                kk = mod(kOffset + 1, nZ) + 1;
                indices = kk - lowerBound + 1;
                arg = (k ./ gamma - floor(k ./ gamma - 1 / 2));
                phaseWeights = exp(-1i * pi .* arg);
                phaseWeights(isnan(phaseWeights(:))) = 0;
                indices(isnan(indices(:))) = 0;
                badHigh = indices(:) > ReceiveSpec.nSamplesIQ;
                badLow = indices(:) < 1;
                indices(badHigh) = 1;
                indices(badLow) = 1;
                indices = freqMapping(indices);
                delayIndices(:, :, :, iTransmission) = indices;
                weights(:, :, :, iTransmission) = phaseWeights;
            end
    end

    scaling = single(ReceiveSpec.nTransmissions * ReconSpec.nz * ReconSpec.nx * 2);
    ReconSpec.delayIndices = int32(delayIndices - 1);
    ReconSpec.interpolationWeights = single(weights ./ scaling);
    ReconSpec.frequencyAxis = single(frequencyAxis);

    transmitDelays = TransmitSpec.transmitDelays(:, 1, :) * 2 * pi;
    delayAx = median(diff(transmitDelays(find(TransmitSpec.apodization), :))); %#ok<FNDSB>
    middleElementReal = floor(ProbeSpec.nElementsX / 2);
    middleElementRf = floor(ReceiveSpec.nChannels / 2);
    delayB = transmitDelays(middleElementReal, :) - double(middleElementRf) * delayAx;
    ReconSpec.planewaveDelays = single([delayAx' delayB']);
end
