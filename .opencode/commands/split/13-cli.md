---
description: Extract argument parsing, printing and main into cli.py
---

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
