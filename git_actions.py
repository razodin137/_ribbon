"""Git actions for Ribbon.

The write path lives here: init, commit, push, GitHub remote creation, and
GitHub Pages. It reads the repository through `git_repo.py`; this module is
imported only when the bar asks for an action.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from html import escape
from pathlib import Path
from urllib.parse import quote

from config import MAX_README_CHARS, README_COMMIT_MESSAGE
from content import choose_html, find_readme
from git_repo import (
    DEFAULT_GITIGNORE,
    _action_error,
    _action_ok,
    _git,
    _git_env,
    _git_ignored,
    _git_in_head,
    _git_text,
    _index_case_mismatch,
    _repo_root,
    gitignore_requirement,
    pages_requirement,
    read_git_status,
)


def _run_git_step(path: Path, args: list[str], timeout: float) -> tuple[bool, str]:
    try:
        proc = _git(path, args, timeout)
    except subprocess.TimeoutExpired:
        return False, "Git took too long and was stopped."
    except OSError as exc:
        return False, str(exc)
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part).strip()
    return proc.returncode == 0, output


def _run_command(cmd: list[str], cwd: Path, timeout: float) -> tuple[bool, str]:
    env = _git_env()
    env["GH_PROMPT_DISABLED"] = "1"
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "The command took too long and was stopped."
    except OSError as exc:
        return False, str(exc)
    output = "\n".join(part for part in (proc.stdout, proc.stderr) if part).strip()
    return proc.returncode == 0, output


def _identity_problem(root: Path) -> str | None:
    name = _git_text(root, ["config", "user.name"])
    email = _git_text(root, ["config", "user.email"])
    if name and email:
        return None
    return (
        "Git needs your name and email first. Run:\n"
        '  git config --global user.name "Your Name"\n'
        '  git config --global user.email "you@example.com"'
    )


def _staged_count(root: Path) -> int:
    text = _git_text(root, ["diff", "--cached", "--name-only"])
    return len([line for line in text.splitlines() if line.strip()])


def _clean_message(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return text[:2000] or fallback


def _push_branch(root: Path, status: dict) -> tuple[bool, str]:
    branch = _git_text(root, ["symbolic-ref", "--short", "-q", "HEAD"]) or status.get("branch")
    if not branch or branch == "HEAD":
        return False, "You are not on a branch."

    upstream = _git_text(
        root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]
    )
    if upstream:
        return _run_git_step(root, ["push"], 120)

    remotes = status.get("remotes") or []
    remote = "origin" if "origin" in remotes else (remotes[0] if remotes else "origin")
    return _run_git_step(root, ["push", "-u", remote, branch], 120)


def _add_readme(root: Path, text: object) -> dict:
    """Write a new README.md and commit just that file."""
    content = str(text or "")
    if not content.strip():
        result = _action_ok("")
        result["readme_written"] = False
        return result

    problem = _identity_problem(root)
    if problem:
        return _action_error(problem)

    if len(content) > MAX_README_CHARS:
        return _action_error(
            f"The README is too long. Keep it under {MAX_README_CHARS} characters."
        )
    if not content.endswith("\n"):
        content += "\n"

    existing = find_readme(root)
    if existing:
        if existing.name != "README.md":
            result = _action_ok(f"{existing.name} already exists; left it unchanged.")
            result["readme_written"] = False
            return result
        try:
            current = existing.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return _action_error(f"Could not read README.md: {exc}")
        if current != content:
            result = _action_ok("README.md already exists; left it unchanged.")
            result["readme_written"] = False
            return result
        written = "README.md is already present."
    else:
        try:
            (root / "README.md").write_text(content, encoding="utf-8")
        except OSError as exc:
            return _action_error(f"Could not write README.md: {exc}")
        written = "Wrote README.md."

    ok, stage_output = _run_git_step(root, ["add", "--", "README.md"], 60)
    if not ok:
        return _action_error("Could not stage README.md.", stage_output)

    staged = _git_text(root, ["diff", "--cached", "--name-only", "--", "README.md"])
    if not staged.strip():
        result = _action_ok(written)
        result["readme_written"] = True
        return result

    ok, commit_output = _run_git_step(
        root, ["commit", "-m", README_COMMIT_MESSAGE, "--", "README.md"], 60
    )
    output = "\n".join(part for part in (stage_output, commit_output) if part)
    if not ok:
        return _action_error("Could not commit README.md.", output)
    result = _action_ok(output or "Wrote and committed README.md.")
    result["readme_written"] = True
    return result


def git_init(target: Path, message: str, make_gitignore: bool) -> dict:
    existing = _git_text(target, ["rev-parse", "--show-toplevel"])
    if existing:
        return _action_error(f"This folder is already inside a Git repository: {existing}")
    message = _clean_message(message, "Initial commit")

    ok, output = _run_git_step(target, ["init"], 30)
    if not ok:
        return _action_error("Could not create the repository.", output)

    if make_gitignore and not (target / ".gitignore").exists():
        try:
            (target / ".gitignore").write_text(DEFAULT_GITIGNORE, encoding="utf-8")
        except OSError as exc:
            return _action_error(f"Could not write .gitignore: {exc}", output)

    blocked = gitignore_requirement(target)
    if blocked:
        return _action_error(blocked, output)

    ok, add_output = _run_git_step(target, ["add", "-A"], 60)
    output = "\n".join(part for part in (output, add_output) if part)
    if not ok:
        return _action_error("Could not stage the files.", output)
    if _staged_count(target) == 0:
        return _action_error("There are no files to commit.", output)

    problem = _identity_problem(target)
    if problem:
        return _action_error(problem, output)

    ok, commit_output = _run_git_step(target, ["commit", "-m", message], 60)
    output = "\n".join(part for part in (output, commit_output) if part)
    if not ok:
        return _action_error("The initial commit failed.", output)
    return _action_ok(output or "Created the repository and first commit.")


def git_commit(target: Path, message: str) -> dict:
    status = read_git_status(target)
    if not status.get("repo"):
        return _action_error("This folder is not a Git repository.")
    if status.get("state") == "detached":
        return _action_error("You are on a detached HEAD. Switch to a branch first.")
    if status.get("conflicted"):
        return _action_error("Resolve the merge conflicts before committing.")

    root = _repo_root(target) or target
    message = _clean_message(message, f"Update {target.name}")

    blocked = gitignore_requirement(root)
    if blocked:
        return _action_error(blocked)

    ok, add_output = _run_git_step(root, ["add", "-A"], 60)
    if not ok:
        return _action_error("Could not stage the files.", add_output)
    if _staged_count(root) == 0:
        return _action_error("There are no changes to commit.", add_output)

    problem = _identity_problem(root)
    if problem:
        return _action_error(problem, add_output)

    ok, commit_output = _run_git_step(root, ["commit", "-m", message], 60)
    if not ok:
        return _action_error("The commit failed.", commit_output)
    return _action_ok(commit_output or "Committed the changes.")


def git_push(target: Path) -> dict:
    status = read_git_status(target)
    if not status.get("repo"):
        return _action_error("This folder is not a Git repository.")
    if status.get("state") == "detached":
        return _action_error("You are on a detached HEAD. Switch to a branch first.")
    if not status.get("has_remote"):
        return _action_error("There is no remote. Create one first.")

    root = _repo_root(target) or target
    blocked = gitignore_requirement(root, include_untracked=False)
    if blocked:
        return _action_error(blocked)
    ok, output = _push_branch(root, status)
    if not ok:
        return _action_error("The push failed.", output)
    return _action_ok(output or "Pushed the commits.")


def _github_owner_repo(root: Path) -> tuple[str, str] | None:
    url = _git_text(root, ["remote", "get-url", "origin"])
    match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/*$", url)
    if not match:
        return None
    return match.group(1), match.group(2)


def _github_pages_url(owner: str, name: str) -> str:
    owner_lower = owner.lower()
    name_lower = name.lower()
    if name_lower == f"{owner_lower}.github.io":
        return f"https://{owner_lower}.github.io/"
    return f"https://{owner_lower}.github.io/{name_lower}/"


def git_create_pages_entry(target: Path) -> dict:
    root = _repo_root(target) or target
    if (root / "index.html").is_file():
        return _action_error("This repository already has an index.html.")
    mismatch = _index_case_mismatch(root)
    if mismatch:
        return _action_error(
            "GitHub Pages is case-sensitive and needs a lowercase index.html. "
            f"This repository has {mismatch}. Rename it to index.html first."
        )
    if _git_ignored(root, "index.html"):
        return _action_error(
            "index.html would be ignored by .gitignore. Unignore it before "
            "creating the Pages entry."
        )
    try:
        names = [entry.name for entry in root.iterdir() if entry.is_file()]
    except OSError as exc:
        return _action_error(f"Could not read the repository folder: {exc}")
    entry = choose_html(names)
    if not entry:
        return _action_error(
            "No HTML page was found. Add one first, then create the Pages entry."
        )
    if _git_ignored(root, entry):
        return _action_error(
            f"{entry} is ignored by .gitignore, so the Pages entry could not "
            "open it. Unignore it first."
        )
    href = quote(entry)
    page = (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f'<meta http-equiv="refresh" content="0; url={href}">\n'
        f"<title>{escape(Path(entry).stem)}</title>\n"
        "</head>\n"
        "<body>\n"
        f'<p><a href="{href}">Open {escape(entry)}</a></p>\n'
        "</body>\n"
        "</html>\n"
    )
    try:
        (root / "index.html").write_text(page, encoding="utf-8")
    except OSError as exc:
        return _action_error(f"Could not write index.html: {exc}")
    return _action_ok(f"Created index.html, which opens {entry}.")


def _enable_github_pages(
    root: Path, owner: str, name: str, branch: str
) -> tuple[bool, str]:
    ok, output = _run_command(
        [
            "gh",
            "api",
            "--method",
            "POST",
            f"repos/{owner}/{name}/pages",
            "-f",
            f"source[branch]={branch}",
            "-f",
            "source[path]=/",
        ],
        root,
        90,
    )
    if not ok and ("409" in output or "already" in output.lower()):
        return True, output
    return ok, output


def _set_repo_homepage(
    root: Path, owner: str, name: str, url: str
) -> tuple[bool, str]:
    return _run_command(
        ["gh", "repo", "edit", f"{owner}/{name}", "--homepage", url], root, 60
    )


def git_create_remote(
    target: Path,
    name: str,
    visibility: str,
    description: str = "",
    pages: bool = False,
    readme: str = "",
) -> dict:
    status = read_git_status(target)
    if not status.get("repo"):
        return _action_error("This folder is not a Git repository.")
    if status.get("state") == "detached":
        return _action_error("You are on a detached HEAD. Switch to a branch first.")

    root = _repo_root(target) or target
    if not _git_text(root, ["rev-parse", "HEAD"]):
        return _action_error("Make the first commit before creating a remote.")
    if status.get("has_remote"):
        return _action_error("This repository already has a remote.")
    if not shutil.which("gh"):
        return _action_error(
            "GitHub CLI (gh) is not installed. Install it, or add a remote by hand."
        )

    ok, auth_output = _run_command(["gh", "auth", "status"], root, 20)
    if not ok:
        return _action_error("GitHub CLI is not logged in. Run: gh auth login", auth_output)

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", name):
        return _action_error(
            "Use a GitHub repo name with letters, numbers, dots, dashes, or underscores."
        )
    if visibility not in ("private", "public"):
        return _action_error("Choose private or public visibility.")

    blocked = gitignore_requirement(root, include_untracked=False)
    if blocked:
        return _action_error(blocked)

    prep = _add_readme(root, readme)
    if not prep["ok"]:
        return prep

    flag = "--private" if visibility == "private" else "--public"
    description = str(description or "").strip()[:350]
    cmd = [
        "gh",
        "repo",
        "create",
        name,
        "--source",
        ".",
        "--remote",
        "origin",
        "--push",
        flag,
    ]
    if description:
        cmd.extend(["--description", description])
    ok, output = _run_command(cmd, root, 180)
    if not ok:
        return _action_error("Creating the GitHub repo failed.", output)

    result = _action_ok(output or f"Created {name} and pushed the commits.")
    if prep.get("readme_written"):
        result["readme_written"] = True
    if not pages:
        return result

    owner_repo = _github_owner_repo(root)
    if not owner_repo:
        result["pages_error"] = (
            "The repo was created, but its origin URL could not be read, "
            "so GitHub Pages was not enabled."
        )
        return result
    owner, repo = owner_repo

    branch = status.get("branch") or _git_text(
        root, ["symbolic-ref", "--short", "-q", "HEAD"]
    )
    if not branch:
        result["pages_error"] = (
            "The repo was created, but the branch name could not be found, "
            "so GitHub Pages was not enabled."
        )
        return result

    missing = pages_requirement(root)
    if missing:
        result["pages_error"] = missing
        return result

    ok, pages_output = _enable_github_pages(root, owner, repo, branch)
    if not ok:
        result["pages_error"] = "GitHub Pages could not be enabled.\n" + pages_output
        return result

    pages_url = _github_pages_url(owner, repo)
    result["pages_url"] = pages_url
    ok, homepage_output = _set_repo_homepage(root, owner, repo, pages_url)
    if not ok:
        result["pages_error"] = (
            "GitHub Pages is on, but the repo homepage could not be set.\n"
            + homepage_output
        )
    return result


def git_enable_pages(target: Path, readme: str = "") -> dict:
    status = read_git_status(target)
    if not status.get("repo"):
        return _action_error("This folder is not a Git repository.")
    if status.get("state") == "detached":
        return _action_error("You are on a detached HEAD. Switch to a branch first.")
    if not status.get("has_remote"):
        return _action_error("Create a GitHub remote first.")

    root = _repo_root(target) or target
    if not shutil.which("gh"):
        return _action_error("GitHub CLI (gh) is not installed.")

    ok, auth_output = _run_command(["gh", "auth", "status"], root, 20)
    if not ok:
        return _action_error("GitHub CLI is not logged in. Run: gh auth login", auth_output)

    owner_repo = _github_owner_repo(root)
    if not owner_repo:
        return _action_error("The origin remote does not point at GitHub.")
    owner, repo = owner_repo

    branch = status.get("branch") or _git_text(
        root, ["symbolic-ref", "--short", "-q", "HEAD"]
    )
    if not branch or branch == "HEAD":
        return _action_error("You are not on a branch.")

    missing = pages_requirement(root)
    if missing:
        return _action_error(missing)

    if not status.get("upstream") or status.get("ahead"):
        return _action_error(
            "GitHub Pages only serves files that have been pushed. Push your "
            "commits first, then publish again."
        )

    blocked = gitignore_requirement(root, include_untracked=False)
    if blocked:
        return _action_error(blocked)

    prep = _add_readme(root, readme)
    if not prep["ok"]:
        return prep
    if prep.get("readme_written"):
        ok, push_output = _push_branch(root, status)
        if not ok:
            return _action_error(
                "README.md was committed, but it could not be pushed.", push_output
            )

    ok, output = _enable_github_pages(root, owner, repo, branch)
    if not ok:
        return _action_error("GitHub Pages could not be enabled.", output)

    pages_url = _github_pages_url(owner, repo)
    result = _action_ok(output or f"Enabled GitHub Pages at {pages_url}.")
    if prep.get("readme_written"):
        result["readme_written"] = True
    result["pages_url"] = pages_url
    ok, homepage_output = _set_repo_homepage(root, owner, repo, pages_url)
    if not ok:
        result["pages_error"] = (
            "GitHub Pages is on, but the repo homepage could not be set.\n"
            + homepage_output
        )
    return result


def run_git_action(action: str, target: Path, body: dict) -> dict:
    if action == "init":
        return git_init(
            target,
            _clean_message(body.get("message"), "Initial commit"),
            bool(body.get("gitignore")),
        )
    if action == "commit":
        return git_commit(target, _clean_message(body.get("message"), f"Update {target.name}"))
    if action == "push":
        return git_push(target)
    if action == "pages":
        return git_enable_pages(target, str(body.get("readme") or ""))
    if action == "pages-entry":
        return git_create_pages_entry(target)
    if action == "remote":
        return git_create_remote(
            target,
            str(body.get("name") or "").strip(),
            str(body.get("visibility") or "private").lower(),
            str(body.get("description") or "").strip(),
            bool(body.get("pages")),
            str(body.get("readme") or ""),
        )
    return _action_error("Unknown Git action.")
