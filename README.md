# Ribbon

Ribbon is a small bar that sits at the top of your screen. It helps you move
between the project folders on your computer. You do not have to type long
web addresses.

```
┌──────────────────────────────────────────────────────────────────────┐
│ ●●● 04 / 11  Beam Library ▾  ‹ Back › Next ▦ Contents ⤨ Drift ↻ ✕  │
└──────────────────────────────────────────────────────────────────────┘
```

## What you need

- Python 3.11 or newer.
- A folder that holds your projects. Put each project in its own folder.
- Git and the GitHub CLI are optional. You only need them for the Git
  buttons.

You do not need to install anything else.

Ribbon is a small Python program. `ribbon.py` runs it and holds its own copy of
the bar's JavaScript and CSS. A few Python files sit next to it, so keep them
together in one folder when you copy Ribbon somewhere else.

## Start Ribbon

1. Open a terminal.
2. Type this command:

```bash
python3 /path/to/_ribbon/ribbon.py
```

3. Your browser opens the first project.
4. Keep the terminal window open while you use Ribbon.
5. When you are done, click the terminal and press **Ctrl+C**.

If you are already in the `_ribbon` folder, this is enough:

```bash
python3 ribbon.py
```

Ribbon looks for project folders near its own folder. If one folder holds all
your projects, it looks inside that folder. It will not guess your home folder
or a system folder. If it cannot find a safe place, or picks the wrong one,
tell it where to look:

```bash
python3 /path/to/_ribbon/ribbon.py --root ~/my-projects
```

Ribbon looks at the folders directly inside that place. It does not list the
files inside those folders.

## A shelf on every new tab

Chrome can show your Ribbon projects every time you open a new tab. It uses a
small extension that comes with Ribbon. You do not need to install anything
from a store.

1. Open `chrome://extensions`.
2. Turn on **Developer mode** in the top right corner.
3. Click **Load unpacked**.
4. Pick the `extension` folder inside `_ribbon`.
5. Open a new tab.

The page shows one card for each project. The card has the project name and
the colour for its kind. Click a card to open the project in the same tab.

Ribbon must be running for the cards to appear. The extension looks for it on
the usual ports, 8765 to 8784. If Ribbon is not running, the page says so and
shows the command to start it. Start Ribbon, then click **Check again**.

If you start Ribbon with `--port` outside that range, the new tab page will
not find it. Leave out `--port` to use the usual range.

## What Ribbon shows

- One row for each project folder.
- A folder with a web page opens that page. `index.html` wins if it is there.
- A folder with only a Markdown file opens the document.
- Any other folder opens a contents card.
- A page with no `<title>` opens as a contents card instead. This keeps
  private pages, like login pages, out of the way.

Markdown is a simple way to write a page using plain text. Ribbon shows the
finished page for you.

## The bar

| Button | What it does | Key |
| --- | --- | --- |
| App name | Opens the app menu | `/` |
| `☆` | Adds or removes a favorite | |
| `‹ Back` | Goes to the project before this one | `[` |
| `› Next` | Goes to the project after this one | `]` |
| `▦ Contents` | Opens or closes the contents card | `C` |
| `⤨ Drift` | Picks another project for you | `R` |
| `↻` | Reloads the project you are looking at | `Shift+R` |
| `✕` | Hides the bar | `H` |

Back and Next wrap around. Ribbon asks the browser to get the projects on
either side ready. Those two clicks then open almost at once. When you move
between projects, the bar stays put. Only the page content cross-fades. Older
browsers just replace the page instead.

The bar also hides when you scroll down. It comes back when you scroll up.
When it is hidden, a small **RIBBON** tab waits in the top right corner. Click
it, or press **H**, to bring the bar back.

Ribbon does not change your project pages. It adds the bar only while it
sends a page to your browser.

## The app menu

Click the app name, or press **`/`**, to open the menu.

- **Search**: start typing to filter the list.
- **Enter**: opens the first match.
- **Escape**: closes the menu.
- **Down arrow**: moves to the first row.
- **Click a row**: opens that project.
- **Click a star**: adds or removes a favorite.
- **Click `✕`**: deletes a folder after you confirm.

The menu puts favorites at the top. It also shows the same three Git lights
as the bar. Rows are sorted so projects that need the most Git work come
first.

