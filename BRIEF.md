# Ribbon — design brief

**Status:** draft, for arguing with
**Date:** 4 November 2026

**Built so far:** directory-only discovery (one row per folder), the contents
card (file grid, hidden entries, ignore status, and a `.gitignore` preview),
a Contents flipper on every HTML page, the deck (`Drift`), derived channels,
Keep/Park, and the sidecar state file. The stage/card overlay, thumbnails,
and the Shelf are still ahead.

---

## TL;DR

Ribbon already has the two hardest parts of StumbleUpon: a persistent toolbar
that sits on top of everything, and a corpus worth wandering through. What it
does not have is a reason to wander.

The move is not to build a social network for one person. It is to make
**discovery a decision engine for shipping**, not a slot machine for browsing.
StumbleUpon gave you novelty. Ribbon should give you **renewal** (seeing old
work again) and **completion** (finding the 80% done).

Three bets, in order:

1. **Drift** — replace the coin-flip `Random` with a biased deck that never
   repeats, learns from what you open, and leans toward unfinished work.
2. **Channels** — let the bar's title double as a room selector, so "Random"
   becomes "stumble inside Python" or "stumble inside needs-push".
3. **The Shelf** — an optional, public, static contact sheet of the work that
   is actually shipped. The private tool becomes the portfolio.

Everything else is optional. Keep the bar. Add a stage.

---

## Where Ribbon is today

| Piece | What it is |
| --- | --- |
| `ribbon.py` | Walks the root, classifies folders as `page`, `markdown`, or `project`, reads titles/READMEs, reads git state, serves everything on `127.0.0.1`. |
| `ribbon.js` | Injects a shadow-DOM bar into every served page: git LEDs, title menu, Back/Next/Random/Reload/Hide, favorites, git action dialogs. |
| `index.html` + `shell.js` | The no-server snapshot version of the same bar. |
| Data | `kind`, `type`, `icon`, `description`, `files`, `mtime`, `git`, `url`, `path`. No tags, no opens, no notes, no screenshots. |

The current `Random` is `Math.random()` over the filtered list. It can land on
the same project twice in a row and it is blind to whether the project is
finished, abandoned, or on fire.

**What Ribbon is good at:** getting you from one project to another without
typing a URL, and making the git state of the whole portfolio visible at a
glance.

**What it is not doing:** helping you decide *which* project deserves the next
hour, and helping you *see* the portfolio as a body of work rather than a list
of folders.

---

## Two jobs

The banner has two jobs that pull in opposite directions. Name them, or the
feature list becomes mush.

**Job A — Ship.** "Get this vibe-coded thing onto GitHub without leaving the
page." The git lights and publish flow already serve this. Discovery must feed
it, not compete with it.

**Job B — Rediscover.** "I have 40 projects and I forgot what half of them
are." This is the StumbleUpon job. It is not about entertainment; it is about
recovering context and finding the thing that is ready to be finished.

The design rule that follows:

> Every discovery surface must end in an action — open, ship, park, or note.
> If a screen only produces scrolling, it is not earning its place in the bar.

---

## What actually transfers from StumbleUpon

StumbleUpon worked because of other people, an infinite corpus, and a thumb
that trained a recommendation engine. Ribbon has none of those literally. Here
is the honest mapping.

| StumbleUpon | Transfers? | Ribbon version |
| --- | --- | --- |
| The toolbar | **Yes, exactly** | Already built. The bar is the product. |
| The Stumble button | **Yes** | `Drift`: biased, no-repeat, keyboard-first. |
| Interest channels | **Yes** | Channels derived from type, git state, and README tags; user can pin. |
| Thumbs up / down | **Partly** | Not a taste rating. A decision: **Keep**, **Park**, **Ship**. |
| Neighbours (people like you) | **No, not yet** | The neighbour is **past you**: what you starred, opened at 2am, abandoned. |
| Page views / stumbled counts | **Partly** | Local opens, last opened, dwell. Useful as "dusty", not as vanity. |
| "More like this" | **Yes** | Related by shared type, tags, and file/README similarity. |
| Public discovery feed | **Yes, as an export** | The Shelf: a static page of shipped work. |
| Social following, comments | **Skip** | One user. No fake crowd. |
| Endless scroll | **Skip** | The corpus is finite. A session should end. |

The honest summary: **copy the mechanics of serendipity, not the mechanics of
engagement.**

---

## The core idea: Drift is a deck, not a die

