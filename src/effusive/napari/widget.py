"""Effusive napari control widget."""

from __future__ import annotations

import datetime
import queue
import struct
import subprocess
from pathlib import Path
from typing import Any, cast

import napari
import numpy as np
from napari.components.overlays import TextOverlay
from napari.layers import Image
from qtpy import QtGui
from qtpy.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer
from qtpy.QtGui import QFont
from qtpy.QtWidgets import (
    QWIDGETSIZE_MAX,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from effusive import config as cf_config
from effusive import shared_memory
from effusive.napari import controls
from effusive.napari import crop as crop_helpers
from effusive.napari import stack as stack_helpers
from effusive.napari import worker as worker_runtime
from effusive.napari.console import ConsoleHighlighter
from effusive.napari.debug import SharedMemoryDebugPanel
from effusive.napari.panels import (
    DataPanel,
    MetadataPanel,
    ProcessingPanel,
    ReconstructionPanel,
    SequencePanel,
    StackPanel,
    SystemPanel,
)
from effusive.napari.theme import (
    ACCENT_DARK,
    ACCENT_LIGHT,
    build_stylesheet,
    make_lucide_icon,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIMER_MS = 40
"""Frame polling interval (25 FPS max)."""

_WORKER = str(Path(__file__).parent.parent / "matlab_worker.py")
"""MATLAB worker script."""

# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------


class EffusiveWidget(QWidget):
    """Napari dock widget for Effusive acquisition control.

    Parameters
    ----------
    viewer : napari.Viewer
        The napari viewer instance to attach to.
    worker_cfg : dict, optional
        Optional configuration dictionary for the MATLAB worker subprocess.

    Attributes
    ----------
    viewer : napari.Viewer
        Napari viewer this widget is attached to.
    _config : EffusiveConfig
        Loaded user configuration; persisted to disk on close.
    """

    def __init__(self, viewer: napari.Viewer, worker_cfg: dict | None = None) -> None:
        super().__init__()
        self.viewer = viewer
        self._worker_cfg = worker_cfg or {}
        self._config = cf_config.load_config()

        # Acquisition state
        self._worker: subprocess.Popen | None = None
        self._shared_memory_segments: tuple = ()
        self._shared_memory_reader: shared_memory.ShmReader | None = None
        self._debug_dialog: SharedMemoryDebugPanel | None = None
        self._debug_dock: QDockWidget | None = None
        self._image_depth_pixels = 0
        self._image_width_pixels = 0
        self._scale_set = False
        self._last_frame = -1
        self._frame_display_offset = 0
        self._pending_display_frame_reset = False
        self._pending_stack_resume_frame_reset = False
        self._stack_completion_freeze_seen = False
        self._timer: QTimer | None = None
        self._log_queue: queue.SimpleQueue[str] = queue.SimpleQueue()
        self._log_file = None

        # Layer references (set by _setup_effusive_layers)
        self._bmode_layer = None
        self._pdi_layer = None
        self._crop_layer = None
        self._stack_preview_bmode_layer = None
        self._stack_preview_pdi_layer = None

        # RF snapshot and crop state
        self._crop_roi: tuple | None = None  # (top, bottom, left, right) pixel indices
        self._depth_step_mm: float = 1.0
        self._lateral_step_mm: float = 1.0
        self._depth_mm: float = 1.0  # z1 - z0, used for RF snapshot scale
        self._last_rf_counter: int = 0
        self._rf_layer = None
        self._waiting_for_snapshot: bool = False  # show_rf stays 1 until MATLAB acks

        # Pending cmd flag resets: list of (field_name, reset_value, min_frame_ctr).
        # Each entry is cleared once _last_frame >= min_frame_ctr, guaranteeing MATLAB
        # has processed at least one frame after the flag was written.
        self._pending_resets: list[tuple[str, int, int]] = []
        self._command_request_ids: dict[str, int] = {
            "freeze": 0,
            "save": 0,
            "svd": 0,
            "voltage": 0,
            "tx_aperture": 0,
            "rx_aperture": 0,
            "tgc": 0,
            "crop": 0,
            "stack": 0,
        }

        # Accordion UI bookkeeping
        self._accordion_buttons: list[tuple[QPushButton, str]] = []

        # Runtime flags
        self._run_button_state = "ready"
        self._save_active = False
        self._udp_server = None
        self._pending_udp_metadata: tuple[str, str, int] | None = None
        self._pending_udp_error: str | None = None
        self._pending_save_target: bool | None = None
        self._pending_save_deadline_s: float = 0.0
        self._freeze_active = False
        # Set by worker.forward_output (background thread) when a
        # "timeToNextAcq" warning is seen in MATLAB's console output; read by
        # runtime.handle_timer_tick (Qt main thread). A single float
        # assignment/read is safe under the GIL without a lock.
        self._last_timing_warning_monotonic: float | None = None

        # Crop mode state
        self._crop_mode_hook_layer_ids: set[int] = set()

        self.setMinimumWidth(460)
        self._restore_dock_size_policy()
        self._setup_ui()
        self._apply_theme()
        controls.refresh_control_locks(self)
        self._viewer_status_key = "cf_status_ready"
        self._viewer_status_overlay = self._create_viewer_text_overlay()
        self._viewer_info_overlay = self._create_viewer_text_overlay()
        self._viewer_info_overlay.color = "#e5e7eb"  # type: ignore
        self.viewer.canvas.overlays["cf_status"] = self._viewer_status_overlay
        self.viewer.canvas.overlays["cf_info"] = self._viewer_info_overlay
        self._set_viewer_status_overlay("cf_status_ready")
        self.viewer.events.theme.connect(self._on_theme_changed)
        self.viewer.layers.events.removed.connect(self._on_layer_removed)
        self.viewer.layers.selection.events.active.connect(
            self._on_active_layer_changed
        )
        QTimer.singleShot(0, self._restore_dock_size_policy)
        QTimer.singleShot(0, lambda: crop_helpers.configure_crop_layer_controls(self))

    def _restore_dock_size_policy(self) -> None:
        """Keep the widget filling napari's vertical dock area.

        Returns
        -------
        None
            The widget size policy is updated in place.
        """
        self.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding,
            QSizePolicy.Policy.Expanding,
        )

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _is_dark(self) -> bool:
        """Return whether the current napari theme is dark.

        Returns
        -------
        bool
            `True` when the viewer theme is not `"light"`.
        """
        return self.viewer.theme != "light"

    def _apply_theme(self) -> None:
        """Rebuild and apply the widget stylesheet from the current napari theme."""
        napari_bg: str | None = None
        try:
            from napari.utils.theme import get_theme

            t = get_theme(self.viewer.theme)
            napari_bg = t.background.as_hex()[:7]
        except Exception:
            pass
        self.setStyleSheet(build_stylesheet(self._is_dark(), napari_bg))

    def _on_theme_changed(self) -> None:
        """Respond to a napari theme-change event."""
        self._apply_theme()
        self._set_viewer_status_overlay(self._viewer_status_key)
        self._viewer_info_overlay.color = "#e5e7eb"  # type: ignore
        accent = ACCENT_DARK if self._is_dark() else ACCENT_LIGHT
        for btn, icon_name in self._accordion_buttons:
            btn.setIcon(make_lucide_icon(icon_name, accent))
        if hasattr(self, "_console_highlighter"):
            self._console_highlighter.set_theme(self._is_dark())
        self._system_panel.refresh_on_theme_change()
        controls.refresh_control_locks(self)

    # ------------------------------------------------------------------
    # Layer events
    # ------------------------------------------------------------------

    def _on_layer_removed(self, event) -> None:
        """Handle a napari layer-removed event."""
        if event.value is self._rf_layer:
            self._rf_layer = None
            self.viewer.canvas.grid.shape = (1, 2)
        if event.value is self._stack_preview_bmode_layer:
            self._stack_preview_bmode_layer = None
        if event.value is self._stack_preview_pdi_layer:
            self._stack_preview_pdi_layer = None

    def _on_active_layer_changed(self, event=None) -> None:
        """Respond to a napari active-layer-selection change."""
        _ = event
        crop_helpers.configure_crop_layer_controls(self)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _create_viewer_text_overlay(self) -> TextOverlay:
        """Create one bottom-left napari text overlay."""
        return TextOverlay(
            position="bottom_left",
            font_size=14,
            color="white",
            opacity=0.85,
            visible=False,
            text="",
        )

    def _refresh_viewer_overlay_text(self) -> None:
        """Refresh the neutral info overlay text."""
        self._viewer_info_overlay.visible = bool(self._viewer_info_overlay.text)

    def _set_viewer_status_overlay(self, status: str) -> None:
        """Set overlay text and colour from status style key.

        Parameters
        ----------
        status : str
            Status style key used to select text and color.

        Returns
        -------
        None
            This helper mutates overlay label state in place.
        """
        style_map = {
            "cf_status_ready": ("Ready", "#a8a8b5"),
            "cf_status_starting": ("Starting", "#6fb7ff"),
            "cf_status_running": ("Live view", "#44d17a"),
            "cf_status_paused": ("Paused", "#f0b04a"),
            "cf_status_recording": ("Recording", "#ff5a5a"),
            "cf_status_zstack": ("Z-stack", "#ff5a5a"),
            "cf_status_stack_initializing": ("Z-stack: Initializing", "#ff5a5a"),
            "cf_status_stack_moving": ("Z-stack: Moving", "#ff5a5a"),
            "cf_status_stack_settling": ("Z-stack: Settling", "#ff5a5a"),
            "cf_status_stack_accumulating": ("Z-stack: Accumulating", "#ff5a5a"),
            "cf_status_stack_finalizing": ("Z-stack: Finalizing", "#ff5a5a"),
            "cf_status_stack_completing": ("Z-stack: Completing", "#ff5a5a"),
            "cf_status_stack_aborting": ("Z-stack: Aborting", "#ff5a5a"),
            "cf_status_zstack_preview": ("Z-stack preview", "#f0b04a"),
            "cf_status_stopping": ("Stopping", "#a8a8b5"),
            "cf_status_stopped": ("Stopped", "#a8a8b5"),
            "cf_status_error": ("Error", "#ff6b6b"),
        }
        self._viewer_status_key = status
        display_text, color = style_map.get(status, ("Status", "#a8a8b5"))
        self._viewer_status_overlay.text = display_text
        self._viewer_status_overlay.color = color  # type: ignore
        self._viewer_status_overlay.visible = True

    def _set_viewer_info_overlay(self, text: str) -> None:
        """Update bottom-left time/frame overlay text.

        Parameters
        ----------
        text : str
            Overlay text. Empty text hides the overlay.
        """
        self._viewer_info_overlay.text = f"•  {text}" if text else ""
        self._refresh_viewer_overlay_text()

    def _setup_ui(self) -> None:
        """Build and attach the top-level layout to the widget."""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_header())

        # Wrap the accordion in a scroll area so switching to a tall panel
        # (e.g. Live view) doesn't cause the dock widget to grow and push
        # napari's Python console downward.  The scroll area is a direct
        # sibling of the header and log section in the root QVBoxLayout so it
        # inherits the full layout width — avoiding the horizontal overflow that
        # occurs when a nested content wrapper is used.
        accordion_scroll = QScrollArea()
        accordion_scroll.setWidget(self._make_accordion())
        accordion_scroll.setWidgetResizable(True)
        accordion_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        accordion_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        root.addWidget(accordion_scroll, stretch=1)

        root.addWidget(self._make_log_section())

    def _make_header(self) -> QWidget:
        """Build the title/status header widget."""
        from effusive.napari import commands as _cmds

        header = QWidget()
        header.setObjectName("cf_header")
        layout = QVBoxLayout(header)
        layout.setContentsMargins(16, 12, 16, 10)
        layout.setSpacing(2)

        # Title row: title + subtitle on left, transport buttons on right.
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title_row.setContentsMargins(0, 0, 0, 0)

        left_col = QVBoxLayout()
        left_col.setSpacing(2)
        title = QLabel("Effusive")
        title.setObjectName("cf_title")
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        title.setFont(font)
        left_col.addWidget(title)
        subtitle = QLabel("fUSI Acquisition")
        subtitle.setObjectName("cf_subtitle")
        left_col.addWidget(subtitle)
        title_row.addLayout(left_col, stretch=1)

        _BTN = 32
        is_dark = self._is_dark()
        accent_fg = "#1c1c27" if is_dark else "#ffffff"
        accent = ACCENT_DARK if is_dark else ACCENT_LIGHT

        self._run_button = QPushButton()
        self._run_button.setObjectName("run_btn_start")
        self._run_button.setFixedSize(_BTN, _BTN)
        self._run_button.setIconSize(QSize(18, 18))
        self._run_button.setIcon(make_lucide_icon("play", accent_fg, size=18))
        self._run_button.setToolTip("Start Effusive")
        self._run_button.clicked.connect(self._on_run_clicked)

        self._pause_button = QPushButton()
        self._pause_button.setCheckable(True)
        self._pause_button.setObjectName("pause_btn_idle")
        self._pause_button.setFixedSize(_BTN, _BTN)
        self._pause_button.setIconSize(QSize(18, 18))
        self._pause_button.setIcon(make_lucide_icon("pause", accent, size=18))
        self._pause_button.setEnabled(False)
        self._pause_button.setVisible(False)
        self._pause_button.setToolTip("Pause the acquisition.")
        self._pause_button.toggled.connect(lambda p: _cmds.handle_pause(self, p))

        btn_col = QHBoxLayout()
        btn_col.setSpacing(4)
        btn_col.setContentsMargins(0, 0, 0, 0)
        btn_col.addWidget(self._run_button)
        btn_col.addWidget(self._pause_button)
        title_row.addLayout(btn_col)
        layout.addLayout(title_row)

        return header

    def _make_accordion(self) -> QWidget:
        """Build the stacked accordion panel container."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Panels are created in order so later panels can reference earlier ones.
        self._system_panel = SystemPanel(self)
        self._metadata_panel = MetadataPanel(self)
        self._sequence_panel = SequencePanel(self)
        self._processing_panel = ProcessingPanel(self)
        self._reconstruction_panel = ReconstructionPanel(self)
        self._stack_panel = StackPanel(self)
        self._data_panel = DataPanel(self)
        self._metadata_panel.refresh_previews()

        panel_list = [
            self._system_panel,
            self._metadata_panel,
            self._sequence_panel,
            self._processing_panel,
            self._reconstruction_panel,
            self._stack_panel,
            self._data_panel,
        ]
        tab_entries = [
            ("System", "cpu"),
            ("Storage", "hard-drive"),
            ("Sequence", "audio-waveform"),
            ("Acquisition", "sliders-horizontal"),
            ("Reconstruction", "grid-3x3"),
            ("Z-stack", "layers"),
            ("Record", "aperture"),
        ]
        btns: list[QPushButton] = []
        accent = ACCENT_DARK if self._is_dark() else ACCENT_LIGHT

        for i, ((title, icon_name), panel) in enumerate(zip(tab_entries, panel_list)):
            btn = QPushButton(title)
            btn.setIcon(make_lucide_icon(icon_name, accent))
            btn.setIconSize(QSize(16, 16))
            btn.setObjectName("accordion_header")
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setMinimumHeight(36)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            layout.addWidget(btn)
            layout.addWidget(panel, stretch=100)
            panel.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            panel.setMinimumHeight(0)
            panel.setVisible(i == 0)
            btns.append(btn)
            self._accordion_buttons.append((btn, icon_name))
        layout.addStretch(1)

        panel_anims: dict[QWidget, QPropertyAnimation] = {}
        _ACCORDION_ANIMATION_DURATION_MS = 200  # ms

        def _animate_panel(
            panel: QWidget, start: int, end: int, *, hide_on_done: bool
        ) -> None:
            """Replace the panel's animation and ignore superseded completions."""
            previous = panel_anims.pop(panel, None)
            if previous is not None:
                previous.stop()
            anim = QPropertyAnimation(panel, b"maximumHeight")
            anim.setDuration(_ACCORDION_ANIMATION_DURATION_MS)
            anim.setStartValue(start)
            anim.setEndValue(end)
            anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
            panel_anims[panel] = anim

            def _on_done() -> None:
                """Apply completion only if this is still the panel's animation."""
                if panel_anims.get(panel) is not anim:
                    return
                del panel_anims[panel]
                if hide_on_done:
                    panel.hide()
                panel.setMaximumHeight(QWIDGETSIZE_MAX)

            anim.finished.connect(_on_done)
            anim.start()

        def _activate(idx: int) -> None:
            """Animate toward the latest button selection, not transient visibility."""
            # A collapsing panel remains visible, but its button is already unchecked.
            target = idx if btns[idx].isChecked() else -1
            available_h = max(container.height() - sum(b.height() for b in btns), 50)

            for j, (b, p) in enumerate(zip(btns, panel_list)):
                active = j == target
                b.blockSignals(True)
                b.setChecked(active)
                b.blockSignals(False)

                if active and (not p.isVisible() or p in panel_anims):
                    start = p.height() if p.isVisible() else 0
                    p.setMaximumHeight(start)
                    p.show()
                    _animate_panel(p, start, available_h, hide_on_done=False)
                elif not active and p.isVisible():
                    _animate_panel(p, p.height(), 0, hide_on_done=True)

        for i, btn in enumerate(btns):
            btn.clicked.connect(lambda _checked, i=i: _activate(i))

        return container

    def _make_log_section(self) -> QWidget:
        """Build the console log panel widget."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(2)

        hdr = QLabel("Console")
        hdr.setObjectName("cf_subtitle")
        layout.addWidget(hdr)

        self._log_text = QPlainTextEdit()
        self._log_text.setObjectName("log_panel")
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumBlockCount(2000)
        self._log_text.setFixedHeight(140)
        font = QFont("Monospace", 8)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._log_text.setFont(font)
        self._console_highlighter = ConsoleHighlighter(
            self._log_text.document(), self._is_dark()
        )
        layout.addWidget(self._log_text)

        return container

    # ------------------------------------------------------------------
    # Run / probe handlers
    # ------------------------------------------------------------------

    def _on_run_clicked(self) -> None:
        """Handle a click on the run/stop button."""
        if self._run_button_state == "ready":
            worker_runtime.start_acquisition(self, _WORKER, TIMER_MS)
        elif self._run_button_state == "running":
            worker_runtime.stop_acquisition(self)

    def open_debug_panel(self) -> None:
        """Open (or raise) the shared-memory debug panel.

        Added as a napari dock widget so it gets napari's own dock chrome
        (title bar, float/close controls), then immediately floated: napari's
        `add_dock_widget` has no floating option, and the panel is only useful
        detached from the main Effusive dock. napari's close button
        (rather than just hiding) deletes the underlying dock widget, so a
        stale reference here is rebuilt from scratch instead of reused.
        """
        if self._debug_dock is not None:
            try:
                self._debug_dock.show()
                self._debug_dock.raise_()
                self._debug_dock.activateWindow()
                return
            except RuntimeError:
                self._debug_dock = None
                self._debug_dialog = None

        self._debug_dialog = SharedMemoryDebugPanel(self)
        self._debug_dock = self.viewer.window.add_dock_widget(
            self._debug_dialog, name="Effusive Debug", area="right"
        )
        self._debug_dock.setFloating(True)
        self._debug_dock.resize(560, 720)

    # ------------------------------------------------------------------
    # Shared-memory command channel
    # ------------------------------------------------------------------

    def schedule_flag_reset(self, flag: str, value: int = 0) -> None:
        """Schedule a command flag reset once MATLAB has processed one more frame.

        Parameters
        ----------
        flag : str
            Name of the `cf_cmd` field to reset.
        value : int, default: 0
            Value to write when the reset fires.
        """
        self._pending_resets.append((flag, value, self._last_frame + 1))

    def write_shared_memory_command(self, **kwargs) -> None:
        """Write keyword field values into the `cf_cmd` shared-memory segment.

        Parameters
        ----------
        **kwargs
            Field names and values to write.

        Raises
        ------
        ValueError
            If any keyword argument is not a recognised `cf_cmd` field name.
        """
        if len(self._shared_memory_segments) < 5:
            return
        shm_cmd = self._shared_memory_segments[3]
        current = list(struct.unpack_from(shared_memory.CMD_FORMAT, shm_cmd.buf, 0))
        unknown_fields = sorted(
            k for k in kwargs if k not in shared_memory.CMD_FIELD_INDEX
        )
        if unknown_fields:
            raise ValueError(
                "Unsupported cf_cmd field(s): " + ", ".join(unknown_fields)
            )
        for k, v in kwargs.items():
            current[shared_memory.CMD_FIELD_INDEX[k]] = v
        struct.pack_into(shared_memory.CMD_FORMAT, shm_cmd.buf, 0, *current)

    def next_command_request_id(self, command_group: str) -> int:
        """Increment and return the request id for a command group.

        Parameters
        ----------
        command_group : str
            Name of the command group tracked in `_command_request_ids`.

        Returns
        -------
        int
            Updated request identifier in the range [1, 2^32-1].
        """
        if command_group not in self._command_request_ids:
            raise ValueError(f"Unsupported command group: {command_group}")
        next_id = (self._command_request_ids[command_group] + 1) % (2**32)
        if next_id == 0:
            next_id = 1
        self._command_request_ids[command_group] = next_id
        return next_id

    def reset_display_frame_counter(self, frame_counter: int) -> None:
        """Restart the visible frame counter from 1 on the current frame.

        Parameters
        ----------
        frame_counter : int
            Absolute shared-memory frame counter for the current frame.

        Returns
        -------
        None
            Updates the visible frame-counter offset in place.
        """
        self._frame_display_offset = max(int(frame_counter) - 1, 0)

    # ------------------------------------------------------------------
    # Layer management
    # ------------------------------------------------------------------

    def _setup_effusive_layers(self) -> None:
        """Create the standard layers, or recreate any that have been deleted."""
        nz = self._image_depth_pixels or 512
        nx = self._image_width_pixels or 512
        # Fill placeholders at each layer's own dB floor so they render as "empty"
        # (dark) rather than at 0.0, which now sits at the bright/peak end of the
        # dB colorbar.
        blank_bmode = np.full(
            (1, nz, nx), shared_memory.BMODE_CONTRAST_LIMITS[0], dtype=np.float32
        )
        blank_pdi = np.full(
            (1, nz, nx), shared_memory.PDI_CONTRAST_LIMITS[0], dtype=np.float32
        )
        scale = (
            [1.0, self._depth_step_mm, self._lateral_step_mm]
            if self._scale_set
            else None
        )
        restored = []

        if self._bmode_layer is None or self._bmode_layer not in self.viewer.layers:
            self._bmode_layer = cast(
                Image,
                self.viewer.add_image(
                    blank_bmode,
                    name="B-mode",
                    colormap="gray",
                    contrast_limits=list(shared_memory.BMODE_CONTRAST_LIMITS),
                    gamma=1.0,
                    units=(None, "mm", "mm"),
                ),
            )
            self._bmode_layer.colorbar.visible = True
            self._bmode_layer.locked = True
            if scale:
                cast(Any, self._bmode_layer).scale = tuple(scale)
            restored.append("B-mode")

        if self._pdi_layer is None or self._pdi_layer not in self.viewer.layers:
            self._pdi_layer = cast(
                Image,
                self.viewer.add_image(
                    blank_pdi,
                    name="Power Doppler",
                    colormap="inferno",
                    contrast_limits=list(shared_memory.PDI_CONTRAST_LIMITS),
                    gamma=1.0,
                    units=(None, "mm", "mm"),
                ),
            )
            self._pdi_layer.colorbar.visible = True
            self._pdi_layer.locked = True
            if scale:
                cast(Any, self._pdi_layer).scale = tuple(scale)
            restored.append("Power Doppler")

        if self._crop_layer is None or self._crop_layer not in self.viewer.layers:
            self._crop_layer = self.viewer.add_shapes(  # type: ignore
                data=[],
                name="Crop ROI",
                face_color=[0, 0, 0, 0],
                edge_color="red",
                edge_width=2,
                units=("mm", "mm"),
            )
            self._crop_layer.locked = True
            saved = self._config.crop.vertices
            if scale and cf_config.validate_crop_vertices(saved):
                try:
                    self._crop_layer.add_rectangles(
                        [np.array(saved)],
                        edge_color="red",
                        face_color=[0, 0, 0, 0],
                        edge_width=2,
                    )
                except Exception:
                    pass
            if scale:
                cast(Any, self._crop_layer).scale = tuple(scale[1:])
            restored.append("Crop ROI")

        crop_helpers.configure_crop_layer_controls(self)
        crop_helpers.set_crop_layer_editable(self, self._crop_roi is None)
        controls.set_crop_button_state(self, self._crop_roi is not None)

        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        if restored:
            self._log_queue.put(f"[{ts}] [viewer] Restored: {', '.join(restored)}.\n")
        else:
            self._log_queue.put(
                f"[{ts}] [viewer] All layers present — nothing to restore.\n"
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _finish_stop(self) -> None:
        """Delegate to worker_runtime.finish_stop from the main thread."""
        worker_runtime.finish_stop(self)

    def closeEvent(self, event: QtGui.QCloseEvent | None) -> None:  # ty: ignore[invalid-method-override]
        """Ensure cleanup happens when the widget is closed.

        Parameters
        ----------
        event : QtGui.QCloseEvent or None
            The Qt close event.
        """
        cf_config.update_config_from_widget(self)
        stack_helpers.close_motor_controller(self)
        worker_runtime.stop_acquisition(self, from_close=True)
        self.viewer.canvas.overlays.pop("cf_status", None)
        self.viewer.canvas.overlays.pop("cf_info", None)
        if event is not None:
            event.accept()
