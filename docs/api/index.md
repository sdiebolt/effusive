---
icon: lucide/book-open
---

# API Reference

Complete reference documentation for the Effusive API.

## MATLAB API

<div class="grid cards" markdown>

- **[:lucide-layers: Sequences](sequences.md)**

    ---

    Verasonics sequence configuration for power Doppler plane wave imaging.

- **[:lucide-cpu: Vantage](vantage.md)**

    ---

    Verasonics Vantage hardware helpers: project activation and RF time tagging.

- **[:lucide-mic-vocal: Probes](probes.md)**

    ---

    Transducer connector mappings for Cortexlab probes.

- **[:lucide-audio-waveform: RF](rf.md)**

    ---

    RF data processing: beamforming and power Doppler computation.

- **[:lucide-wrench: Utilities](utilities.md)**

    ---

    Logging helpers and z-stack NIfTI export.

- **[:lucide-move-3d: Motor Control](motor.md)**

    ---

    Zaber motor control interface and GUI.

- **[:lucide-app-window: GUI](gui.md)**

    ---

    Acquisition GUI figures for B-mode, power Doppler, and Y-stack imaging.

</div>

## Python API

<div class="grid cards" markdown>

- **[:lucide-settings: Configuration](python/config.md)**

    ---

    Dataclasses and loading functions for the two-file config system.

- **[:lucide-share-2: Shared Memory](python/shared_memory.md)**

    ---

    Session-scoped Python shared-memory segments, layout constants, and the IPC protocol.

- **[:lucide-terminal: CLI](python/cli.md)**

    ---

    Command-line entry point for the napari viewer.

- **[:lucide-cpu: MATLAB Worker](python/matlab_worker.md)**

    ---

    Subprocess that runs the MATLAB engine and drives the VSX acquisition loop.

- **[:lucide-radio: UDP Control](python/udp_control.md)**

    ---

    Python-side UDP server for [mpep](https://github.com/cortex-lab/mpep)-compatible experiment control.

- **[:lucide-move-3d: Motor Controller](python/motor_controller.md)**

    ---

    Python-side serial controller for manual z-stack motor jogging.

</div>
