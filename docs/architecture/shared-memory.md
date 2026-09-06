---
icon: lucide/memory-stick
---

# Shared Memory Protocol

CortexFrame uses Python's `multiprocessing.shared_memory` transport to exchange images,
metadata, commands, and status between the Python napari process and the MATLAB worker
subprocess. Each acquisition run gets its own uniquely named segment set (for example
`cf_meta_<run_token>`), created by Python before the worker launches, zero-initialised,
and opened by MATLAB on first use.

## Segment Summary

The table uses logical channel names. At runtime each one is suffixed with a
session token so multiple acquisitions cannot collide with stale segments from a
previous run.

| Logical name | Runtime example | Size | Written by | Read by | Purpose |
|------|------|------|-----------|---------|---------|
| `cf_meta` | `cf_meta_20260519_153012_123456` | 44 bytes | MATLAB (setup + publish) | Python | Frame counter, image dimensions, depth axes, runtime flags, hardware timestamp |
| `cf_bmode` | `cf_bmode_...` | 1 MB | MATLAB (publish) | Python | Raw B-mode image (float32, un-normalized) |
| `cf_pdi` | `cf_pdi_...` | 1 MB | MATLAB (publish) | Python | Raw PDI image (float32, un-normalized) |
| `cf_cmd` | `cf_cmd_...` | 116 bytes | Python | MATLAB | Operator commands and request IDs |
| `cf_rf` | `cf_rf_...` | ~1 MB | MATLAB (publish) | Python | Raw RF snapshot header + int16 data |
| `cf_stack` | `cf_stack_...` | 16 bytes | MATLAB (control) | Python | Z-stack state machine status |
| `cf_ack` | `cf_ack_...` | 36 bytes | MATLAB (control) | Python | Command acknowledgement IDs |

Image segments (`cf_bmode`, `cf_pdi`) are allocated for the maximum supported image size of 512 × 512 pixels. Only the first `nz × nx` elements are valid; dimensions are read from `cf_meta`.

## Segment Layouts

### `cf_meta` / `cf_meta_*` (44 bytes)

Written by `cortexframe.napari.setup` (dimensions and axes) and by `publishProcessedFrame` (counter, flags, timestamp) each frame.

```
[0:8]    uint64   frame_counter       incremented every published frame
[8:12]   int32    nz                  image height in pixels (set at setup)
[12:16]  int32    nx                  image width in pixels (set at setup)
[16:20]  float32  z_start_mm          depth axis start (mm)
[20:24]  float32  z_end_mm            depth axis end (mm)
[24:28]  float32  x_start_mm          lateral axis start (mm)
[28:32]  float32  x_end_mm            lateral axis end (mm)
[32:36]  uint32   runtime_flags       bitmask (see below)
[36:44]  float64  ensemble_time_s     hardware ensemble timestamp (s); 0 if unavailable
```

Runtime flag bits:

| Bit | Constant | Meaning |
|-----|----------|---------|
| 0 | `META_FLAG_SAVE_ACTIVE` | EchoFrame is currently saving to disk |
| 1 | `META_FLAG_FREEZE_ACTIVE` | Acquisition is frozen in VSX |

### `cf_bmode` / `cf_bmode_*` and `cf_pdi` / `cf_pdi_*` (1 MB each)

Row-major float32 arrays of shape `[nz, nx]`, written transpose-then-flatten from MATLAB. Both carry
**raw, un-normalized** amplitude/power straight from EchoFrame -- no log-compression or scaling happens
on the MATLAB side.

Python reads these with `numpy.ndarray(..., dtype=numpy.float32, buffer=shm.buf)`, copies `nz × nx`
elements, then log-compresses each to dB relative to that frame's own peak
(`ShmReader.read_bmode`/`read_pdi` in `shared_memory.py`):

- `cf_bmode`: `20 * log10(raw / raw.max())`, clipped to `BMODE_CONTRAST_LIMITS` (`[-60, 0]` dB).
- `cf_pdi`: `10 * log10(raw / raw.max())`, clipped to `PDI_CONTRAST_LIMITS` (`[-30, 0]` dB).

