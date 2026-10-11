"""Regression tests for narrow-dock control forms."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from qtpy.QtWidgets import QApplication, QFormLayout, QLabel

from effusive import config
from effusive.napari import controls
from effusive.napari import stack as stack_helpers
from effusive.napari.panels import (
    MetadataPanel,
    ProcessingPanel,
    SequencePanel,
    StackPanel,
    SystemPanel,
)


class PanelFormTests(unittest.TestCase):
    """Keep the real control forms usable at narrow widths."""

    @classmethod
    def setUpClass(cls) -> None:
        """Keep a Qt application alive for all form tests."""
        cls.app = QApplication.instance() or QApplication([])

    def test_all_control_forms_support_wrapping(self) -> None:
        """Cover every form, including those containing nested slider layouts."""
        for panel_type, expected_forms in (
            (SystemPanel, 2),
            (MetadataPanel, 2),
            (SequencePanel, 1),
            (ProcessingPanel, 2),
            (StackPanel, 1),
        ):
            with self.subTest(panel=panel_type.__name__):
                owner = MagicMock()
                owner._config = config.load_default_config()
                owner._worker_cfg = {}
                owner._run_button_state = "ready"
                owner._is_dark.return_value = False
                with (
                    patch.object(config, "save_config"),
                    patch.object(controls, "refresh_control_locks"),
                    patch.object(stack_helpers, "refresh_stack_controls"),
                ):
                    panel = panel_type(owner)
                try:
                    forms = panel.findChildren(QFormLayout)
                    self.assertEqual(len(forms), expected_forms)
                    for form in forms:
                        self.assertEqual(
                            form.rowWrapPolicy(), QFormLayout.RowWrapPolicy.WrapLongRows
                        )
                        self.assertEqual(
                            form.fieldGrowthPolicy(),
                            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow,
                        )
                finally:
                    panel.deleteLater()
                    self.app.processEvents()

    def test_row_wraps_only_when_narrow(self) -> None:
        """Move a label above its field, then restore the wide arrangement."""
        owner = MagicMock()
        owner._config = config.load_default_config()
        owner._worker_cfg = {}
        owner._is_dark.return_value = False
        with patch.object(config, "save_config"):
            panel = SystemPanel(owner)
        try:
            label = next(
                label
                for label in panel.findChildren(QLabel)
                if label.text() == "Acquisition:"
            )
            field = panel._simulate_checkbox
            panel.resize(190, 400)
            panel.show()
            self.app.processEvents()
            self.assertGreater(field.geometry().top(), label.geometry().bottom())
            panel.resize(600, 400)
            self.app.processEvents()
            self.assertGreater(field.geometry().left(), label.geometry().right())
            self.assertLess(field.geometry().top(), label.geometry().bottom())
        finally:
            panel.close()
            panel.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
