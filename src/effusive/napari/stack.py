"""Z-stack control, motor helpers, and live preview accumulation for the Effusive napari widget."""

from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import TYPE_CHECKING, cast

import numpy as np
from qtpy.QtWidgets import QMessageBox

from effusive import bids, shared_memory
from effusive.motor_controller import MotorController, create_motor_controller
from effusive.napari import commands, controls

if TYPE_CHECKING:
    from effusive.napari.widget import EffusiveWidget


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STACK_STATUS_TEXT = {
    shared_memory.STACK_STATUS_IDLE: "Idle",
    shared_memory.STACK_STATUS_INITIALIZING: "Initializing",
    shared_memory.STACK_STATUS_MOVING_TO_SLICE: "Moving to slice",
    shared_memory.STACK_STATUS_SETTLING: "Settling",
    shared_memory.STACK_STATUS_ACCUMULATING: "Accumulating",
    shared_memory.STACK_STATUS_FINALIZING_SLICE: "Finalizing slice",
    shared_memory.STACK_STATUS_COMPLETING: "Completing",
    shared_memory.STACK_STATUS_ABORTING: "Aborting",
    shared_memory.STACK_STATUS_ERROR: "Error",
}
"""Viewer labels for z-stack runtime status codes."""

# ---------------------------------------------------------------------------
# Pure utility
# ---------------------------------------------------------------------------


def convert_mm_to_um(value_mm: float) -> int:
    """Convert a millimetre value to whole micrometres.

    Parameters
    ----------
    value_mm : float
        Distance in millimetres.

    Returns
    -------
    int
        Rounded distance in micrometres.
    """
    return int(round(value_mm * 1000.0))


# ---------------------------------------------------------------------------
# Motor controller helpers
# ---------------------------------------------------------------------------


def get_motor_port(widget: "EffusiveWidget") -> str | None:
    """Resolve the stack motor serial port from config or environment.

    Reads from `worker_cfg["stackMotorPort"]` first, then falls back to the
    `EFFUSIVE_STACK_MOTOR_PORT` environment variable. Returns `None` when
    the resulting string is empty after stripping whitespace.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the worker configuration dict.

    Returns
    -------
    str or None
        Serial port string, or `None` if none is configured.
    """
    motor_port = widget._worker_cfg.get("stackMotorPort") or os.environ.get(
        "EFFUSIVE_STACK_MOTOR_PORT", ""
    )
    motor_port = str(motor_port).strip()
    return motor_port or None


def get_motor_limits_mm(widget: "EffusiveWidget") -> tuple[float, float]:
    """Return configured absolute motor limits in millimetres.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the stack configuration.

    Returns
    -------
    tuple of float
        Lower and upper absolute motor limits in millimetres.
    """

    return (
        float(widget._config.stack.motor_min_mm),
        float(widget._config.stack.motor_max_mm),
    )


def close_motor_controller(widget: "EffusiveWidget") -> None:
    """Close and release the manual motor controller if one is open.

    Logs a warning if the controller raises on close but does not propagate
    the exception, so cleanup always completes.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the motor controller reference.

    Returns
    -------
    None
        This helper mutates widget motor controller state in place.
    """
    sp = widget._stack_panel
    controller = sp._stack_motor_controller
    sp._stack_motor_controller = None
    if controller is None:
        return
    try:
        controller.close()
    except Exception as exc:
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        widget._log_queue.put(f"[{ts}] [viewer] Manual motor cleanup warning: {exc}.\n")


def open_motor_controller(widget: "EffusiveWidget") -> MotorController:
    """Open the motor controller, reusing the existing one when the kind matches.

    Reuses the existing controller when its kind (dummy vs real) matches the
    current UI selection. Closes and replaces it otherwise so the new
    selection takes effect immediately.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the motor controller and backend combo.

    Returns
    -------
    MotorController
        Open motor controller matched to the current backend selection.
    """
    sp = widget._stack_panel
    use_dummy = sp._stack_backend_combo.currentText() == "Dummy motor"
    requested_kind = "dummy" if use_dummy else "real"
    controller = sp._stack_motor_controller
    if controller is not None and controller.kind == requested_kind:
        return controller

    if requested_kind == "real":
        sp._stack_motor_homed = False
    else:
        sp._stack_motor_homed = True

    close_motor_controller(widget)
    min_position_mm, max_position_mm = get_motor_limits_mm(widget)
    controller = create_motor_controller(
        use_dummy_motor=use_dummy,
        motor_port=get_motor_port(widget),
        min_position_mm=min_position_mm,
        max_position_mm=max_position_mm,
    )
    sp._stack_motor_controller = controller
    sp._manual_motor_position_um = convert_mm_to_um(controller.current_position_mm)
    return controller


