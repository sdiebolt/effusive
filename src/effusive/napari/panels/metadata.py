"""Recording/session metadata panel for the Effusive napari widget."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from shutil import disk_usage
from typing import TYPE_CHECKING

from qtpy.QtCore import QRegularExpression, QTimer
from qtpy.QtGui import QRegularExpressionValidator
from qtpy.QtWidgets import (
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

from effusive import bids
from effusive.napari import controls
from effusive.napari.components import ElidedPathLabel
from effusive.napari.panels.common import make_lock_hint

if TYPE_CHECKING:
    from effusive.napari.widget import EffusiveWidget


_STORAGE_SPACE_WARNING_BYTES = 100 * 1024**3
_STORAGE_SPACE_OK_BYTES = 500 * 1024**3


def _resolve_existing_storage_path(path_text: str) -> Path | None:
    """Resolve a storage path to the nearest existing directory for disk checks.

    Parameters
    ----------
    path_text : str
        Raw path text from the storage field.

    Returns
    -------
    Path or None
        Existing directory to probe with `disk_usage`, or `None` when no
        suitable parent exists.
    """
    candidate = Path(path_text).expanduser()
    for current in (candidate, *candidate.parents):
        if current.exists() and current.is_dir():
            return current
    return None


def _format_bytes(num_bytes: int) -> str:
    """Format a byte count for compact UI display.

    Parameters
    ----------
    num_bytes : int
        Byte count to format.

    Returns
    -------
    str
        Human-readable size string.
    """
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if value < 1024.0 or unit == "PB":
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{num_bytes} B"


def _storage_space_style(num_free_bytes: int | None) -> str:
    """Return a compact stylesheet for the storage-space indicator.

    Parameters
    ----------
    num_free_bytes : int or None
        Free space in bytes, or `None` when no status is available.

    Returns
    -------
    str
        Qt stylesheet snippet for the indicator label.
    """
    base_style = "padding: 2px 6px; border-radius: 8px; font-weight: 600;"
    if num_free_bytes is None:
        return f"{base_style}"
    if num_free_bytes < _STORAGE_SPACE_WARNING_BYTES:
        return f"{base_style} color: #b91c1c; background: rgba(248, 113, 113, 0.16);"
    if num_free_bytes < _STORAGE_SPACE_OK_BYTES:
        return f"{base_style} color: #b45309; background: rgba(251, 191, 36, 0.18);"
    return f"{base_style} color: #047857; background: rgba(52, 211, 153, 0.16);"


class MetadataPanel(QWidget):
    """Session and recording metadata controls.

    Parameters
    ----------
    widget : EffusiveWidget
        Parent widget owning the shared config and sibling panels.
    """

    def __init__(self, widget: "EffusiveWidget") -> None:
        super().__init__()
        self._widget = widget
        self._recording_widgets: list[QWidget] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        widget = self._widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        storage_form = QFormLayout()
        storage_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        storage_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        storage_form.setSpacing(6)
        self._storage_edit = QLineEdit(
            widget._worker_cfg.get("storagePath", widget._config.system.storage_path)
        )
        self._storage_edit.setPlaceholderText("Storage root directory")
        self._storage_edit.textChanged.connect(
            lambda text: setattr(widget._config.system, "storage_path", text.strip())
        )
        self._storage_edit.textChanged.connect(lambda _: self.refresh_previews())
        self._storage_edit.textChanged.connect(
            lambda _: self.schedule_storage_space_indicator_refresh()
        )
        self._storage_browse_button = QPushButton("Browse")
        self._storage_browse_button.clicked.connect(self._browse_storage_path)
        self._storage_space_label = QLabel()
        self._storage_space_label.setObjectName("cf_info_value")
        self._storage_space_label.setToolTip(
            "Available space on the disk containing the storage root."
        )
        self._storage_space_label.setStyleSheet(_storage_space_style(None))
        storage_row = QHBoxLayout()
        storage_row.addWidget(self._storage_edit)
        storage_row.addWidget(self._storage_browse_button)
        storage_row.addWidget(self._storage_space_label)
        storage_form.addRow("Storage:", storage_row)

        self._session_preview_label = ElidedPathLabel()
        self._session_preview_label.setObjectName("cf_info_value")
        storage_form.addRow("Runtime dir:", self._session_preview_label)

        self._storage_collision_label = QLabel("")
        self._storage_collision_label.setObjectName("cf_info_value")
        self._storage_collision_label.setStyleSheet("color: #d14343; font-weight: 700;")
        self._storage_collision_label.setWordWrap(True)
        storage_form.addRow("", self._storage_collision_label)
        layout.addLayout(storage_form)

        self._storage_space_refresh_timer = QTimer(self)
        self._storage_space_refresh_timer.setSingleShot(True)
        self._storage_space_refresh_timer.setInterval(250)
        self._storage_space_refresh_timer.timeout.connect(
            self.refresh_storage_space_indicator
        )

        self._storage_space_timer = QTimer(self)
        self._storage_space_timer.setInterval(5000)
        self._storage_space_timer.timeout.connect(self.refresh_storage_space_indicator)
        self._storage_space_timer.start()

        self._metadata_lock_hint = make_lock_hint(
            "Session metadata is locked while Effusive is running."
        )
        layout.addWidget(self._metadata_lock_hint)

        label_validator = QRegularExpressionValidator(
            QRegularExpression(r"[A-Za-z0-9]*")
        )

        recording_group = QGroupBox("Recording")
        recording_form = QFormLayout(recording_group)
        recording_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        recording_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        recording_form.setSpacing(6)
        recording_form.setContentsMargins(8, 12, 8, 8)

        self._subject_edit = QLineEdit(widget._config.bids.subject)
        self._subject_edit.setValidator(label_validator)
        self._subject_edit.setToolTip("Required before recording.")
        self._subject_edit.textChanged.connect(lambda _: self._on_metadata_changed())
        recording_form.addRow("Subject:", self._subject_edit)
        self._recording_widgets.append(self._subject_edit)

        default_session = widget._config.bids.session or date.today().strftime("%Y%m%d")
        self._session_edit = QLineEdit(default_session)
        self._session_edit.setValidator(label_validator)
        self._session_edit.setToolTip("Required before recording.")
        self._session_edit.textChanged.connect(lambda _: self._on_metadata_changed())
        recording_form.addRow("Session:", self._session_edit)
        self._recording_widgets.append(self._session_edit)

        self._task_edit = QLineEdit(widget._config.bids.task)
        self._task_edit.setValidator(label_validator)
        self._task_edit.setToolTip("Required for regular fUSI recordings in BIDS mode.")
        self._task_edit.textChanged.connect(lambda _: self._on_metadata_changed())
        recording_form.addRow("Task:", self._task_edit)
        self._recording_widgets.append(self._task_edit)

        self._acq_edit = QLineEdit(widget._config.bids.acq)
        self._acq_edit.setValidator(label_validator)
        self._acq_edit.setToolTip("Optional acquisition label.")
        self._acq_edit.textChanged.connect(lambda _: self._on_metadata_changed())
        recording_form.addRow("Acquisition:", self._acq_edit)
        self._recording_widgets.append(self._acq_edit)

        self._proc_edit = QLineEdit(widget._config.bids.proc)
        self._proc_edit.setValidator(label_validator)
        self._proc_edit.setToolTip("Optional processing label.")
        self._proc_edit.textChanged.connect(lambda _: self._on_metadata_changed())
        recording_form.addRow("Processing:", self._proc_edit)
        self._recording_widgets.append(self._proc_edit)

        run_row = QHBoxLayout()
        self._run_spinbox = QSpinBox()
        self._run_spinbox.setRange(1, 9999)
        self._run_spinbox.setValue(max(1, int(widget._config.bids.run)))
        self._run_spinbox.valueChanged.connect(lambda _: self._on_metadata_changed())
        run_row.addWidget(self._run_spinbox)
        recording_form.addRow("Run:", run_row)
        self._recording_widgets.append(self._run_spinbox)

        self._fusi_row_label = QLabel("fUSI path(s):")
        self._fusi_preview_label = ElidedPathLabel()
        self._fusi_preview_label.setObjectName("cf_info_value")
        recording_form.addRow(self._fusi_row_label, self._fusi_preview_label)

        self._angio_row_label = QLabel("Z-stack path(s):")
        self._angio_preview_label = ElidedPathLabel()
        self._angio_preview_label.setObjectName("cf_info_value")
        recording_form.addRow(self._angio_row_label, self._angio_preview_label)

        layout.addWidget(recording_group)
        layout.addStretch()

        self._set_bids_widget_enabled_states()
        self.refresh_storage_space_indicator()
        self._on_metadata_changed()

    def _set_bids_widget_enabled_states(self) -> None:
        """Enable or disable BIDS-specific widgets from current mode/lock state.

        Returns
        -------
        None
            This helper mutates widget enabled states in place.
        """
        bids_mode = True

        self._subject_edit.setEnabled(True)
        self._session_edit.setEnabled(True)

        self._task_edit.setEnabled(bids_mode)
        self._acq_edit.setEnabled(bids_mode)
        self._proc_edit.setEnabled(bids_mode)
        self._run_spinbox.setEnabled(True)

    def _browse_storage_path(self) -> None:
        """Open a directory picker and write the chosen path into the storage field."""
        start = self._storage_edit.text().strip() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Select Storage Folder", start)
        if folder:
            self._storage_edit.setText(folder)
            self.refresh_storage_space_indicator()

    def schedule_storage_space_indicator_refresh(self) -> None:
        """Debounce storage-space refreshes while the storage path is being edited.

        Returns
        -------
        None
            This helper restarts the debounce timer in place.
        """
        self._storage_space_refresh_timer.start()

    def refresh_storage_space_indicator(self) -> None:
        """Refresh the free-space indicator for the current storage root.

        Returns
        -------
        None
            This helper updates the storage-space label in place.
        """
        storage_root = self._storage_edit.text().strip()
        if not storage_root:
            self._storage_space_label.setText("—")
            self._storage_space_label.setStyleSheet(_storage_space_style(None))
            self._storage_space_label.setToolTip(
                "Choose a storage root to show available disk space."
            )
            return

        resolved = _resolve_existing_storage_path(storage_root)
        if resolved is None:
            self._storage_space_label.setText("?")
            self._storage_space_label.setStyleSheet(_storage_space_style(None))
            self._storage_space_label.setToolTip(
                "No existing parent directory is available to inspect disk space."
            )
            return

        usage = disk_usage(resolved)
        free_text = f"{_format_bytes(usage.free)} free"
        self._storage_space_label.setText(free_text)
        self._storage_space_label.setStyleSheet(_storage_space_style(usage.free))
        self._storage_space_label.setToolTip(
            "\n".join(
                [
                    f"Disk for: {resolved}",
                    f"Free: {_format_bytes(usage.free)}",
                    f"Used: {_format_bytes(usage.used)}",
                    f"Total: {_format_bytes(usage.total)}",
                ]
            )
        )

    def lock_session_fields(self, locked: bool) -> None:
        """Lock or unlock the session-scoped metadata fields.

        Parameters
        ----------
        locked : bool
            Whether session fields should be disabled.

        Returns
        -------
        None
            This helper mutates widget enabled states in place.
        """
        _ = locked
        self._set_bids_widget_enabled_states()
        startup_only_enabled = self._widget._run_button_state == "ready"
        self._storage_edit.setEnabled(startup_only_enabled)
        self._storage_browse_button.setEnabled(startup_only_enabled)
        self.refresh_storage_space_indicator()

    def lock_recording_fields(self, locked: bool) -> None:
        """Lock or unlock the recording-scoped metadata fields.

        Parameters
        ----------
        locked : bool
            Whether recording fields should be disabled.

        Returns
        -------
        None
            This helper mutates widget enabled states in place.
        """
        bids_mode = True
        recording_enabled = not locked
        self._subject_edit.setEnabled(recording_enabled)
        self._session_edit.setEnabled(recording_enabled)
        self._task_edit.setEnabled(bids_mode and recording_enabled)
        self._acq_edit.setEnabled(bids_mode and recording_enabled)
        self._proc_edit.setEnabled(bids_mode and recording_enabled)
        self._run_spinbox.setEnabled(recording_enabled)

    def _on_metadata_changed(self) -> None:
        """Persist metadata values and refresh dependent previews and locks.

        Returns
        -------
        None
            This helper mutates config fields in place.
        """
        cfg = self._widget._config.bids
        cfg.subject = self._subject_edit.text().strip()
        cfg.session = self._session_edit.text().strip()
        cfg.task = self._task_edit.text().strip()
        cfg.acq = self._acq_edit.text().strip()
        cfg.proc = self._proc_edit.text().strip()
        cfg.run = self._run_spinbox.value()

        self._set_bids_widget_enabled_states()
        self.refresh_previews()
        if hasattr(self._widget, "_metadata_panel"):
            controls.refresh_control_locks(self._widget)

    def refresh_previews(self) -> None:
        """Recompute session, fUSI, and z-stack previews.

        Returns
        -------
        None
            This helper updates preview labels in place.
        """
        storage_root = self._storage_edit.text().strip()
        if not storage_root:
            empty_message = "Choose a storage root to preview output paths."
            self._session_preview_label.set_full_text(empty_message)
            self._fusi_preview_label.set_full_text(empty_message)
            self._angio_preview_label.set_full_text(empty_message)
            self._storage_collision_label.setText("")
            if hasattr(self._widget, "_data_panel"):
                self._widget._data_panel.set_record_preview(empty_message)
                self._widget._data_panel.set_record_collision_warning("")
            if hasattr(self._widget, "_stack_panel"):
                self._widget._stack_panel.set_angio_preview(empty_message)
                self._widget._stack_panel.set_angio_collision_warning("")
            return

        session_preview, fusi_preview, angio_preview = self._build_bids_previews(
            Path(storage_root)
        )

        self._session_preview_label.set_full_text(session_preview)
        self._fusi_preview_label.set_full_text(fusi_preview)
        self._angio_preview_label.set_full_text(angio_preview)

        collision_style = "border: 1px solid #d14343; background: rgba(209,67,67,0.08);"
        subject_empty = not bool(self._subject_edit.text().strip())
        session_empty = not bool(self._session_edit.text().strip())

        self._subject_edit.setStyleSheet(collision_style if subject_empty else "")
        self._session_edit.setStyleSheet(collision_style if session_empty else "")
        self._task_edit.setStyleSheet("")
        self._acq_edit.setStyleSheet("")
        self._proc_edit.setStyleSheet("")
        self._run_spinbox.setStyleSheet("")

        fusi_collision = False
        angio_collision = False
        try:
            fusi_collision = bids.check_bids_run_collision(
                Path(storage_root),
                datatype=bids.FUSI_DATATYPE,
                subject=self._subject_edit.text().strip(),
                session=self._session_edit.text().strip(),
                task=self._task_edit.text().strip(),
                acq=self._acq_edit.text().strip(),
                run=self._run_spinbox.value(),
                proc=self._proc_edit.text().strip(),
            )
        except ValueError:
            fusi_collision = False

        try:
            angio_collision = bids.check_bids_run_collision(
                Path(storage_root),
                datatype=bids.ANGIO_DATATYPE,
                subject=self._subject_edit.text().strip(),
                session=self._session_edit.text().strip(),
                task=self._task_edit.text().strip(),
                acq=self._acq_edit.text().strip(),
                run=self._run_spinbox.value(),
                proc=self._proc_edit.text().strip(),
            )
        except ValueError:
            angio_collision = False

        self._storage_collision_label.setText("")

        if hasattr(self._widget, "_data_panel"):
            self._widget._data_panel.set_record_collision_warning(
                "Path already exists for this entity set. Change the storage metadata."
                if fusi_collision
                else ""
            )
        if hasattr(self._widget, "_stack_panel"):
            self._widget._stack_panel.set_angio_collision_warning(
                "Path already exists for this entity set. Change the storage metadata."
                if angio_collision
                else ""
            )

        fusi_invalid = False
        angio_invalid = False
        try:
            bids.validate_bids_entities(
                datatype=bids.FUSI_DATATYPE,
                subject=self._subject_edit.text().strip(),
                session=self._session_edit.text().strip(),
                task=self._task_edit.text().strip(),
                acq=self._acq_edit.text().strip(),
                proc=self._proc_edit.text().strip(),
            )
        except ValueError:
            fusi_invalid = True

        try:
            bids.validate_bids_entities(
                datatype=bids.ANGIO_DATATYPE,
                subject=self._subject_edit.text().strip(),
                session=self._session_edit.text().strip(),
                task=self._task_edit.text().strip(),
                acq=self._acq_edit.text().strip(),
                proc=self._proc_edit.text().strip(),
            )
        except ValueError:
            angio_invalid = True

        fusi_error = fusi_invalid or fusi_collision
        angio_error = angio_invalid or angio_collision
        self._fusi_preview_label.setStyleSheet("color: #d14343;" if fusi_error else "")
        self._angio_preview_label.setStyleSheet(
            "color: #d14343;" if angio_error else ""
        )
        self._fusi_row_label.setStyleSheet("color: #d14343;" if fusi_error else "")
        self._angio_row_label.setStyleSheet("color: #d14343;" if angio_error else "")
        if hasattr(self._widget, "_data_panel"):
            self._widget._data_panel.set_record_preview(fusi_preview)
        if hasattr(self._widget, "_stack_panel"):
            self._widget._stack_panel.set_angio_preview(angio_preview)

    def _build_bids_previews(self, storage_root: Path) -> tuple[str, str, str]:
        """Build BIDS-mode previews for runtime, fUSI, and z-stack outputs.

        Parameters
        ----------
        storage_root : Path
            Root directory selected in the System panel.

        Returns
        -------
        tuple of str
            Runtime-directory, fUSI-file, and angio-file previews.
        """
        session_preview = str(storage_root / "effusive_runtime" / "<sessionId>")

        try:
            bids.validate_bids_label(
                self._subject_edit.text(), "Subject", required=True
            )
            bids.validate_bids_label(
                self._session_edit.text(), "Session", required=True
            )
        except ValueError as error:
            message = str(error)
            return session_preview, message, message

        try:
            fusi_run = self._run_spinbox.value()
            fusi_preview = str(
                bids.build_bids_preview_path(
                    storage_root,
                    datatype=bids.FUSI_DATATYPE,
                    subject=self._subject_edit.text(),
                    session=self._session_edit.text(),
                    task=self._task_edit.text(),
                    acq=self._acq_edit.text(),
                    run=fusi_run,
                    proc=self._proc_edit.text(),
                    suffix="<suffix>",
                    extension=".<ext>",
                )
            )
        except ValueError as error:
            fusi_preview = str(error)

        try:
            angio_run = self._run_spinbox.value()
            angio_preview = str(
                bids.build_bids_preview_path(
                    storage_root,
                    datatype=bids.ANGIO_DATATYPE,
                    subject=self._subject_edit.text(),
                    session=self._session_edit.text(),
                    task=self._task_edit.text(),
                    acq=self._acq_edit.text(),
                    run=angio_run,
                    proc=self._proc_edit.text(),
                    suffix="<suffix>",
                    extension=".<ext>",
                )
            )
        except ValueError as error:
            angio_preview = str(error)

        return session_preview, fusi_preview, angio_preview
