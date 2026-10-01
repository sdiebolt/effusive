"""Effusive shared-memory protocol.

The napari viewer creates a fresh set of seven shared-memory segments before each
acquisition run and passes the resolved names to the MATLAB worker. Default logical
channel names are exposed as module-level constants (`cf_meta`, `cf_bmode`, `cf_pdi`,
`cf_cmd`, `cf_rf`, `cf_stack`, `cf_ack`), but runtime code can override them with a
session token to avoid collisions between acquisitions.

This module defines the binary layouts, lifecycle helpers, and the Python-side reader
and writer utilities used by the napari process.
"""

from __future__ import annotations

import struct
from multiprocessing import resource_tracker, shared_memory

import numpy as np
import numpy.typing as npt

# ---------------------------------------------------------------------------
# Segment names
# ---------------------------------------------------------------------------

SHARED_MEMORY_META_NAME = "cf_meta"
SHARED_MEMORY_BMODE_NAME = "cf_bmode"
SHARED_MEMORY_PDI_NAME = "cf_pdi"
SHARED_MEMORY_CMD_NAME = "cf_cmd"
SHARED_MEMORY_RF_NAME = "cf_rf"
SHARED_MEMORY_STACK_NAME = "cf_stack"
SHARED_MEMORY_ACK_NAME = "cf_ack"

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

MAX_NZ = 512
MAX_NX = 512

META_FORMAT = "<QiiffffId"
# Byte layout (44 bytes, 9 unpacked values, little-endian):
#   [0:8]    uint64  frame_counter     incremented by MATLAB per published frame
#   [8:12]   int32   nz                image depth in pixels
#   [12:16]  int32   nx                image width in pixels
#   [16:20]  float32 z_start_mm        depth axis start (mm)
#   [20:24]  float32 z_end_mm          depth axis end (mm)
#   [24:28]  float32 x_start_mm        lateral axis start (mm)
#   [28:32]  float32 x_end_mm          lateral axis end (mm)
#   [32:36]  uint32  runtime_flags     bitmask of META_FLAG_* values
#   [36:44]  float64 ensemble_time_s   hardware ensemble timestamp (s)
META_SIZE = struct.calcsize(META_FORMAT)  # 44 bytes

META_FLAG_SAVE_ACTIVE = 1 << 0
"""Runtime flag bit indicating that EchoFrame is actively saving to disk."""

META_FLAG_FREEZE_ACTIVE = 1 << 1
"""Runtime flag bit indicating that acquisition is currently frozen in VSX."""

CMD_FORMAT = "<BBBBhBxfBBhhBBBxhhhhBBBBBxhhhhhhhhBBBxiiiiiiIIIIIIIII"
# Byte layout (80 bytes, 40 unpacked values, little-endian):
#   [0]     uint8   vsExit
#   [1]     uint8   freeze
#   [2]     uint8   save_to_disk
#   [3]     uint8   svd_update_flag
#   [4:6]   int16   svd_threshold
#   [6]     uint8   voltage_update_flag
#   [7]             pad
#   [8:12]  float32 voltage_v
#   [12]    uint8   tx_aperture_update_flag
#   [13]    uint8   rx_aperture_update_flag
#   [14:16] int16   tx_aperture   (0–100 %)
#   [16:18] int16   rx_aperture   (0–100 %)
#   [18]    uint8   show_rf       (rising edge triggers RF snapshot)
#   [19]    uint8   crop_update_flag
#   [20]    uint8   crop_reset_flag
#   [21]            pad
#   [22:24] int16   roi_top       (0-based pixel row)
#   [24:26] int16   roi_bottom
#   [26:28] int16   roi_left      (0-based pixel col)
#   [28:30] int16   roi_right
#   [30]    uint8   save_rf       (0=off, 1=save RF data)
#   [31]    uint8   save_rf_time_tag  (0=off, 1=save RF time tags)
#   [32]    uint8   save_bf       (0=off, 1=save BF data)
#   [33]    uint8   save_pdi      (0=off, 1=save PDI data)
#   [34]    uint8   tgc_update_flag
#   [35]            pad
#   [36:38] int16   tgc_point_1
#   [38:40] int16   tgc_point_2
#   [40:42] int16   tgc_point_3
#   [42:44] int16   tgc_point_4
#   [44:46] int16   tgc_point_5
#   [46:48] int16   tgc_point_6
#   [48:50] int16   tgc_point_7
#   [50:52] int16   tgc_point_8
#   [52]    uint8   stack_start_flag      (one-shot: 1=start z-stack)
#   [53]    uint8   stack_abort_flag      (one-shot: 1=abort z-stack)
#   [54]    uint8   stack_use_dummy_motor (0=real, 1=dummy)
#   [55]            pad
#   [56:60] int32   stack_start_um        (start elevation, micrometers)
#   [60:64] int32   stack_step_um         (step size, micrometers)
#   [64:68] int32   stack_n_slices
#   [68:72] int32   stack_npdi_per_slice
#   [72:76] int32   stack_settle_ms
#   [76:80] int32   stack_jog_um          (one-shot relative jog command)
#   [80:84] uint32  freeze_req_id
#   [84:88] uint32  save_req_id
#   [88:92] uint32  svd_req_id
#   [92:96] uint32  voltage_req_id
#   [96:100] uint32 tx_aperture_req_id
#   [100:104] uint32 rx_aperture_req_id
#   [104:108] uint32 tgc_req_id
#   [108:112] uint32 crop_req_id
#   [112:116] uint32 stack_req_id
CMD_SIZE = struct.calcsize(CMD_FORMAT)  # 116 bytes

