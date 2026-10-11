"""System panel for the Effusive napari widget."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from effusive import config as cf_config
from effusive.napari.panels.common import make_lock_hint
from effusive.napari.theme import make_lucide_icon

if TYPE_CHECKING:
    from effusive.napari.widget import EffusiveWidget


_PATH_STATUS_META = {
    "ok": {"icon": "circle-check", "dark": "#34d399", "light": "#047857"},
    "warning": {"icon": "triangle-alert", "dark": "#fbbf24", "light": "#b45309"},
    "error": {"icon": "circle-x", "dark": "#f87171", "light": "#b91c1c"},
}


class SystemPanel(QWidget):
    """System/control panel with startup toggles and configurable paths.

    Parameters
    ----------
    widget : EffusiveWidget
        Parent widget owning the config and viewer.
    """

    def __init__(self, widget: "EffusiveWidget") -> None:
        """Initialise the system panel.

        Parameters
        ----------
        widget : EffusiveWidget
            Parent widget owning shared state and config.
        """
        super().__init__()
        self._widget = widget
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build system-panel controls and layouts."""
        widget = self._widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        self._system_lock_hint = make_lock_hint(
            "Define subject and session in Storage before starting Effusive in BIDS mode."
        )
        layout.addWidget(self._system_lock_hint)

        startup_group = QGroupBox("Startup options")
        startup_form = QFormLayout(startup_group)
        startup_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        startup_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        startup_form.setSpacing(6)
        startup_form.setContentsMargins(8, 12, 8, 8)

        self._simulate_checkbox = QCheckBox("Use simulation mode")
        self._simulate_checkbox.setChecked(widget._config.system.simulate_mode)
        self._simulate_checkbox.setToolTip(
            "Start MATLAB worker with Verasonics simulation enabled."
        )
        self._simulate_checkbox.toggled.connect(self._on_simulate_mode_changed)
        startup_form.addRow("Acquisition:", self._simulate_checkbox)

        self._udp_enable_checkbox = QCheckBox("Enable UDP control server")
        self._udp_enable_checkbox.setChecked(widget._config.system.udp_control_enabled)
        self._udp_enable_checkbox.setToolTip(
            "Run the mpep-compatible UDP control server in napari while acquisition is active."
        )
        self._udp_enable_checkbox.toggled.connect(self._on_udp_enable_changed)
        startup_form.addRow("UDP control:", self._udp_enable_checkbox)

        self._udp_port_spinbox = QSpinBox()
        self._udp_port_spinbox.setRange(1, 65535)
        self._udp_port_spinbox.setValue(int(widget._config.system.udp_control_port))
        self._udp_port_spinbox.setToolTip(
            "UDP port for the napari-side control server."
        )
        self._udp_port_spinbox.valueChanged.connect(self._on_udp_port_changed)
        startup_form.addRow("UDP port:", self._udp_port_spinbox)
        layout.addWidget(startup_group)

        paths_group = QGroupBox("System paths")
        paths_form = QFormLayout(paths_group)
        paths_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        paths_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        paths_form.setSpacing(6)
        paths_form.setContentsMargins(8, 12, 8, 8)

        self._matlab_root_edit, self._matlab_root_status_icon = self._make_path_row(
            paths_form,
            "MATLAB:",
            "Optional MATLAB install root (e.g. /usr/local/MATLAB/R2024a). Leave empty to use worker default or environment.",
            "MATLAB installation root (e.g. /usr/local/MATLAB/R2024a)",
            self._initial_path_value(
                config_value=widget._config.system.matlab_root,
                env_key="MATLAB_ROOT",
            ),
            self._on_matlab_root_changed,
        )
        self._vantage_root_edit, self._vantage_root_status_icon = self._make_path_row(
            paths_form,
            "Vantage:",
            "Vantage/Verasonics installation root (VERASONICS_VPF_ROOT).",
            "Vantage/Verasonics root (VERASONICS_VPF_ROOT)",
            self._initial_path_value(
                config_value=widget._config.system.vantage_root,
                env_key="VERASONICS_VPF_ROOT",
            ),
            self._on_vantage_root_changed,
        )
        self._echoframe_mex_root_edit, self._echoframe_mex_root_status_icon = (
            self._make_path_row(
                paths_form,
                "EchoFrame:",
                "Directory containing echoframe_mex.* (ECHOFRAME_MEX_ROOT).",
                "EchoFrame MEX root (ECHOFRAME_MEX_ROOT)",
                self._initial_path_value(
                    config_value=widget._config.system.echoframe_mex_root,
                    env_key="ECHOFRAME_MEX_ROOT",
                ),
                self._on_echoframe_mex_root_changed,
            )
        )
        layout.addWidget(paths_group)
        self._refresh_path_statuses()

        self._restore_button = QPushButton("Restore Layers")
        self._restore_button.clicked.connect(widget._setup_effusive_layers)
        layout.addWidget(self._restore_button)

        self._debug_button = QPushButton("Open Debug Panel")
        self._debug_button.setToolTip(
            "Show decoded shared-memory buffer values for debugging. Available "
            "while Effusive is running."
        )
        self._debug_button.setEnabled(False)
        self._debug_button.clicked.connect(widget.open_debug_panel)
        layout.addWidget(self._debug_button)

        layout.addStretch()

    def _make_path_row(
        self,
        form: QFormLayout,
        label: str,
        tooltip: str,
        placeholder: str,
        value: str,
        on_change,
    ) -> tuple[QLineEdit, QLabel]:
        """Create one editable path row with browse button.

        Parameters
        ----------
        form : QFormLayout
            Destination form layout.
        label : str
            Row label.
        tooltip : str
            Expected path description.
        placeholder : str
            Placeholder text describing the expected value.
        value : str
            Initial field value.
        on_change : callable
            Slot called on text change.

        Returns
        -------
        tuple of (QLineEdit, QLabel)
            The path editor and status icon label.
        """
        edit = QLineEdit(value)
        edit.setPlaceholderText(placeholder)
        edit.setToolTip(tooltip)
        edit.textChanged.connect(on_change)

        browse_button = QPushButton("Browse")
        browse_button.setToolTip(tooltip)
        browse_button.clicked.connect(lambda: self._browse_path(edit))

        status_icon = QLabel()
        status_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_icon.setFixedWidth(18)

        row = QHBoxLayout()
        row.addWidget(edit)
        row.addWidget(browse_button)
        row.addWidget(status_icon)

        form.addRow(label, row)
        return edit, status_icon

    def _initial_path_value(
        self,
        config_value: str,
        env_key: str,
    ) -> str:
        """Resolve the startup value shown in a system-path editor.

        Parameters
        ----------
        config_value : str
            Persisted config value.
        env_key : str
            Environment-variable fallback key.

        Returns
        -------
        str
            Config value when set; otherwise environment value.
        """
        cfg = config_value.strip()
        if cfg:
            return cfg
        return os.environ.get(env_key, "").strip()

    def _browse_path(self, target_edit: QLineEdit) -> None:
        """Open a directory picker for a path row.

        Parameters
        ----------
        target_edit : QLineEdit
            Path field to populate with the selected directory.
        """
        current = target_edit.text().strip()
        start_dir = current or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "Select directory", start_dir)
        if selected:
            target_edit.setText(selected)

    # ------------------------------------------------------------------
    # Lock control
    # ------------------------------------------------------------------

    def lock_for_run(self, locked: bool) -> None:
        """Enable or disable the startup-only config controls.

        Parameters
        ----------
        locked : bool
            Whether the controls should be locked (disabled).
        """
        self._simulate_checkbox.setEnabled(not locked)
        self._udp_enable_checkbox.setEnabled(not locked)
        self._udp_port_spinbox.setEnabled(not locked)
        self._matlab_root_edit.setEnabled(not locked)
        self._vantage_root_edit.setEnabled(not locked)
        self._echoframe_mex_root_edit.setEnabled(not locked)

    def set_debug_button_enabled(self, enabled: bool) -> None:
        """Enable or disable the debug-panel button.

        Parameters
        ----------
        enabled : bool
            Whether the debug panel should be reachable, i.e. whether
            shared-memory segments are currently open.
        """
        self._debug_button.setEnabled(enabled)

    def set_metadata_gate_locked(self, locked: bool) -> None:
        """Apply or clear the pre-start metadata gate on system controls.

        Parameters
        ----------
        locked : bool
            Whether the system controls should be disabled until session
            metadata is valid.

        Returns
        -------
        None
            This helper mutates widget enabled states in place.
        """
        if self._widget._run_button_state == "ready":
            self._simulate_checkbox.setEnabled(not locked)
            self._udp_enable_checkbox.setEnabled(not locked)
            self._udp_port_spinbox.setEnabled(not locked)
            self._matlab_root_edit.setEnabled(not locked)
            self._vantage_root_edit.setEnabled(not locked)
            self._echoframe_mex_root_edit.setEnabled(not locked)

    def refresh_on_theme_change(self) -> None:
        """Refresh theme-dependent state after a theme change."""
        self._refresh_path_statuses()

    def _refresh_path_statuses(self) -> None:
        """Validate path fields and update status icons and field styles."""
        self._apply_path_status(
            self._matlab_root_edit,
            self._matlab_root_status_icon,
            *self._validate_matlab_root(self._matlab_root_edit.text()),
        )
        self._apply_path_status(
            self._vantage_root_edit,
            self._vantage_root_status_icon,
            *self._validate_vantage_root(self._vantage_root_edit.text()),
        )
        self._apply_path_status(
            self._echoframe_mex_root_edit,
            self._echoframe_mex_root_status_icon,
            *self._validate_echoframe_mex_root(self._echoframe_mex_root_edit.text()),
        )

    def _apply_path_status(
        self,
        edit: QLineEdit,
        icon_label: QLabel,
        status: str,
        detail: str,
    ) -> None:
        """Apply visual state for one path field.

        Parameters
        ----------
        edit : QLineEdit
            Path editor to style.
        icon_label : QLabel
            Label showing status icon.
        status : str
            Status key (`ok`, `warning`, or `error`).
        detail : str
            Tooltip detail shown on the icon.
        """
        is_dark = self._widget._is_dark()
        status_meta = _PATH_STATUS_META[status]
        color = status_meta["dark"] if is_dark else status_meta["light"]
        icon = make_lucide_icon(status_meta["icon"], color)
        icon_label.setPixmap(icon.pixmap(14, 14))
        icon_label.setToolTip(detail)

        border = {
            "ok": "#22c55e",
            "warning": "#f59e0b",
            "error": "#ef4444",
        }[status]
        edit.setStyleSheet(f"border: 1px solid {border}; border-radius: 4px;")

    def _validate_matlab_root(self, value: str) -> tuple[str, str]:
        """Validate MATLAB root path.

        Parameters
        ----------
        value : str
            Raw field value.

        Returns
        -------
        tuple of str
            Status and detail text.
        """
        path = Path(value.strip()).expanduser() if value.strip() else None
        if path is None:
            return "warning", "Not set. Set MATLAB_ROOT or choose a MATLAB root."
        if not path.is_dir():
            return "error", "Path does not exist or is not a directory."
        matlab_bin = path / "bin" / ("matlab.exe" if os.name == "nt" else "matlab")
        if not matlab_bin.is_file():
            return "error", f"Missing MATLAB binary: {matlab_bin}"
        return "ok", "MATLAB root looks valid."

    def _validate_vantage_root(self, value: str) -> tuple[str, str]:
        """Validate Vantage root path.

        Parameters
        ----------
        value : str
            Raw field value.

        Returns
        -------
        tuple of str
            Status and detail text.
        """
        path = Path(value.strip()).expanduser() if value.strip() else None
        if path is None:
            return "warning", "Not set. Set VERASONICS_VPF_ROOT or choose a root."
        if not path.is_dir():
            return "error", "Path does not exist or is not a directory."
        vsx_file = path / "VSX.m"
        if not vsx_file.is_file():
            return "error", f"Missing expected file: {vsx_file}"
        return "ok", "Vantage root contains VSX.m."

    def _validate_echoframe_mex_root(self, value: str) -> tuple[str, str]:
        """Validate EchoFrame MEX-root path.

        Parameters
        ----------
        value : str
            Raw field value.

        Returns
        -------
        tuple of str
            Status and detail text.
        """
        path = Path(value.strip()).expanduser() if value.strip() else None
        if path is None:
            return "warning", "Not set. Set ECHOFRAME_MEX_ROOT or choose a directory."
        if not path.is_dir():
            return "error", "Path does not exist or is not a directory."

        echoframe_mex_candidates = list(path.glob("echoframe_mex.*"))
        if not echoframe_mex_candidates:
            return "error", "Missing echoframe_mex.* in this directory."

        return "ok", "EchoFrame MEX root contains echoframe_mex."

    def _on_simulate_mode_changed(self, checked: bool) -> None:
        """Persist a startup simulation-mode toggle.

        Parameters
        ----------
        checked : bool
            Whether simulation mode should be enabled.
        """
        self._widget._config.system.simulate_mode = bool(checked)
        cf_config.save_config(self._widget._config)

    def _on_udp_enable_changed(self, checked: bool) -> None:
        """Persist a startup UDP-control toggle.

        Parameters
        ----------
        checked : bool
            Whether UDP control should be enabled.
        """
        self._widget._config.system.udp_control_enabled = bool(checked)
        cf_config.save_config(self._widget._config)

    def _on_udp_port_changed(self, value: int) -> None:
        """Persist the UDP-control port value.

        Parameters
        ----------
        value : int
            UDP port number.
        """
        self._widget._config.system.udp_control_port = int(value)
        cf_config.save_config(self._widget._config)

    def _on_matlab_root_changed(self, text: str) -> None:
        """Persist the MATLAB root override.

        Parameters
        ----------
        text : str
            New path value.
        """
        self._widget._config.system.matlab_root = text.strip()
        cf_config.save_config(self._widget._config)
        self._refresh_path_statuses()

    def _on_vantage_root_changed(self, text: str) -> None:
        """Persist the Vantage root override.

        Parameters
        ----------
        text : str
            New path value.
        """
        self._widget._config.system.vantage_root = text.strip()
        cf_config.save_config(self._widget._config)
        self._refresh_path_statuses()

    def _on_echoframe_mex_root_changed(self, text: str) -> None:
        """Persist the EchoFrame MEX-root override.

        Parameters
        ----------
        text : str
            New path value.
        """
        self._widget._config.system.echoframe_mex_root = text.strip()
        cf_config.save_config(self._widget._config)
        self._refresh_path_statuses()
