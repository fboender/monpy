#!/bin/env python3

import argparse
import logging
import os
import json
import time
import traceback
import sys
import errno
import datetime
import sqlite3

from . import model
from monpy.collectors.system import uptime


__METADATA__ = {
    "name": "monpy",
    "version": "0.1",
    "author": "Ferry Boender",
    "author_email": "ferry.boender@gmail.com",
    "desc": "",
    "homepage": "https://github.com/fboender/monpy",
}
STATE_DIR = "/var/lib/monpy/"


class Lock:
    """
    Class to lock a file, to prevent multiple processes from writing to it at
    the same time.
    """
    def __init__(self, path):
        self.path = path

        self.logger = logging.getLogger("monpy.state")

    def lock(self, wait=None):
        """
        Lock the path. Returns True if the file was locked, otherwise returns
        the PID of the processes that's keeping the lock.

        If `wait` is specified, wait for `wait` seconds if locked and try
        again. If still locked after that, fail.
        """
        while True:
            other_pid = self.is_locked()
            if not other_pid:
                # Not locked
                break
            elif wait is None:
                # Locked. Process already running under other PID. Don't try
                # again.
                return other_pid
            else:
                # Locked. Wait for `wait` seconds and try again
                self.logger.info(
                    "Lock file '%s' is locked. Waiting for %s seconds before trying again",
                    self.path,
                    wait
                )
                time.sleep(wait)
                wait = None

        our_pid = os.getpid()
        with open(self.path, 'w') as pidfile:
            pidfile.write(str(our_pid))
            pidfile.flush()

        return True

    def unlock(self):
        os.unlink(self.path)

    def is_locked(self):
        """
        Return `False` if process not yet locked. Return the PID of the other
        process if it is locked.
        """
        if not os.path.exists(self.path):
            return False

        with open(self.path, 'r') as pidfile:
            try:
                pid = int(pidfile.read().strip())
                assert pid != 0
            except Exception:
                # Something's wrong with the pidfile. Remove it
                unlock(self.path)
                return False

            if self._is_pid_running(pid):
                return pid
            else:
                # PID isn't running, but the lock file was still present. Maybe the
                # process crashed? Remove PID file and pretend it wasn't locked.
                self.unlock()
                return False

    def _is_pid_running(self, pid):
        try:
            os.kill(pid, 0)
        except OSError as err:
            if err.errno == errno.ESRCH:
                return False
            elif err.errno == errno.EPERM:
                return True
            else:
                # According to "man 2 kill" possible error values are
                # (EINVAL, EPERM, ESRCH)
                raise
        else:
            return True


class Maintenance:
    """
    Read maintenance info from disk
    """
    def __init__(self, state_dir, maintenance_max):
        self.state_dir = state_dir
        self.maintenance_max = maintenance_max

        self.maintenance_path = os.path.join(self.state_dir, "maintenance")
        self.logger = logging.getLogger("monpy.maintenance")
        self.maintenance = {}
        self._load()

    def _load(self):
        """
        Load all maintenances from disk.
        """
        if not os.path.exists(self.maintenance_path):
            self.logger.debug("No maintenance active")
            return

        now = datetime.datetime.now()
        for fname in os.listdir(self.maintenance_path):
            path = os.path.join(self.maintenance_path, fname)
            stat = os.stat(path)
            mtime = datetime.datetime.fromtimestamp(stat.st_mtime)

            until = None
            with open(path, "r") as fh:
                content = fh.read().strip()
                if content != "":
                    until = datetime.datetime.strptime(content, "%Y-%m-%d %H:%M:%S")

            # Check if maintenance time has exceeded the max time. If so,
            # ignore the maintenance.
            if (now - mtime).total_seconds() > self.maintenance_max:
                self.logger.warning("Maximum maintenance time for %s has been exceeded", fname)
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

        for key in ["ALL", check_name]:
            if key in self.maintenance:
                maintenance = self.maintenance[key]

                # Check for longest maintenance time
                until = maintenance["until"]
                if until is None or until > now:
                    active_maintenance = maintenance

        return active_maintenance


