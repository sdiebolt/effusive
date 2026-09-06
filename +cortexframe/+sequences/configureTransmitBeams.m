function TX = configureTransmitBeams(TransmitSpec, Trans, Resource, ReceiveSpec)
% Configure the Verasonics transmit beam steering structure.
%
% Parameters
% ----------
% TransmitSpec : struct
%     EchoFrame transmit specification; apodization and
%     planewaveOpeningAngle used.
% Trans : struct
%     Verasonics transducer structure.
% Resource : struct
%     Verasonics resource structure.
% ReceiveSpec : struct
%     EchoFrame receive specification; nTransmissions used.
%
% Returns
% -------
% TX : struct
%     Verasonics transmit beamforming structure array, one entry per
%     steering angle.
%
% Notes
% -----
% Base workspace variables:
%
% - `Resource` (struct, write): Temporarily written to the base
%   workspace for `computeTXDelays`, then cleared.
% - `Trans` (struct, write): Temporarily written to the base workspace
%   for `computeTXDelays`, then cleared.
arguments
    TransmitSpec (1, 1) struct
    Trans (1, 1) struct
    Resource (1, 1) struct
    ReceiveSpec (1, 1) struct
end
    TX = repmat( ...
        struct( ...
            waveform=1, ...
            Origin=[0.0, 0.0, 0.0], ...
            focus=0.0, ...
            Steer=[0.0, 0.0], ...
            Apod=TransmitSpec.apodization, ...
            Delay=zeros(1, Resource.Parameters.numTransmit) ...
        ), ...
        1, ...
        ReceiveSpec.nTransmissions ...
    );

    dthetaDop = (TransmitSpec.planewaveOpeningAngle * pi/180) / (ReceiveSpec.nTransmissions - 1);
    startAngleDop = -TransmitSpec.planewaveOpeningAngle * pi / 180 / 2;

    % Verasonics requires Resource and Trans in the base workspace to
    % compute delays.
    assignin('base', 'Resource', Resource);
    assignin('base', 'Trans', Trans)
    for n = 1:ReceiveSpec.nTransmissions
        TX(n).Steer = [(startAngleDop + (n-1)*dthetaDop), 0.0];
        TX(n).Delay = computeTXDelays(TX(n));
    end
    evalin('base', 'clear Resource Trans');
end
