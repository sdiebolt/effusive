"""Runtime polling helpers for the Effusive napari widget."""

from __future__ import annotations

import datetime
import queue
import time
from typing import TYPE_CHECKING

import numpy as np
from napari.utils.notifications import show_error

from effusive import config as cf_config
from effusive import shared_memory
from effusive.napari import controls
from effusive.napari import stack as stack_helpers
from effusive.napari import worker as worker_module

if TYPE_CHECKING:
    from effusive.napari.widget import EffusiveWidget

TIMING_WARNING_HOLD_S = 5.0
"""How long a `timeToNextAcq` warning stays shown in the info overlay after
the last occurrence, so a resolved stall clears on its own."""


def _restore_crop_shape(widget: "EffusiveWidget") -> None:
    """Populate the crop layer with saved vertices once the image scale is known.

    Called on the first frame so the scale is already set on the crop layer
    before the shape is added, keeping pixel coordinates and world coordinates
    in sync.  Does nothing when there are no valid saved vertices, or when the
    layer already has shapes (e.g. user drew one before acquisition started).

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the crop layer and config.

    Returns
    -------
    None
        Mutates the crop layer in place.
    """
    if widget._crop_layer is None:
        return
    if len(widget._crop_layer.data) > 0:
        return
    saved = widget._config.crop.vertices
    if not cf_config.validate_crop_vertices(saved):
        return
    try:
        widget._crop_layer.add_rectangles(
            [np.array(saved)],
            edge_color="red",
            face_color=[0, 0, 0, 0],
            edge_width=2,
        )
    except Exception:
        pass


def apply_pending_udp_metadata(widget: "EffusiveWidget") -> None:
    """Apply any queued UDP metadata update on the main Qt thread.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance owning the metadata controls and pending UDP state.

    Returns
    -------
    None
        Updates metadata controls, previews, and config state in place.
    """
    pending = widget._pending_udp_metadata
    if pending is None:
        return
    widget._pending_udp_metadata = None
    subject, session, run_index = pending
    mp = widget._metadata_panel
    mp._subject_edit.setText(subject)
    mp._session_edit.setText(session)
    mp._run_spinbox.setValue(int(run_index))
    mp.refresh_previews()
    controls.refresh_control_locks(widget)


def drain_log(widget: "EffusiveWidget") -> None:
    """Drain queued log lines into the visible log panel.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the queued log lines and text panel.

    Returns
    -------
    None
        This helper mutates the log panel in place.
    """
    try:
        while True:
            line = widget._log_queue.get_nowait()
            widget._log_text.appendPlainText(line.rstrip())
            scroll_bar = widget._log_text.verticalScrollBar()
            if scroll_bar is not None:
                scroll_bar.setValue(scroll_bar.maximum())
    except queue.Empty:
        pass


def request_rf_snapshot(widget: "EffusiveWidget") -> None:
    """Send the RF snapshot request to MATLAB and arm the snapshot latch.

    Sets `show_rf=1` in the shared-memory command segment and raises
    `_waiting_for_snapshot` so `check_rf_snapshot` will clear the flag once
    MATLAB has written the data. The rising edge is guaranteed to be seen by
    MATLAB regardless of frame rate because the flag is only cleared after the
    snapshot counter advances.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the command channel and snapshot state.

    Returns
    -------
    None
        This helper mutates snapshot state and sends a shared-memory command.
    """
    if not widget._shared_memory_segments:
        return
    widget.write_shared_memory_command(show_rf=1)
    widget._waiting_for_snapshot = True
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    widget._log_queue.put(f"[{ts}] [viewer] Requesting RF snapshot.\n")


def check_rf_snapshot(widget: "EffusiveWidget") -> None:
    """Poll the RF shared-memory segment and update the RF layer.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the RF layer and shared-memory reader.

    Returns
    -------
    None
        This helper updates the RF layer in place when a new snapshot arrives.
    """
    if widget._shared_memory_reader is None:
        return
    try:
        rf_counter, n_samples, n_columns = widget._shared_memory_reader.read_rf_header()
    except Exception:
        return
    if rf_counter == 0 or int(rf_counter) == widget._last_rf_counter:
        return
    widget._last_rf_counter = int(rf_counter)
    if widget._waiting_for_snapshot:
        widget._waiting_for_snapshot = False
        widget.write_shared_memory_command(show_rf=0)
    if n_samples <= 0 or n_columns <= 0:
        return
    try:
        rf_data = widget._shared_memory_reader.read_rf(n_samples, n_columns)
    except Exception as error:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        widget._log_queue.put(f"[{timestamp}] [viewer] RF read error: {error}.\n")
        return
    rf_display = rf_data.astype(np.float32)
    depth_step_rf = widget._depth_mm / max(n_samples, 1) if widget._scale_set else 1.0
    lateral_step_rf = widget._lateral_step_mm if widget._scale_set else 1.0

    if widget._rf_layer is None:
        widget._rf_layer = widget.viewer.add_image(
            rf_display,
            name="RF snapshot",
            colormap="gray",
            gamma=0.2,
            scale=[depth_step_rf, lateral_step_rf],
            units=("mm", "mm"),
        )
        rf_index = widget.viewer.layers.index(widget._rf_layer)
        if rf_index != 2:
            widget.viewer.layers.move(rf_index, 2)
        widget.viewer.canvas.grid.shape = (1, 3)
    else:
        widget._rf_layer.data = rf_display
        widget._rf_layer.scale = [depth_step_rf, lateral_step_rf]

    timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    widget._log_queue.put(
        f"[{timestamp}] [viewer] RF snapshot updated ({n_samples}×{n_columns}).\n"
    )


