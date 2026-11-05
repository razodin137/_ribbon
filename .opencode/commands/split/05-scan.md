---
description: Extract folder tree, stats and gitignore engine into scan.py
---

You are performing one extraction in /home/mrjohn/Work/_ribbon. Do exactly this
task and nothing else. Ranges below are anchors, not line numbers: cut from the
line containing the first anchor up to but not including the line containing the
second. Recompute them in the current files; do not trust any snapshot. Match
the surrounding Python style.

## Task

Create `scan.py` for the folder tree, stats and gitignore engine.

## Cut

- `ribbon.py`: from `def folder_entries` up to `TYPE_COLORS`

## Move

`folder_entries`, `_likely_secret`, `_gitignore_patterns`, `_plain_ignored`,
`_git_check_ignored`, `_gitignore_source`, `folder_tree`, `folder_stats`,
`folder_info`.

Also move `SKIP_DIRS`, `TREE_MAX_ENTRIES` and `TREE_SKIP_DESCENT` out of
`config.py` into here.

## Depends on

`config`, `content` for `fallback_title`, `git_repo` for `_git_text` and
`_git_env`.

## Gotchas

- `folder_tree` shells out through `_git_check_ignored` on the request path,
  bounded by `TREE_MAX_ENTRIES`. Do not change when that call happens.
- `markdown_info` and `project_info` sit at the end of this range but belong to
  `discover.py`. Leave them for the next step.
- Re-export with an explicit list from `ribbon.py`.

## Done when

`npm run check` passes and no module below `scan` imports it.
