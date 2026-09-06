function [Event, SeqControl, triggerOutEventIndex] = configurePowerDopplerEvents(nBuffers, nRepeats, nTransmissions, SeqControl)
% Configure an event sequence for power Doppler imaging.
%
% Parameters
% ----------
% nBuffers : int
%     Number of receive buffers.
% nRepeats : int
%     Ensemble size for Power Doppler calculation.
% nTransmissions : int
%     Number of plane wave angles for compounding.
% SeqControl : struct
%     Pre-existing sequence control structure to extend with additional
%     `transferToHost`, `waitForTransferComplete`, and
%     `markTransferProcessed` commands.
%
% Returns
% -------
% Event : struct
%     Event array defining the full Power Doppler acquisition sequence.
% SeqControl : struct
%     Updated sequence control structure including the new commands.
% triggerOutEventIndex : double
%     Indices into `Event` for the trigger-out events, one per buffer.
arguments
    nBuffers {mustBeInteger, mustBePositive}
    nRepeats {mustBeInteger, mustBePositive}
    nTransmissions {mustBeInteger, mustBePositive}
    SeqControl struct
end
    seqControlIndex = length(SeqControl) + 1;

    % Preallocate Event array: RF time tagging + buffers * (sync +
    % acquisitions + beamform + runtime control + publish + reset) + jump event.
    totalEvents = ( ...
        1 ...
        + nBuffers * ( ...
            1 + nRepeats*nTransmissions + 4 ...
        ) ...
        + 1 ...
    );
    Event = repmat( ...
        struct( ...
            info='', ...
            tx=0, ...
            rcv=0, ...
            recon=0, ...
            process=0, ...
            seqControl=0 ...
        ), ...
        1, ...
        totalEvents ...
    );

    eventIndex = 1;

    Event(eventIndex).info = 'Enable RF time tagging';
    Event(eventIndex).tx = 0;
    Event(eventIndex).rcv = 0;
    Event(eventIndex).recon = 0;
    Event(eventIndex).process = 1;
    Event(eventIndex).seqControl = 0;
    eventIndex = eventIndex + 1;
    postTimeTagEventIndex = eventIndex;

    triggerOutEventIndex = zeros(1, nBuffers);
    for BufferIndex = 1:nBuffers
        Event(eventIndex).info = 'Timeline synchronization and trigger output pulse';
        Event(eventIndex).tx = 0;
        Event(eventIndex).rcv = 0;
        Event(eventIndex).recon = 0;
        Event(eventIndex).process = 0;
        Event(eventIndex).seqControl = 0;
        triggerOutEventIndex(BufferIndex) = eventIndex;
        eventIndex = eventIndex + 1;

        for RepeatIndex = 1:nRepeats
            for TransmitIndex = 1:nTransmissions
                Event(eventIndex).info = 'TX/RX';
                Event(eventIndex).tx = TransmitIndex;
                Event(eventIndex).rcv = (BufferIndex-1) * nRepeats * nTransmissions + (RepeatIndex-1) * nTransmissions + TransmitIndex;
                Event(eventIndex).recon = 0;
                Event(eventIndex).process = 0;
                Event(eventIndex).seqControl = 2;
                eventIndex = eventIndex + 1;
            end
        end

        % We set the seqControl of the last Event from the TX/RX sequence
        % to transferToHost to start transfering the RF buffer.
        SeqControl(seqControlIndex).command = 'transferToHost';
        lastTransferSeqControlIndex = seqControlIndex;
        Event(eventIndex-1).seqControl = [2, seqControlIndex];
        seqControlIndex = seqControlIndex + 1;

        Event(eventIndex).info = 'Beamforming, power Doppler processing, saving to disk';
        Event(eventIndex).tx = 0;
        Event(eventIndex).rcv = 0;
        Event(eventIndex).recon = 0;
        Event(eventIndex).process = 2;
        Event(eventIndex).seqControl = seqControlIndex;
        SeqControl(seqControlIndex).command = 'waitForTransferComplete';
        SeqControl(seqControlIndex).argument = lastTransferSeqControlIndex;
        seqControlIndex = seqControlIndex + 1;
        eventIndex = eventIndex + 1;

        Event(eventIndex).info = 'Runtime control';
        Event(eventIndex).tx = 0;
        Event(eventIndex).rcv = 0;
        Event(eventIndex).recon = 0;
        Event(eventIndex).process = 3;
        Event(eventIndex).seqControl = 0;
        eventIndex = eventIndex + 1;

        Event(eventIndex).info = 'Publish processed frame';
        Event(eventIndex).tx = 0;
        Event(eventIndex).rcv = 0;
        Event(eventIndex).recon = 0;
        Event(eventIndex).process = 4;
        Event(eventIndex).seqControl = 0;
        eventIndex = eventIndex + 1;

        Event(eventIndex).info = 'Reset buffer flag and return to MATLAB';
        Event(eventIndex).tx = 0;
        Event(eventIndex).rcv = 0;
        Event(eventIndex).recon = 0;
        Event(eventIndex).process = 0;
        Event(eventIndex).seqControl = [seqControlIndex, 3];
        SeqControl(seqControlIndex).command = 'markTransferProcessed';
        SeqControl(seqControlIndex).argument = lastTransferSeqControlIndex;
        seqControlIndex = seqControlIndex + 1;
        eventIndex = eventIndex + 1;
    end

    Event(eventIndex).info = 'Jump back after RF time tagging';
    Event(eventIndex).tx = 0;
    Event(eventIndex).rcv = 0;
    Event(eventIndex).recon = 0;
    Event(eventIndex).process = 0;
    Event(eventIndex).seqControl = 4;
    SeqControl(4).argument = postTimeTagEventIndex;
end
