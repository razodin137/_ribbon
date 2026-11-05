"""Shared constants for Ribbon.

Paths, suffix lists, routes, page limits and the accent colours used to tell
projects apart by kind. Nothing here reaches out to the filesystem or holds
state, so any module can import it without a cycle.
"""

from __future__ import annotations

from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
VERSION = "1.4.0"
HTML_SUFFIXES = (".html", ".htm")
MARKDOWN_SUFFIXES = (".md", ".markdown", ".mdown", ".mkd")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif", ".bmp")
CARD_ROUTE = "/__ribbon/card/"
STATIC_ASSETS = {
    "ribbon.js",
    "bar.js",
    "card.js",
    "card.css",
    "bar.css",
    "markdown.css",
}
PREFERRED_HTML = ("index.html", "app.html", "main.html", "home.html", "site.html", "start.html")
PREFERRED_MARKDOWN = (
    "README.md",
    "readme.md",
    "README.markdown",
    "readme.markdown",
    "README.mdown",
    "readme.mdown",
    "index.md",
)
README_NAMES = ("README.md", "readme.md", "README.markdown", "README.txt", "README", "README.rst")
README_COMMIT_MESSAGE = "Add README"
MAX_README_CHARS = 20000
HANDLER_TIMEOUT = 60
# Below this size a gzip header costs more than the bytes it saves.
GZIP_MIN_BYTES = 512
# One source for the bar's height: the page offset and ribbon.js both read it.
BAR_HEIGHT = 40

TYPE_COLORS = {
    "HTML": "hsl(28 64% 62%)",
    "Markdown": "hsl(250 34% 68%)",
    "Python": "hsl(135 42% 58%)",
    "Shell": "hsl(220 8% 62%)",
    "Node": "hsl(48 58% 60%)",
    "Rust": "hsl(14 60% 60%)",
    "Go": "hsl(190 48% 58%)",
    "Ruby": "hsl(349 52% 62%)",
    "Make": "hsl(282 28% 65%)",
    "Docker": "hsl(205 50% 62%)",
    "Project": "hsl(40 10% 62%)",
    "Folder": "hsl(40 8% 58%)",
}
DEFAULT_TYPE_COLOR = "hsl(40 10% 62%)"


def type_color(app_type: str) -> str:
    """One fixed accent per kind of code, so equal projects look equal."""
    return TYPE_COLORS.get(app_type, DEFAULT_TYPE_COLOR)
