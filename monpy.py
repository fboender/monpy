#!/bin/env python3

import argparse
import logging
import os
import json
import time
import traceback
import sys
import errno


__METADATA__ = {
    "name": "monpy",
    "version": "0.1",
    "author": "Ferry Boender",
    "author_email": "ferry.boender@gmail.com",
    "desc": "",
    "homepage": "https://github.com/fboender/monpy",
}
STATE_PATH = "/var/lib/monpy/state.json"


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


class Check:
    """
    Class that internally represents a check to be performed.

    This is not a class to derive checks from. Use the `MonPy.check` decorator
    for that.
    """
    def __init__(self, name, func, desc, check_interval, alert_interval,
                 alert_after, recheck_interval, force, alerter, no_alert,
                 no_suppress, state):
        self.name = name
        self.func = func
        self.desc = desc
        self.check_interval = check_interval
        self.alert_interval = alert_interval
        self.alert_after = alert_after
        self.recheck_interval = recheck_interval
        self.force = force              # Force run
        self.alerter = alerter          # Alerter class
        self.no_alert = no_alert        # Do not emmit alerts (--no-alert)
        self.no_suppress = no_suppress  # Ignore alert timeout
        self.state = state
        self.alerted = False

        # Save intervals in state. Purely informational so that Reporters can
        # use them
        self.state["desc"] = desc
        self.state["check_interval"] = check_interval
        self.state["recheck_interval"] = recheck_interval
        self.state["alert_interval"] = alert_interval

        # Register when we last saw this check (even if it didn't run)
        self.state["last_seen"] = int(time.time())

        self.logger = logging.getLogger(f"monpy.check.{self.name}")

    def run(self):
        """
        Run this check, if `check_interval` has been reached. If
        `recheck_interval` is specified, and there is an active alert, also run
        the check when `recheck_interal` has been reached.
        """
        now = int(time.time())
        elapsed = now - self.state["last_run_start"]
        check_interval_reached = elapsed >= self.check_interval

        # If `recheck_interval` is specified, and there is an active alert, run
        # the check if `recheck_interval` has been reached.
        recheck_interval_reached = False
        if self.recheck_interval is not None and self.active_alerts():
            recheck_interval_reached = elapsed >= self.recheck_interval

        if self.force is False and not (check_interval_reached or recheck_interval_reached):
            self.logger.debug(
                "Not running check '%s', interval (%s, recheck=%s) not reached (%s)",
                self.name,
                self.check_interval,
                self.recheck_interval,
                elapsed
            )
            return

        self.state["last_run_start"] = now
        self.logger.info("Running check '%s'", self.name)
        return_value = None
        try:
            self.func()
        except Exception as err:
            return_value = err
            self.logger.exception("Exception while running check '%s': %s", self.name, err)
            traceback.print_exc()

        if self.alerted is False:
            # No alerts during this check. Reset alert_count for all alerts
            for alert_ident, alert_state in self.state["alerts"].items():
                if "alert_count" in alert_state:
                    alert_state.pop("alert_count")

        self.state["last_run_end"] = int(time.time())

        return return_value

    def history(self, cur_value, hist_size, ident=None):
        """
        Keep a list of check metrics in between invocations.

        `cur_val` is the current measured value. `hist_size` determines the max
        size of the history to keep. Older entries are evicted.

        `ident` can be specified to keep multiple different histories in a
        single check.
        """
        if ident is None:
            ident = "_"

        history = self.state["history"].setdefault(ident, [])
        history.append(cur_value)

        # Prune old history values
        self.state["history"][ident] = history[-hist_size:]

        return history

    def alert(self, msg, ident=None, alerter=None):
        """
        Alert about a problem if alert_interval has been reached, using the
        configured alerter (`self.alerter`).

        You can have different alerts within the same check by providing an
        `ident`.

        If `alerter` is specified, use that alerter instead of `self.alerter`.
        """
        if ident is None:
            ident = "_"

        if alerter is None:
            alerter = self.alerter

        now = int(time.time())
        default_alert_state = {
            "time_seen": 0,
            "time_sent": 0,
            "msg": msg,
        }
        alert_state = self.state["alerts"].setdefault(ident, default_alert_state)
        alert_state["time_seen"] = now

        # Don't alert until `alert_after` alerts
        self.alerted = True  # So we can clear alert count in run() if not alerted
        alert_state["alert_count"] = alert_state.get("alert_count", 0) + 1
        if alert_state["alert_count"] < self.alert_after:
            self.logger.info(
                "Not alerting for '%s.%s' because alert count not reached (%s/%s)",
                self.name,
                ident,
                alert_state["alert_count"],
                self.alert_after
            )
            return

        if self.no_alert is True:
            self.logger.info(
                "Not sending alert (--no-alert) for '%s.%s': %s",
                self.name,
                ident,
                msg
            )
            return

        # Check when last alert was sent
        last_alert_sent = alert_state["time_sent"]
        elapsed = now - last_alert_sent

        if not self.no_suppress and elapsed < self.alert_interval:
            self.logger.info(
                "Supressing alert for '%s.%s'. Alert interval (%ss) not reached (%ss elapsed). Alert: %s",
                self.name,
                ident,
                self.alert_interval,
                elapsed,
                msg
            )
            return

        if alerter is None:
            self.logger.error(
                "Not sending alert (no alerter configured) for '%s.%s': %s",
                self.name,
                ident,
                msg
            )
            return

        self.logger.warning(
            "Sending alert (%s.%s): %s",
            self.name,
            ident,
            msg
        )
        alerter.alert(msg, self.name)

        alert_state["time_sent"] = now
        alert_state["msg"] = msg

    def active_alerts(self):
        active_alerts = []
        for alert in self.state["alerts"].values():
            # If the last time an alert was seen was on or after the last time
            # the check was run the alert is currently active
            if alert["time_seen"] >= self.state["last_run_start"]:
                active_alerts.append(alert)

        return active_alerts

    def __repr__(self):
        return f"<{self.__class__.__name__} " \
               f"'{self.name}' " \
               f"check_interval={self.check_interval} " \
               f"alert_interval={self.alert_interval}" \
               ">"


