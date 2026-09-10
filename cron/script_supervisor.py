"""Linux subreaper used to contain cron pre-run script process trees.

Only owner-local ``/proc/<pid>/task/*/children`` edges are traversed. Every
PID is paired with its Linux start-time ticks before use and revalidated before
signal delivery; no host-wide process-table census is performed.
"""

from __future__ import annotations

import ctypes
import enum
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

_CLEANUP_SECONDS = 1.5
_PR_SET_CHILD_SUBREAPER = 36


class Probe(enum.Enum):
    PRESENT = "PRESENT"
    GONE = "GONE"
    UNKNOWN = "UNKNOWN"


class Cleanup(enum.Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    start_ticks: int
    parent_pid: int
    state: str


def _enable_linux_subreaper() -> None:
    """Fail before script spawn if Linux cannot establish containment."""
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(_PR_SET_CHILD_SUBREAPER, 1, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def _read_identity(pid: int) -> tuple[Probe, ProcessIdentity | None]:
    """Read one PID's birth identity; uncertainty is distinct from absence."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    except (FileNotFoundError, ProcessLookupError):
        return Probe.GONE, None
    except (PermissionError, OSError):
        return Probe.UNKNOWN, None
    try:
        fields = stat.rsplit(")", 1)[1].split()
        identity = ProcessIdentity(pid, int(fields[19]), int(fields[1]), fields[0])
    except (IndexError, ValueError):
        return Probe.UNKNOWN, None
    if identity.state == "Z":
        return Probe.GONE, identity
    return Probe.PRESENT, identity


def _task_children(pid: int) -> tuple[Probe, set[int]]:
    """Return only children named by an owned process's task children files."""
    task_root = Path("/proc/self/task" if pid == os.getpid() else f"/proc/{pid}/task")
    try:
        tasks = tuple(task_root.iterdir())
    except (FileNotFoundError, ProcessLookupError):
        return Probe.GONE, set()
    except (PermissionError, OSError):
        return Probe.UNKNOWN, set()
    children: set[int] = set()
    for task in tasks:
        try:
            words = (task / "children").read_text(encoding="ascii").split()
            children.update(int(word) for word in words)
        except (FileNotFoundError, ProcessLookupError):
            return Probe.UNKNOWN, set()
        except (PermissionError, OSError, ValueError):
            return Probe.UNKNOWN, set()
    return Probe.PRESENT, children


def _owned_census() -> tuple[Probe, list[ProcessIdentity]]:
    """Traverse the supervisor-owned descendant graph without global scans."""
    root = os.getpid()
    queue = [root]
    seen = {root}
    identities: list[ProcessIdentity] = []
    while queue:
        parent = queue.pop(0)
        state, child_pids = _task_children(parent)
        if state is Probe.UNKNOWN:
            return Probe.UNKNOWN, identities
        if state is Probe.GONE and parent == root:
            return Probe.UNKNOWN, identities
        for child_pid in sorted(child_pids):
            if child_pid in seen:
                continue
            seen.add(child_pid)
            child_state, identity = _read_identity(child_pid)
            if child_state is Probe.UNKNOWN:
                return Probe.UNKNOWN, identities
            if child_state is Probe.GONE:
                continue
            assert identity is not None
            if identity.parent_pid != parent:
                return Probe.UNKNOWN, identities
            identities.append(identity)
            queue.append(child_pid)
    return Probe.PRESENT, identities


def _signal_identity(identity: ProcessIdentity, signum: int) -> Probe:
    """Signal only after exact birth/parent revalidation."""
    state, current = _read_identity(identity.pid)
    if state is not Probe.PRESENT:
        return state
    assert current is not None
    if (
        current.start_ticks != identity.start_ticks
        or current.parent_pid != identity.parent_pid
    ):
        return Probe.GONE
    try:
        os.kill(identity.pid, signum)
    except (ProcessLookupError, FileNotFoundError):
        return Probe.GONE
    except (PermissionError, OSError):
        return Probe.UNKNOWN
    return Probe.PRESENT


def _reap_direct(target_pid: int) -> Probe:
    """Reap adopted direct children, leaving Popen to reap its target."""
    state, child_pids = _task_children(os.getpid())
    if state is not Probe.PRESENT:
        return state
    for child_pid in child_pids:
        if child_pid == target_pid:
            continue
        try:
            os.waitpid(child_pid, os.WNOHANG)
        except (ChildProcessError, ProcessLookupError):
            pass
        except OSError:
            return Probe.UNKNOWN
    return Probe.PRESENT


def _cleanup(target: subprocess.Popen) -> Cleanup:
    """Boundedly stop, kill, and reap the complete owned descendant tree."""
    deadline = time.monotonic() + _CLEANUP_SECONDS
    last_uncertain = False
    while time.monotonic() < deadline:
        census_state, identities = _owned_census()
        if census_state is Probe.UNKNOWN:
            last_uncertain = True
            time.sleep(0.01)
            continue
        last_uncertain = False
        if not identities:
            try:
                target.wait(timeout=0)
            except (subprocess.TimeoutExpired, ChildProcessError, OSError):
                last_uncertain = True
                time.sleep(0.01)
                continue
            if _reap_direct(target.pid) is Probe.UNKNOWN:
                last_uncertain = True
                time.sleep(0.01)
                continue
            confirm_state, confirm = _owned_census()
            if confirm_state is Probe.PRESENT and not confirm:
                return Cleanup.COMPLETE
            if confirm_state is Probe.UNKNOWN:
                last_uncertain = True
            time.sleep(0.01)
            continue

        uncertain = False
        for identity in identities:
            if _signal_identity(identity, signal.SIGSTOP) is Probe.UNKNOWN:
                uncertain = True
        stopped_state, stopped = _owned_census()
        if stopped_state is Probe.UNKNOWN:
            uncertain = True
            stopped = identities
        for identity in reversed(stopped):
            if _signal_identity(identity, signal.SIGKILL) is Probe.UNKNOWN:
                uncertain = True
        try:
            target.wait(timeout=0.02)
        except (subprocess.TimeoutExpired, ChildProcessError, OSError):
            pass
        if _reap_direct(target.pid) is Probe.UNKNOWN:
            uncertain = True
        last_uncertain = uncertain
        time.sleep(0.01)

    final_state, final = _owned_census()
    if final_state is Probe.UNKNOWN or last_uncertain:
        return Cleanup.UNKNOWN
    if final:
        return Cleanup.INCOMPLETE
    return Cleanup.COMPLETE


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
    clean = Cleanup.UNKNOWN
    try:
        start_state, identity = _read_identity(target.pid)
        if start_state is not Probe.PRESENT or identity is None:
            raise RuntimeError("cron script target identity is not readable")
        os.write(
            result_fd,
            f"START {identity.pid} {identity.start_ticks}\n".encode("ascii"),
        )
        while not stopping.wait(0.02):
            returncode = target.poll()
            if returncode is not None:
                break
    finally:
        clean = _cleanup(target)

    if clean is not Cleanup.COMPLETE:
        os.write(result_fd, f"CLEANUP {clean.value}\n".encode("ascii"))
        os.close(result_fd)
        return 124
    if stopping.is_set() or returncode is None:
        os.write(result_fd, b"CLEANUP COMPLETE\n")
        os.close(result_fd)
        return 124
    os.write(result_fd, f"RESULT {returncode}\n".encode("ascii"))
    os.close(result_fd)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
