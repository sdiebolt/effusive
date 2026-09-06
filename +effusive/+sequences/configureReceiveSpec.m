function ReceiveSpec = configureReceiveSpec( ...
    numElements, numRcvChannels, transFrequencyMHz, lensCorrection, c0, ...
    samplingMode, aperturePercentage, startDepthMm, desiredEndDepthMm, ...
    nTransmissions, nRepeats, txrxFrameRate, tgcGain, tgcControlPoints, nBuffers ...
)
% Configure the EchoFrame receive specification struct.
%
% Parameters
% ----------
% numElements : int
%     Number of transducer elements.
% numRcvChannels : int
%     Number of hardware receive channels.
% transFrequencyMHz : float
%     Transducer center frequency [MHz].
% lensCorrection : float
%     Lens correction depth offset [wavelengths].
% c0 : float
%     Speed of sound [m/s].
% samplingMode : {'BS50BW', 'BS67BW', 'BS100BW', 'NS200BW'}
%     IQ sampling bandwidth mode.
% aperturePercentage : float
%     Receive aperture percentage (0-100).
% startDepthMm : float
%     Start imaging depth [mm].
% desiredEndDepthMm : float
%     Desired end imaging depth [mm]. Actual end depth is rounded up to the
%     nearest multiple of 128 samples.
% nTransmissions : int
%     Number of plane-wave transmit angles per ensemble.
% nRepeats : int
%     Ensemble size (number of full angle sweeps).
% txrxFrameRate : float
%     TX/RX frame rate [Hz].
% tgcGain : float
%     TGC gain applied uniformly when tgcControlPoints contains NaN.
% tgcControlPoints : double (1, 8)
%     TGC control points. Set to nan(1, 8) to use uniform tgcGain.
% nBuffers : int
%     Number of receive ping-pong buffers.
%
% Returns
% -------
% ReceiveSpec : struct
%     EchoFrame receive specification with all derived depth, sampling,
%     buffer-size, and timing fields populated.
arguments
    numElements (1,1) double
    numRcvChannels (1,1) double
    transFrequencyMHz (1,1) double
    lensCorrection (1,1) double
    c0 (1,1) double
    samplingMode (1,:) char {mustBeMember(samplingMode, {'BS50BW', 'BS67BW', 'BS100BW', 'NS200BW'})}
    aperturePercentage (1,1) double
    startDepthMm (1,1) double
    desiredEndDepthMm (1,1) double
    nTransmissions (1,1) double
    nRepeats (1,1) double
    txrxFrameRate (1,1) double
    tgcGain (1,1) double
    tgcControlPoints (1,8) double
    nBuffers (1,1) double
end
    ReceiveSpec = struct();

    % Sampling system parameters.
    switch numRcvChannels
        case 64
            ReceiveSpec.nChannels = 128;
        case 128
            ReceiveSpec.nChannels = 128;
        case 256
            if numElements <= 128
                ReceiveSpec.nChannels = 128;
            else
                ReceiveSpec.nChannels = 256;
            end
    end

    ReceiveSpec.isIQ = true;
    ReceiveSpec.Fs_base = transFrequencyMHz * 4e6;
    switch samplingMode
        case 'BS50BW'
            ReceiveSpec.samples_per_wavelength = 1;
        case 'BS67BW'
            ReceiveSpec.samples_per_wavelength = 4/3;
        case 'BS100BW'
            ReceiveSpec.samples_per_wavelength = 2;
        case 'NS200BW'
            ReceiveSpec.samples_per_wavelength = 4;
    end
    ReceiveSpec.Fs_iq = ReceiveSpec.Fs_base * ReceiveSpec.samples_per_wavelength / 4;
    ReceiveSpec.sampling_mode = samplingMode;

    % Depth and buffer sizing.
    wvc0 = (transFrequencyMHz * 1e6 / c0) * ReceiveSpec.samples_per_wavelength;
    maxAcqLngth = (desiredEndDepthMm - startDepthMm) * 1e-3 * wvc0;

    % VSX only allows nSamples in multiples of 128, so actual end depth differs.
    ReceiveSpec.nSamples = ceil(maxAcqLngth / 64) * 64 * 2;
    ReceiveSpec.nSamplesIQ = ReceiveSpec.nSamples / 2;
    ReceiveSpec.startDepthMm = startDepthMm;
    ReceiveSpec.desiredEndDepthMm = desiredEndDepthMm;
    ReceiveSpec.actualEndDepthMm = ...
        (ReceiveSpec.nSamples / wvc0 * 1e3) / 2 + startDepthMm;
    ReceiveSpec.startDepthWavelengths = ...
        startDepthMm * 1e-3 * transFrequencyMHz * 1e6 / c0;
    ReceiveSpec.endDepthWavelengths = ...
        ReceiveSpec.actualEndDepthMm * 1e-3 * transFrequencyMHz * 1e6 / c0;
    ReceiveSpec.lensOffset = lensCorrection * 4 * ReceiveSpec.samples_per_wavelength;

    % Acquisition timing.
    ReceiveSpec.transmitReceiveTimeMus = round(1e6 / txrxFrameRate);
    ReceiveSpec.dopplerSamplingFrequency = txrxFrameRate / nTransmissions;
    ReceiveSpec.acquisitionTime = ...
        ReceiveSpec.transmitReceiveTimeMus * nTransmissions * nRepeats * 1e-6;
    ReceiveSpec.triggerOverheadTime = 1e-3;
    ReceiveSpec.pdiTriggerTime = ceil( ...
        (ReceiveSpec.acquisitionTime + ReceiveSpec.triggerOverheadTime) * 1e3 ...
    );
    ReceiveSpec.requiredProcessingTime = (nRepeats * nTransmissions) / txrxFrameRate;

    % Remaining acquisition parameters.
    ReceiveSpec.aperturePercentage = aperturePercentage;
    ReceiveSpec.nTransmissions = nTransmissions;
    ReceiveSpec.nRepeats = nRepeats;
    ReceiveSpec.nBuffers = nBuffers;
    ReceiveSpec.tgcGain = tgcGain;
    ReceiveSpec.tgcControlPoints = tgcControlPoints;
    ReceiveSpec.apodization = effusive.sequences.calculateApertureApodization( ...
        numElements, aperturePercentage, 0.2 ...
    );
end
