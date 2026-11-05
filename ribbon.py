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

The code lives in the modules beside this file. The names below are
re-exported so `import ribbon` keeps working for the tests and for older
imports; edit the defining module, not this launcher.
"""

from __future__ import annotations

from cli import main
from config import APP_DIR
from git_repo import _git_env, _git_text, read_git_status
from inject import inject_html
from roots import default_root, is_safe_default_root
from scan import _git_check_ignored

__all__ = [
    "APP_DIR",
    "main",
    "default_root",
    "is_safe_default_root",
    "read_git_status",
    "inject_html",
    "_git_check_ignored",
    "_git_env",
    "_git_text",
]


if __name__ == "__main__":
    main()
