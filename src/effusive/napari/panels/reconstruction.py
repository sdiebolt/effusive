"""Reconstruction panel for the Effusive napari widget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from effusive import config as cf_config
from effusive.napari import commands
from effusive.napari import controls
from effusive.napari.panels.common import add_labeled_form_row, make_lock_hint

if TYPE_CHECKING:
    from effusive.napari.widget import EffusiveWidget


class ReconstructionPanel(QWidget):
    """Reconstruction controls for beamforming and clutter filtering.

    Parameters
    ----------
    widget : EffusiveWidget
        Parent widget owning the config and shared-memory command channel.
    """

    def __init__(self, widget: "EffusiveWidget") -> None:
        super().__init__()
        self._widget = widget
        self._run_locked_labels: list[QLabel] = []
        self._record_locked_labels: list[QLabel] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Build the reconstruction panel controls."""
        widget = self._widget
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(8)

        self._reconstruction_lock_hint = make_lock_hint(
            "Beamformer applies when Effusive starts; clutter filtering stays live until recording starts."
        )
        layout.addWidget(self._reconstruction_lock_hint)

        beamforming_group = QGroupBox("Beamforming")
        beamforming_form = QFormLayout(beamforming_group)
        beamforming_form.setSpacing(6)
        beamforming_form.setContentsMargins(8, 12, 8, 8)

        self._beamformer_combo = QComboBox()
        self._beamformer_combo.addItem("Fourier", "Fourier")
        self._beamformer_combo.addItem("Delay-and-sum", "DAS")
        index = self._beamformer_combo.findData(widget._config.system.beamformer)
        self._beamformer_combo.setCurrentIndex(max(index, 0))
        self._beamformer_combo.setToolTip(
            "EchoFrame beamformer used when starting acquisition. DAS requires "
            "an EchoFrame MEX built with EF_USE_FFDAS=ON."
        )
        self._beamformer_combo.currentTextChanged.connect(self._on_beamformer_changed)
        beamformer_label = QLabel("Beamformer:")
        self._run_locked_labels.append(beamformer_label)
        beamforming_form.addRow(beamformer_label, self._beamformer_combo)

        self._speed_of_sound_spinbox = QDoubleSpinBox()
        self._speed_of_sound_spinbox.setRange(1000.0, 2000.0)
        self._speed_of_sound_spinbox.setDecimals(1)
        self._speed_of_sound_spinbox.setSingleStep(1.0)
        self._speed_of_sound_spinbox.setSuffix(" m/s")
        self._speed_of_sound_spinbox.setValue(widget._config.sequence.speed_of_sound_m_s)
        self._speed_of_sound_spinbox.setToolTip(
            "Speed of sound used for sequence timing and reconstruction."
        )
        self._speed_of_sound_spinbox.valueChanged.connect(
            self._on_speed_of_sound_changed
        )
        speed_label = QLabel("Speed of sound:")
        self._run_locked_labels.append(speed_label)
        beamforming_form.addRow(speed_label, self._speed_of_sound_spinbox)

        self._das_auto_checkbox = QCheckBox("Auto from probe")
        self._das_auto_checkbox.setChecked(widget._config.system.das_f_number_auto)
        self._das_auto_checkbox.setToolTip(
            "Use the -3 dB piston-element directivity cutoff from Perrot et al."
        )
        self._das_auto_checkbox.toggled.connect(self._on_das_auto_changed)
        self._das_auto_label = QLabel("DAS aperture:")
        self._run_locked_labels.append(self._das_auto_label)
        beamforming_form.addRow(self._das_auto_label, self._das_auto_checkbox)

        self._das_f_number_spinbox = QDoubleSpinBox()
        self._das_f_number_spinbox.setRange(0.1, 10.0)
        self._das_f_number_spinbox.setDecimals(2)
        self._das_f_number_spinbox.setSingleStep(0.05)
        self._das_f_number_spinbox.setValue(widget._config.system.das_f_number)
        self._das_f_number_spinbox.setToolTip(
            "Manual DAS receive f-number. 0.71 matches the original 35° EchoFrame default."
        )
        self._das_f_number_spinbox.valueChanged.connect(self._on_das_f_number_changed)
        self._das_f_number_label = QLabel("Receive f-number:")
        self._run_locked_labels.append(self._das_f_number_label)
        beamforming_form.addRow(self._das_f_number_label, self._das_f_number_spinbox)
        self._refresh_beamformer_params()
        layout.addWidget(beamforming_group)

        clutter_group = QGroupBox("Clutter filter")
        clutter_form = QFormLayout(clutter_group)
        clutter_form.setSpacing(6)
        clutter_form.setContentsMargins(8, 12, 8, 8)

        proc_cfg = widget._config.acquisition
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
            clutter_form, self._record_locked_labels, "SVD threshold:", svd_row
        )
        layout.addWidget(clutter_group)
        layout.addStretch()

    def _on_beamformer_changed(self, value: str) -> None:
        """Persist the startup EchoFrame beamformer choice.

        Parameters
        ----------
        value : str
            Selected beamformer name.
        """
        self._widget._config.system.beamformer = str(
            self._beamformer_combo.currentData()
        )
        self._refresh_beamformer_params()
        cf_config.save_config(self._widget._config)

    def _on_speed_of_sound_changed(self, value: float) -> None:
        """Persist the reconstruction speed of sound.

        Parameters
        ----------
        value : float
            Speed of sound in metres per second.
        """
        self._widget._config.sequence.speed_of_sound_m_s = float(value)
        cf_config.save_config(self._widget._config)

    def _on_das_auto_changed(self, checked: bool) -> None:
        """Persist the automatic DAS f-number toggle.

        Parameters
        ----------
        checked : bool
            Whether EchoFrame should compute the DAS receive f-number from probe metadata.
        """
        self._widget._config.system.das_f_number_auto = bool(checked)
        if not checked:
            self._das_f_number_spinbox.blockSignals(True)
            self._das_f_number_spinbox.setValue(
                self._widget._config.system.das_f_number
            )
            self._das_f_number_spinbox.blockSignals(False)
        self._refresh_beamformer_params()
        cf_config.save_config(self._widget._config)

    def _on_das_f_number_changed(self, value: float) -> None:
        """Persist the manual DAS receive f-number.

        Parameters
        ----------
        value : float
            Manual DAS receive f-number.
        """
        self._widget._config.system.das_f_number = float(value)
        cf_config.save_config(self._widget._config)

    def _refresh_beamformer_params(self) -> None:
        """Show only the parameter note matching the selected beamformer."""
        is_das = self._beamformer_combo.currentData() == "DAS"
        auto = self._das_auto_checkbox.isChecked()
        self._das_auto_label.setVisible(is_das)
        self._das_auto_checkbox.setVisible(is_das)
        self._das_f_number_label.setVisible(is_das)
        self._das_f_number_spinbox.setVisible(is_das)
        self._das_f_number_spinbox.setEnabled(is_das and not auto)

    def set_effective_das_f_number(self, value: float) -> None:
        """Show the effective DAS receive f-number reported by MATLAB setup.

        Parameters
        ----------
        value : float
            Effective DAS receive f-number in degrees.
        """
        if value <= 0 or value != value:
            return
        self._das_f_number_spinbox.blockSignals(True)
        self._das_f_number_spinbox.setValue(value)
        self._das_f_number_spinbox.blockSignals(False)

    def lock_for_run(self, locked: bool) -> None:
        """Enable or disable startup-only reconstruction controls.

        Parameters
        ----------
        locked : bool
            Whether controls that require a restart should be disabled.
        """
        auto = self._das_auto_checkbox.isChecked()
        self._beamformer_combo.setEnabled(not locked)
        self._speed_of_sound_spinbox.setEnabled(not locked)
        self._das_auto_checkbox.setEnabled(not locked)
        self._das_f_number_spinbox.setEnabled(not locked and not auto)
        controls.set_control_labels_locked(self._run_locked_labels, locked)

    def lock_for_recording(self, locked: bool) -> None:
        """Enable or disable record-locked clutter-filter controls.

        Parameters
        ----------
        locked : bool
            Whether controls should be locked because recording or a z-stack is active.
        """
        self._svd_slider.setEnabled(not locked)
        self._svd_spinbox.setEnabled(not locked)
        controls.set_control_labels_locked(self._record_locked_labels, locked)

    def set_metadata_gate_locked(self, locked: bool) -> None:
        """Apply or clear the pre-start metadata gate on startup controls.

        Parameters
        ----------
        locked : bool
            Whether startup controls should be disabled until metadata is valid.
        """
        if self._widget._run_button_state == "ready":
            self.lock_for_run(locked)
