import subprocess
import logging
import re
import os

logger = logging.getLogger("monpy." + __name__)

re_pkg = \
    r"^Inst " \
    r"(?P<name>.*?) " \
    r"\(" \
    r"(.*?) " \
    r"(?P<origin>.*?) " \
    r".*" \
    r"$"

def apt_upgrades(update=True):
    """
    Return info on upgradable packages.

        [
            {
                'name': 'linux-modules-6.17.0-29-generic',
                'origin': 'Ubuntu:24.04/noble-updates'
            },
            ...
        ]

    """
    if update is True:
        cmd = ["apt-get", "-qqq", "update"]
        logger.debug("Running: %s", " ".join(cmd))
        subprocess.run(
            cmd,
            check=True
        )

    res = subprocess.run(
        ["apt-get", "-qqq", "upgrade", "--dry-run"],
        capture_output=True,
        text=True,
        check=True
    )

    updates = []
    for line in res.stdout.splitlines():
        if not line.startswith("Inst "):
            continue

        match = re.match(re_pkg, line)
        update = match.groupdict()
        updates.append(update)

    return updates

def reboot_required():
    """
    Debian-derived systems touch /run/reboot-required when a package indicates
    that the system needs to be rebooted for the upgrade to fully take effect.

    Returns `True` if the system requires a reboot.
    """
    if os.path.exists("/run/reboot-required") or os.path.exists("/var/run/reboot-required"):
        return True
    else:
        return False
