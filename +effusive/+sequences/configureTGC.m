function TGC = configureTGC(ReceiveSpec, Trans)
% Configure the Verasonics time gain compensation structure.
%
% Parameters
% ----------
% ReceiveSpec : struct
%     EchoFrame receive specification; tgcGain and endDepthWavelengths
%     used.
% Trans : struct
%     Verasonics transducer structure. Not directly referenced in this function, but
%     must be present in the workspace for `computeTGCWaveform` to access
%     `Trans.frequency` via `evalin('caller', ...)`.
%
% Returns
% -------
% TGC : struct
%     Verasonics time gain compensation structure.
arguments
    ReceiveSpec (1, 1) struct
    Trans (1, 1) struct
end

    if ~isfield(Trans, 'frequency')
        error( ...
            'configureTGC:MissingTransFrequency', ...
            'Trans.frequency is required to compute the TGC waveform.' ...
        );
    end

    TGC = struct();
    if isfield(ReceiveSpec, 'tgcControlPoints') && all(~isnan(ReceiveSpec.tgcControlPoints))
        TGC(1).CntrlPts = ReceiveSpec.tgcControlPoints;
    else
        TGC(1).CntrlPts = [1,1,1,1,1,1,1,1] .* ReceiveSpec.tgcGain;
    end
    TGC(1).rangeMax = ReceiveSpec.endDepthWavelengths;
    TGC(1).Waveform = computeTGCWaveform(TGC(1));
end
