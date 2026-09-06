"""Small reusable Qt widgets for the CortexFrame napari UI."""

from __future__ import annotations

import typing

from qtpy import QtGui
from qtpy.QtCore import QSize, Qt
from qtpy.QtWidgets import QLabel, QWidget


class ElidedPathLabel(QLabel):
    """Single-line label that elides long text and keeps the full tooltip.

    Parameters
    ----------
    parent : QWidget, optional
        Optional parent widget.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the label with elision enabled.

        Parameters
        ----------
        parent : QWidget, optional
            Optional parent widget.

        Returns
        -------
        None
            This initializer does not return a value.
        """
        super().__init__(parent)
        self._full_text = ""
        self.setWordWrap(False)

    def set_full_text(self, text: str) -> None:
        """Store the original text and refresh the visible elided label.

        Parameters
        ----------
        text : str
            The full string to preserve in the tooltip and elide for display.

        Returns
        -------
        None
            This method updates the label state in place.
        """
        self._full_text = text
        self.setToolTip(text)
        self._refresh_elision()

    def minimumSizeHint(self) -> QSize:
        """Return a near-zero minimum width so the label never blocks layout shrinkage.

        Returns
        -------
        QSize
            Minimum size with zero width and one line-height.
        """
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, a0: typing.Optional[QtGui.QResizeEvent]) -> None:
        """Recompute the elided label whenever the widget width changes.

        Parameters
        ----------
        a0 : QtGui.QResizeEvent or None
            The Qt resize event forwarded by the widget system.

        Returns
        -------
        None
            This method updates the visible label after delegating to Qt.
        """
        super().resizeEvent(a0)
        self._refresh_elision()

    def _refresh_elision(self) -> None:
        """Update the visible label text for the current available width.

        Returns
        -------
        None
            This method recomputes the displayed elided text.
        """
        metrics = self.fontMetrics()
        available = max(self.contentsRect().width(), 12)
        elided = metrics.elidedText(
            self._full_text, Qt.TextElideMode.ElideRight, available
        )
        self.setText(elided)
