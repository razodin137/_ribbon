# Ribbon

**Ribbon wraps around your vibe-coded projects, helps you surface them, and
shows you how far along they are.**

Ribbon is a little bar at the top of your screen. It lets you jump between
all the project folders you made, without typing long addresses. Each folder
gets one line: a page opens the page, and everything else opens a card with
its contents.

```
┌──────────────────────────────────────────────────────────────────────┐
│ ●●● 04 / 11  Beam Library ▾  ‹ Back › Next ▦ Contents ⤨ Drift ↻ ✕  │
└──────────────────────────────────────────────────────────────────────┘
```

## Start it

Open a terminal in the folder that holds `_ribbon` and type this:

```bash
python3 _ribbon/ribbon.py
```

(If `_ribbon` lives somewhere else, use its full path instead.)

A browser window opens with your first app. That's it!

Keep the terminal window open while you use Ribbon. When you are done,
click the terminal and press **Ctrl+C** to stop it.

Ribbon lists **directories, one line per directory**. It looks in the folder
that contains `_ribbon`. If `_ribbon` sits beside a single folder of projects
(the way `Work/tries` works), it lists that folder's children instead.
If it guesses wrong, you can tell it where to look:

```bash
python3 _ribbon/ribbon.py --root ~/my-websites
```

It does not list the files inside those folders. A folder with an HTML page
opens that page; every other folder opens a contents card. A folder with only
a Markdown file opens the document instead.

## What the buttons do

| Button | What it does | Keyboard |
| --- | --- | --- |
| `Beam Library ▾` | Open the app menu: search and jump to any app | `/` |
| `‹ Back` | Go to the app before this one | `[` |
| `› Next` | Go to the app after this one | `]` |
| `▦ Contents` | Flip an HTML page to its contents card | `C` |
| `⤨ Drift` | Deal the next project from a no-repeat deck | `R` |
| `↻` | Reload the app you are looking at | `Shift+R` |
| `✕` | Hide the bar | `H` |

Back and Next wrap around. When you hide the bar, a tiny **RIBBON** tab
appears in the top right corner. Click it — or press **H** — to bring the
bar back.

Drift is not a coin flip. It shuffles the whole list once, weights projects
that need work or have been ignored, and deals them without repeats until the
deck is empty. The deck is remembered for the browser tab, so `R` keeps
moving forward instead of landing on the same project twice.

The app menu also has **Keep** and **Park**:

- **Keep** marks a project as worth finishing. Kept projects come up more
  often in Drift.
- **Park** puts a project away for 14 days. Parked projects are left out of
  the deck until the snooze ends.

Press **K** or **P** to do the same thing without opening the menu. Both
choices are stored next to your other Ribbon data, never inside the project
folder.

The bar also hides itself when you scroll down, and comes back when you
scroll up. At the very top of the page it sits in its own strip, so the
app's own header stays visible. Its buttons stay in the same place on every
app — even an app that is too short to scroll — so you can keep clicking
without looking.

## Find any app fast

Click the app's name in the bar, or press **`/`**, to open the app menu.

- **Search** — start typing to filter the list.
- **Enter** — open the first match.
- **Escape** — close the menu.

Every row shows the same three Git lights as the bar. The list sorts itself
so apps that need the most work come first: no repository, then unsaved or
unpushed changes, then apps that are fully backed up. Hover over a row's
lights to read its Git status.

## Channels

The chips above the search box narrow both the menu and Drift. They are made
from what Ribbon already knows, so there is nothing to configure:

- **All** — the whole portfolio.
- **Needs push** — a remote is set, but commits are waiting.
- **Uncommitted** — the repository has unsaved changes.
- **No repo** — Git has not been started.
- **Dusty** — not opened in 30 days, or never opened.
- **Shipped** — clean and pushed.
- **HTML**, **Python**, **Markdown**, and the other types — one chip per kind
  of project in the folder.

Pick a channel, then press **R**. Drift deals only from that channel. The
number beside each chip is how many projects are in it.

## The state file