This is probably the flash you lost. `Random` is the weakest possible
serendipity: uniform, memoryless, and indifferent to your goals.

Replace it with a **deck**:

- Build an ordered deck of every asset at the start of a session.
- Weight the shuffle by a score (below), but shuffle once.
- Deal without replacement, so you cannot see the same project twice until the
  deck is exhausted.
- Reshuffle with fresh weights when the deck empties.
- `R` deals the next card. Holding `Shift+R` reshuffles.

That single change fixes the two things that make `Random` feel broken: repeats
and aimlessness.

### The score

```
score = base
      + staleness      (days since mtime or last open, capped)
      + unfinished     (no repo > dirty > unpushed > clean)
      + kept           (you said this is worth finishing)
      + channel match  (if drifting inside a channel)
      - parked         (you said not now)
      - recent         (already seen this session)
      + jitter         (small, so the deck is not deterministic)
```

Two guardrails:

- **Ship beats browse.** Unfinished work gets a real bonus, but never so much
  that a clean, shipped project is invisible.
- **Parked means parked.** A park sets a snooze (default 14 days). Ignoring the
  park is how recommendation engines become nagging.

### Channels

A channel is a saved filter the deck can be built from. Derive them, do not
make the user author them:

- **Kind:** Pages, Markdown, Projects.
- **Type:** HTML, Python, JS, Rust, Shell.
- **State:** Needs a repo, Uncommitted, Unpushed, Shipped.
- **Tags:** pulled from README headings, filename tokens, and `package.json` /
  `pyproject.toml` keywords. Show the top 10, let the user pin or hide them.
- **User:** Favorites, Dusty (not opened in 30 days), Never opened.

The bar already has the perfect affordance: the title button opens the menu.
Make the menu's top row a row of channel chips. `Drift` then means "deal from
the current channel." The count in the bar becomes `07 / 40 · Python`.

### Keyboard

Match the existing grammar; do not invent a second one.

| Key | Action |
| --- | --- |
| `R` | Deal next card (Drift) |
| `Shift+R` | Reshuffle / new seed |
| `[` `]` | Back / Next in the deck history |
| `Enter` | Open the card |
| `S` | Ship (opens the git/publish panel) |
| `P` | Park (snooze) |
| `K` | Keep (queue for later, not a public rating) |
| `/` | Search / jump |
| `1`–`9` | Switch channel |
| `Esc` | Close the stage |

---

## The stage

Discovery should not live in the 40px bar. It should be a full-surface overlay
that uses the bar as its frame, then gets out of the way. Think index cards on
a workbench, not a social feed.

```
┌──────────────────────────────────────────────────────────────────────┐
│ ●●● 07 / 40  Python ▾      ‹ Back  › Next  ⤨ Drift  ↻        ✕      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌────────────────────────────────────────────────────────────┐     │
│   │ PY  2026-10-28-intelliprompt                    ● ● ○      │     │
│   │                                                            │     │
│   │ Intelliprompter — local edition                            │     │
│   │ A port of the TypeSafe cookbook to a fully local stack…    │     │
│   │                                                            │     │
│   │ never opened · last touched 6 days ago · 12 files          │     │
│   │                                                            │     │
│   │ [ Open ]   [ Ship ]   [ Park ]   [ Keep ]     1 of 8       │     │
│   └────────────────────────────────────────────────────────────┘     │
│                                                                      │
│                        next card peeks from below                    │
└──────────────────────────────────────────────────────────────────────┘
```

Card anatomy, top to bottom:

1. **Type stripe** — the existing colour-coded badge, used as a 3px left edge.
2. **Title + path** — the folder name is the identity; the title is the human
   name. Show both.
3. **Git lights** — the same three dots, in the same order, always.
4. **One-line README** — already extracted by `readme_summary`.
5. **Context line** — "never opened", "last touched 6 days ago", "3 files",
   "pushed 2 months ago". This is the StumbleUpon "stumbled by" line, honestly
   translated.
6. **Actions** — Open, Ship, Park, Keep. Ship is the primary and should be the
   only one with a filled style.

For media assets (see below), the README line is replaced by a thumbnail.

### Why a card, not a page

The card is the smallest unit that carries enough context to make a decision.
Rendering the actual app inside the stage is tempting and wrong for v1: many
projects are half-built, and a broken page is a bad first impression. Open the
real thing only after the user chooses. Later, a "peek" thumbnail can be an
opt-in preview.

---

## The Shelf

