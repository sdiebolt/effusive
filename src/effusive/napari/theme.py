"""Theme and icon helpers for the Effusive napari UI."""

from __future__ import annotations

from qtpy.QtCore import QRectF, Qt
from qtpy.QtGui import QIcon, QImage, QPainter, QPixmap
from qtpy.QtSvg import QSvgRenderer as _QSvgRenderer
from qtpy.QtWidgets import QApplication

from effusive.assets import load_svg

ACCENT_DARK = "#2dd4bf"
"""Dark-theme accent color."""

ACCENT_LIGHT = "#0d9488"
"""Light-theme accent color."""


def make_lucide_icon(name: str, color: str, size: int = 16) -> QIcon:
    """Render a small Lucide-style SVG icon tinted with `color`.

    Parameters
    ----------
    name : str
        Asset name resolved through `effusive.assets.load_svg`.
    color : str
        CSS-style color string replacing the SVG's `currentColor` token.
    size : int, default: 16
        Requested icon size in logical pixels before device-pixel-ratio scaling.

    Returns
    -------
    QIcon
        Rendered icon, or an empty icon when the SVG asset is missing.
    """
    try:
        svg = load_svg(name)
    except FileNotFoundError:
        return QIcon()

    svg_bytes = svg.replace("currentColor", color).encode()
    screen = QApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen is not None else 1.0
    px = round(size * dpr)

    renderer = _QSvgRenderer(svg_bytes)
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, px, px))
    painter.end()

    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(dpr)
    return QIcon(pixmap)


