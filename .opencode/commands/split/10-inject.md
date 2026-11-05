---
description: Extract the tag scanner and injection into inject.py
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
  write the reason to `.scratch/split/BLOCKED-10-inject` and stop. Do not
  improvise, do not delete a test, and do not weaken the check.
- Verify with `python3 -c "import ribbon"` and `npm run check`. Run the full
  check at most twice.

You are performing one extraction in /home/mrjohn/Work/_ribbon. Do exactly this
task and nothing else. Ranges below are anchors, not line numbers: cut from the
line containing the first anchor up to but not including the line containing the
second. Recompute them in the current files; do not trust any snapshot. Match
the surrounding Python style.

## Task

Create `inject.py` for the byte-level HTML tag scanner and injection.

## Cut

- `ribbon.py`: from `RAW_TEXT_TAGS` up to `BOOT_SCRIPT`
- `ribbon.py`: from `def iter_html_tags` up to `def state_home`

## Move

`RAW_TEXT_TAGS`, `iter_html_tags`, `html_injection_points`, `inject_html`.

## Depends on

`shell` for `BOOT_SCRIPT` and `VIEW_TRANSITION_CSS`, `assets` for
`bar_shell_html` and `asset_url`.

## Gotchas

- Keep the idempotency guard on `data-ribbon-host` and `/__ribbon/ribbon.js`
  byte-for-byte. It is a raw substring test over the whole document by design.
- Do not replace `iter_html_tags` with a regex. `test/injection.test.js` pins
  comments, CDATA, script strings, fake head and body closes, and a quoted `>`
  inside an attribute.
- The stylesheet is inserted before the body offsets are used, so both shift by
  `len(style)`. Preserve the ordering.
- Re-export with an explicit list from `ribbon.py`.

## Done when

`npm run check` passes and `injection.test.js` is green.
