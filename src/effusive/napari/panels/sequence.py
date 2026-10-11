"""Sequence configuration panel for the Effusive napari widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
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
from effusive.napari.panels.common import (
    add_labeled_form_row,
    make_lock_hint,
    mark_dangerous_input,
    mark_dangerous_slider,
)

if TYPE_CHECKING:
    from effusive.napari.widget import EffusiveWidget


class SequencePanel(QWidget):
    """Startup-only sequence configuration panel.

    Parameters
    ----------
    widget : EffusiveWidget
        Parent widget owning the config and viewer.
    """

    def __init__(self, widget: "EffusiveWidget") -> None:
        super().__init__()
        self._widget = widget
        self._startup_only_widgets: list[QWidget] = []
        self._startup_only_labels: list[QLabel] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        widget = self._widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        self._sequence_lock_hint = make_lock_hint(
            "These controls apply when Effusive starts and stay locked while it is running."
        )
        layout.addWidget(self._sequence_lock_hint)

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        form.setSpacing(6)

        probe_names = widget._config.probe_names
        self._probe_combo = QComboBox()
        self._probe_combo.addItems(probe_names)
        default_probe = widget._worker_cfg.get(
            "probeName", widget._config.system.default_probe
        )
        if default_probe in probe_names:
            self._probe_combo.setCurrentText(default_probe)
        self._probe_combo.currentTextChanged.connect(self.on_probe_changed)
        self._probe_combo.currentTextChanged.connect(
            lambda text: setattr(widget._config.system, "default_probe", text)
        )
        form.addRow("Probe:", self._probe_combo)

        probe_name = self._probe_combo.currentText()
        probe = widget._config.get_probe(probe_name)

        freq_row = QHBoxLayout()
        self._freq_slider = mark_dangerous_slider(QSlider(Qt.Orientation.Horizontal))
        self._freq_slider.setRange(5000, 40000)
        default_freq = float(
            widget._worker_cfg.get("transmitFrequency", probe.transmit_frequency_mhz)
        )
        self._freq_slider.setValue(round(default_freq * 1000))
        self._freq_spinbox = mark_dangerous_input(QDoubleSpinBox())
        self._freq_spinbox.setRange(5.0, 40.0)
        self._freq_spinbox.setDecimals(3)
        self._freq_spinbox.setSingleStep(0.001)
        self._freq_spinbox.setSuffix(" MHz")
        self._freq_spinbox.setValue(default_freq)
        self._freq_slider.valueChanged.connect(
            lambda v: commands.handle_transmit_frequency(widget, v)
        )
        self._freq_spinbox.valueChanged.connect(
            lambda value: self._freq_slider.setValue(round(value * 1000))
        )
        freq_row.addWidget(self._freq_slider)
        freq_row.addWidget(self._freq_spinbox)
        add_labeled_form_row(
            form,
            self._startup_only_labels,
            "Transmit frequency:",
            freq_row,
            dangerous=True,
        )

        fps_row = QHBoxLayout()
        self._fps_slider = mark_dangerous_slider(QSlider(Qt.Orientation.Horizontal))
        self._fps_slider.setRange(1000, 50000)
        default_fps = int(
            widget._worker_cfg.get("txrxFrameRate", probe.txrx_frame_rate_hz)
        )
        self._fps_slider.setValue(default_fps)
        self._fps_spinbox = mark_dangerous_input(QSpinBox())
        self._fps_spinbox.setRange(1000, 50000)
        self._fps_spinbox.setSuffix(" Hz")
        self._fps_spinbox.setValue(default_fps)
        self._fps_slider.valueChanged.connect(
            lambda v: commands.handle_frame_rate(widget, v)
        )
        self._fps_spinbox.valueChanged.connect(self._fps_slider.setValue)
        fps_row.addWidget(self._fps_slider)
        fps_row.addWidget(self._fps_spinbox)
        add_labeled_form_row(
            form,
            self._startup_only_labels,
            "Frame rate:",
            fps_row,
            dangerous=True,
        )

        pulse_row = QHBoxLayout()
        self._pulse_slider = mark_dangerous_slider(QSlider(Qt.Orientation.Horizontal))
        self._pulse_slider.setRange(1, 10)
        default_pulse = int(
            widget._worker_cfg.get(
                "transmitPulseLength", widget._config.sequence.transmit_pulse_length
            )
        )
        self._pulse_slider.setValue(default_pulse)
        self._pulse_spinbox = mark_dangerous_input(QSpinBox())
        self._pulse_spinbox.setRange(1, 10)
        self._pulse_spinbox.setSuffix(" ½ cy")
        self._pulse_spinbox.setValue(default_pulse)
        self._pulse_slider.valueChanged.connect(
            lambda v: commands.handle_pulse_length(widget, v)
        )
        self._pulse_spinbox.valueChanged.connect(self._pulse_slider.setValue)
        pulse_row.addWidget(self._pulse_slider)
        pulse_row.addWidget(self._pulse_spinbox)
        add_labeled_form_row(
            form,
            self._startup_only_labels,
            "Pulse length:",
            pulse_row,
            dangerous=True,
        )

        tx_count_row = QHBoxLayout()
        self._tx_count_slider = QSlider(Qt.Orientation.Horizontal)
        self._tx_count_slider.setRange(1, 60)
        default_tx_count = int(
            widget._worker_cfg.get("nTransmissions", probe.n_transmissions)
        )
        self._tx_count_slider.setValue(default_tx_count)
        self._tx_count_spinbox = QSpinBox()
        self._tx_count_spinbox.setRange(1, 60)
        self._tx_count_spinbox.setValue(default_tx_count)
        self._tx_count_slider.valueChanged.connect(
            lambda v: commands.handle_n_transmissions(widget, v)
        )
        self._tx_count_spinbox.valueChanged.connect(self._tx_count_slider.setValue)
        tx_count_row.addWidget(self._tx_count_slider)
        tx_count_row.addWidget(self._tx_count_spinbox)
        add_labeled_form_row(
            form, self._startup_only_labels, "Transmissions:", tx_count_row
        )

        ensemble_row = QHBoxLayout()
        self._ensemble_slider = QSlider(Qt.Orientation.Horizontal)
        self._ensemble_slider.setRange(10, 1000)
        default_ensemble = int(widget._worker_cfg.get("nRepeats", probe.n_repeats))
        self._ensemble_slider.setValue(default_ensemble)
        self._ensemble_spinbox = QSpinBox()
        self._ensemble_spinbox.setRange(10, 1000)
        self._ensemble_spinbox.setValue(default_ensemble)
        self._ensemble_slider.valueChanged.connect(
            lambda v: commands.handle_n_repeats(widget, v)
        )
        self._ensemble_spinbox.valueChanged.connect(self._ensemble_slider.setValue)
        ensemble_row.addWidget(self._ensemble_slider)
        ensemble_row.addWidget(self._ensemble_spinbox)
        add_labeled_form_row(
            form, self._startup_only_labels, "Ensemble size:", ensemble_row
        )

        angle_row = QHBoxLayout()
        self._angle_slider = QSlider(Qt.Orientation.Horizontal)
        self._angle_slider.setRange(0, 60)
        default_angle = int(
            widget._worker_cfg.get(
                "planewaveOpeningAngle", probe.planewave_opening_angle_deg
            )
        )
        self._angle_slider.setValue(default_angle)
        self._angle_spinbox = QSpinBox()
        self._angle_spinbox.setRange(0, 60)
        self._angle_spinbox.setSuffix("°")
        self._angle_spinbox.setValue(default_angle)
        self._angle_slider.valueChanged.connect(
            lambda v: commands.handle_opening_angle(widget, v)
        )
        self._angle_spinbox.valueChanged.connect(self._angle_slider.setValue)
        angle_row.addWidget(self._angle_slider)
        angle_row.addWidget(self._angle_spinbox)
        add_labeled_form_row(
            form, self._startup_only_labels, "Opening angle:", angle_row
        )

        depth_row = QHBoxLayout()
        self._depth_slider = QSlider(Qt.Orientation.Horizontal)
        self._depth_slider.setRange(10, 500)
        default_depth = float(
            widget._worker_cfg.get(
                "desiredEndDepthMm", widget._config.sequence.imaging_depth_mm
            )
        )
        self._depth_slider.setValue(round(default_depth * 10))
        self._depth_spinbox = QDoubleSpinBox()
        self._depth_spinbox.setRange(1.0, 50.0)
        self._depth_spinbox.setDecimals(1)
        self._depth_spinbox.setSingleStep(0.1)
        self._depth_spinbox.setSuffix(" mm")
        self._depth_spinbox.setValue(default_depth)
        self._depth_slider.valueChanged.connect(
            lambda v: commands.handle_imaging_depth(widget, v)
        )
        self._depth_spinbox.valueChanged.connect(
            lambda value: self._depth_slider.setValue(round(value * 10))
        )
        depth_row.addWidget(self._depth_slider)
        depth_row.addWidget(self._depth_spinbox)
        add_labeled_form_row(
            form, self._startup_only_labels, "Imaging depth:", depth_row
        )

        self._startup_only_widgets = [
            self._probe_combo,
            self._freq_slider,
            self._freq_spinbox,
            self._fps_slider,
            self._fps_spinbox,
            self._pulse_slider,
            self._pulse_spinbox,
            self._tx_count_slider,
            self._tx_count_spinbox,
            self._ensemble_slider,
            self._ensemble_spinbox,
            self._angle_slider,
            self._angle_spinbox,
            self._depth_slider,
            self._depth_spinbox,
        ]

        layout.addLayout(form)

        self._sequence_reset_button = QPushButton("Reset to defaults")
        self._sequence_reset_button.clicked.connect(self.reset_to_defaults)
        layout.addWidget(self._sequence_reset_button)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Lock control
    # ------------------------------------------------------------------

    def lock_for_run(self, locked: bool) -> None:
        """Enable or disable all startup-only sequence controls.

        Parameters
        ----------
        locked : bool
            Whether the controls should be locked (disabled).
        """
        from effusive.napari import controls

        for w in self._startup_only_widgets:
            w.setEnabled(not locked)
        controls.set_control_labels_locked(self._startup_only_labels, locked)

    # ------------------------------------------------------------------
    # Probe change
    # ------------------------------------------------------------------

    def on_probe_changed(self, probe_name: str) -> None:
        """Update sequence defaults when the probe selection changes.

        Parameters
        ----------
        probe_name : str
            Name of the newly selected probe.
        """
        probe = self._widget._config.probe_defaults.get(probe_name)
        if probe is None:
            return
        self._freq_slider.setValue(round(probe.transmit_frequency_mhz * 1000))
        self._fps_slider.setValue(probe.txrx_frame_rate_hz)
        self._tx_count_slider.setValue(probe.n_transmissions)
        self._ensemble_slider.setValue(probe.n_repeats)
        self._angle_slider.setValue(probe.planewave_opening_angle_deg)

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset_to_defaults(self) -> None:
        """Reset all sequence controls to the shipped defaults and save."""
        widget = self._widget
        defaults = cf_config.load_default_config()
        probe_name = self._probe_combo.currentText()
        probe = defaults.get_probe(probe_name)
        seq = defaults.sequence

        self._freq_slider.setValue(round(probe.transmit_frequency_mhz * 1000))
        self._fps_slider.setValue(probe.txrx_frame_rate_hz)
        self._tx_count_slider.setValue(probe.n_transmissions)
        self._ensemble_slider.setValue(probe.n_repeats)
        self._angle_slider.setValue(probe.planewave_opening_angle_deg)
        self._pulse_slider.setValue(seq.transmit_pulse_length)
        self._depth_spinbox.setValue(seq.imaging_depth_mm)

        widget._config.probe_defaults[probe_name] = probe
        widget._config.sequence = seq
        cf_config.save_config(widget._config)
