import os

from tools import kb_to_bytes


def memory():
    """
    Return memory information.

    Yields (some field removed for clarity, see /proc/meminfo for all fields):

        {
            "MemTotal": 16645906432,
            "MemFree": 1016553472,
            "MemAvailable": 10159374336,
            "Buffers": 1494290432,
            "Cached": 7146610688,
            "SwapCached": 147230720,
            "Active": 4837314560,
            "SwapTotal": 2046816256,
            "SwapFree": 1370918912,
            "MemFreePerc": 6.106927707137553,
            "MemAvailablePerc": 61.03226866918868,
            "SwapFreePerc": 66.97811334951602
        }

    Values are in bytes, except for "Perc" fields, which are in percentages.
    """
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
    if meminfo["SwapTotal"] > 0:
        meminfo["SwapFreePerc"] = meminfo["SwapFree"] / meminfo["SwapTotal"] * 100

    return meminfo
