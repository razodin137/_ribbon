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
scroll up.

## Find any app fast

Click the app's name in the bar, or press **`/`**, to open the app menu.

- **Search** — start typing to filter the list.
- **Enter** — open the first match.
- **Escape** — close the menu.

## Favorites

The star at the top of the app menu saves the app you are looking at.
Stars next to every row do the same thing. Favorites get their own
section at the top of the menu, so your everyday apps are always one
click away. Click a filled star again to remove it.

The browser remembers your favorites. They work in both the server
version and the no-server version.

## Add a new app

1. Make a folder inside your apps folder.
2. Put a file called `index.html` inside it.
3. Give the page a name, like this:

```html
<title>My Cool App</title>
```

If Ribbon is already running, just refresh. It finds new folders by itself.

Pages without a `<title>` are skipped on purpose. That keeps login pages
and other private things out of the list. If you really want them:

```bash
python3 _ribbon/ribbon.py --include-untitled
```

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
| Right | Green: backed up. Yellow: not pushed. Red: commits waiting. Dark: no remote. | Push or create a remote. |

Hover over a light to read exactly what is going on.

Clicking a light opens a small panel. It shows the repository folder,
branch, changed files, and any warnings. Nothing happens until you press
the button in that panel.

- **Create a repository** makes `.git`, adds a starter `.gitignore`
  (unless you uncheck it), and makes the first commit.
- **Commit** stages every changed file and saves it with your message.
- **Push** sends your commits to the remote.
- **Create a remote** uses the GitHub CLI (`gh`) to make a **private**
  repository and push. You can choose Public instead. Run
  `gh auth login` once before using this.

Two safety notes:

- The panel lists the files that will be committed. Look for `.env`
  files, keys, or anything over 5 MB before pressing the button.
- A nested app shares its parent's repository. The panel shows the real
  repository folder and branch, so you know what you are saving.

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

The folder has four small pieces:

```
_ribbon/
  index.html  the no-server page: bar + big window
  apps.js     the list that page uses (made by --write-apps)
  ribbon.py   finds the apps, serves them, and adds the bar
  ribbon.js   the bar itself
```

The server does not change your pages. The bar is added only while a page
is being sent to your browser. Git actions do change the repository, but
only after you press a button and confirm what will be included.