def request_home_stack_motor(widget: "EffusiveWidget") -> None:
    """Prompt for confirmation before homing the stack motor.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the stack panel and motor controller.

    Returns
    -------
    None
        This helper shows a confirmation dialog, then homes.
    """

    reply = QMessageBox.warning(
        widget,
        "Home stack motor?",
        (
            "Homing may move the motor by a large distance.\n\n"
            "Only continue if the motor path is clear and the probe is safe."
        ),
        QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        QMessageBox.StandardButton.Cancel,
    )
    if reply != QMessageBox.StandardButton.Ok:
        return

    home_stack_motor(widget)


def home_stack_motor(widget: "EffusiveWidget") -> None:
    """Home the selected stack motor backend and unlock absolute moves.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the stack panel and motor controller.

    Returns
    -------
    None
        This helper updates homed state and logs the operation.
    """

    sp = widget._stack_panel
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    if widget._run_button_state != "running":
        widget._log_queue.put(
            f"[{ts}] [viewer] Motor home rejected: start Effusive first.\n"
        )
        return
    if sp._stack_active:
        widget._log_queue.put(
            f"[{ts}] [viewer] Motor home rejected: z-stack is active.\n"
        )
        return

    try:
        controller = open_motor_controller(widget)
        controller.home()
    except Exception as exc:
        sp._stack_motor_homed = False
        widget._log_queue.put(f"[{ts}] [viewer] Motor home error: {exc}.\n")
        refresh_stack_controls(widget)
        return

    sp._stack_motor_homed = True
    sp._manual_motor_position_um = convert_mm_to_um(controller.current_position_mm)
    sp._stack_target_label.setText(
        f"Motor position: {controller.current_position_mm:.3f} mm"
    )
    widget._log_queue.put(
        f"[{ts}] [viewer] Motor homed: target={controller.current_position_mm:.3f} mm.\n"
    )
    refresh_stack_controls(widget)


# ---------------------------------------------------------------------------
# Control state helpers
# ---------------------------------------------------------------------------


def get_jog_lock_reason(widget: "EffusiveWidget") -> str:
    """Return a human-readable string explaining why motor jogging is locked.

    Returns an empty string when jogging is permitted.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the run state and recording flags.

    Returns
    -------
    str
        Lock reason message, or an empty string when jogging is allowed.
    """
    sp = widget._stack_panel
    record_locked = widget._save_active or (
        widget._run_button_state == "running"
        and widget._data_panel._save_button.isChecked()
    )
    if widget._run_button_state != "running":
        return "Start Effusive with the play button before moving the stack motor."
    if (
        sp._stack_backend_combo.currentText() == "Real motor"
        and not sp._stack_motor_homed
    ):
        return "Home the motor before manual jog moves."
    if sp._stack_active:
        return "Motor jog is locked while a z-stack is active."
    if record_locked:
        return "Motor jog is locked while recording is active."
    return ""


