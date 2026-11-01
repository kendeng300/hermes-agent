"""Real scoped entrypoints and marker ownership; no provider or live store.

These regressions intentionally keep the existing public entrypoints and
marker ``running`` projection.  They do not prescribe a new owner service.
"""

from concurrent.futures import Future
from contextlib import nullcontext
import contextvars
import errno
import json
import multiprocessing
import os
from pathlib import Path
import threading
from types import SimpleNamespace

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


@pytest.fixture
def marker_process_case(tmp_path, monkeypatch):
    """Real-clock process IPC must not inherit runtime_case's frozen clock."""
    private_home = tmp_path.resolve()
    monkeypatch.setenv("HERMES_HOME", str(private_home))
    monkeypatch.setattr(scheduler, "_hermes_home", private_home)
    marker = private_home / "data" / "cron_running_ids.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    with jobs.use_cron_store(private_home):
        yield {"home": private_home, "marker": marker}


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
def test_concurrent_process_marker_additions_do_not_lose_an_active_job(marker_process_case):
    """A reads, B attempts/commits, A commits: serialized code keeps both."""
    case = marker_process_case
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


@pytest.mark.parametrize("local_successor", [False, True])
@pytest.mark.parametrize("marker_owner", ["old", "successor", "legacy"])
def test_exact_old_drain_cannot_remove_successor_marker(owner_case, local_successor, marker_owner):
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
    scheduler._running_job_owners[job_id] = (
        successor_runtime["run_id"] if local_successor else old_runtime["run_id"])
    owners = {} if marker_owner == "legacy" else {
        job_id: old_runtime["run_id"] if marker_owner == "old" else successor_runtime["run_id"]}
    case["marker"].write_text(json.dumps({"running": [job_id, "other-owner"], "owners": owners}))
    before = case["marker"].read_bytes()
    with scheduler._job_runtime_scope(old_runtime):
        scheduler._finalize_failed_runtime(case["job"], old_runtime,
                                           "synthetic old failure", drain_record=record)
    assert jobs.get_job(job_id)["dispatch_claim"] == successor_claim
    if marker_owner == "old" and not local_successor:
        assert _running(case["marker"]) == {"other-owner"}, "settled old marker stranded admission"
    else:
        assert case["marker"].read_bytes() == before, "old callback erased successor/unknown marker"
    if local_successor:
        assert scheduler._running_job_owners[job_id] == successor_runtime["run_id"]
        assert job_id in scheduler.get_running_job_ids()
    else:
        assert job_id not in scheduler.get_running_job_ids()


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


@pytest.mark.parametrize("fault", ["lock", errno.EIO, errno.EXDEV, errno.EBUSY])
def test_marker_admission_failure_does_not_start_worker_or_erase_prior_bytes(owner_case, monkeypatch, fault):
    case = owner_case
    job_id = case["job"]["id"]
    original = json.dumps({"running": ["unrelated-unknown"]})
    case["marker"].write_text(original)
    calls = []
    case["callback"] = lambda *args: calls.append(True) or {"final_response": "must not start"}
    runtime = scheduler._prepare_job_runtime(case["job"], dispatched=False)
    before_claim = jobs.get_job(job_id)["dispatch_claim"]
    if fault == "lock":
        real_flock = scheduler.fcntl.flock

        def locked(fd, operation):
            path = Path(f"/proc/self/fd/{fd}").resolve()
            if path == case["marker"].with_suffix(".lock"):
                raise OSError(errno.EIO, "synthetic marker lock failure")
            return real_flock(fd, operation)

        monkeypatch.setattr(scheduler.fcntl, "flock", locked)
    else:
        real_replace = scheduler.os.replace

        def failed_replace(source, target):
            if Path(target) == case["marker"]:
                raise OSError(fault, "synthetic marker write failure")
            return real_replace(source, target)

        monkeypatch.setattr(scheduler.os, "replace", failed_replace)
    with scheduler._job_runtime_scope(runtime):
        assert scheduler.run_one_job(case["job"]) is False
    assert calls == []
    assert jobs.get_job(job_id)["dispatch_claim"] == before_claim
    assert case["marker"].read_text() == original
    assert job_id not in scheduler.get_running_job_ids()
    assert list(case["marker"].parent.glob(".cron-running-*.tmp")) == []


