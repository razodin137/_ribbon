"""Command line entry point for Ribbon.

Reads the arguments, prints what was found, and starts the server. `ribbon.py`
stays a thin launcher so `python3 ribbon.py` keeps working.
"""

from __future__ import annotations

import argparse
import secrets
import threading
import webbrowser
from functools import partial
from pathlib import Path

import assets
from config import VERSION
from discover import discover
from roots import default_root
from server import RibbonHandler, RibbonHTTPServer, RibbonHTTPServerV6, url_host
from state import state_path


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