CMD_FIELDS = (
    "vsExit",
    "freeze",
    "save_to_disk",
    "svd_update_flag",
    "svd_threshold",
    "voltage_update_flag",
    "voltage_v",
    "tx_aperture_update_flag",
    "rx_aperture_update_flag",
    "tx_aperture",
    "rx_aperture",
    "show_rf",
    "crop_update_flag",
    "crop_reset_flag",
    "roi_top",
    "roi_bottom",
    "roi_left",
    "roi_right",
    "save_rf",
    "save_rf_time_tag",
    "save_bf",
    "save_pdi",
    "tgc_update_flag",
    "tgc_point_1",
    "tgc_point_2",
    "tgc_point_3",
    "tgc_point_4",
    "tgc_point_5",
    "tgc_point_6",
    "tgc_point_7",
    "tgc_point_8",
    "stack_start_flag",
    "stack_abort_flag",
    "stack_use_dummy_motor",
    "stack_start_um",
    "stack_step_um",
    "stack_n_slices",
    "stack_npdi_per_slice",
    "stack_settle_ms",
    "stack_jog_um",
    "freeze_req_id",
    "save_req_id",
    "svd_req_id",
    "voltage_req_id",
    "tx_aperture_req_id",
    "rx_aperture_req_id",
    "tgc_req_id",
    "crop_req_id",
    "stack_req_id",
)
"""Command channel fields in `CMD_FORMAT` unpack order."""

CMD_FIELD_INDEX = {name: idx for idx, name in enumerate(CMD_FIELDS)}
"""Map cf_cmd field names to their unpacked tuple indices."""

STACK_FORMAT = "<BBhiii"
# Byte layout (16 bytes, 6 unpacked values, little-endian):
#   [0]     uint8   stack_active        (1 while z-stack is running)
#   [1]     uint8   stack_error         (1 if an error occurred)
#   [2:4]   int16   status_code         (state machine state, see STACK_STATUS_*)
#   [4:8]   int32   current_slice       (0-based; -1 = not yet started)
#   [8:12]  int32   total_slices
#   [12:16] int32   target_position_um  (current motor target, micrometers)
STACK_SIZE = struct.calcsize(STACK_FORMAT)  # 16 bytes

ACK_FORMAT = "<IIIIIIIII"
ACK_SIZE = struct.calcsize(ACK_FORMAT)
ACK_FIELDS = (
    "freeze_ack_id",
    "save_ack_id",
    "svd_ack_id",
    "voltage_ack_id",
    "tx_aperture_ack_id",
    "rx_aperture_ack_id",
    "tgc_ack_id",
    "crop_ack_id",
    "stack_ack_id",
)
ACK_FIELD_INDEX = {name: idx for idx, name in enumerate(ACK_FIELDS)}

STACK_STATUS_IDLE = 0
STACK_STATUS_INITIALIZING = 1
STACK_STATUS_MOVING_TO_SLICE = 2
STACK_STATUS_SETTLING = 3
STACK_STATUS_ACCUMULATING = 4
STACK_STATUS_FINALIZING_SLICE = 5
STACK_STATUS_COMPLETING = 6
STACK_STATUS_ABORTING = 7
STACK_STATUS_ERROR = 8

