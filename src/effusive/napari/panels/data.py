"""Data-recording panel for the Effusive napari widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from effusive.napari import commands
from effusive.napari import runtime as runtime_polling
from effusive.napari.components import ElidedPathLabel
from effusive.napari.panels.common import make_lock_hint

if TYPE_CHECKING:
    from effusive.napari.widget import EffusiveWidget


class DataPanel(QWidget):
    """Data-recording and RF-snapshot panel.

    Parameters
    ----------
    widget : EffusiveWidget
        Parent widget owning the config and viewer.
    """

    def __init__(self, widget: "EffusiveWidget") -> None:
        super().__init__()
        self._widget = widget
        self._setup_ui()

    def _setup_ui(self) -> None:
        widget = self._widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        self._record_lock_hint = make_lock_hint(
            "Start Effusive with the play button before using recording controls."
        )
        layout.addWidget(self._record_lock_hint)

        self._record_preview = ElidedPathLabel()
        self._record_preview.setObjectName("cf_info_value")
        self._record_preview.setToolTip(
            "Resolved output path preview for the next fUSI recording."
        )

        self._collision_warning = QLabel("")
        self._collision_warning.setObjectName("cf_info_value")
        self._collision_warning.setStyleSheet("color: #d14343; font-weight: 700;")
        self._collision_warning.setWordWrap(True)
        self._collision_warning.setVisible(False)
        self._collision_warning.setMaximumHeight(0)
        preview_group = QGroupBox("Output path(s)")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setSpacing(4)
        preview_layout.setContentsMargins(8, 12, 8, 8)
        preview_layout.addWidget(self._record_preview)
        preview_layout.addWidget(self._collision_warning)
        layout.addWidget(preview_group)

        save_group = QGroupBox("Data to save")
        save_layout = QVBoxLayout(save_group)
        save_layout.setSpacing(4)
        save_layout.setContentsMargins(8, 12, 8, 8)

        self._save_rf_checkbox = QCheckBox("RF")
        self._save_rf_checkbox.stateChanged.connect(
            lambda _: commands.handle_save_options(widget)
        )
        save_layout.addWidget(self._save_rf_checkbox)

        self._save_rf_time_tag_checkbox = QCheckBox("RF timestamps")
        self._save_rf_time_tag_checkbox.setChecked(True)
        self._save_rf_time_tag_checkbox.stateChanged.connect(
            lambda _: commands.handle_save_options(widget)
        )
        save_layout.addWidget(self._save_rf_time_tag_checkbox)

        self._save_bf_checkbox = QCheckBox("Beamformed IQ")
        self._save_bf_checkbox.setChecked(True)
        self._save_bf_checkbox.stateChanged.connect(
            lambda _: commands.handle_save_options(widget)
        )
        save_layout.addWidget(self._save_bf_checkbox)

        self._save_pdi_checkbox = QCheckBox("Power Doppler")
        self._save_pdi_checkbox.setChecked(True)
        self._save_pdi_checkbox.stateChanged.connect(
            lambda _: commands.handle_save_options(widget)
        )
        save_layout.addWidget(self._save_pdi_checkbox)

        self._save_group = save_group
        save_group.setEnabled(False)
        layout.addWidget(save_group)

        self._save_button = QPushButton()
        self._save_button.setCheckable(True)
        self._save_button.setEnabled(False)
        self._save_button.toggled.connect(lambda s: commands.handle_save(widget, s))
        self._save_button.setText("Record")
        self._save_button.setObjectName("record_btn_disabled")
        layout.addWidget(self._save_button)

        self._snapshot_rf_button = QPushButton("Snapshot RF")
        self._snapshot_rf_button.clicked.connect(
            lambda: runtime_polling.request_rf_snapshot(widget)
        )
        layout.addWidget(self._snapshot_rf_button)

        layout.addStretch()

    def set_record_collision_warning(self, text: str) -> None:
        """Set an inline collision warning for fUSI recording output.

        Parameters
        ----------
        text : str
            Warning text. Empty text hides the warning.

        Returns
        -------
        None
            This helper updates the warning label in place.
        """
        has_text = bool(text)
        self._collision_warning.setText(text)
        self._collision_warning.setVisible(has_text)
        self._collision_warning.setMaximumHeight(16777215 if has_text else 0)

    def set_record_preview(self, text: str) -> None:
        """Update the read-only next-recording preview.

        Parameters
        ----------
        text : str
            Preview path or validation message.

        Returns
        -------
        None
            This helper updates the preview label in place.
        """
        self._record_preview.set_full_text(text)
