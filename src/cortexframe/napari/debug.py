"""Shared-memory debug panel for the CortexFrame napari widget.

This module provides a diagnostic panel, opened as a floating napari dock
widget, that decodes and displays every `cf_*` shared-memory segment's current
values, so a developer can verify that the GUI is reading and writing the
values it believes it is. Opened via the "Open Debug Panel" button in the
System panel (see `CortexFrameWidget.open_debug_panel`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import QTimer, Qt
from qtpy.QtGui import QHideEvent, QShowEvent
from qtpy.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from cortexframe import shared_memory
from cortexframe.napari.theme import build_stylesheet

if TYPE_CHECKING:
    from cortexframe.napari.widget import CortexFrameWidget

_POLL_MS = 200
"""Debug popup refresh interval; slower than the frame timer since this is
diagnostic-only and does not need to track every frame."""

_STACK_STATUS_NAMES = {
    shared_memory.STACK_STATUS_IDLE: "IDLE",
    shared_memory.STACK_STATUS_INITIALIZING: "INITIALIZING",
    shared_memory.STACK_STATUS_MOVING_TO_SLICE: "MOVING_TO_SLICE",
    shared_memory.STACK_STATUS_SETTLING: "SETTLING",
    shared_memory.STACK_STATUS_ACCUMULATING: "ACCUMULATING",
    shared_memory.STACK_STATUS_FINALIZING_SLICE: "FINALIZING_SLICE",
    shared_memory.STACK_STATUS_COMPLETING: "COMPLETING",
    shared_memory.STACK_STATUS_ABORTING: "ABORTING",
    shared_memory.STACK_STATUS_ERROR: "ERROR",
}

_ACK_SUFFIX = "_ack_id"
_REQ_SUFFIX = "_req_id"


def _add_row(form: QFormLayout, label: str) -> QLabel:
    """Add a read-only value row to a form layout.

    Parameters
    ----------
    form : QFormLayout
        Form layout to append the row to.
    label : str
        Row label text.

    Returns
    -------
    QLabel
        The value label, to be updated on each poll.
    """
    value = QLabel("-")
    value.setObjectName("cf_info_value")
    value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    form.addRow(label + ":", value)
    return value


class SharedMemoryDebugPanel(QWidget):
    """Dock-widget content decoding every `cf_*` shared-memory segment live.

    Meant to be added via `viewer.window.add_dock_widget` (see
    `CortexFrameWidget.open_debug_panel`), which supplies the napari-styled
    dock chrome (title bar, float/close controls).

    Parameters
    ----------
    widget : CortexFrameWidget
        CortexFrame control widget owning the shared-memory reader to poll.
    """

    def __init__(self, widget: "CortexFrameWidget") -> None:
        super().__init__()
        self._widget = widget
        self._apply_theme()
        widget.viewer.events.theme.connect(self._apply_theme)

        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_MS)
        self._timer.timeout.connect(self._refresh)

        root = QVBoxLayout(self)
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        root.addWidget(self._status_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(8)
        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

        self._meta_values = self._add_group(
            content_layout,
            "Meta (cf_meta)",
            [
                "frame_counter",
                "nz",
                "nx",
                "z_start_mm",
                "z_end_mm",
                "x_start_mm",
                "x_end_mm",
                "runtime_flags",
                "save_active",
                "freeze_active",
                "ensemble_time_s",
            ],
        )

        self._cmd_values = self._add_group(
            content_layout, "Command (cf_cmd)", list(shared_memory.CMD_FIELDS)
        )

        self._ack_values = self._add_group(
            content_layout, "Acknowledgements (cf_ack)", list(shared_memory.ACK_FIELDS)
        )

        self._stack_values = self._add_group(
            content_layout,
            "Z-stack (cf_stack)",
            [
                "stack_active",
                "stack_error",
                "status_code",
                "current_slice",
                "total_slices",
                "target_position_um",
            ],
        )

        self._rf_values = self._add_group(
            content_layout,
            "RF snapshot (cf_rf)",
            [
                "rf_counter",
                "nsamples",
                "ncols",
            ],
        )

        self._image_values = self._add_group(
            content_layout,
            "Images (dB, decoded)",
            [
                "bmode_min",
                "bmode_max",
                "bmode_mean",
                "pdi_min",
                "pdi_max",
                "pdi_mean",
            ],
        )

        content_layout.addStretch()

    def _apply_theme(self, event: object = None) -> None:
        """Apply CortexFrame's stylesheet so this standalone window matches napari.

        As a top-level window (not a napari dock widget), this panel does not
        inherit any application-wide stylesheet, so it must build and set its
        own from the current napari theme, same as `CortexFrameWidget` does.

        Parameters
        ----------
        event : object, optional
            Unused; accepted so this can be connected directly to napari's
            `viewer.events.theme` signal.
        """
        is_dark = self._widget._is_dark()
        napari_bg: str | None = None
        try:
            from napari.utils.theme import get_theme

            t = get_theme(self._widget.viewer.theme)
            napari_bg = t.background.as_hex()[:7]
        except Exception:
            pass
        self.setStyleSheet(build_stylesheet(is_dark, napari_bg))

    def _add_group(
        self, parent_layout: QVBoxLayout, title: str, fields: list[str]
    ) -> dict[str, QLabel]:
        """Build a labeled group box of read-only value rows.

        Parameters
        ----------
        parent_layout : QVBoxLayout
            Layout to append the group box to.
        title : str
            Group box title.
        fields : list[str]
            Field names to create one row per.

        Returns
        -------
        dict[str, QLabel]
            Field name to value label mapping, for updates on each poll.
        """
        group = QGroupBox(title)
        form = QFormLayout(group)
        form.setSpacing(4)
        values = {field: _add_row(form, field) for field in fields}
        parent_layout.addWidget(group)
        return values

    def showEvent(self, a0: QShowEvent | None) -> None:
        """Start polling shared memory while the popup is visible.

        Parameters
        ----------
        a0 : QShowEvent, optional
            Qt show event, forwarded to the base implementation.
        """
        super().showEvent(a0)
        self._refresh()
        self._timer.start()

    def hideEvent(self, a0: QHideEvent | None) -> None:
        """Stop polling shared memory once the popup is hidden.

        Parameters
        ----------
        a0 : QHideEvent, optional
            Qt hide event, forwarded to the base implementation.
        """
        self._timer.stop()
        super().hideEvent(a0)

    def _refresh(self) -> None:
        """Poll the widget's shared-memory reader and update every value label."""
        reader = self._widget._shared_memory_reader
        if reader is None:
            self._status_label.setText(
                "No active acquisition: shared-memory segments are not open."
            )
            return
        self._status_label.setText("Live - polling every %d ms." % _POLL_MS)

        try:
            (
                frame_counter,
                nz,
                nx,
                z0,
                z1,
                x0,
                x1,
                runtime_flags,
                ensemble_time_s,
            ) = reader.read_meta()
        except Exception as exc:
            self._status_label.setText(f"Failed to read cf_meta: {exc}")
            return

        runtime_flags = int(runtime_flags)
        self._meta_values["frame_counter"].setText(str(frame_counter))
        self._meta_values["nz"].setText(str(nz))
        self._meta_values["nx"].setText(str(nx))
        self._meta_values["z_start_mm"].setText(f"{z0:.4f}")
        self._meta_values["z_end_mm"].setText(f"{z1:.4f}")
        self._meta_values["x_start_mm"].setText(f"{x0:.4f}")
        self._meta_values["x_end_mm"].setText(f"{x1:.4f}")
        self._meta_values["runtime_flags"].setText(f"0b{runtime_flags:08b}")
        self._meta_values["save_active"].setText(
            str(bool(runtime_flags & shared_memory.META_FLAG_SAVE_ACTIVE))
        )
        self._meta_values["freeze_active"].setText(
            str(bool(runtime_flags & shared_memory.META_FLAG_FREEZE_ACTIVE))
        )
        self._meta_values["ensemble_time_s"].setText(f"{ensemble_time_s:.6f}")

        try:
            cmd_values = reader.read_cmd()
        except Exception as exc:
            cmd_values = None
            self._status_label.setText(f"Failed to read cf_cmd: {exc}")
        if cmd_values is not None:
            for name, value in zip(shared_memory.CMD_FIELDS, cmd_values):
                self._cmd_values[name].setText(str(value))

        try:
            ack_values = reader.read_ack()
        except Exception:
            ack_values = None
        ack_by_name: dict[str, int] = {}
        if ack_values is not None:
            for name, value in zip(shared_memory.ACK_FIELDS, ack_values):
                ack_by_name[name] = value
                self._ack_values[name].setText(str(value))

        if cmd_values is not None and ack_values is not None:
            for name, value in zip(shared_memory.CMD_FIELDS, cmd_values):
                if not name.endswith(_REQ_SUFFIX):
                    continue
                ack_name = name[: -len(_REQ_SUFFIX)] + _ACK_SUFFIX
                ack_value = ack_by_name.get(ack_name)
                label = self._cmd_values[name]
                if ack_value is None:
                    continue
                suffix = " (pending)" if int(value) != int(ack_value) else " (acked)"
                label.setText(str(value) + suffix)

        try:
            stack_values = reader.read_stack_status()
        except Exception:
            stack_values = None
        if stack_values is not None:
            (
                stack_active,
                stack_error,
                status_code,
                current_slice,
                total_slices,
                target_position_um,
            ) = stack_values
            self._stack_values["stack_active"].setText(str(bool(stack_active)))
            self._stack_values["stack_error"].setText(str(bool(stack_error)))
            status_name = _STACK_STATUS_NAMES.get(status_code, str(status_code))
            self._stack_values["status_code"].setText(f"{status_code} ({status_name})")
            self._stack_values["current_slice"].setText(str(current_slice))
            self._stack_values["total_slices"].setText(str(total_slices))
            self._stack_values["target_position_um"].setText(str(target_position_um))

        try:
            rf_counter, nsamples, ncols = reader.read_rf_header()
        except Exception:
            rf_counter = nsamples = ncols = None
        if rf_counter is not None:
            self._rf_values["rf_counter"].setText(str(rf_counter))
            self._rf_values["nsamples"].setText(str(nsamples))
            self._rf_values["ncols"].setText(str(ncols))

        nz_int, nx_int = int(nz), int(nx)
        if nz_int > 0 and nx_int > 0:
            try:
                bmode = reader.read_bmode(nz_int, nx_int)
                self._image_values["bmode_min"].setText(f"{float(bmode.min()):.2f}")
                self._image_values["bmode_max"].setText(f"{float(bmode.max()):.2f}")
                self._image_values["bmode_mean"].setText(f"{float(bmode.mean()):.2f}")
            except Exception:
                pass
            try:
                pdi = reader.read_pdi(nz_int, nx_int)
                self._image_values["pdi_min"].setText(f"{float(pdi.min()):.2f}")
                self._image_values["pdi_max"].setText(f"{float(pdi.max()):.2f}")
                self._image_values["pdi_mean"].setText(f"{float(pdi.mean()):.2f}")
            except Exception:
                pass