def handle_worker_exit(widget: "EffusiveWidget") -> bool:
    """Handle unexpected worker termination during timer polling.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the worker process and shared resources.

    Returns
    -------
    bool
        `True` when the worker had exited and cleanup was performed,
        otherwise `False`.
    """
    if widget._worker is None or widget._worker.poll() is None:
        return False

    return_code = widget._worker.returncode
    widget._worker = None
    timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    widget._log_queue.put(f"[{timestamp}] [viewer] Worker exited (rc={return_code}).\n")
    if widget._timer is not None:
        widget._timer.stop()
        widget._timer = None

    reader = widget._shared_memory_reader
    widget._shared_memory_reader = None
    shared_memory_segments = widget._shared_memory_segments
    widget._shared_memory_segments = ()
    log_file_handle = widget._log_file
    widget._log_file = None
    if reader:
        reader.close()
    if shared_memory_segments:
        shared_memory.close_segments(*shared_memory_segments, unlink=False)
    if log_file_handle:
        log_file_handle.close()
    worker_module.finish_stop(widget)
    widget._set_viewer_status_overlay(
        "cf_status_error" if return_code != 0 else "cf_status_ready",
    )
    return True


def _flush_pending_udp_error(widget: "EffusiveWidget") -> None:
    """Show any pending UDP collision/error notification on the UI thread."""
    message = widget._pending_udp_error
    if not message:
        return
    widget._pending_udp_error = None
    show_error(message)


