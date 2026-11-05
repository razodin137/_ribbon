# Bar extraction — outline for one agent at a time

Status: **plan**, written against commit `ec66416` (bar.css extracted).
Read `BRIEF.md` first for the product picture. This file is only about
getting `ribbon.js` and `shell.js` onto one shared `bar.js`.

Each packet below is small enough to hand to a separate agent, in order.
A packet is done when it is committed, `npm run lint` is clean, and both
entry points still work.

The house style is the repo's own config: double quotes, no semicolons,
2-space indent, spaces inside array brackets (`[ like, this ]`). Never
reformat unrelated code.

---

## The target

`bar.js` is a classic script, not an ES module. It loads before either host:

```html
<script src="bar.js"></script>
<script src="apps.js"></script>
<script src="card.js"></script>
<script src="shell.js"></script>
```

It exposes one global:

```js
window.__RIBBON_BAR__
```

Two layers, in this order:

1. **Pure exports** — no DOM, no state. These can be unit-tested in Node.
2. **`createBar(options)`** — owns the shared bar state and the bar's own
   DOM events. Returns an API the host calls.

The hosts keep only host concerns:

| Host | Keeps |
| --- | --- |
| `ribbon.js` | manifest, shadow markup, signals/channels/deck/drift, contents card, delete panel, hide/scroll/keyboard, navigation by `location.assign`, token from script/meta |
| `shell.js` | `apps.js`, iframe navigation, hash, hide/scroll/keyboard, random, token from `/__ribbon/manifest.json` |

Everything that renders the bar's menu, LEDs, tooltips, git panel, or
favorites moves into `bar.js`.

### `createBar(options)` contract

```js
createBar({
  root,          // Document or ShadowRoot. All queries and creates use it.
  refs,          // element map, see below
  apps,          // initial array (live copy owned by the factory)
  index,         // initial index
  signals,       // shared object, server only; default {}
  canDelete,     // bool, server only; default false
  channel,       // { id, matches(app, id), label(id) } — shell passes all/true
  getToken,      // () => Promise<string>; server resolves immediately
  onSelect,      // (app, index) => void — host navigates
  onDelete,      // (app) => void — server opens the delete panel
  onSignal,      // (name, value) => void — server keep/park
  beforeMenu,    // () => void — server renders channel chips
})
```

Returns:

```js
{
  setApps(next), setIndex(next), setCanDelete(next), setChannel(id), setToken(t),
  currentApp(), appKey(app), isFavorite(app),
  updateCurrentStar(), updateCurrentMeta(),
  renderMenu(query), openMenu(), closeMenu(returnFocus), toggleMenu(),
  toggleFavorite(app, focusStar),
  setGit(git), gitLights(git), gitWorkRank(app),
  openGitPanel(focus), closeGitPanel(), submitGitAction()
}
```

`refs` is the existing element set, unchanged in shape:

```
menuEl, menuCurrentTitle, menuCurrentMeta, menuChannels,
keepButton, parkButton, starButtons, searchInput,
menuFavSection, menuAllSection, menuFavList, menuAllList,
menuAllHeading, menuEmpty, titleButton,
ledButtons, ledsWrap, ledTip, ledRepo, ledChanges, ledRemote,
tipRepoDot, tipChangesDot, tipRemoteDot,
tipRepoText, tipChangesText, tipRemoteText,
gitOverlay, gitTitle, gitSummary, gitFiles, gitWarnings,
gitMessageField, gitMessage, gitNameField, gitName,
gitVisibilityField, gitVisibilityInputs, gitDescriptionField,
gitDescription, gitReadmeField, gitReadme, gitPagesField, gitPages,
gitIgnoreField, gitIgnore, gitNote, gitOutput, gitStatus,
gitCancel, gitPrimary, gitClose
```

`root.ownerDocument || root` is the document used for `createElement`.
For a `ShadowRoot`, that is the page document; for `Document`, it is the
document itself. Query with `root.querySelector`, never bare `document`,
except for `document.activeElement` and `document.title`.

The bar owns these events and must not leave copies in the hosts:

- title button click, both star buttons, search input/keys, menu clicks
- LED click/pointer/focus/blur, tip outside-pointerdown
- git cancel/close/primary/overlay

The host owns:

- page/iframe navigation, keyboard shortcuts, hide/show and scroll
- delete overlay, contents card, signals/channels/drift
- `pointerdown` that closes the menu when the outside click is outside the
  bar; the host can call `bar.closeMenu(false)` from its existing handler

---

## Reconciliation of the 19 diverged functions

These are the 41 same-name functions minus the 22 byte-identical ones:
`41 - 22 = 19`. Line refs are from `ec66416`. "Shell" is `shell.js`;
"ribbon" is `ribbon.js`.