IMAGE_SIZE = MAX_NZ * MAX_NX * np.dtype(np.float32).itemsize  # 1 MB

# RF snapshot segment.
MAX_RF_SAMPLES = 1024
MAX_RF_CHANNELS = 512
RF_HEADER_FORMAT = "<Qii"  # rf_counter (uint64), nsamples (int32), ncols (int32)
RF_HEADER_SIZE = struct.calcsize(RF_HEADER_FORMAT)  # 16 bytes
RF_DATA_SIZE = MAX_RF_SAMPLES * MAX_RF_CHANNELS * np.dtype(np.int16).itemsize
RF_SEGMENT_SIZE = RF_HEADER_SIZE + RF_DATA_SIZE  # ~1 MB

BMODE_CONTRAST_LIMITS = (-60.0, 0.0)
"""B-mode layer contrast limits (dB, relative to the current frame's peak)."""

PDI_CONTRAST_LIMITS = (-30.0, 0.0)
"""Power Doppler layer contrast limits (dB, relative to the current frame's peak)."""

_FLOAT32_TINY = float(np.finfo(np.float32).tiny)
"""Smallest positive normal float32, used to floor peak-relative dB ratios against a
literal zero frame without perturbing any real (however faint) nonzero signal."""

DEFAULT_SEGMENT_NAMES = {
    "meta": SHARED_MEMORY_META_NAME,
    "bmode": SHARED_MEMORY_BMODE_NAME,
    "pdi": SHARED_MEMORY_PDI_NAME,
    "cmd": SHARED_MEMORY_CMD_NAME,
    "rf": SHARED_MEMORY_RF_NAME,
    "stack": SHARED_MEMORY_STACK_NAME,
    "ack": SHARED_MEMORY_ACK_NAME,
}
"""Default shared-memory segment names keyed by logical channel."""


# ---------------------------------------------------------------------------
# Segment lifecycle helpers
# ---------------------------------------------------------------------------


def resolve_segment_names(names: dict[str, str] | None = None) -> dict[str, str]:
    """Return the effective shared-memory names for one acquisition session.

    Parameters
    ----------
    names : dict[str, str], optional
        Optional per-channel name overrides keyed like `"meta"` or `"cmd"`.

    Returns
    -------
    dict[str, str]
        Complete logical-channel to shared-memory-name mapping.
    """
    resolved = dict(DEFAULT_SEGMENT_NAMES)
    if names:
        resolved.update({key: value for key, value in names.items() if value})
    return resolved


def _unlink_if_exists(name: str) -> None:
    """Unlink a shared memory segment if it exists.

    Parameters
    ----------
    name : str
        Name of the shared memory segment to unlink.
    """
    try:
        old = shared_memory.SharedMemory(name=name, create=False)
        old.close()
        old.unlink()
    except FileNotFoundError:
        pass


def _unregister_from_resource_tracker(shm: shared_memory.SharedMemory) -> None:
    """Remove a shared memory handle from Python's automatic cleanup tracker.

    We manage the shared-memory lifecycle explicitly in Effusive, so leaving
    these handles registered causes noisy shutdown warnings when the segments
    were already closed or unlinked by our own cleanup path.
    """
    try:
        tracked_name = getattr(shm, "_name", shm.name)
        resource_tracker.unregister(tracked_name, "shared_memory")
    except Exception:
        pass


