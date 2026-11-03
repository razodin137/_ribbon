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
import shutil
import subprocess
import threading
import time
import webbrowser
from functools import partial
from html import escape, unescape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs, quote, unquote, urlsplit

APP_DIR = Path(__file__).resolve().parent
VERSION = "1.2.0"
HTML_SUFFIXES = (".html", ".htm")
CARD_ROUTE = "/__ribbon/card/"
PREFERRED_HTML = ("index.html", "app.html", "main.html", "home.html", "site.html", "start.html")
README_NAMES = ("README.md", "readme.md", "README.markdown", "README.txt", "README", "README.rst")
README_COMMIT_MESSAGE = "Add README"
MAX_README_CHARS = 20000

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


def app_child_count(path: Path) -> int:
    """How many direct child folders Ribbon would list."""
    try:
        entries = list(path.iterdir())
    except OSError:
        return 0
    count = 0
    for entry in entries:
        if entry.resolve() == APP_DIR:
            continue
        if (
            entry.is_dir()
            and not entry.name.startswith(".")
            and entry.name not in SKIP_DIRS
            and is_app_folder(entry)
        ):
            count += 1
    return count


def default_root() -> Path:
    """The folder that most likely holds the user's apps.

    If _ribbon sits beside the apps, that folder wins. If it sits inside one
    app (the original layout), the folder one level further up wins.
    """
    parent = APP_DIR.parent
    if app_child_count(parent) > 0:
        return parent
    grandparent = parent.parent
    if grandparent != parent and app_child_count(grandparent) > 0:
        return grandparent
    return parent


TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
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


def choose_html(filenames: list[str] | set[str]) -> str | None:
    """Pick the page a folder should open, preferring index.html."""
    names = {name for name in filenames if Path(name).suffix.lower() in HTML_SUFFIXES}
    for preferred in PREFERRED_HTML:
        if preferred in names:
            return preferred
    if not names:
        return None
    return sorted(names, key=str.lower)[0]


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


def readme_summary(path: Path) -> tuple[str, str]:
    text = read_readme(path)
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
            if isinstance(scripts, dict):
                if "start" not in scripts and "dev" in scripts:
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
    if pick("readme.md", "readme.markdown", "readme.txt", "readme.rst", "readme"):
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


def accent_color(rel_dir: str) -> str:
    digest = hashlib.sha1(rel_dir.encode("utf-8")).digest()
    hue = digest[0] * 360 // 256
    return f"hsl({hue} 46% 62%)"


def project_info(path: Path, rel_dir: str) -> dict | None:
    try:
        filenames = [entry.name for entry in path.iterdir() if entry.is_file()]
    except OSError:
        return None
    kind = project_kind(path, filenames)
    if not kind:
        return None
    title, description = readme_summary(path)
    return {
        "kind": "project",
        "title": title or fallback_title(rel_dir),
        "description": description,
        "type": kind["type"],
        "icon": kind["icon"],
        "run": kind["run"],
        "files": folder_entries(path),
        "color": accent_color(rel_dir),
    }


def has_git_ancestor(path: Path, root: Path) -> bool:
    """True when a parent folder between path and root is a Git repository."""
    parent = path.parent
    while parent != root and parent != parent.parent:
        if (parent / ".git").exists():
            return True
        parent = parent.parent
    return False


def is_app_folder(path: Path) -> bool:
    try:
        filenames = [entry.name for entry in path.iterdir() if entry.is_file()]
    except OSError:
        return False
    html = choose_html(filenames)
    if html:
        return not is_shell_page(path / html)
    return project_kind(path, filenames) is not None


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
    info = header[3:] if header.startswith("## ") else ""

    counts = ""
    if " [" in info and info.endswith("]"):
        info, counts = info[:-1].split(" [", 1)

    branch = None
    upstream = None
    detached = False
    no_commits = False

    if info == "HEAD (no branch)":
        detached = True
    elif info.startswith("No commits yet on "):
        no_commits = True
        branch = info[len("No commits yet on ") :]
    elif "..." in info:
        branch, upstream = info.split("...", 1)
    else:
        branch = info or None

    ahead = 0
    behind = 0
    for match in re.finditer(r"(ahead|behind) (\d+)", counts):
        if match.group(1) == "ahead":
            ahead = int(match.group(2))
        else:
            behind = int(match.group(2))

    conflicted = any(line[:2] in {"UU", "AA", "DD", "AU", "UA", "DU", "UD"} for line in file_lines)
    gone = "gone" in counts
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


