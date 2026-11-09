"""HTTP handler and server classes for Ribbon.

`hidden_path` and `contained_target` guard every request, `RibbonHandler`
serves pages, cards, assets and the write endpoints, and the two server
classes pick the address family. `main()` in ribbon.py builds the handler and
sets its class attributes.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import socket
import zlib
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs, quote, unquote, urlsplit

import assets
from config import (
    APP_DIR,
    CARD_ROUTE,
    GZIP_MIN_BYTES,
    HANDLER_TIMEOUT,
    HTML_SUFFIXES,
    MARKDOWN_SUFFIXES,
    STATIC_ASSETS,
)
from content import choose_html, markdown_title, read_markdown
from discover import discover, page_card_info, project_info
from git_repo import (
    GIT_CACHE,
    GIT_LIGHT_SECONDS,
    _repo_root,
    git_detail,
    repo_lock,
)
from inject import inject_html
from markdown_render import markdown_view_html
from remove import delete_plan, remove_directory
from scan import folder_info, folder_tree
from state import (
    STATE_LOCK,
    apply_signal,
    load_state,
    public_state,
    save_state,
)


def hidden_path(raw_path: str) -> bool:
    """True when a request path names a dot entry.

    Ribbon serves a folder of apps, never dotfiles: .git carries cloneable
    history and remote URLs, and .env carries secrets. Decode first, because
    translate_path() decodes too, so %2e must not slip past the check.
    """
    try:
        decoded = unquote(raw_path, errors="surrogatepass")
    except UnicodeDecodeError:
        decoded = unquote(raw_path)
    return any(part.startswith(".") for part in decoded.split("/"))


def contained_target(root: Path, target: Path) -> Path | None:
    """Resolve target, or return None when a symlink leads outside root."""
    try:
        resolved = target.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    return resolved


class RibbonHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    timeout = HANDLER_TIMEOUT
    root: Path = APP_DIR.parent
    include_untitled: bool = False
    token: str = ""
    write_enabled: bool = False
    allowed_origins: ClassVar[set[str]] = set()
    # BaseHTTPRequestHandler would send "SimpleHTTP/0.6 Python/3.15.2". The
    # interpreter version is not the client's business.
    server_version = "Ribbon"
    sys_version = ""

    def version_string(self) -> str:
        return self.server_version

    def log_message(self, fmt: str, *args) -> None:
        if getattr(self.server, "verbose", False):
            super().log_message(fmt, *args)

    def do_GET(self) -> None:
        self._handle(head=False)

    def do_HEAD(self) -> None:
        self._handle(head=True)

    def do_POST(self) -> None:
        from git_actions import run_git_action

        route = urlsplit(self.path).path
        if route not in ("/__ribbon/git", "/__ribbon/signal", "/__ribbon/delete"):
            self.send_error(404, "Not found")
            return

        if route == "/__ribbon/git" and not self.write_enabled:
            self._send_json(
                {
                    "ok": False,
                    "error": "Git actions are disabled. Start ribbon.py on 127.0.0.1 without --no-git-actions.",
                },
                403,
            )
            return

        if route == "/__ribbon/delete" and not self.write_enabled:
            self._send_json(
                {
                    "ok": False,
                    "error": "Deleting is disabled. Start ribbon.py on 127.0.0.1 without --no-git-actions.",
                },
                403,
            )
            return

        if not self._post_guard():
            return

        body = self._read_json_body()
        if body is None:
            return

        if route == "/__ribbon/signal":
            return self._handle_signal(body)

        if route == "/__ribbon/delete":
            return self._handle_delete(body)

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

    def _post_guard(self) -> bool:
        """Reject other websites, not other projects.

        Every project is served from this origin and can read the token from
        its own page or from manifest.json. This guard stops a page on another
        site from driving the action API; it cannot tell a project script from
        the bar. See "Trust boundary" in AGENTS.md.
        """
        origin = self.headers.get("Origin")
        if origin and origin not in self.allowed_origins:
            self._send_json(
                {"ok": False, "error": "This request did not come from the ribbon page."},
                403,
            )
            return False

        content_type = (self.headers.get("Content-Type") or "").lower()
        if not content_type.startswith("application/json"):
            self._send_json({"ok": False, "error": "Expected JSON."}, 415)
            return False

        token = self.headers.get("X-Ribbon-Token") or ""
        if not secrets.compare_digest(token, self.token):
            self._send_json(
                {"ok": False, "error": "Missing or wrong ribbon token."}, 403
            )
            return False
        return True

    def _read_json_body(self) -> dict | None:
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            length = 0
        if length <= 0 or length > 65536:
            self._send_json({"ok": False, "error": "Bad request size."}, 400)
            return None
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send_json({"ok": False, "error": "Bad JSON."}, 400)
            return None
        if not isinstance(body, dict):
            self._send_json({"ok": False, "error": "Bad request."}, 400)
            return None
        return body

    def _handle_signal(self, body: dict) -> None:
        if not self.token:
            self._send_json({"ok": False, "error": "State is read-only here."}, 403)
            return

        key = str(body.get("path") or "")
        signal = str(body.get("signal") or "")
        if not key:
            self._send_json({"ok": False, "error": "Missing app path."}, 400)
            return

        apps = discover(
            self.root,
            include_untitled=self.include_untitled,
            with_git=False,
            max_age=0,
        )
        if not any(app.get("path") == key for app in apps):
            self._send_json(
                {"ok": False, "error": "That app is not in the ribbon."}, 404
            )
            return

        with STATE_LOCK:
            state = load_state(self.root)
            try:
                apply_signal(state, key, signal)
            except ValueError:
                self._send_json({"ok": False, "error": "Unknown signal."}, 400)
                return
            save_state(self.root, state)

        self._send_json({"ok": True, "state": public_state(state)})

    def _deletion_plan(self, requested: str) -> dict:
        plan = delete_plan(self.root, requested)
        apps = discover(
            self.root,
            include_untitled=self.include_untitled,
            with_git=False,
            max_age=0,
        )
        if not any(app.get("path") == plan["dir"] for app in apps):
            raise ValueError("That folder is not in the ribbon list.")
        return plan

    def _delete_error(self) -> str | None:
        if not self.write_enabled:
            return "Deleting is disabled. Start ribbon.py on 127.0.0.1 without --no-git-actions."
        token = self.headers.get("X-Ribbon-Token") or ""
        if not self.token or not secrets.compare_digest(token, self.token):
            return "Missing or wrong ribbon token."
        return None

    def _handle_delete(self, body: dict) -> None:
        requested = str(body.get("dir") or "")
        try:
            plan = self._deletion_plan(requested)
        except ValueError as error:
            self._send_json({"ok": False, "error": str(error)}, 400)
            return
        result = remove_directory(self.root, plan)
        self._send_json(result, 200 if result.get("ok") else 409)

    def _accepts_gzip(self) -> bool:
        """Whether the client listed gzip (or *), with a non-zero weight."""
        header = self.headers.get("Accept-Encoding") or ""
        gzip_q = None
        star_q = None
        for item in header.split(","):
            name, _, params = item.strip().partition(";")
            name = name.strip().lower()
            if name not in ("gzip", "*"):
                continue
            q = 1.0
            for param in params.split(";"):
                key, _, value = param.partition("=")
                if key.strip().lower() == "q":
                    try:
                        q = float(value.strip())
                    except ValueError:
                        q = 0.0
            if name == "gzip":
                gzip_q = q
            else:
                star_q = q
        if gzip_q is not None:
            return gzip_q > 0
        return star_q is not None and star_q > 0

    def _response_body(self, payload: bytes) -> tuple[bytes, bool]:
        """The bytes to send, plus whether they carry a gzip header."""
        if len(payload) >= GZIP_MIN_BYTES and self._accepts_gzip():
            compressor = zlib.compressobj(6, zlib.DEFLATED, 16 + zlib.MAX_WBITS)
            return compressor.compress(payload) + compressor.flush(), True
        return payload, False

    def _etag_for(self, body: bytes) -> str:
        return '"' + hashlib.sha256(body).hexdigest()[:16] + '"'

    def _etag_matches(self, etag: str) -> bool:
        header = self.headers.get("If-None-Match")
        if not header:
            return False
        for candidate in header.split(","):
            candidate = candidate.strip()
            if candidate == "*":
                return True
            if candidate.startswith("W/"):
                candidate = candidate[2:].strip()
            if candidate == etag:
                return True
        return False

    def _write_body(
        self,
        body: bytes,
        content_type: str,
        cache_control: str,
        head: bool,
        *,
        status: int = 200,
        etag: str | None = None,
        gzipped: bool = False,
    ) -> None:
        self.send_response(status)
        if etag is not None:
            self.send_header("ETag", etag)
        self.send_header("Cache-Control", cache_control)
        self.send_header("Content-Type", content_type)
        self.send_header("Vary", "Accept-Encoding")
        if gzipped:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _send_payload(
        self,
        payload: bytes,
        content_type: str,
        cache_control: str,
        head: bool,
        *,
        status: int = 200,
        etag: bool = False,
    ) -> None:
        body, gzipped = self._response_body(payload)
        self._write_body(
            body,
            content_type,
            cache_control,
            head,
            status=status,
            etag=self._etag_for(body) if etag else None,
            gzipped=gzipped,
        )

    def _send_json(self, payload: dict, status: int = 200, head: bool = False) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_payload(
            data,
            "application/json; charset=utf-8",
            "no-store, max-age=0",
            head,
            status=status,
        )

    def _handle(self, head: bool) -> None:
        raw_path = urlsplit(self.path).path

        if hidden_path(raw_path):
            self.send_error(404, "File not found")
            return

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
                self.send_header("Content-Length", "0")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return

        target = contained_target(
            self.root.resolve(), Path(self.translate_path(raw_path))
        )
        if target is None:
            self.send_error(404, "File not found")
            return

        if target.is_dir():
            if not raw_path.endswith("/"):
                self.send_response(301)
                self.send_header("Location", raw_path + "/")
                self.send_header("Content-Length", "0")
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
                else:
                    rel = target.relative_to(self.root.resolve()).as_posix()
                    info = project_info(target, rel)
                    if info and info["kind"] == "markdown":
                        markdown = info.get("markdown_path")
                        if markdown:
                            index = self.root.resolve() / markdown
                    else:
                        return self._serve_card(
                            CARD_ROUTE + (quote(rel, safe="/") + "/" if rel != "." else ""),
                            head,
                        )
            target = index

        if target.is_file() and target.suffix.lower() in HTML_SUFFIXES:
            return self._serve_html(target, head)

        if target.is_file() and target.suffix.lower() in MARKDOWN_SUFFIXES:
            return self._serve_markdown(target, head)

        if head:
            super().do_HEAD()
        else:
            super().do_GET()

    def _serve_html(self, target: Path, head: bool) -> None:
        try:
            token = self.token
            data = inject_html(target.read_bytes(), token, assets.asset_version())
        except OSError:
            self.send_error(404, "File not found")
            return

        self._send_payload(
            data,
            "text/html; charset=utf-8",
            "no-store, max-age=0",
            head,
        )

    def _serve_markdown(self, target: Path, head: bool) -> None:
        try:
            resolved = target.resolve()
            rel = resolved.relative_to(self.root.resolve()).as_posix()
            text = read_markdown(resolved)
        except (OSError, ValueError):
            self.send_error(404, "File not found")
            return

        version = assets.asset_version()
        doc = (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{escape(markdown_title(text, rel))}</title>\n"
            f'<link rel="stylesheet" href="{assets.asset_url("card.css", version)}">\n'
            f'<link rel="stylesheet" href="{assets.asset_url("markdown.css", version)}">\n'
            "</head>\n"
            '<body class="rc-doc-body">\n'
            + markdown_view_html(rel, text)
            + "\n</body>\n"
            "</html>\n"
        ).encode("utf-8")
        payload = inject_html(doc, self.token, version)

        self._send_payload(
            payload,
            "text/html; charset=utf-8",
            "no-store, max-age=0",
            head,
        )

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
        info = page_card_info(target, rel_dir, self.include_untitled)
        if not info:
            info = project_info(target, rel_dir)
        if not info:
            info = folder_info(target, rel_dir)
        info["path"] = rel_dir
        try:
            info["mtime"] = int(target.stat().st_mtime)
        except OSError:
            info["mtime"] = 0
        info["tree"] = folder_tree(target)

        embed = info["kind"] == "page" or (
            parse_qs(urlsplit(self.path).query).get("embed") == [ "1" ]
        )
        embed_class = ' class="rc-embed"' if embed else ""
        version = assets.asset_version()
        data = json.dumps(info, ensure_ascii=False).replace("</", "<\\/")
        doc = (
            "<!doctype html>\n"
            f'<html lang="en"{embed_class}>\n'
            "<head>\n"
            '<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"<title>{escape(info['title'])}</title>\n"
            f'<link rel="stylesheet" href="{assets.asset_url("card.css", version)}">\n'
            f"<script>window.__RIBBON_CARD_APP__ = {data};</script>\n"
            f'<script src="{assets.asset_url("card.js", version)}" defer></script>\n'
            "</head>\n"
            f"<body{embed_class}>\n"
            '<div id="ribbon-card"></div>\n'
            "</body>\n"
            "</html>\n"
        ).encode()
        payload = doc if embed else inject_html(doc, self.token, version)

        self._send_payload(
            payload,
            "text/html; charset=utf-8",
            "no-store, max-age=0",
            head,
        )

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
                            git_max_age=GIT_LIGHT_SECONDS,
                        ),
                        "token": self.token,
                        "write": self.write_enabled,
                        "state": public_state(load_state(self.root))
                        if self.token
                        else {},
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif name == "bar.html":
                # The new tab extension cannot load a remote script, so it
                # fetches this shell and adopts it with its local bar files.
                payload = assets.bar_shell_html()
                content_type = "text/html; charset=utf-8"
            elif name in STATIC_ASSETS:
                payload = assets.asset_bytes(name)
                content_type = (
                    "text/javascript; charset=utf-8"
                    if name.endswith(".js")
                    else "text/css; charset=utf-8"
                )
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
            elif name == "delete.json":
                error = self._delete_error()
                if error:
                    self._send_json({"ok": False, "error": error}, 403, head)
                    return
                requested = (parse_qs(urlsplit(self.path).query).get("dir") or [""])[0]
                try:
                    plan = self._deletion_plan(requested)
                except ValueError as error:
                    self._send_json({"ok": False, "error": str(error)}, 400, head)
                    return
                self._send_json({"ok": True, **plan}, head=head)
                return
            else:
                self.send_error(404, "Not found")
                return
        except OSError:
            self.send_error(500, "Ribbon asset missing")
            return

        if name in STATIC_ASSETS:
            # Only a URL carrying the current asset_version() may be pinned:
            # a rebuilt file gets a new ?v=, so the old URL never changes.
            # A saved page or hand-written reference has no query string and
            # must revalidate instead of staying frozen for a year.
            requested = (parse_qs(urlsplit(self.path).query).get("v") or [""])[0]
            if requested == assets.asset_version():
                cache_control = "public, max-age=31536000, immutable"
            else:
                cache_control = "no-cache"
            # Hash the source bytes, before gzip, so a revalidation can answer
            # 304 without paying for a compression it would throw away.
            etag = self._etag_for(payload)
            if self._etag_matches(etag):
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", cache_control)
                self.send_header("Vary", "Accept-Encoding")
                self.end_headers()
                return
            body, gzipped = self._response_body(payload)
            self._write_body(
                body,
                content_type,
                cache_control,
                head,
                etag=etag,
                gzipped=gzipped,
            )
            return
        body, gzipped = self._response_body(payload)
        self._write_body(
            body,
            content_type,
            "no-store, max-age=0",
            head,
            gzipped=gzipped,
        )


class RibbonHTTPServer(ThreadingHTTPServer):
    address_family = socket.AF_INET


class RibbonHTTPServerV6(RibbonHTTPServer):
    address_family = socket.AF_INET6


def url_host(host: str) -> str:
    if ":" in host and not host.startswith("["):
        return f"[{host}]"
    return host


