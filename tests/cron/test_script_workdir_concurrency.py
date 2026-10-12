"""Pure-script jobs must not queue behind agents or mutate shared cwd state."""

import concurrent.futures
import json
import os
import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def script_env(tmp_path, monkeypatch):
    import cron.scheduler as sched

    home = tmp_path / "home"
    scripts = home / "scripts" / "nested"
    scripts.mkdir(parents=True)
    workdir = tmp_path / "project"
    workdir.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(sched, "_get_hermes_home", lambda: home)
    monkeypatch.setattr(sched, "_cleanup_unverified_jobs", {})
    script = scripts / "poll.py"
    script.write_text(
        "import json, os\n"
        "print(json.dumps({'cwd': os.getcwd(), "
        "'terminal_cwd': os.environ.get('TERMINAL_CWD')}))\n"
    )
    job = {"id": "script-job", "name": "poll", "no_agent": True,
           "script": str(script), "workdir": str(workdir), "deliver": "local"}
    return sched, job, script


@pytest.mark.parametrize("failure", [None, "nonzero", "timeout", "cleanup"])
def test_script_does_not_change_parent_cwd_even_on_failure(script_env, monkeypatch, failure):
    sched, job, script = script_env
    parent_cwd = os.getcwd()
    parent_env = os.environ.copy()
    seen = []

    def run_process(argv, **kwargs):
        seen.append((os.getcwd(), os.environ.copy(), kwargs["cwd"]))
        if failure == "timeout":
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        if failure == "cleanup":
            raise sched.CronScriptCleanupError("synthetic cleanup uncertainty")
        return subprocess.CompletedProcess(argv, 7 if failure == "nonzero" else 0,
                                           stdout="ok", stderr="")

    monkeypatch.setattr(sched, "_run_script_process", run_process)
    pause = MagicMock(return_value="cleanup unverified; job paused")
    monkeypatch.setattr(sched, "_pause_job_for_unverified_script_cleanup", pause)
    success, _, response, error = sched.run_job(job)

    assert seen == [(parent_cwd, parent_env, str(script.parent))]
    assert os.getcwd() == parent_cwd
    assert os.environ.copy() == parent_env
    assert success is (failure is None)
    if failure == "cleanup":
        pause.assert_called_once()
        assert "cleanup unverified" in error
    elif failure == "timeout":
        assert "timed out" in error
    elif failure == "nonzero":
        assert "exited with code 7" in error
    else:
        assert response == "ok"


@pytest.mark.parametrize("baseline", [None, "baseline-project"])
def test_script_runs_during_agent_override_without_leaking_cwd(script_env, monkeypatch, baseline):
    sched, script_job, script = script_env
    if baseline is None:
        monkeypatch.delenv("TERMINAL_CWD", raising=False)
    else:
        monkeypatch.setenv("TERMINAL_CWD", baseline)
    parent_cwd = os.getcwd()
    agent_dir = script.parent.parent.parent / "agent-project"
    agent_dir.mkdir()
    agent_job = {"id": "agent-one", "name": "review", "prompt": "review",
                 "workdir": str(agent_dir), "deliver": "local"}
    next_agent = dict(agent_job, id="agent-two")
    agent_started = threading.Event()
    second_agent_started = threading.Event()
    release_agent = threading.Event()
    script_started = threading.Event()
    release_script = threading.Event()
    script_done = threading.Event()
    calls = []
    saved = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            self.ordinal = len(calls)
            calls.append("agent")

        def run_conversation(self, *args, **kwargs):
            if self.ordinal == 0:
                agent_started.set()
                assert release_agent.wait(15)
            else:
                second_agent_started.set()
            return {"final_response": "review complete", "messages": []}

        def get_activity_summary(self):
            return {"seconds_since_activity": 0.0}

    monkeypatch.setitem(sys.modules, "run_agent", SimpleNamespace(AIAgent=FakeAgent))
    monkeypatch.setattr("hermes_cli.runtime_provider.resolve_runtime_provider", lambda **kw: {
        "provider": "test", "api_key": "synthetic", "base_url": "http://test.invalid",
        "api_mode": "chat_completions",
    })
    monkeypatch.setattr("hermes_cli.env_loader.load_hermes_dotenv", lambda **kw: None)
    monkeypatch.setattr("hermes_cli.env_loader.reset_secret_source_cache", lambda: None)
    monkeypatch.setattr("hermes_state.SessionDB", MagicMock())
    monkeypatch.setattr(sched, "load_config", lambda: {})
    monkeypatch.setattr(sched, "_build_job_prompt", lambda *a, **kw: "review")
    monkeypatch.setattr(sched, "_resolve_origin", lambda job: None)
    monkeypatch.setattr(sched, "_resolve_delivery_target", lambda job: None)
    monkeypatch.setattr(sched, "_resolve_cron_enabled_toolsets", lambda *a: None)
    monkeypatch.setattr(sched, "_teardown_cron_agent", lambda *a: None)
    monkeypatch.setenv("HERMES_CRON_TIMEOUT", "0")
    monkeypatch.setattr(sched, "_running_job_ids", set())
    monkeypatch.setattr(sched, "_record_running_marker", lambda *a: None)
    monkeypatch.setattr(sched, "advance_next_run", lambda *a: None)
    monkeypatch.setattr(sched, "claim_dispatch", lambda *a: True)
    monkeypatch.setattr("cron.jobs.set_dispatch_claim_status", lambda *a: None)
    monkeypatch.setattr(sched, "save_job_output", lambda jid, output: saved.update({jid: output}))
    monkeypatch.setattr(sched, "_deliver_result", lambda *a, **kw: None)
    monkeypatch.setattr(sched, "mark_job_run", lambda jid, *a, **kw:
                        script_done.set() if jid == script_job["id"] else None)
    original_process = sched._run_script_process

    def blocked_script(argv, **kwargs):
        calls.append("script")
        script_started.set()
        assert release_script.wait(15)
        return original_process(argv, **kwargs)

    monkeypatch.setattr(sched, "_run_script_process", blocked_script)
    due = [agent_job]
    monkeypatch.setattr(sched, "get_due_jobs", lambda: list(due))
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as seq, \
         concurrent.futures.ThreadPoolExecutor(max_workers=2) as parallel, \
         concurrent.futures.ThreadPoolExecutor(max_workers=1) as scripts:
        monkeypatch.setattr(sched, "_get_sequential_pool", lambda: seq)
        monkeypatch.setattr(sched, "_get_parallel_pool", lambda workers: parallel)
        monkeypatch.setattr(sched, "_get_script_pool", lambda: scripts)
        try:
            assert sched.tick(verbose=False, sync=False) == 1
            assert agent_started.wait(5), "mock agent did not start"
            assert os.environ["TERMINAL_CWD"] == str(agent_dir)
            due[:] = [script_job, next_agent]
            assert sched.tick(verbose=False, sync=False) == 2
            assert script_started.wait(3), "script queued behind the blocked agent"
            assert not second_agent_started.is_set()
            assert os.getcwd() == parent_cwd
            assert os.environ["TERMINAL_CWD"] == str(agent_dir)
            # Both queued and executing jobs retain the existing overlap guard.
            assert sched.tick(verbose=False, sync=False) == 0
            assert calls.count("script") == 1
            release_script.set()
            assert script_done.wait(5), "script did not finish while agent was blocked"
            assert str(script.parent) in saved[script_job["id"]]
            expected_env = json.dumps({"cwd": str(script.parent), "terminal_cwd": baseline})
            assert expected_env in saved[script_job["id"]]
            assert not second_agent_started.is_set()
        finally:
            release_script.set()
            release_agent.set()
    assert second_agent_started.is_set()
    assert os.getcwd() == parent_cwd
    assert os.environ.get("TERMINAL_CWD") == baseline
    assert sched._terminal_cwd_baseline is None
    assert sched._running_job_ids == set()


