import os

from ..tools import kb_to_bytes, camel_to_snake


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