def build_stylesheet(is_dark: bool, napari_bg: str | None = None) -> str:
    """Return the full widget stylesheet for the active napari theme.

    Parameters
    ----------
    is_dark : bool
        Whether the active napari theme uses the dark palette.
    napari_bg : str, optional
        Optional background color sampled from napari's current theme.

    Returns
    -------
    str
        Qt stylesheet string for the Effusive widget.
    """
    _ = napari_bg or ("#23232e" if is_dark else "#f3f4f6")
    if is_dark:
        header_bg = napari_bg or "#1c1c27"
        header_bdr = ACCENT_DARK
        accent = ACCENT_DARK
        accent_hover = "#5eead4"
        accent_fg = "#1c1c27"
        danger = "#e76f51"
        danger_hover = "#f08b72"
        warning = "#f4a261"
        warning_hover = "#f6b27b"
        tab_bg = "#2d2d3a"
        tab_sel_bg = "#38384a"
        tab_hvr_bg = "#34344a"
        tab_fg = "#c8c8d4"
        sub_fg = "#888898"
        input_bg = "#2d2d3a"
        input_fg = "#c8c8d4"
        input_bdr = "#3d3d4a"
        btn_bg = "#38384a"
        btn_fg = "#c8c8d4"
        btn_hvr_bg = "#44445a"
        disabled_bg = "#252533"
        disabled_fg = "#747486"
        disabled_bdr = "#343448"
    else:
        header_bg = napari_bg or "#f0f0e8"
        header_bdr = ACCENT_LIGHT
        accent = ACCENT_LIGHT
        accent_hover = "#0f766e"
        accent_fg = "#ffffff"
        danger = "#c84c3c"
        danger_hover = "#d86555"
        warning = "#d97706"
        warning_hover = "#b45309"
        tab_bg = "#e0e0e8"
        tab_sel_bg = "#d4d4e0"
        tab_hvr_bg = "#d8d8e8"
        tab_fg = "#2c2c3a"
        sub_fg = "#505060"
        input_bg = "#e8e8f0"
        input_fg = "#2c2c3a"
        input_bdr = "#c0c0cc"
        btn_bg = "#d4d4e0"
        btn_fg = "#2c2c3a"
        btn_hvr_bg = "#c8c8d8"
        disabled_bg = "#ececf2"
        disabled_fg = "#8e8e9f"
        disabled_bdr = "#d0d0db"

    return f"""
/* ---- Header ---- */
#cf_header {{
    background: {header_bg};
    border-bottom: 2px solid {header_bdr};
}}
#cf_title    {{ color: {accent};  background: transparent; }}
#cf_subtitle {{ color: {sub_fg}; font-size: 11px; background: transparent; }}

/* ---- Disabled widgets ---- */
QPushButton:disabled,
QLineEdit:disabled,
QComboBox:disabled,
QDoubleSpinBox:disabled,
QSpinBox:disabled {{
    background: {disabled_bg};
    color: {disabled_fg};
    border: 1px solid {disabled_bdr};
}}
QCheckBox:disabled,
QLabel#danger_label:disabled {{
    color: {disabled_fg};
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid {input_bdr};
    background: {input_bg};
}}
QCheckBox::indicator:checked {{
    background: {accent};
    border: 1px solid {accent};
}}
QCheckBox::indicator:disabled {{
    background: {disabled_bg};
    border: 1px solid {disabled_bdr};
}}
QCheckBox::indicator:checked:disabled {{
    background: {disabled_bdr};
    border: 1px solid {disabled_bdr};
}}
QCheckBox#toggle_switch::indicator {{
    width: 34px;
    height: 18px;
    border-radius: 9px;
    border: 1px solid {input_bdr};
    background: {disabled_bdr};
}}
QCheckBox#toggle_switch::indicator:checked {{
    background: {accent};
    border: 1px solid {accent};
}}
QCheckBox#toggle_switch::indicator:disabled {{
    background: {disabled_bg};
    border: 1px solid {disabled_bdr};
}}

/* ---- Accordion headers ---- */
QPushButton#accordion_header {{
    background: {tab_bg};
    color: {tab_fg};
    border: none;
    border-radius: 0;
    padding: 8px 12px;
    font-weight: bold;
    font-size: 12px;
    text-align: left;
    margin-bottom: 0;
}}
QPushButton#accordion_header:hover:!checked {{
    background: {tab_hvr_bg};
}}
QPushButton#accordion_header:checked {{
    background: {tab_sel_bg};
    color: {accent};
    border-left: 3px solid {accent};
    padding-left: 9px;
}}
QPushButton#accordion_header:focus {{
    outline: none;
}}

/* ---- Inputs ---- */
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {{
    background: {input_bg};
    color: {input_fg};
    border: 1px solid {input_bdr};
    border-radius: 3px;
    padding: 4px 6px;
}}
QDoubleSpinBox[danger="true"], QSpinBox[danger="true"] {{
    color: {danger};
    border: 1px solid {danger};
    font-weight: bold;
}}
QDoubleSpinBox[danger="true"]:disabled, QSpinBox[danger="true"]:disabled {{
    color: {disabled_fg};
    border: 1px solid {disabled_bdr};
    font-weight: normal;
}}
QCheckBox {{
    color: {input_fg};
    spacing: 6px;
}}
QLabel#danger_label, QLabel[danger="true"] {{
    color: {danger};
    font-weight: bold;
}}
QLabel[control_locked="true"] {{
    color: {disabled_fg};
}}
QLabel#danger_label[control_locked="true"], QLabel[danger="true"][control_locked="true"] {{
    color: {disabled_fg};
    font-weight: normal;
}}
QLabel#lock_hint {{
    color: {sub_fg};
    font-size: 11px;
}}
QLabel#lock_hint[locked="true"] {{
    color: {danger};
    font-weight: bold;
}}
QLabel#cf_info_value {{
    font-family: "DejaVu Sans Mono", "Consolas", "Monaco", monospace;
}}

/* ---- Buttons ---- */
QPushButton {{
    background: {btn_bg};
    color: {btn_fg};
    border: none;
    border-radius: 3px;
    padding: 5px 10px;
}}
QPushButton:hover {{
    background: {btn_hvr_bg};
}}
QPushButton#run_btn_start,
QPushButton#run_btn_stop,
QPushButton#run_btn_busy,
QPushButton#run_btn_disabled,
QPushButton#pause_btn_idle,
QPushButton#pause_btn_paused,
QPushButton#pause_btn_disabled {{
    border-radius: 4px;
    padding: 0px;
    border: none;
}}
QPushButton#run_btn_start {{
    background: {accent};
}}
QPushButton#run_btn_start:hover {{
    background: {accent_hover};
}}
QPushButton#run_btn_stop {{
    background: {danger};
}}
QPushButton#run_btn_stop:hover {{
    background: {danger_hover};
}}
QPushButton#run_btn_busy,
QPushButton#run_btn_disabled {{
    background: {disabled_bg};
    border: 1px solid {disabled_bdr};
}}
QPushButton#pause_btn_idle {{
    background: {btn_bg};
}}
QPushButton#pause_btn_idle:hover {{
    background: {btn_hvr_bg};
}}
QPushButton#pause_btn_paused {{
    background: #d97706;
}}
QPushButton#pause_btn_paused:hover {{
    background: #f59e0b;
}}
QPushButton#pause_btn_disabled,
QPushButton#pause_btn_disabled:disabled {{
    background: {disabled_bg};
    border: 1px dashed {disabled_bdr};
}}
QPushButton#record_btn_idle {{
    background: {accent};
    color: {accent_fg};
    font-weight: bold;
    padding: 6px;
}}
QPushButton#record_btn_idle:hover {{
    background: {accent_hover};
}}
QPushButton#record_btn_recording {{
    background: {danger};
    color: #ffffff;
    font-weight: bold;
    padding: 6px;
}}
QPushButton#record_btn_recording:hover {{
    background: {danger_hover};
}}
QPushButton#record_btn_disabled,
QPushButton#record_btn_disabled:disabled {{
    background: {disabled_bg};
    color: {disabled_fg};
    border: 1px dashed {disabled_bdr};
    font-weight: bold;
    padding: 6px;
}}
QPushButton#stack_btn_start {{
    background: {accent};
    color: {accent_fg};
    font-weight: bold;
    padding: 6px;
}}
QPushButton#stack_btn_start:hover {{
    background: {accent_hover};
}}
QPushButton#stack_btn_abort {{
    background: {danger};
    color: #ffffff;
    font-weight: bold;
    padding: 6px;
}}
QPushButton#stack_btn_abort:hover {{
    background: {danger_hover};
}}
QPushButton#stack_btn_home {{
    background: {warning};
    color: #111111;
    font-weight: bold;
    padding: 6px;
}}
QPushButton#stack_btn_home:hover {{
    background: {warning_hover};
}}
QPushButton#stack_btn_home:disabled {{
    background: {disabled_bg};
    color: {disabled_fg};
    border: 1px solid {disabled_bdr};
    font-weight: normal;
}}
QPushButton#stack_btn_disabled,
QPushButton#stack_btn_disabled:disabled {{
    background: {disabled_bg};
    color: {disabled_fg};
    border: 1px dashed {disabled_bdr};
    font-weight: bold;
    padding: 6px;
}}
QPushButton#crop_btn_apply {{
    background: {accent};
    color: {accent_fg};
    font-weight: bold;
}}
QPushButton#crop_btn_apply:hover {{
    background: {accent_hover};
}}
QPushButton#crop_btn_apply:disabled {{
    background: {disabled_bg};
    color: {disabled_fg};
    border: 1px solid {disabled_bdr};
    font-weight: normal;
}}
QPushButton#crop_btn_reset {{
    background: {danger};
    color: #ffffff;
    font-weight: bold;
}}
QPushButton#crop_btn_reset:hover {{
    background: {danger_hover};
}}
QPushButton#crop_btn_reset:disabled {{
    background: {disabled_bg};
    color: {disabled_fg};
    border: 1px solid {disabled_bdr};
    font-weight: normal;
}}

/* ---- Sliders ---- */
QSlider::handle:horizontal {{
    background: {accent};
    border: none;
    width: 14px;
    height: 14px;
    border-radius: 7px;
    margin: -5px 0;
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {input_bdr};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {accent};
    border-radius: 2px;
}}
QSlider#danger_slider::handle:horizontal {{
    background: {danger};
}}
QSlider#danger_slider::sub-page:horizontal {{
    background: {danger};
}}
QSlider::handle:horizontal:disabled {{
    background: {disabled_bdr};
}}
QSlider::groove:horizontal:disabled,
QSlider::sub-page:horizontal:disabled {{
    background: {disabled_bdr};
}}

/* ---- Log panel ---- */
QPlainTextEdit#log_panel {{
    background: {input_bg};
    color: {input_fg};
    border: 1px solid {input_bdr};
    font-family: monospace;
    font-size: 8pt;
}}
QGroupBox {{
    margin-top: 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    top: 0px;
    padding: 0 4px;
}}
QGroupBox:disabled {{
    color: {disabled_fg};
    border: 1px solid {disabled_bdr};
}}
QGroupBox::title:disabled {{
    color: {disabled_fg};
}}
"""