def test_saturated_agent_pool_does_not_block_script(script_env, monkeypatch):
    sched, script_job, _ = script_env
    agent_job = {"id": "parallel-agent", "prompt": "review"}
    agent_started = threading.Event()
    release_agent = threading.Event()
    script_done = threading.Event()
    due = [agent_job]

    def run_one(job, **kwargs):
        if job["id"] == agent_job["id"]:
            agent_started.set()
            assert release_agent.wait(10)
        else:
            script_done.set()
        return True

    monkeypatch.setattr(sched, "get_due_jobs", lambda: list(due))
    monkeypatch.setattr(sched, "advance_next_run", lambda *a: None)
    monkeypatch.setattr(sched, "_record_running_marker", lambda *a: None)
    monkeypatch.setattr("cron.jobs.set_dispatch_claim_status", lambda *a: None)
    monkeypatch.setattr(sched, "_running_job_ids", set())
    monkeypatch.setattr(sched, "run_one_job", run_one)
    monkeypatch.setenv("HERMES_CRON_MAX_PARALLEL", "1")
    # A script without workdir formerly shared the saturated agent pool too.
    script_job["workdir"] = None
    try:
        assert sched.tick(verbose=False, sync=False) == 1
        assert agent_started.wait(3)
        due[:] = [script_job]
        assert sched.tick(verbose=False, sync=False) == 1
        assert script_done.wait(3), "script queued behind a workdir-less agent"
    finally:
        release_agent.set()
        sched._shutdown_parallel_pool()


def test_script_pool_serializes_and_drains_accepted_work(monkeypatch):
    import cron.scheduler as sched

    monkeypatch.setattr(sched, "_parallel_pool", None)
    monkeypatch.setattr(sched, "_sequential_pool", None)
    monkeypatch.setattr(sched, "_script_pool", None)
    started = threading.Event()
    release = threading.Event()
    shutdown_started = threading.Event()
    shutdown_done = threading.Event()
    completed = []
    pool = sched._get_script_pool()
    assert sched._get_script_pool() is pool

    def first():
        started.set()
        assert release.wait(5)
        completed.append("first")

    def shutdown():
        shutdown_started.set()
        sched._shutdown_parallel_pool()
        shutdown_done.set()

    first_future = pool.submit(first)
    second_future = pool.submit(lambda: completed.append("second"))
    thread = threading.Thread(target=shutdown)
    try:
        assert started.wait(3)
        assert not second_future.done()
        thread.start()
        assert shutdown_started.wait(3)
        assert not shutdown_done.is_set()
    finally:
        release.set()
        if thread.ident is not None:
            thread.join(5)
        else:
            sched._shutdown_parallel_pool()
    first_future.result(timeout=1)
    second_future.result(timeout=1)
    assert shutdown_done.is_set()
    assert completed == ["first", "second"]
    assert sched._script_pool is None


def test_agent_prerun_script_keeps_its_agent_environment(script_env, monkeypatch):
    sched, job, script = script_env
    monkeypatch.setenv("TERMINAL_CWD", "active-agent-project")
    monkeypatch.setattr(sched, "_terminal_cwd_baseline", {"TERMINAL_CWD": "baseline"})
    job["no_agent"] = False
    success, output = sched._run_scheduled_job_script(job, str(script))
    assert success
    assert json.loads(output) == {
        "cwd": str(script.parent), "terminal_cwd": "active-agent-project",
    }
