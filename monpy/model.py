import datetime
import logging
import traceback
import json

SCHEMAS = [
    """
        CREATE TABLE IF NOT EXISTS "monpy" (
            key               TEXT,
            value             TEXT,

            PRIMARY KEY (key)
        );
    """,
    """
        CREATE TABLE IF NOT EXISTS "checks" (
            name              TEXT,
            desc              TEXT,
            last_seen         DATETIME,
            last_run_start    DATETIME,
            last_run_end      DATETIME,
            check_interval    INTEGER,
            recheck_interval  INTEGER,
            alert_interval    INTEGER,

            PRIMARY KEY (name)
        );
    """,
    """
        CREATE TABLE IF NOT EXISTS "alerts" (
            check_name        TEXT,
            ident             TEXT,
            msg               TEXT,
            count             INTEGER,
            last_seen         DATETIME,
            last_sent         DATETIME,

            PRIMARY KEY (check_name, ident)
        );
    """,
    """
        CREATE TABLE IF NOT EXISTS "custom_state" (
            check_name        TEXT,
            ident             TEXT,
            last_seen         DATETIME,
            state             TEXT,

            PRIMARY KEY (check_name, ident)
        );
    """,
    """
        -- ident can be NULL, in which case sqlite3 doesn't enforce uniqueness. It does
        -- for empty strings.
        CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_ident
        ON alerts (
            check_name,
            COALESCE(ident, '')
        );
    """,
]
# Handler to the state database connection. Set via `register_db_conn()`.
conn = None


def str_to_dt(s):
    """
    Convert string to datetime.
    """
    if s is not None:
        return datetime.datetime.fromisoformat(s)
    else:
        return None


def dt_to_str(dt):
    """
    Convert datetime to string.
    """
    if dt is not None:
        return str(dt)
    else:
        return None


class Check:
    def __init__(self, name, func, desc, check_interval, recheck_interval,
                 alert_interval, alert_after, alerter, force, no_alert,
                 no_suppress):
        self.logger = logging.getLogger(f"monpy.check.{name}")

        # Check information
        self.name = name
        self.func = func
        self.desc = desc
        self.check_interval = check_interval
        self.recheck_interval = recheck_interval
        self.alert_interval = alert_interval
        self.alert_after = alert_after
        self.alerter = alerter

        # Commandline flags
        self.force = force
        self.no_alert = no_alert
        self.no_suppress = no_suppress

        # Default state if check doesn't exist in the database
        self.last_seen = None
        self.last_run_start = None
        self.last_run_end = None

        self._load()

        self.last_seen = datetime.datetime.now()

    def _load(self):
        """
        Load the check's state from the database if it exists.
        """
        cur = conn.cursor()
        qry = "SELECT * FROM checks WHERE name = ?"
        cur.execute(qry, (self.name, ))
        row = cur.fetchone()
        if row is not None:
            row_dict = dict(row)
            self.last_seen = str_to_dt(row_dict["last_seen"])
            self.last_run_start = str_to_dt(row_dict["last_run_start"])
            self.last_run_end = str_to_dt(row_dict["last_run_end"])

    def _save(self):
        """
        Save the checks's state to the database
        """
        cur = conn.cursor()
        qry = """
            INSERT INTO checks
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                desc = excluded.desc,
                last_seen = excluded.last_seen,
                last_run_start = excluded.last_run_start,
                last_run_end = excluded.last_run_end,
                check_interval = excluded.check_interval,
                recheck_interval = excluded.recheck_interval,
                alert_interval = excluded.alert_interval
            ;
        """
        cur.execute(
            qry,
            (
                self.name,
                self.desc,
                dt_to_str(self.last_seen),
                dt_to_str(self.last_run_start),
                dt_to_str(self.last_run_end),
                self.check_interval,
                self.recheck_interval,
                self.alert_interval
            )
        )

    def should_check(self, now):
        """
        Determine whether this check should be executed or not.

        This depends on commandline flag and the check's state such as when it
        last ran, etc.

        Returns `True` is the check should execute, or `False` if not.
        """
        # --force?
        if self.force is True:
            return True

        # Never ran before?
        if self.last_run_start is None:
            return True

        # Nr of seconds since last run
        elapsed = (now - self.last_run_start).total_seconds()

        # Check if recheck_interval is specified and if there are any active
        # alerts
        if self.recheck_interval is not None and self.active_alerts():
            # Check if recheck_interval has been reached since last run
            if elapsed >= self.recheck_interval:
                return True

        # Check if check_interval has been reached since last run
        if elapsed >= self.check_interval:
            return True

        self.logger.debug(
            "Not running check '%s': Interval (%ss) not reached (%ss)",
            self.name,
            self.check_interval,
            int(elapsed)
        )

        return False

    def run(self):
        """
        Run this check if `check_interval` has been reached. If
        `recheck_interval` is specified, and there is an active alert, also run
        the check when `recheck_interal` has been reached.
        """
        now = datetime.datetime.now()
        self.last_seen = now

        should_check = self.should_check(now)
        if should_check is True:
            self.last_run_start = datetime.datetime.now()
            self.logger.info("Running check '%s'", self.name)
            return_value = None
            try:
                self.func()
            except Exception as err:
                return_value = err
                self.logger.exception("Exception while running check '%s': %s", self.name, err)
                traceback.print_exc()
            finally:
                self._save()
            self.last_run_end = datetime.datetime.now()
        self.reset_alert_count()
        self._save()

    def alert(self, msg, ident=None, alerter=None):
        """
        Alert about a problem if alert_interval has been reached, using the
        configured alerter (`self.alerter`).

        You can have different alerts within the same check by providing an
        `ident`.

        If `alerter` is specified, use that alerter instead of `self.alerter`.
        """
        if alerter is None:
            alerter = self.alerter

        alert = Alert(
            alerter,
            self.name,
            ident,
            msg,
            self.alert_interval,
            self.alert_after,
            self.no_alert,
            self.no_suppress
        )
        alert.alert()

    def reset_alert_count(self):
        """
        Reset the alert count for all alerts that have not been triggered this
        run to 0.
        """
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE alerts SET
                count = 0
            WHERE
                check_name = ? AND
                last_seen < ?
            """,
            (
                self.name,
                self.last_seen
            )
        )

    def active_alerts(self):
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM alerts
            WHERE
                check_name = ? AND
                last_seen >= ?
            """,
            (
                self.name,
                self.last_run_start
            )
        )
        return [dict(r) for r in cur]

    def __repr__(self):
        return f"<{self.__class__.__name__} " \
               f"'{self.name}' " \
               f"check_interval={self.check_interval} " \
               f"alert_interval={self.alert_interval}" \
               ">"

