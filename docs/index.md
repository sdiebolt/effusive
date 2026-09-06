---
icon: lucide/house
---

# CortexFrame

Hybrid Python/MATLAB functional ultrasound imaging (fUSI) acquisition app for the
[Cortexlab](https://www.ucl.ac.uk/brain-sciences/cortexlab) (UCL). CortexFrame opens a
napari control UI, launches a MATLAB worker subprocess, and drives a Verasonics
Vantage scanner through [EchoFrame](https://github.com/watermarkhu/echoframe), with
optional experiment control via [mpep](https://github.com/cortex-lab/mpep)-compatible
UDP messages.

## Setup

Set the following environment variables before launch:

| Variable | Purpose |
|---|---|
| `ECHOFRAME_PATH` | Root of the EchoFrame library |
| `CORTEXFRAME_PATH` | Root of this repository |
| `VERASONICS_VPF_ROOT` | Root of the Verasonics Vantage install |

## Usage

Launch the napari viewer from the command line (run as administrator on Windows):

```bash
uv run cortexframe
```

Then click the play button in the sidebar. CortexFrame runs MATLAB in an isolated
subprocess and streams B-mode/PDI frames to napari through session-scoped shared
memory.

## Features

- Live B-mode and Power Doppler viewing in napari.
- Runtime controls for freeze, voltage, TX/RX aperture, TGC, SVD, crop, RF snapshots, and recording.
- BIDS-like storage naming with path previews and disk free-space feedback in the metadata panel.
- Recording can be started from the UI or by [mpep](https://github.com/cortex-lab/mpep)-compatible UDP triggers.
- Z-stack acquisition with Zaber motor control and NIfTI export.

## API Reference

- [Sequences](./api/sequences.md) — Acquisition sequence definitions
- [Probes](./api/probes.md) — Probe configuration
- [RF Processing](./api/rf.md) — RF data processing
- [Vantage Control](./api/vantage.md) — Verasonics Vantage interface
- [UDP Communication](./api/udp.md) — [mpep](https://github.com/cortex-lab/mpep)-compatible experiment control
- [Utilities](./api/utilities.md) — Logging and z-stack export
- [Motor Control](./api/motor.md) — Zaber motor interface

## Architecture

- [Overview](./architecture/overview.md) — Runtime relationships between napari, MATLAB, VSX, EchoFrame, and shared memory
