function activateVantage(vantagePath)
% Activate a Vantage project folder.
%
% Parameters
% ----------
% vantagePath : str, default: getenv('VERASONICS_VPF_ROOT')
%     Path to a Vantage project folder. By default, the
%     `VERASONICS_VPF_ROOT` environment variable will be used.
arguments
    vantagePath {mustBeFolder} = getenv('VERASONICS_VPF_ROOT')
end

    currentDirectory = pwd;
    restoreDirectory = onCleanup(@() cd(currentDirectory));

    cd(vantagePath);
    activate(showEula=false);
end
