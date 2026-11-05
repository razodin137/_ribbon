"""Folder tree, folder stats and the gitignore engine for Ribbon.

`folder_tree` lists every entry in a folder with its ignore status, asking Git
when the folder is inside a repository and falling back to a small pattern
matcher when it is not. `folder_stats` and `folder_info` build the compact
summary shown on a folder card.
"""

from __future__ import annotations

import subprocess
from fnmatch import fnmatchcase
from pathlib import Path

from config import IMAGE_SUFFIXES, type_color
from content import fallback_title
from git_repo import (
    GITIGNORE_PREVIEW_CHARS,
    SECRET_NAMES,
    SECRET_SUFFIXES,
    _git_env,
    _git_text,
)


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
