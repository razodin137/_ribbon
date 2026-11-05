"""Root auto-detection and its safety guard.

Ribbon serves the whole root as static files, so a guess that lands too high
would expose more of the disk than the user meant. `default_root` finds the
projects folder beside the app; `is_safe_default_root` refuses the filesystem
root, a home folder, and system folders.
"""

from __future__ import annotations

from pathlib import Path

from config import APP_DIR, SKIP_DIRS
from content import choose_html, project_kind


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
