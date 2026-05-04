import os

def kb_to_bytes(s):
    return int(s[:-3]) * 1024

def processes():
    for fname in os.listdir("/proc"):
        fullpath = os.path.join("/proc", fname)
        if not fname.isdigit() or not os.path.isdir(fullpath):
            continue

        process = {
            "pid": int(fname),
            "cmdline": None,
            "cwd": None,
            "exe": None,
            "environ": {},
        }

        try:
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

            yield process
        except FileNotFoundError:
            # Process disappeared, ignore it
            continue