Doing this on the Python side keeps the max-reduce and log10 work off the VSX-blocking MATLAB
callback chain; it runs on napari's decoupled polling tick instead, which cannot stall acquisition.

### `cf_cmd` / `cf_cmd_*` (116 bytes)

Written entirely by Python each command; MATLAB reads it every frame in `processRuntimeControl`.

```
[0]      uint8    vsExit                  0=run, 1=stop VSX
[1]      uint8    freeze                  0=run, 1=freeze acquisition
[2]      uint8    save_to_disk            master save switch (1=enabled)
[3]      uint8    svd_update_flag         1=apply new SVD threshold
[4:6]    int16    svd_threshold           SVD rejection threshold (0-100 %; stored as percent×100)
[6]      uint8    voltage_update_flag     1=apply new transmit voltage
[7]               pad
[8:12]   float32  voltage_v               transmit voltage (V)
[12]     uint8    tx_aperture_update_flag 1=apply TX aperture
[13]     uint8    rx_aperture_update_flag 1=apply RX aperture
[14:16]  int16    tx_aperture             TX aperture (0-100 %)
[16:18]  int16    rx_aperture             RX aperture (0-100 %)
[18]     uint8    show_rf                 rising edge triggers RF snapshot
[19]     uint8    crop_update_flag        1=apply new ROI crop
[20]     uint8    crop_reset_flag         1=reset crop to full FOV
[21]              pad
[22:24]  int16    roi_top                 crop top row (0-based)
[24:26]  int16    roi_bottom              crop bottom row (0-based)
[26:28]  int16    roi_left                crop left column (0-based)
[28:30]  int16    roi_right               crop right column (0-based)
[30]     uint8    save_rf                 1=save raw RF data
[31]     uint8    save_rf_time_tag        1=save RF hardware timestamps
[32]     uint8    save_bf                 1=save beamformed IQ data
[33]     uint8    save_pdi                1=save power Doppler data
[34]     uint8    tgc_update_flag         1=apply new TGC control points
[35]              pad
[36:52]  int16×8  tgc_point_1..8          Verasonics TGC control points (0-1023 each)
[52]     uint8    stack_start_flag        one-shot: 1=start z-stack
[53]     uint8    stack_abort_flag        one-shot: 1=abort active z-stack
[54]     uint8    stack_use_dummy_motor   0=real Zaber motor, 1=dummy backend
[55]              pad
[56:60]  int32    stack_start_um          elevation start position (μm)
[60:64]  int32    stack_step_um           step size between slices (μm)
[64:68]  int32    stack_n_slices          number of slices
[68:72]  int32    stack_npdi_per_slice    PDI frames to average per slice
[72:76]  int32    stack_settle_ms         motor settle time (ms)
[76:80]  int32    stack_jog_um            one-shot relative jog (μm)
[80:84]  uint32   freeze_req_id           request counter for freeze/unfreeze
[84:88]  uint32   save_req_id             request counter for save toggle
[88:92]  uint32   svd_req_id              request counter for SVD update
[92:96]  uint32   voltage_req_id          request counter for voltage update
[96:100] uint32   tx_aperture_req_id      request counter for TX aperture update
[100:104] uint32  rx_aperture_req_id      request counter for RX aperture update
[104:108] uint32  tgc_req_id              request counter for TGC update
[108:112] uint32  crop_req_id             request counter for crop update
[112:116] uint32  stack_req_id            request counter for z-stack command
```

### `cf_rf` / `cf_rf_*` (~1 MB)

Written by `publishProcessedFrame` when an RF snapshot is requested (rising edge of `show_rf`). Format: a 16-byte header followed by raw RF int16 data.

```
[0:8]    uint64   rf_counter          incremented each time a snapshot is written
[8:12]   int32    nsamples            number of samples (rows)
[12:16]  int32    ncols               number of channels (columns)
[16:]    int16    data                row-major RF data, shape [nsamples, ncols]
```

