#!/bin/env python3

#
# EXAMPLE CHECKS
#
# These are just some examples of monitoring checks you can create with MonPy.
# You can base your own monitoring script(s) on this file.
#
# This file uses a configuration file (`config.py`). If you want to try out the
# checks in this example:
#
#   $ cp config.py.in config.py    # modify if needed
#   $ sudo ./checks.py -vvv
#

import os
import sys
import stat
import datetime
import subprocess

from monpy import MonPy
from monpy import collectors
from monpy.alerters import Pushover
from monpy.reporters import HTML
from monpy.tools import Bucket

from config import *

minutely = 60
hourly = 60 * 60
daily = 60 * 60 * 24
weekly = 60 * 60 * 24 * 7

# Nginx log file regexp, used by 'log_nginx_bruteforce' check
re_nginx = \
     r"^" \
     r"(?P<ip>\d+\.\d+\.\d+\.\d+) -\s+" \
     r"(?P<remote_user>.*?)\s+" \
     r"\[(?P<date>.*?)\] " \
     r"\"(?P<request>.*?)\" " \
     r"(?P<status>\d+) " \
     r"(?P<body_bytes_sent>\d+) " \
     r"\"(?P<referer>.*?)\" " \
     r"\"(?P<user_agent>.*?)\"" \
     r"$"


alerter_default = Pushover(PUSHOVER_TOKENS["default"]["user"], PUSHOVER_TOKENS["default"]["app"])
alerter_cve = Pushover(PUSHOVER_TOKENS["cve"]["user"], PUSHOVER_TOKENS["cve"]["app"])
reporter = HTML(out_path="/var/lib/monpy/report.html", auto_refresh=60)
monpy = MonPy(alerter=alerter_default, reporter=reporter, lock_wait=4)

##############################################################################
## System resource monitoring
##############################################################################
@monpy.check(minutely * 10, daily)
def disk_space():
    """
    Check disk space
    """
    for mount in collectors.system.mounts():
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

@monpy.check(minutely, hourly, alert_after=LOAD_MAX_ALERT_AFTER)
def cpu_usage():
    """
    Check CPU usage
    """
    load = collectors.system.cpu_load()
    if load["15min"] > LOAD_MAX:
        monpy.alert(
            f"Load over last 15 minutes higher than {LOAD_MAX} ({load['15min']})"
        )

@monpy.check(minutely, hourly)
def low_mem():
    """
    Check for low available memory
    """
    meminfo = collectors.system.memory()
    avail_p = meminfo["mem_available_perc"]
    avail_mb = meminfo['mem_available'] / (1024 ** 2)
    if meminfo["mem_available_perc"] < LOW_MEM_AVAIL_PERC:
        monpy.alert(
            f"Less than {LOW_MEM_AVAIL_PERC}% available memory ({avail_p:.0f}%, {avail_mb:.0f} MB)"
        )

@monpy.check(minutely, hourly)
def temperatures():
    """
    Check all available system sensors for high temperatures
    """
    for t_info in collectors.system.temperatures():
        if t_info["temperature"] > MAX_TEMPERATURE:
            monpy.alert(
                f"Temperature for sensor '{t_info['name']}' higher than {MAX_TEMPERATURE}°C ({t_info['temperature']}°C, device: {t_info['device']}).",
                ident=t_info['name']
            )

@monpy.check(minutely, hourly)
def proc_with_high_mem():
    """
    Check for processes using a lot of memory
    """
    for process in collectors.system.processes():
        if process.get("vmrss", 0) > PROC_HIGH_MEM_MB * (1024 ** 2):
            ignore = False
            for process_name in PROC_HIGH_MEM_IGNORE:
                if process_name in process["exe"]:
                    ignore = True
                    break

            if ignore:
                continue

            mem_usage_gb = process["vmrss"] / (1024 ** 2)
            monpy.alert(
                f"Process '{process['exe']}' (pid: {process['pid']}) uses more than {PROC_HIGH_MEM_MB} MB of memory ({mem_usage_gb:.2f} MM)",
                ident=process["pid"]
            )

