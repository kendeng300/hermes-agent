"""Private POSIX supervisor for cron pre-run scripts.

The scheduler starts this helper in a fresh session and passes the real script
argv after ``--``.  On Linux the helper becomes a child subreaper before it
starts the script, so a double-forked or ``setsid`` descendant is reparented
here rather than escaping when its wrapper exits.  The helper writes only the
script return code to the private result descriptor; script stdout and stderr
remain the scheduler's ordinary capture pipes.
"""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
import threading
import time

_CLEANUP_SECONDS = 1.5
_PR_SET_CHILD_SUBREAPER = 36


def _enable_linux_subreaper() -> None:
    """Fail before script spawn if Linux cannot establish containment."""
    if not sys.platform.startswith("linux"):
        return
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _live_children():
    import psutil

    try:
        children = psutil.Process(os.getpid()).children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return []
    live = []
    for child in children:
        try:
            if child.is_running() and child.status() != psutil.STATUS_ZOMBIE:
                live.append(child)
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    return live


def _reap_orphans(target_pid: int) -> None:
    """Reap direct adopted children without stealing Popen's target wait."""
    import psutil

    try:
        direct = psutil.Process(os.getpid()).children(recursive=False)
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return
    for child in direct:
        if child.pid == target_pid:
            continue
        try:
            os.waitpid(child.pid, os.WNOHANG)
        except (ChildProcessError, ProcessLookupError, OSError):
            pass


def _cleanup(target: subprocess.Popen) -> bool:
    """Kill the target tree to a fixed point and reap adopted descendants."""
    import psutil

    deadline = time.monotonic() + _CLEANUP_SECONDS
    while time.monotonic() < deadline:
        children = _live_children()
        if not children:
            break
        # psutil validates PID birth identity before signalling.  Kill all
        # observed ancestors and descendants, then enumerate again so a fork
        # racing the first pass is adopted and included in the next pass.
        for child in children:
            try:
                child.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                pass
        try:
            target.wait(timeout=0.02)
        except (subprocess.TimeoutExpired, ChildProcessError, OSError):
            pass
        _reap_orphans(target.pid)
        time.sleep(0.01)

    try:
        target.wait(timeout=max(0.0, deadline - time.monotonic()))
    except (subprocess.TimeoutExpired, ChildProcessError, OSError):
        pass
    _reap_orphans(target.pid)
    return not _live_children()


def main() -> int:
    if len(sys.argv) < 4 or sys.argv[2] != "--":
        return 125
    try:
        result_fd = int(sys.argv[1])
    except ValueError:
        return 125

    _enable_linux_subreaper()
    stopping = threading.Event()

    def _request_stop(_signum, _frame) -> None:
        stopping.set()

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    target = subprocess.Popen(sys.argv[3:])
    returncode = None
    try:
        while not stopping.wait(0.02):
            returncode = target.poll()
            if returncode is not None:
                break
    finally:
        clean = _cleanup(target)

    if stopping.is_set() or not clean or returncode is None:
        return 124
    os.write(result_fd, f"{returncode}\n".encode("ascii"))
    os.close(result_fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
