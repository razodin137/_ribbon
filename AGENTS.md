# Ribbon — notes for agents

This file holds the implementation knowledge that does not belong in
`README.md`. `README.md` is for people who use Ribbon, and it is kept at a
fifth-grade reading level. Do not add internals there. Add them here.

## What this is

Ribbon is a small Python 3.11 program split across the modules beside this
file; the table below maps each one. It serves a folder of projects on a local
address, injects a top bar into each HTML page as it is served, renders
Markdown and folder cards, and can run a small set of Git actions. It uses only
the standard library. Nothing under the served root changes unless the user
presses a Git or delete button.

`ribbon.py` is a launcher: it imports `main` from `cli.py` and re-exports a
handful of names for the tests. No module imports it, so the dependency graph
stays acyclic. `git_actions.py` imports the Git read helpers from `git_repo.py`,
and `server.py` imports `run_git_action` only inside `do_POST()`.

## Commands

```bash
python3 ribbon.py                 # run the release copy
python3 ribbon.py --dev           # read JS/CSS from disk instead of the embed
python3 build.py                  # rewrite the embedded assets in assets.py
python3 build.py --check          # fail if the embed is stale
npm run check                     # lint + python gate + node --test + embed check
npm run lint
npm run check:python              # compile every module, then import the graph
npm test
```

There is no configured Python linter in this repo despite the `.ruff_cache`.
`npm run check:python` compiles every module and imports `ribbon` and
`git_actions`, so a syntax error or a new import cycle fails the check. Match
the surrounding Python style.

## Where things live

| Path | Role |
| --- | --- |
| `ribbon.py` | Launcher; re-exports a few names for the tests |
| `cli.py` | Arguments, banner, server startup |
| `config.py` | Shared constants: paths, suffixes, routes, limits, colours |
| `content.py` | Page metadata, HTML/Markdown choice, README helpers |
| `discover.py` | App discovery and card payloads, with a short cache |
| `scan.py` | Folder tree/stats and the gitignore engine |
| `git_repo.py` | Git read path: status, locks, detail, Pages checks |
| `git_actions.py` | Git write actions: init, commit, push, GitHub remote, Pages |
| `server.py` | `RibbonHandler`, the server classes, path guards |
| `inject.py` | Byte-level tag scanning and bar injection |
| `shell.py` | Boot script, bar markup/host style, page offset CSS |
| `assets.py` | Embedded browser assets and the `--dev` fallback |
| `state.py` | Per-root JSON state |
| `remove.py` | Delete planning and execution |
| `roots.py` | Root auto-detection and its safety guard |
| `markdown_render.py` | Pure Markdown → HTML rendering (`render_markdown`, `markdown_view_html`) |
| `ribbon.js` | Adopts the server-rendered bar shadow root and drives it |
| `bar.js` | Shared bar code: helpers and `createBar` |
| `card.js`, `card.css` | Contents card |
| `bar.css`, `markdown.css` | Bar and Markdown look |
| `build.py` | zlib + base64 embed of the six browser assets into `assets.py`; also copies `bar.js`/`ribbon.js` into `extension/` |
| `test/` | `node:test` files; the Python side is exercised through `python3 -c` bridges |
| `extension/` | Chrome MV3 new-tab extension: `manifest.json`, `newtab.html`, `newtab.css`, `newtab.js`, `home.js`, plus the generated `bar.js` and `ribbon.js` copies |
| `README.md` | User-facing doc, fifth-grade reading level |
| `AGENTS.md` | This file |

The six embedded assets are `bar.css`, `bar.js`, `card.css`, `card.js`,
`markdown.css`, and `ribbon.js` (`ASSETS` in `build.py`).

## New tab extension

`extension/` is a Manifest V3 extension loaded with **Load unpacked**. It
overrides the new tab page with `newtab.html` and needs no icons. The page is a
plain extension page with `host_permissions` for `http://127.0.0.1/*`,
`http://localhost/*`, and `http://[::1]/*`. Those patterns ignore the port, and
host permissions are what let the page fetch Ribbon's JSON cross-origin. The
only `chrome.*` call is `chrome.runtime.getURL` for the home link; keep the page
otherwise API-free unless a feature needs a privileged API.

