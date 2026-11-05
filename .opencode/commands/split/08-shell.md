---
description: Extract the pre-script page shell into shell.py
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
  write the reason to `.scratch/split/BLOCKED-08-shell` and stop. Do not
  improvise, do not delete a test, and do not weaken the check.
- Verify with `python3 -c "import ribbon"` and `npm run check`. Run the full
  check at most twice.

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
