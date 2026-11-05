---
description: Extract app discovery and card payloads into discover.py
---

You are performing one extraction in /home/mrjohn/Work/_ribbon. Do exactly this
task and nothing else. Ranges below are anchors, not line numbers: cut from the
line containing the first anchor up to but not including the line containing the
second. Recompute them in the current files; do not trust any snapshot. Match
the surrounding Python style.

## Task

Create `discover.py` for app discovery and card payloads.

## Cut

- `ribbon.py`: from `_cache` up to `def clean_title`
- `ribbon.py`: from `def markdown_info` up to `class _PooledLock`
- `ribbon.py`: from `def page_card_info` up to `def delete_plan`

## Move

`_cache`, `markdown_info`, `project_info`, `page_card_info`, `directory_app`,
`discover`.

## Depends on

`config`, `content`, `scan`, `git_repo` for `git_status`.

## Gotchas

- `_cache` is mutated by `discover()` and cleared by the delete path. Keep it
  module-level in one place and expose a `clear_cache()` instead of letting
  `remove.py` reach into the dict.
- `discover()` creates one `ThreadPoolExecutor` per call. Keep that shape; do
  not share the pool.
- Re-export with an explicit list from `ribbon.py`.

## Done when

`npm run check` passes and the delete path still clears the discovery cache.
