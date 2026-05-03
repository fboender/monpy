import os
import stat
import fnmatch
import errno
import re
import mmap


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
            'filename': 'passwd',
            'dir': '/etc/',
            'path': '/etc/passwd',
            'type': 'file',
            'size': 2790,
            'mode': 33188,
            'uid': 0,
            'gid': 0,
            'device': 64769
        }
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
        "size": fstat.st_size,
        "mode": fstat.st_mode,
        "uid": fstat.st_uid,
        "gid": fstat.st_gid,
        "device": fstat.st_dev,
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

