---
description: Extract app discovery and card payloads into discover.py
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
  write the reason to `.scratch/split/BLOCKED-06-discover` and stop. Do not
  improvise, do not delete a test, and do not weaken the check.
- Verify with `python3 -c "import ribbon"` and `npm run check`. Run the full
  check at most twice.

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
