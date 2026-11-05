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
    python3 ribbon.py --write-apps    refresh the no-server version
    python3 ribbon.py --help          every option, with examples
"""

from __future__ import annotations

import argparse
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
from datetime import UTC, datetime, timedelta
from fnmatch import fnmatchcase
from functools import partial
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
PARK_DAYS = 14
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
BODY_CLOSE_RE = re.compile(rb"</body\s*>", re.IGNORECASE)
SHELL_MARKER = b"data-ribbon-shell"

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


def extract_title(path: Path) -> str:
    try:
        with path.open("rb") as fh:
            head = fh.read(512 * 1024)
    except OSError:
        return ""
    match = TITLE_RE.search(head)
    return clean_title(match.group(1)) if match else ""


def extract_description(path: Path) -> str:
    try:
        with path.open("rb") as fh:
            head = fh.read(512 * 1024)
    except OSError:
        return ""
    match = META_DESCRIPTION_RE.search(head) or META_DESCRIPTION_FIRST_RE.search(head)
    return clean_title(match.group(1)) if match else ""


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


def is_shell_page(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return SHELL_MARKER in fh.read(8192)
    except OSError:
        return False


GIT_CACHE: dict[str, tuple[float, dict]] = {}
GIT_CACHE_SECONDS = 2.0

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


def git_status(path: Path, max_age: float = GIT_CACHE_SECONDS) -> dict:
    key = str(path.resolve())
    now = time.monotonic()
    cached = GIT_CACHE.get(key)
    if cached and now - cached[0] < max_age:
        return cached[1]

    status = read_git_status(path)
    GIT_CACHE[key] = (now, status)
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
    if not html or is_shell_page(path / html):
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
    if html and not is_shell_page(path / html):
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
        children = sorted(root.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        children = []

    for child in children:
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name in SKIP_DIRS:
            continue
        if child == APP_DIR:
            continue
        try:
            child.resolve().relative_to(root.resolve())
        except (OSError, ValueError):
            continue

        app = directory_app(child, root, include_untitled)
        if with_git:
            app["git"] = git_status(child, max_age=git_max_age)
        apps.append(app)

    apps.sort(key=lambda app: app["path"].lower())
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


def inject_html(data: bytes, token: str = "") -> bytes:
    if SHELL_MARKER in data or b"data-ribbon" in data or b"/__ribbon/ribbon.js" in data:
        return data
    attrs = b' data-ribbon="1"'
    if token:
        attrs += b' data-ribbon-token="' + token.encode("utf-8") + b'"'
    inject = (
        b'<script src="/__ribbon/bar.js" defer></script>'
        + b'<script src="/__ribbon/ribbon.js"'
        + attrs
        + b" defer></script>"
    )
    matches = list(BODY_CLOSE_RE.finditer(data))
    if matches:
        index = matches[-1].start()
        return data[:index] + inject + data[index:]
    return data + inject


def js_literal(value: object) -> str:
    if isinstance(value, dict):
        return "{" + ", ".join(
            json.dumps(str(key), ensure_ascii=False) + ": " + js_literal(item)
            for key, item in value.items()
        ) + "}"
    if isinstance(value, list):
        if not value:
            return "[]"
        return "[ " + ", ".join(js_literal(item) for item in value) + " ]"
    return json.dumps(value, ensure_ascii=False)


def write_apps_file(root: Path, include_untitled: bool) -> tuple[Path, int]:
    apps = discover(
        root,
        include_untitled=include_untitled,
        with_git=True,
        max_age=0,
        git_max_age=0,
    )
    lines = [
        "/* Generated by _ribbon/ribbon.py --write-apps. Re-run after adding a folder. */",
        "window.__RIBBON_APPS__ = [",
    ]
    for index, app in enumerate(apps):
        if app["kind"] == "project":
            url = "project:" + app["path"]
        else:
            rel_file = unquote(app["file"]).lstrip("/")
            url = os.path.relpath(root / rel_file, APP_DIR).replace(os.sep, "/")
        fields = [
            "url: " + json.dumps(url, ensure_ascii=False),
            "title: " + json.dumps(app["title"], ensure_ascii=False),
            "dir: " + json.dumps(app["path"], ensure_ascii=False),
            "kind: " + json.dumps(app["kind"], ensure_ascii=False),
        ]
        for key in ("type", "icon", "description", "run", "color"):
            if app.get(key):
                fields.append(key + ": " + json.dumps(app[key], ensure_ascii=False))
        fields.append("mtime: " + str(int(app.get("mtime") or 0)))
        if app.get("files"):
            fields.append("files: " + js_literal(app["files"]))
        if app.get("stats"):
            fields.append("stats: " + js_literal(app["stats"]))
        if app["kind"] == "markdown":
            markdown_path = app.get("markdown_path") or unquote(app["file"]).lstrip("/")
            text = read_markdown(root / markdown_path)
            html = markdown_view_html(markdown_path, text)
            fields.append("markdownHtml: " + json.dumps(html, ensure_ascii=False))
        fields.append("git: " + js_literal(app["git"]))
        comma = "," if index < len(apps) - 1 else ""
        lines.append("  { " + ", ".join(fields) + " }" + comma)
    lines.append("]")

    target = APP_DIR / "apps.js"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target, len(apps)


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


def apply_signal(state: dict, key: str, signal: str, value: object) -> dict:
    assets = state.setdefault("assets", {})
    entry = assets.get(key)
    if not isinstance(entry, dict):
        entry = {}
    now = datetime.now(UTC)
    if signal == "open":
        try:
            opens = int(entry.get("opens") or 0)
        except (TypeError, ValueError):
            opens = 0
        entry["opens"] = opens + 1
        entry["last_opened"] = now.isoformat(timespec="seconds")
    elif signal == "keep":
        entry["keep"] = bool(value)
        if entry["keep"]:
            entry["parked_until"] = None
    elif signal == "park":
        entry["parked_until"] = (
            (now + timedelta(days=PARK_DAYS)).isoformat(timespec="seconds")
            if value
            else None
        )
    elif signal == "note":
        note = str(value or "").strip()
        if note:
            entry["note"] = note[:500]
        else:
            entry.pop("note", None)
    else:
        raise ValueError("unknown signal")
    entry["updated"] = now.isoformat(timespec="seconds")
    assets[key] = entry
    return state


class RibbonHandler(SimpleHTTPRequestHandler):
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
                apply_signal(state, key, signal, body.get("value"))
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
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return

        target = Path(self.translate_path(raw_path))

        if target.is_dir():
            if not raw_path.endswith("/"):
                self.send_response(301)
                self.send_header("Location", raw_path + "/")
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
            data = inject_html(target.read_bytes(), token)
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

        doc = (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{escape(markdown_title(text, rel))}</title>\n"
            '<link rel="stylesheet" href="/__ribbon/card.css">\n'
            '<link rel="stylesheet" href="/__ribbon/markdown.css">\n'
            "</head>\n"
            '<body class="rc-doc-body">\n'
            + markdown_view_html(rel, text)
            + "\n</body>\n"
            "</html>\n"
        ).encode("utf-8")
        payload = inject_html(doc, self.token)

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

        data = json.dumps(info, ensure_ascii=False).replace("</", "<\\/")
        doc = (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{escape(info['title'])}</title>\n"
            '<link rel="stylesheet" href="/__ribbon/card.css">\n'
            f"<script>window.__RIBBON_CARD_APP__ = {data};</script>\n"
            '<script src="/__ribbon/card.js" defer></script>\n'
            "</head>\n"
            "<body>\n"
            '<div id="ribbon-card"></div>\n'
            "</body>\n"
            "</html>\n"
        ).encode()
        embed = info["kind"] == "page" or (
            parse_qs(urlsplit(self.path).query).get("embed") == [ "1" ]
        )
        payload = doc if embed else inject_html(doc, self.token)

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
                            git_max_age=0,
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
            elif name == "ribbon.js":
                payload = (APP_DIR / "ribbon.js").read_bytes()
                content_type = "text/javascript; charset=utf-8"
            elif name == "bar.js":
                payload = (APP_DIR / "bar.js").read_bytes()
                content_type = "text/javascript; charset=utf-8"
            elif name == "card.js":
                payload = (APP_DIR / "card.js").read_bytes()
                content_type = "text/javascript; charset=utf-8"
            elif name == "card.css":
                payload = (APP_DIR / "card.css").read_bytes()
                content_type = "text/css; charset=utf-8"
            elif name == "bar.css":
                payload = (APP_DIR / "bar.css").read_bytes()
                content_type = "text/css; charset=utf-8"
            elif name == "markdown.css":
                payload = (APP_DIR / "markdown.css").read_bytes()
                content_type = "text/css; charset=utf-8"
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
            etag = '"' + hashlib.sha256(payload).hexdigest()[:16] + '"'
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", "no-cache")
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
            "  python3 ribbon.py --write-apps    refresh apps.js for the static shell\n"
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
    commands.add_argument(
        "--write-apps",
        action="store_true",
        help="rewrite apps.js for the static shell and quit",
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


def static_shell_url(base: str, root: Path) -> str | None:
    shell = APP_DIR / "index.html"
    if not shell.is_file():
        return None
    try:
        rel = shell.parent.relative_to(root).as_posix()
    except ValueError:
        return None
    if rel == ".":
        return base
    return f"{base}{quote(rel, safe='/')}/"


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.list and args.write_apps:
        parser.error("choose one: --list or --write-apps")
    if args.app is not None and (args.list or args.write_apps):
        parser.error("--app only makes sense when starting the server")

    root = Path(args.root).expanduser().resolve() if args.root else default_root()
    if not root.is_dir():
        parser.error(f"that folder does not exist: {root}")

    if args.write_apps:
        target, count = write_apps_file(root, args.include_untitled)
        if not count:
            print_no_apps(root, args.include_untitled)
            print(f"  (wrote an empty list to {target})\n")
            raise SystemExit(1)
        print(f"\n  Wrote {count} apps to {target}\n")
        return

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
    shell = static_shell_url(base, root)
    if shell:
        print(f"  shell   {shell}")
    print("  keys    [ ] prev/next · r drift · k keep · p park · h hide · Ctrl+C stop")
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