#############################################################################
# Docker
#############################################################################
# If /var/lib/docker exists, do docker checks
if os.path.exists("/var/lib/docker/"):
    @monpy.check(minutely * 5, hourly)
    def docker_unhealthy():
        """
        Check for unhealthy containers.
        """
        for container in collectors.docker.containers():
            name = container['Name'].lstrip('/')
            if "Health" not in container["State"]:
                # No health check
                continue

            if container["State"]["Status"] == "exited" and container["State"]["ExitCode"] == 0:
                # Gracefully stopped
                continue

            health_status = container["State"]["Health"]["Status"]

            if health_status != "healthy":
                monpy.alert(
                   f"Container '{name}' is not healthy ({health_status})",
                    ident=container["Id"]
                )

    @monpy.check(hourly, daily)
    def docker_wildcard_bind():
        """
        Check for containers that bind ports on all interfaces (0.0.0.0), and
        are not configured in ALLOW_DOCKER_WILDCARD_BINDS. This bypasses the
        firewall
        """
        for container in collectors.docker.containers():
            if container["State"]["Running"] is not True:
                # We don't care of the container isn't running
                continue

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

    @monpy.check(hourly, daily)
    def docker_mount_socket():
        """
        Check if a docker container mounts the docker socket into it. This is a
        security smell
        """
        for container in collectors.docker.containers():
            if container["State"]["Running"] is not True:
                # We don't care of the contaiener isn't running
                continue

            container_name = container["Name"].lstrip("/")
            if container_name in ALLOW_CONTAINER_DOCKER_SOCKET:
                continue
            for mount in container["Mounts"]:
                if mount["Source"] == "/var/run/docker.sock":
                    monpy.alert(
                        f"Container '{container['Name'].lstrip('/')}' mounts the docker socket in the container",
                        ident=container_name
                    )

    @monpy.check(daily, daily)
    def docker_outdated():
        """
        Check for container updates
        """
        outdated_containers = []
        for container in collectors.docker.containers():
            monpy.log().debug("Checking container '%s' for updates", container["Name"].lstrip('/'))
            if collectors.docker.container_outdated(container):
                monpy.alert(
                    f"Container '{container['Name'].lstrip('/')}' has an update available",
                    ident=container["Name"]
                )

#############################################################################
# Network and website monitoring
#############################################################################
@monpy.check(minutely * 5, hourly, alert_after=2)
def host_ports_reachable():
    """
    Check configured host/ports to see if they are reachable
    """
    for host_port in HOST_PORTS_REACHABLE:
        try:
            hostname = host_port[0]
            port = host_port[1]
            reachable = collectors.net.tcp_connect(hostname, port, raise_exception=True)
        except (ConnectionRefusedError, TimeoutError) as err:
            monpy.alert(
                f"Host '{hostname}:{port}' unreachable: {str(err)}'",
                ident=f"{hostname}:{port}"
            )

@monpy.check(minutely * 5, hourly, alert_after=2)
def http_body():
    """
    Check sites and make sure they're responding with the right data
    """
    for check in HTTP_BODY_CHECKS:
        url, required_status, min_response_time, found_in_body = check
        res = collectors.net.http(url)

        if res["status"] != required_status:
            monpy.alert(
                f"URL '{url} returned status {res['status']}, while {required_status} was expected ({res['reason']})'",
                ident=f"status_{url}"
            )

        if res["response_sec"] > min_response_time:
            monpy.alert(
                f"URL '{url} responded slower than {min_response_time} seconds ({res['response_sec']} seconds)",
                ident=f"slow_{url}"
            )

        if found_in_body not in res["body"]:
            monpy.alert(
                f"URL '{url} response body didn't contain required text '{found_in_body}'",
                ident=f"body_{url}"
            )

@monpy.check(daily, daily)
def ssl_expire():
    """
    Check sites for expiring ssl certs
    """
    for check in SSL_CERT_CHECKS:
        host, port, days = check

        ssl_info = collectors.net.ssl_cert(host, port)
        subject = ssl_info["subject"]["commonName"]
        if ssl_info["expires_days"] <= days:
            monpy.alert(
                f"SSL certificate for '{host}:{port}' (CN={subject}) expires in {ssl_info['expires_days']} days ({ssl_info['not_after_dt']})",
                ident=f"{host}:{port}"
            )

