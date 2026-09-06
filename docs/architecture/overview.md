---
icon: lucide/network
---

# Architecture Overview

This page describes how Effusive's Python, MATLAB, and Verasonics pieces fit together at runtime.

## Main Components

- `effusive` CLI starts napari and launches the MATLAB worker subprocess.
- The napari widget writes operator commands into a session-scoped shared-memory channel set and reads processed frame data back out.
- The MATLAB worker configures the Verasonics sequence and the VSX base workspace before calling `VSX`.
- VSX runs the acquisition/event loop and calls external Effusive process functions each buffer.
- EchoFrame performs beamforming and power Doppler processing inside `processRFEnsembleBlock`.

## Runtime Data Flow

```mermaid
flowchart LR
    A[napari viewer\nEffusive widget] -->|commands| B[cf_cmd_*]
    E[VSX external processes] -->|status + frames| C[cf_bmode_* / cf_pdi_*\ncf_meta_* / cf_stack_*\ncf_rf_* / cf_ack_*]
    C --> A
    D[MATLAB worker] -->|setup sequence + workspace| F[VSX]
    F -->|calls each buffer| E
    E -->|RF input| G[EchoFrame mex]
    G -->|B-mode / PDI| E
    H[mpep-compatible UDP sender\nhttps://github.com/cortex-lab/mpep] -->|start / stop| E
```

## Per-Buffer Processing Shape

After each RF buffer transfer completes, VSX calls three external process functions in sequence.

```mermaid
sequenceDiagram
    participant UI as napari UI
    participant SHM as Shared memory
    participant VSX as VSX event loop
    participant P2 as Process 2<br/>processRFEnsembleBlock
    participant EF as EchoFrame mex
    participant P3 as Process 3<br/>processRuntimeControl
    participant P4 as Process 4<br/>publishProcessedFrame

    UI->>SHM: write cf_cmd_* (commands + req IDs)
    VSX->>VSX: acquire TX/RX ensemble
    VSX->>VSX: transferToHost
    VSX->>P2: waitForTransferComplete → call
    P2->>EF: process RF buffer
    EF-->>P2: B-mode + PDI
    P2->>P2: populate FrameRuntimeState
    VSX->>P3: call
    P3->>SHM: read cf_cmd_*, apply mutations, write cf_ack_* + cf_stack_*
    VSX->>P4: call
    P4->>SHM: write cf_bmode_*, cf_pdi_*, cf_meta_* (+ cf_rf_* if requested)
    SHM-->>UI: next poll reads fresh frame
```

The `*` suffix here means "one unique segment set per acquisition run". Python creates
fresh names before launching MATLAB and passes the resolved names into the worker.

## Ownership Boundaries

- Python owns napari presentation, operator input, worker lifecycle, and shared-memory polling.
- MATLAB owns Verasonics sequence configuration, process-function orchestration, and base-workspace runtime state.
- EchoFrame owns beamforming and Doppler processing internals.
- VSX owns event scheduling and process callback invocation.

## Further Reading

- [Event Timeline](event-timeline.md) — full per-buffer event sequence and process function assignments.
- [Shared Memory Protocol](shared-memory.md) — segment layouts, ownership, and request/ack protocol.
- [Runtime Control](runtime-control.md) — command semantics, save state machine, and z-stack control.
