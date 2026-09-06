"""Shared helpers for CortexFrame widget panel construction."""

from __future__ import annotations

from typing import TypeVar

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSlider,
    QSpinBox,
    QWidget,
)

from cortexframe.napari.components import ElidedPathLabel

_TSpinBox = TypeVar("_TSpinBox", QDoubleSpinBox, QSpinBox)


def make_lock_hint(text: str) -> QLabel:
    """Build a hidden lock-state hint label for a control section.

    Parameters
    ----------
    text : str
        Initial hint text to show when the section becomes locked.

    Returns
    -------
    QLabel
        Word-wrapped label configured with the lock-hint object name.
    """
    label = QLabel(text)
    label.setObjectName("lock_hint")
    label.setWordWrap(True)
    label.setVisible(False)
    return label


def make_system_info_field() -> tuple[QWidget, QLabel, QLabel]:
    """Build a reusable system-info field row.

    Returns
    -------
    QWidget
        Container widget holding the icon and value labels.
    QLabel
        Value label used for the displayed path or status text.
    QLabel
        Icon label used for the status glyph.
    """
    container = QWidget()
    field_layout = QHBoxLayout(container)
    field_layout.setContentsMargins(0, 0, 0, 0)
    field_layout.setSpacing(6)

    icon_label = QLabel()
    icon_label.setFixedWidth(16)
    field_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)

    value_label = ElidedPathLabel()
    value_label.setObjectName("cf_info_value")
    value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    field_layout.addWidget(value_label, 1)
    return container, value_label, icon_label


def make_dangerous_label(text: str) -> QLabel:
    """Build a warning-styled label for acoustically sensitive settings.

    Parameters
    ----------
    text : str
        Base label text without the warning prefix.

    Returns
    -------
    QLabel
        Label configured with the danger style and tooltip.
    """
    label = QLabel(f"⚠ {text}")
    label.setObjectName("danger_label")
    label.setProperty("danger", True)
    label.setToolTip(
        "This parameter affects acoustic safety. Do not change without understanding the implications."
    )
    return label


def mark_dangerous_input(spin_widget: _TSpinBox) -> _TSpinBox:
    """Mark a spin box as acoustically sensitive for stylesheet styling.

    Parameters
    ----------
    spin_widget : QDoubleSpinBox or QSpinBox
        Spin box that should receive the danger property.

    Returns
    -------
    QDoubleSpinBox or QSpinBox
        The same widget instance after styling metadata is attached.
    """
    spin_widget.setProperty("danger", True)
    return spin_widget


def mark_dangerous_slider(slider: QSlider) -> QSlider:
    """Mark a slider as acoustically sensitive for stylesheet styling.

    Parameters
    ----------
    slider : QSlider
        Slider that should receive the danger object name.

    Returns
    -------
    QSlider
        The same slider instance after styling metadata is attached.
    """
    slider.setObjectName("danger_slider")
    return slider


def add_labeled_form_row(
    form: QFormLayout,
    label_list: list[QLabel],
    text: str,
    field: QWidget | QLayout,
    dangerous: bool = False,
) -> QLabel:
    """Add one labeled row to a Qt form and track the label.

    Parameters
    ----------
    form : QFormLayout
        Form layout that receives the new row.
    label_list : list[QLabel]
        Label collection updated so the caller can later toggle lock styling.
    text : str
        Label text for the row.
    field : QWidget or QLayout
        Qt widget or layout inserted into the form field column.
    dangerous : bool, default: False
        Whether to use the danger-styled warning label variant.

    Returns
    -------
    QLabel
        The label instance added to the form.
    """
    label = make_dangerous_label(text) if dangerous else QLabel(text)
    label_list.append(label)
    form.addRow(label, field)
    return label