@monpy.check(minutely * 15, daily)
def external_ip_changed():
    """
    Check if external outgoing IP has changed.
    """
    cur_external_ip = collectors.net.external_ip()

    with monpy.state("external_ip", {"ip": "unknown"}) as state:
        if state["ip"] != cur_external_ip:
            monpy.alert(
                f"External IP changed from '{state['ip']}' to '{cur_external_ip}'"
            )
        state["ip"] = cur_external_ip


#############################################################################
# Server problem and error reporting monitoring
#############################################################################
@monpy.check(hourly, daily)
def mail_in_spool():
    """
    Check if there is local mail in /var/spool/mail. This happens if the mail
    server cannot deliver mail
    """
    for file in collectors.files.files("/var/spool/mail"):
        if file["size"] > 0:
            monpy.alert(
                f"Mail found in /var/spool/mail for '{file['filename']}'",
                ident=file["filename"]
            )

@monpy.check(daily, daily)
def cron_mailto():
    """
    Check that crontabs contain a MAILTO so we're notified of problems when
    cronjobs fail
    """
    files = []
    files.append(collectors.files.file("/etc/crontab"))
    # FIXME
    #files.extend(collectors.files("/etc/cron.d"))
    files.extend(collectors.files.files("/var/spool/cron/crontabs"))

    for file in files:
        if collectors.files.egrep(file["path"], b".*MAILTO.*") is None:
            monpy.alert(
                f"Cron file '{file['path']}' has no MAILTO",
                ident=file["path"],
            )

@monpy.check(minutely * 5, daily)
def systemd_failed_units():
    """
    Check for systemd units / services in failed state
    """
    for unit in collectors.systemd.failed():
        monpy.alert(
            f"Systemd unit '{unit['unit']}' failed.",
            ident=unit["unit"]
        )

#############################################################################
# Security / Indicator of Compromise scans
#############################################################################
@monpy.check(daily, daily)
def high_uptime():
    """
    Check for high system uptime. Systems should be regularly rebooted
    """
    uptime = collectors.system.uptime()
    if uptime["uptime"] > UPTIME_DAYS * 24 * 60 * 60:
        monpy.alert(
            f"Uptime is higher than {UPTIME_DAYS} days"
        )