`newtab.js` probes `8765` through `8784`, the same default window `cli.py`
tries, and accepts a response only when its JSON has an `apps` array. Probe all
20 ports in parallel, then move to the next host, so a new tab does not wait a
timeout per closed port. Keep the range constants in sync with `cli.py`.

`newtab.js` stores the last base URL and its manifest in `localStorage` under
`ribbon.newtab`. A new tab paints that snapshot right away, then asks the cached
base for a fresh manifest. The port scan above runs only when that request
fails, so a live Ribbon never costs a scan and a new tab never waits on ports
that are closed. `normalizeBase()` accepts only the three hosts and
`http`/`https`, so a hand-edited cache cannot point the page elsewhere.
`localStorage` is synchronous, which lets the snapshot land without waiting for
storage.

Ribbon's manifest is `/__ribbon/manifest.json`. Each app carries `title`,
`type`, `color`, `description`, `url`, and Git state. Cards link to
`base + app.url` with no `target`, so a click replaces the new tab as asked.
When no probe succeeds, the page names the problem and shows
`python3 ribbon.py` as the start command.

The shelf sorts in `compareApps()`, and the choice lives in `localStorage`
under `ribbon.newtab.sort` (`status`, `type`, or `name`; `status` is the
default). `statusWork()` ranks a repo by `git.state` through `STATE_WORK`, so
the order agrees with the bar's `gitWorkRank()`: most Git work first, and a
`git.dirty` flag lifts a repo even when its state word says something else.
`type` groups by the same `type` label the card shows, and every mode breaks
ties by name. A new mode re-renders from the snapshot in `shown` instead of
refetching.

`extension/newtab.css` is in the `npm run lint` Stylelint list.

Each card renders the same three Git lights as the bar. `gitLights()`,
`repoTip()`, `changesTip()`, and `remoteTip()` in `newtab.js` mirror the ones
in `bar.js` on purpose: the bar loads asynchronously (and not at all when
Ribbon is down), so cards cannot wait for `window.__RIBBON_BAR__`.
`test/grid-lights.test.js` runs both implementations over the same cases and
fails when they drift. The dots carry their tip on `title`, and the card's
`aria-label` stays the app name and type.

Each card is wrapped in `.card-shell` with the link in `.card` and a separate
`.card-overview` button, because a button inside an anchor is invalid. The
button opens `<dialog id="overview">`, whose iframe loads
`/__ribbon/card/<path>/?embed=1`. The `embed=1` flag keeps the bar out of the
iframe and adds `class="rc-embed"` to the card document, which makes its desk
transparent instead of the warm cream page. `card.js` posts `{type: "ribbon-card-size"}` to the
parent, and both `newtab.js` and `ribbon.js` set the iframe height from it, so
the card is shaped to its own content. Both overviews sit on a warm cream
scrim that is translucent and blurred, so the page or the homepage shows
through around the card. The ribbon steps out of the way while an overview is
open: `ribbon.js` sets `data-card-open` on the bar host, and `newtab.css` fades
the host when its dialog is open, so the black strip never sits above the card.
The card route serves every kind, including Markdown, so every grid item has an
overview. `test/grid-overview.test.js` pins the URL encoding, the dialog, the
size message, the scrim, and the ribbon stand-down; `hidden-paths.test.js`
checks a Markdown folder's card returns 200.

### The same bar on the new tab

The new tab draws no ribbon of its own. `newtab.js` finds Ribbon, fetches
`/__ribbon/bar.html` (the same `bar_shell_html` a served page gets), inserts the
shell, then loads the extension's copies of `bar.js` and `ribbon.js`. MV3 forbids
remote script, so those two are local copies kept in step by `python3 build.py`;
the shell and its CSS still come from the server, so the bar markup has one
source. The page reserves the bar's height with `html::before` in `newtab.css`.

