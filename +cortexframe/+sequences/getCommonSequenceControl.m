function SeqControl = getCommonSequenceControl(transmitReceiveTimeMus)
% Get standard sequence control commands.
%
% This function initializes a `SeqControl` structure with four sequence
% control commands used in most sequences:
%
% - `SeqControl(1)`: `triggerOut`.
% - `SeqControl(2)`: `timeToNextAcq`, with argument `transmitReceiveTimeMus`.
% - `SeqControl(3)`: `returnToMatlab`.
% - `SeqControl(4)`: `jump` to first `Event`.
%
% Parameters
% ----------
% transmitReceiveTimeMus : integer
%     Time between two acquisition events, in microseconds ranging from 0
%     to 4190000.
%
% Returns
% -------
% SeqControl : struct
%     `SeqControl` struct initialized with the four control commands.
    arguments
        transmitReceiveTimeMus (1, 1) {mustBeInteger, mustBeNonnegative}
    end
    SeqControl = struct();

    SeqControl(1).command = 'triggerOut';

    SeqControl(2).command = 'timeToNextAcq';
    SeqControl(2).argument = transmitReceiveTimeMus;

    SeqControl(3).command = 'returnToMatlab';

    SeqControl(4).command = 'jump';
    SeqControl(4).argument = 1;
end
