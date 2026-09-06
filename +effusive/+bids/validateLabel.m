function label = validateLabel(value, fieldName, required)
% Validate one BIDS-like entity label.
%
% Parameters
% ----------
% value : char | string
%     Raw entity label without its BIDS key prefix.
% fieldName : char | string
%     Human-readable field name used in error messages.
% required : logical, default: false
%     Whether an empty label should be rejected.
%
% Returns
% -------
% label : char
%     Trimmed label text when valid.
    arguments
        value
        fieldName
        required (1, 1) logical = false
    end

    label = char(string(value));
    label = strtrim(label);
    if isempty(label)
        if required
            error('%s is required.', char(string(fieldName)));
        end
        return;
    end

    if isempty(regexp(label, '^[A-Za-z0-9]+$', 'once'))
        error('%s must match [A-Za-z0-9]+.', char(string(fieldName)));
    end
end
