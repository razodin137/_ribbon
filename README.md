# Ribbon

Ribbon is a little bar at the top of your screen. It lets you jump between
all the websites you made, without typing long addresses.

```
┌──────────────────────────────────────────────────────────────────────┐
│ ●●● 04 / 11  Beam Library ▾    ‹ Back  › Next  ⤨ Random  ↻    ✕     │
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

Ribbon is good at finding your apps. It looks in the folder that contains
`_ribbon`. If there are no apps there, it looks one folder up.
If it guesses wrong, you can tell it where to look:

```bash
python3 _ribbon/ribbon.py --root ~/my-websites
```

## What the buttons do

| Button | What it does | Keyboard |
| --- | --- | --- |
| `Beam Library ▾` | Open the app menu: search and jump to any app | `/` |
| `‹ Back` | Go to the app before this one | `[` |
| `› Next` | Go to the app after this one | `]` |
| `⤨ Random` | Surprise me — jump to any app | `R` |
| `↻` | Reload the app you are looking at | `Shift+R` |
| `✕` | Hide the bar | `H` |

Back and Next wrap around. When you hide the bar, a tiny **RIBBON** tab
appears in the top right corner. Click it — or press **H** — to bring the
bar back.

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

Pages without a `<title>` are skipped on purpose. That keeps login pages
and other private things out of the list. If you really want them:

```bash
python3 _ribbon/ribbon.py --include-untitled
```

## Scripts, tools, and notes

Folders that are not websites still show up. Ribbon makes a project card
for any folder with a script or a build file such as `package.json`,
`pyproject.toml`, `Cargo.toml`, or a `Makefile`.

The card shows the folder name, the first paragraph of the README, the
kind of project, its files, and a suggested command to run it. It uses
the same Git lights as everything else. Nothing is written into the
folder, and you never have to add an `index.html` just to see it.

Folders with only a Markdown file open as a rendered document instead of
a card. Ribbon looks for `README.md`, `README.markdown`, `index.md`, or
any other `.md` file in the folder. Links and pictures inside the
document keep working, and you can jump back out with the bar.

The app menu shows a small badge for every app: `HTML` for a web page,
`MD` for Markdown, and codes such as `PY`, `JS`, `RS`, or `SH` for
project folders. Hover over the badge to see the full type.

## Check what it found

Want to see the list without opening a browser? Run:

```bash
python3 _ribbon/ribbon.py --list
```

It prints every app it can see, with its folder and whether it is backed
up. To start on a certain app, add its number:

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

One catch: when you open the file directly, some things are turned off by
the browser — the keyboard shortcuts and the scroll-to-hide. Some browsers
also keep favorites in a separate place, or forget them altogether. If you
want everything to work the same way every time, use the server version at
the top of this page.

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
| It says **No apps found** | Your pages may have no `<title>`. Try `--include-untitled`, or point it at the right folder with `--root`. |
| The bar disappeared | Press **H**, or click the little **RIBBON** tab in the top right. |
| The keyboard shortcuts do nothing | Use the server version. Browsers turn them off when you open the file directly. |
| It shows the wrong folder | Add `--root ~/the/folder/you/want`. |
| The address is already in use | Ribbon tries the next port by itself. It tells you which one it picked. |
| The Git buttons are greyed out | Start Ribbon on `127.0.0.1` without `--no-git-actions`. Opening the page as a file cannot run Git. |
| **Create a remote** fails | Run `gh auth login`, and check that the repository name is not already taken. |
| **Publish with GitHub Pages** fails | Pages needs a public repo on the free plan. The repository root needs a lowercase, committed, unignored `index.html`. |
| Ribbon says a `.scratch/` folder is tracked | Remove it with `git rm -r --cached .scratch`, add `.scratch/` to `.gitignore`, then commit. |
| Git says there is nothing to commit | The app was refreshed before the last file change. Close the panel and open it again. |
| You forgot the commands | Run `python3 _ribbon/ribbon.py --help`. |

## All the commands

```bash
python3 _ribbon/ribbon.py                  # start and open the first app
python3 _ribbon/ribbon.py --list           # show the apps and quit
python3 _ribbon/ribbon.py --app 3          # start on app number 3
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

The folder has nine small pieces:

```
_ribbon/
  index.html    the no-server page: bar + big window
  boot.js       the tiny check that restores a hidden bar on load
  shell.js      the bar and window used by the no-server page
  apps.js       the list that page uses (made by --write-apps)
  card.js       the project card shown for scripts and tools
  card.css      the look of that card
  markdown.css  the look of a rendered Markdown document
  ribbon.py     finds the apps, serves them, and adds the bar
  ribbon.js     the bar itself, for the server version
```

The server does not change your pages. The bar is added only while a page
is being sent to your browser. Git actions do change the repository, but
only after you press a button and confirm what will be included.

### Checking the code

The JavaScript and the styles follow the 37signals house style, enforced
by ESLint and Stylelint. Install the tools once, then run the checker:

```bash
cd _ribbon
npm install
npm run lint
```
