"""Real scoped entrypoints and marker ownership; no provider or live store.

These regressions intentionally keep the existing public entrypoints and
marker ``running`` projection.  They do not prescribe a new owner service.
"""

from concurrent.futures import Future
import contextvars
import json
import multiprocessing
import os
from pathlib import Path
import threading

import pytest

from cron import jobs, scheduler
from tools import cronjob_tools
from tests.cron.test_review_job_runtime import runtime_case  # noqa: F401


@pytest.fixture
def owner_case(runtime_case, monkeypatch):
    case = runtime_case
    private_home = case["home"].resolve()
    monkeypatch.setenv("HERMES_HOME", str(private_home))
    monkeypatch.setattr(jobs, "_hermes_now", scheduler._hermes_now)
    monkeypatch.setattr(scheduler, "_running_job_ids", set())
    monkeypatch.setattr(scheduler, "_interrupted_job_ids", set())
    monkeypatch.setattr(scheduler, "_cleanup_unverified_jobs", {})
    monkeypatch.setattr(scheduler, "save_job_output", lambda *args: "synthetic-output")
    monkeypatch.setattr(scheduler, "_deliver_result", lambda *args, **kwargs: None)
    case["policy"]["max_elapsed_seconds"] = 900
    marker = private_home / "data" / "cron_running_ids.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    case["marker"] = marker
    assert scheduler._get_hermes_home().resolve() == private_home
    assert jobs._current_cron_store().cron_dir.resolve() == private_home / "cron"
    yield case


def _running(marker):
    if not marker.exists():
        return set()
    return set(json.loads(marker.read_text())["running"])


@pytest.mark.parametrize("entry", ["manual", "scheduled"])
@pytest.mark.parametrize("outcome", ["complete", "business_failure"])
def test_active_and_terminal_ownership_is_shared_by_manual_and_scheduled(
    owner_case, monkeypatch, entry, outcome
):
    """Observe actual public admission while the synthetic worker is alive."""
    case = owner_case
    job_id = case["job"]["id"]
    entered, release = threading.Event(), threading.Event()
    responses, errors = [], []
    other_id = "unrelated-legacy-owner"
    case["marker"].write_text(json.dumps({"running": [other_id]}))

    def conversation(agent, prompt):
        entered.set()
        assert release.wait(timeout=10), "test did not release its synthetic worker"
        if outcome == "business_failure":
            return {"failed": True, "completed": False, "error": "synthetic review incomplete"}
        return {"final_response": "synthetic verified response"}

    case["callback"] = conversation
    monkeypatch.setattr(scheduler, "get_due_jobs", lambda: [jobs.get_job(job_id)])

    def invoke():
        try:
            if entry == "manual":
                responses.append(cronjob_tools._execute_job_now(jobs.get_job(job_id)))
            else:
                responses.append(scheduler.tick(verbose=False, sync=True))
        except BaseException as error:
            errors.append(error)

    context = contextvars.copy_context()
    caller = threading.Thread(target=context.run, args=(invoke,))
    caller.start()
    try:
        assert entered.wait(timeout=5), "public entrypoint never admitted synthetic work"
        claim = jobs.get_job(job_id)["dispatch_claim"]
        assert claim["status"] == "dispatched"
        assert claim["runtime"]["max_elapsed_seconds"] == 900
        assert job_id in scheduler.get_running_job_ids(), "active manual worker is invisible to owner drain"
        assert _running(case["marker"]) == {job_id, other_id}
    finally:
        release.set()
        caller.join(timeout=10)
        if entry == "scheduled":
            scheduler._shutdown_parallel_pool()
    assert not caller.is_alive(), "owned test caller failed to settle"
    assert errors == []
    assert responses
    stored = jobs.get_job(job_id)
    assert stored["last_status"] == ("ok" if outcome == "complete" else "error")
    assert stored.get("fire_claim") is None and stored.get("dispatch_claim") is None
    assert job_id not in scheduler.get_running_job_ids()
    assert _running(case["marker"]) == {other_id}
    if entry == "manual":
        assert responses[0]["success"] is (outcome == "complete")


def _marker_writer(home, name, first_read, release_first, calling, completed, errors, hold):
    """Separate-process writer with a pause after its actual first read."""
    os.environ["HERMES_HOME"] = home
    marker = Path(home) / "data" / "cron_running_ids.json"
    original_read = Path.read_text
    intercepted = False

    def read(path, *args, **kwargs):
        nonlocal intercepted
        content = original_read(path, *args, **kwargs)
        if hold and path == marker and not intercepted:
            intercepted = True
            first_read.set()
            if not release_first.wait(timeout=10):
                raise AssertionError("coordinator did not release the first marker reader")
        return content

    Path.read_text = read
    try:
        calling.set()
        scheduler._record_running_marker(name, True)
    except BaseException as error:
        errors.send(repr(error))
    finally:
        Path.read_text = original_read
        completed.set()
        errors.close()