def test_marker_lock_contention_has_strict_existing_bound_on_real_clock(marker_process_case, monkeypatch):
    case = marker_process_case
    case["marker"].write_text(json.dumps({"running": ["unknown"]}))
    before = case["marker"].read_bytes()
    clock = iter([100.0, 100.0 + jobs._JOBS_LOCK_TIMEOUT_SECONDS])
    monkeypatch.setattr(scheduler.time, "perf_counter", lambda: next(clock))
    monkeypatch.setattr(scheduler.time, "monotonic", lambda: 1000.0)

    def contended(fd, operation):
        raise BlockingIOError(errno.EAGAIN, "synthetic marker contention")

    monkeypatch.setattr(scheduler.fcntl, "flock", contended)
    with pytest.raises(TimeoutError, match="marker lock"):
        scheduler._record_running_marker("new-writer", True)
    assert case["marker"].read_bytes() == before


@pytest.mark.parametrize("failure", ["prepare", "submit"])
def test_scheduled_reservation_is_visible_then_released_on_preworker_failure(owner_case, monkeypatch, failure):
    case = owner_case
    job_id = case["job"]["id"]
    observed = []
    monkeypatch.setattr(scheduler, "get_due_jobs", lambda: [jobs.get_job(job_id)])
    original_prepare = scheduler._prepare_job_runtime

    def preparation(job, **kwargs):
        observed.append(job_id in scheduler.get_running_job_ids())
        if failure == "prepare":
            raise ValueError("synthetic preparation refusal")
        return original_prepare(job, **kwargs)

    def submit(operation):
        assert job_id in scheduler.get_running_job_ids()
        raise RuntimeError("cannot schedule new futures after interpreter shutdown")

    monkeypatch.setattr(scheduler, "_prepare_job_runtime", preparation)
    monkeypatch.setattr(scheduler, "_get_parallel_pool", lambda *args: SimpleNamespace(submit=submit))
    assert scheduler.tick(verbose=False, sync=True) == 0
    assert observed == [True]
    assert case["agents"] == []
    assert job_id not in scheduler.get_running_job_ids()
    assert job_id not in scheduler._running_job_owners
    assert job_id not in _running(case["marker"])
    if failure == "submit":
        assert jobs.get_job(job_id)["dispatch_claim"]["status"] == "claimed"


@pytest.mark.parametrize("successor_marker", [False, True])
def test_claim_replacement_before_timeout_keeps_actual_old_future_until_drain(
    owner_case, monkeypatch, successor_marker
):
    case = owner_case
    job, marker = case["job"], case["marker"]
    entered, release, finalized = (threading.Event() for _ in range(3))
    runtime = scheduler._prepare_job_runtime(job, dispatched=False)
    replacement = {"at": runtime["dispatch_at"], "status": "dispatched",
                   "runtime": dict(runtime, run_id="c" * 32)}
    original_finalize = scheduler._finalize_failed_runtime
    original_wait = scheduler.concurrent.futures.wait

    def operation():
        entered.set()
        assert release.wait(timeout=5)
        return "settled"

    def wait(futures, **kwargs):
        assert entered.wait(timeout=3)
        jobs.update_job(job["id"], {"dispatch_claim": replacement,
                                   "fire_claim": {"by": "successor"}})
        if successor_marker:
            marker.write_text(json.dumps({"running": [job["id"]],
                              "owners": {job["id"]: replacement["runtime"]["run_id"]}}))
        case["clock"][0] = runtime["deadline_monotonic"] + 1
        return original_wait(futures, timeout=0.001)

    def finalize(*args, **kwargs):
        try:
            return original_finalize(*args, **kwargs)
        finally:
            finalized.set()

    monkeypatch.setattr(scheduler.concurrent.futures, "wait", wait)
    monkeypatch.setattr(scheduler, "_finalize_failed_runtime", finalize)
    try:
        with scheduler._job_runtime_scope(runtime):
            assert scheduler._activate_job_runtime(job, runtime)
            with pytest.raises(TimeoutError):
                scheduler._run_scoped_runtime(job, operation, [])
        assert job["id"] in scheduler.get_running_job_ids()
        assert scheduler._running_job_owners[job["id"]] == runtime["run_id"]
        record = scheduler._cleanup_unverified_jobs[job["id"]]
        assert not record["worker"].done()
        assert scheduler._cleanup_quarantine_reason(job)
        before = marker.read_bytes()
        release.set()
        assert finalized.wait(timeout=3)
        assert jobs.get_job(job["id"])["dispatch_claim"] == replacement
        assert jobs.get_job(job["id"])["fire_claim"] == {"by": "successor"}
        assert job["id"] not in scheduler.get_running_job_ids()
        assert job["id"] not in scheduler._cleanup_unverified_jobs
        if successor_marker:
            assert marker.read_bytes() == before
        else:
            assert job["id"] not in _running(marker)
    finally:
        release.set()
        assert finalized.wait(timeout=3)


