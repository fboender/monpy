#!/bin/env python3

import argparse
import logging
import os
import json
import time
import traceback
import sys


import collectors


__METADATA__ = {
    "name": "monpy",
    "version": "0.1",
    "author": "Ferry Boender",
    "author_email": "ferry.boender@gmail.com",
    "desc": "",
    "homepage": "https://github.com/fboender/monpy",
}
STATE_PATH = "/var/lib/monpy/state.json"


class Check:
    """
    Class that internally represents a check to be performed.

    This is not a class to derive checks from. Use the `MonPy.check` decorator
    for that.
    """
    def __init__(self, name, func, check_interval, alert_interval, force, alerter, no_alert, no_suppress, state):
        self.name = name
        self.func = func
        self.check_interval = check_interval
        self.alert_interval = alert_interval
        self.force = force              # Force run
        self.alerter = alerter          # Alerter class
        self.no_alert = no_alert        # Do not emmit alerts (--no-alert)
        self.no_suppress = no_suppress  # Ignore alert timeout
        self.state = state

        self.logger = logging.getLogger("monpy.check")

    def run(self):
        elapsed = int(time.time()) - self.state["last_run"]

        if self.force is False and elapsed < self.check_interval:
            self.logger.debug("Not running check '%s', interval (%s) not reached (%s)", self.name, self.check_interval, elapsed)
            return

        self.logger.info("Running check '%s'", self.name)
        return_value = None
        try:
            self.func()
        except Exception as err:
            return_value = err
            self.logger.exception(err)
            traceback.print_exc()

        self.state["last_run"] = int(time.time())

        return return_value

    def history(self, cur_value, hist_size, ident=None):
        if ident is None:
            ident = "_"

        history = self.state["history"].setdefault(ident, [])

        # Record current value and prune old ones
        history.append(cur_value)
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
        # FIXME: include ident in logging message
        if self.no_alert is True:
            self.logger.info(
                "Not sending alert (--no-alert) for '%s': %s",
                self.name,
                msg
            )
            return

        if ident is None:
            ident = "_"

        if alerter is None:
            alerter = self.alerter

        # Check when last alert was sent
        last_alert = self.state["alerts"].get(ident, 0)
        now = int(time.time())
        elapsed = now - last_alert

        if not self.no_suppress and elapsed < self.alert_interval:
            self.logger.info(
                "Supressing alert for '%s'. Alert interval (%ss) not reached (%ss elapsed). Alert: %s",
                self.name,
                self.alert_interval,
                elapsed,
                msg
            )
            return

        if alerter is None:
            self.logger.error(
                "Not sending alert (no alerter configured) for '%s': %s",
                self.name,
                msg
            )
            return

        self.logger.warning(
            "Sending alert (%s): %s",
            self.name,
            msg
        )
        alerter.alert(msg)

        self.state["alerts"][ident] = now

    def __repr__(self):
        return f"<{self.__class__.__name__} " \
               f"'{self.name}' " \
               f"check_interval={self.check_interval} " \
               f"alert_interval={self.alert_interval}" \
               ">"


class MonPy:
    def __init__(self, alerter=None, state_path=STATE_PATH):
        self.alerter = alerter
        self.state_path = state_path

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
        self.checks = []
        self.state = self._state_load()

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

        if self.alerter is None:
            self.logger.error("No alerter configured. Alerts will not be sent")

    def _state_load(self):
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

    def check(self, check_interval, alert_interval=0):
        """
        Function decorator to register a function as a monitoring check.

        `check_interval` determines how often to check (seconds).
        `alert_interval` determines how long to wait between alerts (seconds).
        0 means Always Alert.
        """
        def register_wrapper(func):
            name = func.__name__
            state = self.state["checks"].setdefault(
                name,
                {
                    "last_run": 0,
                    "alerts": {},
                    "history": {},
                }
            )
            check = Check(
                name,
                func,
                check_interval,
                alert_interval,
                self.args.force,
                self.alerter,
                self.args.no_alert,
                self.args.no_suppress,
                state
            )
            self.checks.append(check)
            self.logger.debug("Registered '%s'", check)

        return register_wrapper

    def history(self, cur_value, hist_size, ident=None):
        """
        Wrapper around Check.history for currently running check.
        """
        return self.current_check.history(cur_value, hist_size, ident=ident)

    def run(self):
        """
        Run all registered monitoring checks
        """
        exit_code = 0

        for check in self.checks:
            if self.args.check is not None and self.args.check != check.name:
                self.logger.debug("Not running check '%s' due to argument '%s'", check.name, self.args.check)
                continue

            self.current_check = check
            result = check.run()
            if result is not None:
                # Error occured
                exit_code = 1
            self.current_check = None

        self._state_save()
        sys.exit(exit_code)

    def alert(self, msg, ident=None, alerter=None):
        """
        Wrapper around Check.alert for currently running check.
        """
        self.current_check.alert(msg, ident, alerter)
