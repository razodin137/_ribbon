"""Git discovery and inspection for Ribbon.

The read path: repository status, the locks that keep concurrent reads from
duplicating work, git-detail payloads, and the GitHub Pages checks that only
look at the worktree and `.git/config`. `git_actions` imports this module; the
write path stays there.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path


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
GITIGNORE_PREVIEW_CHARS = 4000


class _PooledLock:
    """A lock borrowed from a pool, dropping its key when the last user is done."""

    def __init__(self, pool: "_LockPool", key: str, lock: threading.Lock) -> None:
        self._pool = pool
        self._key = key
        self._lock = lock
        self._dropped = False

    def acquire(self, blocking: bool = True) -> bool:
        acquired = self._lock.acquire(blocking)
        if not acquired:
            self._drop()
        return acquired

    def release(self) -> None:
        self._lock.release()
        self._drop()

    def __enter__(self) -> "_PooledLock":
        self.acquire()
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()

    def _drop(self) -> None:
        if self._dropped:
            return
        self._dropped = True
        self._pool.release(self._key)


class _LockPool:
    """One lock per key, forgotten when the last caller lets go.

    A plain dict of locks grows for the life of the process: every repo and
    every path ever queried. Counting references lets a key go away as soon as
    no caller holds or waits on its lock, without dropping a lock someone else
    still needs.
    """

    def __init__(self) -> None:
        self._guard = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._users: dict[str, int] = {}

    def get(self, key: str) -> _PooledLock:
        with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._locks[key] = lock
                self._users[key] = 0
            self._users[key] += 1
            return _PooledLock(self, key, lock)

    def release(self, key: str) -> None:
        with self._guard:
            count = self._users.get(key, 0) - 1
            if count > 0:
                self._users[key] = count
                return
            self._users.pop(key, None)
            self._locks.pop(key, None)


GIT_CACHE: dict[str, tuple[float, dict]] = {}
GIT_STATUS_LOCKS = _LockPool()
GIT_CACHE_SECONDS = 2.0
# A cold manifest pays for one `git status` per folder. Running a handful at
# once turns that serial wait into roughly the slowest repo instead of the sum.
GIT_STATUS_WORKERS = 8
# The bar redraws on every page load. Re-scanning every repository each time
# makes a fast click feel like a stall, so the manifest reuses Git lights for
# a few seconds. The Git panel still asks for fresh detail when it opens.
GIT_LIGHT_SECONDS = 10.0

GIT_LOCKS = _LockPool()


def repo_lock(path: Path) -> _PooledLock:
    return GIT_LOCKS.get(str(path.resolve()))


GIT_ENV_STRIP = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
    "GIT_CEILING_DIRECTORIES",
)


def _git_env() -> dict[str, str]:
    """Environment for git commands, stripped of repo-selection variables.

    A caller's shell may export GIT_DIR, GIT_INDEX_FILE, or GIT_WORK_TREE.
    Inherited, they override `git -C <path>` and point the command at another
    repository, so every git process Ribbon starts drops them.
    """
    env = os.environ.copy()
    for name in GIT_ENV_STRIP:
        env.pop(name, None)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def _git(path: Path, args: list[str], timeout: float = 4) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=_git_env(),
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


def _git_status_lock(key: str) -> _PooledLock:
    return GIT_STATUS_LOCKS.get(key)


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
    from ribbon import SKIP_DIRS

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
    from ribbon import SKIP_DIRS

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
    from ribbon import readme_state

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


def _repo_root(path: Path) -> Path | None:
    root = _git_text(path, ["rev-parse", "--show-toplevel"])
    return Path(root) if root else None


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
    from ribbon import choose_html

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
