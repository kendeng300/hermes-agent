"""Job-scoped runtime regressions; synthetic jobs and no provider transport."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cron import jobs, scheduler
from tools import delegate_tool as delegate


@pytest.fixture
def runtime_case(tmp_path, monkeypatch):
    monkeypatch.setattr(scheduler, "_cleanup_unverified_jobs", {})
    policy = {"max_concurrent_children": 7, "max_elapsed_seconds": 600,
              "leaf_only": True, "publication_authority": "advisory"}
    cfg = {"model": {"default": "synthetic-model"}, "agent": {"max_turns": 40},
           "cron": {"job_runtime_overrides": {"synthetic-review": policy}},
           "delegation": {"max_concurrent_children": 3, "max_iterations": 20}}
    (tmp_path / "config.yaml").write_text(json.dumps(cfg))
    monkeypatch.setattr(scheduler, "_hermes_home", tmp_path)
    monkeypatch.setattr(scheduler, "load_config", lambda: deepcopy(cfg))
    monkeypatch.setattr("hermes_cli.config.load_config_readonly", lambda: deepcopy(cfg))
    monkeypatch.setattr(delegate, "_load_config", lambda: deepcopy(cfg["delegation"]))
    monkeypatch.setattr("hermes_cli.env_loader.load_hermes_dotenv", lambda *a, **k: None)
    monkeypatch.setattr("hermes_cli.env_loader.reset_secret_source_cache", lambda *a, **k: None)
    monkeypatch.setattr("hermes_state.SessionDB", lambda: MagicMock())
    monkeypatch.setattr("hermes_cli.runtime_provider.resolve_runtime_provider", lambda **k: {
        "api_key": "synthetic-no-transport", "base_url": "https://example.invalid/v1",
        "provider": "openrouter", "api_mode": "chat_completions"})
    monkeypatch.setattr(scheduler, "_resolve_origin", lambda job: None)
    monkeypatch.setattr(scheduler, "_teardown_cron_agent", lambda *a: None)
    start = datetime(2030, 1, 2, 12, 0, tzinfo=timezone.utc)
    clock = [1000.0]
    monkeypatch.setattr(scheduler.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(scheduler, "_hermes_now", lambda: start + timedelta(seconds=clock[0] - 1000))
    state = {"cfg": cfg, "policy": policy, "clock": clock, "agents": [],
             "callback": lambda agent, prompt: {"final_response": "synthetic complete"}}

    class Agent:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.platform = "cron"
            self.model = kwargs["model"]
            self._delegate_depth = 0
            self._interrupt_requested = False
            self._active_children = []
            self._active_children_lock = threading.Lock()
            self.tool_progress_callback = None
            self._print_fn = None
            self.session_id = kwargs["session_id"]
            state["agents"].append(self)

        def run_conversation(self, prompt):
            return state["callback"](self, prompt)

        def interrupt(self, message):
            self._interrupt_requested = True

        def get_activity_summary(self):
            return {"seconds_since_activity": 0.0}

        def close(self):
            pass

    monkeypatch.setattr("run_agent.AIAgent", Agent)
    with jobs.use_cron_store(tmp_path):
        records = [{"id": name, "name": name, "prompt": "Review frozen synthetic evidence.",
                    "model": "synthetic-model", "provider": "openrouter", "enabled": True,
                    "state": "scheduled", "schedule": {"kind": "cron", "expr": "0 12 * * 1-5"},
                    "repeat": {"times": None, "completed": 0}, "deliver": "local"}
                   for name in ("synthetic-review", "ordinary-job")]
        jobs.save_jobs(records)
        state["job"] = records[0]
        state["ordinary"] = records[1]
        state["home"] = tmp_path
        yield state


def _completion_hook(case, monkeypatch, result=True):
    calls = []
    case["policy"]["completion_verifier"] = {
        "callable": "synthetic_review_completion:verify",
        "python_path": [str(case["home"])],
    }

    def process(argv, *, timeout, cwd, env, input_text=None):
        request = json.loads(input_text)
        assert 0 < timeout <= 600
        assert env["PYTHONPATH"] == str(case["home"])
        assert env["HERMES_HOME"] == str(case["home"])
        assert argv[1] == "-c"
        if request["probe"]:
            exists = request["hook"] == "synthetic_review_completion:verify"
            return SimpleNamespace(returncode=0, stdout=json.dumps(exists), stderr="")
        kwargs = request["kwargs"]
        calls.append((kwargs["job_id"], kwargs["run_id"], kwargs["runtime"]))
        return SimpleNamespace(returncode=0, stdout=json.dumps(result), stderr="")

    monkeypatch.setattr(scheduler, "_run_script_process", process)
    return calls


@pytest.mark.parametrize("response", ["[SILENT]", "BLOCKED: missing final reviews", "Interim only"])
def test_scoped_completion_requires_verified_outcome_not_parent_prose(runtime_case, monkeypatch, response):
    c = runtime_case
    calls = _completion_hook(c, monkeypatch, False)
    c["callback"] = lambda agent, prompt: {"final_response": response}
    monkeypatch.setattr(scheduler, "save_job_output", lambda *a: "synthetic-output")
    monkeypatch.setattr(scheduler, "_deliver_result", lambda *a, **k: None)
    scheduler.run_one_job(c["job"])
    stored = jobs.get_job(c["job"]["id"])
    assert stored["last_status"] == "error"
    assert "completion" in stored["last_error"].lower()
    assert len(calls) == 1 and calls[0][0] == c["job"]["id"]
    assert calls[0][1] == calls[0][2]["run_id"]


def test_verified_completion_allows_silent_duplicate_suppression_once(runtime_case, monkeypatch):
    c = runtime_case
    calls = _completion_hook(c, monkeypatch)
    c["callback"] = lambda agent, prompt: {"final_response": "[SILENT]"}
    delivered = []
    monkeypatch.setattr(scheduler, "save_job_output", lambda *a: "synthetic-output")
    monkeypatch.setattr(scheduler, "_deliver_result", lambda *a, **k: delivered.append(a))
    scheduler.run_one_job(c["job"])
    assert jobs.get_job(c["job"]["id"])["last_status"] == "ok"
    assert len(calls) == 1 and delivered == []


@pytest.mark.parametrize("raises", [False, True])
def test_scoped_delivery_failure_cannot_leave_success(runtime_case, monkeypatch, raises):
    c = runtime_case
    _completion_hook(c, monkeypatch)
    monkeypatch.setattr(scheduler, "save_job_output", lambda *a: "synthetic-output")

    def delivery(*args, **kwargs):
        if raises:
            raise RuntimeError("synthetic delivery failure")
        return "synthetic delivery failure"

    monkeypatch.setattr(scheduler, "_deliver_result", delivery)
    scheduler.run_one_job(c["job"])
    stored = jobs.get_job(c["job"]["id"])
    assert stored["last_status"] == "error"
    assert "delivery" in stored["last_error"].lower()


def test_configured_review_iteration_fallback_is_failed_not_completed(runtime_case, monkeypatch):
    c = runtime_case
    _completion_hook(c, monkeypatch)
    c["callback"] = lambda agent, prompt: {"completed": False,
        "turn_exit_reason": "max_iterations_reached(40)", "final_response": "interim summary"}
    success, _, _, error = scheduler.run_job(c["job"])
    assert not success and "interim" in error


@pytest.mark.parametrize("hook", ["bad-name", "missing_synthetic_module:verify", "synthetic_review_completion:missing"])
def test_invalid_completion_hook_records_admission_failure_before_agent(runtime_case, monkeypatch, hook):
    c = runtime_case
    _completion_hook(c, monkeypatch)
    c["policy"]["completion_verifier"]["callable"] = hook
    assert scheduler.run_one_job(c["job"]) is False
    stored = jobs.get_job(c["job"]["id"])
    assert stored["last_status"] == "error"
    assert c["agents"] == []


def test_pool_rejection_preserves_recoverable_claim_and_records_failure(runtime_case, monkeypatch):
    c = runtime_case
    monkeypatch.setattr(scheduler, "get_due_jobs", lambda: [c["job"]])
    monkeypatch.setattr(jobs, "_hermes_now", scheduler._hermes_now)
    monkeypatch.setattr(scheduler, "_get_lock_paths", lambda: (c["home"], c["home"] / "tick.lock"))
    monkeypatch.setattr(scheduler, "_interpreter_shutting_down", lambda error=None: error is not None)
    pool = SimpleNamespace(submit=MagicMock(side_effect=RuntimeError("cannot schedule new futures after interpreter shutdown")))
    monkeypatch.setattr(scheduler, "_get_parallel_pool", lambda *a: pool)
    try:
        scheduler.tick(verbose=False, sync=True)
        stored = jobs.get_job(c["job"]["id"])
        assert stored["dispatch_claim"]["status"] == "claimed"
        assert stored["last_status"] == "error"
        assert c["job"]["id"] not in scheduler.get_running_job_ids()
    finally:
        with scheduler._running_lock:
            scheduler._running_job_ids.discard(c["job"]["id"])


@pytest.mark.parametrize("phase", ["agent", "save", "delivery"])
def test_deadline_retains_unsettled_work_until_actual_drain(runtime_case, monkeypatch, phase):
    c = runtime_case
    entered, release, drained = threading.Event(), threading.Event(), threading.Event()
    real_wait = scheduler.concurrent.futures.wait
    original = scheduler._run_one_job

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return {"final_response": "late response"} if phase == "agent" else None

    def tracked(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        finally:
            drained.set()

    def poll(futures, timeout=None, **kwargs):
        assert entered.wait(timeout=3)
        c["clock"][0] = 1601
        return real_wait(futures, timeout=0.01, **kwargs)

    monkeypatch.setattr(scheduler, "_run_one_job", tracked)
    monkeypatch.setattr(scheduler, "save_job_output", blocked if phase == "save" else lambda *a: "synthetic-output")
    monkeypatch.setattr(scheduler, "_deliver_result", blocked if phase == "delivery" else lambda *a, **k: None)
    monkeypatch.setattr(scheduler, "_notify_provider_jobs_changed", lambda: None)
    if phase == "agent":
        c["callback"] = blocked
    monkeypatch.setattr(scheduler.concurrent.futures, "wait", poll)
    try:
        assert scheduler.run_one_job(c["job"]) is False
        stored = jobs.get_job(c["job"]["id"])
        assert stored["last_status"] == "error" and stored["enabled"] is True
        assert stored["state"] == "scheduled"
        assert scheduler._cleanup_quarantine_reason(stored)
        # The next invocation is refused without mutating the user's pause state.
        assert scheduler.run_one_job(jobs.get_job(c["job"]["id"])) is False
    finally:
        release.set()
        assert drained.wait(timeout=3)
        with scheduler._running_lock:
            scheduler._cleanup_unverified_jobs.pop(c["job"]["id"], None)
            scheduler._running_job_ids.discard(c["job"]["id"])


def test_scoped_schema_and_execution_cap_with_legacy_default_unchanged(runtime_case):
    c = runtime_case
    seen = []

    def inspect(agent, prompt):
        schema = delegate._build_dynamic_schema_overrides()
        seen.append((delegate._get_max_concurrent_children(), schema["description"]))
        return {"final_response": "complete"}

    c["callback"] = inspect
    assert scheduler.run_job(c["job"])[0]
    assert scheduler.run_job(c["ordinary"])[0]
    assert seen[0][0] == 7 and "up to 7" in seen[0][1]
    assert seen[1][0] == 3 and "up to 3" in seen[1][1]
    assert delegate._get_max_concurrent_children() == 3
    assert all(agent.kwargs["model"] == "synthetic-model" and
               agent.kwargs["max_iterations"] == 40 for agent in c["agents"])


def test_seven_real_executor_workers_leaf_only_and_unchanged_child_budget(runtime_case, monkeypatch):
    c = runtime_case
    barrier = threading.Barrier(7)
    builds, workers = [], []
    monkeypatch.setattr(delegate, "is_spawn_paused", lambda: False)
    monkeypatch.setattr(delegate, "_resolve_delegation_credentials", lambda cfg, parent: {
        "model": None, "provider": None, "base_url": None, "api_key": None,
        "api_mode": None, "request_overrides": None, "max_output_tokens": None,
        "command": None, "args": None})
    monkeypatch.setattr(delegate, "_resolve_effective_delegation_model", lambda **k: (None, None))

    def build(**kwargs):
        builds.append(kwargs)
        return SimpleNamespace(_delegate_role=kwargs["role"], _delegate_depth=1,
                               _interrupt_requested=False, session_id="synthetic-child")

    def child(task_index, goal, child, parent_agent):
        workers.append((threading.get_ident(), delegate._get_max_concurrent_children()))
        barrier.wait(timeout=3)
        return {"task_index": task_index, "status": "completed", "summary": goal,
                "api_calls": 1, "duration_seconds": 0, "_child_role": child._delegate_role}

    monkeypatch.setattr(delegate, "_build_child_agent", build)
    monkeypatch.setattr(delegate, "_run_single_child", child)
    outputs = []

    def dispatch(agent, prompt):
        outputs.append(json.loads(delegate.delegate_task(tasks=[
            {"goal": f"Independent synthetic seat {i}", "role": "orchestrator"}
            for i in range(7)], parent_agent=agent)))
        return {"final_response": "complete"}

    c["callback"] = dispatch
    assert scheduler.run_job(c["job"])[0]
    assert len(builds) == 7, outputs
    assert all(row["role"] == "leaf" and row["max_iterations"] == 20 for row in builds)
    assert len({worker[0] for worker in workers}) == 7
    assert all(worker[1] == 7 for worker in workers)
    assert len(outputs[0]["results"]) == 7


@pytest.mark.parametrize("phase", ["preparation", "active_agent", "exact_boundary"])
def test_elapsed_budget_is_not_reset_by_preparation_or_active_progress(runtime_case, monkeypatch, phase):
    c = runtime_case
    build = scheduler._build_job_prompt

    def prepare(*args, **kwargs):
        if phase == "preparation":
            c["clock"][0] += 601
        return build(*args, **kwargs)

    monkeypatch.setattr(scheduler, "_build_job_prompt", prepare)

    def finish(agent, prompt):
        c["clock"][0] += 600 if phase == "exact_boundary" else 601
        return {"final_response": "Never approve this late response"}

    c["callback"] = finish
    success, output, final, error = scheduler.run_job(c["job"])
    assert not success and not final
    assert "deadline" in (error or "").lower()
    if phase == "preparation":
        assert c["agents"] == []


def test_dispatch_claim_is_immutable_and_queue_delay_consumes_budget(runtime_case):
    c = runtime_case
    runtime = scheduler._prepare_job_runtime(c["job"])
    claim = jobs.get_job(c["job"]["id"])["dispatch_claim"]
    assert claim["runtime"]["run_id"] == runtime["run_id"]
    assert claim["runtime"]["job_id"] == c["job"]["id"]
    assert claim["runtime"]["deadline_monotonic"] - claim["runtime"]["dispatch_monotonic"] == 600
    assert claim["runtime"]["publication_authority"] == "advisory"
    with pytest.raises(TypeError):
        runtime["deadline_monotonic"] += 600
    c["clock"][0] += 601
    with scheduler._job_runtime_scope(runtime):
        success, _, final, error = scheduler.run_job(c["job"])
    assert not success and not final and "deadline" in error.lower()
    assert jobs.get_job(c["job"]["id"])["dispatch_claim"]["runtime"] == claim["runtime"]
    assert c["agents"] == []


def test_elapsed_watchdog_interrupts_an_active_worker_not_only_a_late_return(runtime_case, monkeypatch):
    c = runtime_case
    entered, release = threading.Event(), threading.Event()
    real_wait = scheduler.concurrent.futures.wait

    def active(agent, prompt):
        agent.interrupt = lambda message: (setattr(agent, "_interrupt_requested", True), release.set())
        entered.set()
        release.wait(timeout=3)
        return {"final_response": "late active worker"}

    def poll(futures, timeout=None, **kwargs):
        assert entered.wait(timeout=3)
        c["clock"][0] = 1601
        return real_wait(futures, timeout=0.01, **kwargs)

    c["callback"] = active
    monkeypatch.setattr(scheduler.concurrent.futures, "wait", poll)
    try:
        success, _, final, error = scheduler.run_job(c["job"])
        assert not success and not final and "deadline" in error.lower()
        assert c["agents"][0]._interrupt_requested
    finally:
        release.set()


def test_delivery_and_success_mark_cannot_escape_deadline_after_model_return(runtime_case, monkeypatch):
    c = runtime_case
    delivered, marked = [], []
    monkeypatch.setattr(scheduler, "claim_dispatch", lambda job_id: True)
    monkeypatch.setattr(scheduler, "run_job", lambda *a, **k: (True, "complete document", "APPROVED report", None))

    def save_output(*args):
        c["clock"][0] += 601
        return "synthetic-local-output"

    monkeypatch.setattr(scheduler, "save_job_output", save_output)
    monkeypatch.setattr(scheduler, "_deliver_result", lambda job, content, **k: delivered.append(content))
    monkeypatch.setattr(scheduler, "mark_job_run", lambda *a, **k: marked.append((a, k)))
    scheduler.run_one_job(c["job"])
    assert marked and marked[-1][0][1] is False
    assert all("APPROVED report" not in content for content in delivered)


def test_delivery_readback_finishing_late_is_not_a_success(runtime_case, monkeypatch):
    c = runtime_case
    marked = []
    monkeypatch.setattr(scheduler, "claim_dispatch", lambda job_id: True)
    monkeypatch.setattr(scheduler, "run_job", lambda *a, **k: (True, "document", "report", None))
    monkeypatch.setattr(scheduler, "save_job_output", lambda *a: "synthetic-output")
    monkeypatch.setattr(scheduler, "mark_job_run", lambda *a, **k: marked.append((a, k)))

    def delivered(*args, **kwargs):
        c["clock"][0] += 601
        return None

    monkeypatch.setattr(scheduler, "_deliver_result", delivered)
    scheduler.run_one_job(c["job"])
    assert marked[-1][0][1] is False
    assert "deadline" in marked[-1][0][2].lower()


def test_late_worker_drains_without_marking_or_clearing_a_new_claim(runtime_case, monkeypatch):
    c = runtime_case
    entered, release, drained = threading.Event(), threading.Event(), threading.Event()
    real_wait = scheduler.concurrent.futures.wait
    build = scheduler._build_job_prompt
    original = scheduler._run_job

    def blocked(*args, **kwargs):
        entered.set()
        release.wait(timeout=3)
        return build(*args, **kwargs)

    def tracked(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        finally:
            drained.set()

    def poll(futures, timeout=None, **kwargs):
        assert entered.wait(timeout=3)
        c["clock"][0] = 1601
        return real_wait(futures, timeout=0.01, **kwargs)

    monkeypatch.setattr(scheduler, "_build_job_prompt", blocked)
    monkeypatch.setattr(scheduler, "_run_job", tracked)
    monkeypatch.setattr(scheduler.concurrent.futures, "wait", poll)
    try:
        success, _, final, error = scheduler.run_job(c["job"])
        assert not success and not final and "deadline" in error.lower()
        next_claim = {"at": "2030-01-02T12:20:00+00:00", "status": "dispatched",
                      "runtime": {"run_id": "b" * 32}}
        jobs.update_job(c["job"]["id"], {"dispatch_claim": next_claim})
        release.set()
        assert drained.wait(timeout=3)
        assert c["agents"] == []
        assert jobs.get_job(c["job"]["id"])["dispatch_claim"] == next_claim
    finally:
        release.set()


def test_scope_is_thread_local_and_does_not_mutate_operator_config(runtime_case):
    c = runtime_case
    original = deepcopy(c["cfg"])
    runtime = scheduler._prepare_job_runtime(c["job"])
    barrier = threading.Barrier(2)

    def scoped():
        with scheduler._job_runtime_scope(runtime):
            barrier.wait(timeout=3)
            return delegate._get_max_concurrent_children()

    def ordinary():
        barrier.wait(timeout=3)
        return delegate._get_max_concurrent_children()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(scoped), pool.submit(ordinary)
        assert (first.result(), second.result()) == (7, 3)
    assert c["cfg"] == original
    assert delegate._get_max_concurrent_children() == 3


@pytest.mark.parametrize("fault", ["zero_cap", "nonfinite_time", "unknown_authority", "not_leaf", "extra_provider"])
def test_invalid_scoped_policy_fails_before_agent_without_global_fallback(runtime_case, fault):
    c = runtime_case
    if fault == "zero_cap": c["policy"]["max_concurrent_children"] = 0
    elif fault == "nonfinite_time": c["policy"]["max_elapsed_seconds"] = float("inf")
    elif fault == "unknown_authority": c["policy"]["publication_authority"] = "unrestricted"
    elif fault == "not_leaf": c["policy"]["leaf_only"] = False
    else: c["policy"]["provider"] = "different-provider"
    success, _, final, error = scheduler.run_job(c["job"])
    assert not success and not final and error
    assert c["agents"] == []


def test_nested_completion_capability_is_immutable_isolated_and_json_serializable(runtime_case, monkeypatch):
    c = runtime_case
    _completion_hook(c, monkeypatch)
    frozen = scheduler._prepare_job_runtime(c["job"])
    expected = jobs.get_job(c["job"]["id"])["dispatch_claim"]["runtime"]
    with pytest.raises(TypeError):
        frozen["completion_verifier"]["callable"] = "different:verify"
    with pytest.raises(TypeError):
        frozen["completion_verifier"]["python_path"].append("/different")
    assert json.loads(json.dumps(dict(frozen))) == expected
    supplied = deepcopy(expected)
    with delegate.job_runtime_scope(supplied):
        supplied["completion_verifier"]["python_path"].append("/caller-mutation")
        scoped = delegate._JOB_RUNTIME.get()
        assert json.loads(json.dumps(dict(scoped))) == expected
        with pytest.raises(TypeError):
            scoped["completion_verifier"]["python_path"][0] = "/changed"


@pytest.mark.parametrize("replace_claim", [False, True])
def test_idle_actual_model_drain_holds_cwd_and_finalizes_only_old_claim(runtime_case, monkeypatch, replace_claim):
    c = runtime_case
    entered, interrupted, release, model_done, wrapper_done = (threading.Event() for _ in range(5))
    closed = []
    workdir = c["home"] / "scoped-cwd"
    workdir.mkdir()
    c["job"]["workdir"] = str(workdir)
    monkeypatch.setattr(jobs, "_hermes_now", scheduler._hermes_now)
    monkeypatch.setattr(scheduler, "_terminal_cwd_lock", scheduler._ReadWriteLock())
    monkeypatch.setattr(scheduler, "_teardown_cron_agent", lambda *a: closed.append(True))
    monkeypatch.setattr(scheduler, "save_job_output", lambda *a: "synthetic-output")
    monkeypatch.setattr(scheduler, "_deliver_result", lambda *a, **k: None)
    original, real_wait = scheduler._run_job, scheduler.concurrent.futures.wait

    def actual(agent, prompt):
        agent.get_activity_summary = lambda: {"seconds_since_activity": 1000}
        agent.interrupt = lambda *a: interrupted.set()
        entered.set()
        try:
            assert release.wait(timeout=5)
            return {"final_response": "late actual model"}
        finally:
            model_done.set()

    def wrapper(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        finally:
            wrapper_done.set()

    def poll(futures, timeout=None, **kwargs):
        assert entered.wait(timeout=3)
        if not threading.current_thread().name.startswith("cron-scoped-runtime"):
            assert interrupted.wait(timeout=3)
            c["clock"][0] = 1601
        return real_wait(futures, timeout=0.01, **kwargs)

    c["callback"] = actual
    monkeypatch.setattr(scheduler, "_run_job", wrapper)
    monkeypatch.setattr(scheduler.concurrent.futures, "wait", poll)
    assert jobs.claim_job_for_fire(c["job"]["id"])
    replacement = None
    try:
        assert scheduler.run_one_job(c["job"]) is False
        old = jobs.get_job(c["job"]["id"])["dispatch_claim"]["runtime"]
        assert not model_done.is_set() and not wrapper_done.is_set()
        assert closed == [] and os.environ.get("TERMINAL_CWD") == str(workdir)
        assert scheduler._terminal_cwd_lock._writer_active
        record = scheduler._cleanup_unverified_jobs[c["job"]["id"]]
        if replace_claim:
            replacement = {"at": scheduler._hermes_now().isoformat(), "status": "dispatched",
                           "runtime": {**deepcopy(old), "run_id": "c" * 32}}
            jobs.update_job(c["job"]["id"], {"dispatch_claim": replacement,
                "fire_claim": {"at": scheduler._hermes_now().isoformat(), "by": "new-owner"}})
        release.set()
        assert wrapper_done.wait(timeout=3)
        record["worker"].result(timeout=3)
        # The callback has to finalize the old claim before releasing its guard.
        for _ in range(100):
            if c["job"]["id"] not in scheduler.get_running_job_ids():
                break
            threading.Event().wait(0.01)
        stored = jobs.get_job(c["job"]["id"])
        assert not scheduler._terminal_cwd_lock._writer_active and closed
        if replacement is not None:
            assert stored["dispatch_claim"] == replacement
            assert stored["fire_claim"]["by"] == "new-owner"
        else:
            assert stored["last_status"] == "error" and stored["enabled"] is True
            assert "dispatch_claim" not in stored and stored.get("fire_claim") is None
            assert jobs.claim_job_for_fire(c["job"]["id"])
            next_runtime = scheduler._prepare_job_runtime(jobs.get_job(c["job"]["id"]))
            assert next_runtime["run_id"] != old["run_id"]
            assert next_runtime["dispatch_at"] == scheduler._hermes_now().isoformat()
    finally:
        release.set()
        assert model_done.wait(timeout=3)
        assert wrapper_done.wait(timeout=3)
        with scheduler._running_lock:
            scheduler._cleanup_unverified_jobs.pop(c["job"]["id"], None)
            scheduler._running_job_ids.discard(c["job"]["id"])


@pytest.mark.parametrize("scoped", [False, True])
def test_real_child_timeout_keeps_resources_until_actual_drain_only_when_scoped(runtime_case, monkeypatch, scoped):
    c = runtime_case
    entered, interrupted, release, returned = (threading.Event() for _ in range(4))
    closed, leases, results = [], [], []
    child = SimpleNamespace(_subagent_id=None, _delegate_depth=1, _delegate_role="leaf",
        _credential_pool=SimpleNamespace(acquire_lease=lambda: "lease", current=lambda: None,
                                        release_lease=lambda value: leases.append(value)),
        interrupt=lambda: interrupted.set(), close=lambda: closed.append(True),
        get_activity_summary=lambda: {"api_call_count": 1})
    parent = SimpleNamespace(_active_children=[child], _active_children_lock=threading.Lock())

    def actual(**kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return {"final_response": "late child", "completed": False, "api_calls": 1}

    child.run_conversation = actual
    monkeypatch.setattr(delegate, "_get_child_timeout", lambda: 0.01)
    runtime = scheduler._prepare_job_runtime(c["job"]) if scoped else None

    def invoke():
        try:
            with delegate.job_runtime_scope(runtime):
                results.append(delegate._run_single_child(0, "synthetic child", child, parent))
        finally:
            returned.set()

    thread = threading.Thread(target=invoke, daemon=True)
    thread.start()
    try:
        assert entered.wait(timeout=3) and interrupted.wait(timeout=3)
        if scoped:
            assert not returned.wait(timeout=0.05)
            assert closed == [] and leases == [] and child in parent._active_children
        else:
            assert returned.wait(timeout=3)
            assert closed == [True] and leases == ["lease"]
    finally:
        release.set()
        thread.join(timeout=3)
        assert not thread.is_alive()
    assert results[0]["status"] == "timeout"
    assert closed == [True] and leases == ["lease"] and parent._active_children == []


@pytest.mark.parametrize("kind", ["parent", "child"])
@pytest.mark.parametrize("scoped", [False, True])
def test_recorded_tool_worker_drain_precedes_conversation_resource_release(runtime_case, monkeypatch, kind, scoped):
    c = runtime_case
    entered, release, returned = (threading.Event() for _ in range(3))
    closed, tool_threads, results = [], [], []

    def conversation(agent):
        agent._tool_worker_threads = set()
        agent._tool_worker_threads_lock = threading.Lock()

        def actual_tool():
            tid = threading.get_ident()
            with agent._tool_worker_threads_lock:
                agent._tool_worker_threads.add(tid)
            entered.set()
            try:
                assert release.wait(timeout=5)
            finally:
                with agent._tool_worker_threads_lock:
                    agent._tool_worker_threads.discard(tid)

        worker = threading.Thread(target=actual_tool, daemon=True)
        tool_threads.append(worker)
        worker.start()
        assert entered.wait(timeout=3)
        return {"final_response": "conversation returned while tool active", "completed": True, "api_calls": 1}

    if kind == "parent":
        c["callback"] = lambda agent, prompt: conversation(agent)
        monkeypatch.setattr(scheduler, "_teardown_cron_agent", lambda *a: closed.append(True))
        invoke = lambda: scheduler.run_job(c["job"] if scoped else c["ordinary"])
    else:
        child = SimpleNamespace(_subagent_id=None, _delegate_depth=1, _delegate_role="leaf",
                                close=lambda: closed.append(True), interrupt=lambda: None)
        parent = SimpleNamespace(_active_children=[child], _active_children_lock=threading.Lock())
        child.run_conversation = lambda **kwargs: conversation(child)
        runtime = scheduler._prepare_job_runtime(c["job"]) if scoped else None

        def invoke():
            with delegate.job_runtime_scope(runtime):
                return delegate._run_single_child(0, "synthetic tool worker", child, parent)

    def runner():
        try:
            results.append(invoke())
        finally:
            returned.set()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    try:
        assert entered.wait(timeout=3)
        if scoped:
            assert not returned.wait(timeout=0.05)
            assert closed == []
        else:
            assert returned.wait(timeout=3) and closed == [True]
    finally:
        release.set()
        for worker in tool_threads:
            worker.join(timeout=3)
            assert not worker.is_alive()
        thread.join(timeout=3)
        assert not thread.is_alive()
    assert len(results) == 1 and closed == [True]
