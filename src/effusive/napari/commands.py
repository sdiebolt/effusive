"""Acquisition command handlers for the Effusive napari widget.

This module contains signal handlers for live parameter updates (TGC, voltage,
aperture, SVD, save options) that write values into the `cf_cmd` shared-memory
segment. Each handler validates widget state, writes the command, and schedules
any needed flag resets via `schedule_flag_reset`.
"""

from __future__ import annotations

import datetime
import time
from pathlib import Path
from typing import TYPE_CHECKING

from effusive import bids
from effusive.napari import controls

if TYPE_CHECKING:
    from effusive.napari.widget import EffusiveWidget


def handle_pause(widget: "EffusiveWidget", paused: bool) -> None:
    """Handle a pause-toggle request from the pause button.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the pause state and command channel.
    paused : bool
        Whether the acquisition should be paused.

    Returns
    -------
    None
        This helper mutates widget pause state and writes a shared-memory command.
    """
    if not paused:
        widget._stack_panel._stack_preview_hold_display = False
    controls.set_pause_button_state(widget, paused)
    widget.write_shared_memory_command(
        freeze=1 if paused else 0,
        freeze_req_id=widget.next_command_request_id("freeze"),
    )
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    action = "Pause requested" if paused else "Resume requested"
    widget._log_queue.put(f"[{ts}] [viewer] {action}.\n")
    if widget._worker is not None:
        controls.refresh_runtime_status(widget)


def handle_save(widget: "EffusiveWidget", saving: bool) -> None:
    """Handle a save-toggle request from the record button.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the save state and command channel.
    saving : bool
        Whether saving to disk should be enabled.

    Returns
    -------
    None
        This helper mutates widget save state and writes a shared-memory command.
    """
    controls.sync_save_controls(widget)
    controls.refresh_control_locks(widget)
    if saving:
        mp = widget._metadata_panel
        run = mp._run_spinbox.value()
        storage_root = widget._metadata_panel._storage_edit.text().strip()
        try:
            collision = bids.check_bids_run_collision(
                Path(storage_root),
                datatype=bids.FUSI_DATATYPE,
                subject=mp._subject_edit.text().strip(),
                session=mp._session_edit.text().strip(),
                task=mp._task_edit.text().strip(),
                acq=mp._acq_edit.text().strip(),
                run=run,
                proc=mp._proc_edit.text().strip(),
            )
            if collision:
                from napari.utils.notifications import show_error

                show_error(
                    "Path already exists for this entity set. Change the storage metadata."
                )
                btn = widget._data_panel._save_button
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.blockSignals(False)
                controls.sync_save_controls(widget)
                controls.refresh_control_locks(widget)
                return
        except ValueError:
            pass
        bids.write_bids_meta_sidecar(
            task=mp._task_edit.text().strip(),
            acq=mp._acq_edit.text().strip(),
            proc=mp._proc_edit.text().strip(),
            run=run,
            subject=mp._subject_edit.text().strip(),
            session=mp._session_edit.text().strip(),
        )
    widget._pending_save_target = bool(saving)
    widget._pending_save_deadline_s = time.monotonic() + 1.5
    widget.write_shared_memory_command(
        save_to_disk=1 if saving else 0,
        save_req_id=widget.next_command_request_id("save"),
    )
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    widget._log_queue.put(
        f"[{ts}] [viewer] Save to disk {'enabled' if saving else 'disabled'}.\n"
    )


def handle_save_options(widget: "EffusiveWidget") -> None:
    """Handle a change to any save-options checkbox.

    Reads all four save-option checkboxes directly rather than using the emitted
    state, so any single checkbox change refreshes the full set of flags.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the save-option checkboxes and command channel.

    Returns
    -------
    None
        This helper writes updated save-option flags to the shared-memory command.
    """
    dp = widget._data_panel
    save_rf = 1 if dp._save_rf_checkbox.isChecked() else 0
    save_rf_time_tag = 1 if dp._save_rf_time_tag_checkbox.isChecked() else 0
    save_bf = 1 if dp._save_bf_checkbox.isChecked() else 0
    save_pdi = 1 if dp._save_pdi_checkbox.isChecked() else 0
    widget.write_shared_memory_command(
        save_rf=save_rf,
        save_rf_time_tag=save_rf_time_tag,
        save_bf=save_bf,
        save_pdi=save_pdi,
        save_req_id=widget.next_command_request_id("save"),
    )
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    widget._log_queue.put(f"[{ts}] [viewer] Save options updated.\n")


