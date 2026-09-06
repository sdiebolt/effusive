function reinitEchoFrameStorage( ...
    mexCommand, useActiveStorage, StorageSpec, ReceiveSpec, ReconSpec, PDISpec, ...
    ExperimentSpec, TransmitSpec, ProbeSpec)
% Re-initialize EchoFrame storage for a MEX command, choosing active or inactive specs.
%
% Parameters
% ----------
% mexCommand : char
%     EchoFrame MEX re-init command, e.g. `'re-init storage'` or
%     `'re-init experiment'`.
% useActiveStorage : logical
%     When `true`, build storage specs from `StorageSpec` via
%     [`cortexframe.echoframe.configureEchoFrameStorageSpecs`](). When
%     `false`, build placeholder specs via
%     [`cortexframe.rf.inactiveStorageSpecs`]().
% StorageSpec : struct
%     EchoFrame storage specification; only read when `useActiveStorage`.
% ReceiveSpec : struct
%     EchoFrame receive specification.
% ReconSpec : struct
%     EchoFrame reconstruction specification.
% PDISpec : struct
%     EchoFrame PDI specification.
% ExperimentSpec : struct
%     Experiment specification; only read when `useActiveStorage`.
% TransmitSpec : struct
%     Transmit specification; only read when `useActiveStorage`.
% ProbeSpec : struct
%     Probe specification; only read when `useActiveStorage`.
arguments
    mexCommand (1, :) char
    useActiveStorage (1, 1) logical
    StorageSpec (1, 1) struct
    ReceiveSpec (1, 1) struct
    ReconSpec (1, 1) struct
    PDISpec (1, 1) struct
    ExperimentSpec (1, 1) struct
    TransmitSpec (1, 1) struct
    ProbeSpec (1, 1) struct
end
    if useActiveStorage
        [BFStorageSpec, PDIStorageSpec, RFTimeTagStorageSpec, RFStorageSpec] = cortexframe.echoframe.configureEchoFrameStorageSpecs( ...
            're-init', StorageSpec, ReceiveSpec, ReconSpec, PDISpec, ...
            ExperimentSpec, TransmitSpec, ProbeSpec ...
        );
    else
        [BFStorageSpec, PDIStorageSpec, RFTimeTagStorageSpec, RFStorageSpec] = ...
            cortexframe.rf.inactiveStorageSpecs(ReconSpec, PDISpec);
    end
    echoframe_mex( ...
        mexCommand, BFStorageSpec, PDIStorageSpec, RFTimeTagStorageSpec, RFStorageSpec, ...
        ReconSpec, PDISpec ...
    );
end