Ribbon keeps opens, last-opened times, Keep/Park choices, and notes in one
small JSON file outside your project folders:

```
~/.local/state/ribbon/state-<hash>.json
```

The hash comes from the apps folder, so two different portfolios keep
separate state. If `XDG_STATE_HOME` is set, Ribbon uses it instead of
`~/.local/state`.

The file is created on first use and updated when you open a project or press
Keep or Park. Deleting it resets Drift. Nothing is written into your apps.

State works even with `--no-git-actions`: the git buttons are read-only, but
Drift still remembers what you opened. The no-server page cannot write the
state file; it still shuffles, but it forgets between visits.

## Favorites

The star beside the app name in the bar saves the app you are looking
at, without opening the menu. The menu has the same star at the top, and
stars next to every row do the same thing. Favorites get their own
section at the top of the menu, so your everyday apps are always one
click away. Click a filled star again to remove it.

The browser remembers your favorites. They work in both the server
version and the no-server version.

## Add a new app

1. Make a folder inside your apps folder.
2. Put a page inside it. `index.html` is the usual name.
3. Give the page a name, like this:

```html
<title>My Cool App</title>
```

Ribbon also opens any other `.html` file in the folder, so `app.html` or
`landing.html` works for local viewing. If there are several, `index.html`
wins, then names like `app.html`, `main.html`, and `home.html`, then the
alphabetical first one.

GitHub Pages is stricter: it only serves an `index.html` at the repository
root. When you publish a folder that has a different page name, Ribbon
offers to create an `index.html` that opens it. Your page keeps its name.

If Ribbon is already running, just refresh. It finds new folders by itself.

Pages without a `<title>` are not opened on purpose. That keeps login pages
and other private things out of the list. Ribbon still shows the folder, but
as a contents card instead of the page. If you really want the page itself:

```bash
python3 _ribbon/ribbon.py --include-untitled
```

## Delete a folder

Every row in the app menu ends in a small **✕**. Click it to remove that
folder from disk. Ribbon asks first and shows the exact command it will run,
with the full path:

```bash
rm -rf -- '/home/you/apps/2026-10-30-my-old-app'
```

Nothing happens until you press **Delete folder**. Ribbon only deletes a
direct child of the apps folder, and refuses to delete itself, a symlink, or
anything outside that folder. The row disappears from the menu afterward, and
its Keep/Park/note state is removed too.

Deleting is a server action, like the Git buttons. The **✕** is hidden when
Ribbon is read-only (`--no-git-actions`) or when you open the static
`index.html` page.

## Scripts, tools, and folders

Every folder directly inside your apps folder shows up, even if it has no
page. Ribbon labels folders with a script or build file such as
`package.json`, `pyproject.toml`, `Cargo.toml`, or a `Makefile`, then gives
everything else a plain **Folder** card.

Every card shows the folder name, the first paragraph of the README when
there is one, the kind of project, and a suggested command to run it. It
also shows a contents strip: how many files and folders there are, a color
bar of the file types, and the most recently touched items as small tiles.
It uses the same Git lights as everything else. Nothing is written into the
folder, and you never have to add an `index.html` just to see it.

Folders with only a Markdown file open as a rendered document instead of
a card. Ribbon looks for `README.md`, `README.markdown`, `index.md`, or
any other `.md` file in the folder. Links and pictures inside the
document keep working, and you can jump back out with the bar.

The app menu shows a small badge for every folder: `HTML` for a web page,
`MD` for Markdown, and codes such as `PY`, `JS`, `RS`, or `SH` for
project folders. Plain folders get `DIR`. Badges are color-coded by type —
orange for HTML, green for Python, grey for shell scripts, and so on — so
the same kind of project always looks the same. Hover over the badge to see
the full type.

## The contents card

Every contents card shows the whole folder on one page: the file grid, the
hidden files and folders, and the folder's `.gitignore` (or the repository's,
when the folder has none of its own). There is nothing to flip open.

- **ignored** marks a file or folder that `.gitignore` would leave out of a
  commit.
- **hidden** entries are listed even when they are ignored, so you can see
  what is really in the folder.