def handle_svd(widget: "EffusiveWidget", value: int) -> None:
    """Handle an SVD threshold change from the SVD slider.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the SVD controls and command channel.
    value : int
        New SVD threshold value in percent.

    Returns
    -------
    None
        This helper updates the SVD spin box and writes a shared-memory command.
    """
    widget._processing_panel._svd_spinbox.blockSignals(True)
    widget._processing_panel._svd_spinbox.setValue(value)
    widget._processing_panel._svd_spinbox.blockSignals(False)
    widget._config.acquisition.svd_threshold_percent = value
    widget.write_shared_memory_command(
        svd_threshold=value,
        svd_req_id=widget.next_command_request_id("svd"),
    )
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    widget._log_queue.put(f"[{ts}] [viewer] SVD threshold → {value}%.\n")


def handle_voltage(widget: "EffusiveWidget", value: int) -> None:
    """Handle a voltage change from the voltage slider.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the voltage controls and command channel.
    value : int
        New voltage value in tenths of volts (slider units; divide by 10 for V).

    Returns
    -------
    None
        This helper updates the voltage spin box and writes a shared-memory command.
    """
    voltage_v = value / 10.0
    widget._processing_panel._voltage_spinbox.blockSignals(True)
    widget._processing_panel._voltage_spinbox.setValue(voltage_v)
    widget._processing_panel._voltage_spinbox.blockSignals(False)
    widget._config.acquisition.voltage_v = voltage_v
    if widget._shared_memory_segments:
        widget.write_shared_memory_command(
            voltage_v=voltage_v,
            voltage_req_id=widget.next_command_request_id("voltage"),
        )
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        widget._log_queue.put(f"[{ts}] [viewer] Voltage → {voltage_v:.1f} V.\n")


def handle_tx_aperture(widget: "EffusiveWidget", value: int) -> None:
    """Handle a TX aperture change from the TX aperture slider.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the TX aperture controls and command channel.
    value : int
        New TX aperture value as a percentage.

    Returns
    -------
    None
        This helper updates the TX aperture spin box and writes a shared-memory command.
    """
    widget._processing_panel._tx_aperture_spinbox.blockSignals(True)
    widget._processing_panel._tx_aperture_spinbox.setValue(value)
    widget._processing_panel._tx_aperture_spinbox.blockSignals(False)
    widget._config.acquisition.tx_aperture_percent = value
    if widget._shared_memory_segments:
        widget.write_shared_memory_command(
            tx_aperture=value,
            tx_aperture_req_id=widget.next_command_request_id("tx_aperture"),
        )
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        widget._log_queue.put(f"[{ts}] [viewer] TX aperture → {value}%.\n")


def handle_rx_aperture(widget: "EffusiveWidget", value: int) -> None:
    """Handle an RX aperture change from the RX aperture slider.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the RX aperture controls and command channel.
    value : int
        New RX aperture value as a percentage.

    Returns
    -------
    None
        This helper updates the RX aperture spin box and writes a shared-memory command.
    """
    widget._processing_panel._rx_aperture_spinbox.blockSignals(True)
    widget._processing_panel._rx_aperture_spinbox.setValue(value)
    widget._processing_panel._rx_aperture_spinbox.blockSignals(False)
    widget._config.acquisition.rx_aperture_percent = value
    if widget._shared_memory_segments:
        widget.write_shared_memory_command(
            rx_aperture=value,
            rx_aperture_req_id=widget.next_command_request_id("rx_aperture"),
        )
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        widget._log_queue.put(f"[{ts}] [viewer] RX aperture → {value}%.\n")


def _current_probe_cfg(widget: "EffusiveWidget"):
    """Return the ProbeConfig for the currently selected probe, or None."""
    probe_name = widget._sequence_panel._probe_combo.currentText()
    return widget._config.probe_defaults.get(probe_name)


def handle_transmit_frequency(widget: "EffusiveWidget", value: int) -> None:
    """Handle a transmit frequency change from the frequency slider.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the frequency controls and command channel.
    value : int
        New frequency value in kHz (slider units; divide by 1000 for MHz).

    Returns
    -------
    None
        This helper updates the frequency spin box and writes a shared-memory command.
    """
    freq = value / 1000.0
    widget._sequence_panel._freq_spinbox.blockSignals(True)
    widget._sequence_panel._freq_spinbox.setValue(freq)
    widget._sequence_panel._freq_spinbox.blockSignals(False)
    probe = _current_probe_cfg(widget)
    if probe is not None:
        probe.transmit_frequency_mhz = freq
    if widget._shared_memory_segments:
        widget.write_shared_memory_command(
            freq_update_flag=1, transmit_frequency_mhz=freq
        )
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        widget._log_queue.put(f"[{ts}] [viewer] Frequency → {freq:.3f} MHz.\n")
        widget.schedule_flag_reset("freq_update_flag", 0)


