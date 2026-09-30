function ReconSpec = prepareDASBeamforming(ProbeSpec, TransmitSpec, ReceiveSpec, ReconSpec)
% Build ffdas delay-and-sum geometry tables for EchoFrame reconstruction.
% EchoFrame IQ samples are depth-like: one complex sample advances the image
% depth by c/Fs. Geometric DAS sums transmit and receive paths, so scale
% positions by Fs/(2c) to map the two-way path onto EchoFrame's sample axis.

    if ~strcmpi(TransmitSpec.type, 'planewave')
        error('prepareDASBeamforming:UnsupportedTransmit', ...
            'DAS setup currently supports planewave transmits only.');
    end

    nz = double(ReconSpec.nz);
    nx = double(ReconSpec.nx);
    nTx = double(ReceiveSpec.nTransmissions);
    nActive = double(ProbeSpec.nElementsX);
    fsOverTwoC = single(ReceiveSpec.Fs) / (2 * single(ReconSpec.c0));
    startSamples = single(ReconSpec.zAxis(1) * 1e-3) * 2 * fsOverTwoC;

    % Column vector: txDelays(:, iTx) is (nActive, 1). A row channelX would
    % implicit-expand residual to (nActive, nActive) and median(residual(active))
    % would then linear-index only column 1 (bulk uses channelX(1) only).
    channelX = ((0:nActive-1)' - (nActive-1)/2) * double(ProbeSpec.pitchX);
    ReconSpec.dasChannelPositions = single([channelX'; zeros(2, nActive)]) * fsOverTwoC;

    [xGridMm, zGridMm] = meshgrid(double(ReconSpec.xAxis), double(ReconSpec.zAxis));
    xGrid = xGridMm * 1e-3;
    zGrid = zGridMm * 1e-3;
    ReconSpec.dasVoxelPositions = single([xGrid(:)'; zeros(1, nz * nx); zGrid(:)']) * fsOverTwoC;

    receiveSamples = sqrt((xGrid(:) - channelX').^2 + zGrid(:).^2) * fsOverTwoC;
    minOffset = reshape(1 - min(receiveSamples, [], 2), nz, nx);

    % Planewave TX path is z*cos(theta)+x*sin(theta) plus the per-tx bulk delay
    % Verasonics stores by clamping negative TX.Delay to zero. That bulk is in
    % the RF; omitting it desynchronizes steered txs and blurs mid-depth. Do not
    % rebuild the wavefront via min-over-elements or clip maxOffset: the
    % geometric path plus bulk matches min-over(active) to <0.01 sample, and
    % ffdas already zeros channel reads past the IQ buffer so deep rows keep
    % correct depth with partial aperture.
    useTransmitDelays = isfield(TransmitSpec, 'transmitDelays') && any(TransmitSpec.transmitDelays(:) ~= 0);
    if useTransmitDelays
        txDelays = double(TransmitSpec.transmitDelays);
        if ndims(txDelays) == 3
            txDelays = squeeze(txDelays(:, 1, :));
        end
        if size(txDelays, 1) == nTx
            txDelays = txDelays.';
        end
        active = double(TransmitSpec.apodization(:)) ~= 0;
    end

    ReconSpec.dasOffsets = zeros(nz, nx, nTx, 'single');
    for iTx = 1:nTx
        theta = double(TransmitSpec.steerX(iTx));
        sinTheta = sind(theta);
        if useTransmitDelays
            residual = txDelays(:, iTx) - channelX * sinTheta / double(ReconSpec.c0);
            bulk = median(residual(active));
        else
            bulk = 0;
        end
        offsets = (zGrid * cosd(theta) + xGrid * sinTheta) * fsOverTwoC ...
            + bulk * double(ReceiveSpec.Fs) / 2 - startSamples;
        ReconSpec.dasOffsets(:, :, iTx) = single(max(offsets, minOffset));
    end

    ReconSpec.dasWeights = ones(nz, nx, nTx, 'single') ./ single(max(1, nTx * nActive));
    % RFFormatter stores IQ as I - iQ, so ffdas' usual negative phase rotation
    % is conjugated here.
    ReconSpec.dasWavenum = single(4 * pi * double(ProbeSpec.Fc) / double(ReceiveSpec.Fs));
    ReconSpec.dasAlgorithm = int32(1);
    ReconSpec.dasComputeType = int32(0);
    ReconSpec.dasSourceDirections = single(repmat([0; 0; 1; cosd(35)], 1, nActive));
end