def refresh_stack_controls(widget: "EffusiveWidget") -> None:
    """Sync the stack panel button states with the current acquisition state.

    Updates enabled/disabled state and labels for the start/abort button, jog
    buttons, shared parameter widgets, and the stack lock hint, based on
    whether VSX is running, a stack is active, and recording is in progress.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the stack panel widgets and state flags.

    Returns
    -------
    None
        This helper mutates the stack panel widgets in place.
    """
    if not hasattr(widget, "_stack_panel"):
        return
    sp = widget._stack_panel
    if not hasattr(sp, "_stack_action_button"):
        return
    record_locked = widget._save_active or (
        widget._run_button_state == "running"
        and widget._data_panel._save_button.isChecked()
    )
    motion_ready = (
        sp._stack_backend_combo.currentText() == "Dummy motor" or sp._stack_motor_homed
    )
    stack_ready = True
    stack_reason = "Start a new z-stack acquisition."
    mp = widget._metadata_panel
    try:
        bids.validate_bids_entities(
            datatype=bids.ANGIO_DATATYPE,
            subject=mp._subject_edit.text().strip(),
            session=mp._session_edit.text().strip(),
            task=mp._task_edit.text().strip(),
            acq=mp._acq_edit.text().strip(),
            proc=mp._proc_edit.text().strip(),
        )
        if bids.check_bids_run_collision(
            Path(mp._storage_edit.text().strip()),
            datatype=bids.ANGIO_DATATYPE,
            subject=mp._subject_edit.text().strip(),
            session=mp._session_edit.text().strip(),
            task=mp._task_edit.text().strip(),
            acq=mp._acq_edit.text().strip(),
            run=mp._run_spinbox.value(),
            proc=mp._proc_edit.text().strip(),
        ):
            stack_ready = False
            stack_reason = (
                "Path already exists for this entity set. Change the storage metadata."
            )
    except ValueError as error:
        stack_ready = False
        stack_reason = str(error)

    stack_available = (
        widget._run_button_state == "running"
        and not record_locked
        and not sp._stack_active
        and motion_ready
        and stack_ready
    )
    jog_available = (
        widget._run_button_state == "running"
        and not record_locked
        and not sp._stack_active
        and motion_ready
    )
    home_available = (
        widget._run_button_state == "running"
        and not record_locked
        and not sp._stack_active
    )
    shared_available = stack_available or jog_available
    for w in sp._stack_shared_widgets:
        w.setEnabled(shared_available)
    for w in sp._stack_start_widgets:
        w.setEnabled(stack_available)
    sp._stack_jog_back_button.setEnabled(jog_available)
    sp._stack_jog_front_button.setEnabled(jog_available)
    sp._stack_home_button.setEnabled(home_available)
    stack_abort_available = widget._run_button_state == "running" and sp._stack_active
    sp._stack_action_button.setEnabled(stack_available or stack_abort_available)
    if stack_abort_available:
        sp._stack_action_button.setText("Stop z-stack")
        sp._stack_action_button.setObjectName("stack_btn_abort")
        sp._stack_action_button.setToolTip("Stop the active z-stack acquisition.")
    elif stack_available:
        sp._stack_action_button.setText("Start z-stack")
        sp._stack_action_button.setObjectName("stack_btn_start")
        sp._stack_action_button.setToolTip("Start a new z-stack acquisition.")
    else:
        sp._stack_action_button.setText("Start z-stack")
        sp._stack_action_button.setObjectName("stack_btn_disabled")
        sp._stack_action_button.setToolTip(
            stack_reason
            if widget._run_button_state == "running"
            else "Start Effusive with the play button before recording a z-stack."
        )
    style = sp._stack_action_button.style()
    if style is not None:
        style.unpolish(sp._stack_action_button)
        style.polish(sp._stack_action_button)

    lock_reason = get_jog_lock_reason(widget)
    jog_tooltip = (
        lock_reason or "Move the stack motor by one step in the selected direction."
    )
    sp._stack_jog_back_button.setToolTip(jog_tooltip)
    sp._stack_jog_front_button.setToolTip(jog_tooltip)
    sp._stack_home_button.setToolTip(
        "Home the motor and set the absolute reference origin."
    )

    if hasattr(sp, "_stack_lock_hint"):
        if widget._run_button_state != "running":
            hint_text = (
                "Start Effusive with the play button before recording a z-stack."
            )
            locked = True
        elif record_locked:
            hint_text = "Z-stack controls are locked while recording is active."
            locked = True
        elif sp._stack_active:
            hint_text = "Z-stack is active. Start controls are locked until it completes or aborts."
            locked = True
        elif (
            sp._stack_backend_combo.currentText() == "Real motor"
            and not sp._stack_motor_homed
        ):
            hint_text = "Home the motor before starting a z-stack or jogging."
            locked = True
        else:
            hint_text = "Z-stack can be started from this panel."
            locked = False
        controls.set_lock_hint_state(sp._stack_lock_hint, hint_text, locked)


def dispatch_stack_action(widget: "EffusiveWidget") -> None:
    """Dispatch the stack action button press to abort or start.

    Calls `abort_stack` when a z-stack is currently active, otherwise calls
    `start_stack`.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the stack state flag.

    Returns
    -------
    None
        This helper delegates to the start or abort path.
    """
    if widget._stack_panel._stack_active:
        abort_stack(widget)
    else:
        start_stack(widget)


