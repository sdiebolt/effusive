"""Crop layer helpers for the Effusive napari widget."""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import numpy as np

from effusive.config import save_config
from effusive.napari import controls

if TYPE_CHECKING:
    from effusive.napari.widget import EffusiveWidget


def refresh_crop_interaction_lock(widget: "EffusiveWidget") -> None:
    """Sync the crop layer editability with the current acquisition state.

    The crop layer is locked whenever a z-stack sweep is active. Outside of
    a sweep the layer is editable only when no ROI has been applied, so the
    user cannot accidentally drag the shape while acquisition is running on
    the committed region.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the crop layer and the stack-active flag.

    Returns
    -------
    None
        This helper mutates the crop layer in place.
    """
    if not hasattr(widget, "_crop_layer"):
        return
    if widget._stack_panel._stack_active:
        set_crop_layer_editable(widget, False)
        return
    set_crop_layer_editable(widget, widget._crop_roi is None)


def set_crop_layer_editable(widget: "EffusiveWidget", editable: bool) -> None:
    """Set the crop layer editable state and configure its toolbar controls.

    Calling this with `editable=False` also clears any selected shapes and
    forces the layer back to *select* mode, preventing leftover drag handles
    from blocking the view.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the crop layer.
    editable : bool
        `True` to allow drawing and editing; `False` to lock the layer.

    Returns
    -------
    None
        This helper mutates the crop layer in place.
    """
    if widget._crop_layer is None:
        return
    configure_crop_layer_controls(widget)
    try:
        widget._crop_layer.editable = editable
    except Exception:
        pass
    try:
        if not editable:
            widget._crop_layer.selected_data = set()
        widget._crop_layer.mode = "select"
    except Exception:
        pass


def configure_crop_layer_controls(widget: "EffusiveWidget") -> None:
    """Restrict the crop layer toolbar to rectangle-only drawing tools.

    All non-rectangle shape buttons are disabled and de-pressed so the user
    cannot accidentally draw ellipses, lines, or polygons into the ROI layer.
    This is called eagerly on every editability change because napari can
    recreate the controls widget between calls.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the crop layer.

    Returns
    -------
    None
        This helper mutates the napari controls widget in place.
    """
    if widget._crop_layer is None:
        return
    bind_crop_mode_guard(widget)
    controls = get_crop_layer_controls_widget(widget)
    if controls is None:
        return

    enabled_buttons = {
        "select_button",
        "transform_button",
        "rectangle_button",
        "add_rectangle_button",
        "panzoom_button",
    }
    shape_buttons = {name for name in dir(controls) if name.endswith("_button")}
    shape_buttons.update(
        {
            "select_button",
            "direct_button",
            "transform_button",
            "rectangle_button",
            "add_rectangle_button",
            "move_front_button",
            "move_back_button",
            "delete_button",
            "ellipse_button",
            "add_ellipse_button",
            "line_button",
            "add_line_button",
            "path_button",
            "add_path_button",
            "polygon_button",
            "add_polygon_button",
            "polygon_lasso_button",
            "add_polygon_lasso_button",
            "vertex_insert_button",
            "vertex_remove_button",
        }
    )
    for name in sorted(shape_buttons):
        btn = getattr(controls, name, None)
        if btn is None:
            continue
        try:
            is_enabled = name in enabled_buttons
            btn.setEnabled(is_enabled)
            if not is_enabled:
                btn.setChecked(False)
                btn.setDown(False)
                btn.style().unpolish(btn)
                btn.style().polish(btn)
                btn.update()
        except Exception:
            pass


def bind_crop_mode_guard(widget: "EffusiveWidget") -> None:
    """Connect the crop mode guard exactly once per crop layer instance.

    Napari can replace the layer object between sessions, so this uses
    `id(widget._crop_layer)` as a per-instance connection sentinel to avoid
    duplicate signals after a layer restore.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the crop layer and the hook-id set.

    Returns
    -------
    None
        This helper registers a signal connection as a side effect.
    """
    if widget._crop_layer is None:
        return
    layer_id = id(widget._crop_layer)
    if layer_id in widget._crop_mode_hook_layer_ids:
        return
    try:
        widget._crop_layer.events.mode.connect(
            lambda event: guard_crop_mode(widget, event)
        )
        widget._crop_mode_hook_layer_ids.add(layer_id)
    except Exception:
        pass


def guard_crop_mode(widget: "EffusiveWidget", event=None) -> None:
    """Guard against non-rectangle drawing modes on the crop layer.

    Napari allows switching to any shape tool via keyboard shortcut. When the
    user (or napari itself) selects a disallowed mode, this callback forces the
    layer back to *select* mode.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the crop layer.
    event : optional
        Napari mode-change event; ignored but required by the signal protocol.

    Returns
    -------
    None
        This helper mutates the crop layer mode in place.
    """
    _ = event
    if widget._crop_layer is None:
        return
    allowed_modes = {"select", "transform", "add_rectangle"}
    try:
        mode = widget._crop_layer.mode
    except Exception:
        return
    if mode in allowed_modes:
        return
    try:
        widget._crop_layer.mode = "select"
    except Exception:
        pass


