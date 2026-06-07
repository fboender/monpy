import sys
import os
import shutil
from pathlib import Path

from ..tools import kb_to_bytes, camel_to_snake, process_info


def memory():
    """
    Return memory information.

    Yields (some field removed for clarity, see /proc/meminfo for all fields):

        {
            "mem_total": 16645906432,
            "mem_free": 1039073280,
            "mem_available": 10125004800,
            "buffers": 1497112576,
            "cached": 7027367936,
            "swap_cached": 147300352,
            "swap_total": 2046816256,
            "swap_free": 1396477952,
            "mem_free_perc": 6.242215070982804,
            "mem_available_perc": 60.82579426576462,
            "swap_free_perc": 68.22683511069398
        }

    Values are in bytes, except for "_perc" fields, which are in percentages.
    """
    meminfo = {}
    with open("/proc/meminfo", "r") as fh:
        for line in fh:
            key, value = line.strip().split(":", 1)
            key = camel_to_snake(key)
            if value.endswith("kB"):
                meminfo[key] = kb_to_bytes(value)
            elif value.isdigit():
                meminfo[key] = int(value)
            else:
                meminfo[key] = value.strip()

    meminfo["mem_free_perc"] = meminfo["mem_free"] / meminfo["mem_total"] * 100
    meminfo["mem_available_perc"] = meminfo["mem_available"] / meminfo["mem_total"] * 100
    if meminfo["swap_total"] > 0:
        meminfo["swap_free_perc"] = meminfo["swap_free"] / meminfo["swap_total"] * 100

    return meminfo


def uptime():
    """
    System uptime (time since last boot)

    Returns:

        {
            "uptime": <uptime in seconds>,
            "idle": <idle>
        }
    """
    with open("/proc/uptime") as fh:
        parts = fh.readline().strip().split()

        uptime = int(float(parts[0]))
        idle = int(float(parts[1]))

        return {
            "uptime": uptime,
            "idle": idle
        }


def mounts():
    """
    Mount point information.
    """
    with open("/proc/mounts", "r") as fh:
        for line in fh:
            device, mount_point, type_, options, dump, pass_ = line.strip().split()

            total, used, free = shutil.disk_usage(mount_point)

            yield {
                    "device": device,
                    "mount_point": mount_point,
                    "type": type_,
                    "options": options,
                    "dump": dump,
                    "pass": pass_,
                    "size_total_b": total,
                    "size_used_b": used,
                    "size_free_b": free,
                    "size_total_gb": total / (1024 ** 3) if total else 0,
                    "size_used_gb": used / (1024 ** 3) if used else 0,
                    "size_free_gb": free / (1024 ** 3) if free else 0,
                    "size_used_perc": used / total * 100 if used and total else 0,
                    "size_free_perc": free / total * 100 if free and total else 0,
            }

def cpu_load():
    """
    CPU load averages.
    """
    with open("/proc/loadavg") as f:
        parts = f.read().split()

    return {
        "1min": float(parts[0]),
        "5min": float(parts[1]),
        "15min": float(parts[2]),
        "running": int(parts[3].split("/")[0]),
        "total": int(parts[3].split("/")[1]),
        "last_pid": int(parts[4]),
    }


def processes():
    for fname in os.listdir("/proc"):
        fullpath = os.path.join("/proc", fname)
        if not fname.isdigit() or not os.path.isdir(fullpath):
            continue
        pid = fname

        try:
            process = process_info(pid, extend=True)
            yield process
        except FileNotFoundError:
            # Something went wrong with getting the process info. It probably
            # went away. Ignore it.
            continue


def temperatures():
    """
    Read temperatures (°C) for various sensors.

    Yields:

        {
            "path": "/sys/class/hwmon/hwmon3",
            "name": "coretemp",
            "device": "/sys/devices/platform/coretemp.0",
            "temperature": 47.0,
            "model": ""
        }
        {
            "path": "/sys/class/hwmon/hwmon1",
            "name": "nvme",
            "device": "/sys/devices/pci0000:00/0000:00:1d.0/0000:3c:00.0/nvme/nvme0",
            "temperature": 32.85,
            "model": "Samsung SSD 970 EVO 250GB"
        }
    """
    for hwmon in Path("/sys/class/hwmon").glob("*"):
        temperature_info = {
            "path": str(hwmon),
            "name": (hwmon / "name").read_text().strip(),
            "device": str((hwmon / "device").resolve()),
            "temperature": -1,
            "model": ""
        }
        try:
            temperature_info["temperature"] = int((hwmon / "temp1_input").read_text()) / 1000
        except OSError:
            pass

        try:
            temperature_info["model"] = (hwmon / "device" / "model").read_text().strip()
        except FileNotFoundError:
            pass

        yield temperature_info
