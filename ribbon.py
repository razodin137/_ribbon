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
import socket
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

from git_repo import (
    DEFAULT_GITIGNORE,
    GIT_CACHE,
    GIT_CACHE_SECONDS,
    GIT_ENV_STRIP,
    GIT_LIGHT_SECONDS,
    GIT_LOCKS,
    GIT_STATUS_LOCKS,
    GIT_STATUS_WORKERS,
    GITIGNORE_PREVIEW_CHARS,
    LARGE_FILE_BYTES,
    MAX_ACTION_OUTPUT,
    MAX_DETAIL_FILES,
    SCRATCH_DIRS,
    SECRET_NAMES,
    SECRET_SUFFIXES,
    _LockPool,
    _PooledLock,
    _action_error,
    _action_ok,
    _git,
    _git_env,
    _git_ignored,
    _git_in_head,
    _git_status_lock,
    _git_text,
    _git_tracked,
    _index_case_mismatch,
    _plain_gitignore_covers,
    _repo_root,
    file_warnings,
    find_scratch_dirs,
    git_detail,
    git_status,
    gitignore_requirement,
    list_folder_files,
    pages_detail,
    pages_requirement,
    pages_state,
    parse_status_files,
    read_git_status,
    repo_lock,
    scratch_warnings,
)
from markdown_render import markdown_view_html

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
HANDLER_TIMEOUT = 60
# Below this size a gzip header costs more than the bytes it saves.
GZIP_MIN_BYTES = 512
# One source for the bar's height: the page offset and ribbon.js both read it.
BAR_HEIGHT = 40

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

TREE_MAX_ENTRIES = 700

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


SYSTEM_ROOTS = (
    "/bin",
    "/boot",
    "/dev",
    "/etc",
    "/lib",
    "/lib64",
    "/media",
    "/mnt",
    "/opt",
    "/proc",
    "/run",
    "/sbin",
    "/srv",
    "/sys",
    "/usr",
    "/var",
    "/Applications",
    "/Library",
    "/System",
    "/private",
)


def is_safe_default_root(path: Path, home: Path | None = None) -> bool:
    """True when `path` looks like a projects folder, not a broad place.

    Ribbon serves the whole root as static files, so guessing too high exposes
    far more of the disk than the user meant. The filesystem root, a home
    folder, a top-level folder, and anything inside a system folder are never
    guessed. An explicit --root is still allowed to point anywhere.
    """
    try:
        resolved = path.resolve()
    except OSError:
        return False
    if resolved.parent == Path(resolved.anchor):
        return False
    if resolved == (home or Path.home()).expanduser().resolve():
        return False
    for name in SYSTEM_ROOTS:
        system = Path(name)
        if resolved == system or system in resolved.parents:
            return False
    return True


