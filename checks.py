#!/bin/env python3

import stat

from monpy import *
from config import *


minutely = 60
hourly = 60 * 60
daily = 60 * 60 * 24
weekly = 60 * 60 * 24 * 7


monpy = MonPy(
    PUSHOVER_USER_TOKEN,
    PUSHOVER_APP_TOKEN
)

@monpy.check(minutely * 10, daily)
def disk_space():
    """
    Check disk space
    """
    for mount in collectors.mounts():
        if mount["type"] != "ext4":
            continue

        if mount["mount_point"].startswith("/share/"):
            # Bind mounted, we don't care
            continue

        if mount["size_free_perc"] < DISK_SPACE_FREE_PERC:
            monpy.alert(
                f"Mount '{mount['mount_point']}' less than {DISK_SPACE_FREE_PERC}% free ({mount['size_free_perc']:.1f})",
                ident=mount["mount_point"]
            )

@monpy.check(minutely, hourly)
def cpu_usage():
    load = collectors.load()
    history = monpy.history(load["1min"], LOAD_SAMPLES)
    avg = sum(history) / len(history)
    if avg > LOAD_MAX:
        monpy.alert(
            f"Average load of last {LOAD_SAMPLES} minutes higher than {LOAD_MAX} ({avg})"
        )

@monpy.check(minutely, hourly)
def low_mem():
    """
    Check for low available memory
    """
    meminfo = collectors.memory()
    avail_p = meminfo["MemAvailablePerc"]
    avail_mb = meminfo['MemAvailable'] / (1024 ** 2)
    if meminfo["MemAvailablePerc"] < LOW_MEM_AVAIL_PERC:
        monpy.alert(
            f"Less than {LOW_MEM_AVAIL_PERC}% available memory ({avail_p:.0f}%, {avail_mb:.0f} MB)"
        )

@monpy.check(minutely, hourly)
def proc_with_high_mem():
    """
    Check for processes using a lot of memory
    """
    for process in collectors.processes():
        if process.get("vmrss", 0) > PROC_HIGH_MEM_MB * (1024 ** 2):
            mem_usage_gb = process["vmrss"] / (1024 ** 2)
            monpy.alert(
                f"Process '{process['exe']}' (pid: {process['pid']}) uses more than {PROC_HIGH_MEM_MB} MB of memory ({mem_usage_gb:.2f} MM)",
                ident=process["pid"]
            )

@monpy.check(hourly, daily)
def docker_wildcard_bind():
    """
    Check for containers that bind ports on all interfaces (0.0.0.0), and are
    not configured in ALLOW_DOCKER_WILDCARD_BINDS
    """
    for container in collectors.docker_containers():
        ports = container["NetworkSettings"]["Ports"]
        if ports is None:
            continue

        for port, host_ports in ports.items():
            if port in ALLOW_DOCKER_WILDCARD_BINDS:
                continue

            if host_ports is None:
                continue

            for host_port in host_ports:
                if host_port["HostIp"] == "0.0.0.0":
                    monpy.alert(
                        f"Container '{container['Name'].lstrip('/')}' exposes port {port} on all interfaces (0.0.0.0)",
                        ident=f"{container['Name']}-{port}",
                    )

@monpy.check(minutely, hourly)
def nftables_default_policy():
    """
    Check that the nftables firewall has default rules to drop input
    """
    input_4_dropped = False
    input_6_dropped = False

    for element in collectors.nftables()["nftables"]:
        if (
            "chain" in element and
            element["chain"].get("hook", "") == "input" and
            element["chain"].get("policy", "") == "drop"
        ):
            if element["chain"]["family"] == "ip":
                input_4_dropped = True
            elif element["chain"]["family"] == "ip6":
                input_6_dropped = True

    if input_4_dropped is False:
        monpy.alert(
            f"nftables missing default input 'drop' policy for IPv4",
            ident="ipv4"
        )
    if input_6_dropped is False:
        monpy.alert(
            f"nftables missing default input 'drop' policy for IPv6",
            ident="ipv6"
        )

@monpy.check(hourly, daily)
def docker_mount_socket():
    """
    Check if a docker container mounts the docker socket into it
    """
    for container in collectors.docker_containers():
        container_name = container["Name"].lstrip("/")
        if container_name in ALLOW_CONTAINER_DOCKER_SOCKET:
            continue
        for name, mount in container["MountPoints"].items():
            if mount["Source"] == "/var/run/docker.sock":
                monpy.alert(
                    f"Container '{container['Name'].lstrip('/')}' mounts the docker socket in the container",
                    ident=container_name
                )

@monpy.check(hourly, daily)
def mail():
    """
    Check if there is local mail
    """
    for file in collectors.files("/var/spool/mail"):
        if file["size"] > 0:
            monpy.alert(
                f"Mail found in /var/spool/mail for '{file['filename']}'",
                ident=file["filename"]
            )

@monpy.check(daily, daily)
def cron_mailto():
    """
    Check that crontabs contain a MAILTO so we're notified of problems
    """
    files = []
    files.append(collectors.file("/etc/crontab"))
    #files.extend(collectors.files("/etc/cron.d"))
    files.extend(collectors.files("/var/spool/cron/crontabs"))

    for file in files:
        if collectors.egrep(file["path"], b".*MAILTO.*") is None:
            monpy.alert(
                f"Cron file '{file['path']}' has no MAILTO",
                ident=file["path"],
            )

@monpy.check(hourly, daily)
def executables_in_tmp():
    """
    Check for executables in temp directories
    """
    def error(path, err):
        # AppImage mounts can't be read even by root. Same for stuff in
        # /run/user (only readable for that user)
        if (
            isinstance(err, PermissionError) and (
                ".mount_" in path or
                "/run/user" in path
            )
        ):
            return

        raise err

    for temp_path in TEMP_PATHS:
        for file in collectors.files(temp_path, ftype='file', one_fs=False, on_error=error):
            is_exec = bool(file["mode"] & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
            if not is_exec:
                continue

            # Ignore Python standalone executables.
            # FIXME: Would be better to actually checvk for specific standalone
            # executables (such as 'borg'), but that's tricky for now.
            if "_MEI" in file["path"]:
                continue

            monpy.alert(
                f"Executable found in temp dir: {file['path']}",
                ident=file["path"]
            )

monpy.run()
