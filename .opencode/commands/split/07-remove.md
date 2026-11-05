---
description: Extract delete planning and removal into remove.py
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
  write the reason to `.scratch/split/BLOCKED-07-remove` and stop. Do not
  improvise, do not delete a test, and do not weaken the check.
- Verify with `python3 -c "import ribbon"` and `npm run check`. Run the full
  check at most twice.

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
