#!/usr/bin/env python3
"""
Ribbon — browse a folder of standalone HTML apps with a floating top banner.

Run this from anywhere:

    python3 ribbon.py

Ribbon finds the folder that holds your apps, serves it on a local address,
adds the ribbon bar to every page, and opens the first app. Nothing on disk
is changed.

Handy first commands:

    python3 ribbon.py --list          see what it found
    python3 ribbon.py --help          every option, with examples
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import shlex
import shutil
import subprocess
import threading
import time
import webbrowser
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from functools import lru_cache, partial
from html import escape, unescape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs, quote, unquote, urlsplit

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
STATE_VERSION = 1
STATE_DIR_NAME = "ribbon"
STATE_LOCK = threading.Lock()
KEEPALIVE_TIMEOUT = 60

STATE_LABELS = {
    "clean": "all pushed",
    "dirty": "unsaved changes",
    "ahead": "commits to push",
    "behind": "behind the remote",
    "diverged": "ahead and behind",
    "no-upstream": "not linked to a remote",
    "no-commits": "no commits yet",
    "detached": "detached HEAD",
    "conflicted": "conflicts to resolve",
    "no-repo": "no git",
    "error": "git unavailable",
}

DEFAULT_GITIGNORE = """\
node_modules/
.venv/
venv/
env/
__pycache__/
.cache/
.next/
.turbo/
.parcel-cache/
.scratch/
.DS_Store
dist/
build/
out/
target/
coverage/
*.log
.env
.env.*
!.env.example
"""

SCRATCH_DIRS = (".scratch",)

SECRET_NAMES = {
    ".env",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "id_rsa",
    "id_ed25519",
    "credentials",
    "credentials.json",
}
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
LARGE_FILE_BYTES = 5 * 1024 * 1024
MAX_ACTION_OUTPUT = 4000
MAX_DETAIL_FILES = 200
TREE_MAX_ENTRIES = 700
GITIGNORE_PREVIEW_CHARS = 4000

SKIP_DIRS = {
    "node_modules",
    "venv",
    "env",
    ".venv",
    "__pycache__",
    ".cache",
    ".next",
    ".turbo",
    ".parcel-cache",
    "site-packages",
    "vendor",
    "bower_components",
    "dist",
    "build",
    "out",
    "target",
    "coverage",
}

TREE_SKIP_DESCENT = {".git", *SKIP_DIRS}


def child_dirs(path: Path) -> list[Path]:
    try:
        return [
            entry
            for entry in path.iterdir()
            if entry.is_dir()
            and not entry.name.startswith(".")
            and entry.name not in SKIP_DIRS
            and entry.resolve() != APP_DIR
        ]
    except OSError:
        return []


def is_container(path: Path) -> bool:
    """A folder that only holds projects, like Work/tries."""
    try:
        filenames = [entry.name for entry in path.iterdir() if entry.is_file()]
    except OSError:
        return False
    if choose_html(filenames):
        return False
    kind = project_kind(path, filenames)
    if kind and kind.get("type") != "Project":
        return False
    return bool(child_dirs(path))


def default_root() -> Path:
    """The folder whose child directories Ribbon should list.

    If _ribbon sits in a wrapper folder (Work) beside a single container
    (tries), list the container's children. If _ribbon sits beside the
    projects, list them directly.
    """
    parent = APP_DIR.parent
    children = child_dirs(parent)
    if len(children) == 1 and is_container(children[0]):
        return children[0]
    if children:
        return parent

    grandparent = parent.parent
    if grandparent != parent and child_dirs(grandparent):
        return grandparent
    return parent


TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
META_DESCRIPTION_RE = re.compile(
    rb'<meta\s+[^>]*name\s*=\s*["\']description["\'][^>]*'
    rb'content\s*=\s*["\']([^"\']*)["\']',
    re.IGNORECASE | re.DOTALL,
)
META_DESCRIPTION_FIRST_RE = re.compile(
    rb'<meta\s+[^>]*content\s*=\s*["\']([^"\']*)["\'][^>]*'
    rb'name\s*=\s*["\']description["\']',
    re.IGNORECASE | re.DOTALL,
)
HEAD_CLOSE_RE = re.compile(rb"</head\s*>", re.IGNORECASE)
BODY_OPEN_RE = re.compile(rb"<body\b[^>]*>", re.IGNORECASE)
BODY_CLOSE_RE = re.compile(rb"</body\s*>", re.IGNORECASE)
# Runs right after the declarative shadow bar parses, so it is already in its
# hidden state at first paint. ribbon.js reads the same two keys and takes over.
BOOT_SCRIPT = (
    b"<script>try{"
    b'var h=document.querySelector("[data-ribbon-host]");'
    b"if(h){"
    b'if(sessionStorage.getItem("ribbon:hidden")==="1")'
    b'h.setAttribute("data-ribbon-hidden","");'
    b'else if(sessionStorage.getItem("ribbon:scroll")===location.href)'
    b'h.setAttribute("data-ribbon-scrolled","")'
    b"}}catch(_){}"
    b"</script>"
)

_cache: dict[str, object] = {"at": 0.0, "root": "", "apps": []}


def clean_title(raw: bytes) -> str:
    text = raw.decode("utf-8", "replace")
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return " ".join(text.split())[:160]


def fallback_title(rel_dir: str) -> str:
    name = Path(rel_dir).name or rel_dir
    name = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", name)
    name = name.replace("-", " ").replace("_", " ").strip()
    return name or "Untitled"


@lru_cache(maxsize=2048)
def _page_meta(path: str, mtime_ns: int, size: int) -> tuple[str, str]:
    """Title and description from one read of a page's head.

    The key carries the file stamp, so an edit invalidates the entry. The
    manifest asks for a title on every refresh; without this cache that is a
    fresh read of up to 512 KB per app each time.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(512 * 1024)
    except OSError:
        return "", ""
    title = TITLE_RE.search(head)
    description = META_DESCRIPTION_RE.search(head) or META_DESCRIPTION_FIRST_RE.search(head)
    return (
        clean_title(title.group(1)) if title else "",
        clean_title(description.group(1)) if description else "",
    )


def page_meta(path: Path) -> tuple[str, str]:
    try:
        stat = path.stat()
    except OSError:
        return "", ""
    return _page_meta(str(path), stat.st_mtime_ns, stat.st_size)


def extract_title(path: Path) -> str:
    return page_meta(path)[0]


def extract_description(path: Path) -> str:
    return page_meta(path)[1]


def choose_html(filenames: list[str] | set[str]) -> str | None:
    """Pick the page a folder should open, preferring index.html."""
    names = {name for name in filenames if Path(name).suffix.lower() in HTML_SUFFIXES}
    for preferred in PREFERRED_HTML:
        if preferred in names:
            return preferred
    if not names:
        return None
    return min(names, key=str.lower)


def find_readme(path: Path) -> Path | None:
    """Return the folder's README file, if it has one."""
    for name in README_NAMES:
        candidate = path / name
        if candidate.is_file():
            return candidate
    return None


def read_readme(path: Path) -> str:
    candidate = find_readme(path)
    if candidate:
        try:
            return candidate.read_text(encoding="utf-8", errors="replace")[:12000]
        except OSError:
            pass
    return ""


def readme_state(path: Path) -> dict:
    found = find_readme(path)
    return {
        "exists": bool(found),
        "name": found.name if found else "README.md",
    }