class Alert:
    def __init__(self, alerter, check_name, ident, msg, alert_interval,
                 alert_after, no_alert, no_suppress):
        self.logger = logging.getLogger(f"monpy.alert.{check_name}")

        self.alerter = alerter

        # Alert info
        self.check_name = check_name
        self.ident = ident
        self.msg = msg
        self.alert_interval = alert_interval
        self.alert_after = alert_after

        # Default state if alert doesn't exist in the database
        self.count = 0
        self.last_seen = None
        self.last_sent = None

        # Commandline flags
        self.no_alert = no_alert
        self.no_suppress = no_suppress

        self._load()

        self.count += 1
        self.last_seen = datetime.datetime.now()

    def _load(self):
        """
        Load the alert's state from the database if it exists.
        """
        cur = conn.cursor()
        if self.ident is None:
            cur.execute(
                "SELECT * FROM alerts WHERE check_name = ? AND ident is NULL",
                (
                    self.check_name,
                )
            )
        else:
            cur.execute(
                "SELECT * FROM alerts WHERE check_name = ? AND ident = ?",
                (
                    self.check_name,
                    self.ident
                )
            )
        row = cur.fetchone()
        if row is not None:
            row_dict = dict(row)
            self.count = row_dict["count"]
            self.last_seen = str_to_dt(row_dict["last_seen"])
            self.last_sent = str_to_dt(row_dict["last_sent"])

    def _save(self):
        """
        Save the alert's state to the database
        """
        cur = conn.cursor()
        qry = """
            INSERT INTO alerts
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(check_name, COALESCE(ident, '')) DO UPDATE SET
                msg = excluded.msg,
                count = excluded.count,
                last_seen = excluded.last_seen,
                last_sent = excluded.last_sent
            ;
        """
        cur.execute(
            qry,
            (
                self.check_name,
                self.ident,
                self.msg,
                self.count,
                dt_to_str(self.last_seen),
                dt_to_str(self.last_sent)
            )
        )

    def should_alert(self):
        """
        Determine whether an alert should be sent or not.

        This depends on commandline flags, alert_count, etc.

        Returns `True` is an alert should be sent, or `False` if not.
        """
        no_alert_reason = ""

        if self.alerter is None:
            no_alert_reason = "No alerter configured"
        elif self.count < self.alert_after:
            no_alert_reason = "Alert count not reached"
        elif self.no_alert is True:
            no_alert_reason = "--no-alert specified"
        else:
            if self.last_sent is None:
                # Never sent
                return True
            elif self.no_suppress is True:
                # --no-suppress provided
                return True

            # Check if alert time has elapsed
            now = datetime.datetime.now()
            elapsed = (now - self.last_sent).total_seconds()
            if elapsed < self.alert_interval:
                no_alert_reason = f"Alert interval ({self.alert_interval}s) not reached ({elapsed:.0f}s)"
            else:
                # Interval reached
                return True

        # Log a message about why we didn't alert
        if self.ident is not None:
            full_ident = f"{self.check_name}.{self.ident}"
        else:
            full_ident = self.check_name
        self.logger.info(
            "Not alerting for '%s': %s",
            full_ident,
            no_alert_reason
        )
        return False

    def alert(self):
        """
        Check whether an alert should be sent and if so, send it.
        """
        self.logger.warning(
            "Alert (%s.%s): %s",
            self.check_name,
            self.ident,
            self.msg.replace("\n", "\\n")
        )
        if self.should_alert() is True:
            self.logger.warning("Sending alert...")
            self.alerter.alert(self.msg, self.check_name)
            self.last_sent = datetime.datetime.now()

        self._save()

    def __repr__(self):
        return f"<{self.__class__.__name__} " \
               f"'{self.check_name}' " \
               f"ident='{self.ident}'>"


