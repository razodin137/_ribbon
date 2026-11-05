---
description: Extract delete planning and removal into remove.py
---

You are performing one extraction in /home/mrjohn/Work/_ribbon. Do exactly this
task and nothing else. Ranges below are anchors, not line numbers: cut from the
line containing the first anchor up to but not including the line containing the
second. Recompute them in the current files; do not trust any snapshot. Match
the surrounding Python style.

## Task

Create `remove.py` for delete planning and removal.

## Cut

- `ribbon.py`: from `def delete_plan` up to `PAGE_OFFSET_CSS`

## Move

`delete_plan`, `remove_directory`.

## Depends on

`git_repo` for `_action_error` and `_action_ok`, `state` for `load_state`,
`save_state` and `STATE_LOCK`, `discover` for the cache reset.

## Gotchas

- Keep the function-local `from git_actions import _run_command`. Importing the
  write module at load time re-creates the cycle.
- It runs `rm -rf --` as the literal command shown in the UI, then checks
  `os.path.lexists`. Keep both.
- Re-export with an explicit list from `ribbon.py`.

## Done when

`npm run check` passes and a delete still reports the same command string.
