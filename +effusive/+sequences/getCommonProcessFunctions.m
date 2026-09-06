function Process = getCommonProcessFunctions()
% Configure standard external processing functions.
%
% This function initializes a `Process` structure with four external
% processing functions used in most sequences:
%
% - `Process(1) = effusive.vantage.enableRFTimeTagging` should be used
%   as the very first Event in the sequence and will enable RF time
%   tagging.
% - `Process(2) = effusive.rf.processRFEnsembleBlock` runs echoframe_mex
%   and writes results into FrameRuntimeState.
% - `Process(3) = effusive.control.processRuntimeControl` decodes napari
%   commands and applies hardware/storage mutations.
% - `Process(4) = effusive.rf.publishProcessedFrame` writes display data
%   to shared memory and emits timing reports.
%
% Returns
% -------
% struct
%     `Process` struct initialized with the four process functions.
    Process = struct();
    Process(1).classname = 'External';
    Process(1).method = 'effusive.vantage.enableRFTimeTagging';
    Process(1).Parameters = {'srcbuffer', 'none'};

    Process(2).classname = 'External';
    Process(2).method = 'effusive.rf.processRFEnsembleBlock';
    Process(2).Parameters = {
        'srcbuffer', 'receive', ...
        'srcbufnum', 1, ...
        'srcframenum', -1, ...
        'dstbuffer', 'none'
    };

    Process(3).classname = 'External';
    Process(3).method = 'effusive.control.processRuntimeControl';
    Process(3).Parameters = {'srcbuffer', 'none'};

    Process(4).classname = 'External';
    Process(4).method = 'effusive.rf.publishProcessedFrame';
    Process(4).Parameters = {'srcbuffer', 'none'};
end