def get_crop_layer_controls_widget(widget: "EffusiveWidget"):
    """Retrieve the napari controls widget for the crop shapes layer.

    Navigates the private `qt_viewer.controls.widgets` mapping to find the
    toolbar widget associated with the crop layer. Returns `None` whenever
    the viewer internals are not yet initialised or the layer is absent.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the crop layer and napari viewer.

    Returns
    -------
    QWidget or None
        The napari controls widget for the crop layer, or `None` if it cannot
        be found.
    """
    if widget._crop_layer is None:
        return None
    try:
        qt_viewer = getattr(widget.viewer.window, "_qt_viewer", None)
        if qt_viewer is None:
            qt_viewer = getattr(widget.viewer.window, "qt_viewer", None)
        if qt_viewer is None:
            return None
        controls = getattr(qt_viewer, "controls", None)
        if controls is None:
            return None
        widgets = getattr(controls, "widgets", None)
        if widgets is None:
            return None
        if hasattr(widgets, "get"):
            return widgets.get(widget._crop_layer)
        return widgets[widget._crop_layer]
    except Exception:
        return None


def toggle_crop(widget: "EffusiveWidget") -> None:
    """Toggle between applying and resetting the crop ROI.

    Calls `apply_crop` when no ROI is committed, or `reset_crop` when one
    is active.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the crop state.

    Returns
    -------
    None
        This helper delegates to the apply or reset path.
    """
    if widget._crop_roi is None:
        apply_crop(widget)
    else:
        reset_crop(widget)


def apply_crop(widget: "EffusiveWidget") -> None:
    """Validate the drawn ROI and send a crop command to MATLAB.

    Reads the first shape from the crop layer, validates that it is a single
    rectangle within the current frame dimensions, writes the crop command to
    shared memory, and locks the shapes layer so the ROI cannot be
    accidentally moved while acquisition runs on the committed region.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the crop layer, shared-memory command channel,
        and current frame dimensions.

    Returns
    -------
    None
        This helper mutates widget crop state and sends a shared-memory command.
    """
    if widget._crop_layer is None:
        return
    shapes = widget._crop_layer.data
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    if len(shapes) == 0:
        widget._log_queue.put(
            f"[{ts}] [viewer] Crop: draw a rectangle in the 'Crop ROI' layer first.\n"
        )
        return
    if len(shapes) > 1:
        widget._log_queue.put(f"[{ts}] [viewer] Crop error: only one shape allowed.\n")
        return
    shape_types = widget._crop_layer.shape_type
    if shape_types[0] != "rectangle":
        widget._log_queue.put(
            f"[{ts}] [viewer] Crop error: shape must be a rectangle (got '{shape_types[0]}').\n"
        )
        return
    rect = shapes[0]  # (N, 2) array: rows in col 0, cols in col 1 (pixel coords)
    # Save vertices now so the shape is remembered even without active acquisition.
    widget._config.crop.vertices = rect.tolist()
    save_config(widget._config)
    if not widget._shared_memory_segments:
        widget._log_queue.put(f"[{ts}] [viewer] Crop: acquisition not running.\n")
        return
    top = max(0, int(np.floor(rect[:, 0].min())))
    bottom = min(widget._image_depth_pixels, int(np.ceil(rect[:, 0].max())))
    left = max(0, int(np.floor(rect[:, 1].min())))
    right = min(widget._image_width_pixels, int(np.ceil(rect[:, 1].max())))
    if bottom <= top or right <= left:
        widget._log_queue.put(f"[{ts}] [viewer] Crop error: invalid region.\n")
        return
    widget.write_shared_memory_command(
        roi_top=top,
        roi_bottom=bottom,
        roi_left=left,
        roi_right=right,
        crop_update_flag=1,
        crop_reset_flag=0,
        crop_req_id=widget.next_command_request_id("crop"),
    )
    widget._crop_roi = (top, bottom, left, right)
    # Lock the shapes layer so the ROI can't be accidentally moved.
    set_crop_layer_editable(widget, False)
    controls.set_crop_button_state(widget, True)
    widget._log_queue.put(
        f"[{ts}] [viewer] Crop applied: rows {top}–{bottom}, cols {left}–{right}.\n"
    )


def reset_crop(widget: "EffusiveWidget") -> None:
    """Clear the active crop ROI and return to full-frame imaging.

    Sends a crop-reset command to MATLAB when acquisition is running, clears
    the stored ROI, and unlocks the shapes layer so a new rectangle can be
    drawn.

    Parameters
    ----------
    widget : EffusiveWidget
        Widget instance that owns the crop state and shared-memory command
        channel.

    Returns
    -------
    None
        This helper mutates widget crop state and optionally sends a
        shared-memory command.
    """
    if widget._shared_memory_segments:
        widget.write_shared_memory_command(
            crop_update_flag=0,
            crop_reset_flag=1,
            crop_req_id=widget.next_command_request_id("crop"),
        )
    widget._crop_roi = None
    # Don't update translate here, let the timer do it on the next frame
    # so data and translate change atomically and avoid a one-frame flicker.
    # Unlock the shapes layer so a new ROI can be drawn.
    set_crop_layer_editable(widget, True)
    controls.set_crop_button_state(widget, False)
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
    widget._log_queue.put(f"[{ts}] [viewer] Crop reset.\n")