def handle_frame_rate(widget: "EffusiveWidget", value: int) -> None:
    """Handle a frame rate change from the frame rate slider.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the frame rate controls and command channel.
    value : int
        New frame rate in Hz.

    Returns
    -------
    None
        This helper updates the frame rate spin box and writes a shared-memory command.
    """
    widget._sequence_panel._fps_spinbox.blockSignals(True)
    widget._sequence_panel._fps_spinbox.setValue(value)
    widget._sequence_panel._fps_spinbox.blockSignals(False)
    probe = _current_probe_cfg(widget)
    if probe is not None:
        probe.txrx_frame_rate_hz = value
    if widget._shared_memory_segments:
        widget.write_shared_memory_command(
            frame_rate_update_flag=1, frame_rate_hz=value
        )
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        widget._log_queue.put(f"[{ts}] [viewer] Frame rate → {value} Hz.\n")
        widget.schedule_flag_reset("frame_rate_update_flag", 0)


def handle_pulse_length(widget: "EffusiveWidget", value: int) -> None:
    """Handle a pulse length change from the pulse length slider.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the pulse length controls and command channel.
    value : int
        New pulse length in half cycles.

    Returns
    -------
    None
        This helper updates the pulse length spin box and writes a shared-memory command.
    """
    widget._sequence_panel._pulse_spinbox.blockSignals(True)
    widget._sequence_panel._pulse_spinbox.setValue(value)
    widget._sequence_panel._pulse_spinbox.blockSignals(False)
    widget._config.sequence.transmit_pulse_length = value
    if widget._shared_memory_segments:
        widget.write_shared_memory_command(
            pulse_length_update_flag=1, pulse_length=value
        )
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        widget._log_queue.put(f"[{ts}] [viewer] Pulse length → {value} ½ cycles.\n")
        widget.schedule_flag_reset("pulse_length_update_flag", 0)


def handle_n_transmissions(widget: "EffusiveWidget", value: int) -> None:
    """Handle a transmission count change from the transmissions slider.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the transmissions controls and command channel.
    value : int
        New number of transmissions per ensemble.

    Returns
    -------
    None
        This helper updates the transmissions spin box and writes a shared-memory command.
    """
    widget._sequence_panel._tx_count_spinbox.blockSignals(True)
    widget._sequence_panel._tx_count_spinbox.setValue(value)
    widget._sequence_panel._tx_count_spinbox.blockSignals(False)
    probe = _current_probe_cfg(widget)
    if probe is not None:
        probe.n_transmissions = value
    if widget._shared_memory_segments:
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        widget._log_queue.put(
            f"[{ts}] [viewer] # Transmissions → {value} (applies on next start).\n"
        )


def handle_n_repeats(widget: "EffusiveWidget", value: int) -> None:
    """Handle an ensemble size change from the ensemble slider.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the ensemble controls and command channel.
    value : int
        New number of ensemble repeats.

    Returns
    -------
    None
        This helper updates the ensemble spin box and writes a shared-memory command.
    """
    widget._sequence_panel._ensemble_spinbox.blockSignals(True)
    widget._sequence_panel._ensemble_spinbox.setValue(value)
    widget._sequence_panel._ensemble_spinbox.blockSignals(False)
    probe = _current_probe_cfg(widget)
    if probe is not None:
        probe.n_repeats = value
    if widget._shared_memory_segments:
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        widget._log_queue.put(
            f"[{ts}] [viewer] Ensemble size → {value} (applies on next start).\n"
        )


def handle_opening_angle(widget: "EffusiveWidget", value: int) -> None:
    """Handle an opening angle change from the opening angle slider.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the opening angle controls and command channel.
    value : int
        New planewave opening angle in degrees.

    Returns
    -------
    None
        This helper updates the opening angle spin box and writes a shared-memory command.
    """
    widget._sequence_panel._angle_spinbox.blockSignals(True)
    widget._sequence_panel._angle_spinbox.setValue(value)
    widget._sequence_panel._angle_spinbox.blockSignals(False)
    probe = _current_probe_cfg(widget)
    if probe is not None:
        probe.planewave_opening_angle_deg = value
    if widget._shared_memory_segments:
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        widget._log_queue.put(
            f"[{ts}] [viewer] Opening angle → {value}° (applies on next start).\n"
        )