@pytest.mark.skipif("fork" not in multiprocessing.get_all_start_methods(), reason="POSIX process race")
def test_concurrent_process_marker_additions_do_not_lose_an_active_job(owner_case):
    """A reads, B attempts/commits, A commits: serialized code keeps both."""
    case = owner_case
    case["marker"].write_text(json.dumps({"running": ["retained-unknown"]}))
    context = multiprocessing.get_context("fork")
    first_read, release_first = context.Event(), context.Event()
    a_calling, a_done, b_calling, b_done = (context.Event() for _ in range(4))
    a_errors, a_send = context.Pipe(duplex=False)
    b_errors, b_send = context.Pipe(duplex=False)
    first = context.Process(target=_marker_writer, args=(
        str(case["home"]), "writer-a", first_read, release_first,
        a_calling, a_done, a_send, True,
    ))
    second = context.Process(target=_marker_writer, args=(
        str(case["home"]), "writer-b", first_read, release_first,
        b_calling, b_done, b_send, False,
    ))
    started = []
    try:
        first.start()
        started.append(first)
        assert first_read.wait(timeout=5), "first writer did not reach the real marker read"
        second.start()
        started.append(second)
        assert b_calling.wait(timeout=5), "second writer did not attempt the update"
        # Unsafe base lets B finish while A retains the old read. Correct
        # exclusion blocks B; releasing A then lets B read the committed A.
        # The verdict is the final state, not an elapsed-time assertion.
        b_done.wait(timeout=1)
        release_first.set()
        assert a_done.wait(timeout=5) and b_done.wait(timeout=5)
        for process in started:
            process.join(timeout=5)
            assert process.exitcode == 0
        assert not a_errors.poll() or a_errors.recv() == ""
        assert not b_errors.poll() or b_errors.recv() == ""
        assert _running(case["marker"]) == {"retained-unknown", "writer-a", "writer-b"}
    finally:
        release_first.set()
        for process in started:
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        a_send.close()
        b_send.close()
        a_errors.close()
        b_errors.close()


def test_exact_old_drain_cannot_remove_successor_marker(owner_case):
    """Retire the actual old record without erasing another durable owner."""
    case = owner_case
    job_id = case["job"]["id"]
    old_runtime = scheduler._prepare_job_runtime(case["job"])
    successor_runtime = dict(old_runtime, run_id="b" * 32)
    successor_claim = {"at": old_runtime["dispatch_at"], "status": "dispatched",
                       "runtime": successor_runtime}
    jobs.update_job(job_id, {"dispatch_claim": successor_claim})
    worker = Future()
    worker.set_result(False)
    record = {"reason": "synthetic old drain", "pause_persisted": False,
              "runtime_draining": True, "worker": worker,
              "runtime_run_id": old_runtime["run_id"]}
    scheduler._cleanup_unverified_jobs[job_id] = record
    scheduler._running_job_ids.add(job_id)
    # This is the existing reader-visible format. A replacement durable
    # claim is sufficient to forbid the old callback from deleting it;
    # this test does not invent ownership metadata for a legacy entry.
    case["marker"].write_text(json.dumps({"running": [job_id, "other-owner"]}))
    before = case["marker"].read_bytes()
    with scheduler._job_runtime_scope(old_runtime):
        scheduler._finalize_failed_runtime(case["job"], old_runtime,
                                           "synthetic old failure", drain_record=record)
    assert jobs.get_job(job_id)["dispatch_claim"] == successor_claim
    assert case["marker"].read_bytes() == before, "old callback erased successor/unknown marker"


@pytest.mark.parametrize("entry", ["manual", "scheduled"])
def test_unknown_existing_marker_is_not_adopted_or_cleared_by_new_run(owner_case, monkeypatch, entry):
    case = owner_case
    job_id = case["job"]["id"]
    original = json.dumps({"running": [job_id, "other-unknown"], "retained": "unknown owner"})
    case["marker"].write_text(original)
    calls = []
    case["callback"] = lambda *args: calls.append(True) or {"final_response": "must not run"}
    monkeypatch.setattr(scheduler, "get_due_jobs", lambda: [jobs.get_job(job_id)])
    if entry == "manual":
        result = cronjob_tools._execute_job_now(jobs.get_job(job_id))
        assert result["success"] is False
    else:
        try:
            scheduler.tick(verbose=False, sync=True)
        finally:
            scheduler._shutdown_parallel_pool()
    assert calls == [], "new invocation silently adopted unresolved legacy ownership"
    assert case["marker"].read_text() == original


def test_unowned_marker_removal_preserves_legacy_entry(owner_case):
    case = owner_case
    original = json.dumps({"running": ["legacy-unknown", "another-owner"]})
    case["marker"].write_text(original)
    scheduler._record_running_marker("legacy-unknown", False)
    assert case["marker"].read_text() == original


def test_malformed_marker_is_not_replaced_with_empty_state(owner_case):
    case = owner_case
    original = '{"running": ["unknown-owner"'
    case["marker"].write_text(original)
    try:
        scheduler._record_running_marker("new-writer", True)
    except (OSError, ValueError, RuntimeError):
        pass  # An explicit failed update is permitted; fabricated empty state is not.
    assert case["marker"].read_text() == original
