"""Regression tests for sidebar wheel handling, runnable with unittest."""

from __future__ import annotations

import unittest

from qtpy.QtCore import QPoint, QPointF, Qt
from qtpy.QtGui import QWheelEvent
from qtpy.QtTest import QTest
from qtpy.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from effusive.napari.qt import install_no_scroll_wheel_filter


class SidebarWheelTests(unittest.TestCase):
    """Keep sidebar scrolling separate from intentional control edits."""

    @classmethod
    def setUpClass(cls) -> None:
        """Keep one application alive for all Qt tests."""
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        """Build a scrollable panel containing every protected control type."""
        self.scroll = QScrollArea()
        self.scroll.resize(300, 200)
        content = QWidget()
        content.setMinimumHeight(800)
        layout = QVBoxLayout(content)
        self.combo = QComboBox()
        self.combo.addItems(["One", "Two", "Three"])
        self.combo.setCurrentIndex(1)
        self.spin = QSpinBox()
        self.spin.setValue(50)
        self.double_spin = QDoubleSpinBox()
        self.double_spin.setValue(50.0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setValue(50)
        for control in (self.combo, self.spin, self.double_spin, self.slider):
            layout.addWidget(control)
        layout.addStretch()
        self.scroll.setWidget(content)
        self.scroll.setWidgetResizable(True)
        install_no_scroll_wheel_filter(content)
        self.scroll.show()
        self.app.processEvents()

    def tearDown(self) -> None:
        """Dispose of the panel after each test."""
        self.scroll.close()
        self.scroll.deleteLater()
        self.app.processEvents()

    def test_wheel_scrolls_without_changing_controls(self) -> None:
        """Protect all control types in both directions, including focused ones."""
        controls = (self.combo, self.spin, self.double_spin, self.slider)
        for control in controls:
            for focused in (False, True):
                for delta in (-120, 120):
                    with self.subTest(
                        control=type(control).__name__, focused=focused, delta=delta
                    ):
                        if focused:
                            control.setFocus()
                        else:
                            control.clearFocus()
                        scrollbar = self.scroll.verticalScrollBar()
                        scrollbar.setValue(scrollbar.maximum() // 2)
                        before = scrollbar.value()
                        event = QWheelEvent(
                            QPointF(5, 5),
                            QPointF(control.mapToGlobal(QPoint(5, 5))),
                            QPoint(),
                            QPoint(0, delta),
                            Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.NoScrollPhase,
                            False,
                        )
                        QApplication.sendEvent(control, event)
                        self.assertEqual(self.combo.currentIndex(), 1)
                        self.assertEqual(self.spin.value(), 50)
                        self.assertEqual(self.double_spin.value(), 50.0)
                        self.assertEqual(self.slider.value(), 50)
                        if delta < 0:
                            self.assertGreater(scrollbar.value(), before)
                        else:
                            self.assertLess(scrollbar.value(), before)

    def test_keyboard_edits_still_work(self) -> None:
        """Preserve deliberate edits through the keyboard."""
        QTest.keyClick(self.spin, Qt.Key.Key_Up)
        QTest.keyClick(self.double_spin, Qt.Key.Key_Up)
        QTest.keyClick(self.slider, Qt.Key.Key_Right)
        QTest.keyClick(self.combo, Qt.Key.Key_Down)
        self.assertEqual(self.spin.value(), 51)
        self.assertEqual(self.double_spin.value(), 51.0)
        self.assertEqual(self.slider.value(), 51)
        self.assertEqual(self.combo.currentIndex(), 2)


if __name__ == "__main__":
    unittest.main()
