---
description: Extract the per-root state file into state.py
---

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
- `remove.py` uses `STATE_LOCK` directly. Re-export it or update `remove.py` in
  the same pass.
- Re-export with an explicit list from `ribbon.py`.

## Done when

`npm run check` passes and the state file is still created `0600`.
