"""Page metadata and Markdown summaries for Ribbon.

Reads a page's head for its title and description, and decides which HTML or
Markdown file a folder should show. Everything here is read-only; the one cache
is keyed by the file stamp, so an edited page is read again.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from html import unescape
from pathlib import Path

from config import (
    HTML_SUFFIXES,
    MARKDOWN_SUFFIXES,
    PREFERRED_HTML,
    PREFERRED_MARKDOWN,
    README_NAMES,
)


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
