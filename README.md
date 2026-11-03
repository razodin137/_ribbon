# Ribbon

A small app switcher for the standalone HTML sites under
`/home/mrjohn/Work/tries`. There are two ways to run it:

1. **Static shell** — open `_ribbon/index.html`. No server, no page edits.
2. **Tiny server** — `_ribbon/ribbon.py` discovers apps automatically and
   injects the ribbon into every page.

Both show the same bar:

```
┌──────────────────────────────────────────────────────────────────────┐
│ ● 04 / 11  Beam Library          ‹ Back   › Next   ⤨ Random   ✕      │
└──────────────────────────────────────────────────────────────────────┘
```

Next/back/random move between apps, the bar hides on scroll, and `H` or the
`✕` button tucks it away.

## Static shell

Open:

```bash
xdg-open /home/mrjohn/Work/tries/2026-11-03-teaching/_ribbon/index.html
```

or serve it with anything static:

```bash
cd /home/mrjohn/Work/tries
python3 -m http.server 8000
# then open:
# http://localhost:8000/2026-11-03-teaching/_ribbon/
```

The shell puts the banner above an iframe. Apps keep their own assets, fonts,
CSS, and JS; the iframe loads each app's `index.html` directly.

### Add a folder

Drop it under `/home/mrjohn/Work/tries` with an `index.html` and a title:

```html
<title>My Thing</title>
```

Then refresh the list:

```bash
cd /home/mrjohn/Work/tries/2026-11-03-teaching
python3 _ribbon/ribbon.py --write-apps
```

That rewrites `_ribbon/apps.js`. You can also edit `apps.js` by hand; it is
just:

```js
window.__RIBBON_APPS__ = [
  { url: "../../my-thing/index.html", title: "My Thing" },
  { url: "../index.html", title: "The School with a Voice" }
];
```

URLs are relative to `_ribbon/`, which is why the teaching app uses
`../index.html` and the others use `../../`.

### `file://` caveat

Navigation, assets, and the hide button work when you open the shell directly.
Scroll-to-hide and the keyboard shortcuts inside the app need the shell served
over HTTP, because browsers make `file://` iframes cross-origin. Any static
server works; so does the ribbon server below.

## Tiny server

```bash
python3 /home/mrjohn/Work/tries/2026-11-03-teaching/_ribbon/ribbon.py
```

It scans the folder two levels above the script (`/home/mrjohn/Work/tries`),
serves it on `http://127.0.0.1:8765`, and prints both the first app and the
static shell URL. When it serves HTML, it adds one line before `</body>`:

```html
<script src="/__ribbon/ribbon.js" data-ribbon="1" defer></script>
```

Nothing on disk is changed. The injected ribbon lives inside the page, so it
works on any app page without an iframe.

Useful flags:

```bash
./ribbon.py --list                 # show what it found and exit
./ribbon.py --write-apps           # regenerate apps.js (including git status)
./ribbon.py --root ~/some/folder   # index a different folder
./ribbon.py --port 9000            # pick a port
./ribbon.py --no-open              # don't launch a browser
./ribbon.py --include-untitled     # also list pages without a <title>
```

## Controls

| Action | Button | Key |
| --- | --- | --- |
| Previous app | `‹ Back` | `[` |
| Next app | `› Next` | `]` |
| Random app | `⤨ Random` | `R` |
| Hide / show ribbon | `✕` | `H` |

Prev/next wrap around. Hidden state is remembered for the browser tab. When
hidden, a tiny `RIBBON` tab sits at the top right; click it or press `H` to
bring the bar back.

## Status LEDs

Two small LEDs sit beside the count:

| LED | Meaning |
| --- | --- |
| Left | Green: the app's folder is inside a Git repository. Dark: no repository. |
| Right | Green: clean and level with upstream. Amber: uncommitted changes, no upstream, no commits, or detached HEAD. Red: local commits not pushed. Dark: no repository. |

Hover either LED for the branch, upstream, ahead/behind counts, and the exact
reason for the color.

The static shell stores a snapshot in `apps.js` when you run `--write-apps`.
When the shell is served by `ribbon.py`, it refreshes the LEDs live from
`/__ribbon/git.json`. The injected ribbon also gets live status from the
manifest. Nothing is checked from `file://` beyond the snapshot, because the
browser cannot run Git.

## What gets listed

- Every `index.html` under the root, ordered by path (date-prefixed folders
  stay chronological).
- Only pages with a non-empty `<title>` by default. That keeps logins, admin
  screens, and other internals out without a config file. Use
  `--include-untitled` to include them.
- Hidden folders and the usual dependency/build directories are skipped
  (`node_modules`, `.venv`, `dist`, `build`, `out`, `target`, …).
- The shell itself is skipped via its `data-ribbon-shell` marker.
- Nested apps work: `beam/web/index.html` is its own entry.

When the server is running, new folders show up on reload with no rebuild.
For the static shell, run `--write-apps` after adding a folder.

## How the two modes coexist

- The shell page has `<html data-ribbon-shell>`. The server skips injecting
  into it, and the scanner skips listing it.
- `ribbon.js` returns early when `window.self !== window.top`, so an app loaded
  in the shell's iframe never grows a second ribbon when the server is also
  running.
- The server's bar overlays the top 40 px of the page. The shell reserves the
  40 px above the iframe instead, so app headers are never covered.

## Files

```
_ribbon/
  index.html  static shell: banner + iframe
  apps.js     generated list for the static shell
  ribbon.py   discovery, static-list generator, and optional server
  ribbon.js   injected ribbon UI (shadow DOM, self-contained)
  README.md
```
