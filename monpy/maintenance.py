import os
import logging
import datetime


class Maintenance:
    """
    Read maintenance info from disk
    """
    def __init__(self, state_dir, maintenance_max):
        self.state_dir = state_dir
        self.maintenance_max = maintenance_max

        self.maintenance_path = os.path.join(self.state_dir, "maintenance")
        self.logger = logging.getLogger(__name__)
        self.maintenance = {}
        self._load()

    def _load(self):
        """
        Load all maintenances from disk.
        """
        if not os.path.exists(self.maintenance_path):
            return

        now = datetime.datetime.now()

        # Parse all files found in maintenance dir
        for fname in os.listdir(self.maintenance_path):
            path = os.path.join(self.maintenance_path, fname)
            stat = os.stat(path)
            mtime = datetime.datetime.fromtimestamp(stat.st_mtime)

            # Check if maintenance expiration is present in the file. If so,
            # use it. Otherwise, expiratarion is None (forever, until
            # maintenance_max)
            until = None
            with open(path, "r") as fh:
                content = fh.read().strip()
                if content != "":
                    until = datetime.datetime.strptime(content, "%Y-%m-%d %H:%M:%S")

            # Check if maintenance time (at creation; file mtime) has exceeded
            # the max time. If so, remove the maintenance file and ignore it.
            if (now - mtime).total_seconds() > self.maintenance_max:
                self.logger.warning("Maximum maintenance time for '%s' has been exceeded. Removing maintenance", fname)
                os.unlink(path)
                continue

            self.maintenance[fname] = {
                "mtime": mtime,
                "until": until
            }

    def active(self, check_name):
        """
        Check if check with `check_name` is in maintenance.
        """
        now = datetime.datetime.now()
        active_maintenance = False

        # Either "ALL" or check name
        for key in ["ALL", check_name]:
            if key in self.maintenance:
                maintenance = self.maintenance[key]

                # Check for longest maintenance time
                until = maintenance["until"]
                if until is None or until > now:
                    # If no maintenance yet, or this maintenance is longer then
                    # currently known maintenance
                    if active_maintenance is False or maintenance["until"] > active_maintenance:
                        active_maintenance = maintenance

        return active_maintenance


