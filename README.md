# Ribbon

Ribbon is a little bar at the top of your screen. It lets you jump between
all the websites you made, without typing long addresses.

```
┌──────────────────────────────────────────────────────────────────────┐
│ ● 04 / 11  Beam Library ▾      ‹ Back  › Next  ⤨ Random  ↻    ✕     │
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

## What are the two little lights?

They are about **Git**. Git is a tool grown-ups use to save and back up
versions of their work.

- **Left light** — green means this app is saved in Git. Dark means it is
  not.
- **Right light** — green means everything is backed up. Yellow means
  there are changes that are not saved yet. Red means there are saved
  changes that have not been sent to the internet. Dark means there is no
  Git here.

Hover over the lights to read exactly what is going on.

## If something goes wrong

| Problem | Try this |
| --- | --- |
| It says **No apps found** | Your pages may have no `<title>`. Try `--include-untitled`, or point it at the right folder with `--root`. |
| The bar disappeared | Press **H**, or click the little **RIBBON** tab in the top right. |
| The keyboard shortcuts do nothing | Use the server version. Browsers turn them off when you open the file directly. |
| It shows the wrong folder | Add `--root ~/the/folder/you/want`. |
| The address is already in use | Ribbon tries the next port by itself. It tells you which one it picked. |
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

Nothing on your disk is changed when the server runs. The bar is added to
pages only while they are being sent to your browser.