def handle_imaging_depth(widget: "EffusiveWidget", value: int) -> None:
    """Handle an imaging depth change from the depth slider.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the depth controls and command channel.
    value : int
        New imaging depth in tenths of millimetres (slider units; divide by 10 for mm).

    Returns
    -------
    None
        This helper updates the depth spin box and writes a shared-memory command.
    """
    depth = value / 10.0
    widget._sequence_panel._depth_spinbox.blockSignals(True)
    widget._sequence_panel._depth_spinbox.setValue(depth)
    widget._sequence_panel._depth_spinbox.blockSignals(False)
    widget._config.sequence.imaging_depth_mm = depth
    if widget._shared_memory_segments:
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        widget._log_queue.put(
            f"[{ts}] [viewer] Imaging depth → {depth:.1f} mm (applies on next start).\n"
        )


def set_tgc_points(widget: "EffusiveWidget", values: list[int]) -> None:
    """Set all TGC point sliders and spinboxes without firing their signals.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the TGC controls.
    values : list[int]
        Eight TGC point values in the range 0–1023.

    Returns
    -------
    None
        This helper mutates TGC slider and spin box values in place.
    """
    pp = widget._processing_panel
    pp._updating_tgc_controls = True
    try:
        for slider, spin, value in zip(pp._tgc_sliders, pp._tgc_spinboxes, values):
            slider.blockSignals(True)
            spin.blockSignals(True)
            slider.setValue(value)
            spin.setValue(value)
            slider.blockSignals(False)
            spin.blockSignals(False)
    finally:
        pp._updating_tgc_controls = False


def send_tgc_update(widget: "EffusiveWidget", source: str) -> None:
    """Write all TGC control points into the shared-memory command segment.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the TGC sliders and command channel.
    source : str
        Human-readable source label used in the log message (e.g. `"TGC point 3"`).

    Returns
    -------
    None
        This helper writes TGC values to shared memory and schedules a flag reset.
    """
    tgc_points = widget._processing_panel.get_current_tgc_points()
    widget._config.acquisition.tgc_control_points = list(tgc_points)
    if not widget._shared_memory_segments:
        return
    widget.write_shared_memory_command(
        tgc_point_1=tgc_points[0],
        tgc_point_2=tgc_points[1],
        tgc_point_3=tgc_points[2],
        tgc_point_4=tgc_points[3],
        tgc_point_5=tgc_points[4],
        tgc_point_6=tgc_points[5],
        tgc_point_7=tgc_points[6],
        tgc_point_8=tgc_points[7],
        tgc_req_id=widget.next_command_request_id("tgc"),
    )
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    widget._log_queue.put(
        f"[{ts}] [viewer] {source} → [{', '.join(str(v) for v in tgc_points)}].\n"
    )


def handle_tgc_point(widget: "EffusiveWidget", idx: int, value: int) -> None:
    """Handle a single TGC point change from a point slider.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the TGC controls.
    idx : int
        Zero-based index of the TGC control point that changed.
    value : int
        New TGC control point value in the range 0–1023.

    Returns
    -------
    None
        This helper updates the corresponding spin box and writes a TGC command.
    """
    pp = widget._processing_panel
    if pp._updating_tgc_controls:
        return
    pp._tgc_spinboxes[idx].blockSignals(True)
    pp._tgc_spinboxes[idx].setValue(value)
    pp._tgc_spinboxes[idx].blockSignals(False)
    gain_factor = pp.compute_tgc_gain_factor(pp._tgc_all_gain)
    pp._tgc_base_points[idx] = 0.0 if gain_factor == 0 else value / 1023.0 / gain_factor
    send_tgc_update(widget, f"TGC point {idx + 1}")


def handle_tgc_all_gain(widget: "EffusiveWidget", value: int) -> None:
    """Handle a TGC all-gain change from the all-gain slider.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the TGC controls.
    value : int
        New all-gain slider value scaled by 100 (divide by 100 for float gain).

    Returns
    -------
    None
        This helper recomputes all TGC points from stored base values and writes a command.
    """
    pp = widget._processing_panel
    if pp._updating_tgc_controls:
        return
    gain_value = value / 100.0
    pp._tgc_all_gain = gain_value
    widget._config.acquisition.tgc_all_gain = gain_value
    pp._tgc_all_spinbox.blockSignals(True)
    pp._tgc_all_spinbox.setValue(gain_value)
    pp._tgc_all_spinbox.blockSignals(False)
    gain_factor = pp.compute_tgc_gain_factor(gain_value)
    tgc_points = [
        min(1023, max(0, round(base_value * gain_factor * 1023)))
        for base_value in pp._tgc_base_points
    ]
    set_tgc_points(widget, tgc_points)
    send_tgc_update(widget, "TGC All Gain")
