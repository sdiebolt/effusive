function sequence = configurePowerDopplerSequence(probeName, options)
% Configure a Power Doppler plane wave sequence for a given transducer.
%
% This function configures all Verasonics and EchoFrame structures needed
% for Power Doppler imaging. It automatically sets up the transducer based
% on the probe name using VSX's computeTrans function.
%
% Parameters
% ----------
% probeName : {'L22-14v', 'L35-16vX', 'MiniProbe'}
%     Probe identifier. Must be one of:
%     - `'L22-14v'`: L22-14v linear array (15.625 MHz default)
%     - `'L35-16vX'`: L35-16vX linear array (28 MHz default)
%     - `'MiniProbe'`: Custom Cortexlab mini probe
% txrxFrameRate : float, default: 15e3
%     Acquisition frame rate before angle compounding [Hz].
%
%     !!! danger
%         This parameter affects acoustic safety. Do not change without
%         understanding the acoustic safety implications.
%
% transmitPulseLength : int, default: 3
%     Pulse length in half cycles.
%
%     !!! danger
%         This parameter affects acoustic safety. Do not change without
%         understanding the acoustic safety implications.
%
% transmitFrequency : float, default: NaN
%     Transmit frequency [MHz]. Set to NaN to use probe-specific default
%     from VSX (15.625 MHz for L22-14v, 28 MHz for L35-16vX).
%
%     !!! danger
%         This parameter affects acoustic safety. Do not change without
%         understanding the acoustic safety implications.
%
% maxHighVoltage : float, default: NaN
%     Maximum high voltage [V]. Set to NaN to use probe-specific default
%     from VSX (25 V for L22-14v/L35-16vX, 15 V for MiniProbe).
%
%     !!! danger
%         This parameter affects acoustic safety. Do not change without
%         understanding the acoustic safety implications.
%
% transmitAperturePercentage : float, default: 100
%     Transmit aperture percentage (0-100).
%
%     !!! danger
%         This parameter affects acoustic safety. Reducing aperture reduces
%         output power but changing it requires acoustic safety assessment.
%
% receiveAperturePercentage : float, default: 100
%     Receive aperture percentage (0-100).
%     Less critical for acoustic safety than transmit aperture.
%
% startDepthMm : float, default: 0
%     Starting imaging depth [mm].
% desiredEndDepthMm : float, default: 12
%     Desired end imaging depth [mm].
% nTransmissions : int, default: 30
%     Number of plane wave angles for compounding.
% nRepeats : int, default: 300
%     Ensemble size for Power Doppler calculation.
% planewaveOpeningAngle : float, default: 20
%     Total steering angle range for plane waves [degrees].
% c0 : float, default: 1510
%     Speed of sound assumption [m/s].
% samplingMode : char, default: 'BS100BW'
%     Sampling mode. Must be one of:
%
%     - `'BS50BW'`: 50% bandwidth of the demodulation frequency
%     - `'BS67BW'`: 67% bandwidth.
%     - `'BS100BW'`: 100% bandwidth.
%     - `'NS200BW'`: 200% bandwidth.
%
% tgcGain : float, default: 900
%     Time gain compensation gain.
% extraVoxelsX : int, default: 128
%     Extra voxels in X dimension for reconstruction.
%     Should ideally be a power of two.
% extraVoxelsZ : int, default: 0
%     Extra voxels in Z dimension for reconstruction.
%     Should ideally be a power of two.
% svdRejectHighPercentage : float, default: 40
%     Percentage of singular vectors from tissue subspace to remove.
% svdRejectLowPercentage : float, default: 1
%     Percentage of singular vectors from noise subspace to remove.
% initialTransmitVoltage : float, default: 1.6
%     Initial transmit voltage [V].
% zerosEndWavelengths : float, default: 3
%     Number of wavelengths to zero at the end of the TGC vector.
%
% Returns
% -------
% sequence : struct
%     Complete sequence configuration containing all Verasononics and
%     EchoFrame structures:
%     - Trans : Transducer configuration
%     - Resource : System resource configuration
%     - TX : Transmit beamforming structures
%     - TW : Transmit waveform
%     - Receive : Receive beamforming structures
%     - TGC : Time gain compensation
%     - SeqControl : Sequence control commands
%     - Event : Event sequence definition
%     - Process : External processing functions
%     - RcvProfile : Receive profile settings
%     - TPC : Transmit power control
%     - ProbeSpec : EchoFrame probe specifications
%     - TransmitSpec : EchoFrame transmit specifications
%     - ReceiveSpec : EchoFrame receive specifications
%     - ReconSpec : EchoFrame reconstruction specifications
arguments
    probeName (1, :) char {mustBeMember(probeName, {'L22-14v', 'L35-16vX', 'MiniProbe'})}
    options.txrxFrameRate (1, 1) double = 15e3
    options.transmitPulseLength (1, 1) double = 3
    options.transmitFrequency (1, 1) double = NaN
    options.maxHighVoltage (1, 1) double = NaN
    options.transmitAperturePercentage (1, 1) double = 100
    options.receiveAperturePercentage (1, 1) double = 100
    options.startDepthMm (1, 1) double = 0
    options.desiredEndDepthMm (1, 1) double = 12
    options.nTransmissions (1, 1) double = 30
    options.nRepeats (1, 1) double = 300
    options.planewaveOpeningAngle (1, 1) double = 20
    options.c0 (1, 1) double = 1510
    options.samplingMode (1, :) char {mustBeMember(options.samplingMode, {'BS50BW', 'BS67BW', 'BS100BW', 'NS200BW'})} = 'BS100BW'
    options.tgcGain (1, 1) double = 900
    options.tgcControlPoints (1, 8) double = nan(1, 8)
    options.extraVoxelsX (1, 1) double = 128
    options.extraVoxelsZ (1, 1) double = 0
    options.svdRejectHighPercentage (1, 1) double = 40
    options.svdRejectLowPercentage (1, 1) double = 1
    options.initialTransmitVoltage (1, 1) double = 1.6
    options.zerosEndWavelengths (1, 1) double = 3
