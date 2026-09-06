function logMessage(message, varargin)
% Emit a consistently-prefixed MATLAB log line.
%
% Parameters
% ----------
% message : char | string
%     Message format string written after the standard `[matlab]`
%     prefix. A trailing newline is added automatically when missing.
% varargin : any
%     Optional values forwarded to `fprintf`.

    if nargin == 0
        return
    end

    if isstring(message)
        message = char(message);
    end

    fprintf('[matlab] ');
    fprintf(message, varargin{:});

    if isempty(message) || message(end) ~= newline
        fprintf('\n');
    end
end