# ---------------------------------------------------------------------------
# Stack status application
# ---------------------------------------------------------------------------


def apply_stack_status(
    widget: "EffusiveWidget",
    stack_status: tuple[int, int, int, int, int, int],
) -> None:
    """Apply a new z-stack status tuple to widget state and update the UI.

    Decodes the six-element status tuple written by MATLAB, updates the
    stack state flags, refreshes the status labels, and triggers a preview
    state-machine transition when the stack starts or stops.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the stack state and status labels.
    stack_status : tuple of int
        Six-element tuple ``(active, error, status_code, current_slice,
        total_slices, target_um)`` as read from the shared-memory stack
        segment.

    Returns
    -------
    None
        This helper mutates widget stack state and UI labels in place.
    """
    sp = widget._stack_panel
    if stack_status == sp._last_stack_status:
        return

    previous_status = sp._last_stack_status
    sp._last_stack_status = stack_status
    (
        stack_active,
        stack_error,
        status_code,
        current_slice,
        total_slices,
        target_um,
    ) = stack_status
    sp._stack_active = bool(stack_active)
    sp._stack_error = bool(stack_error)
    sp._stack_status_code = int(status_code)
    sp._stack_current_slice = int(current_slice)
    sp._stack_total_slices = int(total_slices)
    sp._stack_target_position_um = int(target_um)

    status_text = _STACK_STATUS_TEXT.get(sp._stack_status_code, "Unknown")
    if sp._stack_error:
        status_text = f"{status_text} (error)"

    if sp._stack_active or sp._stack_target_position_um != 0:
        target_um_for_display = sp._stack_target_position_um
    elif sp._manual_motor_position_um is not None:
        target_um_for_display = sp._manual_motor_position_um
    else:
        target_um_for_display = 0

    if sp._stack_active or target_um_for_display != 0:
        sp._stack_target_label.setText(
            f"Motor position: {target_um_for_display / 1000.0:.3f} mm"
        )
    else:
        sp._stack_target_label.setText("Motor position: -")

    controls.refresh_runtime_status(widget)
    controls.refresh_control_locks(widget)

    handle_stack_preview_transition(widget, previous_status)

    if previous_status is None:
        return
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    widget._log_queue.put(
        f"[{ts}] [viewer] Stack status: {status_text}; "
        f"slice={sp._stack_current_slice}/{sp._stack_total_slices}; "
        f"target={sp._stack_target_position_um} um.\n"
    )


# ---------------------------------------------------------------------------
# Preview state machine
# ---------------------------------------------------------------------------


def reset_stack_preview(widget: "EffusiveWidget") -> None:
    """Clear all preview accumulation buffers and reset slice tracking.

    Called when a new z-stack sweep starts so stale data from a previous
    sweep does not bleed into the new preview volume.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the preview accumulation buffers.

    Returns
    -------
    None
        This helper zeroes all preview state in place.
    """
    sp = widget._stack_panel
    sp._stack_preview_volume = None
    sp._stack_preview_bmode_volume = None
    sp._stack_preview_sum = None
    sp._stack_preview_bmode_sum = None
    sp._stack_preview_count = 0
    sp._stack_preview_slice_index = -1
    sp._stack_preview_paused_on_complete = False
    sp._stack_preview_hold_display = False


def handle_stack_preview_transition(
    widget: "EffusiveWidget",
    previous_status: tuple[int, int, int, int, int, int] | None,
) -> None:
    """React to a stack-active transition by resetting or finalising the preview.

    On a start transition the preview buffers are cleared. On a stop
    transition the current slice is finalised and, when the stack completed
    without error, the last preview frame is held and the standard UI pause
    path is requested so the user can inspect the result.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the preview state and pause control.
    previous_status : tuple of int or None
        The six-element stack status tuple from the previous polling tick,
        or `None` on the very first tick after acquisition starts.

    Returns
    -------
    None
        This helper mutates preview state and may request a pause.
    """
    sp = widget._stack_panel
    previously_active = False
    previous_error = False
    previous_status_code = shared_memory.STACK_STATUS_IDLE
    if previous_status is not None:
        previously_active = bool(previous_status[0])
        previous_error = bool(previous_status[1])
        previous_status_code = int(previous_status[2])

    stack_started = sp._stack_active and not previously_active
    stack_stopped = previously_active and not sp._stack_active

    if stack_started:
        reset_stack_preview(widget)

    if stack_stopped:
        finalize_stack_preview_slice(widget)
        if hasattr(widget, "_metadata_panel"):
            widget._metadata_panel.refresh_previews()
        stack_completed = (
            not sp._stack_error
            and not previous_error
            and (
                previous_status_code == shared_memory.STACK_STATUS_COMPLETING
                or sp._stack_status_code == shared_memory.STACK_STATUS_COMPLETING
            )
        )
        if (
            stack_completed
            and not sp._stack_preview_paused_on_complete
            and widget._run_button_state == "running"
            and not widget._pause_button.isChecked()
        ):
            sp._stack_preview_paused_on_complete = True
            sp._stack_preview_hold_display = True
            commands.handle_pause(widget, True)