class CustomState:
    """
    Store and retrieve custom states that are preserved in between invocations
    of MonPy.

    `ident` uniquely identifies the custom state. It is not bound to a check,
    so you can use a single state in multiple checks.

    If not state for `ident` is found, `default` is used.
    """
    def __init__(self, check_name, ident, default):
        self.check_name = check_name
        self.ident = ident
        self.default = default

    def __enter__(self):
        cur = conn.cursor()
        cur.execute(
            """
            SELECT state FROM custom_state WHERE check_name = ? AND ident = ?
            """,
            (
                self.check_name,
                self.ident,
            )
        )
        row = cur.fetchone()
        if row is not None:
            self.state = json.loads(row[0])
        else:
            self.state = self.default

        return self.state

    def __exit__(self, exc_type, exc_value, traceback):
        now = datetime.datetime.now()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO custom_state VALUES (?, ?, ?, ?)
            ON CONFLICT(check_name, ident) DO UPDATE SET
                last_seen = excluded.last_seen,
                state = excluded.state
            """,
            (
                self.check_name,
                self.ident,
                dt_to_str(now),
                json.dumps(self.state)
            )
        )


def update_run_state(last_run_start, last_run_end):
    """
    Update informational run start / end.
    """
    cur = conn.cursor()
    qry = "INSERT INTO monpy VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value"
    cur.execute(qry, ("last_run_start", dt_to_str(last_run_start)))
    cur.execute(qry, ("last_run_end", dt_to_str(last_run_end)))


def prune_checks(age):
    """
    Prune unseen checks. This happens when a check is renamed or removed.  If
    we haven't seen a check for `age` seconds, remove it (and its alerts) from
    the db.
    """
    # Get checks that should be pruned
    cutoff_dt = datetime.datetime.now() - datetime.timedelta(seconds=age)
    cur = conn.cursor()
    cur.execute('SELECT name FROM checks WHERE last_seen <= ?', (cutoff_dt, ))
    delete_checks = [row[0] for row in cur]

    # Delete alerts and checks
    for delete_check in delete_checks:
        cur.execute('DELETE FROM alerts WHERE check_name = ?', (delete_check, ))
        cur.execute('DELETE FROM custom_state WHERE check_name = ?', (delete_check, ))
        cur.execute('DELETE FROM checks WHERE name = ?', (delete_check, ))


def prune_alerts(age):
    """
    Prune old alerts. This happens when an alert hasn't been seen or sent for
    `age` seconds.
    """
    cutoff_dt = datetime.datetime.now() - datetime.timedelta(seconds=age)
    cur = conn.cursor()
    cur.execute('DELETE FROM alerts WHERE last_seen <= ?', (cutoff_dt, ))


def init_db(db_conn):
    """
    Register a handler to the state database in this module namespace and
    create schema if required. This is called by the MonPy class.
    """
    global conn
    conn = db_conn
    cur = conn.cursor()
    for schema in SCHEMAS:
        cur.execute(schema)