| # | Function | What differs | Verdict |
| --- | --- | --- | --- |
| 1 | `appKey` | shell drops `app.path` | **shell bug** — path-only apps collide |
| 2 | `closeGitPanel` | `catch (error)` vs `catch (_)` | **cosmetic** |
| 3 | `defaultRepoName` | shell handles URL-only apps and strips `.html`; ribbon handles `path` | **both** — shell missing URL/extension handling; ribbon missing `path` |
| 4 | `favoriteRow` | shell has no keep/park flag, no `path` line, no delete button | **missing feature** (signals, delete) + path bug |
| 5 | `matchesQuery` | shell drops `app.path` from the haystack | **shell bug** — path-only apps unsearchable |
| 6 | `onScroll` | `pending` vs `pendingScroll`; different event source | **host difference** (window vs iframe) |
| 7 | `openGitPanel` | shell awaits `gitSession` for the token and guards a closed panel; ribbon fetches immediately | **host difference** (token source) + shell's guard is a ribbon bug fix |
| 8 | `openMenu` | shell omits `renderChannels()` and `updateCurrentMeta()` | **missing feature** — channels and signals meta |
| 9 | `pad` | ribbon takes `total`; shell closes over `apps.length` | **host coupling**, not a bug — shared version takes `total` |
| 10 | `processScroll` | ribbon reads the page; shell reads the iframe and has `suppressScrollUntil` | **host difference** (scroll surface) |
| 11 | `readFavorites` | `catch (error)` vs `catch (_)` | **cosmetic** |
| 12 | `readHidden` | `catch (error)` vs `catch (_)` | **cosmetic** |
| 13 | `reloadApp` | ribbon reloads the page; shell reloads the iframe/app surface | **host difference** |
| 14 | `renderGitPanel` | shell has older Pages handling, narrower warning filter, no `pages.problem` / `case_mismatch`, no block on a Pages problem | **missing feature + bug** in shell |
| 15 | `renderMenu` | shell has no channel filter, no channel-aware empty/heading | **missing feature** — channels |
| 16 | `saveFavorites` | `catch (error)` vs `catch (_)` | **cosmetic** |
| 17 | `setManual` | ribbon also calls `setTopOffset`; shell calls `applyHidden` | **host difference** — how the host hides its own surface |
| 18 | `submitGitAction` | shell queries `document` instead of the shadow root; uses dir/url; has a stale-app guard | **host difference** (root) + path bug + shell's stale guard is a ribbon bug fix |
| 19 | `toggleHidden` | `applyState()` vs `applyHidden()` | **host difference** |

### Decisions, in one line each

- Adopt ribbon's `appKey`, `matchesQuery`, `favoriteRow`, `renderMenu`,
  `renderGitPanel`, `openMenu` superset.
- Adopt shell's `.html?`/trailing-slash handling in `defaultRepoName`, and
  its stale guards in `openGitPanel` / `submitGitAction`.
- Standardise the four cosmetic catches on `_`.
- Keep `onScroll`, `processScroll`, `reloadApp`, `setManual`, `toggleHidden`
  in the hosts. They are about the surface the bar sits on, not the bar.
- `pad` becomes `pad(number, total)`.
- `favoriteRow` becomes `favoriteRow(root, app, appIndex)`; `menuLights`
  becomes `menuLights(root, git)`; both use `root.ownerDocument` for
  `createElement`.

---

## The 22 byte-identical functions

Moved first, bodies unchanged after dedent. They are identical in both
files today (whitespace aside):

```
isFavorite        currentApp        updateCurrentStar
gitLights         gitWorkRank       menuLights
closeMenu         toggleMenu        toggleFavorite
decideGitAction   summaryRow        renderGitUnavailable
setGitBusy        showGitError      setGit
setLedLabel       repoTip           changesTip
remoteTip         openTip           closeTip
closeTipIfUnpinned
```

They become methods inside `createBar` so their free variables resolve to
the factory's state and refs. The only permitted edits in the move are:

- `document.createElement` → `root.ownerDocument.createElement`
- `document.activeElement` stays (focus is document-wide)
- `shadow.querySelector` → `root.querySelector`
- host-specific calls (`setApp`, `location.assign`, `frame`) become
  `options.onSelect` / `options.onReload`
- `app.path || app.dir` becomes `app.path || app.dir || app.url`

---

## Packet 0 — this document

No code. Commit `BAR-EXTRACTION.md`. This is the answer to "write the
answer down".

---

## Packet 1 — pure helpers

**Goal:** `bar.js` exists, is served, and both hosts call the pure layer.
No DOM moves yet.

**Create `bar.js`:** IIFE, `"use strict"`, `window.__RIBBON_BAR__ = { ... }`.
Move, with no behaviour change:

