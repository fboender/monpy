import os
import stat
import fnmatch
import errno
import re
import mmap
import logging
import hashlib


file_types = {
    4096: "fifo",
    8192: "char",
    16384: "dir",
    24576: "block",
    32768: "file",
    40960: "link",
    49152: "socket",
}

def file(path):
    """
    Return file information on `path`. Example output:

        {
            "filename": "passwd",
            "dir": "/etc",
            "path": "/etc/passwd",
            "type": "file",
            "mode": 33188,
            "uid": 0,
            "gid": 0,
            "size": 3137,
            "inode": 12060272,
            "atime": 1778070601.4110885,
            "mtime": 1770810161.1919982,
            "ctime": 1770810161.1940932,
            "device": 64512,
            "nlink": 1
    """
    fname = os.path.basename(path)
    fdir = os.path.dirname(path)
    fstat = os.lstat(path)
    ftype = file_types.get(stat.S_IFMT(fstat.st_mode), "unknown")

    return {
        "filename": fname,
        "dir": fdir,
        "path": path,
        "type": ftype,
        "inode": fstat.st_ino,
        "size": fstat.st_size,
        "atime": fstat.st_atime,
        "mtime": fstat.st_mtime,
        "ctime": fstat.st_ctime,
        "mode": fstat.st_mode,
        "uid": fstat.st_uid,
        "gid": fstat.st_gid,
        "device": fstat.st_dev,
        "nlink": fstat.st_nlink
    }


def files(root_dir, name=None, path=None, ftype=None, min_size=None,
         max_size=None, uid=None, gid=None, perm=None, depth=None,
         one_fs=True, absolute=False, follow_links=False, on_error=None):
    """
    Recursively find files and directories matching certain criteria.

    Basically the unix `find` command, but for Python. For each file that
    matches the criteria, a dict is yielded containing some basic information
    about that file (as returned by `file()`.

    `root_dir` is the starting directory from which to find files.

    If `name` is provided, only files matching the given shell globbing pattern
    will be included.

    If `path` is provided, the same is done but for the file's entire path.

    `ftype` can be used to limit the files to a certain type. Valid values are
    'fifo', 'char', 'dir', 'block', 'file', 'link', 'socket'.

    `min_size` and `max_size` limit files to those who's size is >= `min_size`
    and <= `max_size` respectively.

    `uid` and `gid` limit files to those that match the given owner user and
    group id (integers).

    `perm` is a permissions bitmask (see the `stat.S_IXXX` constants), which
    limits the files to those whoms mode has all the bits in the bitmask set.

    `depth` determines how deep to scan. E.g. `depth=2` will only scan two
    directories deep (relative to `root_dir`).

    `one_fs` limits the scan to the same file system / device that `root_dir`
    is on.

    If `absolute` is set to True, `dirs` and `path` will be made absolute
    (relative to the `/` directory).

    If `follow_links` is set to True, symlinks to dirs will be recursed into,
    as long as the real path lies under `root_dir`. This can lead to endless
    loops. It is disabled by default.

    `on_error` is a callable which will be called when an error occurs. It
    should receive two parameters: the full path to the dir/file that caused
    the problem and the exception. If `on_error` is None (default), an
    exception is raised instead.

    This function yields one dict per file in the form as returned by
    `file()`. The yielded values should *not* be modified, otherwise
    behaviour is unspecified.

    Examples:

    Ignore errors:

        find('/etc', on_error=lambda cur_dir, err: None)

    Find files that are owned by root and have the SUID bit set:

        find('/usr/bin', uid=0, perm=stat.S_ISUID)
    """
    # Figure out device which root_dir is on, so we can honor `one_fs`
    root_stat = os.stat(root_dir)
    root_dev = root_stat.st_dev

    # Stack with dirs we still need to visit
    stack = []
    stack.append(root_dir)

    while stack:
        cur_dir = stack.pop(0)
        if absolute is True:
            cur_dir = os.path.abspath(cur_dir)

        try:
            for fname in os.listdir(cur_dir):
                fpath = os.path.join(cur_dir, fname)
                try:
                    fileinfo = file(fpath)
                except Exception as err:
                    if on_error is None:
                        raise
                    else:
                        on_error(fpath, err)
                        continue

                if (
                    (name is None or fnmatch.fnmatch(fname, name)) and
                    (path is None or fnmatch.fnmatch(fpath, path)) and
                    (ftype is None or ftype == fileinfo["type"]) and
                    (min_size is None or fileinfo["size"] >= min_size) and
                    (max_size is None or fileinfo["size"] <= max_size) and
                    (uid is None or fileinfo["uid"] == uid) and
                    (gid is None or fileinfo["gid"] == gid) and
                    (perm is None or fileinfo["mode"] & perm == perm)
                ):
                    yield fileinfo

                # Recurse into dir?
                if (
                    fileinfo["type"] == "dir" or
                    (
                        follow_links is True and
                        fileinfo["type"] == "link" and
                        os.path.isdir(fileinfo["path"]) and
                        fileinfo["path"].startswith(root_dir)
                    )
                ):
                    this_depth = fpath.lstrip(os.path.sep).count(os.path.sep)
                    depth_reached = depth is not None and this_depth >= depth
                    same_fs = one_fs is False or fileinfo["device"] == root_dev
                    if (not depth_reached and same_fs):
                        stack.append(fileinfo["path"])
        except Exception as err:
            if on_error is None:
                raise
            else:
                on_error(cur_dir, err)

