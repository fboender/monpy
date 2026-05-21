import subprocess
import logging
import re
import os

logger = logging.getLogger("monpy." + __name__)


def apt_updates(update=True):
    """
    Return info on upgradable packages.

    If `update` is True, the package index will be refreshed (`apt-get update`)
    beforehand.

    Returns a list of package updates available:

        [
            {
                "name": "rsync",
                "cur_version": "3.2.7-0ubuntu0.22.04.4",
                "new_version": "3.2.7-0ubuntu0.22.04.6",
                "origins": [
                    "Ubuntu:22.04/jammy-updates",
                    "Ubuntu:22.04/jammy-security"
                ],
                "security": true
            },
            ...
        ]

    NOTE that the `security` field is determined by the origins, and many
    third-part repositories push security updates via a non-security origin.
    This field is therefor not a reliable indicator of whether an update is a
    security update.
    """
    if update is True:
        cmd = ["apt-get", "-qqq", "update"]
        logger.debug("Running: %s", " ".join(cmd))
        subprocess.run(
            cmd,
            check=True
        )

    cmd = ["apt-get", "-qqq", "upgrade", "--with-new-pkgs", "--dry-run"]
    logger.debug("Running: %s", " ".join(cmd))
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=True
    )

    updates = []
    for line in res.stdout.splitlines():
        if not line.startswith("Inst "):
            continue

        update = {
            "name": None,
            "cur_version": None,
            "new_version": None,
            "origins": [],
            "security": False
        }

        # Parse apt-get line. This is horrible code, but there is no other
        # easily parsable output available
        tokens = line.split()
        tokens.pop(0)  # "Inst"
        update["name"] = tokens.pop(0)
        if tokens[0][0] == "[":
            update["cur_version"] = tokens.pop(0).strip("[]")
        if tokens[0][0] == "(":
            update["new_version"] = tokens.pop(0).strip("()")
        update["origins"] = [token.strip(",") for token in tokens if token[0] != "["]
        update["security"] = len([origin for origin in update["origins"] if "-security" in origin]) > 0

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
