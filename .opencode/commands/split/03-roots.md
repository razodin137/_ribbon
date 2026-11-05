---
description: Extract root auto-detection into roots.py
---

You are performing one extraction in /home/mrjohn/Work/_ribbon. Do exactly this
task and nothing else. Ranges below are anchors, not line numbers: cut from the
line containing the first anchor up to but not including the line containing the
second. Recompute them in the current files; do not trust any snapshot. Match
the surrounding Python style.

## Task

Create `roots.py` for root auto-detection and its safety guard.

## Cut

- `ribbon.py`: from `def child_dirs` up to `TITLE_RE`

## Move

`child_dirs`, `is_container`, `SYSTEM_ROOTS`, `is_safe_default_root`,
`default_root`.

## Depends on

`config` only.

## Gotchas

- `test/default-root.test.js` pins four climb cases and two layouts that must
  resolve. Change location, not behaviour.
- `main()` calls `default_root()`, so the re-export must exist before
  `npm run check`.
- Re-export with an explicit list from `ribbon.py`.

## Done when

`npm run check` passes, including `default-root.test.js`.