def clean_markdown(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[*_`>#|]", "", text)
    return " ".join(unescape(text).split())[:220]


def choose_markdown(filenames: list[str] | set[str]) -> str | None:
    """Pick the Markdown file a folder should show."""
    names = {
        name: name
        for name in filenames
        if Path(name).suffix.lower() in MARKDOWN_SUFFIXES
    }
    if not names:
        return None
    lowered = {name.lower(): name for name in names}
    for preferred in PREFERRED_MARKDOWN:
        if preferred.lower() in lowered:
            return lowered[preferred.lower()]
    return min(names, key=str.lower)


def read_markdown(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:250000]
    except OSError:
        return ""


def markdown_summary(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    title = ""
    lines: list[str] = []
    started = False
    for raw in text.splitlines():
        line = raw.strip()
        if not title and line.startswith("#"):
            title = clean_markdown(line.lstrip("#").strip())
            continue
        if not line:
            if started:
                break
            continue
        if line.startswith(("```", "~~~", "|", "---", "<", "![")):
            if started:
                break
            continue
        lines.append(line)
        started = True
        if len(" ".join(lines)) > 220:
            break
    return title, clean_markdown(" ".join(lines))


def readme_summary(path: Path) -> tuple[str, str]:
    return markdown_summary(read_readme(path))


def _safe_url(url: str) -> str:
    value = unescape(url).strip()
    if re.match(r"(?i)^(?:javascript|vbscript|data):", value):
        return "#"
    return url


def _inline_markdown(text: str) -> str:
    codes: list[str] = []

    def stash_code(match: re.Match) -> str:
        codes.append("<code>" + escape(match.group(1)) + "</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`\n]+)`", stash_code, text)
    text = escape(text)

    def image(match: re.Match) -> str:
        alt = match.group(1)
        target = _safe_url(match.group(2).split()[0] if match.group(2).split() else "")
        return f'<img src="{target}" alt="{alt}" loading="lazy">'

    def link(match: re.Match) -> str:
        label = match.group(1)
        target = _safe_url(match.group(2).split()[0] if match.group(2).split() else "")
        return f'<a href="{target}">{label}</a>'

    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", image, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, text)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"__([^_\n]+)__", r"<strong>\1</strong>", text)
    text = re.sub(r"~~([^~\n]+)~~", r"<del>\1</del>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<em>\1</em>", text)
    for index, code in enumerate(codes):
        text = text.replace(f"\x00{index}\x00", code)
    return text


LIST_RE = re.compile(r"^(\s*)([-+*]|\d+[.)])\s+(.*)$")
FENCE_RE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")
HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
SETEXT_RE = re.compile(r"^\s{0,3}(=+|-+)\s*$")
RULE_RE = re.compile(
    r"^\s{0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$"
)
TABLE_SEP_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)


def _table_cells(line: str) -> list[str]:
    row = line.strip()
    row = row.removeprefix("|")
    row = row.removesuffix("|")
    return [cell.strip() for cell in row.split("|")]


def _render_table(lines: list[str], index: int) -> tuple[str, int]:
    headers = _table_cells(lines[index])
    alignments: list[str] = []
    for cell in _table_cells(lines[index + 1]):
        if cell.startswith(":") and cell.endswith(":"):
            alignments.append("center")
        elif cell.endswith(":"):
            alignments.append("right")
        elif cell.startswith(":"):
            alignments.append("left")
        else:
            alignments.append("")
    index += 2
    rows: list[list[str]] = []
    while index < len(lines) and lines[index].strip() and "|" in lines[index]:
        rows.append(_table_cells(lines[index]))
        index += 1

    def cell(tag: str, value: str, position: int) -> str:
        align = alignments[position] if position < len(alignments) else ""
        style = f' style="text-align: {align}"' if align else ""
        return f"<{tag}{style}>{_inline_markdown(value)}</{tag}>"

    head = "".join(cell("th", value, i) for i, value in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(cell("td", value, i) for i, value in enumerate(row)) + "</tr>"
        for row in rows
    )
    table = (
        "<div class=\"rc-table-wrap\"><table><thead><tr>"
        + head
        + "</tr></thead><tbody>"
        + body
        + "</tbody></table></div>"
    )
    return table, index


def _render_list(lines: list[str], index: int) -> tuple[str, int]:
    first = LIST_RE.match(lines[index])
    assert first is not None
    base_indent = len(first.group(1))
    ordered = first.group(2)[0].isdigit()
    start_number = int(re.match(r"\d+", first.group(2)).group()) if ordered else 1
    items: list[str] = []

    while index < len(lines):
        match = LIST_RE.match(lines[index])
        if not match:
            break
        indent = len(match.group(1))
        marker = match.group(2)
        if indent != base_indent or marker[0].isdigit() != ordered:
            break
        content = [match.group(3)]
        item_indent = indent + len(marker) + 1
        index += 1
        while index < len(lines):
            following = lines[index]
            if not following.strip():
                lookahead = index
                while lookahead < len(lines) and not lines[lookahead].strip():
                    lookahead += 1
                if lookahead < len(lines):
                    next_item = LIST_RE.match(lines[lookahead])
                    if next_item and len(next_item.group(1)) == base_indent:
                        break
                    if next_item and len(next_item.group(1)) > base_indent:
                        content.append("")
                        index = lookahead
                        continue
                    if len(lines[lookahead]) - len(lines[lookahead].lstrip()) > base_indent:
                        content.append("")
                        index = lookahead
                        continue
                break
            next_item = LIST_RE.match(following)
            if next_item and len(next_item.group(1)) == base_indent:
                break
            leading = len(following) - len(following.lstrip())
            if leading > base_indent:
                content.append(
                    following[item_indent:]
                    if len(following) >= item_indent
                    else following.lstrip()
                )
                index += 1
                continue
            break
        items.append("\n".join(content))

    rendered: list[str] = []
    for item in items:
        task = ""
        task_match = re.match(r"^\[([ xX])\]\s+(.*)$", item, re.DOTALL)
        if task_match:
            checked = task_match.group(1).lower() == "x"
            task = '<input type="checkbox" disabled' + (" checked" if checked else "") + "> "
            item = task_match.group(2)
        body = _render_blocks(item).strip()
        if body.startswith("<p>"):
            end = body.find("</p>")
            if end != -1:
                body = body[3:end] + body[end + 4 :]
        rendered.append("<li>" + task + body + "</li>")

    if ordered:
        start = f' start="{start_number}"' if start_number != 1 else ""
        return "<ol" + start + ">" + "".join(rendered) + "</ol>", index
    return "<ul>" + "".join(rendered) + "</ul>", index


def _is_block_start(lines: list[str], index: int) -> bool:
    line = lines[index]
    if not line.strip():
        return True
    if FENCE_RE.match(line) or HEADING_RE.match(line) or RULE_RE.match(line):
        return True
    if line.lstrip().startswith(">") or LIST_RE.match(line):
        return True
    if index + 1 < len(lines) and SETEXT_RE.match(lines[index + 1]):
        return True
    return "|" in line and index + 1 < len(lines) and bool(
        TABLE_SEP_RE.match(lines[index + 1])
    )


def _render_blocks(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    output: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue

        fence = FENCE_RE.match(line)
        if fence:
            marker = fence.group(1)
            info = fence.group(2).strip()
            code: list[str] = []
            index += 1
            closing = re.compile(
                r"^\s{0,3}" + re.escape(marker[0]) + r"{" + str(len(marker)) + r",}\s*$"
            )
            while index < len(lines) and not closing.match(lines[index]):
                code.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            language = info.split()[0] if info else ""
            css = f' class="language-{escape(language)}"' if language else ""
            output.append(
                "<pre><code" + css + ">" + escape("\n".join(code)) + "</code></pre>"
            )
            continue

        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            output.append(
                f"<h{level}>{_inline_markdown(heading.group(2))}</h{level}>"
            )
            index += 1
            continue

        if (
            index + 1 < len(lines)
            and SETEXT_RE.match(lines[index + 1])
            and line.strip()
            and not LIST_RE.match(line)
        ):
            level = 1 if lines[index + 1].strip().startswith("=") else 2
            output.append(
                f"<h{level}>{_inline_markdown(line.strip())}</h{level}>"
            )
            index += 2
            continue

        if RULE_RE.match(line):
            output.append("<hr>")
            index += 1
            continue

        if line.lstrip().startswith(">"):
            quote: list[str] = []
            while index < len(lines) and (
                lines[index].lstrip().startswith(">") or not lines[index].strip()
            ):
                quote.append(re.sub(r"^\s{0,3}>\s?", "", lines[index]))
                index += 1
            output.append(
                "<blockquote>" + _render_blocks("\n".join(quote)) + "</blockquote>"
            )
            continue

        if "|" in line and index + 1 < len(lines) and TABLE_SEP_RE.match(lines[index + 1]):
            table, index = _render_table(lines, index)
            output.append(table)
            continue

        if LIST_RE.match(line):
            listing, index = _render_list(lines, index)
            output.append(listing)
            continue

        if line.startswith(("    ", "\t")):
            code = []
            while index < len(lines) and (
                lines[index].startswith("    ")
                or lines[index].startswith("\t")
                or not lines[index].strip()
            ):
                code.append(
                    lines[index][4:]
                    if lines[index].startswith("    ")
                    else lines[index].lstrip("\t")
                )
                index += 1
            while code and not code[-1].strip():
                code.pop()
            output.append("<pre><code>" + escape("\n".join(code)) + "</code></pre>")
            continue

        paragraph = [line.strip()]
        index += 1
        while (
            index < len(lines)
            and lines[index].strip()
            and not _is_block_start(lines, index)
        ):
            paragraph.append(lines[index].strip())
            index += 1
        output.append("<p>" + _inline_markdown(" ".join(paragraph)) + "</p>")

    return "\n".join(output)


def render_markdown(text: str) -> str:
    return _render_blocks(text)


def markdown_title(text: str, rel_path: str) -> str:
    title, _ = markdown_summary(text)
    if title:
        return title
    path = Path(rel_path)
    stem = path.stem
    if stem.lower().startswith("readme"):
        parent = path.parent.as_posix()
        return fallback_title("" if parent == "." else parent)
    return fallback_title(stem)


def markdown_view_html(rel_path: str, text: str) -> str:
    path = Path(rel_path)
    folder = path.parent.as_posix()
    folder_label = "/" if folder in ("", ".") else "/" + folder + "/"
    return (
        '<main class="rc-doc">'
        '<header class="rc-doc-head">'
        '<p class="rc-kicker">Markdown</p>'
        '<p class="rc-doc-path">'
        + escape(folder_label)
        + "<span>"
        + escape(path.name)
        + "</span></p>"
        "</header>"
        '<article class="rc-markdown">'
        + render_markdown(text)
        + "</article>"
        "</main>"
    )


def project_kind(path: Path, filenames: list[str]) -> dict | None:
    """Guess what kind of non-web project a folder holds."""
    names = {name.lower(): name for name in filenames}
    files = sorted(name for name in filenames if not name.startswith("."))
    py_files = sorted(name for name in files if name.lower().endswith(".py"))
    js_files = sorted(
        name
        for name in files
        if name.lower().endswith((".js", ".mjs", ".cjs", ".ts"))
    )
    sh_files = sorted(name for name in files if name.lower().endswith(".sh"))

    def pick(*candidates: str) -> str | None:
        for candidate in candidates:
            if candidate.lower() in names:
                return names[candidate.lower()]
        return None

    if "cargo.toml" in names:
        return {"type": "Rust", "icon": "RS", "run": "cargo run"}
    if "go.mod" in names:
        return {"type": "Go", "icon": "GO", "run": "go run ."}
    if "package.json" in names:
        run = "npm start"
        try:
            data = json.loads((path / names["package.json"]).read_text(encoding="utf-8"))
            scripts = data.get("scripts") if isinstance(data, dict) else None
            if (
                isinstance(scripts, dict)
                and "start" not in scripts
                and "dev" in scripts
            ):
                run = "npm run dev"
        except (OSError, ValueError):
            pass
        return {"type": "Node", "icon": "JS", "run": run}
    if pick("pyproject.toml", "requirements.txt", "setup.py", "main.py", "manage.py") or py_files:
        entry = pick("main.py", "app.py", "cli.py", "__main__.py") or (
            py_files[0] if py_files else ""
        )
        run = f"python3 {entry}" if entry else "python3 ."
        return {"type": "Python", "icon": "PY", "run": run}
    if "gemfile" in names:
        return {"type": "Ruby", "icon": "RB", "run": "bundle install"}
    if pick("makefile", "makefile.am", "justfile"):
        return {"type": "Make", "icon": "MK", "run": "make"}
    if pick("dockerfile", "docker-compose.yml", "compose.yml", "compose.yaml"):
        return {"type": "Docker", "icon": "DK", "run": "docker compose up"}
    if sh_files:
        entry = pick("run.sh", "start.sh", "main.sh") or sh_files[0]
        return {"type": "Shell", "icon": "SH", "run": f"./{entry}"}
    if js_files:
        entry = pick("index.js", "main.js", "server.js", "app.js") or js_files[0]
        return {"type": "Node", "icon": "JS", "run": f"node {entry}"}
    if pick("readme.txt", "readme.rst", "readme"):
        return {"type": "Project", "icon": "MD", "run": ""}
    return None


def folder_entries(path: Path) -> list[str]:
    entries: list[str] = []
    try:
        children = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
    except OSError:
        return entries
    for child in children:
        if child.name.startswith(".") or child.is_symlink():
            continue
        if child.is_dir():
            if child.name in SKIP_DIRS:
                continue
            entries.append(child.name + "/")
        else:
            entries.append(child.name)
        if len(entries) >= 14:
            break
    return entries


def _likely_secret(name: str) -> bool:
    lowered = name.lower()
    return (
        lowered in SECRET_NAMES
        or (
            lowered.startswith(".env.")
            and lowered not in {".env.example", ".env.sample", ".env.template"}
        )
        or lowered.endswith(SECRET_SUFFIXES)
    )


def _gitignore_patterns(root: Path) -> list[tuple[bool, str]]:
    try:
        text = (root / ".gitignore").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    patterns: list[tuple[bool, str]] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        negated = line.startswith("!")
        if negated:
            line = line[1:]
        line = line.strip()
        if line:
            patterns.append((negated, line))
    return patterns


def _plain_ignored(rel: str, is_dir: bool, patterns: list[tuple[bool, str]]) -> bool:
    ignored = False
    parts = rel.split("/")
    for negated, pattern in patterns:
        anchored = pattern.startswith("/")
        dir_only = pattern.endswith("/")
        core = pattern.rstrip("/").lstrip("/")
        if not core:
            continue
        candidates = [ "/".join(parts) ] if anchored or "/" in core else parts
        matched = any(fnmatchcase(candidate, core) for candidate in candidates)
        if not matched and "/" in core:
            for index in range(1, len(parts)):
                if fnmatchcase("/".join(parts[:index]), core):
                    matched = True
                    break
        if matched and dir_only and not is_dir:
            matched = any(fnmatchcase(candidate, core) for candidate in parts[:-1])
        if matched:
            ignored = not negated
    return ignored


def _git_check_ignored(root: Path, paths: list[str]) -> set[str]:
    if not paths:
        return set()
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "--stdin", "--no-index", "-z"],
            input="\0".join(paths).encode("utf-8"),
            capture_output=True,
            timeout=6,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    if proc.returncode not in (0, 1):
        return set()
    return {item for item in proc.stdout.decode("utf-8", "replace").split("\0") if item}


def _gitignore_source(path: Path, root: Path, repo: bool) -> tuple[Path | None, str]:
    if (path / ".gitignore").is_file():
        return path / ".gitignore", ".gitignore"
    if repo and root != path and (root / ".gitignore").is_file():
        return root / ".gitignore", "repo root .gitignore"
    return None, ""


def folder_tree(path: Path) -> dict:
    """Every entry in the folder, hidden ones included, with ignore status."""
    repo_root = _git_text(path, ["rev-parse", "--show-toplevel"])
    repo = bool(repo_root)
    root = Path(repo_root) if repo else path
    try:
        prefix = path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        prefix = ""
    if prefix == ".":
        prefix = ""

    entries: list[dict] = []
    truncated = False

    def walk(current: Path, depth: int) -> None:
        nonlocal truncated
        if len(entries) >= TREE_MAX_ENTRIES:
            truncated = True
            return
        try:
            children = sorted(
                current.iterdir(),
                key=lambda item: (not item.is_dir(), item.name.lower()),
            )
        except OSError:
            return
        for child in children:
            if len(entries) >= TREE_MAX_ENTRIES:
                truncated = True
                return
            link = child.is_symlink()
            try:
                is_dir = child.is_dir() and not link
                size = 0 if is_dir else child.stat().st_size
            except OSError:
                continue
            name = child.name
            entries.append({
                "name": name,
                "path": child.relative_to(path).as_posix(),
                "dir": is_dir,
                "depth": depth,
                "hidden": name.startswith("."),
                "link": link,
                "size": size,
                "secret": _likely_secret(name),
            })
            if is_dir and name not in TREE_SKIP_DESCENT:
                walk(child, depth + 1)

    walk(path, 0)

    if repo:
        inputs = [
            f"{prefix}/{entry['path']}" if prefix else entry["path"]
            for entry in entries
        ]
        ignored = _git_check_ignored(root, inputs)
        for entry, rel in zip(entries, inputs):
            entry["ignored"] = rel in ignored
    else:
        patterns = _gitignore_patterns(path)
        for entry in entries:
            entry["ignored"] = _plain_ignored(entry["path"], entry["dir"], patterns)

    source, label = _gitignore_source(path, root, repo)
    try:
        gitignore = source.read_text(encoding="utf-8", errors="replace")[
            :GITIGNORE_PREVIEW_CHARS
        ] if source else ""
    except OSError:
        gitignore = ""
        source = None

    sensitive = [
        entry["path"]
        for entry in entries
        if entry["secret"] and not entry["ignored"]
    ][:5]

    return {
        "entries": entries,
        "count": len(entries),
        "truncated": truncated,
        "repo": repo,
        "hidden_count": sum(1 for entry in entries if entry["hidden"]),
        "ignored_count": sum(1 for entry in entries if entry["ignored"]),
        "sensitive": sensitive,
        "gitignore": gitignore,
        "gitignore_present": source is not None,
        "gitignore_label": label,
    }


def folder_stats(path: Path) -> dict:
    """A compact, visual summary of one folder: types, sizes, recent items."""
    try:
        children = [
            entry
            for entry in path.iterdir()
            if not entry.name.startswith(".")
        ]
    except OSError:
        children = []

    items: list[dict] = []
    folders = 0
    total = 0
    for child in children:
        if child.is_dir():
            if child.name in SKIP_DIRS:
                continue
            folders += 1
            try:
                mtime = int(child.stat().st_mtime)
            except OSError:
                mtime = 0
            items.append({
                "name": child.name,
                "dir": True,
                "size": 0,
                "mtime": mtime,
            })
            continue
        try:
            stat = child.stat()
        except OSError:
            continue
        items.append({
            "name": child.name,
            "dir": False,
            "size": stat.st_size,
            "mtime": int(stat.st_mtime),
        })
        total += stat.st_size

    types: dict[str, dict] = {}
    files = 0
    for item in items:
        if item["dir"]:
            continue
        files += 1
        ext = Path(item["name"]).suffix.lower().lstrip(".") or "file"
        bucket = types.setdefault(ext, {"ext": ext, "count": 0, "size": 0})
        bucket["count"] += 1
        bucket["size"] += item["size"]

    recent = sorted(items, key=lambda item: item["mtime"], reverse=True)[:8]
    images = [
        item["name"]
        for item in items
        if not item["dir"] and Path(item["name"]).suffix.lower() in IMAGE_SUFFIXES
    ][:6]
    return {
        "files": files,
        "folders": folders,
        "size": total,
        "types": sorted(
            types.values(), key=lambda item: (-item["count"], item["ext"])
        )[:6],
        "recent": recent,
        "images": images,
    }


def folder_info(path: Path, rel_dir: str) -> dict:
    """A folder that has no page, project signature, or document."""
    return {
        "kind": "project",
        "title": fallback_title(rel_dir),
        "description": "",
        "type": "Folder",
        "icon": "DIR",
        "run": "",
        "files": folder_entries(path),
        "stats": folder_stats(path),
        "color": type_color("Folder"),
    }


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


def markdown_info(path: Path, rel_dir: str) -> dict | None:
    try:
        filenames = [entry.name for entry in path.iterdir() if entry.is_file()]
    except OSError:
        return None
    name = choose_markdown(filenames)
    if not name:
        return None
    text = read_markdown(path / name)
    rel_path = name if rel_dir == "." else f"{rel_dir}/{name}"
    return {
        "kind": "markdown",
        "title": markdown_title(text, rel_path),
        "description": markdown_summary(text)[1],
        "type": "Markdown",
        "icon": "MD",
        "run": "",
        "files": folder_entries(path),
        "stats": folder_stats(path),
        "color": type_color("Markdown"),
        "markdown_path": rel_path,
    }


def project_info(path: Path, rel_dir: str) -> dict | None:
    try:
        filenames = [entry.name for entry in path.iterdir() if entry.is_file()]
    except OSError:
        return None
    kind = project_kind(path, filenames)
    if not kind:
        return markdown_info(path, rel_dir)
    title, description = readme_summary(path)
    return {
        "kind": "project",
        "title": title or fallback_title(rel_dir),
        "description": description,
        "type": kind["type"],
        "icon": kind["icon"],
        "run": kind["run"],
        "files": folder_entries(path),
        "stats": folder_stats(path),
        "color": type_color(kind["type"]),
    }


GIT_CACHE: dict[str, tuple[float, dict]] = {}
GIT_STATUS_LOCKS: dict[str, threading.Lock] = {}
GIT_STATUS_LOCKS_GUARD = threading.Lock()
GIT_CACHE_SECONDS = 2.0
# A cold manifest pays for one `git status` per folder. Running a handful at
# once turns that serial wait into roughly the slowest repo instead of the sum.
GIT_STATUS_WORKERS = 8
# The bar redraws on every page load. Re-scanning every repository each time
# makes a fast click feel like a stall, so the manifest reuses Git lights for
# a few seconds. The Git panel still asks for fresh detail when it opens.
GIT_LIGHT_SECONDS = 10.0

GIT_LOCKS: dict[str, threading.Lock] = {}
GIT_LOCKS_GUARD = threading.Lock()


def repo_lock(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with GIT_LOCKS_GUARD:
        lock = GIT_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            GIT_LOCKS[key] = lock
        return lock


def _git(path: Path, args: list[str], timeout: float = 4) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    return subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
        check=False,
    )


def _git_text(path: Path, args: list[str], timeout: float = 4) -> str:
    try:
        proc = _git(path, args, timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def read_git_status(path: Path) -> dict:
    """Return one coarse state word, plus the flags behind it.

    `state` answers "what is the most urgent thing about this repo?" and the
    checks below are ordered, so the first true one wins. Branch and history
    states come before "dirty", which means any of them hides uncommitted work
    from that word. Read `dirty` and `dirty_count` when the working tree
    matters; never infer them from `state`.
    """
    try:
        proc = _git(
            path,
            [
                "-c",
                "core.quotePath=false",
                "status",
                "--porcelain=v1",
                "--branch",
                "--untracked-files=normal",
            ],
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"repo": False, "state": "error"}

    if proc.returncode != 0:
        return {"repo": False, "state": "no-repo"}

    lines = proc.stdout.splitlines()
    header = lines[0] if lines else ""
    file_lines = lines[1:]
    dirty = bool(file_lines)
    branch_info = header[3:] if header.startswith("## ") else ""

    tracking = ""
    if " [" in branch_info and branch_info.endswith("]"):
        branch_info, tracking = branch_info[:-1].split(" [", 1)

    branch = None
    upstream = None
    detached = False
    no_commits = False

    if branch_info == "HEAD (no branch)":
        detached = True
    elif branch_info.startswith("No commits yet on "):
        no_commits = True
        branch = branch_info[len("No commits yet on ") :]
    elif "..." in branch_info:
        branch, upstream = branch_info.split("...", 1)
    else:
        branch = branch_info or None

    ahead = 0
    behind = 0
    for match in re.finditer(r"(ahead|behind) (\d+)", tracking):
        if match.group(1) == "ahead":
            ahead = int(match.group(2))
        else:
            behind = int(match.group(2))

    conflicted = any(line[:2] in {"UU", "AA", "DD", "AU", "UA", "DU", "UD"} for line in file_lines)
    gone = "gone" in tracking
    # Ordered on purpose: everything above "dirty" is about the branch or the
    # history, so it wins the one-word label. See the docstring.
    if detached:
        state = "detached"
    elif no_commits:
        state = "no-commits"
    elif conflicted:
        state = "conflicted"
    elif ahead and behind:
        state = "diverged"
    elif ahead:
        state = "ahead"
    elif behind:
        state = "behind"
    elif not upstream or gone:
        state = "no-upstream"
    elif dirty:
        state = "dirty"
    else:
        state = "clean"

    remotes: list[str] = []
    if not detached:
        remotes = [line.strip() for line in _git_text(path, ["remote"]).splitlines() if line.strip()]

    return {
        "repo": True,
        "branch": branch,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "dirty": dirty,
        "dirty_count": len(file_lines),
        "conflicted": conflicted,
        "has_remote": bool(remotes),
        "remotes": remotes,
        "state": state,
    }


def _git_status_lock(key: str) -> threading.Lock:
    with GIT_STATUS_LOCKS_GUARD:
        lock = GIT_STATUS_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            GIT_STATUS_LOCKS[key] = lock
        return lock


def git_status(path: Path, max_age: float = GIT_CACHE_SECONDS) -> dict:
    key = str(path.resolve())
    cached = GIT_CACHE.get(key)
    if cached and time.monotonic() - cached[0] < max_age:
        return cached[1]

    # Prerendered neighbours ask for the manifest at the same moment. One
    # lock per repo stops them running the same `git status` in parallel;
    # whoever loses the race takes the fresh cache entry.
    with _git_status_lock(key):
        cached = GIT_CACHE.get(key)
        if cached and time.monotonic() - cached[0] < max_age:
            return cached[1]
        status = read_git_status(path)
        GIT_CACHE[key] = (time.monotonic(), status)
        return status


def list_folder_files(root: Path) -> list[dict]:
    files: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name != ".git" and name not in SKIP_DIRS
        )
        for name in sorted(filenames):
            rel = (Path(dirpath) / name).relative_to(root).as_posix()
            files.append({"code": "?", "path": rel})
            if len(files) >= MAX_DETAIL_FILES:
                return files
    return files


def parse_status_files(output: str) -> list[dict]:
    files: list[dict] = []
    for line in output.splitlines():
        if not line or line.startswith("## "):
            continue
        code = line[:2]
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip().strip('"')
        if path:
            files.append({"code": code, "path": path})
        if len(files) >= MAX_DETAIL_FILES:
            break
    return files


def _git_ignored(path: Path, relative: str) -> bool:
    try:
        proc = _git(path, ["check-ignore", "-q", "--", relative], 4)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _git_tracked(path: Path, relative: str) -> bool:
    return bool(_git_text(path, ["ls-files", "--", relative]))


def _git_in_head(path: Path, relative: str) -> bool:
    return bool(_git_text(path, ["ls-tree", "--name-only", "HEAD", "--", relative]))


def find_scratch_dirs(root: Path) -> list[Path]:
    """Every .scratch folder under root, skipping build and vendor folders."""
    found: list[Path] = []
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = sorted(
            name for name in dirnames if name != ".git" and name not in SKIP_DIRS
        )
        for name in SCRATCH_DIRS:
            if name in dirnames:
                found.append(Path(dirpath) / name)
                dirnames.remove(name)
    return found


def _plain_gitignore_covers(root: Path, name: str) -> bool:
    """Best-effort .gitignore check for folders that are not a repo yet."""
    try:
        text = (root / ".gitignore").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "!")):
            continue
        pattern = line.lstrip("/").rstrip("/")
        if pattern in (name, f"{name}/*", f"**/{name}", "*", ".*"):
            return True
    return False


