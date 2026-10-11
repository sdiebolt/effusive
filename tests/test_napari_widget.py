"""Focused tests for Effusive's dock sizing, without starting acquisition."""

from __future__ import annotations

import unittest
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

from qtpy.QtCore import Qt
from qtpy.QtWidgets import (
    QWIDGETSIZE_MAX,
    QApplication,
    QDockWidget,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from effusive.napari.widget import EffusiveWidget


class _TitleBar(QWidget):
    """Expose the same visible title label as napari's custom title bar."""

    def __init__(self, dock: QDockWidget) -> None:
        """Build a lightweight title bar without initializing a viewer."""
        super().__init__(dock)
        self.title = QLabel("Effusive", self)


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

    def test_versioned_native_dock_title(self) -> None:
        """Set the window title without changing unrelated docks."""
        self.dock.setWidget(self.widget)
        self.other_dock.setWindowTitle("Other")
        with patch("effusive.napari.widget.version", return_value="0.1.2") as version:
            self.widget._setup_dock_title()
        version.assert_called_once_with("effusive")
        self.assertEqual(self.dock.windowTitle(), "Effusive v0.1.2")
        self.assertEqual(self.other_dock.windowTitle(), "Other")

    def test_versioned_custom_title_survives_recreation(self) -> None:
        """Update the visible label after napari recreates its custom title bar."""
        self.dock.setWidget(self.widget)
        title_bar = _TitleBar(self.dock)
        self.dock.setTitleBarWidget(title_bar)
        with patch("effusive.napari.widget.version", return_value="0.1.2"):
            self.widget._setup_dock_title()
        self.assertEqual(title_bar.title.text(), "Effusive v0.1.2")
        for signal, value in (
            (self.dock.topLevelChanged, True),
            (self.dock.dockLocationChanged, Qt.DockWidgetArea.LeftDockWidgetArea),
        ):
            replacement = _TitleBar(self.dock)
            self.dock.setTitleBarWidget(replacement)
            signal.emit(value)
            self.assertEqual(replacement.title.text(), "Effusive v0.1.2")

    def test_versioned_title_without_package_metadata(self) -> None:
        """Use a development title when distribution metadata is unavailable."""
        self.dock.setWidget(self.widget)
        with patch("effusive.napari.widget.version", side_effect=PackageNotFoundError):
            self.widget._setup_dock_title()
        self.assertEqual(self.dock.windowTitle(), "Effusive vdev")

    def test_title_setup_without_dock(self) -> None:
        """Do nothing if the widget has not been docked."""
        with patch("effusive.napari.widget.version") as version:
            self.widget._setup_dock_title()
        version.assert_not_called()

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
