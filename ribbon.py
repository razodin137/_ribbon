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
import hashlib
import json
import os
import secrets
import shlex
import shutil
import socket
import threading
import webbrowser
import zlib
from functools import partial
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs, quote, unquote, urlsplit

import assets
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
from config import (
    APP_DIR,
    CARD_ROUTE,
    DEFAULT_TYPE_COLOR,
    GZIP_MIN_BYTES,
    HANDLER_TIMEOUT,
    HTML_SUFFIXES,
    IMAGE_SUFFIXES,
    MARKDOWN_SUFFIXES,
    MAX_README_CHARS,
    PREFERRED_HTML,
    PREFERRED_MARKDOWN,
    README_COMMIT_MESSAGE,
    README_NAMES,
    STATE_LABELS,
    STATIC_ASSETS,
    TYPE_COLORS,
    VERSION,
    type_color,
)
from content import (
    META_DESCRIPTION_FIRST_RE,
    META_DESCRIPTION_RE,
    TITLE_RE,
    _page_meta,
    choose_html,
    choose_markdown,
    clean_markdown,
    clean_title,
    extract_description,
    extract_title,
    fallback_title,
    find_readme,
    markdown_summary,
    markdown_title,
    page_meta,
    project_kind,
    read_markdown,
    read_readme,
    readme_state,
    readme_summary,
)
from discover import (
    clear_cache,
    directory_app,
    discover,
    markdown_info,
    page_card_info,
    project_info,
)
from inject import (
    RAW_TEXT_TAGS,
    html_injection_points,
    inject_html,
    iter_html_tags,
)
from markdown_render import markdown_view_html
from remove import delete_plan, remove_directory
from roots import (
    SYSTEM_ROOTS,
    child_dirs,
    default_root,
    is_container,
    is_safe_default_root,
)
from scan import (
    SKIP_DIRS,
    TREE_MAX_ENTRIES,
    TREE_SKIP_DESCENT,
    _git_check_ignored,
    _gitignore_patterns,
    _gitignore_source,
    _likely_secret,
    _plain_ignored,
    folder_entries,
    folder_info,
    folder_stats,
    folder_tree,
)
from server import (
    RibbonHandler,
    RibbonHTTPServer,
    RibbonHTTPServerV6,
    contained_target,
    hidden_path,
    url_host,
)
from state import (
    STATE_DIR_NAME,
    STATE_LOCK,
    STATE_VERSION,
    apply_signal,
    empty_state,
    load_state,
    public_state,
    save_state,
    state_home,
    state_path,
)


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
    parser = build_parser()
    args = parser.parse_args()
    assets.DEV_ASSETS = args.dev

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

    missing = assets.missing_assets(args.dev)
    if missing:
        if args.dev:
            parser.error(
                "--dev needs these files beside ribbon.py: " + ", ".join(missing)
            )
        parser.error(
            "this assets.py has no embedded copy of "
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
