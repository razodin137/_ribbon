---
description: Extract the HTTP handler and server classes into server.py
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
  write the reason to `.scratch/split/BLOCKED-12-server` and stop. Do not
  improvise, do not delete a test, and do not weaken the check.
- Verify with `python3 -c "import ribbon"` and `npm run check`. Run the full
  check at most twice.

You are performing one extraction in /home/mrjohn/Work/_ribbon. Do exactly this
task and nothing else. Ranges below are anchors, not line numbers: cut from the
line containing the first anchor up to but not including the line containing the
second. Recompute them in the current files; do not trust any snapshot. Match
the surrounding Python style.

## Task

Create `server.py` for the HTTP handler and server classes. This is the largest
cut; do it alone.

## Cut

- `ribbon.py`: from `def hidden_path` up to `def build_parser`

## Move

`hidden_path`, `contained_target`, `RibbonHandler`, `RibbonHTTPServer`,
`RibbonHTTPServerV6`, `url_host`.

## Depends on

`config`, `content`, `scan`, `discover`, `git_repo`, `git_actions`, `remove`,
`state`, `inject`, `assets`, `shell` — this is the composition root.

## Gotchas

- `hidden_path` decodes before testing for dot entries because
  `translate_path()` decodes too, so a percent-encoded dot still 404s.
  `test/hidden-paths.test.js` runs a live server against it.
- `contained_target` refuses a symlink that leaves the root. Both GET and HEAD
  go through it.
- `root`, `token`, `write_enabled`, `include_untitled` and `allowed_origins` are
  class attributes set by `main()`. After extraction `cli.py` imports the class
  and assigns to it; same object, so this keeps working.
- The POST path lazily imports `_repo_root`, `git_detail` and `run_git_action`
  from `git_actions`. `git_detail` now comes from `git_repo`; split that import.
- Re-export with an explicit list from `ribbon.py`.

## Done when

`npm run check` passes, including the three live-server tests.
