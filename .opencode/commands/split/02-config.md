---
description: Extract module-level constants into config.py
---

You are performing one extraction in /home/mrjohn/Work/_ribbon. Do exactly this
task and nothing else. Ranges below are anchors, not line numbers: cut from the
line containing the first anchor up to but not including the line containing the
second. Recompute them in the current files; do not trust any snapshot. Match
the surrounding Python style.

## Task

Create `config.py` holding module-level constants only.

## Cut

- `ribbon.py`: from `APP_DIR` up to `def child_dirs`
- `ribbon.py`: from `TYPE_COLORS` up to `def markdown_info`

## Move

Every module-level assignment in the first range, plus `TYPE_COLORS`,
`DEFAULT_TYPE_COLOR` and `type_color()`.

## Do not move

`STATE_LOCK` goes to state, `_cache` to discover, `_disk_asset_cache` and
`_asset_version_cache` to assets, `BOOT_SCRIPT` to shell, `RAW_TEXT_TAGS` to
inject, the `GIT_CACHE` family to `git_repo`.

## Gotchas

- `APP_DIR` uses `Path(__file__).resolve().parent`. Every module sits beside
  `ribbon.py`, so it still resolves; do not change it.
- Run the `git_repo` extraction first, or the Git constants have no home.
- Re-export with an explicit list, never `import *`.

## Done when

`npm run check` passes and `grep '^APP_DIR' ribbon.py` returns only a re-export.
