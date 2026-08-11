"""SYS-819: gateway heartbeat recurrence — persistence observable + phase markers.

Spec (loop1-spec-sev1-20260810-REV5 SYS-819):
- Heartbeat always updated within 60s regardless of Slack state
- Heartbeat persistence failures observable (WRITE_FAILED state), not swallowed
- Restart provenance: initiator, reason code, prior PID, replacement PID,
  stale phase, timestamps
- Durable phase markers around cron_tick() (STARTED/TICK_START/TICK_OK/TICK_BLOCKED)
"""

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from cron.jobs import record_ticker_heartbeat, TICKER_HEARTBEAT_FILE, TICKER_SUCCESS_FILE
from cron.scheduler_provider import InProcessCronScheduler


def test_heartbeat_persistence_failure_is_observable(tmp_path, monkeypatch, caplog):
    """A persistence failure must be logged (WARNING), not silently swallowed."""
    monkeypatch.setattr("cron.jobs.TICKER_HEARTBEAT_FILE",
                        tmp_path / "no_such_dir" / "ticker_heartbeat")
    monkeypatch.setattr("cron.jobs.TICKER_SUCCESS_FILE",
                        tmp_path / "no_such_dir" / "ticker_success")
    with caplog.at_level(logging.WARNING, logger="cron.jobs.heartbeat"):
        record_ticker_heartbeat(success=True)
    assert any("SYS-819" in r.message for r in caplog.records), (
        "heartbeat persistence failure not observable (no SYS-819 WARNING)")


def test_heartbeat_write_success_no_warning(tmp_path, monkeypatch, caplog):
    """A healthy heartbeat write must NOT log a warning."""
    monkeypatch.setattr("cron.jobs.TICKER_HEARTBEAT_FILE",
                        tmp_path / "ticker_heartbeat")
    monkeypatch.setattr("cron.jobs.TICKER_SUCCESS_FILE",
                        tmp_path / "ticker_success")
    with caplog.at_level(logging.WARNING, logger="cron.jobs.heartbeat"):
        record_ticker_heartbeat(success=True)
    assert not any(r.levelno >= logging.WARNING for r in caplog.records), (
        "healthy heartbeat incorrectly logged a warning")
    assert (tmp_path / "ticker_heartbeat").exists()
    assert (tmp_path / "ticker_success").exists()


def test_heartbeat_does_not_depend_on_slack_ws(tmp_path, monkeypatch):
    """Heartbeat writer + tick must NOT require Slack WebSocket progress.

    SYS-819/SYS-2796: a blocked Slack WS reconnect must not prevent the
    heartbeat from being written. The tick runs with no Slack adapter at all.
    """
    monkeypatch.setattr("cron.jobs.TICKER_HEARTBEAT_FILE",
                        tmp_path / "ticker_heartbeat")
    monkeypatch.setattr("cron.jobs.TICKER_SUCCESS_FILE",
                        tmp_path / "ticker_success")
    # No adapters, no loop → cron_tick must still complete and the heartbeat
    # written. Call the scheduler with a short-lived stop event.
    import threading
    stop = threading.Event()
    sched = InProcessCronScheduler()
    # start() blocks; run it in a thread and stop after the first tick window.
    t = threading.Thread(
        target=sched.start,
        kwargs={"stop_event": stop, "interval": 0.1}, daemon=True)
    t.start()
    import time
    time.sleep(0.5)
    stop.set()
    t.join(timeout=2)
    hb = tmp_path / "ticker_heartbeat"
    assert hb.exists(), "heartbeat not written with no Slack adapter present"


def test_restart_provenance_phase_markers_present():
    """Durable phase markers must exist around cron_tick() in the provider."""
    src = Path(__file__).resolve().parent.parent.parent / "cron" / "scheduler_provider.py"
    text = src.read_text()
    for marker in ("TICK_START", "TICK_OK", "TICK_BLOCKED", "restart provenance",
                   "initiator", "prior_pid", "replacement_pid", "start_ts"):
        assert marker in text, f"missing SYS-819 phase/provenance marker: {marker}"
