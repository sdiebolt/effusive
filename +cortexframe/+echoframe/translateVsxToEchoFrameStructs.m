function [ProbeSpec, TransmitSpec, ReceiveSpec] = translateVsxToEchoFrameStructs( ...
    Resource, Trans, TX, Receive, ProbeSpec, TransmitSpec, ReceiveSpec ...
)
% Translate Verasonics sequence structs into EchoFrame structs.
%
% Parameters
% ----------
% Resource : struct
%     Verasonics Resource struct.
% Trans : struct
%     Verasonics probe/transducer struct.
% TX : struct array
%     Verasonics transmit definitions.
% Receive : struct array
%     Verasonics receive definitions.
% ProbeSpec : struct
%     EchoFrame probe specification.
% TransmitSpec : struct
%     EchoFrame transmit specification.
% ReceiveSpec : struct
%     EchoFrame receive specification.
%
% Returns
% -------
% ProbeSpec : struct
%     Updated probe specification.
% TransmitSpec : struct
%     Updated transmit specification.
% ReceiveSpec : struct
%     Updated receive specification.

    ProbeSpec.nElementsX = Trans.numelements;
    ProbeSpec.nElementsY = 0;
    ProbeSpec.pitchX = Trans.spacingMm / 1e3;
    ProbeSpec.pitchY = 0;
    ProbeSpec.Fc = Trans.frequency * 1e6;
    ProbeSpec.element_position = Trans.ElementPos;

    steer = [TX.Steer] * 180 / pi;
    transmitDelays = [TX(:).Delay] / (Trans.frequency * 1e6);
    transmitDelays = reshape(transmitDelays, ProbeSpec.nElementsX, 1, length(TX));

    TransmitSpec.c0 = Resource.Parameters.speedOfSound;
    TransmitSpec.type = 'planewave';
    TransmitSpec.steerX = steer(1:2:end);
    TransmitSpec.steerY = steer(1:2:end);
    TransmitSpec.apodization = TX(1).Apod';
    TransmitSpec.transmitDelays = transmitDelays;
    TransmitSpec.nTransmission = length(TX);

    if ~isfield(ReceiveSpec, 'nSamples')
        ReceiveSpec.nSamples = Receive(1).endSample;
    end
    if ~isfield(ReceiveSpec, 'nSamplesIQ')
        ReceiveSpec.nSamplesIQ = ReceiveSpec.nSamples / 2;
    end
    if ~isfield(ReceiveSpec, 'nTransmissions')
        ReceiveSpec.nTransmissions = length(TX);
    end
    if ~isfield(ReceiveSpec, 'sampling_mode')
        ReceiveSpec.sampling_mode = Receive(1).sampleMode;
    end
    if ~isfield(ReceiveSpec, 'nRepeats')
        ReceiveSpec.nRepeats = Receive(end).framenum;
    end
    if ~isfield(ReceiveSpec, 'nChannels')
        ReceiveSpec.nChannels = Resource.RcvBuffer.colsPerFrame;
    end
    if ~isfield(ReceiveSpec, 'channel2ElementMap')
        if ~isfield(Trans, 'ConnectorES') || isempty(Trans.ConnectorES)
            error('Trans.ConnectorES is required to build channel2ElementMap.');
        end
        ReceiveSpec.channel2ElementMap = Trans.ConnectorES - 1;
    end
    if ~isfield(ReceiveSpec, 'Fs_base')
        ReceiveSpec.Fs_base = Receive(1).decimSampleRate * 1e6;
    end
    if ~isfield(ReceiveSpec, 'Fs')
        try
            ReceiveSpec.Fs = Receive(1).demodFrequency * Receive(1).samplesPerWave * 1e6;
        catch
            ReceiveSpec.Fs = ReceiveSpec.Fs_iq;
        end
    end
    if ~isfield(ReceiveSpec, 'rfDataType')
        ReceiveSpec.rfDataType = 'int16';
    end
    if ~isfield(ReceiveSpec, 'nBuffers')
        ReceiveSpec.nBuffers = max([Receive(:).bufnum]);
    end
    if ~isfield(ReceiveSpec, 'samples_per_wavelength')
        ReceiveSpec.samples_per_wavelength = Receive(1).samplesPerWave;
    end

    wvc0 = (Trans.frequency * 1e6 / Resource.Parameters.speedOfSound) ...
        * ReceiveSpec.samples_per_wavelength;

    if ~isfield(ReceiveSpec, 'startDepthMm')
        ReceiveSpec.startDepthMm = Receive(1).startDepth / wvc0 * 1e3;
    end
    if ~isfield(ReceiveSpec, 'actualEndDepthMm')
        ReceiveSpec.actualEndDepthMm = Receive(1).endDepth / wvc0 * 1e3;
    end
end
