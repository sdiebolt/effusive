"""Console formatting helpers for the Effusive napari UI."""

from __future__ import annotations

from qtpy.QtGui import QColor, QFont, QSyntaxHighlighter, QTextCharFormat


class ConsoleHighlighter(QSyntaxHighlighter):
    """Line-based syntax highlighter for the runtime log panel.

    Parameters
    ----------
    parent : object
        Qt text document or parent object passed to `QSyntaxHighlighter`.
    is_dark : bool
        Whether the current napari theme uses the dark palette.
    """

    def __init__(self, parent, is_dark: bool) -> None:
        """Initialize the highlighter using the current napari theme.

        Parameters
        ----------
        parent : object
            Qt text document or parent object passed to `QSyntaxHighlighter`.
        is_dark : bool
            Whether the current napari theme uses the dark palette.

        Returns
        -------
        None
            This initializer does not return a value.
        """
        super().__init__(parent)
        self._set_palette(is_dark)

    def set_theme(self, is_dark: bool) -> None:
        """Refresh the color palette after a theme change.

        Parameters
        ----------
        is_dark : bool
            Whether the new napari theme uses the dark palette.

        Returns
        -------
        None
            This method updates the formatter state in place.
        """
        self._set_palette(is_dark)
        self.rehighlight()

    def _make_format(self, color: str, *, bold: bool = False, italic: bool = False):
        """Build a Qt text format used by the log highlighter.

        Parameters
        ----------
        color : str
            CSS-style color string used for the foreground color.
        bold : bool, default: False
            Whether to apply bold font weight.
        italic : bool, default: False
            Whether to apply italic font styling.

        Returns
        -------
        QTextCharFormat
            Configured Qt text format for one log token category.
        """
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        if italic:
            fmt.setFontItalic(True)
        return fmt

    def _set_palette(self, is_dark: bool) -> None:
        """Compute source and severity palettes for the active theme.

        Parameters
        ----------
        is_dark : bool
            Whether the active napari theme uses the dark palette.

        Returns
        -------
        None
            This method updates the cached text formats in place.
        """
        if is_dark:
            self._formats = {
                "default": self._make_format("#c8c8d4"),
                "timestamp": self._make_format("#7c7c92"),
                "viewer": self._make_format("#2dd4bf"),
                "worker": self._make_format("#f59e0b"),
                "matlab": self._make_format("#60a5fa"),
                "warning": self._make_format("#fb923c", bold=True),
                "error": self._make_format("#f87171", bold=True),
                "action": self._make_format("#facc15", bold=True),
            }
        else:
            self._formats = {
                "default": self._make_format("#2c2c3a"),
                "timestamp": self._make_format("#7a7a8d"),
                "viewer": self._make_format("#0d9488"),
                "worker": self._make_format("#b45309"),
                "matlab": self._make_format("#2563eb"),
                "warning": self._make_format("#c2410c", bold=True),
                "error": self._make_format("#b91c1c", bold=True),
                "action": self._make_format("#a16207", bold=True),
            }
        self._tag_formats = {
            "default": self._make_format(
                self._formats["default"].foreground().color().name(), bold=True
            ),
            "viewer": self._make_format(
                self._formats["viewer"].foreground().color().name(), bold=True
            ),
            "worker": self._make_format(
                self._formats["worker"].foreground().color().name(), bold=True
            ),
            "matlab": self._make_format(
                self._formats["matlab"].foreground().color().name(), bold=True
            ),
        }

    def highlightBlock(self, text: str | None) -> None:
        """Apply source-aware and severity-aware formatting to one log line.

        Parameters
        ----------
        text : str or None
            One log line supplied by Qt for syntax highlighting.

        Returns
        -------
        None
            This method updates character formatting on the current text block.
        """
        if text is None:
            return
        lower = text.lower()
        source = "default"

        if "[viewer]" in text:
            source = "viewer"
        elif "[worker]" in text:
            source = "worker"
        elif (
            "[matlab]" in text
            or "[effusive]" in text
            or (text.startswith("[") and "] [" not in text)
        ):
            source = "matlab"

        self.setFormat(0, len(text), self._formats[source])

        if len(text) >= 14 and text.startswith("[") and text[13] == "]":
            self.setFormat(0, 14, self._formats["timestamp"])

        search_start = (
            14 if len(text) >= 14 and text.startswith("[") and text[13] == "]" else 0
        )
        source_tag_start = text.find("[", search_start)
        if source_tag_start != -1:
            source_tag_end = text.find("]", source_tag_start)
            if source_tag_end != -1:
                self.setFormat(
                    source_tag_start,
                    source_tag_end - source_tag_start + 1,
                    self._tag_formats.get(source, self._tag_formats["default"]),
                )

        for keyword in ("error", "failed", "traceback", "rejected"):
            start = lower.find(keyword)
            while start != -1:
                self.setFormat(start, len(keyword), self._formats["error"])
                start = lower.find(keyword, start + len(keyword))

        for keyword in ("warning", "timed out", "ignored"):
            start = lower.find(keyword)
            while start != -1:
                self.setFormat(start, len(keyword), self._formats["warning"])
                start = lower.find(keyword, start + len(keyword))

        for keyword in ("requested", "applied", "updated"):
            start = lower.find(keyword)
            while start != -1:
                self.setFormat(start, len(keyword), self._formats["action"])
                start = lower.find(keyword, start + len(keyword))
