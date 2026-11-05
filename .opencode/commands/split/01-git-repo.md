---
description: Extract the Git read layer into git_repo.py
---

You are performing one extraction in /home/mrjohn/Work/_ribbon. Do exactly this
task and nothing else. Ranges below are anchors, not line numbers: cut from the
line containing the first anchor up to but not including the line containing the
second. Recompute them in the current files; do not trust any snapshot. Match
the surrounding Python style. There is no Python linter configured; `npm run
check` covers eslint, stylelint, node:test and the embed check.

## Task

Create `git_repo.py` and move the Git read layer into it.

## Cut

- `ribbon.py`: from `class _PooledLock` up to `def page_card_info`
- `git_actions.py`: from `def _repo_root` up to `def _identity_problem`
- `git_actions.py`: from `def _index_case_mismatch` up to `def git_create_pages_entry`

## Move

`_PooledLock`, `_LockPool`, `GIT_CACHE`, `GIT_STATUS_LOCKS`, `GIT_CACHE_SECONDS`,
`GIT_STATUS_WORKERS`, `GIT_LIGHT_SECONDS`, `GIT_LOCKS`, `repo_lock`,
`GIT_ENV_STRIP`, `_git_env`, `_git`, `_git_text`, `read_git_status`,
`_git_status_lock`, `git_status`, `list_folder_files`, `parse_status_files`,
`_git_ignored`, `_git_tracked`, `_git_in_head`, `find_scratch_dirs`,
`_plain_gitignore_covers`, `scratch_warnings`, `gitignore_requirement`,
`file_warnings`, `git_detail`, `_action_error`, `_action_ok`.

From `git_actions.py`: `_repo_root`, `_index_case_mismatch`, `pages_state`,
`pages_requirement`, `pages_detail`.

Constants to move in: `DEFAULT_GITIGNORE`, `SCRATCH_DIRS`, `SECRET_NAMES`,
`SECRET_SUFFIXES`, `LARGE_FILE_BYTES`, `MAX_ACTION_OUTPUT`, `MAX_DETAIL_FILES`,
`GITIGNORE_PREVIEW_CHARS`.

## Why

The pages helpers only read `.git/config` and the worktree. Moving them down
makes `git_actions` depend on `git_repo` in one direction. Without them the
cycle merely flips instead of breaking.

## Do not move

`SKIP_DIRS`, `TREE_MAX_ENTRIES`, `TREE_SKIP_DESCENT` and `_likely_secret`
belong to the scan layer. `readme_state` and `read_readme` stay where they are.

## Ribbon shim

Re-export every moved name from `ribbon.py` with an explicit list. Never
`import *`.

## Gotchas

- Delete the function-local `from git_actions import pages_detail` inside
  `git_detail`; it becomes a plain call.
- `repo_lock` is used by the handler's Git POST path. A missing re-export will
  not fail `npm test`; grep for it.
- Do not move `SKIP_DIRS`; `folder_tree` uses it and it belongs to the scan
  layer.

## Done when

`npm run check` passes and `grep 'from git_actions' ribbon.py` shows only
write-path imports.
