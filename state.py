"""Per-root state for Ribbon.

Opens are counted in a small JSON file under the user's state folder, keyed by
the served root. The file names folders the user has opened, so it is written
with mode 0600. Nothing here touches the served folder.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path


STATE_VERSION = 1
STATE_DIR_NAME = "ribbon"
STATE_LOCK = threading.Lock()


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
