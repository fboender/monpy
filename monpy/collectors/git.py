import logging
import os
import subprocess
from pathlib import Path
import datetime


logger = logging.getLogger(__name__)


class Repo:
    """
    Git repo information and manipulation.
    """
    def __init__(self, path, fetch=False, fast_forward=False):
        """
        `path` is the path to the git repo checkout.

        If `fetch` is True, a fetch is performed (see `Repo.fetch()`). If
        `fast_forward` is True, the repo is fast-forwarded (see
        `fast_forward()`)
        """
        self.path = path

        # Test path and raise exception on problems
        Path(self.path).stat()

        if fetch is not False:
            self.fetch()
        if fast_forward is not False:
            self.fast_forward()

    def _git_cmd(self, *args):
        """
        Execute git command in repo dir
        """
        git_dir = os.path.join(self.path, ".git")
        cmd = [
            "git",
            "--work-tree", self.path,
            "--git-dir", git_dir,
            *args
        ]
        logger.debug("Running: %s", " ".join(cmd))
        proc = subprocess.run(
            cmd,
            capture_output=True,
            encoding="utf-8"
        )
        if proc.returncode != 0:
            logger.error("Error running command '%s': %s", " ".join(cmd), proc.stderr)
            proc.check_returncode()

        return proc.stdout

    def _parse_raw_commit(self, raw_commit):
        commit = {
            "commit": None,
            "message": "",
            "added": [],
            "modified": [],
            "deleted": []
        }

        for line in raw_commit:
            if line.startswith("commit "):
                commit["commit"] = line.split(" ", 1)[1]
            elif line.startswith("    "):
                commit["message"] = commit["message"] + line[4:] + "\n"
            elif line.startswith(":"):
                old_mode, new_mode, head_blob, blob_index, status, changed_path = line.split(maxsplit=6)
                self.has_changes = True
                if status == "A":
                    commit["added"].append(changed_path)
                if status == "M":
                    commit["modified"].append(changed_path)
                elif status == "D":
                    commit["deleted"].append(changed_path)

        return commit

    def status(self):
        """
        Current status of repository.

        Returns:

            {
                "branch": "main",
                "tracking_branch": "origin/main",
                "has_changes": True,
                "ahead": 0,
                "behind": 2,
                "added": [
                    "foo.txt"
                ],
                "modified": [],
                "deleted": [],
                "untracked": []
            }

        """
        result = {
            "branch": None,
            "tracking_branch": None,
            "has_changes": False,
            "ahead": None,
            "behind": None,
            "added": [],
            "modified": [],
            "deleted": [],
            "untracked": [],
        }

        # Get current branch
        result["branch"] = self._git_cmd(
            "rev-parse",
            "--abbrev-ref",
            "HEAD"
        ).strip()

        # Get tracking branch (usually remote)
        result["tracking_branch"] = self._git_cmd(
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            f"{result['branch']}@{{u}}"
        ).strip()

        # Get ahead / behind tracking branch
        ahead_behind = self._git_cmd(
            "rev-list",
            "--left-right",
            "--count",
            f"{result['branch']}...{result['tracking_branch']}"
        ).strip()
        result["ahead"], result["behind"] = [int(x) for x in ahead_behind.split()]

        # Get working tree status
        res = self._git_cmd(
            "diff-index",
            "HEAD", "--"
        )
        for line in res.splitlines():
            old_mode, new_mode, head_blob, blob_index, status, changed_path = line.split(maxsplit=6)
            self.has_changes = True
            if status == "A":
                result["has_changes"] = True
                result["added"].append(changed_path)
            if status == "M":
                result["has_changes"] = True
                result["modified"].append(changed_path)
            elif status == "D":
                result["has_changes"] = True
                result["deleted"].append(changed_path)

        # Get untracked files
        untracked_lines = self._git_cmd("ls-files", "--others", "--exclude-standard").strip()
        for line in untracked_lines.splitlines():
            result["untracked"].append(line)

        return result

    def log(self, last=1, from_commit=None):
        """
        Fetch a list of the last `last` commit(s), or since `from_commit` (hash).

        Returns:

            [
                {
                    "hash": "f5ad6b288d63f89d727d5088b85a6fe9ca19feca",
                    "author": "Ferry Boender <ferry.boender@gmail.com>",
                    "date": datetime.datetime(2026, 6, 4, 14, 31, 14, tzinfo=datetime.timezone(datetime.timedelta(seconds=7200))),
                    "message": "testje\n",
                    "added": [],
                    "modified": ["test.md"],
                    "deleted": [],
                },
                ...
            ]
        """
        commits = []

        cmd = ["log", "--raw", "--reverse"]
        if from_commit is not None:
            cmd.append("..." + from_commit)
        else:
            cmd.append(f"-{last}")
        log = self._git_cmd(*cmd)
        commit = None
        for line in log.splitlines():
            if line.startswith("commit "):
                if commit is not None:
                    commits.append(commit)
                commit = {
                    "hash": "",
                    "author": "",
                    "date": "",
                    "message": "",
                    "added": [],
                    "modified": [],
                    "deleted": []
                }
                commit["hash"] = line.split(" ", 1)[1]
            elif line.startswith("Author:"):
                commit["author"] = line.split(":", 1)[1].strip()
            elif line.startswith("Date:"):
                dt = line.split(":", 1)[1].strip()
                commit["date"] = datetime.datetime.strptime(dt, "%a %b %d %H:%M:%S %Y %z")
            elif line.startswith("    "):
                commit["message"] = commit["message"] + line[4:] + "\n"
            elif line.startswith(":"):
                old_mode, new_mode, head_blob, blob_index, status, changed_path = line.split(maxsplit=6)
                self.has_changes = True
                if status == "A":
                    commit["added"].append(changed_path)
                if status == "M":
                    commit["modified"].append(changed_path)
                elif status == "D":
                    commit["deleted"].append(changed_path)
        if commit is not None:
            commits.append(commit)

        return commits

    def fetch(self):
        """
        Fetch remote changes without rebasing, merging or fast-forwarding.
        """
        self._git_cmd("fetch", "-q")

        # Refresh the index, or we might get wrong results.
        self._git_cmd("update-index", "-q", "--refresh")

    def fast_forward(self):
        """
        Fast-forward current branch to its tracking branch.
        """
        self._git_cmd("merge", "--ff-only")
