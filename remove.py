"""Folder deletion for Ribbon.

`delete_plan` checks that a request names a direct child folder of the root and
builds the exact command the bar shows. `remove_directory` runs that command,
then forgets the folder's state and cached scan. Ribbon's own folder, symlinks,
and paths outside the root are refused before anything runs.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from config import APP_DIR
from discover import clear_cache
from git_repo import GIT_CACHE, _action_error, _action_ok
from state import STATE_LOCK, load_state, save_state


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
    clear_cache()
    return {
        **_action_ok(output),
        "dir": key,
        "path": path,
        "command": command,
    }
