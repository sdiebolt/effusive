"""UI state management helpers for the CortexFrame napari widget.

This module owns all control-state transitions: button text, enabled states,
lock hints, and the save/pause/stack control synchronisation that must stay
consistent across runtime transitions.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from qtpy.QtWidgets import QLabel, QWidget

from cortexframe import bids, shared_memory
from cortexframe.napari import crop as crop_helpers
from cortexframe.napari import stack as stack_helpers
from cortexframe.napari.theme import ACCENT_DARK, ACCENT_LIGHT, make_lucide_icon

if TYPE_CHECKING:
    from cortexframe.napari.widget import CortexFrameWidget


def _repolish(widget: QWidget) -> None:
    """Refresh a Qt widget's stylesheet state if a style object exists.

    Parameters
    ----------
    widget : QWidget
        Widget whose style should be re-applied.
    """
    style = widget.style()
    if style is None:
        return
    style.unpolish(widget)
    style.polish(widget)


def bids_startup_ready(widget: "CortexFrameWidget") -> tuple[bool, str]:
    """Return whether BIDS mode has enough session metadata to start CortexFrame.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance that owns the BIDS mode and system identity fields.

    Returns
    -------
    tuple of bool and str
        Pair `(ready, reason)` where `reason` is suitable for a tooltip.
    """
    try:
        bids.validate_bids_label(
            widget._metadata_panel._subject_edit.text(), "Subject", required=True
        )
        bids.validate_bids_label(
            widget._metadata_panel._session_edit.text(), "Session", required=True
        )
    except ValueError as error:
        return False, str(error)
    return True, "Start or stop CortexFrame."


def bids_record_ready(widget: "CortexFrameWidget") -> tuple[bool, str]:
    """Return whether BIDS mode has enough metadata to start `fusi` recording.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance that owns the required system and recording fields.

    Returns
    -------
    tuple of bool and str
        Pair `(ready, reason)` where `reason` is suitable for a tooltip.
    """
    try:
        bids.validate_bids_entities(
            datatype=bids.FUSI_DATATYPE,
            subject=widget._metadata_panel._subject_edit.text(),
            session=widget._metadata_panel._session_edit.text(),
            task=widget._metadata_panel._task_edit.text(),
            acq=widget._metadata_panel._acq_edit.text(),
            proc=widget._metadata_panel._proc_edit.text(),
        )
        collision = bids.check_bids_run_collision(
            Path(widget._metadata_panel._storage_edit.text().strip()),
            datatype=bids.FUSI_DATATYPE,
            subject=widget._metadata_panel._subject_edit.text().strip(),
            session=widget._metadata_panel._session_edit.text().strip(),
            task=widget._metadata_panel._task_edit.text().strip(),
            acq=widget._metadata_panel._acq_edit.text().strip(),
            run=widget._metadata_panel._run_spinbox.value(),
            proc=widget._metadata_panel._proc_edit.text().strip(),
        )
        if collision:
            return (
                False,
                "Path already exists for this entity set. Change the storage metadata.",
            )
    except ValueError as error:
        return False, str(error)
    return True, "Start or stop saving data to disk."


def set_run_button_state(widget: "CortexFrameWidget", state: str) -> None:
    """Update the run button label, style, and enabled state.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance that owns the run button.
    state : str
        One of `"ready"`, `"running"`, or `"stopping"`.
    """
    states = {
        "ready": ("run_btn_start", True),
        "running": ("run_btn_stop", True),
        "stopping": ("run_btn_busy", False),
    }
    object_name, enabled = states[state]
    widget._run_button_state = state
    widget._run_button.setObjectName(object_name)
    if state == "ready":
        enabled = bids_startup_ready(widget)[0]
    widget._run_button.setEnabled(enabled)
    _repolish(widget._run_button)
    refresh_control_locks(widget)


def set_pause_button_state(widget: "CortexFrameWidget", paused: bool) -> None:
    """Update the pause button text and style without firing its signal.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance that owns the pause button.
    paused : bool
        Whether the acquisition is currently paused.
    """
    btn = widget._pause_button
    btn.blockSignals(True)
    btn.setChecked(paused)
    btn.blockSignals(False)
    is_dark = widget._is_dark()
    accent = ACCENT_DARK if is_dark else ACCENT_LIGHT
    disabled_fg = "#747486" if is_dark else "#8e8e9f"
    if not btn.isEnabled():
        btn.setObjectName("pause_btn_disabled")
        btn.setToolTip("Pause becomes available once CortexFrame is running.")
        btn.setIcon(make_lucide_icon("pause", disabled_fg, size=18))
    elif paused:
        btn.setObjectName("pause_btn_paused")
        btn.setToolTip("Resume the acquisition.")
        btn.setIcon(make_lucide_icon("play", "#ffffff", size=18))
    else:
        btn.setObjectName("pause_btn_idle")
        btn.setToolTip("Pause the acquisition.")
        btn.setIcon(make_lucide_icon("pause", accent, size=18))
    _repolish(btn)


def set_crop_button_state(widget: "CortexFrameWidget", applied: bool) -> None:
    """Update the crop action button text and style.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance that owns the crop action button.
    applied : bool
        Whether a crop ROI is currently applied.
    """
    btn = widget._processing_panel._crop_action_button
    btn.setText("Reset Crop" if applied else "Apply Crop")
    btn.setObjectName("crop_btn_reset" if applied else "crop_btn_apply")
    btn.setToolTip(
        "Reset the active crop and unlock the ROI layer."
        if applied
        else "Apply the current ROI crop and lock the ROI layer."
    )
    _repolish(btn)


def set_save_controls_enabled(widget: "CortexFrameWidget", enabled: bool) -> None:
    """Enable or disable the save-options group box.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance that owns the save group box.
    enabled : bool
        Whether save-options controls should accept interaction.
    """
    widget._data_panel._save_group.setEnabled(enabled)


def set_save_checkbox_state(widget: "CortexFrameWidget", checked: bool) -> None:
    """Set the record checkbox state without emitting its toggled signal.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance that owns the record button.
    checked : bool
        Desired checked state.
    """
    btn = widget._data_panel._save_button
    btn.blockSignals(True)
    btn.setChecked(checked)
    btn.blockSignals(False)


def set_record_button_state(widget: "CortexFrameWidget", recording: bool) -> None:
    """Update the record button text and style.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance that owns the record button.
    recording : bool
        Whether recording is currently active.
    """
    btn = widget._data_panel._save_button
    is_enabled = btn.isEnabled()
    btn.setText("Stop Recording" if recording else "Record")
    if not is_enabled:
        btn.setObjectName("record_btn_disabled")
    else:
        btn.setObjectName("record_btn_recording" if recording else "record_btn_idle")
    _repolish(btn)


def sync_save_controls(widget: "CortexFrameWidget") -> None:
    """Synchronise the save button and group enabled states with runtime flags.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance that owns the save controls.
    """
    runtime_available = widget._run_button_state == "running"
    stack_locked = widget._stack_panel._stack_active
    paused = widget._pause_button.isChecked()
    manual_save_requested = widget._data_panel._save_button.isChecked()
    record_ready, record_reason = bids_record_ready(widget)
    set_save_controls_enabled(
        widget,
        runtime_available
        and not manual_save_requested
        and not stack_locked
        and record_ready,
    )
    widget._data_panel._save_button.setEnabled(
        runtime_available
        and not stack_locked
        and not (manual_save_requested and paused)
        and (manual_save_requested or record_ready)
    )
    if not runtime_available:
        widget._data_panel._save_button.setToolTip(
            "Start CortexFrame with the play button before recording to disk."
        )
    elif stack_locked:
        widget._data_panel._save_button.setToolTip(
            "Locked during active z-stack acquisition."
        )
    elif manual_save_requested and paused:
        widget._data_panel._save_button.setToolTip(
            "Resume acquisition before stopping recording."
        )
    elif manual_save_requested:
        widget._data_panel._save_button.setToolTip("Stop saving data to disk.")
    else:
        widget._data_panel._save_button.setToolTip(record_reason)
    set_record_button_state(widget, manual_save_requested)


def set_lock_hint_state(label: QLabel, text: str, locked: bool) -> None:
    """Update a lock-hint label's text, visibility, and locked property.

    Parameters
    ----------
    label : QLabel
        Lock-hint label to update.
    text : str
        Hint text to set on the label.
    locked : bool
        Whether the hint should be shown (controls section is locked).
    """
    label.setText(text)
    label.setProperty("locked", locked)
    label.setVisible(locked)
    style = label.style()
    if style is not None:
        style.unpolish(label)
        style.polish(label)


def set_control_labels_locked(labels: list[QLabel], locked: bool) -> None:
    """Apply the `control_locked` style property to a list of labels.

    Parameters
    ----------
    labels : list[QLabel]
        Labels whose `control_locked` property should be updated.
    locked : bool
        Value to assign to the `control_locked` property.
    """
    for label in labels:
        label.setProperty("control_locked", locked)
        style = label.style()
        if style is not None:
            style.unpolish(label)
            style.polish(label)


def set_config_controls_locked(widget: "CortexFrameWidget", locked: bool) -> None:
    """Lock or unlock startup-only config controls on the sequence panel.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance that owns the sequence panel.
    locked : bool
        Whether config controls should be locked (disabled).
    """
    if hasattr(widget, "_sequence_panel"):
        widget._sequence_panel.lock_for_run(locked)


def set_runtime_controls_enabled(widget: "CortexFrameWidget", enabled: bool) -> None:
    """Enable or disable runtime-only controls (pause button and stack).

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance that owns the runtime controls.
    enabled : bool
        Whether runtime controls should accept interaction.
    """
    if not enabled:
        set_pause_button_state(widget, False)
    widget._pause_button.setVisible(enabled)
    widget._pause_button.setEnabled(enabled)
    set_pause_button_state(widget, widget._pause_button.isChecked())
    stack_helpers.refresh_stack_controls(widget)


def refresh_runtime_status(widget: "CortexFrameWidget") -> None:
    """Recompute and display the header status string from current runtime state.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance that owns the status label and runtime state flags.
    """
    if widget._run_button_state != "running":
        return
    if widget._last_frame < 1 and not widget._save_active:
        widget._set_viewer_status_overlay("cf_status_starting")
        return
    sp = widget._stack_panel
    if sp._stack_active:
        stack_status_overlays = {
            shared_memory.STACK_STATUS_INITIALIZING: "cf_status_stack_initializing",
            shared_memory.STACK_STATUS_MOVING_TO_SLICE: "cf_status_stack_moving",
            shared_memory.STACK_STATUS_SETTLING: "cf_status_stack_settling",
            shared_memory.STACK_STATUS_ACCUMULATING: "cf_status_stack_accumulating",
            shared_memory.STACK_STATUS_FINALIZING_SLICE: "cf_status_stack_finalizing",
            shared_memory.STACK_STATUS_COMPLETING: "cf_status_stack_completing",
            shared_memory.STACK_STATUS_ABORTING: "cf_status_stack_aborting",
            shared_memory.STACK_STATUS_ERROR: "cf_status_error",
        }
        widget._set_viewer_status_overlay(
            stack_status_overlays.get(sp._stack_status_code, "cf_status_zstack")
        )
        return
    if sp._stack_error:
        widget._set_viewer_status_overlay("cf_status_error")
        return
    pause_btn = widget._pause_button
    if pause_btn.isChecked():
        if sp._stack_preview_hold_display:
            widget._set_viewer_status_overlay("cf_status_zstack_preview")
        else:
            widget._set_viewer_status_overlay("cf_status_paused")
    elif widget._save_active:
        widget._set_viewer_status_overlay("cf_status_recording")
    else:
        widget._set_viewer_status_overlay("cf_status_running")


def refresh_control_locks(widget: "CortexFrameWidget") -> None:
    """Recompute all control enabled and locked states from current runtime flags.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance that owns all runtime controls.
    """
    # Guard: called during panel construction before all panels exist.
    if not hasattr(widget, "_sequence_panel"):
        return

    sync_save_controls(widget)

    startup_enabled = widget._run_button_state == "ready"
    record_locked = widget._save_active or (
        widget._run_button_state == "running"
        and widget._data_panel._save_button.isChecked()
    )
    record_locked_controls_enabled = (
        widget._run_button_state != "stopping"
        and not record_locked
        and not widget._stack_panel._stack_active
    )

    widget._system_panel.lock_for_run(not startup_enabled)
    widget._system_panel.set_debug_button_enabled(widget._run_button_state == "running")
    widget._metadata_panel.lock_session_fields(not startup_enabled)
    widget._sequence_panel.lock_for_run(not startup_enabled)
    widget._processing_panel.lock_for_recording(not record_locked_controls_enabled)
    widget._metadata_panel.lock_recording_fields(
        record_locked or widget._stack_panel._stack_active
    )

    run_ready, run_reason = bids_startup_ready(widget)
    run_btn = widget._run_button
    is_dark = widget._is_dark()
    disabled_fg = "#747486" if is_dark else "#8e8e9f"
    if widget._run_button_state == "ready":
        widget._system_panel.set_metadata_gate_locked(not run_ready)
        run_btn.setEnabled(run_ready)
        run_btn.setToolTip(run_reason)
        run_btn.setObjectName("run_btn_start" if run_ready else "run_btn_disabled")
        # Icon must contrast against accent background; use accent_fg.
        icon_color = ("#1c1c27" if is_dark else "#ffffff") if run_ready else disabled_fg
        run_btn.setIcon(make_lucide_icon("play", icon_color, size=18))
    elif widget._run_button_state == "running":
        run_btn.setToolTip("Stop CortexFrame.")
        run_btn.setObjectName("run_btn_stop")
        run_btn.setIcon(make_lucide_icon("square", "#ffffff", size=18))
    else:
        run_btn.setToolTip("Waiting for MATLAB worker to stop.")
        run_btn.setObjectName("run_btn_busy")
        run_btn.setIcon(make_lucide_icon("square", disabled_fg, size=18))
    _repolish(run_btn)

    set_lock_hint_state(
        widget._sequence_panel._sequence_lock_hint,
        "Sequence parameters are locked while CortexFrame is running."
        if not startup_enabled
        else "Sequence parameters apply when CortexFrame starts.",
        not startup_enabled,
    )

    set_lock_hint_state(
        widget._system_panel._system_lock_hint,
        run_reason,
        widget._run_button_state == "ready" and not run_ready,
    )

    live_locked = not record_locked_controls_enabled
    set_lock_hint_state(
        widget._processing_panel._live_lock_hint,
        "Acquisition parameters are locked while z-stack is active."
        if widget._stack_panel._stack_active
        else "Acquisition parameters are locked while recording."
        if record_locked
        else "Acquisition parameters stay live until recording starts.",
        live_locked,
    )

    set_lock_hint_state(
        widget._data_panel._record_lock_hint,
        "Start CortexFrame with the play button before using recording controls."
        if widget._run_button_state == "ready"
        else "Recording controls are locked while a z-stack is active."
        if widget._stack_panel._stack_active
        else "Recording controls stay available while CortexFrame is running.",
        widget._run_button_state == "ready" or widget._stack_panel._stack_active,
    )

    widget._processing_panel._crop_action_button.setEnabled(
        widget._run_button_state == "running"
        and not record_locked
        and not widget._stack_panel._stack_active
    )

    widget._data_panel._snapshot_rf_button.setEnabled(
        widget._run_button_state == "running" and not widget._stack_panel._stack_active
    )

    pause_btn = widget._pause_button
    pause_running = widget._run_button_state == "running"
    pause_btn.setVisible(pause_running)
    pause_btn.setEnabled(pause_running and not widget._stack_panel._stack_active)
    set_pause_button_state(widget, pause_btn.isChecked())

    stack_helpers.refresh_stack_controls(widget)
    crop_helpers.refresh_crop_interaction_lock(widget)


def apply_runtime_flags(widget: "CortexFrameWidget", runtime_flags: int) -> None:
    """Decode the runtime-flags bitmask and update save and UDP control state.

    Parameters
    ----------
    widget : CortexFrameWidget
        Widget instance that owns the runtime save and freeze state.
    runtime_flags : int
        Bitmask read from the `cf_meta` shared-memory segment.
    """
    save_active_raw = bool(runtime_flags & shared_memory.META_FLAG_SAVE_ACTIVE)
    save_active = save_active_raw
    pending_target = widget._pending_save_target
    if pending_target is not None:
        if save_active_raw == pending_target:
            widget._pending_save_target = None
            widget._pending_save_deadline_s = 0.0
        elif time.monotonic() < widget._pending_save_deadline_s:
            save_active = bool(pending_target)
        else:
            widget._pending_save_target = None
            widget._pending_save_deadline_s = 0.0

    freeze_active = bool(runtime_flags & shared_memory.META_FLAG_FREEZE_ACTIVE)
    save_button_checked = widget._data_panel._save_button.isChecked()
    if (
        save_active == widget._save_active
        and freeze_active == widget._freeze_active
        and save_button_checked == save_active
    ):
        return

    widget._save_active = save_active
    widget._freeze_active = freeze_active
    set_pause_button_state(widget, freeze_active)

    set_save_checkbox_state(widget, save_active)

    sync_save_controls(widget)
    refresh_runtime_status(widget)
    refresh_control_locks(widget)