end

    % Transducer setup.
    switch probeName
        case {'L22-14v', 'L35-16vX'}
            % Use VSX computeTrans for standard Verasonics probes.
            Trans = computeTrans(struct(name=probeName, units='mm'));
        case 'MiniProbe'
            % MiniProbe requires manual configuration with custom mapping.
            Trans = effusive.sequences.configureMiniProbeTransducer();
    end

    if ~isnan(options.transmitFrequency)
        % Keep both field spellings in sync: Verasonics structs use `frequency`
        % throughout this codebase, while some scripts also populate `Frequency`.
        Trans.frequency = options.transmitFrequency;
        Trans.Frequency = options.transmitFrequency;
    end

    if ~isnan(options.maxHighVoltage)
        Trans.maxHighVoltage = options.maxHighVoltage;
    end

    % EchoFrame transmit and receive specifications.
    TransmitSpec = effusive.sequences.configureTransmitSpec( ...
        Trans.numelements, ...
        options.txrxFrameRate, ...
        options.transmitPulseLength, ...
        options.transmitAperturePercentage, ...
        options.planewaveOpeningAngle, ...
        options.c0 ...
    );

    % numRcvChannels is a Vantage hardware constant, also set in configureResource.
    numRcvChannels = 128;
    ReceiveSpec = effusive.sequences.configureReceiveSpec( ...
        Trans.numelements, ...
        numRcvChannels, ...
        Trans.frequency, ...
        Trans.lensCorrection, ...
        options.c0, ...
        options.samplingMode, ...
        options.receiveAperturePercentage, ...
        options.startDepthMm, ...
        options.desiredEndDepthMm, ...
        options.nTransmissions, ...
        options.nRepeats, ...
        options.txrxFrameRate, ...
        options.tgcGain, ...
        options.tgcControlPoints, ...
        2 ...
    );

    % System resource configuration (requires ReceiveSpec for buffer sizing).
    Resource = effusive.sequences.configureResource(ReceiveSpec, options.c0);

    % Image reconstruction specification.
    ReconSpec = struct( ...
        nDims=2, ...
        extra_voxels_z=options.extraVoxelsZ, ...
        extra_voxels_x=options.extraVoxelsX, ...
        svdRejectHighPercentage=options.svdRejectHighPercentage, ...
        svdRejectLowPercentage=options.svdRejectLowPercentage, ...
        c0=options.c0, ...
        samples_per_wavelength=ReceiveSpec.samples_per_wavelength ...
    );

    % Transducer-derived probe specification.
    ProbeSpec = struct( ...
        Fc=Trans.frequency * 1e6, ...
        pitchX=Trans.spacingMm * 1e-3, ...
        pitchY=0, ...
        useOuterElements=true ...
    );

    % System receive profile.
    if strcmp(probeName, 'L35-16vX')
        RcvProfile = struct( ...
            LnaZinSel=30, ...
            AntiAliasCutoff=20, ...
            LnaGain=15, ...
            PgaGain=24 ...
        );
    else
        RcvProfile = struct( ...
            LnaZinSel=15, ...
            AntiAliasCutoff=35, ...
            LnaGain=18, ...
            PgaGain=30 ...
        );
    end

    % Transmit waveform.
    TW = effusive.sequences.configureTransmitWaveform( ...
        ProbeSpec.Fc, TransmitSpec.transmitPulseLength ...
    );

    % Transmit beam steering.
    TX = effusive.sequences.configureTransmitBeams( ...
        TransmitSpec, Trans, Resource, ReceiveSpec ...
    );

    % Receive structure.
    Receive = effusive.sequences.configureReceive(Trans.frequency, ReceiveSpec);

    % Time gain compensation.
    TGC = effusive.sequences.configureTGC(ReceiveSpec, Trans);

    % TGC vector for EchoFrame.
    ReconSpec = effusive.sequences.configureTGCVector( ...
        ReconSpec, ReceiveSpec, zerosEndWavelengths=options.zerosEndWavelengths ...
    );

    % External processing functions.
    Process = effusive.sequences.getCommonProcessFunctions();

    % Sequence control.
    SeqControl = effusive.sequences.getCommonSequenceControl( ...
        ReceiveSpec.transmitReceiveTimeMus ...
    );

    % Event sequence.
    [Event, SeqControl, triggerOutEventIndex] = effusive.sequences.configurePowerDopplerEvents( ...
        ReceiveSpec.nBuffers, ReceiveSpec.nRepeats, ReceiveSpec.nTransmissions, SeqControl ...
    );

    % Transmit power control.
    TPC = effusive.sequences.configureTPC(options.initialTransmitVoltage);

    sequence = struct( ...
        Trans=Trans, ...
        Resource=Resource, ...
        TX=TX, ...
        TW=TW, ...
        Receive=Receive, ...
        TGC=TGC, ...
        SeqControl=SeqControl, ...
        Event=Event, ...
        triggerOutEventIndex=triggerOutEventIndex, ...
        Process=Process, ...
        RcvProfile=RcvProfile, ...
        TPC=TPC, ...
        ProbeSpec=ProbeSpec, ...
        TransmitSpec=TransmitSpec, ...
        ReceiveSpec=ReceiveSpec, ...
        ReconSpec=ReconSpec ...
    );
end
