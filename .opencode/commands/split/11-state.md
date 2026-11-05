---
description: Extract the per-root state file into state.py
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
  write the reason to `.scratch/split/BLOCKED-11-state` and stop. Do not
  improvise, do not delete a test, and do not weaken the check.
- Verify with `python3 -c "import ribbon"` and `npm run check`. Run the full
  check at most twice.

You are performing one extraction in /home/mrjohn/Work/_ribbon. Do exactly this
task and nothing else. Ranges below are anchors, not line numbers: cut from the
line containing the first anchor up to but not including the line containing the
second. Recompute them in the current files; do not trust any snapshot. Match
the surrounding Python style.

## Task

Create `state.py` for the per-root state file.

## Cut

- `ribbon.py`: from `def state_home` up to `def hidden_path`

## Move

`STATE_LOCK`, `STATE_VERSION`, `STATE_DIR_NAME`, `state_home`, `state_path`,
`empty_state`, `load_state`, `save_state`, `public_state`, `apply_signal`.

## Do not move

`STATE_LABELS` is display text and belongs with `cli.state_label`.

## Gotchas

- `save_state` writes a pid-and-thread-named temp file opened `0600`, then
  `os.replace`s it, and unlinks on failure. Keep the mode and the unlink; that
  is a documented privacy guarantee.
- `remove.py` does not exist yet; it is cut after this step and imports
  `STATE_LOCK`, `load_state` and `save_state` from here at module level. Never
  import `ribbon` from `state`: under `python3 ribbon.py` the server runs as
  `__main__`, so that import loads a second copy of the module and the lock
  stops being shared.
- Re-export with an explicit list from `ribbon.py`.

## Done when

`npm run check` passes and the state file is still created `0600`.