def handle_timer_tick(widget: "EffusiveWidget") -> None:
    """Process one timer tick for shared-memory polling and display updates.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the polling timer, shared-memory reader,
        and napari layers.

    Returns
    -------
    None
        This helper mutates widget runtime state and layers in place.
    """
    _flush_pending_udp_error(widget)
    apply_pending_udp_metadata(widget)
    drain_log(widget)

    if handle_worker_exit(widget):
        return

    if widget._shared_memory_reader is None:
        return

    check_rf_snapshot(widget)

    try:
        (
            frame_counter,
            image_depth_pixels,
            image_width_pixels,
            z0,
            z1,
            x0,
            x1,
            runtime_flags,
            ensemble_time_s,
        ) = widget._shared_memory_reader.read_meta()
    except Exception:
        return

    previous_save_active = widget._save_active
    previous_stack_active = widget._stack_panel._stack_active
    controls.apply_runtime_flags(widget, int(runtime_flags))
    if widget._run_button_state == "running":
        desired_freeze = bool(widget._pause_button.isChecked())
        if desired_freeze != widget._freeze_active:
            widget.write_shared_memory_command(
                freeze=1 if desired_freeze else 0,
                freeze_req_id=widget.next_command_request_id("freeze"),
            )

    try:
        stack_helpers.apply_stack_status(
            widget, widget._shared_memory_reader.read_stack_status()
        )
    except Exception:
        pass

    frame_counter = int(frame_counter)
    if frame_counter > 0:
        if (
            widget._pending_stack_resume_frame_reset
            and widget._stack_completion_freeze_seen
            and not widget._freeze_active
            and frame_counter != widget._last_frame
        ):
            widget.reset_display_frame_counter(frame_counter)
            widget._pending_stack_resume_frame_reset = False
            widget._stack_completion_freeze_seen = False
        if widget._pending_stack_resume_frame_reset and widget._freeze_active:
            widget._stack_completion_freeze_seen = True
        if widget._pending_display_frame_reset:
            widget.reset_display_frame_counter(frame_counter)
            widget._pending_display_frame_reset = False
        if widget._save_active != previous_save_active:
            widget.reset_display_frame_counter(frame_counter)
            widget._metadata_panel.refresh_previews()
        if widget._stack_panel._stack_active and not previous_stack_active:
            widget.reset_display_frame_counter(frame_counter)
        elif previous_stack_active and not widget._stack_panel._stack_active:
            if widget._stack_panel._stack_preview_hold_display:
                widget._pending_stack_resume_frame_reset = True
                widget._stack_completion_freeze_seen = widget._freeze_active
            else:
                widget._pending_display_frame_reset = True

    if image_depth_pixels == 0 or image_width_pixels == 0:
        return

    if widget._pending_resets:
        still_pending = []
        for flag_name, reset_value, minimum_frame in widget._pending_resets:
            if frame_counter >= minimum_frame:
                widget.write_shared_memory_command(**{flag_name: reset_value})
            else:
                still_pending.append((flag_name, reset_value, minimum_frame))
        widget._pending_resets = still_pending

    if frame_counter <= 0:
        return

    first_scale = (
        not widget._scale_set and image_depth_pixels > 1 and image_width_pixels > 1
    )
    if first_scale:
        depth_step = (z1 - z0) / (image_depth_pixels - 1)
        lateral_step = (x1 - x0) / (image_width_pixels - 1)
        widget._depth_step_mm = depth_step
        widget._lateral_step_mm = lateral_step
        widget._depth_mm = z1 - z0
        if widget._bmode_layer is not None:
            widget._bmode_layer.scale = (1.0, depth_step, lateral_step)
        if widget._pdi_layer is not None:
            widget._pdi_layer.scale = (1.0, depth_step, lateral_step)
        if widget._crop_layer is not None:
            widget._crop_layer.scale = (depth_step, lateral_step)
            _restore_crop_shape(widget)
        widget._scale_set = True

    if frame_counter == widget._last_frame:
        return

    first_displayable_frame = widget._last_frame < 1
    widget._last_frame = frame_counter
    if first_displayable_frame:
        controls.refresh_runtime_status(widget)
    sp = widget._stack_panel
    if sp._stack_active and sp._stack_total_slices > 0 and sp._stack_current_slice >= 0:
        frame_text = f"Slice {min(sp._stack_current_slice + 1, sp._stack_total_slices)}/{sp._stack_total_slices}"
    elif (
        sp._stack_preview_hold_display
        and sp._stack_preview_volume is not None
        and sp._stack_preview_slice_index >= 0
    ):
        frame_text = f"Slice {sp._stack_preview_slice_index + 1}/{sp._stack_preview_volume.shape[0]}"
    else:
        frame_text = f"Frame {frame_counter - widget._frame_display_offset}"
    widget._image_depth_pixels = int(image_depth_pixels)
    widget._image_width_pixels = int(image_width_pixels)

    if ensemble_time_s > 0.0:
        info_text = f"{frame_text} • t = {ensemble_time_s:.3f} s"
    else:
        info_text = frame_text
    last_warning = widget._last_timing_warning_monotonic
    if (
        last_warning is not None
        and time.monotonic() - last_warning < TIMING_WARNING_HOLD_S
    ):
        info_text += "  ⚠ timeToNextAcq"
    widget._set_viewer_info_overlay(info_text)

    bmode = widget._shared_memory_reader.read_bmode(
        widget._image_depth_pixels, widget._image_width_pixels
    )
    pdi = widget._shared_memory_reader.read_pdi(
        widget._image_depth_pixels, widget._image_width_pixels
    )

    preview_active = stack_helpers.update_stack_preview(widget, bmode, pdi)
    sp = widget._stack_panel
    hold_stack_preview = (
        sp._stack_preview_hold_display
        and widget._pause_button.isChecked()
        and not sp._stack_active
    )
    if (
        widget._bmode_layer is not None
        and not preview_active
        and not hold_stack_preview
    ):
        widget._bmode_layer.data = bmode[np.newaxis, :, :]  # type: ignore
        widget._bmode_layer.scale = (
            1.0,
            widget._depth_step_mm,
            widget._lateral_step_mm,
        )
        widget._bmode_layer.translate = (0.0, 0.0, 0.0)

    if widget._pdi_layer is not None:
        if preview_active or hold_stack_preview:
            pass
        elif widget._crop_roi is not None:
            top, bottom, left, right = widget._crop_roi
            widget._pdi_layer.data = pdi[np.newaxis, top:bottom, left:right]  # type: ignore
            widget._pdi_layer.scale = (
                1.0,
                widget._depth_step_mm,
                widget._lateral_step_mm,
            )
            widget._pdi_layer.translate = (
                0.0,
                top * widget._depth_step_mm,
                left * widget._lateral_step_mm,
            )
        else:
            widget._pdi_layer.data = pdi[np.newaxis, :, :]  # type: ignore
            widget._pdi_layer.scale = (
                1.0,
                widget._depth_step_mm,
                widget._lateral_step_mm,
            )
            widget._pdi_layer.translate = (0.0, 0.0, 0.0)

    if first_scale:
        try:
            widget.viewer.reset_view()
        except Exception:
            pass