def default_root() -> Path | None:
    """The folder whose child directories Ribbon should list.

    If _ribbon sits in a wrapper folder (Work) beside a single container
    (tries), list the container's children. If _ribbon sits beside the
    projects, list them directly. A guess that lands on the filesystem root, a
    home folder, or a system folder is refused, so the caller has to ask for
    --root.
    """
    parent = APP_DIR.parent
    children = child_dirs(parent)
    candidate: Path | None = None
    if len(children) == 1 and is_container(children[0]):
        candidate = children[0]
    elif children:
        candidate = parent
    else:
        grandparent = parent.parent
        if grandparent != parent and child_dirs(grandparent):
            candidate = grandparent

    if candidate is None or not is_safe_default_root(candidate):
        return None
    return candidate


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
# Contents of these elements are text, not markup, so a <body> or </head>
# written inside one is not a real tag. The scanner below skips them.
RAW_TEXT_TAGS = frozenset(
    (
        b"script",
        b"style",
        b"textarea",
        b"title",
        b"xmp",
        b"iframe",
        b"noembed",
        b"noframes",
        b"noscript",
        b"plaintext",
    )
)
# Runs right after the declarative shadow bar parses. data-ribbon-booting turns
# off the bar's transition, so the hidden state lands without animating. Two
# frames later the attribute is removed and normal transitions resume.
# ribbon.js reads the same two keys and takes over.
BOOT_SCRIPT = (
    b"<script>try{"
    b'var h=document.querySelector("[data-ribbon-host]");'
    b"if(h){"
    b'h.setAttribute("data-ribbon-booting","");'
    b"requestAnimationFrame(function(){requestAnimationFrame(function(){"
    b'h.removeAttribute("data-ribbon-booting")'
    b"})});"
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
            env=_git_env(),
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

    # Sort by the path Ribbon reports instead of trusting the scan order or
    # that every caller passed an immediate child.
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
    from git_actions import _run_command

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
# sit under it. A generated block on the root element holds that strip in
# normal flow, so it exists at first paint even when the scripts are slow or
# blocked. It is not a child of <body>: a body child takes part in the page's
# layout, so it would sit beside the content in a row-flex body or become an
# extra grid item. ribbon.js removes the strip with the same host attribute it
# uses when the bar is hidden by hand.
PAGE_OFFSET_CSS = (
    f'html::before{{content:"";display:block;height:{BAR_HEIGHT}px;pointer-events:none;}}\n'
    "html:has([data-ribbon-host][data-ribbon-hidden])::before{display:none;}\n"
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
        <span class="led-tip-hint">Tap again for Git actions</span>
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
    # bar.css: 25718 bytes -> 4662 compressed
    "bar.css": (
        "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"
    ),
    # bar.js: 42466 bytes -> 10232 compressed
    "bar.js": (
        "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"
        "b1NCxzyfuJ+6FKnyn+J6tz9pBu5SIED/D73ET/4="
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
    # ribbon.js: 45680 bytes -> 11445 compressed
    "ribbon.js": (
        "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"
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
        b'<div data-ribbon-host data-ribbon-height="'
        + str(BAR_HEIGHT).encode("utf-8")
        + b'" style="'
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


def iter_html_tags(data: bytes):
    """Yield (is_closing, name, start, end) for real tags in an HTML document.

    This is a small scanner, not a tree builder. It exists so injection never
    lands inside a comment or a script/style body, where a regex like
    rb"<body\\b[^>]*>" would happily match. It also skips CDATA, declarations
    such as <!DOCTYPE>, processing instructions, and the raw text of elements
    like <script>, <style>, <textarea>, and <title>. Attribute values are
    scanned with quote awareness, so a > inside a quoted value does not end a
    tag.
    """
    n = len(data)
    i = 0
    while i < n:
        start = data.find(b"<", i)
        if start < 0:
            return
        if data.startswith(b"<!--", start):
            close = data.find(b"-->", start + 4)
            i = n if close < 0 else close + 3
            continue
        if data.startswith(b"<![CDATA[", start):
            close = data.find(b"]]>", start + 9)
            i = n if close < 0 else close + 3
            continue
        if data.startswith(b"<!", start) or data.startswith(b"<?", start):
            close = data.find(b">", start + 2)
            i = n if close < 0 else close + 1
            continue

        j = start + 1
        closing = j < n and data[j : j + 1] == b"/"
        if closing:
            j += 1
        name_start = j
        while j < n:
            char = data[j : j + 1]
            if char.isspace() or char in (b">", b"/"):
                break
            j += 1
        name = data[name_start:j].lower()
        if not name or not name[0:1].isalpha():
            i = start + 1
            continue

        quote = b""
        while j < n:
            char = data[j : j + 1]
            if quote:
                if char == quote:
                    quote = b""
            elif char in (b'"', b"'"):
                quote = char
            elif char == b">":
                break
            j += 1
        if j >= n:
            return

        end = j + 1
        yield closing, name, start, end
        i = end
        if closing:
            continue
        if name == b"plaintext":
            return
        if name in RAW_TEXT_TAGS:
            close = re.search(
                rb"</" + re.escape(name) + rb"(?=[\s/>])", data[end:], re.IGNORECASE
            )
            if close is None:
                return
            i = end + close.start()


def html_injection_points(data: bytes) -> tuple[int | None, int | None, int | None]:
    """Where the style and the bar block belong in a page.

    Returns the end of the first real <body ...> tag, the start of the last
    real </head>, and the start of the last real </body>. Any of them is None
    when the document does not contain that tag.
    """
    body_open = None
    head_close = None
    body_close = None
    for closing, name, start, end in iter_html_tags(data):
        if closing:
            if name == b"head":
                head_close = start
            elif name == b"body":
                body_close = start
        elif name == b"body" and body_open is None:
            body_open = end
    return body_open, head_close, body_close


def inject_html(data: bytes, token: str = "", version: str = "") -> bytes:
    """Insert the bar's shell and scripts into a page.

    The stylesheet is metadata content, so it goes at the end of <head>.
    The rest of the block goes immediately after <body> so the bar is present
    at first paint instead of popping in. That placement is a trade-off: the
    injected bar host is body's first element child, so a page rule like
    `body > :first-child` matches it instead of the page's own first element,
    and sibling rules built on it skip over the rest of Ribbon's markup. Pages
    that style their first child by position should use a class. The page
    offset is a generated box on <html>, not a body child, so it stays out of
    the page's flex and grid layout. Pages with no <head> fall back to keeping
    the stylesheet in the body block.
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
        + BOOT_SCRIPT
        + b'<script src="' + asset_url("bar.js", version).encode("utf-8") + b'" defer></script>'
        + b'<script src="' + asset_url("ribbon.js", version).encode("utf-8") + b'"'
        + attrs
        + b" defer></script>"
    )
    body_open, head_close, body_close = html_injection_points(data)
    if head_close is not None:
        data = data[:head_close] + style + data[head_close:]
        if body_open is not None and head_close <= body_open:
            body_open += len(style)
        if body_close is not None and head_close <= body_close:
            body_close += len(style)
    else:
        inject = style + inject
    if body_open is not None:
        return data[:body_open] + inject + data[body_open:]
    if body_close is not None:
        return data[:body_close] + inject + data[body_close:]
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
    try:
        # 0600: the state names folders the user has opened. os.replace keeps
        # the temp file's mode, so the final file is private too.
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(state, ensure_ascii=False, indent=2) + "\n")
        os.replace(temp, path)
    finally:
        try:
            temp.unlink()
        except OSError:
            pass


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


def hidden_path(raw_path: str) -> bool:
    """True when a request path names a dot entry.

    Ribbon serves a folder of apps, never dotfiles: .git carries cloneable
    history and remote URLs, and .env carries secrets. Decode first, because
    translate_path() decodes too, so %2e must not slip past the check.
    """
    try:
        decoded = unquote(raw_path, errors="surrogatepass")
    except UnicodeDecodeError:
        decoded = unquote(raw_path)
    return any(part.startswith(".") for part in decoded.split("/"))


def contained_target(root: Path, target: Path) -> Path | None:
    """Resolve target, or return None when a symlink leads outside root."""
    try:
        resolved = target.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    return resolved


class RibbonHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = HANDLER_TIMEOUT
    root: Path = APP_DIR.parent
    include_untitled: bool = False
    token: str = ""
    write_enabled: bool = False
    allowed_origins: ClassVar[set[str]] = set()
    # BaseHTTPRequestHandler would send "SimpleHTTP/0.6 Python/3.15.2". The
    # interpreter version is not the client's business.
    server_version = "Ribbon"
    sys_version = ""

    def version_string(self) -> str:
        return self.server_version

    def log_message(self, fmt: str, *args) -> None:
        if getattr(self.server, "verbose", False):
            super().log_message(fmt, *args)

    def do_GET(self) -> None:
        self._handle(head=False)

    def do_HEAD(self) -> None:
        self._handle(head=True)

    def do_POST(self) -> None:
        from git_actions import run_git_action

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
        """Reject other websites, not other projects.

        Every project is served from this origin and can read the token from
        its own page or from manifest.json. This guard stops a page on another
        site from driving the action API; it cannot tell a project script from
        the bar. See "Trust boundary" in AGENTS.md.
        """
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
        if len(payload) >= GZIP_MIN_BYTES and self._accepts_gzip():
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

        if hidden_path(raw_path):
            self.send_error(404, "File not found")
            return

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

        target = contained_target(
            self.root.resolve(), Path(self.translate_path(raw_path))
        )
        if target is None:
            self.send_error(404, "File not found")
            return

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

        if name in STATIC_ASSETS:
            # Only a URL carrying the current asset_version() may be pinned:
            # a rebuilt file gets a new ?v=, so the old URL never changes.
            # A saved page or hand-written reference has no query string and
            # must revalidate instead of staying frozen for a year.
            requested = (parse_qs(urlsplit(self.path).query).get("v") or [""])[0]
            if requested == asset_version():
                cache_control = "public, max-age=31536000, immutable"
            else:
                cache_control = "no-cache"
            # Hash the source bytes, before gzip, so a revalidation can answer
            # 304 without paying for a compression it would throw away.
            etag = self._etag_for(payload)
            if self._etag_matches(etag):
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", cache_control)
                self.send_header("Vary", "Accept-Encoding")
                self.end_headers()
                return
            body, gzipped = self._response_body(payload)
            self._write_body(
                body,
                content_type,
                cache_control,
                head,
                etag=etag,
                gzipped=gzipped,
            )
            return
        body, gzipped = self._response_body(payload)
        self._write_body(
            body,
            content_type,
            "no-store, max-age=0",
            head,
            gzipped=gzipped,
        )


class RibbonHTTPServer(ThreadingHTTPServer):
    address_family = socket.AF_INET


class RibbonHTTPServerV6(RibbonHTTPServer):
    address_family = socket.AF_INET6


def url_host(host: str) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


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
        "--host",
        default="127.0.0.1",
        help=(
            "address to listen on (default: 127.0.0.1). Any other address lets "
            "other devices on the network read every project, with no password"
        ),
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

    if args.root:
        root = Path(args.root).expanduser().resolve()
    else:
        root = default_root()
        if root is None:
            parser.error(
                "could not find a projects folder near ribbon.py. "
                "Pick one with --root FOLDER, for example --root ~/my-projects"
            )
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
    server_cls = RibbonHTTPServerV6 if ":" in args.host else RibbonHTTPServer
    for port in range(args.port, args.port + 20):
        try:
            httpd = server_cls((args.host, port), handler)
            break
        except OSError:
            continue
    if httpd is None:
        parser.error(f"no free port in {args.port}-{args.port + 19}")

    httpd.verbose = args.verbose  # type: ignore[attr-defined]
    chosen_port = httpd.server_address[1]
    host_for_url = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    host_for_url = url_host(host_for_url)
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

    if not local_host:
        print()
        print("  WARNING: Ribbon is listening beyond this computer.")
        print(f"  Address {args.host}, port {chosen_port}.")
        print(f"  Anyone who can reach it can read every project under {root},")
        print("  plus the app list and Git status. There is no password.")
        print("  Use a network you trust. Git actions, deletes, and saved state")
        print("  stay off.")

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