## Favorites

Use the star beside the app name in the bar, or the stars in the menu. A
filled star means the project is a favorite. Click it again to remove it.

Your browser remembers favorites. They are kept in the browser, not inside
your project folder.

## Channels

The chips above the search box narrow both the menu and Drift. They are made
from what Ribbon already knows. There is nothing to set up.

- **All**: every project.
- **Needs push**: a remote is set, but some commits are waiting to go out.
- **Uncommitted**: the project has changes that are not saved in Git yet.
- **No repo**: Git has not been started in that folder.
- **Dusty**: the project has not been opened in 30 days, or was never opened.
- **Shipped**: the project is clean and pushed.
- **HTML**, **Python**, **Markdown**, and other types: one chip for each kind
  of project.

The number beside a chip tells you how many projects are in it. Pick a
channel, then press **R**. Drift picks only from that channel.

## Drift

Drift is not a coin flip. It shuffles the whole list once. Projects that need
work, or that you have not opened in a while, are more likely to come up
early. It does not repeat a project until the deck is empty.

The deck is remembered for the browser tab. Close the tab to start a new
deck, or pick another channel.

## The three little lights

The three lights show the **Git** state of the project you are looking at.
Git is a tool that saves old versions of your work. A **repository** (or
**repo**) is a project folder that Git watches.

| Light | What it means | Click it to |
| --- | --- | --- |
| Left | Green: this folder is in Git. Dark: it is not. | Create a repository. |
| Middle | Green: nothing new to save. Yellow: there are unsaved changes. | Save the changes with a commit. |
| Right | Green: backed up. Yellow: not pushed. Red: commits are waiting. Dark: no remote. | Push, make a remote, or publish to GitHub Pages. |

Hover over a light to read what is going on. On a phone, tap a light once to
read the same message, then tap it again to open the Git panel. The menu shows
the same lights next to every app, so you can scan the whole list.

Clicking a light on a computer, or tapping it twice on a phone, opens a small
panel. It shows the repo folder, branch, changed files, and any warnings.
Nothing happens until you press the button in that panel.

- **Create a repository** makes `.git`, adds a starter `.gitignore`, and
  makes the first commit.
- **Commit** saves the changed files with your message.
- **Push** sends your commits to the remote.
- **Create a remote** uses the GitHub CLI (`gh`) to make a repo and push it.
  Run `gh auth login` once before you use this.
- **Publish to GitHub Pages** puts your page on the web. GitHub Pages needs a
  public repo on the free plan. It also needs a lowercase `index.html` at the
  root of the repo. If your page has another name, Ribbon offers to make an
  `index.html` that opens it. Commit and push that file, then publish again.

If a folder has no README, the remote and Pages panels offer a **README.md**
box. Ribbon writes the file, commits it, and pushes it before it makes or
publishes the repo. An existing README is never overwritten.

Git buttons only work when Ribbon runs on your own computer at `127.0.0.1`
or `localhost`. Use `--no-git-actions` if you want the lights but no buttons.

## The contents card

A contents card shows a whole folder on one page:

- how many files and folders it has
- a color bar for the kinds of files
- the files you touched most recently
- hidden files and folders, even when they are ignored
- the folder's `.gitignore`, or the repo's when the folder has no own file

The card marks files that Git would ignore. It also warns about likely
secrets, such as `.env`, that Git would include. Check the card before you
press **Commit**. It answers a simple question: will the next commit include
something it should not?

When a project opens a real HTML page, use **Contents** or **C** to see its
card. Press **C** or **Escape** to close it.

## Add a new project

1. Make a new folder inside your projects folder.
2. Put a page in it. The usual name is `index.html`.
3. Give the page a title:

```html
<title>My Cool App</title>
```

4. Come back to the tab or refresh the page. Ribbon refetches the list when
   the page regains focus and when the app menu opens.

Ribbon also opens other `.html` files, such as `app.html` or `landing.html`.
If there are several, `index.html` wins. Then it tries names like `app.html`,
`main.html`, `home.html`, `site.html`, and `start.html`. After that, it uses
the first one in alphabetical order.

Pages without a title are skipped on purpose. If you want to open them
anyway, use:

