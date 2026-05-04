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
    def __init__(self, name, func, check_interval, alert_interval, last_run, force):
        self.name = name
        self.func = func
        self.check_interval = check_interval
        self.alert_interval = alert_interval
        self.last_run = last_run
        self.force = force

        self.logger = logging.getLogger("check")

    def run(self):
        elapsed = int(time.time()) - self.last_run

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

        self.last_run = int(time.time())

        return return_value

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

        self.checks = []
        self.state = self._state_load()
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
        self.logger = logging.getLogger(__package__)
        self.logger.setLevel(loglevel)
        self.logger.addHandler(handler)

        if self.alerter is None:
            self.logger.error("No alerter configured. Alerts will not be sent")

    def _state_load(self):
        try:
            with open(self.state_path, "r") as fh:
                state = json.load(fh)
                # Provide backwards compatibility with state file
                state.setdefault("checks", {})
                state.setdefault("alerts", {})
                state.setdefault("history", {})
                return state
        except FileNotFoundError:
            return {
                "checks": {},
                "alerts": {},
                "history": {}
            }

    def _state_save(self):
        state_dir = os.path.dirname(self.state_path)
        os.makedirs(state_dir, exist_ok=True)
        with open(self.state_path, "w") as fh:
            json.dump(self.state, fh)

    def _full_ident(self, ident):
        if ident is not None:
            return f"{self.current_check.name}__{ident}"
        else:
            return f"{self.current_check.name}"

    def check(self, check_interval, alert_interval=0):
        """
        Function decorator to register a function as a monitoring check.

        `check_interval` determines how often to check (seconds).
        `alert_interval` determines how long to wait between alerts (seconds).
        0 means Always Alert.
        """
        def register_wrapper(func):
            name = func.__name__
            check_state = self.state["checks"].setdefault(
                name,
                {
                    "last_run": 0,
                }
            )
            check = Check(
                name,
                func,
                check_interval,
                alert_interval,
                check_state["last_run"],
                force=self.args.force
            )
            self.checks.append(check)
            self.logger.debug("Registered check '%s' with interval %s", name, check_interval)

        return register_wrapper

    def history(self, cur_value, hist_size, ident=None):
        """
        Keep a history of last values for checks. Can be used to calculate, for
        instance, an average over a longer period of time.
        """
        full_ident = self._full_ident(ident)

        history = self.state["history"].setdefault(full_ident, [])
        history.append(cur_value)
        history = history[-hist_size:]
        self.state["history"][full_ident] = history

        return history

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

            # Save check state
            check_state = self.state["checks"][check.name]
            check_state["last_run"] = check.last_run

        self._state_save()
        sys.exit(exit_code)

    def alert(self, msg, ident=None):
        """
        Alert about a problem if alert_interval has been reached, using the
        configured alerter (`self.alerter`).
        """
        full_ident = self._full_ident(ident)
        last_alert = self.state["alerts"].get(full_ident, 0)
        now = int(time.time())
        elapsed = now - last_alert

        if not self.args.no_suppress and elapsed < self.current_check.alert_interval:
            self.logger.info(
                "Supressing alert for '%s'. Alert interval (%ss) not reached (%ss elapsed). Alert: %s",
                self.current_check.name,
                self.current_check.alert_interval,
                elapsed,
                msg
            )
            return

        if self.args.no_alert is True:
            self.logger.info(
                "Not sending alert (--no-alert) for '%s': %s",
                self.current_check.name,
                msg
            )
            return

        if self.alerter is None:
            self.logger.error(
                "Not sending alert (no alerter configured) for '%s': %s",
                self.current_check.name,
                msg
            )
            return

        self.logger.warning(
            "Sending alert (%s): %s",
            self.current_check.name,
            msg
        )
        self.alerter.alert(msg)
        self.state["alerts"][full_ident] = now
