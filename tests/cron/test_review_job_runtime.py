"""Job-scoped runtime regressions; synthetic jobs and no provider transport."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cron import jobs, scheduler
from tools import delegate_tool as delegate


@pytest.fixture
def runtime_case(tmp_path, monkeypatch):
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
