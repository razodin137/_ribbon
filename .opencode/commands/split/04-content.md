---
description: Extract page metadata and Markdown summaries into content.py
---

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
