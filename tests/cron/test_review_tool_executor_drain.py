"""Actual tool-pool ownership for the opt-in scheduled-review runtime.

No model, provider, delivery or real tool transport is used. The executor,
Future state transitions, context propagation and scheduler drain are real.
"""
from contextlib import nullcontext
import contextvars
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agent import tool_executor as execution
from cron import jobs, scheduler
from tools import daemon_pool, delegate_tool as delegate
from tests.cron.test_review_job_runtime import runtime_case  # noqa: F401


@pytest.fixture
def tools_case(monkeypatch):
    """Keep real dispatch/worker lifetime, stub unrelated external edges."""
    agent = SimpleNamespace()

    def install(target):
        target._interrupt_requested = False
        target._tool_worker_threads = set()
        target._tool_worker_threads_lock = threading.Lock()
        target.log_prefix = ""
        target.quiet_mode = True
        target.verbose_logging = False
        target.log_prefix_chars = 200
        target.tool_delay = 0
        target.tool_progress_callback = target.tool_start_callback = target.tool_complete_callback = None
        target._checkpoint_mgr = SimpleNamespace(enabled=False)
        target._subdirectory_hints = SimpleNamespace(check_tool_call=lambda *a: None)
        target._tool_guardrails = SimpleNamespace(before_call=lambda *a: SimpleNamespace(allows_execution=True))
        target._context_engine_tool_names = set()
        target._memory_manager = None
        target.valid_tool_names = set()
        target.session_id = "synthetic-session"
        target._touch_activity = lambda *a: None
        target._vprint = lambda *a, **k: None
        target._should_emit_quiet_tool_messages = lambda: False
        target._should_start_quiet_spinner = lambda: False
        target._append_guardrail_observation = lambda name, args, result, **k: result
        target._record_file_mutation_result = lambda *a: None
        target._tool_result_content_for_active_model = lambda name, result: result
        target._flush_messages_to_session_db = lambda *a: None
        target._apply_pending_steer_to_tool_results = lambda *a: None
        target._invoke_tool = MagicMock(return_value='{"ok":true}')
        target.interrupt = lambda *a: setattr(target, "_interrupt_requested", True)
        return target

    install(agent)
    ra = SimpleNamespace(_set_interrupt=lambda *a: None,
                         handle_function_call=lambda *a, **k: agent._invoke_tool(*a, **k))
    monkeypatch.setattr(execution, "_ra", lambda: ra)
    monkeypatch.setattr("hermes_cli.plugins.resolve_pre_tool_block", lambda *a, **k: None)
    monkeypatch.setattr(execution, "_apply_tool_request_middleware_for_agent",
                        lambda agent, **k: (k["function_args"], []))
    monkeypatch.setattr(execution, "_emit_terminal_post_tool_call", lambda *a, **k: None)
    monkeypatch.setattr(execution, "get_active_env", lambda *a: None)
    monkeypatch.setattr(execution, "maybe_persist_tool_result", lambda **k: k["content"])
    monkeypatch.setattr(execution, "enforce_turn_budget", lambda *a, **k: None)
    monkeypatch.setattr(execution, "_resolve_concurrent_tool_timeout", lambda: 0.03)
    return SimpleNamespace(agent=agent, install=install, ra=ra)


def _message(count=1):
    return SimpleNamespace(tool_calls=[SimpleNamespace(id=f"call-{i}",
        function=SimpleNamespace(name="synthetic_tool", arguments="{}")) for i in range(count)])


def _start(call, *, scoped=True):
    done, errors = threading.Event(), []
    # Expired capability must STILL drain. Checking remaining time here would
    # incorrectly turn the exact failure path into unscoped abandonment.
    runtime = {"job_id": "synthetic-review", "run_id": "a" * 32,
               "deadline_monotonic": -1, "max_elapsed_seconds": 600}

    def run():
        try:
            with delegate.job_runtime_scope(runtime) if scoped else nullcontext():
                call()
        except BaseException as exc:
            errors.append(exc)
        finally:
            done.set()

    thread = threading.Thread(target=contextvars.copy_context().run, args=(run,), daemon=True)
    thread.start()
    return thread, done, errors


