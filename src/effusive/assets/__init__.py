"""Effusive assets module.

Contains SVG icons and other static assets used by the application.
"""

from pathlib import Path


def load_svg(name: str) -> str:
    """Load an SVG icon by name.

    Parameters
    ----------
    name : str
        Name of the SVG file (without .svg extension).

    Returns
    -------
    str
        Contents of the SVG file.

    Raises
    ------
    FileNotFoundError
        If the SVG file does not exist.
    """
    svg_path = Path(__file__).parent / f"{name}.svg"
    return svg_path.read_text()
