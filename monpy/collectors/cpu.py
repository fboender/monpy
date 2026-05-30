import os

def load():
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
