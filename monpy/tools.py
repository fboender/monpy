import os
from pathlib import Path
import re
import datetime
import time


def kb_to_bytes(s):
    return int(s[:-3]) * 1024


def process_info(pid, extend_environ=False, extend_status=False,
                 extend_stat=False):
    process = {
        "pid": int(pid),
        "cmdline": None,
        "cwd": None,
        "exe": None,
    }

    fullpath = os.path.join("/proc", str(pid))
    with open(os.path.join(fullpath, "cmdline"), "rb") as fh:
        cmd = fh.read().split(b"\0")
        cmd = [c.decode() for c in cmd if c]
        process["cmdline"] = " ".join(cmd)

        try:
            process["cwd"] = os.readlink(os.path.join(fullpath, "cwd"))
        except (FileNotFoundError, ProcessLookupError):
            pass

        try:
            process["exe"] = os.readlink(os.path.join(fullpath, "exe"))
        except (FileNotFoundError, ProcessLookupError):
            pass

        if extend_environ is True:
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

        if extend_status is True:
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

        if extend_stat is True:
            with open("/proc/uptime") as fh:
                uptime = float(fh.readline().split()[0])

            with open(os.path.join(fullpath, "stat")) as fh:
                stat = fh.read()

            rest = stat[stat.rfind(")") + 2:].split()
            start_ticks = int(rest[19])
            clk_tck = os.sysconf(os.sysconf_names["SC_CLK_TCK"])

            boot_time = time.time() - uptime
            process["start_time"] = datetime.datetime.fromtimestamp(boot_time + start_ticks / clk_tck)

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
