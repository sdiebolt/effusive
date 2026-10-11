"""Focused tests for Effusive's dock sizing, without starting acquisition."""

from __future__ import annotations

import unittest

from qtpy.QtWidgets import (
    QWIDGETSIZE_MAX,
    QApplication,
    QDockWidget,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from effusive.napari.widget import EffusiveWidget


class DockSizingTests(unittest.TestCase):
    """Restore dock sizing after napari wraps the control widget."""

    @classmethod
    def setUpClass(cls) -> None:
        """Keep a Qt application alive for the widget tests."""
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        """Initialize only the Qt base, avoiding config and acquisition setup."""
        self.widget = EffusiveWidget.__new__(EffusiveWidget)
        QWidget.__init__(self.widget)
        self.dock = QDockWidget()
        self.other_dock = QDockWidget()

    def tearDown(self) -> None:
        """Delete Qt objects without invoking acquisition shutdown callbacks."""
        self.widget.deleteLater()
        self.dock.deleteLater()
        self.other_dock.deleteLater()
        self.app.processEvents()

    def test_undocked_widget_expands(self) -> None:
        """Allow the initial sizing call before the dock wrapper exists."""
        self.widget._restore_dock_size_policy()
        self.assertEqual(
            self.widget.sizePolicy().horizontalPolicy(),
            QSizePolicy.Policy.MinimumExpanding,
        )
        self.assertEqual(
            self.widget.sizePolicy().verticalPolicy(), QSizePolicy.Policy.Expanding
        )

    def test_restore_enclosing_dock_only(self) -> None:
        """Remove the dock cap through a wrapper without changing other docks."""
        wrapper = QWidget()
        QVBoxLayout(wrapper).addWidget(self.widget)
        self.dock.setWidget(wrapper)
        for target in (self.widget, self.dock, self.other_dock):
            target.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum
            )
        self.dock.setMaximumHeight(300)
        self.other_dock.setMaximumHeight(250)

        self.widget._restore_dock_size_policy()

        for target in (self.widget, self.dock):
            self.assertEqual(
                target.sizePolicy().horizontalPolicy(),
                QSizePolicy.Policy.MinimumExpanding,
            )
            self.assertEqual(
                target.sizePolicy().verticalPolicy(), QSizePolicy.Policy.Expanding
            )
        self.assertEqual(self.dock.maximumHeight(), QWIDGETSIZE_MAX)
        self.assertEqual(self.other_dock.maximumHeight(), 250)
        self.assertEqual(
            self.other_dock.sizePolicy().verticalPolicy(), QSizePolicy.Policy.Maximum
        )


if __name__ == "__main__":
    unittest.main()