@monpy.check(hourly, daily, recheck_interval=minutely * 5)
def executables_in_tmp():
    """
    Check for executables in temp directories. These are indicators of system
    compromise (malware, coin miners)
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
        if not os.path.exists(temp_path):
            continue

        for file in collectors.files.files(temp_path, ftype='file', one_fs=False, on_error=error):
            is_exec = bool(file["mode"] & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
            if not is_exec:
                continue

            # Ignore Python standalone executables.
            # FIXME: Would be better to actually checvk for specific standalone
            # executables (such as 'borg'), but that's tricky for now.
            if "_MEI" in file["path"]:
                continue
            # Pyinfra may leave temp executables behind
            if file["path"].startswith("/tmp/pyinfra-sudo-askpass-"):
                continue

            monpy.alert(
                f"Executable found in temp dir: {file['path']}",
                ident=file["path"]
            )

@monpy.check(minutely, hourly)
def nftables_default_policy():
    """
    Check that the nftables firewall has default rules to drop input
    """
    input_4_dropped = False
    input_6_dropped = False

    for element in collectors.nftables.rulesets()["nftables"]:
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

@monpy.check(minutely * 5, hourly, alert_after=2)
def listening_ports():
    """
    Check all local ports that are listening on external (all) interfaces
    against an allowlist
    """
    listen_ports = []

    # Gather all ports that are listening on all interfaces
    for port in collectors.net.netstat():
        if port["state"] != "LISTEN":
            continue
        if port["local"][0] not in ["0.0.0.0", "::"]:
            continue

        listen_ports.append(port)

    # Check each port that listens on all interfaces to see if the executable
    # listening on the port is in the LISTEN_PORT_PROC_ALLOWED allow list
    for listen_port in listen_ports:
        addr = listen_port["local"][0]
        port_nr = listen_port["local"][1]
        # There can be more than one executable listening on the port (forks),
        # so build a list of them
        listen_exes = [process["exe"] for process in listen_port["processes"]]
        exe_allowed = LISTEN_PORT_PROC_ALLOWED.get(port_nr, None)

        if exe_allowed not in listen_exes:
            monpy.alert(
                f"Executables {listen_exes} not configured to be allowed to listen on port '{port_nr}'",
                ident=port_nr
            )

if SCAN_DEVICES_NETWORK is not False:
    @monpy.check(hourly, hourly)
    def network_devices():
        """
        Scan for new devices (MAC addresses) on a network
        """
        with monpy.state("devices", {}) as state:
            for device in collectors.net.devices(SCAN_DEVICES_NETWORK):
                monpy.log().debug(
                    "Found IP %s with MAC '%s' (hostname=%s, vendor=%s)",
                    device["ip"],
                    device["mac"],
                    device["hostname"],
                    device["vendor"]
                )
                if device["mac"] is None:
                    continue

                # Alert only once by keeping the mac in monpy status
                if device["mac"] not in state:
                    state[device["mac"]] = device
                    monpy.alert(
                        f"New device found on network '{SCAN_DEVICES_NETWORK}': {device['ip']} (hostname={device['hostname']}, vendor={device['vendor']}, mac={device['mac']})",
                        device["mac"]
                    )

            # Write CSV file of devices
            import csv
            headers = ["MAC", "IP", "Status", "hostname", "vendor"]

            csv_path = os.path.join(monpy.state_dir, "devices.csv")
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f, delimiter="\t")
                writer.writerow(headers)
                for device in state.values():
                    writer.writerow(
                        [
                            device["mac"],
                            device["ip"],
                            device["status"],
                            device["hostname"],
                            device["vendor"]
                        ]
                    )


@monpy.check(daily, daily)
def apt_security_updates_available():
    """
    Notify about security updates being available.

    NOTE that third-party repositories may push security updates as regular
    updates, which won't be shown here.
    """
    security_updates = [
        update
        for update in collectors.apt.updates()
        if update["security"] is True
    ]

    if security_updates:
        msg = "Security updates available:\n\n"
        msg += "\n".join(
            [
                f" - {update['name']} (from {update['cur_version']} to {update['new_version']})"
                for update in security_updates
            ]
        )
        monpy.alert(msg)

@monpy.check(hourly, daily)
def reboot_required():
    """
    Debian-derived systems touch /run/reboot-required when a package indicates
    that the system needs to be rebooted for the upgrade to fully take effect.
    """
    if collectors.apt.reboot_required() is True:
        monpy.alert(
            f"A reboot is required after updating packages."
        )

@monpy.check(hourly, hourly)
def checksums():
    """
    Check file changes using checksums.
    """
    for path, checksum in CHECKSUM_FILES:
        if collectors.files.checksum(path) != checksum:
            monpy.alert(
                f"Checksum for '{path}' didn't match",
                ident=path
            )

if CVE_KEYWORDS:
    @monpy.check(daily, daily, recheck_interval=minutely * 5)
    def new_cves():
        """
        Report on newly published CVEs for specific keywords.
        """

        for new_cve in collectors.cve.new():
            for keyword in [k.lower() for k in CVE_KEYWORDS]:
                if (
                    keyword in new_cve["title"].lower() or
                    keyword in new_cve["description"].lower() or
                    keyword in new_cve["vendor"].lower() or
                    keyword in new_cve["product"].lower()
                ):
                    from html import escape
                    monpy.alert(
                        f"<b><a href=\"{new_cve['url']}\">{new_cve['id']}</a>: " \
                        f"{escape(new_cve['vendor'])} - {escape(new_cve['product'])}</b>: " \
                        f"<i>{escape(new_cve['title'])}</i>: {escape(new_cve['description'])}",
                        ident=new_cve["id"],
                        alerter=alerter_cve
                    )

#############################################################################
# Log monitoring
#############################################################################
@monpy.check(minutely, minutely)
def log_nginx_bruteforce():
    """
    Check nginx logs for brute force attacks and ban the IP using nftables if
    an attack is detected. This requires your nftables config to have an
    `ip_block` set that bans IPs:

        table ip filter {
            set ip_block {
                type ipv4_addr
            }

            chain incoming {
                ip saddr @ip_block drop
            }
        }
    """
    if not LOG_NGINX_FILES:
        return

    sqlite_path = os.path.join(os.path.dirname(monpy.state_path), "buckets.sqlite3")
    bucket = Bucket(sqlite_path, "log_nginx_bruteforce")
    banned_this_check = []
    for log_path in LOG_NGINX_FILES:
        for request in collectors.files.log_watch(log_path, monpy, re_nginx):
            # Ignore based on IP
            if request["ip"] in LOG_NGINX_IGNORE_IPS:
                continue

            # Already banned this check
            if request['ip'] in banned_this_check:
                continue

            # Only ban for certain request statusses
            if request["status"] not in ("400", "401", "403", "404", "406", "408", "502"):
                continue

            # Increase counter for this ip
            ip_cnt = bucket.get(request["ip"], 0)
            bucket.set(request["ip"], ip_cnt + 1, commit=False)

            if ip_cnt >= LOG_NGINX_BAN_CNT:
                # Ban IP by adding it to the nft "ip_block" set
                proc = subprocess.run(
                    ["nft", "add", "element", "ip", "filter", "ip_block", f"{{ {request['ip']} }}"],
                    check=True
                )

                banned_this_check.append(request['ip'])

                msg = f"Banned IP '{request['ip']}' due to suspicious requests"
                monpy.log().warning(msg)

    # Forget IP after not seeing it for 4 hours
    bucket.vacuum(60 * 60 * 4)
    bucket.commit()

#############################################################################
# Misc stuff
#############################################################################
@monpy.check(daily, daily, recheck_interval=hourly)
def git_repo_status():
    """
    Check for out-of-date git repositories
    """
    for path in GIT_REPO_STATUS:
        repo = collectors.git.Repo(path, fetch=True)
        status = repo.status()
        if status["has_changes"] > 0:
            monpy.alert(
                f"Repo '{path}' has uncommited changes",
                ident=path
            )
        if status["ahead"] > 0:
            monpy.alert(
                f"Repo '{path}' is {status['ahead']} commits ahead of remote '{status['tracking_branch']}",
                ident=path
            )
        if status["behind"] > 0:
            monpy.alert(
                f"Repo '{path}' is {status['behind']} commits behind remote '{status['tracking_branch']}'",
                ident=path
            )

@monpy.check(daily, daily)
def python_venv_vulns():
    """
    Scan local python virtualenvs for installed vulnerable packages.
    """
    run = False
    try:
        PIPAUDIT_VENV_ROOTS
        if PIPAUDIT_VENV_ROOTS:
            run = True
    except NameError:
        pass

    if run is False:
        monpy.logger.info("PIPAUDIT_VENV_ROOT undefined or empty. Not auditing any Python virtualenvs for vulnerabilities")
        return

    # Find 'site-packages' directories in venv_path
    for venv_root in PIPAUDIT_VENV_ROOTS:
        for site_pkg_path in collectors.files.files(venv_root, name="site-packages"):
            venv_name = site_pkg_path["path"][len(venv_root):].split("/", 1)[0]
            for vuln in collectors.python.pip_audit(site_pkg_path["path"], PIPAUDIT_PATH):
                monpy.alert(
                    f"Package {vuln['name']} v{vuln['version']}' in virtualenv '{venv_name}' vulnerable (fixed in v{vuln['fixed']}): {vuln['vulnerability_id']} {vuln['description']}",
                    ident=f"{venv_name}_{vuln['name']}_{vuln['version']}"
                )


if os.path.exists("checks_local.py"):
    # Local only checks
    from checks_local import register
    register(monpy)

sys.exit(monpy.run())
