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

    nElementRf = double(ReceiveSpec.nChannels);
    ReconSpec.xAxis = linspace( ...
        -(nElementRf / 2) * ProbeSpec.pitchX, ...
        (nElementRf / 2) * ProbeSpec.pitchX, ...
        nx ...
    ) * 1e3;
    % actualEndDepthMm is the absolute acquisition end, not a span from
    % startDepthMm. Adding startDepthMm again would stretch zAxis past the
    % RF buffer whenever startDepthMm > 0 and misregister DAS voxel depths.
    ReconSpec.zAxis = linspace( ...
        ReceiveSpec.startDepthMm, ...
        ReceiveSpec.actualEndDepthMm, ...
        nz ...
    );
    ReconSpec.imageSize = [nz nx];
    ReconSpec.number_of_sensors_x = ProbeSpec.nElementsX;
    ReconSpec.pitch_x = ProbeSpec.pitchX;

    if ~isfield(ReconSpec, 'beamformerType') || isempty(ReconSpec.beamformerType)
        ReconSpec.beamformerType = ReconSpec.method;
    end

    switch ReconSpec.method
        case 'Fourier'
            ReconSpec.beamformerType = 'Fourier';
            ReconSpec = effusive.echoframe.prepareFourierBeamforming( ...
                ProbeSpec, TransmitSpec, ReceiveSpec, ReconSpec ...
            );
        case 'DAS'
            ReconSpec.beamformerType = 'DAS';
            ReconSpec = effusive.echoframe.prepareDASBeamforming( ...
                ProbeSpec, TransmitSpec, ReceiveSpec, ReconSpec ...
            );
        otherwise
            error('Unsupported ReconSpec.method: %s', ReconSpec.method);
    end
end
