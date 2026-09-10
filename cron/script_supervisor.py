"""Private POSIX supervisor for cron pre-run scripts.

The scheduler starts this helper in a fresh session and passes the real script
argv after ``--``.  The helper becomes a child subreaper before it starts the
script, so a double-forked or ``setsid`` descendant is reparented here rather
than escaping when its wrapper exits.  The private control descriptor carries
the target PID plus Linux birth identity and, after cleanup, its return code.
Script stdout and stderr remain the scheduler's ordinary capture pipes.
"""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

_CLEANUP_SECONDS = 1.5
_PR_SET_CHILD_SUBREAPER = 36


def _enable_linux_subreaper() -> None:
    """Fail before script spawn if Linux cannot establish containment."""
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _children():
    import psutil

    try:
        return psutil.Process(os.getpid()).children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return []


def _birth_identity(pid: int) -> int:
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    return int(stat.rsplit(")", 1)[1].split()[19])


def _has_live_children() -> bool:
    import psutil

    for child in _children():
        try:
            if child.is_running() and child.status() != psutil.STATUS_ZOMBIE:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    return False


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
    """Stop, kill, and reap owned descendants before this owner exits."""
    import psutil

    deadline = time.monotonic() + _CLEANUP_SECONDS
    while time.monotonic() < deadline:
        children = _children()
        if not children:
            break
        # First stop every known process.  Stopped parents cannot win a fork
        # race while the second ancestry read discovers their last children.
        for child in children:
            try:
                if child.is_running() and child.status() != psutil.STATUS_ZOMBIE:
                    child.suspend()
            except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
                pass
        children = _children()
        # psutil Process validates birth identity immediately before signal.
        # Descendants die before this supervisor/containment owner exits.
        for child in reversed(children):
            try:
                if child.is_running() and child.status() != psutil.STATUS_ZOMBIE:
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
    return not _has_live_children()


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
    target = subprocess.Popen(sys.argv[3:], start_new_session=True)
    returncode = None
    try:
        os.write(
            result_fd,
            f"START {target.pid} {_birth_identity(target.pid)}\n".encode("ascii"),
        )
        while not stopping.wait(0.02):
            returncode = target.poll()
            if returncode is not None:
                break
    finally:
        clean = _cleanup(target)

    if stopping.is_set() or not clean or returncode is None:
        return 124
    os.write(result_fd, f"RESULT {returncode}\n".encode("ascii"))
    os.close(result_fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
