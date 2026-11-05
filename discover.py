"""App discovery and card payloads for Ribbon.

`discover` turns every immediate child folder of the root into one card, asking
Git for status when asked to. Its result is cached for a moment so the cards
and the manifest share one scan; `clear_cache` forgets it after a delete.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

from config import APP_DIR, CARD_ROUTE, SKIP_DIRS, type_color
from content import (
    choose_html,
    choose_markdown,
    extract_description,
    extract_title,
    fallback_title,
    markdown_summary,
    markdown_title,
    project_kind,
    read_markdown,
    readme_summary,
)
from git_repo import GIT_CACHE_SECONDS, GIT_STATUS_WORKERS, git_status
from scan import folder_entries, folder_info, folder_stats


_cache: dict[str, object] = {"at": 0.0, "root": "", "apps": []}


def clear_cache() -> None:
    """Forget the last scan, so a removed folder drops out at once."""
    _cache["at"] = 0.0


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
