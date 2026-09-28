[![PyPI version](https://img.shields.io/pypi/v/effusive?style=flat-square&color=ffd33d&label=PyPI)](https://pypi.org/project/effusive/)
[![Python versions](https://img.shields.io/pypi/pyversions/effusive?style=flat-square&color=0099e5&logo=python&logoColor=white)](https://pypi.org/project/effusive/)
[![License](https://img.shields.io/github/license/sdiebolt/effusive?style=flat-square&color=3ad9a4)](https://github.com/sdiebolt/effusive/blob/main/LICENSE)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.22555686-8b7ff7?style=flat-square)](https://doi.org/10.5281/zenodo.22555686)
[![Docs](https://img.shields.io/github/actions/workflow/status/sdiebolt/effusive/docs.yml?branch=main&style=flat-square&label=docs)](https://sdiebolt.github.io/effusive/)
[![Discord](https://img.shields.io/badge/Discord-join-5865F2?style=flat-square&logo=discord&logoColor=white)](https://discord.gg/mZd87tgmy2)

# Effusive

Effusive is an open-source acquisition and control application for functional ultrasound
imaging (fUSI) on Verasonics Vantage systems. It provides a napari-based interface for
configuring acquisitions, visualizing B-mode and power Doppler images in real time, and
recording fUSI data. Effusive builds on
[EchoFrame](https://github.com/BrainEchoLab/EchoFrame) for high-performance ultrasound
beamforming and acquisition.

> [!WARNING]
> Effusive is alpha software. Use it at your own risk, especially on acquisition
> hardware. If you want to start experimenting with it, please contact the maintainers.

## Requirements

- Linux or Windows.
- Python 3.11 with `uv`.
- MATLAB R2024a.
- Verasonics Vantage software 5.0.0.
- [EchoFrame](https://github.com/BrainEchoLab/EchoFrame)
- Optional: a sender for [mpep](https://github.com/cortex-lab/mpep)-compatible UDP experiment-control messages.

## Run

On Windows, start terminal as administrator.

```bash
uv run effusive
```

Then click the play button in the napari sidebar. The UI stays in `Starting...`
until the first frame arrives from MATLAB.

## Configuration

Defaults ship in `src/effusive/default_config.toml`. User settings persist in
`platformdirs.user_config_dir("effusive")` as `current_config.toml`
(for example `~/.config/effusive/current_config.toml` on Linux).

Config covers probe defaults, acquisition settings, storage path,
simulate mode, z-stack defaults, BIDS-like metadata, and the last crop ROI.
