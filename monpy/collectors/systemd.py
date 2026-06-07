import subprocess
import json

def _systemctl_cmd(type):
    proc = subprocess.run(
        ["systemctl", "--output=json", "--all", type],
        check=True,
        capture_output=True,
        encoding="utf-8"
    )
    elements = json.loads(proc.stdout)
    return elements

def units():
    """
    Systemd unit status
    """
    for element in _systemctl_cmd("list-units"):
        yield element

def timers():
    """
    Systemd timer status
    """
    for element in _systemctl_cmd("list-timers"):
        yield element

def automounts():
    """
    Systemd automounts status
    """
    for element in _systemctl_cmd("list-automounts"):
        yield element

def paths():
    """
    Systemd path status
    """
    for element in _systemctl_cmd("list-paths"):
        yield element

def sockets():
    """
    Systemd socket status
    """
    for element in _systemctl_cmd("list-sockets"):
        yield element

def failed():
    """
    Systemd failed units
    """
    for element in _systemctl_cmd("--failed"):
        yield element

def show(unit):
    """
    Systemd show unit information
    """
    proc = subprocess.run(
        ["systemctl", "show", unit],
        check=True,
        capture_output=True,
        encoding="utf-8"
    )
    status = {}
    for line in proc.stdout.splitlines():
        key, value = line.strip().split("=", 1)
        status[key] = value
    return status

def journalctl(unit):
    """
    Journalctl unit info
    """
    proc = subprocess.run(
        ["journalctl", "--output", "json", "-u", unit],
        check=True,
        capture_output=True,
        encoding="utf-8"
    )
    for line in proc.stdout.splitlines():
        elements = json.loads(line)
        yield elements