def ensure_stack_preview_volume(widget: "EffusiveWidget") -> None:
    """Allocate preview accumulation arrays sized for the current stack.

    Does nothing when the arrays already have the correct shape. Called once
    per frame during an active sweep to lazily initialise the buffers after
    the first metadata read sets `_image_depth_pixels`, `_image_width_pixels`, and `_stack_total_slices`.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the preview buffers and dimension state.

    Returns
    -------
    None
        This helper allocates or no-ops the preview arrays in place.
    """
    sp = widget._stack_panel
    if (
        widget._image_depth_pixels <= 0
        or widget._image_width_pixels <= 0
        or sp._stack_total_slices <= 0
    ):
        return
    if sp._stack_preview_volume is not None and sp._stack_preview_volume.shape == (
        sp._stack_total_slices,
        widget._image_depth_pixels,
        widget._image_width_pixels,
    ):
        return

    sp._stack_preview_volume = np.zeros(
        (
            sp._stack_total_slices,
            widget._image_depth_pixels,
            widget._image_width_pixels,
        ),
        dtype=np.float32,
    )
    sp._stack_preview_bmode_volume = np.full(
        (
            sp._stack_total_slices,
            widget._image_depth_pixels,
            widget._image_width_pixels,
        ),
        fill_value=shared_memory.BMODE_CONTRAST_LIMITS[0],
        dtype=np.float32,
    )
    sp._stack_preview_sum = np.zeros(
        (widget._image_depth_pixels, widget._image_width_pixels), dtype=np.float32
    )
    sp._stack_preview_bmode_sum = np.zeros(
        (widget._image_depth_pixels, widget._image_width_pixels), dtype=np.float32
    )
    sp._stack_preview_count = 0
    sp._stack_preview_slice_index = sp._stack_current_slice


def finalize_stack_preview_slice(widget: "EffusiveWidget") -> None:
    """Write the running average of the current slice into the preview volume.

    Divides the accumulated PDI and B-mode sums by the frame count and stores
    the result at the current slice index, then resets the per-slice accumulators
    so the next slice starts from zero.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the preview accumulation buffers.

    Returns
    -------
    None
        This helper mutates the preview volume in place.
    """
    sp = widget._stack_panel
    if sp._stack_preview_volume is None:
        return
    if (
        sp._stack_preview_sum is None
        or sp._stack_preview_bmode_sum is None
        or sp._stack_preview_count <= 0
    ):
        return
    if not (0 <= sp._stack_preview_slice_index < sp._stack_preview_volume.shape[0]):
        return
    bmode_sum = sp._stack_preview_bmode_sum
    sp._stack_preview_volume[sp._stack_preview_slice_index, :, :] = (
        sp._stack_preview_sum / float(sp._stack_preview_count)
    )
    if sp._stack_preview_bmode_volume is not None and bmode_sum is not None:
        sp._stack_preview_bmode_volume[sp._stack_preview_slice_index, :, :] = (
            bmode_sum / float(sp._stack_preview_count)
        )
    sp._stack_preview_sum.fill(0.0)
    if bmode_sum is not None:
        bmode_sum.fill(0.0)
    sp._stack_preview_count = 0