- **not ignored** flags a likely secret such as `.env` that a commit would
  include.

Check this card before you press **Commit**. It answers the question the git
panel cannot: will the next commit contain something it should not?

When a folder opens a real HTML page, the bar has a **Contents** button. It
flips the page over to the same contents card. Press **C** or click
**Contents** again to return, and press **Esc** while the card is open to
close it. The no-server snapshot still opens contents cards for folders without
a page, but it cannot see hidden files or ignore rules, and its HTML pages have
no Contents button; start `ribbon.py` for the full card.

## Check what it found

Want to see the list without opening a browser? Run:

```bash
python3 _ribbon/ribbon.py --list
```

It prints every folder it can see, with its path and whether it is backed
up. To start on a certain folder, add its number:

```bash
python3 _ribbon/ribbon.py --app 3
```

## The no-server version

Opening `_ribbon/index.html` directly also works. It shows the same bar
above a big window with the app inside.

But the list it uses is a snapshot. After you add a new app, refresh the
snapshot first:

```bash
cd /path/to/your-apps
python3 _ribbon/ribbon.py --write-apps
```

Then open `_ribbon/index.html`.

`apps.js` is generated locally and is in `.gitignore`, so a fresh clone shows
an empty bar until you run the command once.

One catch: when you open the file directly, some things are turned off by
the browser — the keyboard shortcuts and the scroll-to-hide. Some browsers
also keep favorites in a separate place, or forget them altogether. The
no-server page still has the old **Random** button: Drift, channels, and
Keep/Park need the server. If you want everything to work the same way every
time, use the server version at the top of this page.

## The three little lights

They show the **Git** state of the app you are looking at. Git is a tool
grown-ups use to save and back up versions of their work.

| Light | What it means | Click it to |
| --- | --- | --- |
| Left | Green: this folder is saved in Git. Dark: it is not. | Create a repository. |
| Middle | Green: nothing new to save. Yellow: unsaved changes. | Commit the changes. |
| Right | Green: backed up. Yellow: not pushed. Red: commits waiting. Dark: no remote. | Push, create a remote, or publish to GitHub Pages. |

Hover over a light to read exactly what is going on. The app menu repeats
all three lights next to every app, so you can scan the whole list at once.

Clicking a light opens a small panel. It shows the repository folder,
branch, changed files, and any warnings. Nothing happens until you press
the button in that panel.

- **Create a repository** makes `.git`, adds a starter `.gitignore`
  (unless you uncheck it), and makes the first commit.
- **Commit** stages every changed file and saves it with your message.
- **Push** sends your commits to the remote.
- **Create a remote** uses the GitHub CLI (`gh`) to make a **private**
  repository and push. You can choose Public instead, add a description,
  and tick **Publish with GitHub Pages** to turn on Pages for the repo and
  set the new Pages address as its homepage. Run `gh auth login` once before
  using this. On GitHub's free plan, Pages needs a public repository.
- **Publish to GitHub Pages** does the same for a repository that already
  has a remote. Click the right-hand light when everything is pushed. Pages
  uses the current branch and the repository root, so it needs an
  `index.html` there. If your page has another name, Ribbon offers to create
  an `index.html` that opens it; commit and push that file, then publish.

If the folder has no README, both **Create a remote** and **Publish to
GitHub Pages** offer a **README.md** box. Type a short introduction and
Ribbon writes `README.md`, commits it, and pushes it before it creates or
publishes the repository. Leave the box empty to skip it. An existing
README is detected and never overwritten.

Two safety notes:

- The panel lists the files that will be committed. Look for `.env`
  files, keys, or anything over 5 MB before pressing the button.
- A nested app shares its parent's repository. The panel shows the real
  repository folder and branch, so you know what you are saving.

Ribbon checks `.scratch/` folders before it commits or publishes. Hidden
scratch folders are meant for local notes and browser profiles, so they
must be listed in `.gitignore`. Ribbon's starter `.gitignore` already
includes `.scratch/`. If an older repository has one outside `.gitignore`,
the panel explains how to remove it with `git rm -r --cached` before you
push.