def create_segments(
    names: dict[str, str] | None = None,
) -> tuple[shared_memory.SharedMemory, ...]:
    """Create all shared-memory segments, replacing any stale ones.

    Parameters
    ----------
    names : dict[str, str], optional
        Optional per-channel name overrides keyed like `"meta"` or `"cmd"`.

    Returns
    -------
    tuple[shared_memory.SharedMemory, ...]
        A tuple containing (shm_meta, shm_bmode, shm_pdi, shm_cmd, shm_rf, shm_stack, shm_ack).
    """
    resolved = resolve_segment_names(names)
    for name, size in (
        (resolved["meta"], META_SIZE),
        (resolved["bmode"], IMAGE_SIZE),
        (resolved["pdi"], IMAGE_SIZE),
        (resolved["cmd"], CMD_SIZE),
        (resolved["rf"], RF_SEGMENT_SIZE),
        (resolved["stack"], STACK_SIZE),
        (resolved["ack"], ACK_SIZE),
    ):
        _unlink_if_exists(name)

    shm_meta = shared_memory.SharedMemory(
        name=resolved["meta"], create=True, size=META_SIZE
    )
    shm_bmode = shared_memory.SharedMemory(
        name=resolved["bmode"], create=True, size=IMAGE_SIZE
    )
    shm_pdi = shared_memory.SharedMemory(
        name=resolved["pdi"], create=True, size=IMAGE_SIZE
    )
    shm_cmd = shared_memory.SharedMemory(
        name=resolved["cmd"], create=True, size=CMD_SIZE
    )
    shm_rf = shared_memory.SharedMemory(
        name=resolved["rf"], create=True, size=RF_SEGMENT_SIZE
    )
    shm_stack = shared_memory.SharedMemory(
        name=resolved["stack"], create=True, size=STACK_SIZE
    )
    shm_ack = shared_memory.SharedMemory(
        name=resolved["ack"], create=True, size=ACK_SIZE
    )

    # Zero-initialise everything.
    for shm in (shm_meta, shm_bmode, shm_pdi, shm_cmd, shm_rf, shm_stack, shm_ack):
        buf = np.ndarray(shm.size, dtype=np.uint8, buffer=shm.buf)
        buf[:] = 0
        _unregister_from_resource_tracker(shm)

    return shm_meta, shm_bmode, shm_pdi, shm_cmd, shm_rf, shm_stack, shm_ack


def close_segments(*shms: shared_memory.SharedMemory, unlink: bool = True) -> None:
    """Close and optionally unlink shared memory segments.

    Parameters
    ----------
    *shms : shared_memory.SharedMemory
        Variable number of shared memory segments to close.
    unlink : bool, default: True
        Whether to unlink (remove) the segments after closing.
    """
    for shm in shms:
        try:
            shm.close()
            if unlink:
                shm.unlink()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Reader (used by the napari viewer process)
# ---------------------------------------------------------------------------