`ribbon.js` reads three attributes for this case, set by `newtab.js` on the
local `ribbon.js` tag: `data-ribbon-base` (the server origin, so the manifest
and app links resolve there rather than at `chrome-extension://`),
`data-ribbon-title="home"` (the name the dropdown shows when no app matches),
and `data-ribbon-home` (the bar's home button). On a served page none of those
are set, and `scriptBase` still comes from the script URL.

The home control is a toolbar button beside the title star, not a dropdown
row: `<span class="home-wrap" data-home hidden>` with an anchor
`class="title-home" data-home-link` in `BAR_MARKUP`. The server cannot know
the extension's address, so `extension/home.js` runs as a content script on the
three hosts, sets the anchor's `href` from
`globalThis.chrome.runtime.getURL("newtab.html")`, and clears `hidden`. It is
static in the shell, so re-rendering the app lists cannot wipe it. The button
carries no Git lights, star, or contents control, as asked.

Two manifest entries carry that: `content_scripts` for `home.js`, and a
`web_accessible_resources` entry exposing `newtab.html` to the same matches, so
a project page may navigate to the grid. `home.js` is not copied by `build.py`.

When Ribbon is not running the page has no base and shows no bar; the notice
still names the start command. `test/home-button.test.js` pins the title home
button, the content script, the manifest pair, and the bar install path.

## Build and embed contract

`assets.py` carries the browser assets between these markers:

```
# --- embedded assets: generated by build.py; do not edit ---
# --- end embedded assets ---
```

`asset_bytes()` reads the embedded copy unless `DEV_ASSETS` is true (`--dev`).
`asset_stamp()` and `asset_version()` follow the same switch, so a `--dev`
change also changes the injected `?v=`.

After editing any of the six assets, run `python3 build.py`. `npm run check`
ends with `build.py --check`, which fails if the embed is stale. Do not edit the
generated block by hand.

The extension cannot load `bar.js` or `ribbon.js` from the server, so `build.py`
also copies those two into `extension/`. `--check` fails when either copy drifts
from its source. Edit the root file, never the copy. The `extension/newtab.css`
and `newtab.js` files are hand-written, not generated.

`build.py` refuses any CSS asset that contains `</style` (case-insensitive),
because `bar_shell_html()` pastes the CSS into a `<style>` tag.

## Request flow

`RibbonHandler._handle()` in `server.py`:

1. `/__ribbon/card/...` → `_serve_card()`
2. `/__ribbon/...` → `_serve_asset()` (`manifest.json`, `bar.html`, `git.json`,
   `delete.json`, or a static asset)
3. `/` with no root `index.html` → redirect to the first app
4. A directory → `index.html`, else `choose_html()`, else the chosen Markdown
   file, else a contents card
5. `.html` / `.htm` → `_serve_html()` (read the file, then inject)
6. `.md` family → `_serve_markdown()` (build a page, then inject)
7. Anything else → `SimpleHTTPRequestHandler`

Generated pages (`_serve_markdown`, `_serve_card`) are built by Ribbon and then
passed through `inject_html()` like normal HTML. `_serve_card()` skips injection
when the card is the page itself (`embed`), because the card already sits in the
bar's document.

## Connection handling

`RibbonHandler` talks HTTP/1.1, so browsers keep connections alive. Its
`timeout` is set from `HANDLER_TIMEOUT` (60 s); `StreamRequestHandler.setup()`
applies that to the connection socket. An idle keep-alive connection closes
after 60 s instead of pinning a `ThreadingHTTPServer` thread. The same limit
also covers a stalled read or write on an active connection, so do not assume a
request handler has unlimited socket time.

## The bar has two halves

- **Shell**: `BAR_MARKUP` and `bar_shell_html()` in `shell.py`. It is static
  HTML rendered before any script runs, inside a declarative shadow root.
  `PAGE_OFFSET_CSS` reserves the bar's height on `<html>` before first paint,
  without adding an in-flow child to `<body>`.
- **Behavior**: `bar.js`, adopted by `ribbon.js`.

New bar UI means adding markup to `BAR_MARKUP` and behavior to `bar.js`, not to
`ribbon.js`. `test/bar-duplication.test.js` fails if:

- a function defined in `bar.js` is defined again in `ribbon.js`
- a static `shadow.querySelector*` selector in `ribbon.js` does not exist in
  `BAR_MARKUP`

## Page offset

`PAGE_OFFSET_CSS` reserves `BAR_HEIGHT` with an `html::before` box, so the
reservation exists at first paint without being a child of `<body>`. That
matters for a page whose body is a row-flex or grid container: an in-flow body
child would sit beside the content or take a grid cell. The box is hidden with
`html:has([data-ribbon-host][data-ribbon-hidden])::before`, so hiding the bar by
hand removes it. `BAR_HEIGHT` travels to `ribbon.js` on the host's
`data-ribbon-height`, so scroll compensation cannot drift from the server.

## Modals and focus

`git-dialog` and `delete-dialog` are `aria-modal="true"`, so Tab must not leave
them. `bar.trapTab(event, overlay)` in `bar.js` wraps Tab at either end and
pulls focus back if it escaped. Both overlays focus a control as soon as they
open, which is what lets the overlay's `keydown` listener see the key.
`test/focus-trap.test.js` pins the wrap, the recapture, and the hidden-control
skip. A new modal needs the same trap call and an initial focus.

## Boot script and storage contract

`BOOT_SCRIPT` in `shell.py` runs before `ribbon.js` and reads the same
`sessionStorage` keys. It sets `data-ribbon-booting` before the hidden or
scrolled attribute, so the bar's transition is off while the initial state
lands. Two frames later it removes `data-ribbon-booting` and normal transitions
resume. `test/storage-contract.test.js` pins the key names and values against
`ribbon.js`. Change both sides together.

`test/page-offset.test.js` pins the pre-script page offset and the hidden state.
`test/boot-transition.test.js` pins the transition-free boot and the two-frame
release. `test/view-transition.test.js` pins the cross-document transition setup
and the reduced-motion opt-out.

## Injection guard — findings

`inject_html()` starts with:

```python
if b"data-ribbon-host" in data or b"/__ribbon/ribbon.js" in data:
    return data
```

This is an idempotency guard, not a security check. It stops Ribbon from adding
a second bar to a document that already has one.

Facts that matter:

- It is a raw substring test over the whole document, including visible body
  text. It does not parse tags.
- Every real injection contains both strings (`<div data-ribbon-host ...>` and
  `src="/__ribbon/ribbon.js?v=..."`), so the guard cannot miss Ribbon's own
  output.
- The earlier test was the broader `data-ribbon`, which collides with ordinary
  pages. Commit `2fe83dc` narrowed it to `data-ribbon-host`.
- A page that only *mentions* either string (docs, a code sample, a saved copy)
  is served unchanged and loses the bar. A saved copy also keeps its old asset
  URL.
- Only HTML files under the served root can trip it. No file in this repo does.
- The false-positive direction is cosmetic and recoverable: the bar is absent,
  the page is intact.

Why it stays: the match is narrow, every injection is caught, and the failure
mode is a missing bar on an unusual page. A structural matcher (`<tag ...
data-ribbon-host`) would add regex surface without a clear gain. If the guard is
ever changed, keep both directions covered and add a test that (a) a page with
the real markup is not injected twice, and (b) ordinary page text does not block
injection.

### Tag scanning

Injection uses `iter_html_tags()`, a byte scanner that skips comments, CDATA,
declarations, processing instructions, and the raw text of `RAW_TEXT_TAGS`.
`html_injection_points()` returns the first real `<body>`, the last real
`</head>`, and the last real `</body>`. The stylesheet is inserted before those
body offsets are used, so both body offsets shift by `len(style)`. Do not
replace this with a regex over raw bytes: a `<body>` in a documented example
comment or a JavaScript string would move the bar, and a `</head>` in a script
would split it. `test/injection.test.js` pins comments, script strings, fake
head and body closes, and a quoted `>` inside a body attribute.

## Cross-document view transitions — scope

`VIEW_TRANSITION_CSS` is injected into every page Ribbon serves, and it starts
with `@view-transition { navigation: auto; }`. That opt-in is document-wide.
The browser cannot tell a bar-driven project switch from a link inside a
project, so every same-origin navigation between injected pages gets a
cross-document transition. Internal links cross-fade too, and the project's own
`view-transition-name` elements join the same transition tree as `ribbon-bar`.

This is deliberate: the bar's continuity depends on the opt-in, and there is no
per-navigation CSS hook. Things to keep in mind:

- Ribbon's style is inserted just before `</head>`, so it comes after the
  page's own head styles. An earlier `@view-transition { navigation: none; }`
  in the page loses to Ribbon's `auto`; only `prefers-reduced-motion` opts out.
- A project must not use `view-transition-name: ribbon-bar`. `BAR_HOST_STYLE`
  claims that name with `!important`, and a duplicate name aborts the
  transition.
- `::view-transition-old/new(ribbon-bar)` are `animation: none`, so the bar
  snaps into place while only the page content cross-fades.

Limiting the transition to bar clicks would need a cross-navigation marker plus
`pageswap`/`skipTransition()`, which is fragile for a cosmetic effect. If the
scope changes, update `test/view-transition.test.js` and `README.md` together.

## Security model

- Binds `127.0.0.1` by default (`--host`).
- A token is generated only for local hosts (`secrets.token_urlsafe(24)`) and
  written into the page as `data-ribbon-token`.
- Every POST (`/__ribbon/git`, `/__ribbon/signal`, `/__ribbon/delete`) passes
  `_post_guard()`: `Origin` allowlist, JSON `Content-Type`, and a constant-time
  `X-Ribbon-Token` compare.
- `write_enabled` is true only on a local host and without `--no-git-actions`.
  Signals and deletes need the token as well.
- `--host` on a non-local address is read-only but unauthenticated. Anyone who
  can reach the port can read every page under the root and both JSON endpoints
  (`manifest.json`, `git.json`). There is no read token, by design: a browser
  navigation cannot carry one, and the bar fetches those endpoints on every
  page. `main()` therefore prints a warning before the banner whenever the
  bind address is not `127.0.0.1`, `localhost`, or `::1`. Do not remove that
  warning without adding real read protection and documenting it.
- Deletes are limited to direct children of the root; `delete_plan()` refuses
  the app itself, symlinks, and paths outside the root.
- Git actions take a per-repo non-blocking lock and return `409` if one is
  already running.
- GET never serves a dot entry. `hidden_path()` runs in `_handle()` before
  `translate_path()`, so `.git`, `.env`, and any folder inside them return 404,
  including the card route and a percent-encoded `%2e`. This is why the check
  decodes first: `translate_path()` decodes too, so an undecoded check would
  miss `/%2egit/config`. `test/hidden-paths.test.js` pins the cases against a
  real server.
- GET is confined to the root. `contained_target()` resolves the target and
  refuses it when a symlink leads outside, so `/link.txt` pointing at
  `/etc/passwd` is a 404. Symlinks that stay inside the root still work. This
  matches what `delete_plan()` already did for writes.
- The auto-detected root is guarded. `default_root()` may return `None`, and
  `is_safe_default_root()` refuses the filesystem root, `Path.home()`, any
  top-level folder, and anything inside `SYSTEM_ROOTS` (`/usr`, `/etc`, `/opt`,
  `/var`, and the macOS system folders). Without a safe guess, `main()` stops
  and asks for `--root`. An explicit `--root` is not checked: the user chose
  it. This matters because the whole root is served as static files, so a
  guess that climbed to `/` or `~` would expose the disk. `test/default-root.test.js`
  pins the four climb cases (`~`, `~/bin`, `/opt/ribbon`, `/usr/local/bin`), the
  two layouts that should still resolve (a single container child, projects
  beside the app), and the guard itself.

### Trust boundary — every served project is trusted

All served pages share one origin with the bar and its action API. That is
deliberate: the bar is injected into each page and must run as that page, so
there is no origin boundary between a project and the bar.

Consequences:

- Any script in any served page can read the token from `data-ribbon-token` on
  the `ribbon.js` tag or from `/__ribbon/manifest.json`, then POST to
  `/__ribbon/delete` or `/__ribbon/git` with the right headers.
- The `Origin` allowlist and the token are CSRF defenses. They stop another
  website from driving Ribbon. They do not stop a project Ribbon serves,
  because that project is already same-origin and can read the token.
- Therefore every project under the root is trusted. Ribbon is not a sandbox.
  `--no-git-actions` is the only mode that removes write endpoints, and it is
  the right choice when the root holds code you did not write.

Moving the actions to a different origin would only help if the credential
stayed out of the page origin. The bar's UI runs in the page, so it cannot hold
a secret that page scripts cannot read. A real fix needs the bar itself on the
action origin (an iframe or a second window), not just a second port: a second
port with CORS open to the page origin would leave the same exposure. Until
then, the boundary is documented rather than enforced.

## State

`state_path(root)` is
`$XDG_STATE_HOME/ribbon/state-<sha1(root)[:12]>.json`, falling back to
`~/.local/state/...`. `STATE_LOCK` serializes reads and writes. State is
read-only when there is no token (non-local host).

`save_state()` writes a pid-and-thread-named temp file, replaces it in one step,
and unlinks the temp file on any failure. The temp file is opened `0600`, and
`os.replace` keeps that mode, so the final state file is private even under a
permissive umask.

## Assets and caching

- Static assets live at `/__ribbon/<name>`. They are sent with
  `Cache-Control: public, max-age=31536000, immutable` only when the request's
  `?v=` equals `asset_version()`; without a matching version they are sent with
  `no-cache` and revalidated by ETag, so a saved page or manual reference picks
  up a rebuilt asset instead of staying pinned for a year.
- `asset_version()` hashes the sorted assets and caches on `asset_stamp()`.
- Dynamic responses use `no-store, max-age=0`.
- Responses gzip when the client accepts it and the body is at least
  `GZIP_MIN_BYTES` (512); a smaller body is sent as-is because the header costs
  more than it saves. `_write_body()` always sets `Vary: Accept-Encoding`.
- `git_status()` caches for `GIT_CACHE_SECONDS` (2s); `GIT_LIGHT_SECONDS` is
  used for the lighter list view.
- `GIT_LOCKS` and `GIT_STATUS_LOCKS` are `_LockPool`s. They hand out a reference
  counted lock and forget the key when the last caller releases it or fails a
  non-blocking acquire, so a long-lived process does not accumulate one lock per
  path ever seen.
- `discover()` creates one `ThreadPoolExecutor` per manifest request, with up
  to `GIT_STATUS_WORKERS` (8) threads. Concurrent manifests multiply threads,
  not git work: `git_status()` holds `_git_status_lock(key)` across
  `read_git_status()`, so at most one `git status` runs per repo however many
  requests arrive. A shared pool would not help much, since the extra threads
  would be parked on the same locks.

## Tests

| File | Pins |
| --- | --- |
| `bar-pure.test.js` | The pure helpers exposed on `window.__RIBBON_BAR__` |
| `bar-duplication.test.js` | No `bar.js` function is redefined in `ribbon.js`; every static selector exists in `BAR_MARKUP`; the markup parser can read the shell |
| `storage-contract.test.js` | `BOOT_SCRIPT` keys and values match `ribbon.js` |
| `view-transition.test.js` | View-transition opt-in, named bar, reduced motion |
| `page-offset.test.js` | Pre-script root-element offset, hidden-state coupling, no post-load body padding |
| `default-root.test.js` | The auto-detected root never climbs to `/`, a home folder, or a system folder; the wrapper and sibling layouts still resolve |
| `hidden-paths.test.js` | A live server refuses dot entries, `%2e`-encoded ones, card listings, and symlinks out of the root, on GET and HEAD; normal pages, in-root symlinks, and a Markdown project's card still serve |
| `injection.test.js` | `inject_html()` ignores `<body>` in comments and script strings, only trusts a real `</head>`/`</body>`, respects quoted `>` in an attribute, and does not shift offsets after inserting the stylesheet |
| `home-button.test.js` | The bar's title carries a hidden home button, `home.js` points it at the new tab page, the manifest declares the content script and the web-accessible page, the new tab installs the server bar, and `build.py` keeps its bar copies in step |
| `grid-lights.test.js` | The grid card's `gitLights()` matches `bar.js` for every state, and a card renders all three dots |
| `grid-overview.test.js` | The overview URL is encoded and embedded, each card has the overview button, the dialog is card-sized, the card reports its height, both overviews use the blurred cream scrim, and the ribbon steps aside while one is open |

## Style

37signals house style is adopted: `@37signals/eslint-config` and
`@37signals/stylelint-config-scss` in `package.json` and the configs. Keep JS in
double quotes, no semicolons, 2-space indent, no trailing commas, spaces inside
array brackets, and no space before call parentheses. Prefer `const`; never
`var`.

`README.md` is written for people at about a fifth-grade reading level. Keep
user-visible behavior there, in plain words. Put implementation detail,
history, and invariants here.

## Editing checklist

1. Change the canonical file: `bar.js`, `ribbon.js`, a CSS file, or the
   Python module that owns the behavior.
2. If a browser asset changed, run `python3 build.py`.
3. Run `npm run check`.
4. If user-visible behavior changed, update `README.md` in plain language.
5. If an invariant or internal decision changed, update this file.
