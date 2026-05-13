import subprocess
import logging
import re
import os

logger = logging.getLogger("monpy." + __name__)

re_pkg = \
    r"^" \
    r"(?P<name>.*?)/" \
    r"(?P<origins>.*?) " \
    r"(?P<upgrade_to>.*?) " \
    r"(?P<architecture>.*?) " \
    r"\[upgradable from: (?P<upgrade_from>.*?)\]" \
    r".*" \
    r"$"

def apt_upgrades(update=True):
    """
    Return info on upgradable packages.
    """
    if update is True:
        logger.debug("Running: apt -qqq update")
        subprocess.run(
            ["apt", "-qqq", "update"],
            check=True
        )

    res = subprocess.run(
        ["apt", "-qqq", "list", "--upgradable"],
        capture_output=True,
        text=True,
        check=True
    )

    updates = []
    for line in res.stdout.splitlines():
        match = re.match(re_pkg, line)
        update = match.groupdict()
        update["origins"] = update["origins"].split(",")
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