class ShmReader:
    """Open existing shared memory segments for reading (napari side).

    Parameters
    ----------
    names : dict[str, str], optional
        Optional per-channel name overrides keyed like `"meta"` or `"cmd"`.
    """

    def __init__(self, names: dict[str, str] | None = None) -> None:
        """Attach to an existing shared-memory channel set.

        Parameters
        ----------
        names : dict[str, str], optional
            Optional per-channel name overrides keyed like `"meta"` or `"cmd"`.

        Returns
        -------
        None
            Initializes shared-memory handles in place.
        """
        resolved = resolve_segment_names(names)
        self._meta = shared_memory.SharedMemory(name=resolved["meta"], create=False)
        self._bmode = shared_memory.SharedMemory(name=resolved["bmode"], create=False)
        self._pdi = shared_memory.SharedMemory(name=resolved["pdi"], create=False)
        self._cmd = shared_memory.SharedMemory(name=resolved["cmd"], create=False)
        self._rf = shared_memory.SharedMemory(name=resolved["rf"], create=False)
        self._stack = shared_memory.SharedMemory(name=resolved["stack"], create=False)
        self._ack = shared_memory.SharedMemory(name=resolved["ack"], create=False)
        for shm in (
            self._meta,
            self._bmode,
            self._pdi,
            self._cmd,
            self._rf,
            self._stack,
            self._ack,
        ):
            _unregister_from_resource_tracker(shm)

    # -- Meta ---------------------------------------------------------------

    def read_meta(self) -> tuple[int, int, int, float, float, float, float, int, float]:
        """Read metadata from shared memory.

        Returns
        -------
        tuple[int, int, int, float, float, float, float, int, float]
            A tuple containing (frame_counter, nz, nx, z_start_mm, z_end_mm,
            x_start_mm, x_end_mm, runtime_flags, ensemble_time_s).
        """
        buf = self._meta.buf
        assert buf is not None
        return struct.unpack_from(META_FORMAT, buf, 0)

    # -- Image data ---------------------------------------------------------

    def read_bmode(self, nz: int, nx: int) -> npt.NDArray:
        """Read raw B-mode amplitude from shared memory and log-compress it to dB.

        MATLAB sends the raw (un-normalized) B-mode amplitude; this converts it to
        dB relative to the current frame's own peak (`20 * log10(raw / raw.max())`),
        matching the fixed `BMODE_CONTRAST_LIMITS` colorbar.

        Parameters
        ----------
        nz : int
            Number of rows (z-dimension).
        nx : int
            Number of columns (x-dimension).

        Returns
        -------
        numpy.ndarray
            A (nz, nx) float32 array in dB, clipped to `BMODE_CONTRAST_LIMITS`.
        """
        view = np.ndarray((nz, nx), dtype=np.float32, buffer=self._bmode.buf)
        raw = view.copy()
        peak = max(float(raw.max()), _FLOAT32_TINY)
        bmode_db = 20.0 * np.log10(np.maximum(raw, _FLOAT32_TINY) / peak)
        np.clip(bmode_db, *BMODE_CONTRAST_LIMITS, out=bmode_db)
        return bmode_db

    def read_pdi(self, nz: int, nx: int) -> npt.NDArray:
        """Read raw power Doppler power from shared memory and log-compress it to dB.

        MATLAB sends the raw (un-normalized) PDI power; this converts it to dB
        relative to the current frame's own peak (`10 * log10(raw / raw.max())`),
        matching the fixed `PDI_CONTRAST_LIMITS` colorbar.

        Parameters
        ----------
        nz : int
            Number of rows (z-dimension).
        nx : int
            Number of columns (x-dimension).

        Returns
        -------
        numpy.ndarray
            A (nz, nx) float32 array in dB, clipped to `PDI_CONTRAST_LIMITS`.
        """
        view = np.ndarray((nz, nx), dtype=np.float32, buffer=self._pdi.buf)
        raw = view.copy()
        peak = max(float(raw.max()), _FLOAT32_TINY)
        pdi_db = 10.0 * np.log10(np.maximum(raw, _FLOAT32_TINY) / peak)
        np.clip(pdi_db, *PDI_CONTRAST_LIMITS, out=pdi_db)
        return pdi_db

    def read_rf_header(self) -> tuple[int, int, int]:
        """Read the RF segment header from shared memory.

        Returns
        -------
        tuple[int, int, int]
            A tuple containing (rf_counter, nsamples, ncols).
        """
        buf = self._rf.buf
        assert buf is not None
        return struct.unpack_from(RF_HEADER_FORMAT, buf, 0)

    def read_rf(self, nsamples: int, ncols: int) -> npt.NDArray:
        """Copy RF snapshot from shared memory as an int16 array.

        Parameters
        ----------
        nsamples : int
            Number of samples (rows).
        ncols : int
            Number of channels/columns.

        Returns
        -------
        numpy.ndarray
            A (nsamples, ncols) int16 array.
        """
        view = np.ndarray(
            (nsamples, ncols),
            dtype=np.int16,
            buffer=self._rf.buf,
            offset=RF_HEADER_SIZE,
        )
        return view.copy()

    # -- Z-stack status --------------------------------------------------------

    def read_stack_status(self) -> tuple[int, int, int, int, int, int]:
        """Read z-stack status from shared memory.

        Returns
        -------
        tuple[int, int, int, int, int, int]
            A tuple containing (stack_active, stack_error, status_code,
            current_slice, total_slices, target_position_um).
        """
        buf = self._stack.buf
        assert buf is not None
        return struct.unpack_from(STACK_FORMAT, buf, 0)

    def read_ack(self) -> tuple[int, int, int, int, int, int, int, int, int]:
        """Read command acknowledgements from shared memory.

        Returns
        -------
        tuple[int, int, int, int, int, int, int, int, int]
            A tuple containing the acknowledgement counters in `ACK_FIELDS` order.
        """
        buf = self._ack.buf
        assert buf is not None
        return struct.unpack_from(ACK_FORMAT, buf, 0)

    def read_cmd(self) -> tuple:
        """Read the current `cf_cmd` command channel contents from shared memory.

        This reflects the last values napari wrote (or MATLAB's own defaults if
        napari has not written yet), in `CMD_FIELDS` order. Intended for
        diagnostics: comparing this against what the GUI intended to send.

        Returns
        -------
        tuple
            A tuple containing the command channel values in `CMD_FIELDS` order.
        """
        buf = self._cmd.buf
        assert buf is not None
        return struct.unpack_from(CMD_FORMAT, buf, 0)

    # -- Lifecycle ----------------------------------------------------------

    def close(self) -> None:
        """Close all shared memory segment handles.

        Shared-memory handles are unregistered from Python's automatic cleanup
        tracker as soon as they are opened, so shutdown is entirely managed by
        Effusive's explicit close/unlink paths.
        """
        for shm in (
            self._meta,
            self._bmode,
            self._pdi,
            self._cmd,
            self._rf,
            self._stack,
            self._ack,
        ):
            try:
                shm.close()
            except Exception:
                pass