def scratch_warnings(root: Path, repo: bool) -> list[str]:
    warnings: list[str] = []
    for target in find_scratch_dirs(root):
        rel = target.relative_to(root).as_posix()
        label = rel + "/"
        if repo and _git_tracked(root, rel):
            warnings.append(
                f"{label} is tracked by Git and would be published. "
                f"Remove it with: git rm -r --cached {rel}"
            )
            continue
        if repo and _git_ignored(root, rel):
            continue
        if not repo and _plain_gitignore_covers(root, target.name):
            continue
        warnings.append(
            f"{label} is not gitignored — add {rel}/ to .gitignore "
            "so it is not published."
        )
    return warnings


def gitignore_requirement(root: Path, include_untracked: bool = True) -> str | None:
    """Block commits and pushes that would publish a .scratch folder."""
    for target in find_scratch_dirs(root):
        rel = target.relative_to(root).as_posix()
        if _git_tracked(root, rel):
            return (
                f"{rel}/ is tracked by Git, so its files would be published.\n"
                f"Remove it from the repository first:\n"
                f"  git rm -r --cached {rel}\n"
                f"  printf '{rel}/\\n' >> .gitignore"
            )
        if include_untracked and not _git_ignored(root, rel):
            return (
                f"{rel}/ is not gitignored, so it would be committed.\n"
                f"Add it to .gitignore first:\n"
                f"  printf '{rel}/\\n' >> .gitignore"
            )
    return None


def file_warnings(root: Path, files: list[dict], repo: bool = False) -> list[str]:
    warnings: list[str] = []
    if files and not (root / ".gitignore").is_file():
        warnings.append("No .gitignore — generated folders may be committed.")
    warnings.extend(scratch_warnings(root, repo))

    secrets_found: list[str] = []
    large_found: list[str] = []
    for item in files:
        name = Path(item["path"]).name.lower()
        likely_secret = (
            name in SECRET_NAMES
            or (name.startswith(".env.") and name not in {".env.example", ".env.sample", ".env.template"})
            or name.endswith(SECRET_SUFFIXES)
        )
        if likely_secret:
            secrets_found.append(item["path"])
        try:
            target = root / item["path"]
            if target.is_file() and target.stat().st_size > LARGE_FILE_BYTES:
                large_found.append(item["path"])
        except OSError:
            pass

    if secrets_found:
        warnings.append("Possible secrets: " + ", ".join(secrets_found[:5]))
    if large_found:
        warnings.append("Large files (over 5 MB): " + ", ".join(large_found[:5]))
    return warnings


def git_detail(path: Path) -> dict:
    status = read_git_status(path)
    GIT_CACHE[str(path.resolve())] = (time.monotonic(), status)
    identity_ok = bool(_git_text(path, ["config", "user.name"])) and bool(
        _git_text(path, ["config", "user.email"])
    )
    detail = {
        **status,
        "root": None,
        "files": [],
        "warnings": [],
        "identity_ok": identity_ok,
        "has_gitignore": (path / ".gitignore").is_file(),
        "readme": readme_state(path),
        "gh": bool(shutil.which("gh")),
    }
    if not status.get("repo"):
        files = list_folder_files(path)
        detail["root"] = str(path)
        detail["files"] = files
        detail["dirty_count"] = len(files)
        detail["warnings"] = file_warnings(path, files)
        detail["pages"] = pages_detail(path)
        return detail

    root_text = _git_text(path, ["rev-parse", "--show-toplevel"])
    root = Path(root_text) if root_text else path
    files: list[dict] = []
    try:
        proc = _git(
            root,
            [
                "-c",
                "core.quotePath=false",
                "status",
                "--porcelain=v1",
                "--branch",
                "--untracked-files=normal",
            ],
            timeout=8,
        )
        if proc.returncode == 0:
            files = parse_status_files(proc.stdout)
    except (OSError, subprocess.TimeoutExpired):
        pass

    detail["root"] = str(root)
    detail["remote_url"] = _git_text(root, ["remote", "get-url", "origin"]) or None
    detail["files"] = files
    detail["dirty_count"] = len(files)
    detail["warnings"] = file_warnings(root, files, repo=True)
    detail["has_gitignore"] = (root / ".gitignore").is_file()
    detail["readme"] = readme_state(root)
    detail["identity_ok"] = bool(_git_text(root, ["config", "user.name"])) and bool(
        _git_text(root, ["config", "user.email"])
    )
    detail["pages"] = pages_detail(root, repo=True)
    return detail


def _action_error(message: str, output: str = "") -> dict:
    return {"ok": False, "error": message, "output": output[-MAX_ACTION_OUTPUT:]}


def _action_ok(output: str) -> dict:
    return {"ok": True, "error": None, "output": output[-MAX_ACTION_OUTPUT:]}


def _run_git_step(path: Path, args: list[str], timeout: float) -> tuple[bool, str]:
    try:
        proc = _git(path, args, timeout)
    except subprocess.TimeoutExpired:
        return False, "Git took too long and was stopped."
    except OSError as exc:
        return False, str(exc)
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part).strip()
    return proc.returncode == 0, output


def _run_command(cmd: list[str], cwd: Path, timeout: float) -> tuple[bool, str]:
    env = os.environ.copy()
    env["GH_PROMPT_DISABLED"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "The command took too long and was stopped."
    except OSError as exc:
        return False, str(exc)
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part).strip()
    return proc.returncode == 0, output


def _repo_root(path: Path) -> Path | None:
    root = _git_text(path, ["rev-parse", "--show-toplevel"])
    return Path(root) if root else None


def _identity_problem(root: Path) -> str | None:
    name = _git_text(root, ["config", "user.name"])
    email = _git_text(root, ["config", "user.email"])
    if name and email:
        return None
    return (
        "Git needs your name and email first. Run:\n"
        '  git config --global user.name "Your Name"\n'
        '  git config --global user.email "you@example.com"'
    )


def _staged_count(root: Path) -> int:
    text = _git_text(root, ["diff", "--cached", "--name-only"])
    return len([line for line in text.splitlines() if line.strip()])


def _clean_message(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text[:2000] or fallback


def _push_branch(root: Path, status: dict) -> tuple[bool, str]:
    branch = _git_text(root, ["symbolic-ref", "--short", "-q", "HEAD"]) or status.get("branch")
    if not branch or branch == "HEAD":
        return False, "You are not on a branch."

    upstream = _git_text(
        root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]
    )
    if upstream:
        return _run_git_step(root, ["push"], 120)

    remotes = status.get("remotes") or []
    remote = "origin" if "origin" in remotes else (remotes[0] if remotes else "origin")
    return _run_git_step(root, ["push", "-u", remote, branch], 120)


def _add_readme(root: Path, text: object) -> dict:
    """Write a new README.md and commit just that file."""
    content = str(text or "")
    if not content.strip():
        result = _action_ok("")
        result["readme_written"] = False
        return result

    problem = _identity_problem(root)
    if problem:
        return _action_error(problem)

    if len(content) > MAX_README_CHARS:
        return _action_error(
            f"The README is too long. Keep it under {MAX_README_CHARS} characters."
        )
    if not content.endswith("\n"):
        content += "\n"

    existing = find_readme(root)
    if existing:
        if existing.name != "README.md":
            result = _action_ok(f"{existing.name} already exists; left it unchanged.")
            result["readme_written"] = False
            return result
        try:
            current = existing.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return _action_error(f"Could not read README.md: {exc}")
        if current != content:
            result = _action_ok("README.md already exists; left it unchanged.")
            result["readme_written"] = False
            return result
        written = "README.md is already present."
    else:
        try:
            (root / "README.md").write_text(content, encoding="utf-8")
        except OSError as exc:
            return _action_error(f"Could not write README.md: {exc}")
        written = "Wrote README.md."

    ok, stage_output = _run_git_step(root, ["add", "--", "README.md"], 60)
    if not ok:
        return _action_error("Could not stage README.md.", stage_output)

    staged = _git_text(root, ["diff", "--cached", "--name-only", "--", "README.md"])
    if not staged.strip():
        result = _action_ok(written)
        result["readme_written"] = True
        return result

    ok, commit_output = _run_git_step(
        root, ["commit", "-m", README_COMMIT_MESSAGE, "--", "README.md"], 60
    )
    output = "\n".join(part for part in (stage_output, commit_output) if part)
    if not ok:
        return _action_error("Could not commit README.md.", output)
    result = _action_ok(output or "Wrote and committed README.md.")
    result["readme_written"] = True
    return result


def git_init(target: Path, message: str, make_gitignore: bool) -> dict:
    existing = _git_text(target, ["rev-parse", "--show-toplevel"])
    if existing:
        return _action_error(f"This folder is already inside a Git repository: {existing}")
    message = _clean_message(message, "Initial commit")

    ok, output = _run_git_step(target, ["init"], 30)
    if not ok:
        return _action_error("Could not create the repository.", output)

    if make_gitignore and not (target / ".gitignore").exists():
        try:
            (target / ".gitignore").write_text(DEFAULT_GITIGNORE, encoding="utf-8")
        except OSError as exc:
            return _action_error(f"Could not write .gitignore: {exc}", output)

    blocked = gitignore_requirement(target)
    if blocked:
        return _action_error(blocked, output)

    ok, add_output = _run_git_step(target, ["add", "-A"], 60)
    output = "\n".join(part for part in (output, add_output) if part)
    if not ok:
        return _action_error("Could not stage the files.", output)
    if _staged_count(target) == 0:
        return _action_error("There are no files to commit.", output)

    problem = _identity_problem(target)
    if problem:
        return _action_error(problem, output)

    ok, commit_output = _run_git_step(target, ["commit", "-m", message], 60)
    output = "\n".join(part for part in (output, commit_output) if part)
    if not ok:
        return _action_error("The initial commit failed.", output)
    return _action_ok(output or "Created the repository and first commit.")


