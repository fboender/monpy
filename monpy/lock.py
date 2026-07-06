import os
import time
import logging
import errno


class Lock:
    """
    Class to lock a file, to prevent multiple processes from writing to it at
    the same time.
    """
    def __init__(self, path):
        self.path = path

        self.logger = logging.getLogger(__name__)

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
                self.unlock(self.path)
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

