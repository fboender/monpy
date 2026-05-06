"""
Collector that gathers information about a local Git repository.

By default it will try to do a `git fetch` on the repo to fetch new changes,
without merging, rebasing or fast-forwarding the current branch. If you don't
want to fetch, you can pass `fetch=False` as a parameter.

You'll probably want to use a [fine-grained personal access
token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens#fine-grained-personal-access-tokens)
to clone the repo.

Repository info example:

    {
        "path": "/opt/apps/monpy",
        "cur_branch": "main",
        "remote_branch": "origin/main",
        "ahead": 0,
        "behind": 2,
        "has_changes": false,
        "modified": [],
        "deleted": [],
        "untracked": []
    }

Where `modified`, `deleted` and `untracked` are lists of files in the repo that
have those changes.
"""

import logging
import os
import subprocess

logger = logging.getLogger("monpy." + __name__)

def _git_cmd(path, *args):
    git_dir = os.path.join(path, ".git")
    cmd = [
        "git",
        "--work-tree", path,
        "--git-dir", git_dir,
        *args
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        encoding="utf-8"
    )
    if proc.returncode != 0:
        logger.error("Error running command '%s': %s", " ".join(cmd), proc.stderr)
        proc.check_returncode()

    return proc.stdout

def git_repo(path, fetch=True):
    """
    Get on-disk repository information such as ahead, behind and changes. If
    `fetch` is True (default), new changes will be be fetched from a remote
    without a merge, rebase or fast forward.
    """
    if fetch is True:
        logger.info("Fetching remote changes for repo '%s'", path)
        _git_cmd(path, "fetch", "-q")

        # Refresh the index, or we might get wrong results.
        logger.debug("Updating git repo index")
        _git_cmd(path, "update-index", "-q", "--refresh")

    cur_branch = _git_cmd(path, "rev-parse", "--abbrev-ref", "HEAD").strip()
    remote_branch = _git_cmd(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", f"{cur_branch}@{{u}}").strip()
    ahead_behind = _git_cmd(path, "rev-list", "--left-right", "--count", f"{cur_branch}...{remote_branch}").strip()
    ahead, behind = [int(x) for x in ahead_behind.split()]

    repo_info = {
        "path": path,
        "cur_branch": cur_branch,
        "remote_branch": remote_branch,
        "ahead": ahead,
        "behind": behind,
        "has_changes": False,
        "modified": [],
        "deleted": [],
        "untracked": [],
    }

    status = _git_cmd(path, "diff-index", "HEAD", "--")
    for line in status.splitlines():
        old_mode, new_mode, head_blob, blob_index, status, changed_path = line.split(maxsplit=6)
        repo_info["has_changes"] = True
        if status == "M":
            repo_info["modified"].append(changed_path)
        elif status == "D":
            repo_info["deleted"].append(changed_path)

    untracked = _git_cmd(path, "ls-files", "--others", "--exclude-standard").strip()
    for line in untracked.splitlines():
        repo_info["has_changes"] = True
        repo_info["untracked"].append(line)

    return repo_info