def egrep(path, regex):
    """
    Grep for regex `regex` in file `path`. It uses memory mapping, so it should
    be reasonably fast.

    `regex` may be both a compiled regexp (`re.compile()`), or a string.

    Files are opened in binary mode, so the regexp must also be binary (e.g.
    `b".*foo.*"`). Symlinks are not dereferrenced. Since `egrep` uses memory
    mapping, this will fail on symlinks.

    Returns match objects.
    """
    with open(path, "rb") as f:
        if hasattr(regex, 'search'):
            return regex.search(mmap.mmap(f.fileno(),
                                          0,
                                          access=mmap.ACCESS_READ))
        else:
            return re.search(regex, mmap.mmap(f.fileno(),
                                              0,
                                              access=mmap.ACCESS_READ))

def _find_inode_in_dir(inode, dir):
    for file_info in files(dir, depth=1):
        if file_info["inode"] == inode:
            return file_info["path"]

def log_watch(path, monpy, parse_regex=None, from_top=False):
    """
    Yield unseen lines in `path`. If `path` has been rotated, an attempt will
    be made to find the file it was rotated to, and the unseen lines will be
    yielded.

    `monpy` is a reference to the `MonPy()` instance, so we can track the
    state of the file (lines seen).

    if `parse_regex` is supplied, we'll use the regex to parse each log line
    and yield the resulting match. Lines not matching the regexp will cause a
    WARNNIG log message but will otherwise be ignored.

    If this is the first time we see a file, and `from_top` is True, than the
    entire file is yielded. Otherwise (the default), we start from the end of
    the file.
    """
    logger = logging.getLogger("monpy." + __name__)
    logger.debug("Inspecting log file '%s'", path)
    try:
        file_info = file(path)
        # FIXME: Remove from state
    except FileNotFoundError:
        logger.warning("Log file not found: '%s'. Continuing with next log file", path)
        return

    state = monpy.current_check.state

    # Create "log_watch" key if not present
    if not "log_watch" in state:
        state["log_watch"] = {}

    # Get current log state for path, or set if not set
    if path in state["log_watch"]:
        log_state = state["log_watch"][path]
    else:
        # Log file never seen.
        log_state = state["log_watch"][path] = {
            "inode": file_info["inode"]
        }
        if from_top is True:
            log_state["pos"] = 0
        else:
            # Start at end of file
            log_state["pos"] = file_info["size"]

    # Keep a list of log files and their positions that we should process
    logs = []

    # Check if the inode in the current log state is the same as on disk. If
    # not, the file has been rotated or deleted
    if log_state["inode"] is not None and log_state["inode"] != file_info["inode"]:
        # Log file rotated. Find path to inode in log dir for rotated file
        prev_log_path = _find_inode_in_dir(log_state["inode"], os.path.dirname(path))
        if prev_log_path is not None:
            # Rotated log file found in current dir. Add to the list of logs to
            # process
            logs.append((prev_log_path, log_state["pos"]))

        # Reset log pos so we start yielding from the top of the new log file
        log_state["pos"] = 0

    # Add current (or new) log file to the list of logs to process
    logs.append((path, log_state["pos"]))

    # Process queued log files
    for log_file, log_pos in logs:
        with open(log_file, "r") as fh:
            # Register inode of current log file and add to log processing queue
            log_state["inode"] = file_info["inode"]
            fh.seek(log_pos)
            for line in fh.readlines():
                if parse_regex is not None:
                    match = re.match(parse_regex, line)
                    if match:
                        yield match.groupdict()
                    else:
                        logger.warning("RegEx didn't match line: %s", line)
                else:
                    yield line

            # Register last position in log file in state
            log_state["pos"] = fh.tell()

def checksum(path):
    """
    Generate sha256 hash of file contents.

    You can do the same from the commandline with:

        $ sha256sum ~/.bashrc
        ee2565b9b0f2d10e566df1d2661acf638cace964dc89bd8ab339c69c144e0840  /home/fboender/.bashrc
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()
