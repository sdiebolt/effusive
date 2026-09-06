function ReconSpec = configureTGCVector(ReconSpec, ReceiveSpec, options)
% Configure the TGC compensation vector for EchoFrame reconstruction.
%
% Parameters
% ----------
% ReconSpec : struct
%     EchoFrame reconstruction specification; tgcVector field is set.
% ReceiveSpec : struct
%     EchoFrame receive specification; samples_per_wavelength and
%     nSamplesIQ used.
% options.zerosEndWavelengths : double, default: 3
%     Number of wavelengths to zero at the end of the TGC vector.
%
% Returns
% -------
% ReconSpec : struct
%     Updated reconstruction specification with tgcVector set.
arguments
    ReconSpec (1, 1) struct
    ReceiveSpec (1, 1) struct
    options.zerosEndWavelengths (1, 1) double = 3
end
    temp_kernel = gausswin(20, 5)';
    zeros_samples_start = zeros(1, round(10 * ReceiveSpec.samples_per_wavelength));
    zeros_samples_end = zeros(1, round(options.zerosEndWavelengths * ReceiveSpec.samples_per_wavelength));
    tgc = ones(1, ReceiveSpec.nSamplesIQ - length(zeros_samples_start) - length(zeros_samples_end));
    ReconSpec.tgcVector = convn([zeros_samples_start tgc zeros_samples_end], temp_kernel, 'same');
end