```
appKey(app)
pad(number, total)
matchesQuery(app, query)
escapeAttribute(value)          // from shell.js
defaultRepoName(app)            // change from currentApp() to app
gitLights(git)
gitWorkRank(app)
decideGitAction(detail, focus)
repoTip(git)
changesTip(git, dirty, count)
remoteTip(git, hasRemote)
isParked(entry)
```

Also move the `LED_WORK` constant.

**Wire:**

- `ribbon.py`: serve `/__ribbon/bar.js` next to `bar.css`.
- `index.html`: `<script src="bar.js"></script>` before `apps.js`.
- `ribbon.js` / `shell.js`: delete their copies and call
  `window.__RIBBON_BAR__.…`. Keep a local `const bar = window.__RIBBON_BAR__`
  at the top of each IIFE.
- `pad` call sites: pass `apps.length` explicitly.
- `defaultRepoName` call sites: pass `currentApp()`.
- `matchesQuery`, `appKey`: call sites only.

**Acceptance**

- `npm run lint` clean.
- `window.__RIBBON_BAR__.gitLights({ repo: true, state: "clean" })` returns
  the same object as before.
- Both screenshots look unchanged.
- No function with these names remains in `ribbon.js` or `shell.js`.

Commit: `add bar.js and move the pure helpers`.

---

## Packet 2 — menu, favorites, rows

**Depends on:** Packet 1.

**Goal:** `createBar` exists and owns the menu and favorite rows.

**Move into `createBar`:**

```
isFavorite, currentApp, updateCurrentStar
closeMenu, toggleMenu, toggleFavorite
menuLights(root, git)
favoriteRow(root, app, appIndex)
renderMenu(query)
openMenu()
```

`favoriteRow` keeps ribbon's keep/park flag, path line, and delete button.
The shell passes `signals = {}` and `canDelete = false`, so it renders the
plain row without changing markup.

`renderMenu` keeps ribbon's channel filter. The shell passes
`channel = { id: "all", matches: () => true, label: () => "All apps" }`.

`openMenu` calls `beforeMenu()` when provided (ribbon renders chips) and
calls `updateCurrentMeta()` only when the refs exist.

**Wire:**

- `createBar` wires title, stars, search, menu clicks.
- Menu row click → `options.onSelect(app, index)`.
- Delete click → `options.onDelete(app)`.
- `toggleFavorite` keeps focus after re-render.
- Hosts remove their copies and their duplicate listeners.
- Hosts call `bar.setApps` / `bar.setIndex` when their navigation changes.
- Ribbon's `applyApps` calls `bar.setApps(apps)`, `bar.setIndex(index)`,
  `bar.updateCurrentStar()`, `bar.updateCurrentMeta()`, and
  `bar.renderMenu(...)` when the menu is open.
- Shell's `setApp` calls `bar.setIndex(index)`, `bar.updateCurrentStar()`,
  `bar.closeMenu(false)`, `bar.closeTip()`.

**Acceptance**

- Menu opens/closes from the title, Escape, and an outside click.
- Search filters; Enter/Down focus the first row.
- Star toggles from the title and from a row; the star survives a reload.
- Server menu shows the keep/park flag and the delete button; shell does not.
- Channels still filter the server menu.
- Lint + screenshots.

Commit: `move the menu and favorite rows into bar.js`.

---

## Packet 3 — LEDs, tooltips, git sync

**Depends on:** Packet 2.

**Move into `createBar`:**

```
setLedLabel, setGit
repoTip, changesTip, remoteTip   // already pure; use from the pure layer
gitLights, gitWorkRank           // already pure
openTip, closeTip, closeTipIfUnpinned
```

`createBar` owns `tipPinned`, `tipTimer`, `hoverCapable`, and the LED/tip
events (click, pointerenter/leave, focus/blur, outside pointerdown).

**Wire:**

- Hosts call `bar.setGit(app.git)` wherever they used to call `setGit`.
- Shell's `refreshGit` calls `bar.setGit(data)`.
- Remove the hosts' LED/tip listeners and their state.
- Server `setGit` must still read `git.remote_url` for the Pages hint.

**Acceptance**

- LEDs change on a page with a repo, with changes, and with no remote.
- Hover/focus shows the tooltip; clicking an LED opens the git panel.
- Lint + screenshots.

Commit: `move LEDs and git sync into bar.js`.

---

## Packet 4 — git panel

**Depends on:** Packet 3.

**Move into `createBar`:**

```
decideGitAction, summaryRow, renderGitUnavailable, renderGitPanel
openGitPanel, closeGitPanel, setGitBusy, showGitError, submitGitAction
defaultRepoName   // pure, use from the pure layer
```

Use ribbon's `renderGitPanel` (Pages problem, case mismatch, gitignore
filter, primary blocking). Use shell's stale guards:

- after the token/fetch resolves, `if (gitOverlay.hidden) return`
- after a write resolves, update `app.git` only if `app === currentApp()`

