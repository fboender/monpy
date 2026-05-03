import sys
import shutil

def mounts():
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
