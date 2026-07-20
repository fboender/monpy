<!-- TOC -->
* [About](#about)
    * [Why](#why)
* [Getting started](#getting-started)
    * [Installation](#installation)
    * [Usage](#usage)
* [Status](#status)
* [Components](#components)
    * [MonPy class](#monpy-class)
    * [The `check()` decorator](#the-`check()`-decorator)
    * [Collectors](#collectors)
    * [Alerters](#alerters)
    * [Reporters](#reporters)
* [How-to](#how-to)
    * [Run check at specific time](#run-check-at-specific-time)
    * [Maintenance](#maintenance)
    * [Include checks from other file](#include-checks-from-other-file)
* [License and contributing](#license-and-contributing)
<!-- EOTOC -->

# About

MonPy is a system, security and performance monitoring tool where you write
checks in Python instead of some declarative markup language or via a web UI.
Simple, fast and powerful. No external libraries required, only a Python
installation.

MonPy provides tooling to easily write checks, generate alerts and keep custom
state. Various useful data [collectors](#collectors) are provided
out-of-the-box.

Rather than calling some commandline tool or binary, with MonPy you write a
Python script that defines what and how to monitor things. You run this script
to actually perform the monitoring.

See [`checks.py`](checks.py) for examples of what's possible and how to write
checks.

## Why

As an SRE with over 20 year of experience, I have found that the vast majority
of monitoring tools prioritize fancy dashboards and graphs over precise
monitoring and alerts. They make it easy to add tons of out-of-the-box metrics
about services, but make it difficult - if not impossible - to add a simple
exception to a specific monitoring check or alert.

MonPy takes a different approach. Checks are written in plain Python code,
making it easy to reason about the logic and simple to add actual things you
care about. For example, you'd want to know if any of your disks have less
than 10% disk space available, unless that disk is huge and 10% still means
dozens of free gigabytes. MonPy easily allows you to add simple or complex
exceptions.

MonPy heavily prioritizes alerting over dashboard and metrics (which often
offer little to no additional benefit over system or application logging).
Alerts keep being sent until the problem has actually been solved (or you just
stop monitoring pointless things).

With checks being written in a real, powerful programming language, you can
monitor basically everything you could ever care about. From system / docker
container health and log file monitoring to security problems such as new CVEs
for your stack and Indicators of Compromise, or website response times.

Finally, since MonPy monitoring scripts are just plain old code, you can
easily distribute them to various systems and environments using any old
deployment strategy. Use standard methods of configuration to tailor the
scripts to a specific environment.


# Getting started

## Installation

MonPy is tested with Python v3.10.12+. Older versions may work, but it is not
guaranteed.

To install MonPy:

    $ sudo pip3 install git+https://github.com/fboender/monpy

If you get a "`This environment is externally managed`" error, you can safely
override that warning, since MonPy does not come with any additional
requirements or external libraries:

    $ sudo pip3 install --break-system-packages git+https://github.com/fboender/monpy

If you'd rather not do that, you can instead create a virtualenv:

    $ virtualenv monpy
    $ monpy/bin/pip3 install git+https://github.com/fboender/monpy

To run a MonPy monitoring script, you'll have to refer to the `python3`
interpreter in that virtualenv, either through direct invocation:

    $ monpy/bin/python3 checks.py -v

Or by changing the shebang in the script to:

    #!/path/to/monpy/bin/python3

## Usage

MonPy is used as a Python library from a custom monitoring script. A simple
example (`checks.py`):

    #!/bin/env python3

    import sys
    from monpy import MonPy
    from monpy import collectors
    from monpy.alerters import Pushover

    alerter = Pushover("USER_TOKEN", "APP_TOKEN")
    monpy = MonPy(alerter=alerter)

    @monpy.check(60, 3600)
    def low_mem_available():
        mem_info = collectors.system.memory()
        if mem_info["mem_available_perc"] < 10:
            monpy.alert("Less than 10% memory available")

    sys.exit(monpy.run())

You execute the script to perform the monitoring checks:

    $ python3 checks.py -vvv
    2026-06-13 04:33:25,473    DEBUG monpy.maintenance | No maintenance active
    2026-06-13 04:33:25,474    DEBUG monpy | Registered '<Check 'low_mem_available' check_interval=60 alert_interval=3600>'
    2026-06-13 04:33:25,474     INFO monpy | Starting run...
    2026-06-13 04:33:25,474     INFO monpy.check.low_mem_available | Running check 'low_mem_available'
    2026-06-13 04:33:25,475  WARNING monpy.alert.low_mem_available | Alert (low_mem_available.None): Less than 10% memory available
    2026-06-13 04:33:25,475  WARNING monpy.alert.low_mem_available | Sending alert...
    2026-06-13 04:33:25,476     INFO monpy | Ending run. Duration: 0.001342s

The script works as follows:

1. We import the main `MonPy` orchestrator class, the
   [collectors](#collectors) and an alert method
   ([Pushover](https://pushover.net/))
1. The alerter and `MonPy` instance are configured
1. We define a check `low_mem_available` using the `@monpy.check` decorator.
   The first argument is the `check_interval`, which we set to every 60
   seconds. The second argument specifies the `alert_interval`. This
   determines how often we alert about a problem. In this case, once an hour
1. The `low_mem_available` check uses the `system.memory` collector to
   retrieve information about the current memory status, and checks that at
   least 10% memory is available. If not, it issues an alert.
1. Finally, we execute the `monpy.run()` method, which will run the actual
   checks. Its exit code is returned to the calling parent process using
   `sys.exit()`.

If we run the script again before `check_interval` is reached, the
`low_mem_available` check will not run:

    2026-06-13 04:43:41,187    DEBUG monpy.check.low_mem_available | Not running check 'low_mem_available': Interval (60s) not reached (2s)

We can ignore the `check_interval` and force checks to run using the `-f`
(force) parameter. You can also specify a specific check to run:

    $ python3 check.py -vvv -f low_mem_available
    2026-06-13 04:46:15,105     INFO monpy.check.low_mem_available | Running check 'low_mem_available'
    2026-06-13 04:46:15,106  WARNING monpy.alert.low_mem_available | Alert (low_mem_available.None): Less than 10% memory available
    2026-06-13 04:46:15,106     INFO monpy.alert.low_mem_available | Not alerting for 'low_mem_available': Alert interval (3600s) not reached (18s)

Argument parsing is handled by the `MonPy` orchestrator class. Full usage:

    usage: monpy [-h] [--version] [-v] [-f] [--no-alert] [--no-suppress]
                 [--log-file PATH]
                 [CHECK]

    MonPy is a system, security and performance monitoring tool where you write
    checks in Python instead of some declarative markup language or via a web UI.
    Simple, fast and powerful. No external libraries required, only a Python
    installation.

    positional arguments:
      CHECK            Check to run. If not given, runs all checks that have
                       reached their check_interval

    options:
      -h, --help       show this help message and exit
      --version        show program's version number and exit
      -v, --verbose    Verbosity. May be specified multiple times (-vvv)
      -f, --force      Force checks to run
      --no-alert       Don't send alerts (see them using -vvv)
      --no-suppress    Ignore alert interval and do not suppress alerts
      --log-file PATH  Log to file. If not given, log to stderr

A cronjob can be used to run the script every minute:

    * * * * * cd /opt/monpy && ./checks.py -v --log-file /var/log/monpy.log

See [`checks.py`](checks.py) for more examples of what's possible and how to
write checks.

# Status

This project is currently in active development, and is not considered stable.

MonPy is a personal project, designed and maintained for my own needs. It's
provided AS IS, in the hopes that it will be useful to someone else.

It is unlikely I will implement feature requests or provide substantial
support for this project, beyond my own needs. There is no desire to grow this
project beyond its current scope.

I do not accept contributions for this project.

If you find MonPy useful and would like to see it grow into something bigger
and better, feel free to fork and rename the project.

# Components

## MonPy class

The `MonPy` class is the main orchestrator. It registers checks (using the
[`Monpy.check()`](#the-check-decorator)), alerters and reporters. It executes
checks, handlers maintenance and state and sends alerts:

* `MonPy.check()`: Decorator function for registering checks.
* `MonPy.alert()`: Send alerts if `alert_interval` has been reached for the
  alert.
* `MonPy.state()`: Keep custom state for checks.
* `MonPy.log()`: Check logging instance

Definition:

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

## The `check()` decorator

Checks are written in Python as functions decorated with the `MonPy.check()`
decorator:

    def check(self, check_interval=60, alert_interval=0, alert_after=1,
              recheck_interval=None):
        """
        Function decorator to register a function as a monitoring check.

        `check_interval` determines how often to check (seconds).

        `alert_interval` determines how long to wait between alerts (seconds).
        0 will alert every check, if there is a problem.

        Alerts will be supressed until the check alerts `alert_after` times in
        a row. Default is 1, which will alert immediately. If the check
        recoveres before reaching `alert_after`, the alert counter will be
        reset and no alert will be sent. Note that this interacts with the
        `check_interval` value. If `check_interval` is 5 minutes and
        `alert_after` is 2, an alert won't be sent for 10 minutes.

        If there is an active alert and `recheck_interval` is not None, the
        check will run more frequently (at every `recheck_interval`).
        """

## Collectors

Various [collectors](monpy/monpy/collectors/) are provided:

* **[system](monpy/collectors/system.py)**: Memory, CPU, temperature, process and disk information.
* **[net](monpy/collectors/net.py)**: TCP connections, http, SSL and external otugoing IP information.
* **[files](monpy/collectors/files.py)**: File information, including a `find`-like method, grep, log watcher and file content checksummer.
* **[systemd](monpy/collectors/systemd.py)**: Systemd unit, timer and mount information, including degraded units.
* **[docker](monpy/collectors/docker.py)**: Various docker inspection tools, including container information and whether containers have updates.
* **[nftables](monpy/collectors/nftables.py)**: Nftables ruleset information.
* **[apt](monpy/collectors/apt.py)**: APT package status: whether updates are available and whether the system requires a reboot.
* **[git](monpy/collectors/git.py)**: Git repo information such as status, log, fetch and fast forwarding.
* **[cve](monpy/collectors/cve.py)**: CVE monitoring.
* **[nginx](monpy/collectors/nginx.py)**: Nginx status monitoring.
* **[python](monpy/collectors/python.py)**: Python virtualenv security auditing.

## Alerters

There are currently two alerters:

* `StdErr`: Writes alerts to stderr
* `Pushover`: Sends alerts via pushover

Alerters can be configured globally when instantiating the MonPy instance:

    alerter = Pushover(PUSHOVER_USER_TOKEN, PUSHOVER_APP_TOKEN)
    monpy = MonPy(alerter=alerter)

You can use a custom alerter when issuing an alert:

    customer_alerter = StdErr()
    monpy.alert(
        "test alter",
        alerter=customer_alerter
    )

## Reporters

At the end of a run, you can generate a report about the current status. At
the moment, only a HTML reporter is available. To use it:

    from reporters import HTML
    reporter = HTML(out_path="/var/lib/monpy/report.html")
    monpy = MonPy(reporter=reporter)

Output example:

![html report](contrib/report_html.png)

# How-to

## Run check at specific time

MonPy is designed to run checks periodically, not at a specific time. If you
want to run checks at a specific time, create a separate check script and use
cron to schedule it at the proper time:

    # check_daily_at_08_30.py
    @monpy.check(0, 0)
    def test():
        [...]

Cron entry:

    # Run at 08:30 every day
    30 8 * * * cd /opt/apps/monpy && ./check_daily_at_08_30.py

You can also check the time manually in a check:

    import datetime
    
    @monpy.check(minutely, minutely)
    def test_specific_time():
        now = datetime.datetime.now()
        if now.hour != 8 or now.minute != 30:
            # Only run at 08:30
            return

        ...

## Maintenance

Maintenance can be activated by creating a directory `maintenance` in the
state dir and creating files in it. By default this would be
`/var/lib/monpy/maintenance`. 

If a file `ALL` exists in this directory, all checks will be put in
maintenance. If a file exists that matches a check name, only that check will
be put into maintenance. Checks that are in maintenance will not be executed.

Files can (but don't need to) contain a timestamp in the form of `YYYY-MM-DD
HH:MM:SS` to specify the time until which the maintenance is active. For
example:

    $ date +"%Y-%m-%d %H:%M:%S" -d "+1 hour" > /var/lib/monpy/maintenance/ALL
 
You can pass a `maintenance_max` parameter to the `MonPy` instance, which will
determine the maximum time for a maintenance period. The default is 3600
seconds (1 hour). This is measured from the `mtime` of a maintenance file.

## Include checks from other file

If you'd like to structure your checks over multiple files, you can do so
using a wrapper. In your main file:

    # Import code from security.py
    from security import register as security_register

    # Register MonPy checks found in securitypy
    security_register(monpy)

In `security.py`:

    from collectors import log_watch

    def register(monpy):
        @monpy.check(60, 60)
        def app_log_watch():
            for line in log_watch("/path/to/server.log"):
                if "ALERT" in line:
                    monpy.alert("ALERT found in log file: {line}")

If you want more control over the checks from another file, you can use
closures and manual registration with MonPy instead of using the decorator.
For example, in an imported file:

    def test_undecorated(monpy):
        def inner():
            monpy.alert("Alert from undecorated")
        return inner

Then in your main checks file, you can register it manually:

    from external import test_undecorated
    monpy.register(test_undecorated(monpy), minutely, hourly)

# License and contributing

MonPy is released under the [MIT License](LICENSE.txt).

I do not take contributions to this project. See the [Status](#status) chapter
for more information.