`openGitPanel` gets the token from `options.getToken()`; the server returns
`ribbonToken`, the shell returns `gitSession.then((s) => s.token)`.
`submitGitAction` queries `root.querySelector('input[name="git-visibility"]:checked')`.

`closeGitPanel` standardises the catch on `_`.

**Wire:**

- Remove both hosts' git-panel functions and listeners.
- Hosts call `bar.openGitPanel(focus)` from the LED click (now inside bar).
- The delete panel and card overlay remain in `ribbon.js`.

**Acceptance**

- Server: click an LED, panel opens, shows status, Cancel/Escape closes,
  focus returns to the LED.
- Server: a repo with an `index.html` case mismatch shows the Pages note
  and a disabled primary.
- Shell over `file://`: panel says to start the server.
- Shell over HTTP: token is fetched before the panel renders.
- Lint + screenshots.

Commit: `move the git panel into bar.js`.

---

## Packet 5 — server-only meta, channels, delete hooks

**Depends on:** Packet 4.

**Move into `createBar`:**

```
updateCurrentMeta()
relativeTime(value)
```

`updateCurrentMeta` reads `signals`, `menuCurrentMeta`, `keepButton`,
`parkButton`, `app.mtime`. Guard on missing refs so the shell can call it
harmlessly.

`openMenu` already calls `beforeMenu()`; ribbon passes `renderChannels`.
The channel chip click calls `bar.setChannel(id)` then `options.onChannel(id)`
so the host can rebuild the deck and save the channel.

The delete button in `favoriteRow` calls `options.onDelete(app)`; ribbon
passes `openDeletePanel`.

**Wire:**

- Ribbon removes `updateCurrentMeta` and `relativeTime`.
- `createBar` owns the keep/park button listeners and calls
  `options.onSignal(name, value)`; ribbon passes `signal`.
- The shell passes no `onSignal`, so the buttons are never wired there.
- Ribbon still owns `signal()` and the deck invalidation.

**Acceptance**

- Keep/Park change the flag in the row and the meta line.
- Channel chips still rebuild the menu and the deck.
- Delete still opens the delete panel from a row.
- Shell still renders the plain menu (no meta, no chips, no delete).
- Lint + screenshots.

Commit: `move meta and server bar hooks into bar.js`.

---

## Packet 6 — cleanup and proof

**Depends on:** Packets 1–5.

- `grep` both hosts for the names in this document; only `bar.js` should
  define them.
- Remove now-dead CSS classes only if nothing renders them.
- Update the README file list (`bar.js`) and the freeze note in `shell.js`.
- Run the full check:

```bash
cd _ribbon
npm run lint
python3 -m py_compile ribbon.py
```

- Screenshot both entry points with headless Chromium:

```bash
python3 ribbon.py --root /tmp/opencode/ribbon/demo --port 8799 --no-open
chromium --headless=new --no-sandbox --disable-gpu --hide-scrollbars \
  --window-size=1100,240 --virtual-time-budget=5000 \
  --screenshot=/tmp/opencode/ribbon/server.png http://127.0.0.1:8799/
chromium --headless=new --no-sandbox --disable-gpu --hide-scrollbars \
  --allow-file-access-from-files --window-size=1100,240 \
  --virtual-time-budget=5000 \
  --screenshot=/tmp/opencode/ribbon/shell.png \
  file:///home/mrjohn/Work/_ribbon/index.html
```

The demo root used above is:

```text
/tmp/opencode/ribbon/demo/
  index.html      a plain page
  alpha/index.html
  beta/README.md
```

Commit: `finish the bar.js extraction`.

---

## Guardrails for every packet

1. One packet, one commit. Do not mix a move with a feature.
2. Do not change bar.css or card.css in these packets.
3. Do not add dependencies. `bar.js` is a classic script.
4. Keep both entry points working at the end of every packet:
   - server: `python3 ribbon.py --root …`
   - no server: open `_ribbon/index.html` directly.
5. If a function has a host-specific branch, stop and put the branch in the
   host. Do not grow a second `if (shadow)` inside `bar.js`.
6. `shell.js` stays frozen for *new features*; it only loses code that has
   moved to `bar.js`.
7. When in doubt, prefer the ribbon version (it is the fuller one) and
   parameterise the shell's missing data through `options`.

---

## Why this order

- Packet 1 has no DOM and no state, so it cannot break a screenshot.
- Packet 2 is the first move that touches the menu; it proves the
  `createBar` shape and the `root` parameter on `favoriteRow`/`renderMenu`.
- Packet 3 is isolated to the LEDs and the tip, which are easy to inspect.
- Packet 4 is the largest surface (forms, async, token) and goes last among
  the shared UI.
- Packet 5 is server-only, so it cannot regress the no-server page.
- Packet 6 is the proof and the cleanup.