This is the bridge from private tool to public portfolio, and the part that
makes Ribbon more than a launcher.

**What it is:** a static `index.html` generated from the same discovery data,
listing only assets that are explicitly marked public. Not a CMS. Not a feed.
A contact sheet.

- One card per project: thumbnail, title, one line, type, link.
- Grouped by channel, or in a single shuffled grid.
- Optional "stumble" button on the public page that deals from the deck.
- No analytics, no comments, no accounts.
- Deployable by pushing the generated folder to GitHub Pages — the same flow
  the ribbon already has.

**What makes it safe:**

- Public is opt-in per project, stored in the sidecar state, not inferred.
- The export refuses to include a project whose repo is dirty or unpushed
  unless the user explicitly overrides.
- `.scratch/`, `.env`, and ignored files are never exported.
- The generated page is plain HTML/CSS/JS; no server needed.

**What makes it good:** the thumbnail. A portfolio of text cards is a list. A
portfolio of screenshots is a portfolio. Add a `--shoot` pass (headless
Chromium) that captures one 1200×750 image per page and stores it in
`_ribbon/.shots/`, keyed by path hash. For media folders, use the first image
or video frame instead.

---

## Asset cards (the "other stuff" answer)

Right now Ribbon sees three kinds: `page`, `markdown`, `project`. If the
portfolio is growing beyond websites and scripts, add a fourth:

**`asset`** — a folder that contains media but no entry point:
`*.png`, `*.jpg`, `*.webp`, `*.mp4`, `*.webm`, `*.gif`, `*.svg`, `*.blend`,
`*.glb`, `*.wav`.

The card shows:

- a thumbnail (image, or first frame of video),
- dimensions/duration and file size,
- the folder name and any README,
- the same git lights, because assets need backing up too.

This turns the ribbon into a **visual StumbleUpon for your own output**, which
is the most literal reading of what you asked. It also makes the Shelf worth
sharing: people can see the work, not just the repo names.

Cost: one new classifier branch, a thumbnail cache, and a media element in the
card. No server-side transcoding in v1.

---

## Feature ladder

### Now — one weekend, no new dependencies

- **Deck-based Drift.** Weighted shuffle, no repeats, respects Park.
- **Signals.** Local `state.json`: opens, last opened, keep/park, note.
  Endpoints behind the existing token.
- **Context line** on the card: opens, last touched, git summary.
- **Channel chips** in the existing menu, derived from kind/type/state.
- **Rename** `Random` → `Drift` in the UI (keep `R`).

### Next — a week, still local

- **Drift stage.** Full-surface card overlay with the four actions.
- **Ship queue.** A saved channel: "closest to done", sorted by unfinished
  score. This is the feature that directly moves the GitHub goal.
- **Notes.** One free-text "next step" per project, shown on the card and
  editable from the bar. This is the cheapest memory aid in the whole brief.
- **Auto-tags** from README headings and package metadata.
- **Related drift.** "More like this" using shared tags and type.

### Later — only if the first two earn it

- **Asset kind + thumbnails.**
- **Screenshots** and the static **Shelf** export.
- **Time capsule.** "On this day" / "one year ago" channel.
- **Optional shared taste file.** If you ever want friends to stumble your
  shelf, export a small JSON of public projects + tags. No accounts, no server.

### Skip

- Comments, likes from other people, follower counts.
- Infinite scroll on the shelf.
- Streaks or notifications that reward opening the bar.
- Ranking by most-viewed. That is the opposite of discovery.
- A second persistent toolbar. One bar, always.

---

## Data and server sketch

State belongs to Ribbon, not to the projects. Never write into an app folder.

```
~/.local/state/ribbon/state.json     (default)
  or <root>/.ribbon/state.json       (--portable)
```

```json
{
  "version": 1,
  "assets": {
    "2026-10-28-intelliprompt": {
      "opens": 4,
      "last_opened": "2026-11-02T22:14:00Z",
      "dwell_seconds": 312,
      "keep": true,
      "parked_until": null,
      "public": false,
      "note": "local TTS is the last blocker",
      "tags": ["python", "tts", "cookbook"]
    }
  },
  "channels": ["python", "needs-push", "dusty"],
  "deck": { "seed": 1234, "order": ["..."] }
}
```

Endpoints, all `POST` behind the ribbon token, all local-only:

