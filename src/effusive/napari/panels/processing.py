"""Live-processing panel for the Effusive napari widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from effusive import config as cf_config
from effusive.napari import commands
from effusive.napari import controls
from effusive.napari import crop as crop_helpers
from effusive.napari.panels.common import (
    add_labeled_form_row,
    make_lock_hint,
    mark_dangerous_input,
    mark_dangerous_slider,
)

if TYPE_CHECKING:
    from effusive.napari.widget import EffusiveWidget


class ProcessingPanel(QWidget):
    """Live-processing control panel with voltage, apertures, TGC, and crop.

    Parameters
    ----------
    widget : EffusiveWidget
        Parent widget owning the config and viewer.
    """

    def __init__(self, widget: "EffusiveWidget") -> None:
        super().__init__()
        self._widget = widget
        # TGC state.
        self._tgc_sliders: list[QSlider] = []
        self._tgc_spinboxes: list[QSpinBox] = []
        self._tgc_base_points: list[float] = []
        self._tgc_all_gain: float = 0.0
        self._updating_tgc_controls: bool = False
        # Lock lists.
        self._record_locked_widgets: list[QWidget] = []
        self._record_locked_labels: list[QLabel] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        widget = self._widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        self._live_lock_hint = make_lock_hint(
            "Voltage, apertures, TGC, SVD, and crop stay live until recording starts."
        )
        layout.addWidget(self._live_lock_hint)

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setSpacing(6)

        proc_cfg = widget._config.acquisition

        volt_row = QHBoxLayout()
        self._voltage_slider = mark_dangerous_slider(QSlider(Qt.Orientation.Horizontal))
        self._voltage_slider.setRange(16, 250)
        default_voltage = min(
            max(float(widget._worker_cfg.get("voltage", proc_cfg.voltage_v)), 1.6), 25.0
        )
        self._voltage_slider.setValue(round(default_voltage * 10))
        self._voltage_spinbox = mark_dangerous_input(QDoubleSpinBox())
        self._voltage_spinbox.setRange(1.6, 25.0)
        self._voltage_spinbox.setDecimals(1)
        self._voltage_spinbox.setSingleStep(0.1)
        self._voltage_spinbox.setSuffix(" V")
        self._voltage_spinbox.setValue(default_voltage)
        self._voltage_slider.valueChanged.connect(
            lambda v: commands.handle_voltage(widget, v)
        )
        self._voltage_spinbox.valueChanged.connect(
            lambda value: self._voltage_slider.setValue(round(value * 10))
        )
        volt_row.addWidget(self._voltage_slider)
        volt_row.addWidget(self._voltage_spinbox)
        add_labeled_form_row(
            form, self._record_locked_labels, "Voltage:", volt_row, dangerous=True
        )

        tx_row = QHBoxLayout()
        self._tx_aperture_slider = mark_dangerous_slider(
            QSlider(Qt.Orientation.Horizontal)
        )
        self._tx_aperture_slider.setRange(0, 100)
        default_tx_aperture = int(
            widget._worker_cfg.get(
                "transmitAperturePercentage", proc_cfg.tx_aperture_percent
            )
        )
        self._tx_aperture_slider.setValue(default_tx_aperture)
        self._tx_aperture_spinbox = mark_dangerous_input(QSpinBox())
        self._tx_aperture_spinbox.setRange(0, 100)
        self._tx_aperture_spinbox.setSuffix("%")
        self._tx_aperture_spinbox.setValue(default_tx_aperture)
        self._tx_aperture_slider.valueChanged.connect(
            lambda v: commands.handle_tx_aperture(widget, v)
        )
        self._tx_aperture_spinbox.valueChanged.connect(
            self._tx_aperture_slider.setValue
        )
        tx_row.addWidget(self._tx_aperture_slider)
        tx_row.addWidget(self._tx_aperture_spinbox)
        add_labeled_form_row(
            form, self._record_locked_labels, "TX aperture:", tx_row, dangerous=True
        )

        rx_row = QHBoxLayout()
        self._rx_aperture_slider = QSlider(Qt.Orientation.Horizontal)
        self._rx_aperture_slider.setRange(0, 100)
        default_rx_aperture = int(
            widget._worker_cfg.get(
                "receiveAperturePercentage", proc_cfg.rx_aperture_percent
            )
        )
        self._rx_aperture_slider.setValue(default_rx_aperture)
        self._rx_aperture_spinbox = QSpinBox()
        self._rx_aperture_spinbox.setRange(0, 100)
        self._rx_aperture_spinbox.setSuffix("%")
        self._rx_aperture_spinbox.setValue(default_rx_aperture)
        self._rx_aperture_slider.valueChanged.connect(
            lambda v: commands.handle_rx_aperture(widget, v)
        )
        self._rx_aperture_spinbox.valueChanged.connect(
            self._rx_aperture_slider.setValue
        )
        rx_row.addWidget(self._rx_aperture_slider)
        rx_row.addWidget(self._rx_aperture_spinbox)
        add_labeled_form_row(form, self._record_locked_labels, "RX aperture:", rx_row)

        svd_row = QHBoxLayout()
        self._svd_slider = QSlider(Qt.Orientation.Horizontal)
        self._svd_slider.setRange(0, 100)
        default_svd = int(
            widget._worker_cfg.get("svdThreshold", proc_cfg.svd_threshold_percent)
        )
        self._svd_slider.setValue(default_svd)
        self._svd_spinbox = QSpinBox()
        self._svd_spinbox.setRange(0, 100)
        self._svd_spinbox.setSuffix("%")
        self._svd_spinbox.setValue(default_svd)
        self._svd_slider.valueChanged.connect(lambda v: commands.handle_svd(widget, v))
        self._svd_spinbox.valueChanged.connect(self._svd_slider.setValue)
        svd_row.addWidget(self._svd_slider)
        svd_row.addWidget(self._svd_spinbox)
        add_labeled_form_row(
            form, self._record_locked_labels, "SVD threshold:", svd_row
        )

        layout.addLayout(form)

        tgc_group = QGroupBox("TGC")
        tgc_layout = QFormLayout(tgc_group)
        tgc_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        tgc_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        tgc_layout.setSpacing(6)
        initial_tgc_points = self.get_initial_tgc_points()
        saved_all_gain = proc_cfg.tgc_all_gain
        saved_gain_factor = self.compute_tgc_gain_factor(saved_all_gain)
        # Back-compute base points so re-applying the saved gain reproduces saved
        # absolute TGC values without double-scaling.
        self._tgc_base_points = [
            v / (saved_gain_factor * 1023.0) for v in initial_tgc_points
        ]
        self._tgc_all_gain = saved_all_gain

        tgc_all_row = QHBoxLayout()
        self._tgc_all_slider = QSlider(Qt.Orientation.Horizontal)
        self._tgc_all_slider.setRange(-100, 100)
        self._tgc_all_slider.setValue(round(saved_all_gain * 100))
        self._tgc_all_spinbox = QDoubleSpinBox()
        self._tgc_all_spinbox.setRange(-1.0, 1.0)
        self._tgc_all_spinbox.setDecimals(2)
        self._tgc_all_spinbox.setSingleStep(0.01)
        self._tgc_all_spinbox.setValue(saved_all_gain)
        self._tgc_all_slider.valueChanged.connect(
            lambda v: commands.handle_tgc_all_gain(widget, v)
        )
        self._tgc_all_spinbox.valueChanged.connect(
            lambda value: self._tgc_all_slider.setValue(round(value * 100))
        )
        tgc_all_row.addWidget(self._tgc_all_slider)
        tgc_all_row.addWidget(self._tgc_all_spinbox)
        tgc_all_label = QLabel("TGC All Gain:")
        self._record_locked_labels.append(tgc_all_label)
        tgc_layout.addRow(tgc_all_label, tgc_all_row)

        self._tgc_sliders = []
        self._tgc_spinboxes = []
        for idx, initial_value in enumerate(initial_tgc_points, start=1):
            point_row = QHBoxLayout()
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 1023)
            slider.setValue(initial_value)
            spin = QSpinBox()
            spin.setRange(0, 1023)
            spin.setValue(initial_value)
            slider.valueChanged.connect(
                lambda value, i=idx - 1: commands.handle_tgc_point(widget, i, value)
            )
            spin.valueChanged.connect(slider.setValue)
            point_row.addWidget(slider)
            point_row.addWidget(spin)
            point_label = QLabel(f"Point {idx}:")
            self._record_locked_labels.append(point_label)
            tgc_layout.addRow(point_label, point_row)
            self._tgc_sliders.append(slider)
            self._tgc_spinboxes.append(spin)

        layout.addWidget(tgc_group)

        crop_row = QHBoxLayout()
        self._crop_action_button = QPushButton()
        self._crop_action_button.clicked.connect(
            lambda: crop_helpers.toggle_crop(widget)
        )
        crop_row.addWidget(self._crop_action_button)
        layout.addLayout(crop_row)
        self._crop_action_button.setText("Apply Crop")
        self._crop_action_button.setObjectName("crop_btn_apply")
        self._crop_action_button.setToolTip(
            "Apply the current ROI crop and lock the ROI layer."
        )

        self._record_locked_widgets = [
            self._voltage_slider,
            self._voltage_spinbox,
            self._tx_aperture_slider,
            self._tx_aperture_spinbox,
            self._rx_aperture_slider,
            self._rx_aperture_spinbox,
            self._svd_slider,
            self._svd_spinbox,
            self._tgc_all_slider,
            self._tgc_all_spinbox,
            *self._tgc_sliders,
            *self._tgc_spinboxes,
        ]

        self._processing_reset_button = QPushButton("Reset to defaults")
        self._processing_reset_button.clicked.connect(self.reset_to_defaults)
        layout.addWidget(self._processing_reset_button)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Lock control
    # ------------------------------------------------------------------

    def lock_for_recording(self, locked: bool) -> None:
        """Enable or disable all record-locked processing controls.

        Parameters
        ----------
        locked : bool
            Whether the controls should be locked (disabled).
        """
        for w in self._record_locked_widgets:
            w.setEnabled(not locked)
        controls.set_control_labels_locked(self._record_locked_labels, locked)

    # ------------------------------------------------------------------
    # TGC helpers
    # ------------------------------------------------------------------

    def get_initial_tgc_points(self) -> list[int]:
        """Return the startup TGC control-point values from the worker config.

        Returns
        -------
        list of int
            Eight TGC control-point values in the range 0–1023.
        """
        widget = self._widget
        cfg_points = widget._worker_cfg.get("tgcControlPoints")
        if isinstance(cfg_points, list) and len(cfg_points) == 8:
            return [int(min(max(round(float(v)), 0), 1023)) for v in cfg_points]
        if len(widget._config.acquisition.tgc_control_points) == 8:
            return [
                int(min(max(v, 0), 1023))
                for v in widget._config.acquisition.tgc_control_points
            ]
        default_tgc = int(widget._worker_cfg.get("tgcGain", 900))
        return [min(max(default_tgc, 0), 1023)] * 8

    def get_current_tgc_points(self) -> list[int]:
        """Return the current TGC control-point values from the slider widgets.

        Returns
        -------
        list of int
            Eight TGC control-point values as currently set in the UI.
        """
        return [slider.value() for slider in self._tgc_sliders]

    @staticmethod
    def compute_tgc_gain_factor(slider_value: float) -> float:
        """Compute the multiplicative gain factor for the TGC all-gain slider.

        Parameters
        ----------
        slider_value : float
            Normalised all-gain slider position in the range −1.0 to +1.0.

        Returns
        -------
        float
            Gain multiplier applied to the stored base TGC points.
        """
        return 1.05 * slider_value * slider_value + 1.95 * slider_value + 1.0

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset_to_defaults(self) -> None:
        """Reset all processing controls to the shipped defaults and save."""
        widget = self._widget
        defaults = cf_config.load_default_config().acquisition

        self._voltage_slider.setValue(round(defaults.voltage_v * 10))
        self._tx_aperture_slider.setValue(defaults.tx_aperture_percent)
        self._rx_aperture_slider.setValue(defaults.rx_aperture_percent)
        self._svd_slider.setValue(defaults.svd_threshold_percent)

        self._updating_tgc_controls = True
        for slider, spin, value in zip(
            self._tgc_sliders, self._tgc_spinboxes, defaults.tgc_control_points
        ):
            slider.setValue(value)
            spin.setValue(value)
        self._tgc_base_points = [v / 1023.0 for v in defaults.tgc_control_points]
        self._tgc_all_gain = 0.0
        self._tgc_all_slider.setValue(0)
        self._tgc_all_spinbox.setValue(0.0)
        self._updating_tgc_controls = False

        widget._config.acquisition = defaults
        cf_config.save_config(widget._config)