```bash
python3 /path/to/_ribbon/ribbon.py --include-untitled
```

## Delete a project

Every row in the app menu ends with a small **✕**. Click it to remove that
folder from disk. Ribbon asks first and shows the exact command it will run,
with the full path:

```bash
rm -rf -- '/home/you/projects/my-old-app'
```

Nothing happens until you press **Delete folder**. Ribbon only deletes a
direct child of the projects folder. It refuses to delete itself, a symlink,
or anything outside that folder. The row disappears from the menu after the
delete, and its saved Ribbon data is removed too.

The **✕** is hidden when Ribbon is read-only (`--no-git-actions`).

## Where Ribbon keeps your data

Ribbon keeps a small state file outside your project folders:

```
~/.local/state/ribbon/state-<hash>.json
```

The hash comes from the projects folder. Two different folders keep separate
state. If `XDG_STATE_HOME` is set, Ribbon uses that place instead of
`~/.local`.

The file remembers which projects you opened and when. Delete the file to
reset Drift. Nothing is written inside your projects unless you press a Git
or delete button.

## Keep your projects safe

Ribbon serves every project from the same address. The bar's key sits in each
page, so a script in one project can read the key and press the bar's buttons.
That means any project you add can delete or change the other projects.

Only put projects you trust in the folder. Do not serve a project you found
online, a page from someone else, or an app that runs code you have not read.

Ribbon is for your own computer. Keep it on `127.0.0.1` or `localhost`. Do not
use `--host` on a network you do not control.

`--host 0.0.0.0` (or any address other than `127.0.0.1`, `localhost`, or
`::1`) lets other devices read your projects. There is no password. Anyone who
can reach that address can open every page, the app list, and the Git status,
and can read the files Ribbon serves. Ribbon prints a warning when it starts
this way. Git buttons, delete, and saved state stay off, but reading is still
open. Only use it on a network you trust.

The key and the address check stop other websites from pressing the buttons.
They do not stop code that Ribbon itself serves. That code is already inside.
Use `--no-git-actions` when you want to look without any buttons that change
files.

Ribbon does not serve a file or folder whose name starts with a dot. That keeps
`.git` and `.env` out of the browser. The contents card still lists them, so you
can spot a secret before a commit. A link inside a project that points outside
your projects folder is not served either.

## All the commands

```bash
python3 /path/to/_ribbon/ribbon.py                 # start and open the first app
python3 /path/to/_ribbon/ribbon.py --list          # show the folders and quit
python3 /path/to/_ribbon/ribbon.py --app 3         # start on folder number 3
python3 /path/to/_ribbon/ribbon.py --root ~/sites  # use a different folder
python3 /path/to/_ribbon/ribbon.py --port 9000     # use a different port
python3 /path/to/_ribbon/ribbon.py --host 0.0.0.0 # let the network read (no password)
python3 /path/to/_ribbon/ribbon.py --no-open       # do not open a browser
python3 /path/to/_ribbon/ribbon.py --include-untitled
python3 /path/to/_ribbon/ribbon.py --no-git-actions # lights only, no buttons
python3 /path/to/_ribbon/ribbon.py --verbose       # show every request
python3 /path/to/_ribbon/ribbon.py --dev           # read JS/CSS from disk
python3 /path/to/_ribbon/ribbon.py --help          # all options
```

If the first port is busy, Ribbon tries the next one. It tells you which one
it picked.

## Check the code

You need Node.js only if you want to run the code checks. You do not need it
to use Ribbon.

```bash
cd _ribbon
npm install
npm run check
```

`npm run check` runs ESLint, Stylelint, and the tests. It also checks that
the copy inside `ribbon.py` matches the files on disk. The tests check the
small helpers in `bar.js`. They also fail if a function that belongs in
`bar.js` is written again in `ribbon.js`, or if a selector in `ribbon.js` does
not exist in the bar markup.

Ribbon ships with the JavaScript and CSS inside `ribbon.py`. If you edit one
of those browser files, rebuild the copy:

```bash
python3 build.py           # embed the current JS and CSS
python3 build.py --check   # fail if the copy is stale
```

Both forms refuse a CSS file that contains `</style`. The bar pastes
`bar.css` straight into a `<style>` tag, so that text would close the tag
early.