def file_warnings(root: Path, files: list[dict]) -> list[str]:
    warnings: list[str] = []
    if files and not (root / ".gitignore").is_file():
        warnings.append("No .gitignore — generated folders may be committed.")

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
        detail["pages"] = pages_state(path)
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
    detail["warnings"] = file_warnings(root, files)
    detail["has_gitignore"] = (root / ".gitignore").is_file()
    detail["readme"] = readme_state(root)
    detail["identity_ok"] = bool(_git_text(root, ["config", "user.name"])) and bool(
        _git_text(root, ["config", "user.email"])
    )
    detail["pages"] = pages_state(root)
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


def pages_state(path: Path) -> dict:
    try:
        names = [entry.name for entry in path.iterdir() if entry.is_file()]
    except OSError:
        names = []
    return {
        "index": (path / "index.html").is_file(),
        "entry": choose_html(names),
    }


def pages_requirement(root: Path) -> str | None:
    if (root / "index.html").is_file():
        return None
    entry = pages_state(root)["entry"]
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


def git_create_pages_entry(target: Path) -> dict:
    root = _repo_root(target) or target
    if (root / "index.html").is_file():
        return _action_error("This repository already has an index.html.")
    try:
        names = [entry.name for entry in root.iterdir() if entry.is_file()]
    except OSError as exc:
        return _action_error(f"Could not read the repository folder: {exc}")
    entry = choose_html(names)
    if not entry:
        return _action_error(
            "No HTML page was found. Add one first, then create the Pages entry."
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


def discover(
    root: Path,
    include_untitled: bool = False,
    with_git: bool = False,
    max_age: float = 1.0,
    git_max_age: float = GIT_CACHE_SECONDS,
) -> list[dict]:
    """Every page or project folder under root, in stable path order."""
    now = time.monotonic()
    cache_key = f"{root}|{int(include_untitled)}|{int(with_git)}"
    if (
        _cache["root"] == cache_key
        and now - float(_cache["at"]) < max_age
    ):
        return _cache["apps"]  # type: ignore[return-value]

    apps: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(root):
        directory = Path(dirpath)
        dirnames[:] = sorted(
            d
            for d in dirnames
            if d not in SKIP_DIRS
            and not d.startswith(".")
            and directory / d != APP_DIR
        )
        if directory == APP_DIR:
            continue

        html = choose_html(filenames)
        page = directory / html if html else None
        if page is not None and is_shell_page(page):
            continue

        if page is not None:
            title = extract_title(page)
            if not title and not include_untitled:
                continue
            rel_dir = page.parent.relative_to(root).as_posix()
            rel_file = page.relative_to(root).as_posix()
            if rel_dir == ".":
                url = "/" if page.name == "index.html" else "/" + quote(page.name)
            else:
                url = "/" + quote(rel_dir, safe="/") + "/"
                if page.name != "index.html":
                    url += quote(page.name)
            try:
                mtime = int(page.stat().st_mtime)
            except OSError:
                mtime = 0
            app = {
                "kind": "page",
                "url": url,
                "file": "/" + quote(rel_file, safe="/"),
                "path": rel_dir,
                "title": title or fallback_title(rel_dir),
                "mtime": mtime,
                "color": accent_color(rel_dir),
            }
            if with_git:
                app["git"] = git_status(directory, max_age=git_max_age)
            apps.append(app)
            continue

        info = project_info(directory, directory.relative_to(root).as_posix())
        if not info or has_git_ancestor(directory, root):
            continue
        try:
            mtime = int(directory.stat().st_mtime)
        except OSError:
            mtime = 0
        rel_dir = directory.relative_to(root).as_posix()
        app = {
            **info,
            "url": CARD_ROUTE + (quote(rel_dir, safe="/") + "/" if rel_dir != "." else ""),
            "file": "",
            "path": rel_dir,
            "mtime": mtime,
        }
        if with_git:
            app["git"] = git_status(directory, max_age=git_max_age)
        apps.append(app)

    apps.sort(key=lambda app: app["path"].lower())
    _cache.update(at=now, root=cache_key, apps=apps)
    return apps


def inject_html(data: bytes, token: str = "") -> bytes:
    if SHELL_MARKER in data or b"data-ribbon" in data or b"/__ribbon/ribbon.js" in data:
        return data
    attrs = b' data-ribbon="1"'
    if token:
        attrs += b' data-ribbon-token="' + token.encode("utf-8") + b'"'
    inject = b'<script src="/__ribbon/ribbon.js"' + attrs + b" defer></script>"
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
            url = os.path.relpath(
                root / app["file"].lstrip("/"), APP_DIR
            ).replace(os.sep, "/")
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
        fields.append("git: " + js_literal(app["git"]))
        comma = "," if index < len(apps) - 1 else ""
        lines.append("  { " + ", ".join(fields) + " }" + comma)
    lines.append("]")

    target = APP_DIR / "apps.js"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target, len(apps)


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
        if urlsplit(self.path).path != "/__ribbon/git":
            self.send_error(404, "Not found")
            return

        if not self.write_enabled:
            self._send_json(
                {
                    "ok": False,
                    "error": "Git actions are disabled. Start ribbon.py on 127.0.0.1 without --no-git-actions.",
                },
                403,
            )
            return

        origin = self.headers.get("Origin")
        if origin and origin not in self.allowed_origins:
            self._send_json(
                {"ok": False, "error": "This request did not come from the ribbon page."},
                403,
            )
            return

        content_type = (self.headers.get("Content-Type") or "").lower()
        if not content_type.startswith("application/json"):
            self._send_json({"ok": False, "error": "Expected JSON."}, 415)
            return

        token = self.headers.get("X-Ribbon-Token") or ""
        if not secrets.compare_digest(token, self.token):
            self._send_json(
                {"ok": False, "error": "Missing or wrong ribbon token."}, 403
            )
            return

        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        if length <= 0 or length > 65536:
            self._send_json({"ok": False, "error": "Bad request size."}, 400)
            return

        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json({"ok": False, "error": "Bad JSON."}, 400)
            return
        if not isinstance(body, dict):
            self._send_json({"ok": False, "error": "Bad request."}, 400)
            return

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
                elif project_kind(target, names):
                    rel = target.relative_to(self.root.resolve()).as_posix()
                    return self._serve_card(
                        CARD_ROUTE + (quote(rel, safe="/") + "/" if rel != "." else ""),
                        head,
                    )
            target = index

        if target.is_file() and target.suffix.lower() in (".html", ".htm"):
            return self._serve_html(target, head)

        if head:
            super().do_HEAD()
        else:
            super().do_GET()

    def _serve_html(self, target: Path, head: bool) -> None:
        try:
            token = self.token if self.write_enabled else ""
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
        info = project_info(target, rel_dir)
        if not info:
            self.send_error(404, "No project here")
            return
        info["path"] = rel_dir
        try:
            info["mtime"] = int(target.stat().st_mtime)
        except OSError:
            info["mtime"] = 0

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
        ).encode("utf-8")
        payload = inject_html(doc, self.token if self.write_enabled else "")

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
                        "token": self.token if self.write_enabled else "",
                        "write": self.write_enabled,
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif name == "ribbon.js":
                payload = (APP_DIR / "ribbon.js").read_bytes()
                content_type = "text/javascript; charset=utf-8"
            elif name == "card.js":
                payload = (APP_DIR / "card.js").read_bytes()
                content_type = "text/javascript; charset=utf-8"
            elif name == "card.css":
                payload = (APP_DIR / "card.css").read_bytes()
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
            else:
                self.send_error(404, "Not found")
                return
        except OSError:
            self.send_error(500, "Ribbon asset missing")
            return

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.end_headers()
        if not head:
            self.wfile.write(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ribbon.py",
        description="Browse a folder of HTML apps with a floating switcher bar.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python3 ribbon.py                 start the server and open the first app\n"
            "  python3 ribbon.py --list          show every app it can find, then quit\n"
            "  python3 ribbon.py --write-apps    refresh apps.js for the static shell\n"
            "  python3 ribbon.py --app 3         start on app number 3\n"
            "  python3 ribbon.py --root ~/sites --port 9000\n"
            "\n"
            "Ribbon looks for the folder that holds your apps: beside this script\n"
            "first, then one level further up. Use --root to point it anywhere.\n"
            "It lists folders with an HTML page (index.html preferred) or a project."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")

    commands = parser.add_argument_group("commands")
    commands.add_argument(
        "--list", action="store_true", help="list the apps it found and quit"
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
        help="open app number N instead of the first",
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
        help="also list pages that have no <title>",
    )
    return parser


def state_label(app: dict) -> str:
    state = (app.get("git") or {}).get("state", "")
    return STATE_LABELS.get(state, state)


def print_apps(root: Path, apps: list[dict]) -> None:
    noun = "app" if len(apps) == 1 else "apps"
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
    print(f"\n  No apps found in {root}\n")
    print("  Ribbon lists folders with an HTML page (index.html preferred)")
    print("  or a project folder with a README, script, or build file.")
    if not include_untitled:
        print("  Pages without a title are skipped by default:\n")
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
    RibbonHandler.write_enabled = write_enabled
    RibbonHandler.token = secrets.token_urlsafe(24) if write_enabled else ""
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
    print(f"  apps    {len(apps)}")
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
    print("  keys    [ ] prev/next · r random · h hide · Ctrl+C stop")
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
