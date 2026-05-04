def uptime():
    with open("/proc/uptime") as fh:
        parts = fh.readline().strip().split()

        uptime = int(float(parts[0]))
        idle = int(float(parts[1]))

        return {
            "uptime": uptime,
            "idle": idle
        }