| Endpoint | Purpose |
| --- | --- |
| `GET /__ribbon/api/state` | Full sidecar for the UI |
| `POST /__ribbon/api/signal` | `{path, open|keep|park|note}` |
| `POST /__ribbon/api/drift` | `{channel, seed}` → next card |
| `POST /__ribbon/api/shelf` | Build the static export |

Rules:

- Writes are atomic (temp file + rename), like the rest of the tool.
- The static/no-server version keeps signals in `localStorage` and degrades
  gracefully; it cannot write the sidecar.
- No new Python dependency. `json`, `random`, `hashlib` are enough.

---

## Design language

The bar is already a small, confident piece of design: near-black, warm off-
white, mono micro-labels, three LEDs, generous 40px. Do not redesign it. Extend
its grammar.

- **The card is paper, not chrome.** Warm off-white surface, 1px rule, a type
  stripe, no drop shadows beyond one soft lift. The bar stays dark.
- **Colour does one job.** Existing type colours identify the asset. Do not add
  a second colour system for "mood" or "score".
- **Numbers are mono.** Counts, dates, file sizes in the same 10px mono as the
  LED labels.
- **Motion is a deal, not a slide.** New card rises 8px and fades in over
  140ms. No parallax, no spring.
- **One primary per card.** Ship. Everything else is a ghost button.
- **Empty states are instructions.** "Nothing here needs a repo. Lucky you."
  Not a shrug emoji.

---

## Guardrails

1. **The bar never grows.** Discovery opens over it and closes. The 40px stays
   40px.
2. **Never write into a project folder.** State, shots, and exports live in
   Ribbon's own directories.
3. **No engagement mechanics.** No streaks, no badges for opening apps, no
   "you haven't visited in 3 days".
4. **Parked means quiet.** Respect snoozes and hides.
5. **Degrade without the server.** The no-server page still navigates, still
   favorites, still shows a plain shuffle. It just cannot persist signals.
6. **Ship is always one keystroke from discovery.** The whole point.
7. **No fake social proof.** If a number is shown, it is yours.

---

## How we would know it worked

- **Repeat rate** of Drift drops to zero within a deck.
- **Dusty recovery:** number of projects opened that had not been opened in
  30+ days.
- **Ship throughput:** percentage of the portfolio with a remote, and median
  days from "dirty" to "pushed".
- **Decision speed:** time from pressing `R` to pressing `Enter` or `S`.
- **The bar stays fast:** no measurable layout shift, no new blocking request.
- **You delete fewer projects.** The honest signal that rediscovery is working.

---

## The flash, reconstructed

Four plausible versions of the idea you lost. Which one was it?

1. **The deck.** Random, but shuffled once and dealt without replacement.
   (Most likely. It is the smallest change with the biggest felt difference.)
2. **The channel in the title.** The bar's title becomes the room, and Drift
   deals from that room. (Most elegant. Uses an affordance that already exists.)
3. **The visual shelf.** Your assets are the point; the ribbon should show
   thumbnails, not filenames. (Most likely if "portfolio of assets" is literal.)
4. **The daily card.** Ribbon opens on one project each morning, chosen by the
   deck. (Most StumbleUpon. Also the most likely to be annoying.)

They are not mutually exclusive, but they are different first commits.

---

## Recommended first slice

Ship this and stop:

1. `state.json` with opens, last opened, keep, park, note.
2. A weighted deck in `ribbon.py`, served by `GET /__ribbon/api/apps` as an
   ordered list plus an opaque `seed`.
3. `R` deals the next card; `Shift+R` reshuffles; `[`/`]` walk history.
4. Channel chips in the existing menu: `All`, `Needs push`, `No repo`,
   `Dusty`, plus one per detected type.
5. The card overlay with Open / Ship / Park / Keep.
6. Rename `Random` to `Drift`.

Do not build the Shelf, thumbnails, or the asset kind until this slice has
been used for a week. The deck will tell you whether the appetite is real.

---

## Open questions

1. **Primary job:** is this for *finishing* the backlog, or *showing off* what
   is done? The brief assumes finishing. The Shelf assumes showing off.
2. **Public by default?** A portfolio wants an audience; a workbench wants
   privacy. Which is Ribbon?
3. **Screenshots:** is headless Chromium acceptable as a dependency, or does
   that break the "one Python file" promise?
4. **State location:** sidecar in the root (portable, travels with the folder)
   or in `~/.local/state` (clean, but invisible)? Default to the latter.
5. **The name:** does "Drift" feel right, or should it stay "Random" and let
   the behaviour change quietly?