def update_stack_preview(
    widget: "EffusiveWidget", bmode: np.ndarray, pdi: np.ndarray
) -> bool:
    """Accumulate one frame into the running z-stack preview and update layers.

    Adds the incoming B-mode and PDI frames to the per-slice running sums,
    writes the current average into the preview volume, and pushes both the
    PDI and B-mode volumes to the napari layers. On a slice index change the
    previous slice is first finalised.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the preview buffers, napari layers, and
        stack geometry spinboxes.
    bmode : numpy.ndarray
        2-D B-mode frame with shape `(nz, nx)`.
    pdi : numpy.ndarray
        2-D PDI frame with shape `(nz, nx)`.

    Returns
    -------
    bool
        `True` when a z-stack sweep is active and the preview was updated;
        `False` when no sweep is running.
    """
    sp = widget._stack_panel
    if not sp._stack_active:
        return False
    if sp._stack_total_slices <= 0 or sp._stack_current_slice < 0:
        return False
    ensure_stack_preview_volume(widget)
    if sp._stack_preview_volume is None:
        return False
    if sp._stack_preview_sum is None or sp._stack_preview_bmode_sum is None:
        sp._stack_preview_sum = np.zeros(
            (widget._image_depth_pixels, widget._image_width_pixels), dtype=np.float32
        )
        sp._stack_preview_bmode_sum = np.zeros(
            (widget._image_depth_pixels, widget._image_width_pixels), dtype=np.float32
        )
    pdi_sum = cast(np.ndarray | None, sp._stack_preview_sum)
    bmode_sum = cast(np.ndarray | None, sp._stack_preview_bmode_sum)
    if pdi_sum is None or bmode_sum is None:
        return False

    if sp._stack_preview_slice_index != sp._stack_current_slice:
        finalize_stack_preview_slice(widget)
        sp._stack_preview_slice_index = sp._stack_current_slice

    pdi_sum += pdi
    bmode_sum += bmode
    sp._stack_preview_count += 1
    sp._stack_preview_volume[sp._stack_preview_slice_index, :, :] = pdi_sum / float(
        sp._stack_preview_count
    )
    if sp._stack_preview_bmode_volume is not None:
        sp._stack_preview_bmode_volume[sp._stack_preview_slice_index, :, :] = (
            bmode_sum / float(sp._stack_preview_count)
        )

    slice_pitch_mm = abs(sp._stack_step_mm_spinbox.value())
    if slice_pitch_mm <= 0:
        slice_pitch_mm = 1.0
    stack_scale = [slice_pitch_mm, widget._depth_step_mm, widget._lateral_step_mm]
    stack_translate = [sp._stack_start_mm_spinbox.value(), 0.0, 0.0]

    if widget._bmode_layer is not None and sp._stack_preview_bmode_volume is not None:
        widget._bmode_layer.data = sp._stack_preview_bmode_volume  # type: ignore
        widget._bmode_layer.scale = tuple(stack_scale)
        widget._bmode_layer.translate = tuple(stack_translate)

    if widget._pdi_layer is not None:
        widget._pdi_layer.data = sp._stack_preview_volume  # type: ignore
        widget._pdi_layer.scale = tuple(stack_scale)
        widget._pdi_layer.translate = tuple(stack_translate)
    return True


# ---------------------------------------------------------------------------
# Command callbacks
# ---------------------------------------------------------------------------