def _pool_probe(monkeypatch, *, submit_error=None, shutdown_error=None):
    real = daemon_pool.DaemonThreadPoolExecutor
    instances, shutting = [], threading.Event()

    class Pool(real):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.accepted, self.shutdown_calls = [], []
            instances.append(self)

        def submit(self, *a, **k):
            if self.accepted and submit_error is not None:
                raise submit_error
            future = super().submit(*a, **k)
            self.accepted.append(future)
            return future

        def shutdown(self, wait=True, *, cancel_futures=False):
            self.shutdown_calls.append((wait, cancel_futures))
            shutting.set()
            if shutdown_error is not None and len(self.shutdown_calls) == 1:
                raise shutdown_error
            return super().shutdown(wait=wait, cancel_futures=cancel_futures)

    monkeypatch.setattr(daemon_pool, "DaemonThreadPoolExecutor", Pool)
    return instances, shutting


def _gate_wrapper(monkeypatch, location, entered, release):
    real = execution.propagate_context_to_thread

    def propagate(target):
        wrapped = real(target)

        def worker(*a, **k):
            if location == "before_registration":
                entered.set()
                assert release.wait(8)
            try:
                return wrapped(*a, **k)
            finally:
                if location == "after_wrapper_cleanup":
                    entered.set()
                    assert release.wait(8)

        return worker

    monkeypatch.setattr(execution, "propagate_context_to_thread", propagate)


@pytest.mark.parametrize("scoped", [False, True])
@pytest.mark.parametrize("reason", ["timeout", "interrupt"])
@pytest.mark.parametrize("location", ["before_registration", "after_wrapper_cleanup"])
def test_real_pool_retains_unregistered_worker_until_exit(tools_case, monkeypatch, scoped, reason, location):
    entered, release = threading.Event(), threading.Event()
    agent = tools_case.agent
    _gate_wrapper(monkeypatch, location, entered, release)
    pools, shutting = _pool_probe(monkeypatch)
    real_wait = execution.concurrent.futures.wait

    def wait(futures, timeout=None, **kwargs):
        assert entered.wait(3)
        if reason == "interrupt":
            agent._interrupt_requested = True
        return real_wait(futures, timeout=min(timeout or 0.01, 0.01), **kwargs)

    if reason == "interrupt":
        monkeypatch.setattr(execution, "_resolve_concurrent_tool_timeout", lambda: None)
    monkeypatch.setattr(execution.concurrent.futures, "wait", wait)
    messages = []
    thread, done, errors = _start(lambda: execution.execute_tool_calls_concurrent(agent, _message(), messages, "task"), scoped=scoped)
    try:
        assert entered.wait(3) and shutting.wait(3)
        assert not agent._tool_worker_threads
        assert pools[0].accepted[0].running()
        if scoped:
            assert not done.wait(0.05), "scoped executor released an actual running worker"
        else:
            assert done.wait(3), "ordinary timeout/interrupt must keep its existing prompt return"
    finally:
        release.set()
        thread.join(3)
        for pool in pools:
            pool.shutdown(wait=True)
    assert not thread.is_alive() and not errors
    assert all(f.done() for f in pools[0].accepted)
    assert len(messages) == 1