@pytest.mark.parametrize("no_agent", [False, True])
def test_scheduled_hard_cleanup_can_resume_without_stranded_owned_reservation(
    owner_case, monkeypatch, no_agent
):
    case = owner_case
    job = jobs.update_job(case["ordinary"]["id"], {"no_agent": no_agent, "script": "synthetic.py"})
    calls = []

    def script(*args, **kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise scheduler.CronScriptCleanupError("synthetic process cleanup not proved")
        return True, "synthetic script complete"

    monkeypatch.setattr(scheduler, "_run_job_script", script)
    monkeypatch.setattr(scheduler, "_notify_provider_jobs_changed", lambda: None)
    monkeypatch.setattr(scheduler, "get_due_jobs", lambda: [jobs.get_job(job["id"])])
    try:
        scheduler.tick(verbose=False, sync=True)
        paused = jobs.get_job(job["id"])
        assert paused["state"] == "paused" and not paused["enabled"]
        assert calls == [True]
        assert job["id"] in scheduler.get_running_job_ids()
        owner = scheduler._running_job_owners[job["id"]]
        assert json.loads(case["marker"].read_text())["owners"][job["id"]] == owner
        assert scheduler.tick(verbose=False, sync=True) == 0
        jobs.resume_job(job["id"])
        assert scheduler.tick(verbose=False, sync=True) == 1
        assert calls == [True, True]
        assert jobs.get_job(job["id"])["last_status"] == "ok"
        assert job["id"] not in scheduler.get_running_job_ids()
        assert job["id"] not in _running(case["marker"])
        assert job["id"] not in scheduler._cleanup_unverified_jobs
    finally:
        scheduler._shutdown_parallel_pool()


@pytest.mark.parametrize("target", ["marker", "lock"])
def test_marker_and_lock_symlinks_are_refused_without_touching_target(marker_process_case, target):
    case = marker_process_case
    referent = case["home"] / "retained.json"
    original = '{"running": ["unknown"], "retain": "original bytes"}'
    referent.write_text(original)
    path = case["marker"] if target == "marker" else case["marker"].with_suffix(".lock")
    path.symlink_to(referent)
    with pytest.raises((OSError, ValueError), match="[Ss]ymlink"):
        scheduler._record_running_marker("new", True)
    assert path.is_symlink()
    assert referent.read_text() == original


@pytest.mark.parametrize("commit_persisted", [False, True])
@pytest.mark.parametrize("rollback_fails", [False, True])
def test_failed_claim_commit_and_rollback_never_launch_or_hide_unverified_owner(
    owner_case, monkeypatch, commit_persisted, rollback_fails
):
    case = owner_case
    job = case["job"]
    runtime = scheduler._prepare_job_runtime(job, dispatched=False)
    before_claim = jobs.get_job(job["id"])["dispatch_claim"]
    original = '{"running": ["retained-unknown"], "extra": "retained"}'
    case["marker"].write_text(original)
    real_update, real_write = jobs.update_job, scheduler._write_running_marker
    writes = []

    def update(job_id, changes):
        if (changes.get("dispatch_claim") or {}).get("status") == "dispatched":
            if commit_persisted:
                real_update(job_id, changes)
            raise OSError(errno.EIO, "synthetic claim commit failure")
        return real_update(job_id, changes)

    def write(marker, text):
        writes.append(text)
        if rollback_fails and len(writes) == 2:
            raise OSError(errno.EIO, "synthetic rollback write failure")
        return real_write(marker, text)

    monkeypatch.setattr(jobs, "update_job", update)
    monkeypatch.setattr(scheduler, "_write_running_marker", write)
    with scheduler._job_runtime_scope(runtime):
        assert scheduler.run_one_job(job) is False
    assert case["agents"] == []
    assert jobs.get_job(job["id"])["dispatch_claim"] == (
        dict(before_claim, status="dispatched") if commit_persisted else before_claim)
    if rollback_fails:
        assert job["id"] in scheduler.get_running_job_ids()
        assert scheduler._running_job_owners[job["id"]] == runtime["run_id"]
        assert scheduler._cleanup_unverified_jobs[job["id"]]["marker_unverified"]
        assert _running(case["marker"]) == {job["id"], "retained-unknown"}
    else:
        assert case["marker"].read_text() == original
        assert job["id"] not in scheduler.get_running_job_ids()
    assert len(writes) == 2


def test_release_write_failure_retains_exact_owner_and_preserves_successor_claim(owner_case, monkeypatch):
    case = owner_case
    job = case["job"]
    runtime = scheduler._prepare_job_runtime(job, dispatched=False)
    with scheduler._job_runtime_scope(runtime):
        assert scheduler._activate_job_runtime(job, runtime)
    replacement = {"at": runtime["dispatch_at"], "status": "dispatched",
                   "runtime": dict(runtime, run_id="d" * 32)}
    jobs.update_job(job["id"], {"dispatch_claim": replacement})
    before = case["marker"].read_bytes()
    real_replace = scheduler.os.replace

    def replace(source, destination):
        if Path(destination) == case["marker"]:
            raise OSError(errno.EBUSY, "synthetic release write failure")
        return real_replace(source, destination)

    monkeypatch.setattr(scheduler.os, "replace", replace)
    assert scheduler._release_running_owner(job, runtime["run_id"]) is False
    assert case["marker"].read_bytes() == before
    assert jobs.get_job(job["id"])["dispatch_claim"] == replacement
    assert job["id"] in scheduler.get_running_job_ids()
    assert scheduler._cleanup_unverified_jobs[job["id"]]["marker_unverified"]


@pytest.mark.parametrize("new_owner", [False, True])
def test_actual_queued_cancellation_releases_only_its_reservation(owner_case, monkeypatch, new_owner):
    case = owner_case
    job_id = case["job"]["id"]
    queued = Future()
    monkeypatch.setattr(scheduler, "get_due_jobs", lambda: [jobs.get_job(job_id)])
    monkeypatch.setattr(scheduler, "_get_parallel_pool", lambda *args:
                        SimpleNamespace(submit=lambda operation: queued))
    assert scheduler.tick(verbose=False, sync=False) == 1
    assert job_id in scheduler.get_running_job_ids()
    before = jobs.get_job(job_id)["dispatch_claim"]
    assert before["status"] == "claimed"
    if new_owner:
        scheduler._running_job_owners[job_id] = "newer-local-owner"
    assert queued.cancel()
    assert jobs.get_job(job_id)["dispatch_claim"] == before
    assert case["agents"] == [] and job_id not in _running(case["marker"])
    assert (job_id in scheduler.get_running_job_ids()) is new_owner
    if new_owner:
        assert scheduler._running_job_owners[job_id] == "newer-local-owner"


@pytest.mark.parametrize("kind", ["directory", "fifo"])
def test_nonregular_marker_is_refused_before_read_without_replacement(marker_process_case, kind):
    marker = marker_process_case["marker"]
    if kind == "directory":
        marker.mkdir()
    else:
        if not hasattr(os, "mkfifo"):
            pytest.skip("FIFO is POSIX-only")
        os.mkfifo(marker)
    before = marker.stat()
    with pytest.raises(ValueError, match="regular file"):
        scheduler._record_running_marker("new-owner", True)
    after = marker.stat()
    assert (before.st_ino, before.st_mode) == (after.st_ino, after.st_mode)


def _same_claim_contender(home, job, runtime, reads_ready, start_worker, release, results):
    """Real public runtime admission with degraded cross-process jobs locking."""
    os.environ["HERMES_HOME"] = home
    scheduler._hermes_home = Path(home)
    scheduler._running_job_ids = set()
    scheduler._running_job_owners = {}
    scheduler._cleanup_unverified_jobs = {}
    jobs._jobs_lock = nullcontext  # Deliberate existing fail-open outcome.
    real_get = jobs.get_job
    reads = 0

    def get(job_id):
        nonlocal reads
        current = real_get(job_id)
        reads += 1
        # Public run_one_job's snapshot is read #1; activation read #2.
        # Both contenders must retain the SAME claimed preimage before either
        # enters strict marker exclusion. Never barrier the locked re-read.
        if reads == 2:
            reads_ready.wait(timeout=5)
        return current

    def work(*args, **kwargs):
        start_worker.send("started")
        assert release.wait(timeout=10)
        return True

    jobs.get_job = get
    scheduler._run_one_job = work
    try:
        with jobs.use_cron_store(Path(home)), scheduler._job_runtime_scope(runtime):
            results.send(scheduler.run_one_job(job))
    except BaseException as error:
        results.send(repr(error))
    finally:
        results.close()
        start_worker.close()


@pytest.mark.skipif("fork" not in multiprocessing.get_all_start_methods(), reason="POSIX process race")
def test_same_claim_can_start_only_one_worker_when_jobs_lock_degrades(marker_process_case, monkeypatch):
    case = marker_process_case
    job = {"id": "same-token", "name": "synthetic", "prompt": "synthetic", "enabled": True,
           "state": "scheduled", "schedule": {"kind": "interval", "minutes": 5}, "deliver": "local"}
    jobs.save_jobs([job])
    cfg = {"cron": {"job_runtime_overrides": {job["id"]: {
        "max_concurrent_children": 7, "max_elapsed_seconds": 900,
        "leaf_only": True, "publication_authority": "advisory"}}}}
    monkeypatch.setattr("hermes_cli.config.load_config_readonly", lambda: cfg)
    runtime = dict(scheduler._prepare_job_runtime(job, dispatched=False))
    context = multiprocessing.get_context("fork")
    reads_ready, release = context.Barrier(2), context.Event()
    workers, result_readers, started_readers, senders = [], [], [], []
    for _ in range(2):
        result_read, result_send = context.Pipe(duplex=False)
        started_read, started_send = context.Pipe(duplex=False)
        result_readers.append(result_read)
        started_readers.append(started_read)
        senders.extend([result_send, started_send])
        workers.append(context.Process(target=_same_claim_contender, args=(
            str(case["home"]), job, runtime, reads_ready, started_send, release, result_send)))
    try:
        for worker in workers:
            worker.start()
        # The accepted worker holds the marker until explicitly released. The
        # rejected contender must return without starting another worker.
        from multiprocessing.connection import wait
        pending_results = wait(result_readers, timeout=5)
        assert pending_results, "neither contender was rejected while the winner was alive"
        assert pending_results[0].recv() is False
        starts = wait(started_readers, timeout=5)
        assert len(starts) == 1 and starts[0].recv() == "started"
        assert jobs.get_job(job["id"])["dispatch_claim"]["status"] == "dispatched"
        release.set()
        other = [reader for reader in result_readers if reader is not pending_results[0]][0]
        assert other.poll(5) and other.recv() is True
        for worker in workers:
            worker.join(timeout=5)
            assert worker.exitcode == 0
        assert job["id"] not in _running(case["marker"])
    finally:
        release.set()
        for worker in workers:
            worker.join(timeout=5)
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)
        for connection in result_readers + started_readers + senders:
            connection.close()
