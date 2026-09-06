"""Panel widgets for the CortexFrame napari widget."""

from cortexframe.napari.panels.common import (
    add_labeled_form_row,
    make_dangerous_label,
    make_lock_hint,
    make_system_info_field,
    mark_dangerous_input,
    mark_dangerous_slider,
)
from cortexframe.napari.panels.data import DataPanel
from cortexframe.napari.panels.metadata import MetadataPanel
from cortexframe.napari.panels.processing import ProcessingPanel
from cortexframe.napari.panels.sequence import SequencePanel
from cortexframe.napari.panels.stack import StackPanel
from cortexframe.napari.panels.system import SystemPanel

__all__ = [
    "DataPanel",
    "MetadataPanel",
    "ProcessingPanel",
    "SequencePanel",
    "StackPanel",
    "SystemPanel",
    "add_labeled_form_row",
    "make_dangerous_label",
    "make_lock_hint",
    "make_system_info_field",
    "mark_dangerous_input",
    "mark_dangerous_slider",
]
