"""Z-stack panel for the Effusive napari widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from qtpy.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from effusive import config as cf_config
from effusive import shared_memory
from effusive.napari import stack as stack_helpers
from effusive.napari.components import ElidedPathLabel
from effusive.napari.panels.common import make_lock_hint

if TYPE_CHECKING:
    from effusive.motor_controller import MotorController
    from effusive.napari.widget import EffusiveWidget


class StackPanel(QWidget):
    """Z-stack acquisition panel with motor control and stack preview state.

    Parameters
    ----------
    widget : EffusiveWidget
        Parent widget owning the config and viewer.
    """

    def __init__(self, widget: "EffusiveWidget") -> None:
        super().__init__()
        self._widget = widget

        # Runtime state.
        self._stack_active: bool = False
        self._stack_error: bool = False
        self._stack_status_code: int = shared_memory.STACK_STATUS_IDLE
        self._stack_current_slice: int = -1
        self._stack_total_slices: int = 0
        self._stack_target_position_um: int = 0
        self._manual_motor_position_um: int | None = None
        self._stack_motor_homed: bool = False
        self._stack_motor_controller: MotorController | None = None
        self._last_stack_status: tuple[int, int, int, int, int, int] | None = None

        # Preview accumulation state.
        self._stack_preview_volume: np.ndarray | None = None
        self._stack_preview_bmode_volume: np.ndarray | None = None
        self._stack_preview_sum: np.ndarray | None = None
        self._stack_preview_bmode_sum: np.ndarray | None = None
        self._stack_preview_count: int = 0
        self._stack_preview_slice_index: int = -1
        self._stack_preview_paused_on_complete: bool = False
        self._stack_preview_hold_display: bool = False

        # Lock widget lists (populated during _setup_ui).
        self._stack_shared_widgets: list[QWidget] = []
        self._stack_start_widgets: list[QWidget] = []

        self._setup_ui()

    def _setup_ui(self) -> None:
        widget = self._widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        self._stack_lock_hint = make_lock_hint(
            "Start Effusive with the play button before recording a z-stack."
        )
        layout.addWidget(self._stack_lock_hint)

        self._angio_preview = ElidedPathLabel()
        self._angio_preview.setObjectName("cf_info_value")
        self._angio_preview.setToolTip(
            "Resolved output path preview for the next angio export."
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
        preview_layout.addWidget(self._angio_preview)
        preview_layout.addWidget(self._collision_warning)
        layout.addWidget(preview_group)

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setSpacing(6)

        self._stack_backend_combo = QComboBox()
        self._stack_backend_combo.addItems(["Real motor", "Dummy motor"])
        self._stack_backend_combo.setCurrentText(
            "Dummy motor" if widget._config.system.simulate_mode else "Real motor"
        )
        form.addRow("Backend:", self._stack_backend_combo)

        self._stack_start_mm_spinbox = QDoubleSpinBox()
        self._stack_start_mm_spinbox.setRange(-100.0, 100.0)
        self._stack_start_mm_spinbox.setDecimals(3)
        self._stack_start_mm_spinbox.setSingleStep(0.001)
        self._stack_start_mm_spinbox.setSuffix(" mm")
        form.addRow("Start position:", self._stack_start_mm_spinbox)

        stack_cfg = widget._config.stack

        self._stack_step_mm_spinbox = QDoubleSpinBox()
        self._stack_step_mm_spinbox.setRange(-100.0, 100.0)
        self._stack_step_mm_spinbox.setDecimals(3)
        self._stack_step_mm_spinbox.setValue(stack_cfg.step_mm)
        self._stack_step_mm_spinbox.setSingleStep(0.001)
        self._stack_step_mm_spinbox.setSuffix(" mm")
        self._stack_step_mm_spinbox.valueChanged.connect(
            lambda v: setattr(widget._config.stack, "step_mm", v)
        )
        form.addRow("Step size:", self._stack_step_mm_spinbox)

        self._stack_n_slices_spinbox = QSpinBox()
        self._stack_n_slices_spinbox.setRange(1, 10000)
        self._stack_n_slices_spinbox.setValue(stack_cfg.n_slices)
        self._stack_n_slices_spinbox.valueChanged.connect(
            lambda v: setattr(widget._config.stack, "n_slices", v)
        )
        form.addRow("Slices:", self._stack_n_slices_spinbox)

        self._stack_npdi_per_slice_spinbox = QSpinBox()
        self._stack_npdi_per_slice_spinbox.setRange(1, 100000)
        self._stack_npdi_per_slice_spinbox.setValue(stack_cfg.frames_per_slice)
        self._stack_npdi_per_slice_spinbox.valueChanged.connect(
            lambda v: setattr(widget._config.stack, "frames_per_slice", v)
        )
        form.addRow("Frames / slice:", self._stack_npdi_per_slice_spinbox)

        self._stack_settle_ms_spinbox = QSpinBox()
        self._stack_settle_ms_spinbox.setRange(0, 3_600_000)
        self._stack_settle_ms_spinbox.setValue(stack_cfg.settle_ms)
        self._stack_settle_ms_spinbox.setSuffix(" ms")
        self._stack_settle_ms_spinbox.valueChanged.connect(
            lambda v: setattr(widget._config.stack, "settle_ms", v)
        )
        form.addRow("Settle time:", self._stack_settle_ms_spinbox)

        layout.addLayout(form)

        jog_row = QHBoxLayout()
        self._stack_home_button = QPushButton("Home")
        self._stack_home_button.setObjectName("stack_btn_home")
        self._stack_home_button.clicked.connect(
            lambda: stack_helpers.request_home_stack_motor(widget)
        )
        jog_row.addWidget(self._stack_home_button)
        self._stack_jog_back_button = QPushButton("<- Back")
        self._stack_jog_back_button.clicked.connect(
            lambda: stack_helpers.jog_stack(widget, -1)
        )
        jog_row.addWidget(self._stack_jog_back_button)
        self._stack_jog_front_button = QPushButton("Front ->")
        self._stack_jog_front_button.clicked.connect(
            lambda: stack_helpers.jog_stack(widget, 1)
        )
        jog_row.addWidget(self._stack_jog_front_button)
        layout.addLayout(jog_row)

        stack_runtime_group = QGroupBox("Runtime")
        stack_runtime_layout = QVBoxLayout(stack_runtime_group)
        stack_runtime_layout.setSpacing(4)
        stack_runtime_layout.setContentsMargins(8, 12, 8, 8)

        self._stack_target_label = QLabel("Motor position: -")
        stack_runtime_layout.addWidget(self._stack_target_label)
        layout.addWidget(stack_runtime_group)

        self._stack_action_button = QPushButton()
        self._stack_action_button.clicked.connect(
            lambda: stack_helpers.dispatch_stack_action(widget)
        )
        layout.addWidget(self._stack_action_button)

        self._stack_shared_widgets = [
            self._stack_backend_combo,
            self._stack_step_mm_spinbox,
        ]
        self._stack_start_widgets = [
            self._stack_start_mm_spinbox,
            self._stack_n_slices_spinbox,
            self._stack_npdi_per_slice_spinbox,
            self._stack_settle_ms_spinbox,
        ]

        self._stack_reset_button = QPushButton("Reset to defaults")
        self._stack_reset_button.clicked.connect(self.reset_to_defaults)
        layout.addWidget(self._stack_reset_button)

        stack_helpers.refresh_stack_controls(widget)
        layout.addStretch()

    def set_angio_collision_warning(self, text: str) -> None:
        """Set an inline collision warning for z-stack output.

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

    def set_angio_preview(self, text: str) -> None:
        """Update the read-only next z-stack preview.

        Parameters
        ----------
        text : str
            Preview path or validation message.

        Returns
        -------
        None
            This helper updates the preview label in place.
        """
        self._angio_preview.set_full_text(text)

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset_to_defaults(self) -> None:
        """Reset all stack controls to the shipped defaults and save."""
        widget = self._widget
        defaults = cf_config.load_default_config().stack

        self._stack_step_mm_spinbox.setValue(defaults.step_mm)
        self._stack_n_slices_spinbox.setValue(defaults.n_slices)
        self._stack_npdi_per_slice_spinbox.setValue(defaults.frames_per_slice)
        self._stack_settle_ms_spinbox.setValue(defaults.settle_ms)

        widget._config.stack = defaults
        cf_config.save_config(widget._config)
