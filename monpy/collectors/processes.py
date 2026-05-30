import os

from ..tools import kb_to_bytes, process_info

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
