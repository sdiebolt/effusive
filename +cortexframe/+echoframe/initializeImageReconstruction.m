function [ProbeSpec, ReceiveSpec, ReconSpec] = initializeImageReconstruction( ...
    ProbeSpec, TransmitSpec, ReceiveSpec, ReconSpec)
% Initialize EchoFrame reconstruction geometry and kernels.
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
% ProbeSpec : struct
%     Unmodified probe specification.
% ReceiveSpec : struct
%     Unmodified receive specification.
% ReconSpec : struct
%     Reconstruction spec with initialized fields.

    switch ReconSpec.method
        case 'Fourier'
            nz = double(ReceiveSpec.nSamplesIQ) + double(ReconSpec.extra_voxels_z);
            nz = nz + rem(nz, 2);
            nx = double(ReceiveSpec.nChannels) + double(ReconSpec.extra_voxels_x);
            nx = nx + rem(nx, 2);
            ReconSpec.nz = int32(nz);
            ReconSpec.nx = int32(nx);

            tempKernel = gausswin(30, 5)';
            zerosSamplesStart = zeros(1, round(10 * ReceiveSpec.samples_per_wavelength));
            zerosSamplesEnd = zeros(1, round(3 * ReceiveSpec.samples_per_wavelength));
            tgc = ones(1, ReceiveSpec.nSamplesIQ - numel(zerosSamplesStart) - numel(zerosSamplesEnd));
            ReconSpec.tgcVector = convn([zerosSamplesStart tgc zerosSamplesEnd], tempKernel, 'same');
            ReconSpec = cortexframe.echoframe.prepareFourierBeamforming( ...
                ProbeSpec, TransmitSpec, ReceiveSpec, ReconSpec ...
            );
        otherwise
            error('Unsupported ReconSpec.method: %s', ReconSpec.method);
    end

    nElementRf = double(ReceiveSpec.nChannels);
    ReconSpec.xAxis = linspace( ...
        -(nElementRf / 2) * ProbeSpec.pitchX, ...
        (nElementRf / 2) * ProbeSpec.pitchX, ...
        nx ...
    ) * 1e3;
    ReconSpec.zAxis = linspace( ...
        ReceiveSpec.startDepthMm, ...
        ReceiveSpec.startDepthMm + ReceiveSpec.actualEndDepthMm, ...
        nz ...
    );
    ReconSpec.imageSize = [nz nx];
    ReconSpec.number_of_sensors_x = ProbeSpec.nElementsX;
    ReconSpec.pitch_x = ProbeSpec.pitchX;
end
