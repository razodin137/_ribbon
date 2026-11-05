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
# Runs before <body> parses, so the declarative shadow bar is already in its
# hidden state at first paint. ribbon.js reads the same two keys and takes over.
BOOT_SCRIPT = (
    b"<script>try{"
    b"var h=document.documentElement;"
    b'if(sessionStorage.getItem("ribbon:hidden")==="1")h.classList.add("ribbon-hidden");'
    b'else if(sessionStorage.getItem("ribbon:scroll")===location.href)'
    b'h.classList.add("ribbon-scrolled")'
    b"}catch(_){}"
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

        app = directory_app(child, root, include_untitled)
        if with_git:
            app["git"] = git_status(child, max_age=git_max_age)
        apps.append(app)

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
VIEW_TRANSITION_CSS = (
    "@view-transition { navigation: auto; }\n"
    "::view-transition-old(ribbon-bar),\n"
    "::view-transition-new(ribbon-bar) {\n"
    "  animation: none;\n"
    "  mix-blend-mode: normal;\n"
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
    # bar.css: 25283 bytes -> 4555 compressed
    "bar.css": (
        "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"
    ),
    # bar.js: 39986 bytes -> 9479 compressed
    "bar.js": (
        "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"
        "Zziz7U/i9X0KguJ/AHRwXUY="
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
    # ribbon.js: 44721 bytes -> 11028 compressed
    "ribbon.js": (
        "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"
        "K2wr3uIVBngdA4OqBT0JN3a3Q/jnfwFFdiqj"
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
    if b"data-ribbon-host" in data or b"/__ribbon/ribbon.js" in data:
        return data
    attrs = b' data-ribbon="1"'
    if token:
        attrs += b' data-ribbon-token="' + escape(token).encode("utf-8") + b'"'
    inject = (
        b"<style>" + VIEW_TRANSITION_CSS.encode("utf-8") + b"</style>"
        + bar_shell_html()
        + b'<script src="' + asset_url("bar.js", version).encode("utf-8") + b'" defer></script>'
        + b'<script src="' + asset_url("ribbon.js", version).encode("utf-8") + b'"'
        + attrs
        + b" defer></script>"
    )
    heads = list(HEAD_CLOSE_RE.finditer(data))
    if heads:
        index = heads[-1].start()
        data = data[:index] + BOOT_SCRIPT + data[index:]
    else:
        inject = BOOT_SCRIPT + inject
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

    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        self.wfile.write(data)

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

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        if not head:
            self.wfile.write(data)

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

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        if not head:
            self.wfile.write(payload)

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

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        if not head:
            self.wfile.write(payload)

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
                    self._send_json({"ok": False, "error": error}, 403)
                    return
                requested = (parse_qs(urlsplit(self.path).query).get("dir") or [""])[0]
                try:
                    plan = self._deletion_plan(requested)
                except ValueError as error:
                    self._send_json({"ok": False, "error": str(error)}, 400)
                    return
                self._send_json({"ok": True, **plan})
                return
            else:
                self.send_error(404, "Not found")
                return
        except OSError:
            self.send_error(500, "Ribbon asset missing")
            return

        if name in STATIC_ASSETS:
            # The injected URLs carry asset_version(), so a changed file gets
            # a new URL. Cache the old one for a year instead of asking the
            # browser to check back on every page.
            etag = '"' + hashlib.sha256(payload).hexdigest()[:16] + '"'
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
        else:
            self.send_response(200)
            self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if not head:
            self.wfile.write(payload)


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