def start_stack(widget: "EffusiveWidget") -> None:
    """Validate preconditions and send the z-stack start command to MATLAB.

    Closes any open manual motor controller so the MATLAB-side z-stack driver
    takes exclusive motor ownership. Writes all stack geometry parameters to
    the shared-memory command segment.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the stack parameter spinboxes and the
        shared-memory command channel.

    Returns
    -------
    None
        This helper sends a shared-memory command and logs the outcome.
    """
    sp = widget._stack_panel
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    if not widget._shared_memory_segments or widget._run_button_state != "running":
        widget._log_queue.put(
            f"[{ts}] [viewer] Stack start rejected: Effusive is not running.\n"
        )
        return
    if sp._stack_active:
        widget._log_queue.put(
            f"[{ts}] [viewer] Stack start rejected: a z-stack is already active.\n"
        )
        return
    if (
        sp._stack_backend_combo.currentText() == "Real motor"
        and not sp._stack_motor_homed
    ):
        widget._log_queue.put(
            f"[{ts}] [viewer] Stack start rejected: home the motor first.\n"
        )
        return

    mp = widget._metadata_panel
    storage_root = widget._metadata_panel._storage_edit.text().strip()
    run = mp._run_spinbox.value()
    try:
        collision = bids.check_bids_run_collision(
            Path(storage_root),
            datatype=bids.ANGIO_DATATYPE,
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
            return
    except ValueError:
        pass

    bids.write_bids_meta_sidecar(
        task=mp._task_edit.text().strip(),
        acq=mp._acq_edit.text().strip(),
        proc=mp._proc_edit.text().strip(),
        run=mp._run_spinbox.value(),
        subject=mp._subject_edit.text().strip(),
        session=mp._session_edit.text().strip(),
    )

    close_motor_controller(widget)

    widget.write_shared_memory_command(
        stack_use_dummy_motor=1
        if sp._stack_backend_combo.currentText() == "Dummy motor"
        else 0,
        stack_start_um=convert_mm_to_um(sp._stack_start_mm_spinbox.value()),
        stack_step_um=convert_mm_to_um(sp._stack_step_mm_spinbox.value()),
        stack_n_slices=sp._stack_n_slices_spinbox.value(),
        stack_npdi_per_slice=sp._stack_npdi_per_slice_spinbox.value(),
        stack_settle_ms=sp._stack_settle_ms_spinbox.value(),
        stack_start_flag=1,
        stack_abort_flag=0,
        stack_req_id=widget.next_command_request_id("stack"),
    )
    widget._log_queue.put(
        f"[{ts}] [viewer] Stack request sent: "
        f"backend={sp._stack_backend_combo.currentText().lower()}, "
        f"start={sp._stack_start_mm_spinbox.value():.3f} mm, "
        f"step={sp._stack_step_mm_spinbox.value():.3f} mm, "
        f"slices={sp._stack_n_slices_spinbox.value()}, "
        f"frames/slice={sp._stack_npdi_per_slice_spinbox.value()}, "
        f"settle={sp._stack_settle_ms_spinbox.value()} ms.\n"
    )


def abort_stack(widget: "EffusiveWidget") -> None:
    """Send the z-stack abort command to MATLAB.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the stack state flag and shared-memory
        command channel.

    Returns
    -------
    None
        This helper sends a shared-memory command and logs the outcome.
    """
    sp = widget._stack_panel
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    if not widget._shared_memory_segments or widget._run_button_state != "running":
        widget._log_queue.put(
            f"[{ts}] [viewer] Stack abort rejected: Effusive is not running.\n"
        )
        return
    if not sp._stack_active:
        widget._log_queue.put(
            f"[{ts}] [viewer] Stack abort ignored: no active z-stack.\n"
        )
        return
    widget.write_shared_memory_command(
        stack_start_flag=0,
        stack_abort_flag=1,
        stack_req_id=widget.next_command_request_id("stack"),
    )
    widget._log_queue.put(f"[{ts}] [viewer] Stack abort requested.\n")


def jog_stack(widget: "EffusiveWidget", direction: int) -> None:
    """Move the stack motor by one step in the requested direction.

    Uses the step size from the stack step spinbox as the jog magnitude.
    Rejects the jog when it is currently locked (no VSX, active stack, or
    active recording) and logs the reason. On success, updates
    `_manual_motor_position_um` and refreshes the target label.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the motor controller, step spinbox, and
        target label.
    direction : int
        `+1` to move toward the front of the sample; `-1` to move toward the
        back.

    Returns
    -------
    None
        This helper mutates motor position state and logs the outcome.
    """
    sp = widget._stack_panel
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    lock_reason = get_jog_lock_reason(widget)
    if lock_reason:
        widget._log_queue.put(f"[{ts}] [viewer] Stack jog rejected: {lock_reason}\n")
        return

    jog_mm = abs(sp._stack_step_mm_spinbox.value())
    if jog_mm <= 0.0:
        widget._log_queue.put(
            f"[{ts}] [viewer] Stack jog rejected: step size must be non-zero.\n"
        )
        return
    jog_mm = float(direction) * jog_mm
    try:
        controller = open_motor_controller(widget)
        target_position_mm = controller.jog_relative(jog_mm)
    except Exception as exc:
        widget._log_queue.put(f"[{ts}] [viewer] Stack jog error: {exc}.\n")
        return

    sp._manual_motor_position_um = convert_mm_to_um(target_position_mm)
    sp._stack_target_label.setText(f"Motor position: {target_position_mm:.3f} mm")
    widget._log_queue.put(
        f"[{ts}] [viewer] Stack jog moved: "
        f"backend={sp._stack_backend_combo.currentText().lower()}, "
        f"delta={jog_mm:.3f} mm, target={target_position_mm:.3f} mm.\n"
    )