def test_parallel_workers_all_drain_but_queued_tools_never_start(tools_case, monkeypatch):
    entered = [threading.Event(), threading.Event()]
    release = [threading.Event(), threading.Event()]
    started, lock = [], threading.Lock()
    monkeypatch.setattr(execution, "_MAX_TOOL_WORKERS", 2)
    pools, shutting = _pool_probe(monkeypatch)

    def tool(*a, **k):
        with lock:
            index = len(started)
            started.append(index)
        assert index < 2, "queued work must remain cancelled"
        entered[index].set()
        assert release[index].wait(8)
        return '{"ok":true}'

    tools_case.agent._invoke_tool.side_effect = tool
    thread, done, errors = _start(lambda: execution.execute_tool_calls_concurrent(tools_case.agent, _message(4), [], "task"))
    try:
        assert all(event.wait(3) for event in entered) and shutting.wait(3)
        assert not done.wait(0.05)
        release[0].set()
        assert not done.wait(0.05), "one remaining worker still owns resources"
        assert started == [0, 1]
        assert all(f.cancelled() for f in pools[0].accepted[2:])
    finally:
        for event in release:
            event.set()
        thread.join(3)
        for pool in pools:
            pool.shutdown(wait=True)
    assert not errors and not thread.is_alive()


@pytest.mark.parametrize("failure", ["submit", "interpreter_shutdown", "shutdown_error", "shutdown_interrupt"])
def test_partial_setup_and_cleanup_failure_drain_accepted_workers(tools_case, monkeypatch, failure):
    entered, release = threading.Event(), threading.Event()
    _gate_wrapper(monkeypatch, "before_registration", entered, release)
    submit_error = (RuntimeError("cannot schedule new futures after interpreter shutdown")
                    if failure == "interpreter_shutdown" else RuntimeError("synthetic submit refused")) if failure in {"submit", "interpreter_shutdown"} else None
    shutdown_error = KeyboardInterrupt("synthetic join interrupted") if failure == "shutdown_interrupt" else (RuntimeError("synthetic join error") if failure == "shutdown_error" else None)
    pools, shutting = _pool_probe(monkeypatch, submit_error=submit_error, shutdown_error=shutdown_error)
    thread, done, errors = _start(lambda: execution.execute_tool_calls_concurrent(tools_case.agent, _message(2 if submit_error else 1), [], "task"))
    try:
        assert entered.wait(3) and shutting.wait(3)
        assert not done.wait(0.05), "failure is not evidence the accepted worker drained"
    finally:
        release.set()
        thread.join(3)
        for pool in pools:
            pool.shutdown(wait=True)
    assert not thread.is_alive() and all(f.done() for f in pools[0].accepted)
    if failure == "interpreter_shutdown":
        assert errors == []
    else:
        expected = shutdown_error or submit_error
        assert len(errors) == 1 and errors[0] is expected


@pytest.mark.parametrize("mode", ["no_calls", "blocked", "constructor_error", "success", "tool_error", "tool_interrupt"])
def test_zero_work_and_completed_work_do_not_need_extra_lifetime(tools_case, monkeypatch, mode):
    pools, _ = _pool_probe(monkeypatch)
    agent = tools_case.agent
    messages = []
    if mode == "blocked":
        monkeypatch.setattr("hermes_cli.plugins.resolve_pre_tool_block", lambda *a, **k: "synthetic blocked")
    if mode == "constructor_error":
        def broken(**kwargs):
            raise RuntimeError("synthetic constructor failed")
        monkeypatch.setattr(daemon_pool, "DaemonThreadPoolExecutor", broken)
    if mode == "tool_error":
        agent._invoke_tool.side_effect = ValueError("synthetic tool error")
    if mode == "tool_interrupt":
        agent._invoke_tool.side_effect = KeyboardInterrupt()
    thread, done, errors = _start(lambda: execution.execute_tool_calls_concurrent(agent, _message(0 if mode == "no_calls" else 1), messages, "task"))
    thread.join(3)
    assert done.is_set() and not thread.is_alive()
    assert not agent._tool_worker_threads
    if mode == "constructor_error":
        assert len(errors) == 1 and "constructor failed" in str(errors[0])
        assert not pools
    else:
        assert not errors
        assert len(messages) == (0 if mode == "no_calls" else 1)
        assert all(f.done() for pool in pools for f in pool.accepted)
    if mode in {"no_calls", "blocked"}:
        assert not pools and agent._invoke_tool.call_count == 0