Maximum dimensions are 1024 samples × 512 channels; the actual dimensions vary with probe and imaging depth.

### `cf_stack` / `cf_stack_*` (16 bytes)

Written by `processRuntimeControl` whenever the z-stack state changes.

```
[0]     uint8    stack_active        1 while a z-stack acquisition is running
[1]     uint8    stack_error         1 if the z-stack encountered an error
[2:4]   int16    status_code         state machine state (see below)
[4:8]   int32    current_slice       current slice index (0-based; -1=not started)
[8:12]  int32    total_slices        total slices for this run
[12:16] int32    target_position_um  current motor target position (μm)
```

Z-stack status codes:

| Code | Constant | Meaning |
|------|----------|---------|
| 0 | `STACK_STATUS_IDLE` | No active stack |
| 1 | `STACK_STATUS_INITIALIZING` | Starting up, computing slice positions |
| 2 | `STACK_STATUS_MOVING_TO_SLICE` | Motor moving to target position |
| 3 | `STACK_STATUS_SETTLING` | Waiting for motor settle delay |
| 4 | `STACK_STATUS_ACCUMULATING` | Collecting PDI frames for current slice |
| 5 | `STACK_STATUS_FINALIZING_SLICE` | Averaging accumulated frames |
| 6 | `STACK_STATUS_COMPLETING` | Stack done, exporting NIfTI files |
| 7 | `STACK_STATUS_ABORTING` | Aborting on user request or vsExit |
| 8 | `STACK_STATUS_ERROR` | Motor or processing error |

### `cf_ack` / `cf_ack_*` (36 bytes)

Nine uint32 acknowledgement counters written by `processRuntimeControl` when a command is applied. Python matches an ack ID against the request ID it sent to confirm the command was processed.

```
[0:4]    uint32   freeze_ack_id
[4:8]    uint32   save_ack_id
[8:12]   uint32   svd_ack_id
[12:16]  uint32   voltage_ack_id
[16:20]  uint32   tx_aperture_ack_id
[20:24]  uint32   rx_aperture_ack_id
[24:28]  uint32   tgc_ack_id
[28:32]  uint32   crop_ack_id
[32:36]  uint32   stack_ack_id
```

## Request/Ack Protocol

Shared memory offers no atomic read-modify-write primitives. To avoid the UI re-applying a stale command on every frame, each command type carries a monotonically-incrementing uint32 request ID alongside its payload fields.

```
Python side (napari widget; logical names shown)
  1. Increment the per-command request counter.
  2. Write the new counter value and payload into cf_cmd.

MATLAB side (processRuntimeControl, every frame)
  3. Read cf_cmd.
  4. Compare the incoming req_id against the last-seen req_id (persistent).
  5. If the ID has changed, apply the command.
  6. Write the req_id into the corresponding cf_ack field.
  7. Update the persistent last-seen req_id.

Python side (optional wait for confirmation)
  8. Poll cf_ack until ack_id == req_id.
```

A request ID of zero is treated as "no change" by MATLAB (persistent variables initialise to zero, matching the initial cf_cmd state). The first real command from Python uses ID 1 or higher.

## Lifecycle

Python generates a fresh set of shared-memory names for each acquisition, calls
`shared_memory.create_segments(...)`, and passes those resolved names into the MATLAB
worker config. This creates fresh zero-initialised segments and avoids collisions with
stale names from a previous session.

MATLAB opens segments lazily: `processRuntimeControl` opens `cf_cmd_*`, `cf_stack_*`,
and `cf_ack_*` on its first call; `publishProcessedFrame` opens `cf_bmode_*`,
`cf_pdi_*`, `cf_meta_*`, and `cf_rf_*` on the first frame with `frameReady=true`.

When the session ends Python sends `vsExit=1` in `cf_cmd_*`, waits for the worker to
exit, then closes and unlinks the segments via `shared_memory.close_segments(...)`.
