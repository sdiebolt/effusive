"""Shared Qt helpers for Effusive panels."""

from __future__ import annotations

from qtpy.QtCore import QEvent, QObject
from qtpy.QtWidgets import (
    QAbstractScrollArea,
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QSlider,
    QWidget,
)


class _NoScrollWheelFilter(QObject):
    """Forward control wheel events to the enclosing scroll area's viewport."""

    def eventFilter(  # ty: ignore[invalid-method-override]
        self, watched: QObject | None, event: QEvent | None
    ) -> bool:
        """Scroll the sidebar instead of changing the watched control's value.

        Parameters
        ----------
        watched : QObject or None
            Control receiving the event.
        event : QEvent or None
            Event delivered to the control.

        Returns
        -------
        bool
            Whether the event was handled and should be withheld from the control.
        """
        if (
            event is not None
            and event.type() == QEvent.Type.Wheel
            and isinstance(watched, QWidget)
        ):
            ancestor = watched.parentWidget()
            while ancestor is not None and not isinstance(
                ancestor, QAbstractScrollArea
            ):
                ancestor = ancestor.parentWidget()
            if ancestor is not None:
                # Scroll areas handle wheel events on their viewport, not themselves.
                QApplication.sendEvent(ancestor.viewport(), event)
            return True
        return super().eventFilter(watched, event)


def install_no_scroll_wheel_filter(root: QWidget) -> None:
    """Prevent existing combo boxes, spinboxes and sliders from capturing scrolling.

    Call after constructing the panel; controls added later are not covered.

    Parameters
    ----------
    root : QWidget
        Widget whose descendants should forward wheel events to their scroll area.
    """
    wheel_filter = _NoScrollWheelFilter(root)
    for widget in root.findChildren((QComboBox, QAbstractSpinBox, QSlider)):
        widget.installEventFilter(wheel_filter)
