"""Regression tests for interrupted accordion animations."""

from __future__ import annotations

import unittest
from contextlib import ExitStack
from unittest.mock import patch

from qtpy.QtCore import QAbstractAnimation, QPoint, QPointF, QPropertyAnimation, Qt
from qtpy.QtGui import QIcon, QWheelEvent
from qtpy.QtWidgets import QApplication, QPushButton, QSlider, QWidget

from effusive.napari import widget as widget_module
from effusive.napari.widget import EffusiveWidget


class _Panel(QWidget):
    """Stand in for acquisition panels without initializing hardware or config."""

    def __init__(self, parent: QWidget) -> None:
        """Include a slider to test filter installation across all sections."""
        super().__init__(parent)
        self.slider = QSlider(Qt.Orientation.Horizontal, self)
        self.slider.setValue(50)

    def refresh_previews(self) -> None:
        """Leave metadata previews unused in these layout tests."""


class AccordionTests(unittest.TestCase):
    """Ensure the latest section selection wins over interrupted animations."""

    @classmethod
    def setUpClass(cls) -> None:
        """Keep one Qt application alive for all tests."""
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        """Build the real accordion using lightweight panel stand-ins."""
        self.widget = EffusiveWidget.__new__(EffusiveWidget)
        QWidget.__init__(self.widget)
        self.widget._accordion_buttons = []
        self.animations: list[QPropertyAnimation] = []
        with ExitStack() as stack:
            for name in (
                "SystemPanel",
                "MetadataPanel",
                "SequencePanel",
                "ProcessingPanel",
                "StackPanel",
                "DataPanel",
            ):
                stack.enter_context(patch.object(widget_module, name, _Panel))
            stack.enter_context(
                patch.object(EffusiveWidget, "_is_dark", return_value=False)
            )
            stack.enter_context(
                patch.object(widget_module, "make_lucide_icon", return_value=QIcon())
            )
            stack.enter_context(
                patch.object(
                    widget_module,
                    "QPropertyAnimation",
                    side_effect=self._make_animation,
                )
            )
            self.container = self.widget._make_accordion()
            self.container.resize(460, 800)
            self.container.show()
            self.app.processEvents()
            # The button callbacks look up QPropertyAnimation when clicked.
            self.patches = stack.pop_all()
        self.buttons = self.container.findChildren(QPushButton)
        self.panels = self.container.findChildren(_Panel)

    def tearDown(self) -> None:
        """Stop animations and dispose of Qt objects without acquisition shutdown."""
        for animation in self.animations:
            animation.stop()
        self.patches.close()
        self.container.close()
        self.container.deleteLater()
        self.widget.deleteLater()
        self.app.processEvents()

    def _make_animation(
        self, panel: QWidget, property_name: bytes
    ) -> QPropertyAnimation:
        """Record real Qt animations so completion can be tested without sleeps."""
        animation = QPropertyAnimation(panel, property_name)
        self.animations.append(animation)
        return animation

    def _finish_animations(self) -> None:
        """Finish running animations synchronously for deterministic assertions."""
        for animation in self.animations:
            if animation.state() == QAbstractAnimation.State.Running:
                animation.setCurrentTime(animation.duration())

    def test_reselect_collapsing_panel(self) -> None:
        """Return to A while its collapse is running and ignore stale callbacks."""
        self.buttons[1].click()
        collapse = self.animations[0]
        collapse.setCurrentTime(50)
        self.buttons[0].click()
        self.assertTrue(self.buttons[0].isChecked())
        self.assertEqual(collapse.state(), QAbstractAnimation.State.Stopped)
        height = self.panels[0].maximumHeight()
        collapse.finished.emit()
        self.assertTrue(self.panels[0].isVisible())
        self.assertEqual(self.panels[0].maximumHeight(), height)
        self._finish_animations()
        self.assertEqual(
            [panel.isVisible() for panel in self.panels],
            [True] + [False] * (len(self.panels) - 1),
        )

    def test_collapse_expanding_panel(self) -> None:
        """Click the opening section again to collapse it without competing animations."""
        self.buttons[1].click()
        expansion = self.animations[1]
        expansion.setCurrentTime(50)
        self.buttons[1].click()
        self.assertFalse(self.buttons[1].isChecked())
        self.assertEqual(expansion.state(), QAbstractAnimation.State.Stopped)
        height = self.panels[1].maximumHeight()
        expansion.finished.emit()
        self.assertEqual(self.panels[1].maximumHeight(), height)
        self._finish_animations()
        self.assertFalse(any(panel.isVisible() for panel in self.panels))
        self.assertFalse(any(button.isChecked() for button in self.buttons))

    def test_wheel_filter_installed_on_all_panels(self) -> None:
        """Protect sliders in every section of the accordion."""
        for panel in self.panels:
            event = QWheelEvent(
                QPointF(5, 5),
                QPointF(panel.slider.mapToGlobal(QPoint(5, 5))),
                QPoint(),
                QPoint(0, 120),
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
                Qt.ScrollPhase.NoScrollPhase,
                False,
            )
            QApplication.sendEvent(panel.slider, event)
            self.assertEqual(panel.slider.value(), 50)

    def test_normal_switch_and_collapse(self) -> None:
        """Preserve normal section switching and the all-closed state."""
        self.buttons[1].click()
        self._finish_animations()
        self.assertEqual(
            [panel.isVisible() for panel in self.panels],
            [False, True] + [False] * (len(self.panels) - 2),
        )
        self.buttons[1].click()
        self._finish_animations()
        self.assertFalse(any(panel.isVisible() for panel in self.panels))


if __name__ == "__main__":
    unittest.main()