def git_commit(target: Path, message: str) -> dict:
    status = read_git_status(target)
    if not status.get("repo"):
        return _action_error("This folder is not a Git repository.")
    if status.get("state") == "detached":
        return _action_error("You are on a detached HEAD. Switch to a branch first.")
    if status.get("conflicted"):
        return _action_error("Resolve the merge conflicts before committing.")

    root = _repo_root(target) or target
    message = _clean_message(message, f"Update {target.name}")

    blocked = gitignore_requirement(root)
    if blocked:
        return _action_error(blocked)

    ok, add_output = _run_git_step(root, ["add", "-A"], 60)
    if not ok:
        return _action_error("Could not stage the files.", add_output)
    if _staged_count(root) == 0:
        return _action_error("There are no changes to commit.", add_output)

    problem = _identity_problem(root)
    if problem:
        return _action_error(problem, add_output)

    ok, commit_output = _run_git_step(root, ["commit", "-m", message], 60)
    if not ok:
        return _action_error("The commit failed.", commit_output)
    return _action_ok(commit_output or "Committed the changes.")


def git_push(target: Path) -> dict:
    status = read_git_status(target)
    if not status.get("repo"):
        return _action_error("This folder is not a Git repository.")
    if status.get("state") == "detached":
        return _action_error("You are on a detached HEAD. Switch to a branch first.")
    if not status.get("has_remote"):
        return _action_error("There is no remote. Create one first.")

    root = _repo_root(target) or target
    blocked = gitignore_requirement(root, include_untracked=False)
    if blocked:
        return _action_error(blocked)
    ok, output = _push_branch(root, status)
    if not ok:
        return _action_error("The push failed.", output)
    return _action_ok(output or "Pushed the commits.")


