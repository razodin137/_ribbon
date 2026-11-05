#!/usr/bin/env python3
"""
Ribbon — browse a folder of standalone HTML apps with a floating top banner.

Run this from anywhere:

    python3 ribbon.py

Ribbon finds the folder that holds your apps, serves it on a local address,
adds the ribbon bar to every page, and opens the first app. Nothing on disk
is changed.

Handy first commands:

    python3 ribbon.py --list          see what it found
    python3 ribbon.py --help          every option, with examples
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shlex
import shutil
import socket
import threading
import webbrowser
import zlib
from functools import partial
from html import escape
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs, quote, unquote, urlsplit

import assets
from cli import main
from git_repo import (
    DEFAULT_GITIGNORE,
    GIT_CACHE,
    GIT_CACHE_SECONDS,
    GIT_ENV_STRIP,
    GIT_LIGHT_SECONDS,
    GIT_LOCKS,
    GIT_STATUS_LOCKS,
    GIT_STATUS_WORKERS,
    GITIGNORE_PREVIEW_CHARS,
    LARGE_FILE_BYTES,
    MAX_ACTION_OUTPUT,
    MAX_DETAIL_FILES,
    SCRATCH_DIRS,
    SECRET_NAMES,
    SECRET_SUFFIXES,
    _LockPool,
    _PooledLock,
    _action_error,
    _action_ok,
    _git,
    _git_env,
    _git_ignored,
    _git_in_head,
    _git_status_lock,
    _git_text,
    _git_tracked,
    _index_case_mismatch,
    _plain_gitignore_covers,
    _repo_root,
    file_warnings,
    find_scratch_dirs,
    git_detail,
    git_status,
    gitignore_requirement,
    list_folder_files,
    pages_detail,
    pages_requirement,
    pages_state,
    parse_status_files,
    read_git_status,
    repo_lock,
    scratch_warnings,
)
from config import (
    APP_DIR,
    CARD_ROUTE,
    DEFAULT_TYPE_COLOR,
    GZIP_MIN_BYTES,
    HANDLER_TIMEOUT,
    HTML_SUFFIXES,
    IMAGE_SUFFIXES,
    MARKDOWN_SUFFIXES,
    MAX_README_CHARS,
    PREFERRED_HTML,
    PREFERRED_MARKDOWN,
    README_COMMIT_MESSAGE,
    README_NAMES,
    STATIC_ASSETS,
    TYPE_COLORS,
    VERSION,
    type_color,
)
from content import (
    META_DESCRIPTION_FIRST_RE,
    META_DESCRIPTION_RE,
    TITLE_RE,
    _page_meta,
    choose_html,
    choose_markdown,
    clean_markdown,
    clean_title,
    extract_description,
    extract_title,
    fallback_title,
    find_readme,
    markdown_summary,
    markdown_title,
    page_meta,
    project_kind,
    read_markdown,
    read_readme,
    readme_state,
    readme_summary,
)
from discover import (
    clear_cache,
    directory_app,
    discover,
    markdown_info,
    page_card_info,
    project_info,
)
from inject import (
    RAW_TEXT_TAGS,
    html_injection_points,
    inject_html,
    iter_html_tags,
)
from markdown_render import markdown_view_html
from remove import delete_plan, remove_directory
from roots import (
    SYSTEM_ROOTS,
    child_dirs,
    default_root,
    is_container,
    is_safe_default_root,
)
from scan import (
    SKIP_DIRS,
    TREE_MAX_ENTRIES,
    TREE_SKIP_DESCENT,
    _git_check_ignored,
    _gitignore_patterns,
    _gitignore_source,
    _likely_secret,
    _plain_ignored,
    folder_entries,
    folder_info,
    folder_stats,
    folder_tree,
)
from server import (
    RibbonHandler,
    RibbonHTTPServer,
    RibbonHTTPServerV6,
    contained_target,
    hidden_path,
    url_host,
)
from state import (
    STATE_DIR_NAME,
    STATE_LOCK,
    STATE_VERSION,
    apply_signal,
    empty_state,
    load_state,
    public_state,
    save_state,
    state_home,
    state_path,
)


if __name__ == "__main__":
    main()
