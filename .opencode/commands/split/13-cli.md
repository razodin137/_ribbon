---
description: Extract argument parsing, printing and main into cli.py
---

## Guardrails

Read these first. They beat anything below that contradicts them.

- This repository is the only source of truth. Do not read or write anything
  under `~/.local/share/opencode`, `~/.config/opencode`, `/tmp`, `~/Projects`
  or any other Ribbon checkout. There is no pre-split original to go looking
  for: the current files are correct, and every earlier step is committed.
- Never run `git stash`, `git checkout`, `git reset`, `git restore`,
  `git clean`, or `cp` over a tracked file. Use `git diff` and
  `git show HEAD:<path>` if you need history.
- Never replace a whole file. Edit inside the ranges named below, and only
  there. `ribbon.py` must never shrink to a fragment.
- Touch only the files this task names. Leave `AGENTS.md`, `README.md`,
  `package.json`, `.opencode/`, `scripts/` and the other steps' files alone.
- Do not print whole files. Use `grep -n` and `sed -n`, and keep output short.
- If an anchor is missing, appears twice, or the move would change behaviour,
  write the reason to `.scratch/split/BLOCKED-13-cli` and stop. Do not
  improvise, do not delete a test, and do not weaken the check.
- Verify with `python3 -c "import ribbon"` and `npm run check`. Run the full
  check at most twice.

You are performing one extraction in /home/mrjohn/Work/_ribbon. Do exactly this
task and nothing else. Ranges below are anchors, not line numbers: cut from the
line containing the first anchor up to but not including the line containing the
second. Recompute them in the current files; do not trust any snapshot. Match
the surrounding Python style.

## Task

Create `cli.py` for argument parsing, printing and `main()`.

## Cut

- `ribbon.py`: from `def build_parser` to the end of the file

## Move

`build_parser`, `state_label`, `print_apps`, `print_no_apps`, `main`, and
`STATE_LABELS`.

## Leave behind

`ribbon.py` keeps the shebang, the module docstring, `from cli import main`, and
`if __name__ == "__main__": main()`. `python3 ribbon.py` must still run.

## Gotchas

- `main()` sets `DEV_ASSETS`, which lives in `assets.py` after that extraction.
  Use `assets.DEV_ASSETS = args.dev`; a `global` statement cannot cross modules.
- `main()` mutates `RibbonHandler` class attributes. Import the class, then
  assign; do not assign to a copy.
- `main()` prints the unauthenticated-bind warning before the banner for any
  host other than `127.0.0.1`, `localhost` or `::1`. `test/host-warning.test.js`
  pins it.

## Done when

`python3 ribbon.py --list` still prints, and `npm run check` passes.
