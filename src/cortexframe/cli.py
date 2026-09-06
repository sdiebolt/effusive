"""CortexFrame command-line entry point.

Opens a napari viewer with live B-mode and PDI layers and a control dock widget. The
MATLAB worker subprocess is not started automatically: click the play button in the
sidebar after configuring acquisition parameters.

Usage:

```bash
cortexframe
```
"""

from __future__ import annotations

import napari
from qtpy.QtWidgets import QApplication

from cortexframe import config as cf_config
from cortexframe.napari import worker as worker_module
from cortexframe.napari.plugin import make_main_widget


def main() -> None:
    """Run the CortexFrame napari viewer."""
    viewer = napari.Viewer(title="CortexFrame")
    widget = make_main_widget(viewer)
    viewer.window.add_dock_widget(widget, name="CortexFrame", area="right")

    # widget._config is kept live by command handlers and panel connections;
    # saving it here requires no Qt object access so it works even after teardown.
    app = QApplication.instance()
    assert app is not None
    app.aboutToQuit.connect(lambda: cf_config.save_config(widget._config))

    napari.run()

    worker_module.stop_acquisition(widget, from_close=True)


if __name__ == "__main__":
    main()
