function Resource = configureResource(ReceiveSpec, c0)
% Configure the Verasonics Resource structure.
%
% Parameters
% ----------
% ReceiveSpec : struct
%     EchoFrame receive specification; nBuffers, nSamples, nTransmissions,
%     and nRepeats are used to size the receive buffer.
% c0 : float
%     Speed of sound [m/s].
%
% Returns
% -------
% Resource : struct
%     Verasonics resource structure with acquisition parameters and
%     receive buffer configured.
arguments
    ReceiveSpec (1,1) struct
    c0 (1,1) double
end
    Resource = struct();
    Resource.Parameters.simulateMode = 0;
    Resource.Parameters.waitForProcessing = 1;
    Resource.Parameters.numTransmit = 128;
    Resource.Parameters.numRcvChannels = 128;
    Resource.Parameters.speedOfSound = c0;
    Resource.Parameters.speedCorrectionFactor = 1.0;
    Resource.Parameters.numLogDataRecs = 128;
    Resource.VDAS.dmaTimeout = 120*1000;
    Resource.Parameters.GUI = 'cortexframe.napari.stubGui';

    Resource.RcvBuffer(1).datatype = 'int16';
    Resource.RcvBuffer(1).colsPerFrame = Resource.Parameters.numRcvChannels;
    Resource.RcvBuffer(1).numFrames = ReceiveSpec.nBuffers;
    Resource.RcvBuffer(1).rowsPerFrame = ...
        ReceiveSpec.nSamples * ReceiveSpec.nTransmissions * ReceiveSpec.nRepeats;
end