GitHub Pages only serves what Git publishes. Before turning Pages on,
Ribbon checks that the repository root has a lowercase `index.html` and
that Git will actually include that file. A differently named page, an
ignored file, or an uncommitted `index.html` is reported instead of
letting the site go live without a home page.

Git actions only work when the ribbon server is running on `127.0.0.1`.
Use `--no-git-actions` if you want the lights but not the buttons.

## If something goes wrong

| Problem | Try this |
| --- | --- |
| It says **No folders found** | Your pages may have no `<title>`. Try `--include-untitled`, or point it at the right folder with `--root`. |
| The bar disappeared | Press **H**, or click the little **RIBBON** tab in the top right. |
| The keyboard shortcuts do nothing | Use the server version. Browsers turn them off when you open the file directly. |
| It shows the wrong folder | Add `--root ~/the/folder/you/want`. Ribbon lists the folders directly inside it. |
| The address is already in use | Ribbon tries the next port by itself. It tells you which one it picked. |
| The Git buttons are greyed out | Start Ribbon on `127.0.0.1` without `--no-git-actions`. Opening the page as a file cannot run Git. |
| **Create a remote** fails | Run `gh auth login`, and check that the repository name is not already taken. |
| **Publish with GitHub Pages** fails | Pages needs a public repo on the free plan. The repository root needs a lowercase, committed, unignored `index.html`. |
| Drift keeps skipping a project | It is **Parked**, or it is not in the active channel. Choose **All**, then press **P** to unpark it. |
| Drift repeats a project | Close the tab to clear the deck, or pick another channel. The deck is remembered per tab. |
| Keep/Park do nothing | Use the server version on `127.0.0.1`. The no-server page cannot save state. |
| You want to reset Drift | Delete `~/.local/state/ribbon/state-<hash>.json`. |
| Ribbon says a `.scratch/` folder is tracked | Remove it with `git rm -r --cached .scratch`, add `.scratch/` to `.gitignore`, then commit. |
| Git says there is nothing to commit | The app was refreshed before the last file change. Close the panel and open it again. |
| You forgot the commands | Run `python3 _ribbon/ribbon.py --help`. |

## All the commands

```bash
python3 _ribbon/ribbon.py                  # start and open the first app
python3 _ribbon/ribbon.py --list           # show the apps and quit
python3 _ribbon/ribbon.py --app 3          # start on folder number 3
python3 _ribbon/ribbon.py --root ~/sites   # use a different folder
python3 _ribbon/ribbon.py --port 9000      # use a different port
python3 _ribbon/ribbon.py --no-open        # don't open a browser
python3 _ribbon/ribbon.py --include-untitled
python3 _ribbon/ribbon.py --write-apps     # refresh the no-server list
python3 _ribbon/ribbon.py --no-git-actions # lights only, no commit/push
python3 _ribbon/ribbon.py --verbose        # show every request
python3 _ribbon/ribbon.py --help           # all options, with examples
```

## For the very curious

The folder has ten small pieces:

```
_ribbon/
  index.html    the no-server page: bar + big window
  boot.js       the tiny check that restores a hidden bar on load
  shell.js      the bar and window used by the no-server page
  apps.js       the list that page uses (made by --write-apps, local only)
  card.js       the contents card: file grid, hidden files, and .gitignore
  card.css      the look of that card
  markdown.css  the look of a rendered Markdown document
  ribbon.py     finds the apps, serves them, and saves state
  ribbon.js     the bar itself, for the server version
  BRIEF.md      the design notes behind Drift, channels, and the Shelf
```

The server does not change your pages. The bar is added only while a page
is being sent to your browser. Git actions do change the repository, but
only after you press a button and confirm what will be included. Drift state
is written to the state file described above, never into an app folder.

### Checking the code

The JavaScript and the styles follow the 37signals house style, enforced
by ESLint and Stylelint. Install the tools once, then run the checker:

```bash
cd _ribbon
npm install
npm run lint
```
