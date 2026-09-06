"""Napari plugin widget factory for Effusive (registered in `napari.yaml`).

`make_main_widget` is the entry point napari's Plugins menu calls to build the
Effusive control widget. It reproduces what the `effusive` CLI does
today (grid view, control widget, standard layers).

napari's npe2 dispatcher only injects a `Viewer` into *class-based* widget
contributions (by inspecting `__init__`); function-based contributions like
this one are always called with zero arguments. `viewer` therefore defaults to
`None` and falls back to `napari.current_viewer()` when called that way; it
still takes `viewer` explicitly when called directly (e.g. from `cli.py`).
"""

from __future__ import annotations

from weakref import WeakKeyDictionary

import napari

from effusive.napari.widget import EffusiveWidget

_main_widgets: WeakKeyDictionary[napari.Viewer, EffusiveWidget] = WeakKeyDictionary()
"""Per-viewer `EffusiveWidget` registry, so reopening the Plugins-menu entry
reuses the existing widget instead of creating a second one that would fight
over the same shared-memory segment names."""


def make_main_widget(viewer: napari.Viewer | None = None) -> EffusiveWidget:
    """Build (or reuse) the Effusive control widget for a viewer.

    Configures the grid view, creates the control widget, and restores its
    standard layers (B-mode, power Doppler, crop ROI).

    Parameters
    ----------
    viewer : napari.Viewer, optional
        Viewer to attach the control widget and layers to. When `None` (the
        case when napari's Plugins menu invokes this factory), resolved via
        `napari.current_viewer()`.

    Returns
    -------
    EffusiveWidget
        The control widget, ready to be docked by napari.

    Raises
    ------
    RuntimeError
        If `viewer` is `None` and there is no current napari viewer.
    """
    if viewer is None:
        viewer = napari.current_viewer()
    if viewer is None:
        raise RuntimeError("make_main_widget() requires an active napari viewer.")

    existing = _main_widgets.get(viewer)
    if existing is not None:
        return existing

    viewer.canvas.overlays.scale_bar.visible = True

    # Show B-mode and PDI side by side in a 1x2 grid.
    viewer.canvas.grid.enabled = True
    viewer.canvas.grid.shape = (1, 2)

    widget = EffusiveWidget(viewer)
    widget._setup_effusive_layers()

    _main_widgets[viewer] = widget
    return widget
