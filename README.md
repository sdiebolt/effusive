# CortexFrame

CortexFrame is Cortexlab's hybrid Python/MATLAB fUSI acquisition app for Verasonics
Vantage. The `cortexframe` CLI opens a napari control UI, launches a MATLAB worker
subprocess, and streams live B-mode/PDI frames through Python shared memory while
MATLAB keeps ownership of VSX and EchoFrame.

> [!WARNING]
> EchoFrame-fUSI is alpha software. Use it at your own risk, especially on acquisition hardware.
> If you want to start experimenting with it, please open an issue or contact the maintainers.

## What it does

- Live napari viewer for B-mode and Power Doppler.
- MATLAB worker configures Verasonics/VSX and EchoFrame.
- Session-scoped shared-memory command/status path between napari and MATLAB.
- Runtime controls for freeze, voltage, TX/RX aperture, TGC, SVD, crop, RF snapshot, and save.
- Recording with BIDS-like naming, startable from the UI or mpep-compatible UDP triggers.
- Storage-path previews, BIDS entity previews, and free-space monitoring in the metadata panel.
- Z-stack acquisition with Zaber motor support.

## Requirements

- Linux or Windows.
- Python 3.11 with `uv`.
- MATLAB R2024a.
- Verasonics Vantage software 5.0.0.
- [EchoFrame](https://gitlab.com/c7859/cube-ultrasound-brain-imaging/EchoFrame).
- Optional: a sender for [mpep](https://github.com/cortex-lab/mpep)-compatible UDP experiment-control messages.

Set environment before launch:

| Variable | Purpose |
|---|---|
| `CORTEXFRAME_PATH` | Root of this repository. |
| `ECHOFRAME_PATH` | Root of EchoFrame. |
| `ECHOFRAME_MEX_ROOT` | Directory containing `echoframe_mex.*` (for example `EchoFrame/build`). |
| `VERASONICS_VPF_ROOT` | Root of Verasonics Vantage install. |

## Run

On Windows, start terminal as administrator.

```bash
uv run cortexframe
```

Then click the play button in the napari sidebar. The UI stays in `Starting...`
until the first frame arrives from MATLAB.

## Configuration

Defaults ship in `src/cortexframe/default_config.toml`. User settings persist in
`platformdirs.user_config_dir("cortexframe")` as `current_config.toml`
(for example `~/.config/cortexframe/current_config.toml` on Linux).

Config covers probe defaults, acquisition settings, storage path,
simulate mode, z-stack defaults, BIDS-like metadata, and the last crop ROI.

## Docs

- Build docs: `just docs`
- Serve docs: `just serve-docs`
- Architecture overview: `docs/architecture/overview.md`