@pytest.mark.parametrize("outcome", ["success", "error", "interrupt"])
def test_sequential_handler_is_inline_and_keeps_ownership(tools_case, monkeypatch, outcome):
    entered, release = threading.Event(), threading.Event()
    pools, _ = _pool_probe(monkeypatch)

    def tool(*a, **k):
        entered.set()
        assert release.wait(8)
        if outcome == "error":
            raise ValueError("synthetic inline error")
        if outcome == "interrupt":
            raise KeyboardInterrupt()
        return '{"ok":true}'

    tools_case.agent._invoke_tool.side_effect = tool
    thread, done, errors = _start(lambda: execution.execute_tool_calls_sequential(tools_case.agent, _message(), [], "task"))
    try:
        assert entered.wait(3) and not done.wait(0.05)
        assert pools == [], "sequential dispatch must not acquire a new executor"
    finally:
        release.set()
        thread.join(3)
    assert not thread.is_alive() and not errors


@pytest.mark.parametrize("location", ["before_registration", "after_wrapper_cleanup"])
def test_outer_deadline_fails_but_real_tool_pool_keeps_cwd_and_claim(runtime_case, tools_case, monkeypatch, location):
    c = runtime_case
    entered, release, conversation_done = (threading.Event() for _ in range(3))
    closed, delivered = [], []
    _gate_wrapper(monkeypatch, location, entered, release)
    workdir = c["home"] / "actual-tool-cwd"
    workdir.mkdir()
    c["job"]["workdir"] = str(workdir)
    monkeypatch.setattr(scheduler, "_terminal_cwd_lock", scheduler._ReadWriteLock())
    monkeypatch.setattr(scheduler, "_teardown_cron_agent", lambda *a: closed.append(True))
    monkeypatch.setattr(scheduler, "save_job_output", lambda *a: "synthetic-output")
    monkeypatch.setattr(scheduler, "_deliver_result", lambda *a, **k: delivered.append(True))
    real_wait = execution.concurrent.futures.wait

    def wait(futures, timeout=None, **kwargs):
        assert entered.wait(3)
        c["clock"][0] = 1601
        return real_wait(futures, timeout=0.01, **kwargs)

    monkeypatch.setattr(execution.concurrent.futures, "wait", wait)

    def conversation(agent, prompt):
        tools_case.install(agent)
        try:
            execution.execute_tool_calls_concurrent(agent, _message(), [], "task")
            return {"final_response": "late tool conversation"}
        finally:
            conversation_done.set()

    c["callback"] = conversation
    assert jobs.claim_job_for_fire(c["job"]["id"])
    record = None
    try:
        assert scheduler.run_one_job(c["job"]) is False
        assert entered.is_set() and not conversation_done.is_set()
        assert closed == [] and delivered == []
        assert scheduler._terminal_cwd_lock._writer_active
        assert c["job"]["id"] in scheduler.get_running_job_ids()
        record = scheduler._cleanup_unverified_jobs[c["job"]["id"]]
        stored = jobs.get_job(c["job"]["id"])
        old_runtime = stored["dispatch_claim"]["runtime"]
        assert stored["last_status"] == "error" and stored["enabled"] is True
        assert scheduler.run_one_job(stored) is False
        assert jobs.get_job(c["job"]["id"])["dispatch_claim"]["runtime"] == old_runtime
    finally:
        release.set()
        assert conversation_done.wait(3)
        if record is not None:
            record["worker"].result(timeout=3)
        for _ in range(100):
            if c["job"]["id"] not in scheduler.get_running_job_ids():
                break
            threading.Event().wait(0.01)
    assert closed == [True] and delivered == []
    assert not scheduler._terminal_cwd_lock._writer_active
    assert c["job"]["id"] not in scheduler.get_running_job_ids()
    assert "dispatch_claim" not in jobs.get_job(c["job"]["id"])
