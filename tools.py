import os
from pathlib import Path
import re
import sqlite3
import datetime


def kb_to_bytes(s):
    return int(s[:-3]) * 1024


def process_info(pid, extend=False):
    fullpath = os.path.join("/proc", str(pid))
    process = {
        "pid": int(pid),
        "cmdline": None,
        "cwd": None,
        "exe": None,
    }

    with open(os.path.join(fullpath, "cmdline"), "rb") as fh:
        cmd = fh.read().split(b"\0")
        cmd = [c.decode() for c in cmd if c]
        process["cmdline"] = " ".join(cmd)

        try:
            process["cwd"] = os.readlink(os.path.join(fullpath, "cwd"))
        except FileNotFoundError:
            pass

        try:
            process["exe"] = os.readlink(os.path.join(fullpath, "exe"))
        except FileNotFoundError:
            pass

        if extend is True:
            process["environ"] = {}
            try:
                with open(os.path.join(fullpath, "environ"), "rb") as fh:
                    for item in fh.read().split(b"\0"):
                        try:
                            key, value = item.decode().split("=", 1)
                            process["environ"][key] = value.strip()
                        except ValueError:
                            # Some processes have a really weird environ
                            pass
            except ProcessLookupError:
                pass

        if extend is True:
            with open(os.path.join(fullpath, "status"), "r") as fh:
                for line in fh:
                    key, value = line.split(":", 1)
                    value = value.strip()

                    if "\t" in value:
                        value = value.split("\t")
                    elif value.endswith("kB"):
                        value = kb_to_bytes(value)
                    elif value.isdigit():
                        value = int(value)

                    process[key.lower()] = value

        return process


def inode_pid_map():
    inode_map = {}

    for pid in filter(str.isdigit, os.listdir("/proc")):
        fd_dir = Path("/proc") / pid / "fd"
        if not fd_dir.exists():
            continue
        try:
            for fd in fd_dir.iterdir():
                try:
                    target = os.readlink(fd)
                    if target.startswith("socket:["):
                        inode = int(target[8:-1])
                        inode_map.setdefault(inode, []).append(int(pid))
                except OSError:
                    pass
        except PermissionError:
            continue
    return inode_map


def camel_to_snake(s):
    return re.sub(r'([a-z])([A-Z])', r'\1_\2', s).lower()


class Bucket:
    """
    Efficiently keep a key/value mapping using sqlite3.
    """
    def __init__(self, path, bucket_id):
        self.path = path
        self.bucket_id = bucket_id
        self.conn = sqlite3.connect(self.path)
        self._create_table()

    def _create_table(self):
        """
        Create key/value mapping table if not exists.
        """
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name=?
            """,
            ("buckets",)
        )
        if cur.fetchone() is None:
            cur.execute(
                """
                CREATE TABLE buckets (
                    bucket_id TEXT NOT NULL,
                    key       TEXT NOT NULL,
                    value     INTEGER,
                    last_seen DATETIME,
                    PRIMARY KEY (bucket_id, key)
                )
                """
            )

    def get(self, key, default_val=None):
        """
        Get value for `key`. If `key` is not found, return `default_val`
        """
        cur = self.conn.cursor()
        cur.execute("SELECT value FROM buckets WHERE bucket_id = ? and key = ?", (self.bucket_id, key))
        row = cur.fetchone()
        if row is None:
            return default_val
        else:
            return row[0]

    def set(self, key, value, commit=True):
        """
        Set value of `key` to `value`
        """
        now = datetime.datetime.now(datetime.UTC).isoformat()
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO buckets (bucket_id, key, value, last_seen)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(bucket_id, key)
            DO UPDATE SET value = excluded.value, last_seen = excluded.last_seen
            """,
            (self.bucket_id, key, value, now)
        )
        if commit is True:
            self.conn.commit()

    def vacuum(self, seconds):
        """
        Remove stale keys not seen in more than `seconds`
        """
        now = datetime.datetime.now(datetime.UTC)
        delta = datetime.timedelta(seconds=seconds)
        cut_off = (now - delta).isoformat()
        cur = self.conn.cursor()
        cur.execute("DELETE FROM buckets WHERE last_seen <= ?", (cut_off, ))
        self.conn.commit()

    def commit(self):
        self.conn.commit()
