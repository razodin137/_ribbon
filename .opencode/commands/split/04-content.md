---
description: Extract page metadata and Markdown summaries into content.py
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
  write the reason to `.scratch/split/BLOCKED-04-content` and stop. Do not
  improvise, do not delete a test, and do not weaken the check.
- Verify with `python3 -c "import ribbon"` and `npm run check`. Run the full
  check at most twice.

You are performing one extraction in /home/mrjohn/Work/_ribbon. Do exactly this
task and nothing else. Ranges below are anchors, not line numbers: cut from the
line containing the first anchor up to but not including the line containing the
second. Recompute them in the current files; do not trust any snapshot. Match
the surrounding Python style.

## Task

Create `content.py` for page metadata and Markdown summaries.

## Cut

- `ribbon.py`: from `TITLE_RE` up to `RAW_TEXT_TAGS`
- `ribbon.py`: from `def clean_title` up to `def folder_entries`

## Move

`TITLE_RE`, `META_DESCRIPTION_RE`, `META_DESCRIPTION_FIRST_RE`, `clean_title`,
`fallback_title`, `_page_meta`, `page_meta`, `extract_title`,
`extract_description`, `choose_html`, `find_readme`, `read_readme`,
`readme_state`, `clean_markdown`, `choose_markdown`, `read_markdown`,
`markdown_summary`, `readme_summary`, `markdown_title`, `project_kind`.

## Do not move

`_cache` sits between the two ranges and belongs to `discover.py`.

## Depends on

`config`, `markdown_render`.

## Gotchas

- `git_repo.git_detail` calls `readme_state`, so `git_repo` imports `content`.
  Never add the reverse edge.
- `_page_meta` is `lru_cache`d process-wide. Keep the decorator with the
  function.
- Re-export with an explicit list from `ribbon.py`.

## Done when

`npm run check` passes and `content.py` imports nothing from `git_repo`, `scan`
or `discover`.
