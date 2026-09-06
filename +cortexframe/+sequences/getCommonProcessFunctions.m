function Process = getCommonProcessFunctions()
% Configure standard external processing functions.
%
% This function initializes a `Process` structure with four external
% processing functions used in most sequences:
%
% - `Process(1) = cortexframe.vantage.enableRFTimeTagging` should be used
%   as the very first Event in the sequence and will enable RF time
%   tagging.
% - `Process(2) = cortexframe.rf.processRFEnsembleBlock` runs echoframe_mex
%   and writes results into FrameRuntimeState.
% - `Process(3) = cortexframe.control.processRuntimeControl` decodes napari
%   commands and applies hardware/storage mutations.
% - `Process(4) = cortexframe.rf.publishProcessedFrame` writes display data
%   to shared memory and emits timing reports.
%
% Returns
% -------
% struct
%     `Process` struct initialized with the four process functions.
    Process = struct();
    Process(1).classname = 'External';
    Process(1).method = 'cortexframe.vantage.enableRFTimeTagging';
    Process(1).Parameters = {'srcbuffer', 'none'};

    Process(2).classname = 'External';
    Process(2).method = 'cortexframe.rf.processRFEnsembleBlock';
    Process(2).Parameters = {
        'srcbuffer', 'receive', ...
        'srcbufnum', 1, ...
        'srcframenum', -1, ...
        'dstbuffer', 'none'
    };

    Process(3).classname = 'External';
    Process(3).method = 'cortexframe.control.processRuntimeControl';
    Process(3).Parameters = {'srcbuffer', 'none'};

    Process(4).classname = 'External';
    Process(4).method = 'cortexframe.rf.publishProcessedFrame';
    Process(4).Parameters = {'srcbuffer', 'none'};
end
