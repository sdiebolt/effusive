function runtimeFlags = metaRuntimeFlags(saveActive, freezeActive)
% Build the `cf_meta` runtime flag bitmask.
%
% Parameters
% ----------
% saveActive : logical
%     Whether saving is active (controls bit 0).
% freezeActive : logical
%     Whether VSX is currently frozen (controls bit 1).
%
% Returns
% -------
% runtimeFlags : uint32
%     Bitmask of runtime flags to write into `cf_meta` for napari to read.

    runtimeFlags = uint32(0);
    if saveActive
        runtimeFlags = bitor(runtimeFlags, uint32(1));
    end
    if freezeActive
        runtimeFlags = bitor(runtimeFlags, uint32(2));
    end
end