class MonPy:
    def __init__(self, alerter=None, reporter=None, state_dir=STATE_DIR,
                 lock_wait=None, prune_check_age=86400*2,
                 prune_alert_age=86400*2, boot_wait=60*2,
                 maintenance_max=3600):
        """
        Main MonPy class that orchestrates the running of checks, alerting and
        reporting.

        If `alerter` is specified, MonPy will send alerts via that alerter. It
        should be an instance of a class with an `alert()` method with
        signature:

            def alert(self, msg, check_name):
                ...

        If `reporter` is specified, MonPy will call it after a completed run.
        If should be an instance of a class with a method with signature:

            def render(self, state):
                ...

        If `state_dir` is specified, that dir will be used to store check and
        alert state.  Otherwise the default will be used.

        If `lock_wait` (int or float) is specified, MonPy will wait `lock_wait`
        seconds and retry in case the state file is locked.

        `prune_check_age` is the number of seconds after which the state of
        unseen checks are pruned.

        `prune_alert_age` is the number of seconds after which old alerts are
        pruned.

        `boot_wait` delays running checks for X seconds after the system has
        rebooted. This is to prevent false-positives such as unhealthy services
        that haven't started properly yet after a reboot.

        `maintenance_max` is the maximum amount of time all (or a specific)
        checks can be in maintenance. If it is exceeded, the maintenance will
        be ignored.
        """
        self.alerter = alerter
        self.reporter = reporter
        self.state_dir = state_dir
        self.state_path = os.path.join(self.state_dir, "state.sqlite3")
        self.lock_wait = lock_wait
        self.prune_check_age = prune_check_age
        self.prune_alert_age = prune_alert_age
        self.boot_wait = boot_wait
        self.maintenance_max = maintenance_max

        self.checks = []

        # Reference to currently running check (self.run()), so that the check
        # can call `monpy.history()` and `monpy.alert()` and we know which
        # check is calling it.
        self.current_check = None

        parser = argparse.ArgumentParser(prog=__METADATA__["name"],
                                         description=__METADATA__["desc"])
        parser.add_argument("--version",
                            action="version",
                            version="%(prog)s {}".format(__METADATA__["version"]))
        parser.add_argument("-v", "--verbose",
                            action="count",
                            default=0,
                            help="Verbosity. May be specified multiple \
                                  times (-vvv)")
        parser.add_argument("-f", "--force",
                            dest="force",
                            action="store_true",
                            default=False,
                            help="Force checks to run")
        parser.add_argument("--no-alert",
                            dest="no_alert",
                            action="store_true",
                            default=False,
                            help="Don't send alerts (see them using -vvv)")
        parser.add_argument("--no-suppress",
                            dest="no_suppress",
                            action="store_true",
                            default=False,
                            help="Ignore alert interval and do not suppress alerts")
        parser.add_argument('--log-file',
                            metavar='PATH',
                            dest='log_file',
                            type=str,
                            default=None,
                            help='Log to file. If not given, log to stderr')
        parser.add_argument("check",
                            metavar="CHECK",
                            type=str,
                            nargs="?",
                            help="Check to run. If not given, runs all checks")

        self.args = parser.parse_args()

        # Configure application logging
        loglevel = logging.CRITICAL - ((self.args.verbose + 1) * 10)
        if loglevel > logging.ERROR:
            loglevel = logging.ERROR
        if loglevel < logging.DEBUG:
            loglevel = logging.DEBUG

        # Configure application logging
        if self.args.log_file is None:
            handler = logging.StreamHandler()
        else:
            handler = logging.FileHandler(self.args.log_file)
        fmt = '%(asctime)s %(levelname)8s %(name)s | %(message)s'
        formatter = logging.Formatter(fmt)
        handler.setFormatter(formatter)
        self.logger = logging.getLogger("monpy")
        self.logger.setLevel(loglevel)
        self.logger.addHandler(handler)

        self.maintenance = Maintenance(self.state_dir, self.maintenance_max)

        # Connect to state database
        conn = sqlite3.connect(self.state_path)
        conn.row_factory = sqlite3.Row
        model.init_db(conn)

    def _register(self, func, check_interval, alert_interval=0, alert_after=1,
                 recheck_interval=None):
        """
        Register a check function.

        It is preferred to use the MonPy.check() decorator instead of this
        method, unless you want to do special things.
        """
        name = func.__name__
        desc = ""
        if func.__doc__ is not None:
            desc = " ".join([s.strip() for s in func.__doc__.strip().splitlines()])

        check = model.Check(
            name=name,
            func=func,
            desc=desc,
            check_interval=check_interval,
            recheck_interval=recheck_interval,
            alert_interval=alert_interval,
            alert_after=alert_after,
            alerter=self.alerter,
            force=self.args.force,
            no_alert=self.args.no_alert,
            no_suppress=self.args.no_suppress
        )
        self.checks.append(check)
        self.logger.debug("Registered '%s'", check)

    def check(self, check_interval, alert_interval=0, alert_after=1,
              recheck_interval=None):
        """
        Function decorator to register a function as a monitoring check.

        `check_interval` determines how often to check (seconds).

        `alert_interval` determines how long to wait between alerts (seconds).
        0 will always alert.

        Alerts will be supressed until the check alerts `alert_after` times in
        a row. Default is 1, which will alert immediately. If the check
        recoveres before reaching `alert_after`, the alert counter will be
        reset and no alert will be sent. Note that this interacts with the
        `check_interval` value. If `check_interval` is 5 minutes and
        `alert_after` is 2, an alert won't be sent for 10 minutes.

        If there is an active alert and `recheck_interval` is not None, the
        check will run more frequently (at every `recheck_interval`).
        """
        def register_wrapper(func):
            self._register(
                func,
                check_interval,
                alert_interval=alert_interval,
                alert_after=alert_after,
                recheck_interval=recheck_interval
            )

        return register_wrapper

    def run(self):
        """
        Attempt to run all registered monitoring checks.
        """
        exit_code = 0

        # Check system uptime and don't run checks if system has just rebooted
        uptime_sec = uptime()["uptime"]
        if uptime_sec < self.boot_wait:
            self.logger.info(
                "System uptime (%ss) smaller than boot_wait (%ss). Not running checks.",
                uptime_sec,
                self.boot_wait
            )
            return 0

        # Last run of MonPy itself (not a check)
        last_run_start = datetime.datetime.now()
        self.logger.info("Starting run...")

        for check in self.checks:
            if self.args.check is not None and self.args.check != check.name:
                self.logger.debug("Not running check '%s' due to argument '%s'", check.name, self.args.check)
                continue

            maintenance = self.maintenance.active(check.name)
            if maintenance is not False:
                self.logger.debug("Not running check '%s' due to maintenance (until %s)", check.name, maintenance["until"] or "forever")
                continue

            # Register current check so the check can call `monpy.history()`, etc.
            self.current_check = check

            # Run the check
            result = check.run()
            if result is not None:
                # Error occured
                exit_code = 1
            self.current_check = None

        # Clean up some stuff
        model.prune_checks(self.prune_check_age)
        model.prune_alerts(self.prune_alert_age)

        last_run_end = datetime.datetime.now()
        duration = (last_run_end - last_run_start).total_seconds()
        self.logger.info("Ending run. Duration: %ss", duration)

        # Save state
        model.update_run_state(last_run_start, last_run_end)
        model.conn.commit()

        # Call reporter
        if self.reporter is not None:
            self.logger.info("Calling reporter '%s'", self.reporter)
            self.reporter.render()

        return exit_code

    def alert(self, msg, ident=None, alerter=None):
        """
        Send an alert.

        The optional `ident` uniquely identifies the alert within a single
        check, allowing for multiple different alerts per check.

        If `alerter` is specified, the alert is sent via that alerter.
        Otherwise the default configgered alerter is used.

        Usage:

            @monpy.check(60, 3600)
            def some_check():
                cpu = "cpu0"
                monpy.alert(f"High CPU usage on {cpu}", cpu)
        """
        self.current_check.alert(msg, ident, alerter)

    def log(self):
        """
        Returns an instance of the current check's logger, which checks can use
        to log custom messages.

            @monpy.check(60, 3600)
            def some_check():
                monpy.log().debug("Debug message")
        """
        return self.current_check.logger

    def state(self, ident, default):
        """
        Store and retrieve custom states that are preserved between invocations
        of MonPy.

        `ident` uniquely identifies the custom state. It is not bound to a
        check, so you can use a single state in multiple checks.

        If not state for `ident` is found, `default` is used.

        You can store any JSON-serializable state.

        This method is a context. To use it:

            with monpy.state("mystate", {}) as state:
                state["curval"] = 10
        """
        return model.CustomState(ident, default)
