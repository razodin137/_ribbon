---
description: Extract the pre-script page shell into shell.py
---

You are performing one extraction in /home/mrjohn/Work/_ribbon. Do exactly this
task and nothing else. Ranges below are anchors, not line numbers: cut from the
line containing the first anchor up to but not including the line containing the
second. Recompute them in the current files; do not trust any snapshot. Match
the surrounding Python style.

## Task

Create `shell.py` holding the pre-script page shell.

## Cut

- `ribbon.py`: from `BOOT_SCRIPT` up to `def clean_title`
- `ribbon.py`: from `PAGE_OFFSET_CSS` up to `_EMBEDDED_ASSETS_B64`

## Move

`BOOT_SCRIPT`, `PAGE_OFFSET_CSS`, `BAR_HOST_STYLE`, `VIEW_TRANSITION_CSS`,
`BAR_MARKUP`.

## Depends on

`config.BAR_HEIGHT`.

## Gotchas

- Five tests read `ribbon.py` as text and will fail: `bar-duplication` for
  `BAR_MARKUP`, `boot-transition` and `storage-contract` for `BOOT_SCRIPT`,
  `page-offset` for `PAGE_OFFSET_CSS`, `view-transition` for
  `VIEW_TRANSITION_CSS`. Add a `test/source.js` that concatenates the modules,
  or repoint each test at `shell.py`.
- `BAR_MARKUP` is a join over many string literals parsed before any script
  runs. Keep it byte-identical.
- This is the zero-risk cut. Good warm-up if any other extraction is blocked.

## Done when

`npm run check` passes, including the five source-reading tests.
