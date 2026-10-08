#!/bin/env python3

import sys
from monpy import MonPy
from monpy import collectors

monpy = MonPy(
    state_dir="."
)

@monpy.check(0, 0)
def high_uptime():
    """
    Check for high system uptime. Systems should be regularly rebooted
    """
    uptime = collectors.system.uptime()
    if uptime["uptime"] > config["uptime_days"] * 24 * 60 * 60:
        monpy.alert(
            f"Uptime is higher than {config['uptime_days']} days"
        )

sys.exit(monpy.run())
