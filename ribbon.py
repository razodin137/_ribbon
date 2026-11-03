#!/usr/bin/env python3
"""
Ribbon — browse a folder of standalone HTML apps with a floating top banner.

Run this from anywhere:

    python3 ribbon.py

It serves the folder above this script (override with --root), auto-discovers
every index.html underneath it, injects ribbon.js into served HTML, and opens
the first app. Nothing on disk is modified.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import threading
import time
import webbrowser
from functools import partial
from html import unescape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

APP_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = APP_DIR.parent.parent

SKIP_DIRS = {
    "node_modules",
    "venv",
    "env",
    "__pycache__",
    "site-packages",
    "vendor",
    "bower_components",
    "dist",
    "build",
    "out",
    "target",
    "coverage",
}

TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
BODY_CLOSE_RE = re.compile(rb"</body\s*>", re.IGNORECASE)
INJECT = b'<script src="/__ribbon/ribbon.js" data-ribbon="1" defer></script>'
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


def is_shell_page(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return SHELL_MARKER in fh.read(8192)
    except OSError:
        return False


GIT_CACHE: dict[str, tuple[float, dict]] = {}
GIT_CACHE_SECONDS = 2.0


def read_git_status(path: Path) -> dict:
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(path),
                "status",
                "--porcelain=v1",
                "--branch",
                "--untracked-files=normal",
            ],
            capture_output=True,
            text=True,
            timeout=4,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"repo": False, "state": "error"}

    if proc.returncode != 0:
        return {"repo": False, "state": "no-repo"}

    lines = proc.stdout.splitlines()
    header = lines[0] if lines else ""
    dirty = len(lines) > 1
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

    gone = "gone" in counts
    if detached:
        state = "detached"
    elif no_commits:
        state = "no-commits"
    elif ahead > 0:
        state = "ahead"
    elif not upstream or gone:
        state = "no-upstream"
    elif dirty:
        state = "dirty"
    else:
        state = "clean"

    return {
        "repo": True,
        "branch": branch,
        "upstream": upstream,
        "ahead": ahead,
        "behind": behind,
        "dirty": dirty,
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


def discover(
    root: Path,
    include_untitled: bool = False,
    with_git: bool = False,
    max_age: float = 1.0,
) -> list[dict]:
    """Every titled index.html under root, in stable path order."""
    now = time.monotonic()
    cache_key = f"{root}|{int(include_untitled)}|{int(with_git)}"
    if (
        _cache["root"] == cache_key
        and now - float(_cache["at"]) < max_age
    ):
        return _cache["apps"]  # type: ignore[return-value]

    apps: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")
        )
        if "index.html" not in filenames:
            continue

        page = Path(dirpath) / "index.html"
        if is_shell_page(page):
            continue

        title = extract_title(page)
        if not title and not include_untitled:
            continue

        rel_dir = page.parent.relative_to(root).as_posix()
        rel_file = page.relative_to(root).as_posix()
        url = "/" if rel_dir == "." else "/" + quote(rel_dir, safe="/") + "/"
        try:
            mtime = int(page.stat().st_mtime)
        except OSError:
            mtime = 0

        app = {
            "url": url,
            "file": "/" + quote(rel_file, safe="/"),
            "path": rel_dir,
            "title": title or fallback_title(rel_dir),
            "mtime": mtime,
        }
        if with_git:
            app["git"] = git_status(page.parent)

        apps.append(app)

    apps.sort(key=lambda app: app["path"].lower())
    _cache.update(at=now, root=cache_key, apps=apps)
    return apps


def inject_html(data: bytes) -> bytes:
    if SHELL_MARKER in data or b"data-ribbon" in data or b"/__ribbon/ribbon.js" in data:
        return data
    matches = list(BODY_CLOSE_RE.finditer(data))
    if matches:
        index = matches[-1].start()
        return data[:index] + INJECT + data[index:]
    return data + INJECT


def write_apps_file(root: Path, include_untitled: bool) -> tuple[Path, int]:
    apps = discover(root, include_untitled=include_untitled, with_git=True, max_age=0)
    lines = [
        "/* Generated by _ribbon/ribbon.py --write-apps. Re-run after adding a folder. */",
        "window.__RIBBON_APPS__ = [",
    ]
    for index, app in enumerate(apps):
        relative = os.path.relpath(
            root / app["file"].lstrip("/"), APP_DIR
        ).replace(os.sep, "/")
        comma = "," if index < len(apps) - 1 else ""
        lines.append(
            "  { url: %s, title: %s, dir: %s, git: %s }%s"
            % (
                json.dumps(relative, ensure_ascii=False),
                json.dumps(app["title"], ensure_ascii=False),
                json.dumps(app["path"], ensure_ascii=False),
                json.dumps(app["git"], ensure_ascii=False),
                comma,
            )
        )
    lines.append("];")

    target = APP_DIR / "apps.js"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target, len(apps)


class RibbonHandler(SimpleHTTPRequestHandler):
    root: Path = DEFAULT_ROOT
    include_untitled: bool = False

    def log_message(self, fmt: str, *args) -> None:
        if getattr(self.server, "verbose", False):
            super().log_message(fmt, *args)

    def do_GET(self) -> None:  # noqa: N802
        self._handle(head=False)

    def do_HEAD(self) -> None:  # noqa: N802
        self._handle(head=True)

    def _handle(self, head: bool) -> None:
        raw_path = urlsplit(self.path).path

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
            target = target / "index.html"

        if target.is_file() and target.suffix.lower() in (".html", ".htm"):
            return self._serve_html(target, head)

        if head:
            super().do_HEAD()
        else:
            super().do_GET()

    def _serve_html(self, target: Path, head: bool) -> None:
        try:
            data = inject_html(target.read_bytes())
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

    def _serve_asset(self, name: str, head: bool) -> None:
        try:
            if name == "manifest.json":
                payload = json.dumps(
                    {
                        "apps": discover(
                            self.root,
                            include_untitled=self.include_untitled,
                            with_git=True,
                        )
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif name == "ribbon.js":
                payload = (APP_DIR / "ribbon.js").read_bytes()
                content_type = "text/javascript; charset=utf-8"
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
                    git_status(target), ensure_ascii=False
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve a folder of HTML apps with a floating ribbon switcher."
    )
    parser.add_argument(
        "--root",
        default=str(DEFAULT_ROOT),
        help="folder to scan and serve (default: the folder above this script)",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-open", action="store_true", help="don't open a browser")
    parser.add_argument(
        "--include-untitled",
        action="store_true",
        help="also list index.html pages that have no <title>",
    )
    parser.add_argument("--list", action="store_true", help="list discovered apps and exit")
    parser.add_argument(
        "--write-apps",
        action="store_true",
        help="write apps.js for the static shell and exit",
    )
    parser.add_argument("--verbose", action="store_true", help="log every request")
    args = parser.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        parser.error(f"not a folder: {root}")

    if args.write_apps:
        target, count = write_apps_file(root, args.include_untitled)
        print(f"wrote {target} ({count} apps)")
        return

    if args.list:
        apps = discover(
            root,
            include_untitled=args.include_untitled,
            with_git=True,
            max_age=0,
        )
        for index, app in enumerate(apps, 1):
            state = (app.get("git") or {}).get("state", "")
            suffix = f"  [{state}]" if state else ""
            print(f"{index:2d}  {app['title']}{suffix}\n    {app['url']}")
        if not apps:
            print("No index.html files found.")
        return

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
    host_for_url = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    url = f"http://{host_for_url}:{httpd.server_address[1]}/"
    apps = discover(
        root,
        include_untitled=args.include_untitled,
        with_git=False,
        max_age=0,
    )

    print(f"\n  Ribbon → {url}")
    print(f"  root   → {root}")
    print(f"  apps   → {len(apps)}")
    shell = APP_DIR / "index.html"
    if shell.is_file():
        try:
            shell_rel = shell.parent.relative_to(root).as_posix()
        except ValueError:
            shell_rel = ""
        if shell_rel and shell_rel != ".":
            print(f"  shell  → {url}{quote(shell_rel, safe='/')}/")
        elif shell_rel == ".":
            print(f"  shell  → {url}")
    print("  keys   → [ ] prev/next · r random · h hide\n")

    if not args.no_open:
        timer = threading.Timer(0.4, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  bye\n")


if __name__ == "__main__":
    main()