class MonPy:
    def __init__(self, alerter=None, reporter=None, state_path=STATE_PATH,
                 lock_wait=None, prune_check_age=86400*2):
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

        If `state_path` is specified, that path will be used as the state file.
        Otherwise the default will be used.

        If `lock_wait` (int or float) is specified, MonPy will wait `lock_wait`
        seconds and retry in case the state file is locked.

        `prune_check_age` is the number of seconds after which the state of
        unseen checks are pruned.
        """
        self.alerter = alerter
        self.reporter = reporter
        self.state_path = state_path
        self.lock_wait = lock_wait
        self.prune_check_age = prune_check_age
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

        self.state_path_lock = f"{self.state_path}.lock"
        self.locker = Lock(self.state_path_lock)
        self.state = self._state_load()

        if self.alerter is None:
            self.logger.error("No alerter configured. Alerts will not be sent")

    def _state_load(self):
        locked = self.locker.lock(wait=self.lock_wait)
        if locked is not True:
            raise RuntimeError(f"'{self.state_path}' is locked by another instance. If this is wrong, remote the '{self.state_path_lock}' file.")

        try:
            with open(self.state_path, "r") as fh:
                state = json.load(fh)
                if "history" in state:
                    raise RuntimeError(f"Old '{self.state_path}' format detected. Delete it first")
                return state
        except FileNotFoundError:
            return {
                "checks": {},
            }

    def _state_save(self):
        state_dir = os.path.dirname(self.state_path)
        os.makedirs(state_dir, exist_ok=True)
        with open(self.state_path, "w") as fh:
            json.dump(self.state, fh)
        self.locker.unlock()

    def register(self, func, check_interval, alert_interval=0, alert_after=1,
                 recheck_interval=None):
        """
        Register a check function. It is preferred to use the MonPy.check()
        decorator instead of this method, unless you want to do special things.
        """
        name = func.__name__
        desc = ""
        if func.__doc__ is not None:
            desc = " ".join([s.strip() for s in func.__doc__.strip().splitlines()])
        state = self.state["checks"].setdefault(
            name,
            {
                "last_run_start": 0,
                "last_run_end": 0,
                "alerts": {},
                "history": {},
            }
        )
        check = Check(
            name,
            func,
            desc,
            check_interval,
            alert_interval,
            alert_after,
            recheck_interval,
            self.args.force,
            self.alerter,
            self.args.no_alert,
            self.args.no_suppress,
            state
        )
        self.checks.append(check)
        self.logger.debug("Registered '%s'", check)

    def check(self, check_interval, alert_interval=0, alert_after=1,
              recheck_interval=None):
        """
        Function decorator to register a function as a monitoring check.

        `check_interval` determines how often to check (seconds).

        `alert_interval` determines how long to wait between alerts (seconds).
        0 means Always Alert.

        Alerts will be supressed until the check alerts `alert_after` times in
        a row. Default is 1, which will alert immediately. If the check
        recoveres before reaching `alert_after`, the alert counter will be
        reset and no alert will be sent. Note that this interacts with the
        `check_interval` value. If `check_interval` is 5 minutes and
        `alert_after` is 2, an alert won't be sent for 10 minutes.
        """
        def register_wrapper(func):
            self.register(
                func,
                check_interval,
                alert_interval=alert_interval,
                alert_after=alert_after,
                recheck_interval=recheck_interval
            )

        return register_wrapper

    def run(self):
        """
        Run all registered monitoring checks
        """
        exit_code = 0
        status = self.state.setdefault("status", {})
        # Last run of MonPy itself (not a check)
        status["last_run_start"] = int(time.time())

        #seen_checks = []     TEMP DISABLED, SEE BELOW
        for check in self.checks:
            #seen_checks.append(check.name)  TEMP DISABLED, SEE BELOW

            if self.args.check is not None and self.args.check != check.name:
                self.logger.debug("Not running check '%s' due to argument '%s'", check.name, self.args.check)
                continue

            # Register current check so the check can call `monpy.history()`, etc.
            self.current_check = check
            result = check.run()
            if result is not None:
                # Error occured
                exit_code = 1
            self.current_check = None

        status["last_run_end"] = int(time.time())

        # Clean unseen checks. This happens when a check is renamed or removed.
        # If we haven't seen a check for `self.prune_check_age` seconds, remove
        # it from the state.
        del_checks = []
        now = int(time.time())
        for check_name, check_state in self.state["checks"].items():
            last_seen = check_state.get("last_seen", 0)
            if last_seen < (now - self.prune_check_age):
                del_checks.append(check_name)
        for del_check in del_checks:
            self.state["checks"].pop(del_check)

        self._state_save()

        # Call reporter
        if self.reporter is not None:
            self.logger.info("Calling reporter '%s'", self.reporter)
            self.reporter.render(self.state)

        return exit_code

    def history(self, cur_value, hist_size, ident=None):
        """
        Wrapper around Check.history for currently running check.
        """
        return self.current_check.history(cur_value, hist_size, ident=ident)

    def alert(self, msg, ident=None, alerter=None):
        """
        Wrapper around Check.alert for currently running check.
        """
        self.current_check.alert(msg, ident, alerter)