While you work on the bar, you can skip the rebuild. Run
`python3 ribbon.py --dev`. That reads the JS and CSS from disk, so every
reload shows your edit. Use the normal command when you want to check what
the release copy will serve.

## The files

```
_ribbon/
  ribbon.py     finds the projects, serves them, and paints the bar shell
  build.py      embeds the browser files into ribbon.py
  ribbon.js     adopts the server-rendered bar shadow root and drives it
  bar.js        shared bar code: helpers and createBar
  card.js       the contents card
  bar.css       the look of the bar
  card.css      the look of the contents card
  markdown.css  the look of a Markdown document
  test/         tests for the shared bar code
  AGENTS.md     notes for agents and people who work on the code
  package.json  the code-check commands
```

The browser files are the source. `build.py` compresses them and writes the
result into `ribbon.py`, which is why the release copy works on its own. Run
it after every change to those files, or use `--dev` while editing.

The bar has two halves, and both have to change together. The static shell is
`BAR_MARKUP` in `ribbon.py`, because it is rendered into the page before any
script runs. Its behavior is `bar.js`. New bar features go there, not in
`ribbon.js`. A new button means adding its markup to `BAR_MARKUP` in
`ribbon.py` and its behavior to `bar.js`.

## Known limitations

The bar arrives as an inline boot script and an inline `<style>` block. A page
can set its own `Content-Security-Policy` in a `<meta>` tag. If that policy
blocks inline code, the browser drops both. The page then opens without the
bar. Ribbon does not read the page's policy, and it does not add a nonce or a
hash. So a strict policy cannot allow the bar. A policy that allows
`'unsafe-inline'` and has no nonce or hash lets it through. Otherwise, relax or
remove the policy while you use Ribbon.

The contents card and the Markdown view are built by Ribbon, so they do not
have this problem.

Ribbon puts its bar at the top of `<body>`, before the page's own content. So
the bar is there at first paint and cannot pop in. That spot has a cost.
Selectors that use position see Ribbon's nodes first. `body > :first-child`
matches the injected `<style>`. Rules such as `body > :first-child + *` then
skip past the rest of Ribbon's markup. If a page styles its first child by
position, give that element a class instead.

Ribbon checks the page text for `data-ribbon-host` and
`/__ribbon/ribbon.js` to decide if the bar is already there. A page that only
talks about Ribbon can contain one of those strings. Ribbon then treats it as
a page that already has the bar, and does not add one. This is rare. The check
is plain text, so it also reads the page's visible words.

## If something goes wrong

| Problem | Try this |
| --- | --- |
| It says **No folders found** | Your pages may have no `<title>`. Try `--include-untitled`, or use `--root` to pick the right folder. |
| The bar disappeared | Press **H**, or click the small **RIBBON** tab in the top right. |
| The bar is missing on one page | That page's `Content-Security-Policy` may block inline code. See [Known limitations](#known-limitations). |
| The bar is missing on a page that talks about Ribbon | The page contains `data-ribbon-host` or `/__ribbon/ribbon.js` as text. Ribbon thinks the page already has the bar. See [Known limitations](#known-limitations). |
| It shows the wrong folder | Add `--root ~/the/folder/you/want`. |
| It asks you to use `--root` | Ribbon could not find a safe folder near itself. Add `--root ~/the/folder/you/want`. |
| The address is already in use | Ribbon tries the next port by itself. Read the address it prints. |
| The Git buttons are greyed out | Start Ribbon on `127.0.0.1` or `localhost`, and do not use `--no-git-actions`. |
| **Create a remote** fails | Run `gh auth login`. Check that the repo name is not already taken. |
| **Publish with GitHub Pages** fails | Use a public repo on the free plan. The repo root needs a lowercase, committed, unignored `index.html`. |
| Drift repeats a project | Pick another channel, or close the tab to clear the deck. |
| You want to reset Drift | Delete `~/.local/state/ribbon/state-<hash>.json`. |
| Ribbon says a `.scratch/` folder is tracked | Run `git rm -r --cached .scratch`, add `.scratch/` to `.gitignore`, then commit. |
| Git says there is nothing to commit | Close the panel and open it again after the file changes. |
| You forgot the commands | Run `python3 /path/to/_ribbon/ribbon.py --help`. |