def _github_owner_repo(root: Path) -> tuple[str, str] | None:
    url = _git_text(root, ["remote", "get-url", "origin"])
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/*$", url)
    if not match:
        return None
    return match.group(1), match.group(2)


def _github_pages_url(owner: str, name: str) -> str:
    owner_lower = owner.lower()
    name_lower = name.lower()
    if name_lower == f"{owner_lower}.github.io":
        return f"https://{owner_lower}.github.io/"
    return f"https://{owner_lower}.github.io/{name_lower}/"


def _index_case_mismatch(path: Path) -> str | None:
    try:
        names = sorted(entry.name for entry in path.iterdir() if entry.is_file())
    except OSError:
        return None
    for name in names:
        if name != "index.html" and name.lower() == "index.html":
            return name
    return None


def pages_state(path: Path) -> dict:
    try:
        names = [entry.name for entry in path.iterdir() if entry.is_file()]
    except OSError:
        names = []
    return {
        "index": (path / "index.html").is_file(),
        "entry": choose_html(names),
        "case_mismatch": _index_case_mismatch(path),
    }


def pages_requirement(
    root: Path, state: dict | None = None, repo: bool | None = None
) -> str | None:
    """Why GitHub Pages would not serve this folder, or None when it will."""
    state = state if state is not None else pages_state(root)
    if not state["index"]:
        mismatch = state.get("case_mismatch")
        if mismatch:
            return (
                "GitHub Pages is case-sensitive and needs a lowercase index.html. "
                f"This folder has {mismatch}. Rename it to index.html, then "
                "publish again."
            )
        entry = state["entry"]
        if entry:
            return (
                "GitHub Pages needs an index.html at the repository root. "
                f"This repo's page is {entry}. Rename it to index.html, or "
                "create an index.html that opens it."
            )
        return (
            "GitHub Pages needs an index.html at the repository root. "
            "Add one, then publish again."
        )

    if repo is None:
        repo = _repo_root(root) is not None
    if repo:
        head = bool(_git_text(root, ["rev-parse", "--verify", "HEAD"]))
        in_head = _git_in_head(root, "index.html")
        if not in_head and _git_ignored(root, "index.html"):
            return (
                "GitHub Pages only serves files that Git publishes, but "
                "index.html is ignored by .gitignore. Unignore it, commit it, "
                "then publish again."
            )
        if head and not in_head:
            return (
                "GitHub Pages only serves committed files, but index.html is "
                "not in the last commit. Commit and push it, then publish again."
            )
    return None


def pages_detail(root: Path, repo: bool = False) -> dict:
    state = pages_state(root)
    state["problem"] = pages_requirement(root, state, repo=repo)
    return state


def git_create_pages_entry(target: Path) -> dict:
    root = _repo_root(target) or target
    if (root / "index.html").is_file():
        return _action_error("This repository already has an index.html.")
    mismatch = _index_case_mismatch(root)
    if mismatch:
        return _action_error(
            "GitHub Pages is case-sensitive and needs a lowercase index.html. "
            f"This repository has {mismatch}. Rename it to index.html first."
        )
    if _git_ignored(root, "index.html"):
        return _action_error(
            "index.html would be ignored by .gitignore. Unignore it before "
            "creating the Pages entry."
        )
    try:
        names = [entry.name for entry in root.iterdir() if entry.is_file()]
    except OSError as exc:
        return _action_error(f"Could not read the repository folder: {exc}")
    entry = choose_html(names)
    if not entry:
        return _action_error(
            "No HTML page was found. Add one first, then create the Pages entry."
        )
    if _git_ignored(root, entry):
        return _action_error(
            f"{entry} is ignored by .gitignore, so the Pages entry could not "
            "open it. Unignore it first."
        )
    href = quote(entry)
    page = (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f'<meta http-equiv="refresh" content="0; url={href}">\n'
        f"<title>{escape(Path(entry).stem)}</title>\n"
        "</head>\n"
        "<body>\n"
        f'<p><a href="{href}">Open {escape(entry)}</a></p>\n'
        "</body>\n"
        "</html>\n"
    )
    try:
        (root / "index.html").write_text(page, encoding="utf-8")
    except OSError as exc:
        return _action_error(f"Could not write index.html: {exc}")
    return _action_ok(f"Created index.html, which opens {entry}.")


def _enable_github_pages(
    root: Path, owner: str, name: str, branch: str
) -> tuple[bool, str]:
    ok, output = _run_command(
        [
            "gh",
            "api",
            "--method",
            "POST",
            f"repos/{owner}/{name}/pages",
            "-f",
            f"source[branch]={branch}",
            "-f",
            "source[path]=/",
        ],
        root,
        90,
    )
    if not ok and ("409" in output or "already" in output.lower()):
        return True, output
    return ok, output


def _set_repo_homepage(
    root: Path, owner: str, name: str, url: str
) -> tuple[bool, str]:
    return _run_command(
        ["gh", "repo", "edit", f"{owner}/{name}", "--homepage", url], root, 60
    )


def git_create_remote(
    target: Path,
    name: str,
    visibility: str,
    description: str = "",
    pages: bool = False,
    readme: str = "",
) -> dict:
    status = read_git_status(target)
    if not status.get("repo"):
        return _action_error("This folder is not a Git repository.")
    if status.get("state") == "detached":
        return _action_error("You are on a detached HEAD. Switch to a branch first.")

    root = _repo_root(target) or target
    if not _git_text(root, ["rev-parse", "HEAD"]):
        return _action_error("Make the first commit before creating a remote.")
    if status.get("has_remote"):
        return _action_error("This repository already has a remote.")
    if not shutil.which("gh"):
        return _action_error(
            "GitHub CLI (gh) is not installed. Install it, or add a remote by hand."
        )

    ok, auth_output = _run_command(["gh", "auth", "status"], root, 20)
    if not ok:
        return _action_error("GitHub CLI is not logged in. Run: gh auth login", auth_output)

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", name):
        return _action_error(
            "Use a GitHub repo name with letters, numbers, dots, dashes, or underscores."
        )
    if visibility not in ("private", "public"):
        return _action_error("Choose private or public visibility.")

    blocked = gitignore_requirement(root, include_untracked=False)
    if blocked:
        return _action_error(blocked)

    prep = _add_readme(root, readme)
    if not prep["ok"]:
        return prep

    flag = "--private" if visibility == "private" else "--public"
    description = str(description or "").strip()[:350]
    cmd = [
        "gh",
        "repo",
        "create",
        name,
        "--source",
        ".",
        "--remote",
        "origin",
        "--push",
        flag,
    ]
    if description:
        cmd.extend(["--description", description])
    ok, output = _run_command(cmd, root, 180)
    if not ok:
        return _action_error("Creating the GitHub repo failed.", output)

    result = _action_ok(output or f"Created {name} and pushed the commits.")
    if prep.get("readme_written"):
        result["readme_written"] = True
    if not pages:
        return result

    owner_repo = _github_owner_repo(root)
    if not owner_repo:
        result["pages_error"] = (
            "The repo was created, but its origin URL could not be read, "
            "so GitHub Pages was not enabled."
        )
        return result
    owner, repo = owner_repo

    branch = status.get("branch") or _git_text(
        root, ["symbolic-ref", "--short", "-q", "HEAD"]
    )
    if not branch:
        result["pages_error"] = (
            "The repo was created, but the branch name could not be found, "
            "so GitHub Pages was not enabled."
        )
        return result

    missing = pages_requirement(root)
    if missing:
        result["pages_error"] = missing
        return result

    ok, pages_output = _enable_github_pages(root, owner, repo, branch)
    if not ok:
        result["pages_error"] = "GitHub Pages could not be enabled.\n" + pages_output
        return result

    pages_url = _github_pages_url(owner, repo)
    result["pages_url"] = pages_url
    ok, homepage_output = _set_repo_homepage(root, owner, repo, pages_url)
    if not ok:
        result["pages_error"] = (
            "GitHub Pages is on, but the repo homepage could not be set.\n"
            + homepage_output
        )
    return result


def git_enable_pages(target: Path, readme: str = "") -> dict:
    status = read_git_status(target)
    if not status.get("repo"):
        return _action_error("This folder is not a Git repository.")
    if status.get("state") == "detached":
        return _action_error("You are on a detached HEAD. Switch to a branch first.")
    if not status.get("has_remote"):
        return _action_error("Create a GitHub remote first.")

    root = _repo_root(target) or target
    if not shutil.which("gh"):
        return _action_error("GitHub CLI (gh) is not installed.")

    ok, auth_output = _run_command(["gh", "auth", "status"], root, 20)
    if not ok:
        return _action_error("GitHub CLI is not logged in. Run: gh auth login", auth_output)

    owner_repo = _github_owner_repo(root)
    if not owner_repo:
        return _action_error("The origin remote does not point at GitHub.")
    owner, repo = owner_repo

    branch = status.get("branch") or _git_text(
        root, ["symbolic-ref", "--short", "-q", "HEAD"]
    )
    if not branch or branch == "HEAD":
        return _action_error("You are not on a branch.")

    missing = pages_requirement(root)
    if missing:
        return _action_error(missing)

    if not status.get("upstream") or status.get("ahead"):
        return _action_error(
            "GitHub Pages only serves files that have been pushed. Push your "
            "commits first, then publish again."
        )

    blocked = gitignore_requirement(root, include_untracked=False)
    if blocked:
        return _action_error(blocked)

    prep = _add_readme(root, readme)
    if not prep["ok"]:
        return prep
    if prep.get("readme_written"):
        ok, push_output = _push_branch(root, status)
        if not ok:
            return _action_error(
                "README.md was committed, but it could not be pushed.", push_output
            )

    ok, output = _enable_github_pages(root, owner, repo, branch)
    if not ok:
        return _action_error("GitHub Pages could not be enabled.", output)

    pages_url = _github_pages_url(owner, repo)
    result = _action_ok(output or f"Enabled GitHub Pages at {pages_url}.")
    if prep.get("readme_written"):
        result["readme_written"] = True
    result["pages_url"] = pages_url
    ok, homepage_output = _set_repo_homepage(root, owner, repo, pages_url)
    if not ok:
        result["pages_error"] = (
            "GitHub Pages is on, but the repo homepage could not be set.\n"
            + homepage_output
        )
    return result


def run_git_action(action: str, target: Path, body: dict) -> dict:
    if action == "init":
        return git_init(
            target,
            _clean_message(body.get("message"), "Initial commit"),
            bool(body.get("gitignore")),
        )
    if action == "commit":
        return git_commit(target, _clean_message(body.get("message"), f"Update {target.name}"))
    if action == "push":
        return git_push(target)
    if action == "pages":
        return git_enable_pages(target, str(body.get("readme") or ""))
    if action == "pages-entry":
        return git_create_pages_entry(target)
    if action == "remote":
        return git_create_remote(
            target,
            str(body.get("name") or "").strip(),
            str(body.get("visibility") or "private").lower(),
            str(body.get("description") or "").strip(),
            bool(body.get("pages")),
            str(body.get("readme") or ""),
        )
    return _action_error("Unknown Git action.")


def page_card_info(
    path: Path, rel_dir: str, include_untitled: bool = False
) -> dict | None:
    """The overview card for a folder whose page Ribbon serves."""
    try:
        filenames = [entry.name for entry in path.iterdir() if entry.is_file()]
    except OSError:
        return None
    html = choose_html(filenames)
    if not html:
        return None
    page = path / html
    title = extract_title(page)
    if not title and not include_untitled:
        return None
    _, summary = readme_summary(path)
    return {
        "kind": "page",
        "title": title or fallback_title(rel_dir),
        "description": summary or extract_description(page),
        "type": "HTML",
        "icon": "HTML",
        "run": "",
        "files": folder_entries(path),
        "stats": folder_stats(path),
        "color": type_color("HTML"),
    }


def directory_app(path: Path, root: Path, include_untitled: bool) -> dict:
    """One directory, represented as its page or as a folder card."""
    rel_dir = path.relative_to(root).as_posix()
    try:
        filenames = [entry.name for entry in path.iterdir() if entry.is_file()]
    except OSError:
        filenames = []

    html = choose_html(filenames)
    if html:
        page = path / html
        title = extract_title(page)
        if title or include_untitled:
            url = "/" + quote(rel_dir, safe="/") + "/"
            if html != "index.html":
                url += quote(html)
            try:
                mtime = int(page.stat().st_mtime)
            except OSError:
                mtime = 0
            return {
                "kind": "page",
                "url": url,
                "file": "/" + quote(f"{rel_dir}/{html}", safe="/"),
                "path": rel_dir,
                "title": title or fallback_title(rel_dir),
                "type": "HTML",
                "icon": "HTML",
                "mtime": mtime,
                "color": type_color("HTML"),
            }

    info = project_info(path, rel_dir)
    if not info:
        info = folder_info(path, rel_dir)
    try:
        mtime = int(path.stat().st_mtime)
    except OSError:
        mtime = 0
    if info["kind"] == "markdown":
        rel_file = info.get("markdown_path") or rel_dir
        url = "/" + quote(rel_file, safe="/")
        file = url
    else:
        url = CARD_ROUTE + quote(rel_dir + "/", safe="/")
        file = ""
    return {
        **info,
        "url": url,
        "file": file,
        "path": rel_dir,
        "mtime": mtime,
    }


def discover(
    root: Path,
    include_untitled: bool = False,
    with_git: bool = False,
    max_age: float = 1.0,
    git_max_age: float = GIT_CACHE_SECONDS,
) -> list[dict]:
    """One entry per immediate child folder of root, in stable name order."""
    now = time.monotonic()
    cache_key = f"{root}|{int(include_untitled)}|{int(with_git)}"
    if (
        _cache["root"] == cache_key
        and now - float(_cache["at"]) < max_age
    ):
        return _cache["apps"]  # type: ignore[return-value]

    apps: list[dict] = []
    folders: list[Path] = []
    try:
        root_resolved = root.resolve()
        children = sorted(root.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        root_resolved = root
        children = []

    for child in children:
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name in SKIP_DIRS:
            continue
        if child == APP_DIR:
            continue
        try:
            child.resolve().relative_to(root_resolved)
        except (OSError, ValueError):
            continue

        folders.append(child)
        apps.append(directory_app(child, root, include_untitled))

    if with_git and apps:
        # `discover` runs on the manifest request thread, once the page has
        # already asked for it, so a serial pass over every repo shows up as
        # a stall. `git_status` is subprocess-bound, and the cache and
        # per-repo locks it uses are already thread-safe.
        workers = min(GIT_STATUS_WORKERS, len(apps))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            statuses = list(
                pool.map(
                    lambda folder: git_status(folder, max_age=git_max_age),
                    folders,
                )
            )
        for app, status in zip(apps, statuses):
            app["git"] = status

    # `children` is already in name order, and every app's path is its child
    # folder's name, so appending in this loop keeps that order.
    _cache.update(at=now, root=cache_key, apps=apps)
    return apps


def delete_plan(root: Path, requested: str) -> dict:
    """Validate a direct child folder and describe the exact removal command."""
    root = root.resolve()
    name = str(requested or "").strip()
    if (
        not name
        or name in (".", "..")
        or "/" in name
        or "\\" in name
        or name.startswith(".")
    ):
        raise ValueError("That is not a folder in the ribbon list.")
    target = root / name
    if target.is_symlink():
        raise ValueError("Ribbon will not delete a symlink.")
    try:
        resolved = target.resolve(strict=True)
    except OSError:
        raise ValueError("That folder no longer exists.") from None
    if not resolved.is_dir() or resolved.parent != root:
        raise ValueError("That is not a folder directly inside the ribbon root.")
    if resolved == APP_DIR.resolve():
        raise ValueError("That is Ribbon's own folder.")
    path = str(resolved)
    return {
        "dir": name,
        "path": path,
        "command": "rm -rf -- " + shlex.quote(path),
    }


def remove_directory(root: Path, plan: dict) -> dict:
    """Run the exact command shown to the user, then forget the folder's state."""
    path = str(plan.get("path") or "")
    command = str(plan.get("command") or "")
    if not path or not command:
        return _action_error("Ribbon could not work out what to delete.")
    ok, output = _run_command(["rm", "-rf", "--", path], cwd=root, timeout=30)
    if not ok:
        return _action_error("The folder could not be deleted.", output)
    if os.path.lexists(path):
        return _action_error(
            "The command finished, but the folder is still there.",
            output,
        )
    with STATE_LOCK:
        state = load_state(root)
        assets = state.get("assets")
        key = str(plan.get("dir") or "")
        if isinstance(assets, dict) and key in assets:
            assets.pop(key, None)
            save_state(root, state)
    GIT_CACHE.clear()
    _cache["at"] = 0.0
    return {
        **_action_ok(output),
        "dir": key,
        "path": path,
        "command": command,
    }


# The bar floats above the page, so the document needs a strip of its own to
# sit under it. The offset is in normal flow, so it exists at first paint even
# when the scripts are slow or blocked. ribbon.js hides it with the same host
# attribute it uses when the bar is hidden by hand.
PAGE_OFFSET_CSS = (
    "[data-ribbon-host][data-ribbon-hidden] + [data-ribbon-offset]"
    " { display: none !important; }\n"
)
PAGE_OFFSET_MARKUP = (
    '<div data-ribbon-offset aria-hidden="true" style="'
    "display:block!important;"
    "height:40px!important;"
    "min-height:40px!important;"
    "margin:0!important;"
    "padding:0!important;"
    "border:0!important;"
    "flex:none!important;"
    "pointer-events:none!important"
    '"></div>'
)

BAR_HOST_STYLE = (
    "position:fixed!important;"
    "top:0!important;"
    "right:0!important;"
    "left:0!important;"
    "width:100%!important;"
    "height:auto!important;"
    "margin:0!important;"
    "padding:0!important;"
    "border:0!important;"
    "background:transparent!important;"
    "z-index:2147483647!important;"
    "display:block!important;"
    "pointer-events:none!important;"
    "isolation:isolate!important;"
    "view-transition-name:ribbon-bar!important"
)

# Cross-document view transitions: the bar is a named element in both
# documents, so it is lifted out of the root cross-fade and survives the
# navigation unchanged. Naming the host (not .bar inside its shadow root)
# is what makes the snapshot part of the document's view transition tree.
# Reduced motion opts out of the transition entirely; the blanket rule is
# there for engines that ignore @view-transition inside @media.
VIEW_TRANSITION_CSS = (
    "@view-transition { navigation: auto; }\n"
    "::view-transition-old(ribbon-bar),\n"
    "::view-transition-new(ribbon-bar) {\n"
    "  animation: none;\n"
    "  mix-blend-mode: normal;\n"
    "}\n"
    "@media (prefers-reduced-motion: reduce) {\n"
    "  @view-transition { navigation: none; }\n"
    "  ::view-transition-old(root),\n"
    "  ::view-transition-new(root) {\n"
    "    animation: none;\n"
    "  }\n"
    "}\n"
)

BAR_MARKUP = "".join(
    line.strip()
    for line in """\
<div class="bar" role="navigation" aria-label="App ribbon">
  <div class="meta">
    <span class="led-wrap">
      <span class="leds" role="group" aria-label="Git status" aria-describedby="led-tip">
        <button class="led-btn" type="button" data-led="repo" aria-label="Repository status"><span class="led off" data-led-dot="repo" aria-hidden="true"></span></button>
        <button class="led-btn" type="button" data-led="changes" aria-label="Changes status"><span class="led off" data-led-dot="changes" aria-hidden="true"></span></button>
        <button class="led-btn" type="button" data-led="remote" aria-label="Remote status"><span class="led off" data-led-dot="remote" aria-hidden="true"></span></button>
      </span>
      <span class="led-tip" id="led-tip" role="tooltip" aria-hidden="true">
        <span class="led-tip-row"><span class="led off" data-tip-led="repo" aria-hidden="true"></span><span data-tip-text="repo"></span></span>
        <span class="led-tip-row"><span class="led off" data-tip-led="changes" aria-hidden="true"></span><span data-tip-text="changes"></span></span>
        <span class="led-tip-row"><span class="led off" data-tip-led="remote" aria-hidden="true"></span><span data-tip-text="remote"></span></span>
      </span>
    </span>
    <span class="count"></span>
  </div>
  <div class="title-wrap">
    <button class="star-btn title-star" type="button" aria-pressed="false" aria-label="Add to favorites" title="Add to favorites">☆</button>
    <button class="title" type="button" aria-haspopup="dialog" aria-expanded="false" title="Show all apps">
      <span class="title-text"></span>
      <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>
    </button>
  </div>
  <div class="actions">
    <button class="btn" type="button" data-act="prev" aria-label="Previous app" title="Previous app — [">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>
      <span class="label">Back</span>
    </button>
    <button class="btn" type="button" data-act="next" aria-label="Next app" title="Next app — ]">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>
      <span class="label">Next</span>
    </button>
    <button class="btn" type="button" data-act="contents" aria-label="Show contents" aria-pressed="false" title="Show contents — C">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
      <span class="label">Contents</span>
    </button>
    <button class="btn" type="button" data-act="drift" aria-label="Drift to another app" title="Drift to another app — R">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 4l3 3-3 3"/><path d="M18 20l3-3-3-3"/><path d="M3 7h3c2 0 3.5 1 4.5 2.5l3 5C14.5 16 16 17 18 17h3"/><path d="M3 17h3c2 0 3.5-1 4.5-2.5l3-5C14.5 8 16 7 18 7h3"/></svg>
      <span class="label">Drift</span>
    </button>
    <button class="btn" type="button" data-act="reload" aria-label="Reload app" title="Reload app — Shift+R">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>
    </button>
    <span class="sep" aria-hidden="true"></span>
    <button class="btn" type="button" data-act="hide" aria-label="Hide ribbon" title="Hide ribbon — H">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6L6 18"/><path d="M6 6l12 12"/></svg>
    </button>
  </div>
  <div class="menu" hidden role="dialog" aria-label="All apps">
    <div class="menu-top">
      <div class="menu-current">
        <span class="menu-current-label">Current app</span>
        <span class="menu-current-title"></span>
        <span class="menu-current-meta"></span>
      </div>
      <button class="star-btn" type="button" aria-pressed="false" aria-label="Add to favorites" title="Add to favorites">☆</button>
    </div>
    <div class="menu-current-hint">drift deals from the active channel</div>
    <div class="menu-channels" role="group" aria-label="Channels"></div>
    <div class="menu-search">
      <input class="menu-input" type="search" placeholder="Search apps…" aria-label="Search apps" autocomplete="off" spellcheck="false">
    </div>
    <div class="menu-scroll">
      <div class="menu-section" data-section="favorites" hidden>
        <div class="menu-heading">Favorites</div>
        <div class="menu-list" data-list="favorites"></div>
      </div>
      <div class="menu-section" data-section="all">
        <div class="menu-heading">All apps</div>
        <div class="menu-list" data-list="all"></div>
      </div>
      <div class="menu-empty" hidden>No apps match.</div>
    </div>
  </div>
</div>
<div class="card-overlay" hidden>
  <button class="card-close" type="button" aria-label="Close contents" title="Close contents — Esc">✕ Close</button>
  <iframe class="card-frame" title="Project contents"></iframe>
</div>
<button class="peek" type="button" aria-label="Show ribbon" title="Show ribbon — H">
  <span aria-hidden="true">▤</span><span class="peek-label">ribbon</span>
</button>
<div class="git-overlay" hidden>
  <div class="git-dialog" role="dialog" aria-modal="true" aria-labelledby="git-title">
    <div class="git-head">
      <div class="git-heading">
        <div class="git-kicker">Git</div>
        <div class="git-title" id="git-title"></div>
      </div>
      <button class="git-close" type="button" aria-label="Close">✕</button>
    </div>
    <div class="git-body">
      <div class="git-summary"></div>
      <div class="git-files" hidden></div>
      <div class="git-warnings" hidden></div>
      <label class="git-field git-message-field" hidden>
        <span class="git-label">Commit message</span>
        <input class="git-input git-message" type="text" maxlength="2000" autocomplete="off">
      </label>
      <label class="git-field git-name-field" hidden>
        <span class="git-label">GitHub repo name</span>
        <input class="git-input git-name" type="text" maxlength="100" autocomplete="off" spellcheck="false">
      </label>
      <div class="git-field git-visibility-field" hidden>
        <span class="git-label">Visibility</span>
        <div class="git-radios">
          <label class="git-radio"><input type="radio" name="git-visibility" value="private" checked> Private</label>
          <label class="git-radio"><input type="radio" name="git-visibility" value="public"> Public</label>
        </div>
      </div>
      <label class="git-field git-description-field" hidden>
        <span class="git-label">Description (optional)</span>
        <input class="git-input git-description" type="text" maxlength="350" autocomplete="off" placeholder="What is this app?">
      </label>
      <label class="git-field git-readme-field" hidden>
        <span class="git-label">README.md</span>
        <textarea class="git-input git-textarea git-readme" rows="6" maxlength="20000" spellcheck="false" placeholder="Write a short README…"></textarea>
        <span class="git-hint">No README yet. Ribbon will write this to README.md, commit it, and push it before publishing.</span>
      </label>
      <label class="git-check git-pages-field" hidden>
        <input type="checkbox" class="git-pages">
        <span>Publish with GitHub Pages and set it as the repo homepage</span>
      </label>
      <label class="git-check git-ignore-field" hidden>
        <input type="checkbox" class="git-ignore" checked>
        <span>Add a .gitignore for node_modules, .venv, dist…</span>
      </label>
      <div class="git-note" hidden></div>
      <pre class="git-output" hidden></pre>
    </div>
    <div class="git-actions">
      <span class="git-status"></span>
      <button class="btn git-cancel" type="button">Close</button>
      <button class="btn git-primary" type="button" hidden></button>
    </div>
  </div>
</div>
<div class="delete-overlay" hidden>
  <div class="delete-dialog" role="alertdialog" aria-modal="true" aria-labelledby="delete-title" aria-describedby="delete-warning">
    <div class="delete-head">
      <div class="delete-heading">
        <div class="delete-kicker">Delete folder</div>
        <div class="delete-title" id="delete-title"></div>
      </div>
      <button class="git-close delete-close" type="button" aria-label="Close">✕</button>
    </div>
    <div class="delete-body">
      <p class="delete-warn" id="delete-warning">This removes the folder and everything inside it. It cannot be undone.</p>
      <div class="delete-path"></div>
      <div>
        <div class="delete-command-label">Command</div>
        <pre class="delete-command"></pre>
      </div>
      <div class="delete-note">Ribbon will run exactly this command, then remove the folder from the list.</div>
      <pre class="delete-command delete-output" hidden></pre>
    </div>
    <div class="delete-actions">
      <span class="delete-status" role="status" aria-live="polite"></span>
      <button class="btn delete-cancel" type="button">Cancel</button>
      <button class="btn delete-primary" type="button" disabled>Delete folder</button>
    </div>
  </div>
</div>
""".splitlines()
)

# --- embedded assets: generated by build.py; do not edit ---
_EMBEDDED_ASSETS_B64: dict[str, str] = {
    # bar.css: 25388 bytes -> 4585 compressed
    "bar.css": (
        "eNrtXOuO6zaS/n+egjgHg+3OWI4kS7LcjQV2Z4BgFpj8SbA/FsFgQEu0rWlZMiS5Lwka2IeYJ5wn"
        "meJVJEXZcnen02cwSHJyLFFFVrEuH6tIfvsN+qFYr+sKrXGD/vH/f0fdjqC6IqjtnkrS7gjp0KZu"
        "2GNoMv+EvoF/0Y+kuSc5wh369q9/bRiFb+nrrG0RruBFXh86aFBUXS2//Y8WtTt48YCauu7Q+okS"
        "4t/O/9ZSyt9++nSzq9sO/YJwWd7A10VX4PIWPcML+tEMifefEPI8oOntblDkHx5v2YOiurtBXwgh"
        "qzzjT/ZHGAU8Wy1XYRrxZ2VRkRvUbNf4KozjGer/mAeLa94GZxmpOvgw93ES4dtPMIJvZuibm5s1"
        "AXEQ9le86UgDY13Xj15b/FxU2xv4e5OTxoNHbNRzKlY62kPdAi91BR2TEnfFPaEd5UV7KPHTDdqU"
        "hPGAy2JbeUVH9u0NokMgDX28xYcbFISczx0ptjsY2z1uroQQ2Kj3uNkW0IFPfxxwnrMB+Wh5eIQ/"
        "gwX/eo2zu21TH6tcyCBYzlCQwn8gAH++YqSyuqwb2QNIlT1UrHVdvYfhANm2LotcNKNiFe1AHGyi"
        "ae8B65315EMH/N/5Ir6G/6EUXoYR/GG/D1I+EQ9kfVd0Hh103tQHb1OUIBIQc3lsrgL4/Bq1uDs2"
        "uCNXwTyIryWL01tv6qrzNnhflDAPx8JrcdV6LWmKzQx5+HAoidc+tTAjM/QH4PHue5z9yH5/Bx/O"
        "0OcfybYm6H//5/MM/VCDcOoZ+hMp70lXZHiG/rsBBZ6hnqjqEjQG1FBOC5WeJ2c20Hnnjfeg/Ts2"
        "obiiNlHgluS02RGoAuWSZPBhBZarf+t8eagLqlceuQf9AjXDx66mz7sGBgnKDXPL/gpqSv7vyr9W"
        "74QCq3YoTPx9i7Ljusi8Nfm5IM3VPAQzAo2i/w9gjusDzoruCTSMNiUwakruoShLL9vhaks0eszK"
        "mJ0jh91sikfOcVcfhJI3XFzs7yXZyL/+DCqbk0eQo89IUmLzovW2IIAZ9zBXP+W4wx73Pt6uyHNS"
        "/eWadets0WZNXZYkF23Y0NzyynCZXXmB7/8OeQgs9prJT4hBGqc1A3xm6Ej3pMOM+EWeYcV1iDal"
        "JuerKbV1e19XdQtDAf/143ffww/vB7I9lsA0+p5UJajuH+sKjBq3oNh/LtYETAWEj2hT0G/1ua3E"
        "wgOXpKNs0SZMVedBSPYDf8J88jXldw4S9R4afAAn6nCQlhCcIhBMMwkiTrG9SIB/O7ZdsXnyMmCH"
        "uXzb65pON0z5b+Vs2T9ewp9qXle6W+40G5wXR+g3GTphpjsH3EC3SibrrmJMgPshGN5nZGjbrneK"
        "6aJiDuXlvD8UeQexNUjPsG9y3XNs/FDsR2fY51pFh78DX8keZMempbojbIY7gGO2gxDN1WWPq+Jw"
        "LJmi6gIEK77n4dmOeHbU9yHYIO3DTZ0dW+++aIt1SYBAfew4ZgitkMdRAnwsWnj1ZtMS5oYEPTaL"
        "QpaWKFOngsT+72wJfYniaBkFdmgtKuhK6F8gQ+iAtWTgvnvS4KS5S55phNXD3qNI90QZmtd3jCdj"
        "gEmcBykexn6f24HAGX4Ao/JXEBcWKcVaDAFwDOBsEMXKScwfcFMN+yX+ehGf6zcMI6C4BLIr39Wt"
        "9T7qO13j3NVnspzYp7843ad6r3MKKmTprJx/o0Pd4XldcbCCJV6DnoKfVfGShSUWlX5Ph3Hdh0xP"
        "wEoVNRe+5gD2+FG6B273j558U1RXixA8/0wRv3+gMS+SQU/5BYhPKAh0fdfhoxuJR9cO60iH/uNL"
        "sA5A+xzAk1rrIhyAy3mkQ9wvZEWiPPkAQFDIhz16ED4i8v0hOAR1cQVb1rIjj52nARMZGB524PxZ"
        "WxYtmj2sqgawhHm8omQPOCQah4VexNA0zDy5mq/Sa6OlVwMyo+EBVI9pme2DJCoEDC49UI8qAfyf"
        "BJWnEJQ0Bwr36gOpqPeWPIIF6RwK/36LbHFpViWXe8y6VJT8/Pn2tLF5scRD1MAC8et0GBhTaab/"
        "jOpFFiO6nvSJJoCm7ujiKIpzsr3WBeo1EBp+OYnI6COv7XDT3XLoBAtPXZiMxO+RRZEjCc5h7PiA"
        "R1Gj2cLRDFS7ugHc2sGyoihzfajrss7u2AcZyJcmF6TtZ5tstV7dUlcmvVocHsTKvSs6sHiOTi8F"
        "5JEOyAP4RwJyrSexNuHdULHpWCFMLNyVGGhBMGBBR0HsdchxCnvJNPYmw0aUmLHBfwFy7j36Jtr4"
        "JHGCScO5xty5uhbj9jrG92O+kGH+lYnmRjm2AUJ9FhNxAQJdxhyC8u/eCoBy3aJjZjpBR7MpaXTU"
        "vDtlqH9ByrI4tEXriBnUEnre0DzbkXtdZaXwVJxa6Foi9cy5EhzLL6jw0Pf7E4Y46pFHMPec5P/5"
        "uWuO5PNf5GgcrixIfebLEF9eV8fpSMmjdqwhpdQCSpHvtBzmB/OiIWKBAiwf95WOqQA5RYshcgoS"
        "iZwozJJypK2X/v1uhuLEF+NxzeSrgJVcwU9DVhTHRqkDWaUj0Gos5WTkp6gqjiav+MtnPoU/iYSN"
        "7uVl6OYtaKC43G1LKSjPRB9wIMnmXnTvgcVTpwPdWy7QdIDIau+VeE1Kc1g8OCnXqLKrCw0N/voJ"
        "nNVY/ibS3J5mW0eIIE0mFoljyR2D9T4yDVl/C7/k9OOGu0+4u7ejhD3QYQbOniKFQd526O8wy3OB"
        "REdmzJLErqh43NACNbOF1RneRXxk2dkPLZB0Ho8F/MhIXH5JNsk68XUh7XBVkXIk18hCAGXmBkmW"
        "mIOJB2nCXqAUn+7EQv5S9KZw1mLQQXrZsjt0RYfVajUZfeEVjlYn0JfMGCtddKAnKodLwBNEdyvm"
        "IEGFw4VDQ9pWQwu/DJA0J+zTMliSzNAyklkZR8HMaiZEpvxKwHNhko23wnKUmCcWML0v4sAk/i2C"
        "hWR4uVmuE6IYdkvcGH6//lrhVSyiNl0BfZy898I3waz8PSHv/SL8tZxqXzZwPmlkyVht0ZFUt1K9"
        "cjpeaIbCCpBG6TJTjKxc8IgpWs38dMwWFT+vt8dApB8USdA+vOZpCpVsmi/iWyXmnGzwsexu3Wmr"
        "HrS2oNjZjhbDHAFCocmiOhw7Y+Xl86KBraw6Ff8Nsq+Ja40QBgt/M7pn4KR6hjIGqDlQ6tczyifM"
        "oSfmLDnz8Sr5a7vs9Nru5Qb8R0Z2dZkzbVfOLVumSaZPESsEG8tp76lf0Jg5DRl8aUv+obcmO3xf"
        "UNrU+eCCoSb+ju7kEDNKS/39CHcEU6ImFks5eZVq+toXCi1fLp9a2hkNaSbR+D2UlY7XI8MkRELV"
        "MIpJSVY/1ZEyy2C+MDfosq3nnu4FfjcWuSP5Kc199yvUs/Bl+DE4NprgYY8g2nJlV44tjo0I0tRb"
        "6tKNwSsiTi70wNYb1sWFe12YZjU+HSaenvVeREpZ2BrLUkvXyX4462zm56wMOvA48alSpoMIr2qO"
        "kxmWJh1EWJXyHA2j1NgLXc7uq7PF4zmvsRKBtb/ifC7ZDb00L/s22WOzHmjErqnJXynaN8AaXqhH"
        "fqB5MpFi4YG3z6uIiD3ibAaD7IFYQuJ1ZDKyLZ8OO5MRgd63TcE2erGQPDR8TTFCa0ukLLUJz9/0"
        "Rm3G5mgMDQlW2LjH96+8V3rCkcVaiorwIGGx4AEYZpbWm0upp4E+X1TsYKTvrj3vn9rSVqWf5qCm"
        "fYHtN19ajpX2+hgWsi2zF26tmu7hZC7rDDqPXr54lAK/cAuWY/EoKY0sHk998laZF04xJ2By5N8a"
        "dIkGha/TIC7yEzpkbbJKdBXy8XKVK30QpN5MIzg95glhZsc2KrMdeoM9yYFZNTwT7PpSVDqyfx/w"
        "JQBEujsmCSdsml+IEuLpt+6C3bPN+elCnGibF7ist3rCgpY0Y58VQGm0ub4QUr6m+pk4q5/hBdVP"
        "ml1BqT+sfsbxx9xY5jxhIDaRXV6AVdNKV9oTFmwuyB/aZVZ6BIRmK61dgo6zJu5ZvdZ1U6UAzldn"
        "xRd3RXZHGj1n8PWWYdUG1Z49icZ1pWBbrQb1Ubs6qpvxus6fzPmWruvMpOpDESvefi2nzcIBd3w9"
        "8F6nFoIT1VDwVaCC3roh+A58I/0fQOpS5yWr93tc5VpV31Ke+OtPzZmsakza63C1U+LVxUbnhsjA"
        "yjJDgM+W6817nnEJVLHYdKTxYPUDMNWT65+zWlTVnbZSNibA0b1ukPwAxAuSZqltqYGy1Mt2nBo6"
        "Aj6+E4n688mct1lcnqiJGTZuD5ImLXjarHea6WrJE33rrlIeqSlA259Gi1QmAI2H9eIv2SqOo9RQ"
        "3M3GvTXF2bUT/X7JV0kUJ7cGTffQ3bUpV2lK5QTJ/tA9mbUGtuFLGvcEoavCjp4xk0r4rPdzGkBu"
        "i+5lGNv/qjG2xvZ5+Yyg68RE1/aGwjShGwqXodxQ+G/0/bWgbzrnHw96y1FNxN20+b8S6B7gJsrg"
        "q2A3o5CVdftRck5nDoLSQgWih4J+xbzTRXtfopHtZYNUkxL0S7OVIvj2dN4szURJqmXXye0GxmKL"
        "f9ge9xy8WHGQOwJ5hkZrOeGIzxrUng70tgeSNpF+NdQfR18mH8OiX2nQksV7XB7JuwJdR1bVDnRy"
        "2gFqkFZ41T7mB7GxgU3AezsY0KKxMWpd16bG+Inb29TOoed+3BNimtJAGdHs4p62Qfndbj9QVVHJ"
        "CDjSnKhAyAGbdKR0IrR1BzvBjPRveR7ECpoDPRrVIqcODY686R3u2QnHXoQRFyHf6GYV1ByMK1dF"
        "kztAoB1svhko2pQDwebeh0U8Ua9cH1vbAkmardJwZH3/bPBCdxnpP38ZbCpCveER57lDQxCR5jHZ"
        "Byf3O9FWF5wZif8lvOz57Y3hV7+9UfH5a+5uZBgUZgFgFD/RIgWoxyr5bGXfYMKW/EKsDeEsyc0F"
        "Y1mwd07FyXWHPKdy+sROPDl94Y9k+qI+ylKdqdshWuKLLIaLlCQX/P4tzfLZ1/rHOkp3X3Ojzt06"
        "VMx07untAPSa/QoDQ1y53AqnvFq2I9ndy9aaqQNx6BtobDOxuBjZXKUGddZz8qFLbvVhsE1Vk9jn"
        "2dm3CGcvhEnu9cfievzIzSBfPZqbViiPn1TC1dMDOLLeQ4Hfkq5YLvMC184CnX0DdC59+6TYrw0m"
        "e6HkaR5m4W8AAy8sEEybhPN5wI9SDWALpQ9dCuhHyC+Fq/VCQJrnK5z2q9pp9QLa9FyxwAzSjmLB"
        "IOTLzoJlkPqnqwbaAEZKBpt1RBcaFk0HA5eVDJTaTbqsjSkc877WXXViHO+R69JvsJh6P8VqzLdb"
        "iaoX76jqY96b7agau77hwkNd8bWzznRDJ/6eTKERiCMGVM/AkOSHU45WLs3jXBHJ8qVi4q1OVo4e"
        "4QrTC45wMfVt77f9wQKe7DW2Jtu3FbbkoLU3mvOTCAP3wG9Z1bb6qTVohpt8YrVMvzlWRnNVPFuN"
        "emUz4oIDCaKTdSx9RKcDGGu5afB+4s52JSXx27BbM9fsHvPwqiq6oV/zEvS7Da0Wui/F0ut/o80U"
        "Z30e/8S9IxIbi03rMgKreQnfydddCmSTySfG+dEYauH0YExC7/Qyz07nJE+z9CNcXOqnU7IYQ6c7"
        "dtHJmYuM/ZMFY/H6WdemcRe+8GdoQY8fUQGvQof71qi83oeq+7IOhNxNvrJXKvtL9Dm2znysTutz"
        "+orUUD9uS799ccAzmXCp9jw1S9Pr1XqBo4+QqQtfpuSvvDVw/P4+Y5v02J2BQSJvktYvDeyfTjC3"
        "8LS5hdLcqEqzs4y7+qE6c3O0Uv8eP0ShLR9556ApoNMXc9vj4JY/Q9bTgSVr1x4KEm939r1PjpyM"
        "6/+1J3mB0ZV2ayjfcsIExS/Sdl9nr9UXzWNbMtkL5IGCSI4Pu6bU6XLCdgT8lbyHwt6XAK9cRXuR"
        "ZbPOj/H26kYxeUmYcGwKshg3fMmbV808iWqygyZxItow8sYOKCM5e9s3kFuAxomym8Uk8xoi4Y6Z"
        "UWv66yihnXvyIm3y+HldPk++IRwWEYz7Sbx4IHrLPfGXVEm9U3NqnmIbNtGGfWjIhjSt15D8mJEc"
        "fKu8XZz+7jVQGNIM9TfpGm6nJ/1P6B9nUg=="
    ),
    # bar.js: 40252 bytes -> 9545 compressed
    "bar.js": (
        "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"
        "VG7uif2papEJ+wmubPOTaH2XAqP4H+u6pwE="
    ),
    # card.css: 11003 bytes -> 2718 compressed
    "card.css": (
        "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"
    ),
    # card.js: 10191 bytes -> 2984 compressed
    "card.js": (
        "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"
        "QYSnkIU0DaMsdf71EB7+BVVHk4g="
    ),
    # markdown.css: 4098 bytes -> 1156 compressed
    "markdown.css": (
        "eNq1V92OqzYQvs9TWCsdaVFDRNiQTVmdqu9R9cLBE3BjMMc4m6TVvnvHhgRjvHtWW/WGhMGen29m"
        "Po/3kl1XqoiZLOI9/if/LAiJY5TQooBGxwygzUkhhVRxzS+PvCHyKIpqSV6penRWRiTbfXOkvDlG"
        "0csC1THetYJec7IXsji+oKTmTVwBLyudk3WSvFYBIRukVJW8yUliXlrKGG/KnDyn7YWkG3xk2/Zi"
        "PslXUAchz/EFvRW8NbI9LY6lkqeG5aNfDLpjZL7amPKpw0Z+kBj2gdZcXJ2vVmoQGtd0/G9AV7Pe"
        "AcEbGP1fZUYWn2F/5Lrf3NVS6sq6TxvNqeC0A/ayeFsshgxY8M+c6So3aDw+b5P2sjRgfIsmWBB6"
        "0nICyNMOsdhshocNXioGGN8aZZ0UnI2xqJOAaFwTK8r4qUMlw847bLGPUUtbUJG3iNe0BGdRqShv"
        "Bv2XuKsok+cc3wjhTQca3Tc+JeMGYCVES7siGbM6fu9V3Fegm4jJfEGsDfiRiygmhDIL670IDwJs"
        "lOY3PiuK1W2eRlSaF2N5veuRwByVTcw11IjOHtNlkmw+/HXqND9cEZ9GY+3npGtpAfEe9BmgmeYK"
        "HU56dfdsGeE6dfOEpaW1rG3lzBPWl+YQ1pEXR1DhoGwEIedNh4KaNVSgB+L0S10wRGNF56ELtok1"
        "IkCj7dhAZKNfJWuovXDyfA8HqcCGdUf14eFl7Ijn3sKtxYZXE3lOGtnnJdjxAz9N6qKlurK2JnDc"
        "SaSvC9pczxUoCCFVnzSwnyFVy0aGkfJdQXCaIfYPMzKBdlCCIRyx/D+1/8ZZqzBrPc+V/kbyA1ed"
        "jouKC+ZgFmvZWtz8HdV66QlSX/DkCza+IPMF20m60FWosYtWWWZq6UtsPnRP9Nm6jbFw096aB1sa"
        "AsH664BeCFq3j9jfmYJ6STav5yVJ8W8U2JzazQNf3Llh9dRb9ynjA4Z3k77aZE7fOcnwPV2v1rvg"
        "ys9mydUVUtR6207CE0hfYEeHHyepwfvQKl9iXjTdC7BdPG1yw7uroEsBFyY5EHDoz/XQZsHJL+bh"
        "N0efMH81DTaqM2/ZzGm4mLdCKqq5RIUVEmUDXWcTfl+BVAfKlqM8HPB0zYnLL3ebnVayKd9jiEAJ"
        "FpKBC4DVS7IvzxapP1v4U8XAUl/o4xDLrnbbYOENJ4w7Lc5mqbWZQNbb/z1Uf2LMwv7OM5G4jiW+"
        "rdtZ+HM0xqaa6jcdYrjV/ExxGNrgaQ7G/ZB9/6j8wDweMoKGzpgbx4WOGeWdCDvj9Rya3nHbj+8n"
        "0VfO63LQjkNiP3+YMdwdQG5189UKmZls2pP+Q19b+P5QVFAccXp++NPjL8vhhsfshNdTxsdMMpjx"
        "GHHeAL47doN7I7nFP8SCVgVtO7CXQ/vPL7pf01DR6cojWs2m1fc8jPefxdbSoB12c2LK08gwOs0L"
        "Km5yzH7IE2v4v1GSP5D9XgPjlDw6hZOZa1zU2wpdt12ONdcaMyGSzYDAm7lBu/dDd7UhKrsl3c1X"
        "j3efWTelm9vyt8W/9lQA3Q=="
    ),
    # ribbon.js: 45191 bytes -> 11293 compressed
    "ribbon.js": (
        "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"
        "5/8AE2PWMw=="
    ),
}
# --- end embedded assets ---

# The release copy serves the assets embedded above, so one ribbon.py is all
# you need. --dev reads the files beside this script instead, so editing the
# bar shows up on the next request without a rebuild.
DEV_ASSETS = False

_disk_asset_cache: dict[str, tuple[int, int, bytes]] = {}


@lru_cache(maxsize=None)
def embedded_asset(name: str) -> bytes | None:
    encoded = _EMBEDDED_ASSETS_B64.get(name)
    if not encoded:
        return None
    try:
        return zlib.decompress(base64.b64decode(encoded))
    except (ValueError, zlib.error):
        return None


def disk_asset(name: str) -> bytes:
    path = APP_DIR / name
    stat = path.stat()
    key = (stat.st_mtime_ns, stat.st_size)
    cached = _disk_asset_cache.get(name)
    if cached is not None and (cached[0], cached[1]) == key:
        return cached[2]
    data = path.read_bytes()
    _disk_asset_cache[name] = (key[0], key[1], data)
    return data


def asset_bytes(name: str) -> bytes:
    """One asset, from the release build or from disk with --dev."""
    if not DEV_ASSETS:
        data = embedded_asset(name)
        if data is not None:
            return data
    return disk_asset(name)


def asset_stamp(name: str) -> tuple:
    if not DEV_ASSETS and embedded_asset(name) is not None:
        return ("embedded", name)
    try:
        stat = (APP_DIR / name).stat()
    except OSError:
        return ("missing", name)
    return ("disk", name, stat.st_mtime_ns, stat.st_size)


def missing_assets(dev: bool) -> list[str]:
    missing = []
    for name in sorted(STATIC_ASSETS):
        if dev:
            if not (APP_DIR / name).is_file():
                missing.append(name)
        elif embedded_asset(name) is None:
            missing.append(name)
    return missing


def bar_css() -> bytes:
    try:
        return asset_bytes("bar.css")
    except OSError:
        return b""


def bar_shell_html() -> bytes:
    return (
        b'<div data-ribbon-host style="'
        + BAR_HOST_STYLE.encode("utf-8")
        + b'"><template shadowrootmode="open"><style>'
        + bar_css()
        + b"</style>"
        + BAR_MARKUP.encode("utf-8")
        + b"</template></div>"
    )


_asset_version_cache: tuple[tuple, str] | None = None


def asset_version() -> str:
    """A short hash of every static asset, so a cached URL cannot go stale."""
    global _asset_version_cache
    key = tuple(asset_stamp(name) for name in sorted(STATIC_ASSETS))
    if _asset_version_cache is not None and _asset_version_cache[0] == key:
        return _asset_version_cache[1]
    digest = hashlib.sha256()
    for name in sorted(STATIC_ASSETS):
        try:
            payload = asset_bytes(name)
        except OSError:
            continue
        digest.update(name.encode("utf-8"))
        digest.update(payload)
    version = digest.hexdigest()[:12]
    _asset_version_cache = (key, version)
    return version


def asset_url(name: str, version: str) -> str:
    return "/__ribbon/" + name + ("?v=" + version if version else "")


def inject_html(data: bytes, token: str = "", version: str = "") -> bytes:
    """Insert the bar's shell and scripts into a page.

    The stylesheet is metadata content, so it goes at the end of <head>.
    The rest of the block goes immediately after <body> so the bar is present
    at first paint instead of popping in. That placement is a trade-off: the
    injected offset div becomes body's first child, so a page rule like
    `body > :first-child` matches it instead of the page's own first element,
    and sibling rules built on it skip over the rest of Ribbon's markup. Pages
    that style their first child by position should use a class. Pages with
    no <head> fall back to keeping the stylesheet in the body block.
    """
    if b"data-ribbon-host" in data or b"/__ribbon/ribbon.js" in data:
        return data
    attrs = b' data-ribbon="1"'
    if token:
        attrs += b' data-ribbon-token="' + escape(token).encode("utf-8") + b'"'
    style = (
        b"<style>"
        + VIEW_TRANSITION_CSS.encode("utf-8")
        + PAGE_OFFSET_CSS.encode("utf-8")
        + b"</style>"
    )
    inject = (
        bar_shell_html()
        + PAGE_OFFSET_MARKUP.encode("utf-8")
        + BOOT_SCRIPT
        + b'<script src="' + asset_url("bar.js", version).encode("utf-8") + b'" defer></script>'
        + b'<script src="' + asset_url("ribbon.js", version).encode("utf-8") + b'"'
        + attrs
        + b" defer></script>"
    )
    heads = list(HEAD_CLOSE_RE.finditer(data))
    if heads:
        index = heads[-1].start()
        data = data[:index] + style + data[index:]
    else:
        inject = style + inject
    opening = BODY_OPEN_RE.search(data)
    if opening:
        index = opening.end()
        return data[:index] + inject + data[index:]
    matches = list(BODY_CLOSE_RE.finditer(data))
    if matches:
        index = matches[-1].start()
        return data[:index] + inject + data[index:]
    return data + inject


def state_home() -> Path:
    configured = os.environ.get("XDG_STATE_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "state"


def state_path(root: Path) -> Path:
    digest = hashlib.sha1(str(root).encode("utf-8")).hexdigest()[:12]
    return state_home() / STATE_DIR_NAME / f"state-{digest}.json"


def empty_state(root: Path) -> dict:
    return {"version": STATE_VERSION, "root": str(root), "assets": {}}


def load_state(root: Path) -> dict:
    try:
        data = json.loads(state_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty_state(root)
    if not isinstance(data, dict) or data.get("root") != str(root):
        return empty_state(root)
    if not isinstance(data.get("assets"), dict):
        data["assets"] = {}
    data["version"] = STATE_VERSION
    return data


def save_state(root: Path, state: dict) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, path)


def public_state(state: dict) -> dict:
    return {
        "version": state.get("version", STATE_VERSION),
        "assets": state.get("assets", {}),
    }


def apply_signal(state: dict, key: str, signal: str) -> dict:
    assets = state.setdefault("assets", {})
    entry = assets.get(key)
    if not isinstance(entry, dict):
        entry = {}
    now = datetime.now(UTC)
    if signal != "open":
        raise ValueError("unknown signal")
    try:
        opens = int(entry.get("opens") or 0)
    except (TypeError, ValueError):
        opens = 0
    entry["opens"] = opens + 1
    entry["last_opened"] = now.isoformat(timespec="seconds")
    entry["updated"] = now.isoformat(timespec="seconds")
    assets[key] = entry
    return state


class RibbonHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = KEEPALIVE_TIMEOUT
    root: Path = APP_DIR.parent
    include_untitled: bool = False
    token: str = ""
    write_enabled: bool = False
    allowed_origins: ClassVar[set[str]] = set()

    def log_message(self, fmt: str, *args) -> None:
        if getattr(self.server, "verbose", False):
            super().log_message(fmt, *args)

    def do_GET(self) -> None:
        self._handle(head=False)

    def do_HEAD(self) -> None:
        self._handle(head=True)

    def do_POST(self) -> None:
        route = urlsplit(self.path).path
        if route not in ("/__ribbon/git", "/__ribbon/signal", "/__ribbon/delete"):
            self.send_error(404, "Not found")
            return

        if route == "/__ribbon/git" and not self.write_enabled:
            self._send_json(
                {
                    "ok": False,
                    "error": "Git actions are disabled. Start ribbon.py on 127.0.0.1 without --no-git-actions.",
                },
                403,
            )
            return

        if route == "/__ribbon/delete" and not self.write_enabled:
            self._send_json(
                {
                    "ok": False,
                    "error": "Deleting is disabled. Start ribbon.py on 127.0.0.1 without --no-git-actions.",
                },
                403,
            )
            return

        if not self._post_guard():
            return

        body = self._read_json_body()
        if body is None:
            return

        if route == "/__ribbon/signal":
            return self._handle_signal(body)

        if route == "/__ribbon/delete":
            return self._handle_delete(body)

        requested = str(body.get("dir") or "")
        try:
            target = (self.root / requested).resolve()
            target.relative_to(self.root.resolve())
        except (OSError, ValueError):
            self._send_json(
                {"ok": False, "error": "That folder is outside the ribbon root."}, 400
            )
            return
        if not target.is_dir():
            self._send_json({"ok": False, "error": "That folder does not exist."}, 404)
            return

        action = str(body.get("action") or "")
        lock = repo_lock(_repo_root(target) or target)
        if not lock.acquire(blocking=False):
            self._send_json(
                {
                    "ok": False,
                    "error": "Another Git action is already running for this app.",
                },
                409,
            )
            return
        try:
            result = run_git_action(action, target, body)
        finally:
            lock.release()

        GIT_CACHE.clear()
        payload = {
            **result,
            "action": action,
            "status": git_detail(target),
            "write": self.write_enabled,
        }
        self._send_json(payload, 200 if result.get("ok") else 409)

    def _post_guard(self) -> bool:
        origin = self.headers.get("Origin")
        if origin and origin not in self.allowed_origins:
            self._send_json(
                {"ok": False, "error": "This request did not come from the ribbon page."},
                403,
            )
            return False

        content_type = (self.headers.get("Content-Type") or "").lower()
        if not content_type.startswith("application/json"):
            self._send_json({"ok": False, "error": "Expected JSON."}, 415)
            return False

        token = self.headers.get("X-Ribbon-Token") or ""
        if not secrets.compare_digest(token, self.token):
            self._send_json(
                {"ok": False, "error": "Missing or wrong ribbon token."}, 403
            )
            return False
        return True

    def _read_json_body(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        if length <= 0 or length > 65536:
            self._send_json({"ok": False, "error": "Bad request size."}, 400)
            return None
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json({"ok": False, "error": "Bad JSON."}, 400)
            return None
        if not isinstance(body, dict):
            self._send_json({"ok": False, "error": "Bad request."}, 400)
            return None
        return body

    def _handle_signal(self, body: dict) -> None:
        if not self.token:
            self._send_json({"ok": False, "error": "State is read-only here."}, 403)
            return

        key = str(body.get("path") or "")
        signal = str(body.get("signal") or "")
        if not key:
            self._send_json({"ok": False, "error": "Missing app path."}, 400)
            return

        apps = discover(
            self.root,
            include_untitled=self.include_untitled,
            with_git=False,
            max_age=0,
        )
        if not any(app.get("path") == key for app in apps):
            self._send_json(
                {"ok": False, "error": "That app is not in the ribbon."}, 404
            )
            return

        with STATE_LOCK:
            state = load_state(self.root)
            try:
                apply_signal(state, key, signal)
            except ValueError:
                self._send_json({"ok": False, "error": "Unknown signal."}, 400)
                return
            save_state(self.root, state)

        self._send_json({"ok": True, "state": public_state(state)})

    def _deletion_plan(self, requested: str) -> dict:
        plan = delete_plan(self.root, requested)
        apps = discover(
            self.root,
            include_untitled=self.include_untitled,
            with_git=False,
            max_age=0,
        )
        if not any(app.get("path") == plan["dir"] for app in apps):
            raise ValueError("That folder is not in the ribbon list.")
        return plan

    def _delete_error(self) -> str | None:
        if not self.write_enabled:
            return "Deleting is disabled. Start ribbon.py on 127.0.0.1 without --no-git-actions."
        token = self.headers.get("X-Ribbon-Token") or ""
        if not self.token or not secrets.compare_digest(token, self.token):
            return "Missing or wrong ribbon token."
        return None

    def _handle_delete(self, body: dict) -> None:
        requested = str(body.get("dir") or "")
        try:
            plan = self._deletion_plan(requested)
        except ValueError as error:
            self._send_json({"ok": False, "error": str(error)}, 400)
            return
        result = remove_directory(self.root, plan)
        self._send_json(result, 200 if result.get("ok") else 409)

    def _accepts_gzip(self) -> bool:
        """Whether the client listed gzip (or *), with a non-zero weight."""
        header = self.headers.get("Accept-Encoding") or ""
        gzip_q = None
        star_q = None
        for item in header.split(","):
            name, _, params = item.strip().partition(";")
            name = name.strip().lower()
            if name not in ("gzip", "*"):
                continue
            q = 1.0
            for param in params.split(";"):
                key, _, value = param.partition("=")
                if key.strip().lower() == "q":
                    try:
                        q = float(value.strip())
                    except ValueError:
                        q = 0.0
            if name == "gzip":
                gzip_q = q
            else:
                star_q = q
        if gzip_q is not None:
            return gzip_q > 0
        return star_q is not None and star_q > 0

    def _response_body(self, payload: bytes) -> tuple[bytes, bool]:
        """The bytes to send, plus whether they carry a gzip header."""
        if payload and self._accepts_gzip():
            compressor = zlib.compressobj(6, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
            return compressor.compress(payload) + compressor.flush(), True
        return payload, False

    def _etag_for(self, body: bytes) -> str:
        return '"' + hashlib.sha256(body).hexdigest()[:16] + '"'

    def _etag_matches(self, etag: str) -> bool:
        header = self.headers.get("If-None-Match")
        if not header:
            return False
        for candidate in header.split(","):
            candidate = candidate.strip()
            if candidate == "*":
                return True
            if candidate.startswith("W/"):
                candidate = candidate[2:].strip()
            if candidate == etag:
                return True
        return False

    def _write_body(
        self,
        body: bytes,
        content_type: str,
        cache_control: str,
        head: bool,
        *,
        status: int = 200,
        etag: str | None = None,
        gzipped: bool = False,
    ) -> None:
        self.send_response(status)
        if etag is not None:
            self.send_header("ETag", etag)
        self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Type", content_type)
        self.send_header("Vary", "Accept-Encoding")
        if gzipped:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _send_payload(
        self,
        payload: bytes,
        content_type: str,
        cache_control: str,
        head: bool,
        *,
        status: int = 200,
        etag: bool = False,
    ) -> None:
        body, gzipped = self._response_body(payload)
        self._write_body(
            body,
            content_type,
            cache_control,
            head,
            status=status,
            etag=self._etag_for(body) if etag else None,
            gzipped=gzipped,
        )

    def _send_json(self, payload: dict, status: int = 200, head: bool = False) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_payload(
            data,
            "application/json; charset=utf-8",
            "no-store, max-age=0",
            head,
            status=status,
        )

    def _handle(self, head: bool) -> None:
        raw_path = urlsplit(self.path).path

        if raw_path.startswith(CARD_ROUTE):
            return self._serve_card(raw_path, head)

        if raw_path.startswith("/__ribbon/"):
            return self._serve_asset(raw_path[len("/__ribbon/") :], head)

        if raw_path == "/" and not (self.root / "index.html").is_file():
            apps = discover(
                self.root,
                include_untitled=self.include_untitled,
                with_git=False,
            )
            if apps:
                self.send_response(302)
                self.send_header("Location", apps[0]["url"])
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return

        target = Path(self.translate_path(raw_path))

        if target.is_dir():
            if not raw_path.endswith("/"):
                self.send_response(301)
                self.send_header("Location", raw_path + "/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            index = target / "index.html"
            if not index.is_file():
                try:
                    names = [entry.name for entry in target.iterdir() if entry.is_file()]
                except OSError:
                    names = []
                html = choose_html(names)
                if html:
                    index = target / html
                else:
                    rel = target.relative_to(self.root.resolve()).as_posix()
                    info = project_info(target, rel)
                    if info and info["kind"] == "markdown":
                        markdown = info.get("markdown_path")
                        if markdown:
                            index = self.root.resolve() / markdown
                    else:
                        return self._serve_card(
                            CARD_ROUTE + (quote(rel, safe="/") + "/" if rel != "." else ""),
                            head,
                        )
            target = index

        if target.is_file() and target.suffix.lower() in HTML_SUFFIXES:
            return self._serve_html(target, head)

        if target.is_file() and target.suffix.lower() in MARKDOWN_SUFFIXES:
            return self._serve_markdown(target, head)

        if head:
            super().do_HEAD()
        else:
            super().do_GET()

    def _serve_html(self, target: Path, head: bool) -> None:
        try:
            token = self.token
            data = inject_html(target.read_bytes(), token, asset_version())
        except OSError:
            self.send_error(404, "File not found")
            return

        self._send_payload(
            data,
            "text/html; charset=utf-8",
            "no-store, max-age=0",
            head,
        )

    def _serve_markdown(self, target: Path, head: bool) -> None:
        try:
            resolved = target.resolve()
            rel = resolved.relative_to(self.root.resolve()).as_posix()
            text = read_markdown(resolved)
        except (OSError, ValueError):
            self.send_error(404, "File not found")
            return

        version = asset_version()
        doc = (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{escape(markdown_title(text, rel))}</title>\n"
            f'<link rel="stylesheet" href="{asset_url("card.css", version)}">\n'
            f'<link rel="stylesheet" href="{asset_url("markdown.css", version)}">\n'
            "</head>\n"
            '<body class="rc-doc-body">\n'
            + markdown_view_html(rel, text)
            + "\n</body>\n"
            "</html>\n"
        ).encode("utf-8")
        payload = inject_html(doc, self.token, version)

        self._send_payload(
            payload,
            "text/html; charset=utf-8",
            "no-store, max-age=0",
            head,
        )

    def _serve_card(self, raw_path: str, head: bool) -> None:
        rel = unquote(raw_path[len(CARD_ROUTE) :]).strip("/")
        rel = rel or "."
        try:
            target = (self.root / rel).resolve()
            target.relative_to(self.root.resolve())
        except (OSError, ValueError):
            self.send_error(400, "Bad folder")
            return
        if not target.is_dir():
            self.send_error(404, "Not a folder")
            return

        rel_dir = target.relative_to(self.root.resolve()).as_posix()
        info = page_card_info(target, rel_dir, self.include_untitled)
        if not info:
            info = project_info(target, rel_dir)
        if not info:
            info = folder_info(target, rel_dir)
        if info["kind"] == "markdown":
            self.send_error(404, "No project here")
            return
        info["path"] = rel_dir
        try:
            info["mtime"] = int(target.stat().st_mtime)
        except OSError:
            info["mtime"] = 0
        info["tree"] = folder_tree(target)

        version = asset_version()
        data = json.dumps(info, ensure_ascii=False).replace("</", "<\\/")
        doc = (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{escape(info['title'])}</title>\n"
            f'<link rel="stylesheet" href="{asset_url("card.css", version)}">\n'
            f"<script>window.__RIBBON_CARD_APP__ = {data};</script>\n"
            f'<script src="{asset_url("card.js", version)}" defer></script>\n'
            "</head>\n"
            "<body>\n"
            '<div id="ribbon-card"></div>\n'
            "</body>\n"
            "</html>\n"
        ).encode()
        embed = info["kind"] == "page" or (
            parse_qs(urlsplit(self.path).query).get("embed") == [ "1" ]
        )
        payload = doc if embed else inject_html(doc, self.token, version)

        self._send_payload(
            payload,
            "text/html; charset=utf-8",
            "no-store, max-age=0",
            head,
        )

    def _serve_asset(self, name: str, head: bool) -> None:
        try:
            if name == "manifest.json":
                payload = json.dumps(
                    {
                        "apps": discover(
                            self.root,
                            include_untitled=self.include_untitled,
                            with_git=True,
                            max_age=0,
                            git_max_age=GIT_LIGHT_SECONDS,
                        ),
                        "token": self.token,
                        "write": self.write_enabled,
                        "state": public_state(load_state(self.root))
                        if self.token
                        else {},
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif name in STATIC_ASSETS:
                payload = asset_bytes(name)
                content_type = (
                    "text/javascript; charset=utf-8"
                    if name.endswith(".js")
                    else "text/css; charset=utf-8"
                )
            elif name == "git.json":
                requested = (parse_qs(urlsplit(self.path).query).get("dir") or [""])[0]
                try:
                    target = (self.root / requested).resolve()
                    target.relative_to(self.root.resolve())
                except (OSError, ValueError):
                    self.send_error(400, "Bad folder")
                    return
                if not target.is_dir():
                    self.send_error(404, "Not a folder")
                    return
                payload = json.dumps(
                    {
                        **git_detail(target),
                        "write": self.write_enabled,
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif name == "delete.json":
                error = self._delete_error()
                if error:
                    self._send_json({"ok": False, "error": error}, 403, head)
                    return
                requested = (parse_qs(urlsplit(self.path).query).get("dir") or [""])[0]
                try:
                    plan = self._deletion_plan(requested)
                except ValueError as error:
                    self._send_json({"ok": False, "error": str(error)}, 400, head)
                    return
                self._send_json({"ok": True, **plan}, head=head)
                return
            else:
                self.send_error(404, "Not found")
                return
        except OSError:
            self.send_error(500, "Ribbon asset missing")
            return

        body, gzipped = self._response_body(payload)
        if name in STATIC_ASSETS:
            # The injected URLs carry asset_version(), so a changed file gets
            # a new URL. Cache the old one for a year instead of asking the
            # browser to check back on every page.
            etag = self._etag_for(body)
            if self._etag_matches(etag):
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                self.send_header("Vary", "Accept-Encoding")
                self.end_headers()
                return
            self._write_body(
                body,
                content_type,
                "public, max-age=31536000, immutable",
                head,
                etag=etag,
                gzipped=gzipped,
            )
            return
        self._write_body(
            body,
            content_type,
            "no-store, max-age=0",
            head,
            gzipped=gzipped,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ribbon.py",
        description="Browse a folder of project directories with a floating switcher bar.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python3 ribbon.py                 start the server and open the first folder\n"
            "  python3 ribbon.py --list          show every folder it can find, then quit\n"
            "  python3 ribbon.py --app 3         start on folder number 3\n"
            "  python3 ribbon.py --root ~/sites --port 9000\n"
            "\n"
            "Ribbon lists the folders directly inside your root folder. If _ribbon\n"
            "sits in a wrapper like Work/ beside a single projects folder, it uses\n"
            "that folder. Use --root to point it anywhere. A folder with a page\n"
            "opens the page; every other folder opens a contents card."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    commands = parser.add_argument_group("commands")
    commands.add_argument(
        "--list", action="store_true", help="list the folders it found and quit"
    )

    server = parser.add_argument_group("server")
    server.add_argument(
        "--root",
        metavar="FOLDER",
        help="folder to scan and serve (default: auto-detect)",
    )
    server.add_argument(
        "--port", type=int, default=8765, help="first port to try (default: 8765)"
    )
    server.add_argument(
        "--host", default="127.0.0.1", help="address to listen on (default: 127.0.0.1)"
    )
    server.add_argument(
        "--app",
        type=int,
        metavar="N",
        help="start on folder number N instead of the first",
    )
    server.add_argument("--no-open", action="store_true", help="don't launch a browser")
    server.add_argument("--verbose", action="store_true", help="log every request")
    server.add_argument(
        "--dev",
        action="store_true",
        help="serve JS and CSS from the files beside this script, not the embedded copies",
    )
    server.add_argument(
        "--no-git-actions",
        action="store_true",
        help="show Git status but disable commit/push buttons",
    )

    finding = parser.add_argument_group("finding apps")
    finding.add_argument(
        "--include-untitled",
        action="store_true",
        help="open pages that have no <title> instead of their folder card",
    )
    return parser


def state_label(app: dict) -> str:
    """The one-word label for a repo's state, or its raw state if unknown.

    This is the coarse word from read_git_status, so it can hide uncommitted
    work. Use the app's `git.dirty` flag when that matters.
    """
    state = (app.get("git") or {}).get("state", "")
    return STATE_LABELS.get(state, state)


def print_apps(root: Path, apps: list[dict]) -> None:
    noun = "folder" if len(apps) == 1 else "folders"
    print(f"\n  Ribbon found {len(apps)} {noun} in {root}\n")
    width = len(str(len(apps)))
    for index, app in enumerate(apps, 1):
        print(f"  {index:>{width}}  {app['title']}")
        line = f"      {app['url']}"
        label = state_label(app)
        if label:
            line += f"  ·  {label}"
        print(line)
    print()


def print_no_apps(root: Path, include_untitled: bool) -> None:
    print(f"\n  No folders found in {root}\n")
    print("  Ribbon lists every folder directly inside the root folder.")
    print("  A folder with a page opens that page. Every other folder opens")
    print("  a card with its README, file types, and contents.")
    if not include_untitled:
        print("  Pages without a title show their folder card instead:\n")
        print("    python3 ribbon.py --list --include-untitled\n")
    print("  Try pointing it somewhere else:\n")
    print(f"    python3 ribbon.py --root {root.parent}")
    print("    python3 ribbon.py --help\n")


def main() -> None:
    global DEV_ASSETS

    parser = build_parser()
    args = parser.parse_args()
    DEV_ASSETS = args.dev

    if args.app is not None and args.list:
        parser.error("--app only makes sense when starting the server")

    root = Path(args.root).expanduser().resolve() if args.root else default_root()
    if not root.is_dir():
        parser.error(f"that folder does not exist: {root}")

    apps = discover(
        root,
        include_untitled=args.include_untitled,
        with_git=args.list,
        max_age=0,
        git_max_age=0,
    )

    if args.list:
        if not apps:
            print_no_apps(root, args.include_untitled)
            raise SystemExit(1)
        print_apps(root, apps)
        return

    missing = missing_assets(args.dev)
    if missing:
        if args.dev:
            parser.error(
                "--dev needs these files beside ribbon.py: " + ", ".join(missing)
            )
        parser.error(
            "this ribbon.py has no embedded copy of "
            + ", ".join(missing)
            + " (run python3 build.py, or use --dev)"
        )

    if not apps:
        print_no_apps(root, args.include_untitled)
        raise SystemExit(1)

    if args.app is not None and not 1 <= args.app <= len(apps):
        parser.error(f"--app must be between 1 and {len(apps)}")

    handler = partial(RibbonHandler, directory=str(root))
    RibbonHandler.root = root
    RibbonHandler.include_untitled = args.include_untitled

    httpd = None
    for port in range(args.port, args.port + 20):
        try:
            httpd = ThreadingHTTPServer((args.host, port), handler)
            break
        except OSError:
            continue
    if httpd is None:
        parser.error(f"no free port in {args.port}-{args.port + 19}")

    httpd.verbose = args.verbose  # type: ignore[attr-defined]
    chosen_port = httpd.server_address[1]
    host_for_url = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    base = f"http://{host_for_url}:{chosen_port}/"

    write_enabled = (not args.no_git_actions) and args.host in (
        "127.0.0.1",
        "localhost",
        "::1",
    )
    local_host = args.host in ("127.0.0.1", "localhost", "::1")
    RibbonHandler.write_enabled = write_enabled
    RibbonHandler.token = secrets.token_urlsafe(24) if local_host else ""
    origins = {base.rstrip("/")}
    if args.host in ("127.0.0.1", "localhost"):
        origins.add(f"http://127.0.0.1:{chosen_port}")
        origins.add(f"http://localhost:{chosen_port}")
    RibbonHandler.allowed_origins = origins

    if args.app is not None:
        launch = base + apps[args.app - 1]["url"].lstrip("/")
    else:
        launch = base

    print()
    print(f"  Ribbon {VERSION} is running")
    print(f"  folder  {root}")
    print(f"  folders {len(apps)}")
    if RibbonHandler.token:
        print(f"  state   {state_path(root)}")
    print(f"  open    {launch}")
    if args.port != 0 and chosen_port != args.port:
        print(f"  note    port {args.port} was busy, using {chosen_port}")
    if write_enabled:
        print("  git     actions enabled (commit, push, GitHub)")
    else:
        print("  git     read-only")
        print("  note    start on 127.0.0.1 to enable Git actions")
    print("  keys    [ ] prev/next · r drift · h hide · Ctrl+C stop")
    print()

    if not args.no_open:
        timer = threading.Timer(0.4, lambda: webbrowser.open(launch))
        timer.daemon = True
        timer.start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  bye\n")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
