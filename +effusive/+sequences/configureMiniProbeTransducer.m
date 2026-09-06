function Trans = configureMiniProbeTransducer()
% Configure mini probe transducer `Trans` structure.
%
% This probe uses the L22-14v connector but with custom element mapping.
%
% Returns
% -------
% struct
%     The `Trans` structure to be used with VSX for the mini probe.

    Trans = struct();
    Trans.name = 'cortex mini probe';
    Trans.id = hex2dec('02AB18');
    Trans.units = 'mm';
    Trans.frequency = 15.625;
    % 80% relative bandwidth.
    Trans.Bandwidth = Trans.frequency * [1-0.4, 1+0.4];
    % Linear array.
    Trans.type = 0;
    % HDI connector.
    Trans.connType = 1;
    Trans.numelements = 128;
    % 90 micron pitch (different from L22-14v).
    Trans.spacingMm = 0.09;
    Trans.elementWidth = 0.8 * Trans.spacingMm;
    Trans.elevationApertureMm = 6.0;
    % Nominal elevation focus depth from lens on face of transducer.
    Trans.elevationFocusMm = 15;
    Trans.maxHighVoltage = 15;

    % Element positions.
    Trans.ElementPos = zeros(Trans.numelements, 5);
    Trans.ElementPos(:,1) = Trans.spacingMm * ( ...
        -((Trans.numelements - 1) / 2):((Trans.numelements - 1) / 2) ...
    );
    % No lens correction for mini probe.
    Trans.lensCorrection = 0;

    % Element sensitivity.
    Theta = (-pi/2:pi/100:pi/2);
    Theta(51) = 0.0000001;
    Trans.ElementSens = abs(cos(Theta));

    % Connector mapping - use custom mini probe mapping.
    [~, Trans.ConnectorES] = sort(effusive.probes.miniProbeMapping());

    % Impedance - same as L22-14v.
    Trans.impedance = [
        10.00, 11.16-54.28i;
        11.00, 12.02-44.73i;
        12.00, 14.38-39.52i;
        13.00, 14.19-33.50i;
        14.00, 14.43-27.21i;
        15.00, 16.01-21.87i;
        16.00, 16.82-17.73i;
        17.00, 17.81-13.12i;
        18.00, 18.65-8.77i;
        19.00, 20.90-4.20i;
        20.00, 23.60-1.48i;
        21.00, 25.54+0.61i;
        22.00, 27.02+1.89i;
        23.00, 26.97+2.95i;
        24.00, 25.99+5.39i;
        25.00, 25.24+9.19i
    ];
end
