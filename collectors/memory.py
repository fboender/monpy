import os

from tools import kb_to_bytes


def memory():
    meminfo = {}
    with open("/proc/meminfo", "r") as fh:
        for line in fh:
            key, value = line.strip().split(":", 1)
            if value.endswith("kB"):
                meminfo[key] = kb_to_bytes(value)
            elif value.isdigit():
                meminfo[key] = int(value)
            else:
                meminfo[key] = value.strip()

    meminfo["MemFreePerc"] = meminfo["MemFree"] / meminfo["MemTotal"] * 100
    meminfo["MemAvailablePerc"] = meminfo["MemAvailable"] / meminfo["MemTotal"] * 100

    return meminfo
