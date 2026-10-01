"""Configuration loading and persistence for Effusive.

Provides dataclasses for all tunable parameters and two-file persistence:
`default_config.toml` ships with the package and is never modified; the user's
`~/.config/effusive/current_config.toml` is created on first run and updated
when the widget closes or when a reset-to-defaults button is pressed.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import platformdirs
import tomli_w

if TYPE_CHECKING:
    from effusive.napari.widget import EffusiveWidget

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "default_config.toml"
"""Shipped read-only defaults."""

USER_CONFIG_DIR = Path(platformdirs.user_config_dir("effusive"))
"""Platform-appropriate user config directory (XDG on Linux, AppData on Windows)."""

USER_CONFIG_PATH = USER_CONFIG_DIR / "current_config.toml"
"""User-writable config file; created from defaults on first run."""


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ProbeConfig:
    """Sequence defaults for a single probe model.

    Attributes
    ----------
    transmit_frequency_mhz : float
        Default transmit centre frequency in MHz.
    txrx_frame_rate_hz : int
        Default TX/RX frame rate in Hz.
    n_transmissions : int
        Default number of plane-wave transmissions per ensemble.
    n_repeats : int
        Default ensemble size (number of TX/RX cycles).
    planewave_opening_angle_deg : int
        Default compound plane-wave opening half-angle in degrees.
    """

    transmit_frequency_mhz: float
    txrx_frame_rate_hz: int
    n_transmissions: int
    n_repeats: int
    planewave_opening_angle_deg: int


@dataclass
class SystemConfig:
    """Persistent system-level settings.

    Attributes
    ----------
    default_probe : str
        Probe name selected at startup.
    storage_path : str
        Default directory for saved data.
    matlab_root : str
        Optional MATLAB installation root override.
    vantage_root : str
        Optional Vantage (Verasonics) installation root override.
    echoframe_mex_root : str
        Optional EchoFrame runtime-MEX files directory override.
    beamformer : str
        EchoFrame beamformer selected at startup (`Fourier` or `DAS`).
    simulate_mode : bool
        Whether simulate mode is on at startup.
    udp_control_enabled : bool
        Whether the napari-side UDP control server starts with acquisition.
    udp_control_port : int
        UDP port used by the napari-side UDP control server.
    """

    default_probe: str
    storage_path: str
    matlab_root: str = ""
    vantage_root: str = ""
    echoframe_mex_root: str = ""
    beamformer: str = "Fourier"
    simulate_mode: bool = True
    udp_control_enabled: bool = True
    udp_control_port: int = 1025


@dataclass
class SequenceConfig:
    """Sequence parameters that are probe-independent.

    Attributes
    ----------
    transmit_pulse_length : int
        Default pulse length in half-cycles.
    imaging_depth_mm : float
        Default desired end depth in millimetres.
    speed_of_sound_m_s : float
        Speed of sound used for sequence timing and reconstruction.
    """

    transmit_pulse_length: int
    imaging_depth_mm: float
    speed_of_sound_m_s: float


@dataclass
class AcquisitionConfig:
    """Live-adjustable acquisition parameter defaults.

    Attributes
    ----------
    voltage_v : float
        Default transmit voltage in volts.
    tx_aperture_percent : int
        Default TX aperture as a percentage of the full array.
    rx_aperture_percent : int
        Default RX aperture as a percentage of the full array.
    svd_threshold_percent : int
        Default SVD clutter-filter threshold as a percentage.
    tgc_control_points : list of int
        Eight TGC control-point values in the range 0–1023.
    """

    voltage_v: float
    tx_aperture_percent: int
    rx_aperture_percent: int
    svd_threshold_percent: int
    tgc_control_points: list[int] = field(default_factory=lambda: [900] * 8)
    tgc_all_gain: float = 0.0


@dataclass
class StackConfig:
    """Z-stack acquisition defaults.

    Attributes
    ----------
    step_mm : float
        Default inter-slice step size in millimetres.
    n_slices : int
        Default number of slices.
    frames_per_slice : int
        Default number of Power Doppler frames to accumulate per slice.
    settle_ms : int
        Default motor settle time in milliseconds.
    motor_min_mm : float
        Minimum allowed absolute motor position in millimetres.
    motor_max_mm : float
        Maximum allowed absolute motor position in millimetres.
    """

    step_mm: float
    n_slices: int
    frames_per_slice: int
    settle_ms: int
    motor_min_mm: float
    motor_max_mm: float


@dataclass
class BidsConfig:
    """Persistent BIDS-like recording metadata defaults.

    Attributes
    ----------
    subject : str
        Default subject label without the `sub-` prefix.
    session : str
        Default session label without the `ses-` prefix.
    task : str
        Default task label without the `task-` prefix.
    acq : str
        Default acquisition label without the `acq-` prefix.
    proc : str
        Default processing label without the `proc-` prefix.
    run : int
        Default run value for recordings.
    """

    subject: str = ""
    session: str = ""
    task: str = ""
    acq: str = ""
    proc: str = ""
    run: int = 1


@dataclass
class CropConfig:
    """Persisted crop ROI shape.

    Attributes
    ----------
    vertices : list of list of float
        Four `[row, col]` vertices of the last applied rectangle in pixel
        coordinates.  An empty list means no crop ROI is saved.
    """

    vertices: list[list[float]] = field(default_factory=list)


@dataclass
class EffusiveConfig:
    """Top-level Effusive configuration.

    Attributes
    ----------
    probe_names : list of str
        Ordered list of available probe model names.
    system : SystemConfig
        System-level settings.
    probe_defaults : dict of str to ProbeConfig
        Per-probe sequence defaults keyed by probe name.
    sequence : SequenceConfig
        Probe-independent sequence defaults.
    acquisition : AcquisitionConfig
        Live-adjustable acquisition defaults.
    stack : StackConfig
        Z-stack acquisition defaults.
    bids : BidsConfig
        BIDS-like storage defaults and entity labels.
    crop : CropConfig
        Last applied crop ROI vertices.
    """

    probe_names: list[str]
    system: SystemConfig
    probe_defaults: dict[str, ProbeConfig]
    sequence: SequenceConfig
    acquisition: AcquisitionConfig
    stack: StackConfig
    bids: BidsConfig = field(default_factory=BidsConfig)
    crop: CropConfig = field(default_factory=CropConfig)

    def get_probe(self, name: str) -> ProbeConfig:
        """Return the config for a probe, falling back to the first available.

        Parameters
        ----------
        name : str
            Probe model name.

        Returns
        -------
        ProbeConfig
            Config for `name` if present, otherwise the first entry.
        """
        return self.probe_defaults.get(name) or next(iter(self.probe_defaults.values()))


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _config_from_dict(data: dict) -> EffusiveConfig:
    """Build a EffusiveConfig from a raw TOML-parsed dictionary.

    Parameters
    ----------
    data : dict
        Dictionary as returned by `tomllib.load`.

    Returns
    -------
    EffusiveConfig
        Fully populated config object.
    """
    with _DEFAULT_CONFIG_PATH.open("rb") as defaults_file:
        default_data = tomllib.load(defaults_file)

    stack_data = dict(default_data.get("stack", {}))
    stack_data.update(data.get("stack", {}))

    bids_data = dict(default_data.get("bids", {}))
    bids_data.update(data.get("bids", {}))

    system_data = dict(default_data.get("system", {}))
    system_data.update(data.get("system", {}))
    system_data.pop("das_cone_angle_auto", None)
    system_data.pop("das_cone_angle_deg", None)
    system_data.pop("das_f_number_auto", None)
    system_data.pop("das_f_number", None)

    sequence_data = dict(default_data.get("sequence", {}))
    sequence_data.update(data.get("sequence", {}))

    acquisition_data = dict(default_data.get("acquisition", {}))
    acquisition_data.update(data.get("acquisition", {}))

    return EffusiveConfig(
        probe_names=data["probe_names"],
        system=SystemConfig(**system_data),
        probe_defaults={
            name: ProbeConfig(**probe_data)
            for name, probe_data in data.get("probe_defaults", {}).items()
        },
        sequence=SequenceConfig(**sequence_data),
        acquisition=AcquisitionConfig(**acquisition_data),
        stack=StackConfig(**stack_data),
        bids=BidsConfig(**bids_data),
        crop=CropConfig(vertices=data.get("crop", {}).get("vertices", [])),
    )


def _config_to_dict(config: EffusiveConfig) -> dict:
    """Serialise a EffusiveConfig to a plain dictionary suitable for TOML.

    Parameters
    ----------
    config : EffusiveConfig
        Config object to serialise.

    Returns
    -------
    dict
        Nested dict ready to pass to `tomli_w.dumps`.
    """
    return {
        "probe_names": config.probe_names,
        "system": {
            "default_probe": config.system.default_probe,
            "storage_path": config.system.storage_path,
            "matlab_root": config.system.matlab_root,
            "vantage_root": config.system.vantage_root,
            "echoframe_mex_root": config.system.echoframe_mex_root,
            "beamformer": config.system.beamformer,
            "simulate_mode": config.system.simulate_mode,
            "udp_control_enabled": config.system.udp_control_enabled,
            "udp_control_port": config.system.udp_control_port,
        },
        "probe_defaults": {
            name: {
                "transmit_frequency_mhz": p.transmit_frequency_mhz,
                "txrx_frame_rate_hz": p.txrx_frame_rate_hz,
                "n_transmissions": p.n_transmissions,
                "n_repeats": p.n_repeats,
                "planewave_opening_angle_deg": p.planewave_opening_angle_deg,
            }
            for name, p in config.probe_defaults.items()
        },
        "sequence": {
            "transmit_pulse_length": config.sequence.transmit_pulse_length,
            "imaging_depth_mm": config.sequence.imaging_depth_mm,
            "speed_of_sound_m_s": config.sequence.speed_of_sound_m_s,
        },
        "acquisition": {
            "voltage_v": config.acquisition.voltage_v,
            "tx_aperture_percent": config.acquisition.tx_aperture_percent,
            "rx_aperture_percent": config.acquisition.rx_aperture_percent,
            "svd_threshold_percent": config.acquisition.svd_threshold_percent,
            "tgc_control_points": config.acquisition.tgc_control_points,
            "tgc_all_gain": config.acquisition.tgc_all_gain,
        },
        "stack": {
            "step_mm": config.stack.step_mm,
            "n_slices": config.stack.n_slices,
            "frames_per_slice": config.stack.frames_per_slice,
            "settle_ms": config.stack.settle_ms,
            "motor_min_mm": config.stack.motor_min_mm,
            "motor_max_mm": config.stack.motor_max_mm,
        },
        "bids": {
            "subject": config.bids.subject,
            "session": config.bids.session,
            "task": config.bids.task,
            "acq": config.bids.acq,
            "proc": config.bids.proc,
            "run": config.bids.run,
        },
        "crop": {
            "vertices": config.crop.vertices,
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def validate_crop_vertices(vertices: list) -> bool:
    """Return True if `vertices` is a valid saved crop rectangle.

    A valid entry is a list of exactly four `[row, col]` pairs where both
    values are finite numbers.  This guards against hand-edited config files
    that contain malformed data.

    Parameters
    ----------
    vertices : list
        Value read from the `crop.vertices` config field.

    Returns
    -------
    bool
        `True` when the vertices can safely be passed to the shapes layer.
    """
    if not isinstance(vertices, list) or len(vertices) != 4:
        return False
    for point in vertices:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            return False
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in point):
            return False
    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_default_config() -> EffusiveConfig:
    """Load the shipped read-only default configuration.

    Returns
    -------
    EffusiveConfig
        Config populated from `default_config.toml`.
    """
    with _DEFAULT_CONFIG_PATH.open("rb") as f:
        return _config_from_dict(tomllib.load(f))


def load_config() -> EffusiveConfig:
    """Load the user config, creating it from defaults if it does not exist.

    Returns
    -------
    EffusiveConfig
        Config populated from `~/.config/effusive/current_config.toml`,
        or from the shipped defaults if no user config exists yet.
    """
    if USER_CONFIG_PATH.exists():
        with USER_CONFIG_PATH.open("rb") as f:
            return _config_from_dict(tomllib.load(f))
    config = load_default_config()
    save_config(config)
    return config


def save_config(config: EffusiveConfig) -> None:
    """Write a config object to the user config file.

    Creates `~/.config/effusive/` if it does not exist.

    Parameters
    ----------
    config : EffusiveConfig
        Config to persist.

    Returns
    -------
    None
        Writes `~/.config/effusive/current_config.toml` in place.
    """
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with USER_CONFIG_PATH.open("wb") as f:
        tomli_w.dump(_config_to_dict(config), f)


def update_config_from_widget(widget: "EffusiveWidget") -> None:
    """Collect current widget values into `widget._config` and save to disk.

    Reads all slider/spinbox values from the widget and writes them into the
    corresponding config fields, then calls `save_config`. Attributes are
    checked with `hasattr` so this is safe to call before all panels are built.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the UI controls and `_config`.

    Returns
    -------
    None
        Mutates `widget._config` in place and writes the user config file.
    """
    cfg = widget._config

    if hasattr(widget, "_system_panel"):
        cfg.system.simulate_mode = widget._system_panel._simulate_checkbox.isChecked()
        cfg.system.udp_control_enabled = (
            widget._system_panel._udp_enable_checkbox.isChecked()
        )
        cfg.system.udp_control_port = widget._system_panel._udp_port_spinbox.value()
    if hasattr(widget, "_reconstruction_panel"):
        rp = widget._reconstruction_panel
        cfg.system.beamformer = str(rp._beamformer_combo.currentData())
    if hasattr(widget, "_sequence_panel"):
        cfg.system.default_probe = widget._sequence_panel._probe_combo.currentText()
    if hasattr(widget, "_system_panel"):
        cfg.system.matlab_root = widget._system_panel._matlab_root_edit.text().strip()
        cfg.system.vantage_root = widget._system_panel._vantage_root_edit.text().strip()
        cfg.system.echoframe_mex_root = (
            widget._system_panel._echoframe_mex_root_edit.text().strip()
        )
    if hasattr(widget, "_metadata_panel"):
        cfg.system.storage_path = widget._metadata_panel._storage_edit.text().strip()

    probe_name = cfg.system.default_probe
    if probe_name not in cfg.probe_defaults:
        cfg.probe_defaults[probe_name] = cfg.get_probe(probe_name)
    probe = cfg.probe_defaults[probe_name]

    if hasattr(widget, "_sequence_panel"):
        sp = widget._sequence_panel
        probe.transmit_frequency_mhz = sp._freq_slider.value() / 1000.0
        probe.txrx_frame_rate_hz = sp._fps_slider.value()
        probe.n_transmissions = sp._tx_count_slider.value()
        probe.n_repeats = sp._ensemble_slider.value()
        probe.planewave_opening_angle_deg = sp._angle_slider.value()
        cfg.sequence.transmit_pulse_length = sp._pulse_slider.value()
        cfg.sequence.imaging_depth_mm = sp._depth_slider.value() / 10.0
    if hasattr(widget, "_reconstruction_panel"):
        cfg.sequence.speed_of_sound_m_s = (
            widget._reconstruction_panel._speed_of_sound_spinbox.value()
        )

    if hasattr(widget, "_processing_panel"):
        pp = widget._processing_panel
        cfg.acquisition.voltage_v = pp._voltage_slider.value() / 10.0
        cfg.acquisition.tx_aperture_percent = pp._tx_aperture_slider.value()
        cfg.acquisition.rx_aperture_percent = pp._rx_aperture_slider.value()
        if len(pp._tgc_sliders) == 8:
            cfg.acquisition.tgc_control_points = [s.value() for s in pp._tgc_sliders]
    if hasattr(widget, "_reconstruction_panel"):
        cfg.acquisition.svd_threshold_percent = (
            widget._reconstruction_panel._svd_slider.value()
        )

    if hasattr(widget, "_stack_panel"):
        stp = widget._stack_panel
        cfg.stack.step_mm = stp._stack_step_mm_spinbox.value()
        cfg.stack.n_slices = stp._stack_n_slices_spinbox.value()
        cfg.stack.frames_per_slice = stp._stack_npdi_per_slice_spinbox.value()
        cfg.stack.settle_ms = stp._stack_settle_ms_spinbox.value()

    if hasattr(widget, "_metadata_panel"):
        mp = widget._metadata_panel
        cfg.bids.subject = mp._subject_edit.text().strip()
        cfg.bids.session = mp._session_edit.text().strip()
        cfg.bids.task = mp._task_edit.text().strip()
        cfg.bids.acq = mp._acq_edit.text().strip()
        cfg.bids.proc = mp._proc_edit.text().strip()
        cfg.bids.run = mp._run_spinbox.value()

    save_config(cfg)
