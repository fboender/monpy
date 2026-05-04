import logging
import os
import subprocess

logger = logging.getLogger(__package__)

def git_cmd(path, *args):
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
        encoding="utf-8",
        check=True
    )
    return proc.stdout

def git_repo(path, fetch=True):
    if fetch is True:
        logger.info("Fetching remote changes for repo '%s'", path)
        git_cmd(path, "fetch", "-q")

        # Refresh the index, or we might get wrong results.
        logger.debug("Updating git repo index")
        git_cmd(path, "update-index", "-q", "--refresh")

    cur_branch = git_cmd(path, "rev-parse", "--abbrev-ref", "HEAD").strip()
    remote_branch = git_cmd(path, "rev-parse", "--abbrev-ref", "--symbolic-full-name", f"{cur_branch}@{{u}}").strip()
    ahead_behind = git_cmd(path, "rev-list", "--left-right", "--count", f"{cur_branch}...{remote_branch}").strip()
    ahead, behind = [int(x) for x in ahead_behind.split()]

    return {
        "path": path,
        "cur_branch": cur_branch,
        "remote_branch": remote_branch,
        "ahead": ahead,
        "behind": behind
    }
