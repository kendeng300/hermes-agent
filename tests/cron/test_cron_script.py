"""Tests for cron job script injection feature.

Tests cover:
- Script field in job creation / storage / update
- Script execution and output injection into prompts
- Error handling (missing script, timeout, non-zero exit)
- Path resolution (absolute, relative to HERMES_HOME/scripts/)
"""

import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Ensure project root is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def cron_env(tmp_path, monkeypatch):
    """Isolated cron environment with temp HERMES_HOME."""
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "cron").mkdir()
    (hermes_home / "cron" / "output").mkdir()
    (hermes_home / "scripts").mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    # Clear cached module-level paths
    import cron.jobs as jobs_mod
    monkeypatch.setattr(jobs_mod, "HERMES_DIR", hermes_home)
    monkeypatch.setattr(jobs_mod, "CRON_DIR", hermes_home / "cron")
    monkeypatch.setattr(jobs_mod, "JOBS_FILE", hermes_home / "cron" / "jobs.json")
    monkeypatch.setattr(jobs_mod, "OUTPUT_DIR", hermes_home / "cron" / "output")

    return hermes_home


class TestJobScriptField:
    """Test that the script field is stored and retrieved correctly."""

    def test_create_job_with_script(self, cron_env):
        from cron.jobs import create_job, get_job

        job = create_job(
            prompt="Analyze the data",
            schedule="every 30m",
            script="/path/to/monitor.py",
        )
        assert job["script"] == "/path/to/monitor.py"

        loaded = get_job(job["id"])
        assert loaded["script"] == "/path/to/monitor.py"

    def test_create_job_without_script(self, cron_env):
        from cron.jobs import create_job

        job = create_job(prompt="Hello", schedule="every 1h")
        assert job.get("script") is None

    def test_create_job_empty_script_normalized_to_none(self, cron_env):
        from cron.jobs import create_job

        job = create_job(prompt="Hello", schedule="every 1h", script="  ")
        assert job.get("script") is None

    def test_update_job_add_script(self, cron_env):
        from cron.jobs import create_job, update_job

        job = create_job(prompt="Hello", schedule="every 1h")
        assert job.get("script") is None

        updated = update_job(job["id"], {"script": "/new/script.py"})
        assert updated["script"] == "/new/script.py"

    def test_update_job_clear_script(self, cron_env):
        from cron.jobs import create_job, update_job

        job = create_job(prompt="Hello", schedule="every 1h", script="/some/script.py")
        assert job["script"] == "/some/script.py"

        updated = update_job(job["id"], {"script": None})
        assert updated.get("script") is None


def test_cronjob_tool_rejects_stale_past_one_shot(cron_env, monkeypatch):
    from tools.cronjob_tools import cronjob

    now = datetime(2026, 3, 18, 4, 30, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("cron.jobs._hermes_now", lambda: now)
    stale = (now - timedelta(minutes=5)).isoformat()

    result = json.loads(cronjob(action="create", prompt="Too late", schedule=stale))

    assert result["success"] is False
    assert "past and cannot be scheduled" in result["error"]


class TestRunJobScript:
    """Test the _run_job_script() function."""

    def test_successful_script(self, cron_env):
        from cron.scheduler import _run_job_script

        script = cron_env / "scripts" / "test.py"
        script.write_text('print("hello from script")\n')

        success, output = _run_job_script(str(script))
        assert success is True
        assert output == "hello from script"

    def test_script_relative_path(self, cron_env):
        from cron.scheduler import _run_job_script

        script = cron_env / "scripts" / "relative.py"
        script.write_text('print("relative works")\n')

        success, output = _run_job_script("relative.py")
        assert success is True
        assert output == "relative works"

    def test_script_not_found(self, cron_env):
        from cron.scheduler import _run_job_script

        success, output = _run_job_script("nonexistent_script.py")
        assert success is False
        assert "not found" in output.lower()

    def test_script_nonzero_exit(self, cron_env):
        from cron.scheduler import _run_job_script

        script = cron_env / "scripts" / "fail.py"
        script.write_text(textwrap.dedent("""\
            import sys
            print("partial output")
            print("error info", file=sys.stderr)
            sys.exit(1)
        """))

        success, output = _run_job_script(str(script))
        assert success is False
        assert "exited with code 1" in output
        assert "error info" in output

    @pytest.mark.parametrize("returncode", [0, 7])
    def test_immediate_exit_handshake_is_repeatable(
        self, cron_env, returncode
    ):
        """A target that is already a zombie still has a stable birth ID."""
        from cron.scheduler import _run_job_script

        script = cron_env / "scripts" / f"immediate_{returncode}.py"
        script.write_text(
            f"import sys\nprint('instant-{returncode}')\nsys.exit({returncode})\n"
        )
        for _ in range(8):
            success, output = _run_job_script(str(script))
            assert success is (returncode == 0)
            if returncode == 0:
                assert output == "instant-0"
            else:
                assert "Script exited with code 7" in output
                assert "instant-7" in output

    def test_immediate_wake_gate_handshake_is_repeatable(self, cron_env):
        from cron.scheduler import _parse_wake_gate, _run_job_script

        script = cron_env / "scripts" / "immediate_wake.py"
        script.write_text('print(\'{"wakeAgent": false}\')\n')
        for _ in range(8):
            success, output = _run_job_script(str(script))
            assert success is True
            assert _parse_wake_gate(output) is False

    def test_script_subprocess_env_sanitized(self, cron_env, monkeypatch):
        """Cron scripts must not inherit Hermes provider env (SECURITY.md §2.3)."""
        from tools.environments.local import _HERMES_PROVIDER_ENV_BLOCKLIST
        from cron.scheduler import _run_job_script

        # sorted() so the probed var is deterministic across runs
        # (frozenset iteration order varies with PYTHONHASHSEED).
        blocked_var = sorted(_HERMES_PROVIDER_ENV_BLOCKLIST)[0]
        monkeypatch.setenv(blocked_var, "must_not_leak")

        script = cron_env / "scripts" / "env_probe.py"
        script.write_text(
            textwrap.dedent(
                f"""\
                import os
                key = {blocked_var!r}
                print("PRESENT" if os.environ.get(key) else "ABSENT")
                """
            )
        )

        success, output = _run_job_script("env_probe.py")
        assert success is True
        assert output == "ABSENT"

    def test_script_empty_output(self, cron_env):
        from cron.scheduler import _run_job_script

        script = cron_env / "scripts" / "empty.py"
        script.write_text("# no output\n")

        success, output = _run_job_script(str(script))
        assert success is True
        assert output == ""

    def test_script_timeout(self, cron_env, monkeypatch):
        from cron import scheduler as sched_mod
        from cron.scheduler import _run_job_script

        # Use a very short timeout
        monkeypatch.setattr(sched_mod, "_SCRIPT_TIMEOUT", 1)

        script = cron_env / "scripts" / "slow.py"
        script.write_text("import time; time.sleep(30)\n")

        success, output = _run_job_script(str(script))
        assert success is False
        assert "timed out" in output.lower()

    @pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux subreaper")
    @pytest.mark.live_system_guard_bypass
    def test_script_timeout_kills_descendant_process(self, cron_env, monkeypatch):
        """A timed-out wrapper must not leave its long-running child alive."""
        import psutil
        from cron import scheduler as sched_mod
        from cron.scheduler import _run_job_script

        monkeypatch.setattr(sched_mod, "_SCRIPT_TIMEOUT", 1)

        child_pid_path = cron_env / "scripts" / "child.identity"
        child = cron_env / "scripts" / "child.py"
        child.write_text(textwrap.dedent(f"""\
            import os
            import pathlib
            import time

            stat = pathlib.Path(f"/proc/{{os.getpid()}}/stat").read_text()
            birth = stat.rsplit(")", 1)[1].split()[19]
            pathlib.Path({str(child_pid_path)!r}).write_text(
                f"{{os.getpid()}}:{{birth}}"
            )
            time.sleep(30)
        """))
        wrapper = cron_env / "scripts" / "wrapper.py"
        wrapper.write_text(textwrap.dedent(f"""\
            import pathlib
            import subprocess
            import sys
            import time

            subprocess.Popen([sys.executable, {str(child)!r}])
            time.sleep(30)
        """))

        identity = None
        try:
            success, output = _run_job_script(str(wrapper))
            assert success is False
            assert "timed out" in output.lower()
            identity = self._read_identity(child_pid_path)
            self._assert_identity_exits(identity)
        finally:
            identity = identity or self._read_identity_if_present(child_pid_path)
            if identity is not None:
                self._kill_identity_if_live(identity)

    @pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux subreaper")
    @pytest.mark.live_system_guard_bypass
    def test_script_timeout_kills_escaped_session_child(self, cron_env, monkeypatch):
        """A setsid child remains owned even after leaving the initial group."""
        from cron import scheduler as sched_mod
        from cron.scheduler import _run_job_script

        monkeypatch.setattr(sched_mod, "_SCRIPT_TIMEOUT", 1)
        child_pid_path = cron_env / "scripts" / "escaped.identity"
        child = cron_env / "scripts" / "escaped.py"
        child.write_text(textwrap.dedent(f"""\
            import os
            import pathlib
            import time

            stat = pathlib.Path(f"/proc/{{os.getpid()}}/stat").read_text()
            birth = stat.rsplit(")", 1)[1].split()[19]
            pathlib.Path({str(child_pid_path)!r}).write_text(
                f"{{os.getpid()}}:{{birth}}"
            )
            time.sleep(30)
        """))
        wrapper = cron_env / "scripts" / "escaped_wrapper.py"
        wrapper.write_text(textwrap.dedent(f"""\
            import pathlib
            import subprocess
            import sys
            import time

            subprocess.Popen(
                [sys.executable, {str(child)!r}],
                start_new_session=True,
            )
            time.sleep(30)
        """))

        identity = None
        try:
            success, output = _run_job_script(str(wrapper))
            assert success is False
            assert "timed out" in output.lower()
            identity = self._read_identity(child_pid_path)
            self._assert_identity_exits(identity)
        finally:
            identity = identity or self._read_identity_if_present(child_pid_path)
            if identity is not None:
                self._kill_identity_if_live(identity)

    @pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux subreaper")
    @pytest.mark.live_system_guard_bypass
    def test_wrapper_exit_pipe_holder_is_bounded_and_killed(self, cron_env, monkeypatch):
        """A reaped wrapper cannot leave a same-group pipe holder behind."""
        from cron import scheduler as sched_mod
        from cron.scheduler import _run_job_script

        monkeypatch.setattr(sched_mod, "_SCRIPT_TIMEOUT", 1)
        child_pid_path = cron_env / "scripts" / "pipe_holder.identity"
        child = cron_env / "scripts" / "pipe_holder.py"
        child.write_text(textwrap.dedent(f"""\
            import os
            import pathlib
            import time

            stat = pathlib.Path(f"/proc/{{os.getpid()}}/stat").read_text()
            birth = stat.rsplit(")", 1)[1].split()[19]
            pathlib.Path({str(child_pid_path)!r}).write_text(
                f"{{os.getpid()}}:{{birth}}"
            )
            time.sleep(30)
        """))
        wrapper = cron_env / "scripts" / "pipe_wrapper.py"
        wrapper.write_text(textwrap.dedent(f"""\
            import pathlib
            import subprocess
            import sys
            import time

            subprocess.Popen([sys.executable, {str(child)!r}])
            deadline = time.monotonic() + 1
            while not pathlib.Path({str(child_pid_path)!r}).exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError("pipe holder did not publish identity")
                time.sleep(0.01)
        """))

        identity = None
        started = time.monotonic()
        try:
            success, output = _run_job_script(str(wrapper))
            assert time.monotonic() - started < 6
            assert success is True
            assert output == ""
            identity = self._read_identity(child_pid_path)
            self._assert_identity_exits(identity)
        finally:
            identity = identity or self._read_identity_if_present(child_pid_path)
            if identity is not None:
                self._kill_identity_if_live(identity)

    @pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux subreaper")
    @pytest.mark.live_system_guard_bypass
    def test_fast_detached_child_cannot_escape_successful_wrapper(self, cron_env):
        """A fast setsid child is adopted even after redirecting captured pipes."""
        from cron.scheduler import _run_job_script

        child_pid_path = cron_env / "scripts" / "fast_detached.identity"
        wrapper = cron_env / "scripts" / "fast_wrapper.py"
        wrapper.write_text(textwrap.dedent(f"""\
            import os
            import pathlib
            import time

            if os.fork() == 0:
                os.setsid()
                if os.fork() != 0:
                    os._exit(0)
                devnull = os.open(os.devnull, os.O_RDWR)
                for fd in (0, 1, 2):
                    os.dup2(devnull, fd)
                stat = pathlib.Path(f"/proc/{{os.getpid()}}/stat").read_text()
                birth = stat.rsplit(")", 1)[1].split()[19]
                pathlib.Path({str(child_pid_path)!r}).write_text(
                    f"{{os.getpid()}}:{{birth}}"
                )
                time.sleep(30)
            deadline = time.monotonic() + 1
            while not pathlib.Path({str(child_pid_path)!r}).exists():
                if time.monotonic() >= deadline:
                    raise RuntimeError("detached child did not publish identity")
                time.sleep(0.01)
        """))

        identity = None
        try:
            success, output = _run_job_script(str(wrapper))
            assert success is True
            assert output == ""
            identity = self._read_identity(child_pid_path)
            self._assert_identity_exits(identity)
        finally:
            identity = identity or self._read_identity_if_present(child_pid_path)
            if identity is not None:
                self._kill_identity_if_live(identity)

    @staticmethod
    def _read_identity(path):
        pid, birth = path.read_text().split(":")
        return int(pid), int(birth)

    @classmethod
    def _read_identity_if_present(cls, path):
        try:
            return cls._read_identity(path)
        except (FileNotFoundError, ValueError):
            return None

    @staticmethod
    def _current_birth(pid):
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
            return int(stat.rsplit(")", 1)[1].split()[19])
        except (FileNotFoundError, PermissionError, OSError, ValueError, IndexError):
            return None

    @classmethod
    def _assert_identity_exits(cls, identity, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if cls._current_birth(identity[0]) != identity[1]:
                return
            time.sleep(0.05)
        pytest.fail(f"cron script descendant identity {identity!r} is still running")

    @classmethod
    def _kill_identity_if_live(cls, identity):
        import psutil

        pid, birth = identity
        if cls._current_birth(pid) != birth:
            return
        try:
            process = psutil.Process(pid)
            if cls._current_birth(pid) == birth:
                process.kill()
                process.wait(timeout=2)
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            pass

    @pytest.mark.parametrize(
        "platform",
        ["win32", "darwin"],
    )
    def test_unsupported_platform_fails_closed_before_spawn(self, monkeypatch, platform):
        from cron import scheduler as sched_mod

        popen = MagicMock()
        pipe = MagicMock()
        monkeypatch.setattr(sched_mod, "sys", SimpleNamespace(platform=platform))
        monkeypatch.setattr(sched_mod.subprocess, "Popen", popen)
        monkeypatch.setattr(sched_mod.os, "pipe", pipe)

        with pytest.raises(RuntimeError, match=(
            rf"Cron script process-tree containment requires Linux; "
            rf"refusing to spawn on {platform}"
        )):
            sched_mod._run_script_process(["script"], timeout=1, cwd="/", env={})

        pipe.assert_not_called()
        popen.assert_not_called()

    @pytest.mark.parametrize(
        "raised",
        [
            OSError("pipe read failed"),
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte"),
            KeyboardInterrupt(),
            SystemExit(7),
        ],
        ids=["oserror", "decode-error", "keyboard-interrupt", "system-exit"],
    )
    def test_every_post_spawn_exception_cleans_and_preserves_exception(
        self, monkeypatch, raised
    ):
        from cron import scheduler as sched_mod

        actual_fds = {}
        real_pipe = sched_mod.os.pipe

        def capture_pipe():
            pair = real_pipe()
            actual_fds["pair"] = pair
            return pair

        process = MagicMock(pid=43210, returncode=None)
        process.communicate.side_effect = raised
        cleanup = MagicMock(return_value=None)
        popen = MagicMock(return_value=process)
        monkeypatch.setattr(sched_mod.os, "pipe", capture_pipe)
        monkeypatch.setattr(sched_mod.subprocess, "Popen", popen)
        monkeypatch.setattr(sched_mod, "_read_supervisor_start", MagicMock(return_value=(50, 60)))
        monkeypatch.setattr(sched_mod, "_cleanup_preserving_exception", cleanup)

        with pytest.raises(type(raised)) as caught:
            sched_mod._run_script_process(["script"], timeout=1, cwd="/", env={})

        assert caught.value is raised
        read_fd, write_fd = actual_fds["pair"]
        assert popen.call_args.kwargs["pass_fds"] == (write_fd,)
        cleanup.assert_called_once_with(process, (50, 60), read_fd)

    @pytest.mark.parametrize(
        "close_error",
        [OSError("close failed"), KeyboardInterrupt(), SystemExit(8)],
        ids=["oserror", "keyboard-interrupt", "system-exit"],
    )
    def test_post_spawn_control_fd_close_exception_cleans(
        self, monkeypatch, close_error
    ):
        from cron import scheduler as sched_mod

        process = MagicMock(pid=43210, returncode=None)
        real_close = sched_mod.os.close
        cleanup = MagicMock(return_value=None)

        def _close(fd):
            if fd == 101:
                raise close_error
            return real_close(fd)

        monkeypatch.setattr(sched_mod.os, "pipe", MagicMock(return_value=(100, 101)))
        monkeypatch.setattr(sched_mod.os, "close", _close)
        monkeypatch.setattr(sched_mod.subprocess, "Popen", MagicMock(return_value=process))
        monkeypatch.setattr(sched_mod, "_cleanup_preserving_exception", cleanup)

        with pytest.raises(type(close_error)) as caught:
            sched_mod._run_script_process(["script"], timeout=1, cwd="/", env={})

        assert caught.value is close_error
        cleanup.assert_called_once_with(process, None, 100)

    def test_cleanup_baseexception_after_success_is_propagated(self, monkeypatch):
        from cron import scheduler as sched_mod

        actual_fds = {}
        real_pipe = sched_mod.os.pipe

        def capture_pipe():
            pair = real_pipe()
            actual_fds["pair"] = pair
            return pair

        process = MagicMock(pid=43210, returncode=0)
        process.communicate.return_value = ("out", "err")
        cleanup_error = SystemExit(9)
        cleanup = MagicMock(side_effect=cleanup_error)
        preserving = MagicMock(return_value=None)
        popen = MagicMock(return_value=process)
        monkeypatch.setattr(sched_mod.os, "pipe", capture_pipe)
        monkeypatch.setattr(sched_mod.subprocess, "Popen", popen)
        monkeypatch.setattr(sched_mod, "_read_supervisor_start", MagicMock(return_value=(50, 60)))
        monkeypatch.setattr(sched_mod, "_cleanup_linux_supervisor", cleanup)
        monkeypatch.setattr(sched_mod, "_cleanup_preserving_exception", preserving)

        with pytest.raises(SystemExit) as caught:
            sched_mod._run_script_process(["script"], timeout=1, cwd="/", env={})

        assert caught.value is cleanup_error
        read_fd, write_fd = actual_fds["pair"]
        assert popen.call_args.kwargs["pass_fds"] == (write_fd,)
        preserving.assert_called_once_with(process, (50, 60), read_fd)

    def test_active_exception_cleanup_retries_without_masking(self, monkeypatch):
        from cron import scheduler as sched_mod

        process = MagicMock(pid=43210)
        cleanup = MagicMock(side_effect=[KeyboardInterrupt(), None])
        monkeypatch.setattr(sched_mod, "_cleanup_linux_supervisor", cleanup)

        sched_mod._cleanup_preserving_exception(process, (50, 60), 15)

        assert cleanup.call_count == 2

    def test_timeout_with_unverified_cleanup_has_distinct_outward_error(
        self, monkeypatch
    ):
        from cron import scheduler as sched_mod

        process = MagicMock(pid=43210, returncode=None)
        timeout = subprocess.TimeoutExpired("script", 1)
        process.communicate.side_effect = timeout
        cleanup = sched_mod.CronScriptCleanupError("attestation missing")
        monkeypatch.setattr(
            sched_mod.subprocess, "Popen", MagicMock(return_value=process)
        )
        monkeypatch.setattr(
            sched_mod,
            "_read_supervisor_start",
            MagicMock(return_value=(50, 60)),
        )
        monkeypatch.setattr(
            sched_mod,
            "_cleanup_preserving_exception",
            MagicMock(return_value=cleanup),
        )

        with pytest.raises(sched_mod.CronScriptCleanupError) as caught:
            sched_mod._run_script_process(
                ["script"], timeout=1, cwd="/", env={}
            )

        assert caught.value.original_error is timeout
        assert "TimeoutExpired" in str(caught.value)
        assert "attestation missing" in str(caught.value)

    @pytest.mark.parametrize(
        "attestation",
        [
            "missing RESULT",
            "invalid RESULT bytes",
            "supervisor exited 124 with CLEANUP UNKNOWN",
        ],
    )
    def test_cleanup_unverified_durably_pauses_only_exact_job(
        self, cron_env, monkeypatch, attestation
    ):
        from cron import scheduler as sched_mod
        from cron.jobs import create_job, get_job

        script = cron_env / "scripts" / "pause.py"
        script.write_text("print('never')\n")
        job = create_job(prompt="one", schedule="every 5m", script="pause.py")
        other = create_job(prompt="two", schedule="every 5m")
        cleanup = sched_mod.CronScriptCleanupError(
            f"TimeoutExpired after 1s; cleanup: {attestation}"
        )
        monkeypatch.setattr(sched_mod, "_run_job_script", MagicMock(side_effect=cleanup))
        monkeypatch.setattr(sched_mod, "_notify_provider_jobs_changed", MagicMock())
        try:
            ok, error = sched_mod._run_scheduled_job_script(job, "pause.py")
            paused = get_job(job["id"])
            unchanged = get_job(other["id"])
            assert ok is False
            assert "cleanup unverified" in error
            assert paused["enabled"] is False
            assert paused["state"] == "paused"
            assert paused["paused_reason"] == paused["last_error"] == error
            assert "TimeoutExpired" in error and attestation in error
            assert unchanged["enabled"] is True
            assert unchanged["state"] == "scheduled"
        finally:
            with sched_mod._running_lock:
                sched_mod._cleanup_unverified_jobs.pop(job["id"], None)

    def test_pause_persistence_failure_blocks_next_in_process_spawn(
        self, monkeypatch
    ):
        from cron import jobs as jobs_mod
        from cron import scheduler as sched_mod

        job = {"id": "cleanup-uncertain", "enabled": True, "state": "scheduled"}
        cleanup = sched_mod.CronScriptCleanupError("missing cleanup attestation")
        monkeypatch.setattr(
            jobs_mod, "update_job", MagicMock(side_effect=OSError("disk unavailable"))
        )
        claim = MagicMock()
        monkeypatch.setattr(sched_mod, "claim_dispatch", claim)
        try:
            with pytest.raises(
                sched_mod.CronScriptCleanupError, match="CRITICAL"
            ) as caught:
                sched_mod._pause_job_for_unverified_script_cleanup(job, cleanup)
            assert job["enabled"] is False
            assert job["state"] == "paused"
            assert "disk unavailable" in str(caught.value)
            assert sched_mod.run_one_job(job) is False
            claim.assert_not_called()
        finally:
            with sched_mod._running_lock:
                sched_mod._cleanup_unverified_jobs.pop(job["id"], None)

    @pytest.mark.parametrize(
        ("schedule", "repeat"),
        [
            ("every 5m", None),
            ("every 5m", 3),
            ((datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(), 1),
        ],
        ids=["recurring", "finite-repeat", "one-shot"],
    )
    def test_cleanup_quarantine_preserves_paused_row_across_finalization(
        self, cron_env, monkeypatch, schedule, repeat
    ):
        from cron import jobs as jobs_mod
        from cron import scheduler as sched_mod
        from cron.jobs import create_job, get_job

        job = create_job(
            prompt="run",
            schedule=schedule,
            repeat=repeat,
            script="owned.py",
        )
        paused_postimage = {}

        def fail_with_cleanup(target, *, defer_agent_teardown=None):
            cleanup = sched_mod.CronScriptCleanupError(
                "TimeoutExpired; cleanup: missing RESULT"
            )
            reason = sched_mod._pause_job_for_unverified_script_cleanup(
                target, cleanup
            )
            paused_postimage.update(get_job(target["id"]))
            return False, reason, "", reason

        mark = MagicMock()
        monkeypatch.setattr(sched_mod, "run_job", fail_with_cleanup)
        monkeypatch.setattr(sched_mod, "save_job_output", MagicMock(return_value="out"))
        monkeypatch.setattr(sched_mod, "_deliver_result", MagicMock(return_value=None))
        monkeypatch.setattr(sched_mod, "mark_job_run", mark)
        monkeypatch.setattr(sched_mod, "_notify_provider_jobs_changed", MagicMock())
        try:
            assert sched_mod.run_one_job(job) is False
            assert get_job(job["id"]) == paused_postimage
            assert paused_postimage["enabled"] is False
            assert paused_postimage["state"] == "paused"
            assert paused_postimage["last_error"] == paused_postimage["paused_reason"]
            mark.assert_not_called()
            jobs_mod.mark_job_run(job["id"], True)
            assert get_job(job["id"]) == paused_postimage
        finally:
            with sched_mod._running_lock:
                sched_mod._cleanup_unverified_jobs.pop(job["id"], None)

    def test_builtin_tick_accepts_exact_durable_resume(self, cron_env, monkeypatch):
        from cron import scheduler as sched_mod
        from cron.jobs import create_job, get_job, resume_job

        job = create_job(prompt="run", schedule="every 5m")
        cleanup = sched_mod.CronScriptCleanupError("cleanup attestation missing")
        monkeypatch.setattr(sched_mod, "_notify_provider_jobs_changed", MagicMock())
        sched_mod._pause_job_for_unverified_script_cleanup(job, cleanup)
        resumed = resume_job(job["id"])
        assert resumed["state"] == "scheduled"

        monkeypatch.setattr(sched_mod, "get_due_jobs", MagicMock(return_value=[job]))
        monkeypatch.setattr(sched_mod, "advance_next_run", MagicMock(return_value=True))
        monkeypatch.setattr(
            sched_mod,
            "_get_lock_paths",
            MagicMock(return_value=(cron_env / "cron", cron_env / "cron" / "tick.lock")),
        )
        monkeypatch.setattr(
            sched_mod, "run_job", MagicMock(return_value=(True, "out", "done", None))
        )
        monkeypatch.setattr(sched_mod, "save_job_output", MagicMock(return_value="out"))
        monkeypatch.setattr(sched_mod, "_deliver_result", MagicMock(return_value=None))
        try:
            assert sched_mod.tick(verbose=False, sync=True) == 1
            assert get_job(job["id"])["last_status"] == "ok"
            with sched_mod._running_lock:
                assert job["id"] not in sched_mod._cleanup_unverified_jobs
        finally:
            with sched_mod._running_lock:
                sched_mod._cleanup_unverified_jobs.pop(job["id"], None)

    def test_provider_fire_accepts_exact_durable_trigger(self, cron_env, monkeypatch):
        from cron import scheduler as sched_mod
        from cron.jobs import create_job, get_job, trigger_job
        from cron.scheduler_provider import InProcessCronScheduler

        job = create_job(prompt="run", schedule="every 5m")
        cleanup = sched_mod.CronScriptCleanupError("cleanup attestation invalid")
        monkeypatch.setattr(sched_mod, "_notify_provider_jobs_changed", MagicMock())
        sched_mod._pause_job_for_unverified_script_cleanup(job, cleanup)
        assert trigger_job(job["id"])["state"] == "scheduled"
        monkeypatch.setattr(
            sched_mod, "run_job", MagicMock(return_value=(True, "out", "done", None))
        )
        monkeypatch.setattr(sched_mod, "save_job_output", MagicMock(return_value="out"))
        monkeypatch.setattr(sched_mod, "_deliver_result", MagicMock(return_value=None))
        try:
            assert InProcessCronScheduler().fire_due(job["id"]) is True
            assert get_job(job["id"])["last_status"] == "ok"
            with sched_mod._running_lock:
                assert job["id"] not in sched_mod._cleanup_unverified_jobs
        finally:
            with sched_mod._running_lock:
                sched_mod._cleanup_unverified_jobs.pop(job["id"], None)

    def test_manual_fire_accepts_resume_and_returns_current_result(
        self, cron_env, monkeypatch
    ):
        from cron import scheduler as sched_mod
        from cron.jobs import create_job, get_job, resume_job
        from tools.cronjob_tools import _execute_job_now

        job = create_job(prompt="run", schedule="every 5m")
        cleanup = sched_mod.CronScriptCleanupError("cleanup attestation missing")
        monkeypatch.setattr(sched_mod, "_notify_provider_jobs_changed", MagicMock())
        sched_mod._pause_job_for_unverified_script_cleanup(job, cleanup)
        resume_job(job["id"])
        monkeypatch.setattr(
            sched_mod, "run_job", MagicMock(return_value=(True, "out", "done", None))
        )
        monkeypatch.setattr(sched_mod, "save_job_output", MagicMock(return_value="out"))
        monkeypatch.setattr(sched_mod, "_deliver_result", MagicMock(return_value=None))
        try:
            result = _execute_job_now(job)
            assert result == {"claimed": True, "success": True, "error": None}
            assert get_job(job["id"])["last_status"] == "ok"
        finally:
            with sched_mod._running_lock:
                sched_mod._cleanup_unverified_jobs.pop(job["id"], None)

    def test_pause_persistence_failure_is_actionable_for_manual_and_provider(
        self, cron_env, monkeypatch
    ):
        from cron import jobs as jobs_mod
        from cron import scheduler as sched_mod
        from cron.scheduler_provider import InProcessCronScheduler
        from tools.cronjob_tools import _execute_job_now

        job = jobs_mod.create_job(prompt="run", schedule="every 5m")
        original_update = jobs_mod.update_job
        monkeypatch.setattr(
            jobs_mod, "update_job", MagicMock(side_effect=OSError("disk unavailable"))
        )
        cleanup = sched_mod.CronScriptCleanupError("cleanup attestation missing")
        try:
            with pytest.raises(sched_mod.CronScriptCleanupError, match="CRITICAL"):
                sched_mod._pause_job_for_unverified_script_cleanup(job, cleanup)
            monkeypatch.setattr(jobs_mod, "update_job", original_update)
            spawn = MagicMock()
            monkeypatch.setattr(sched_mod, "claim_dispatch", spawn)

            manual = _execute_job_now(job)
            assert manual["claimed"] is True
            assert manual["success"] is False
            assert "cleanup attestation missing" in manual["error"]
            assert "durable pause failed: disk unavailable" in manual["error"]
            assert InProcessCronScheduler().fire_due(job["id"]) is False
            spawn.assert_not_called()
        finally:
            with sched_mod._running_lock:
                sched_mod._cleanup_unverified_jobs.pop(job["id"], None)

    def test_verified_cleanup_timeout_does_not_pause(self, monkeypatch):
        from cron import scheduler as sched_mod

        pause = MagicMock()
        monkeypatch.setattr(
            sched_mod,
            "_run_job_script",
            MagicMock(return_value=(False, "Script timed out after 1s")),
        )
        monkeypatch.setattr(sched_mod, "_pause_job_for_unverified_script_cleanup", pause)

        assert sched_mod._run_scheduled_job_script(
            {"id": "ordinary-timeout"}, "slow.py"
        ) == (False, "Script timed out after 1s")
        pause.assert_not_called()

    def test_next_tick_filters_cleanup_unverified_job_before_advance_or_spawn(
        self, cron_env, monkeypatch
    ):
        from cron import scheduler as sched_mod

        job = {
            "id": "quarantined-next-tick",
            "enabled": True,
            "state": "scheduled",
        }
        advance = MagicMock()
        run = MagicMock()
        monkeypatch.setattr(sched_mod, "get_due_jobs", MagicMock(return_value=[job]))
        monkeypatch.setattr(sched_mod, "advance_next_run", advance)
        monkeypatch.setattr(sched_mod, "run_one_job", run)
        monkeypatch.setattr(
            sched_mod,
            "_get_lock_paths",
            MagicMock(return_value=(cron_env / "cron", cron_env / "cron" / "tick.lock")),
        )
        try:
            with sched_mod._running_lock:
                sched_mod._cleanup_unverified_jobs[job["id"]] = {
                    "reason": "cleanup uncertain",
                    "pause_persisted": False,
                }
            assert sched_mod.tick(verbose=False) == 0
            advance.assert_not_called()
            run.assert_not_called()
        finally:
            with sched_mod._running_lock:
                sched_mod._cleanup_unverified_jobs.pop(job["id"], None)

    def test_agent_script_path_pauses_before_agent_spawn(
        self, cron_env, monkeypatch
    ):
        from cron import scheduler as sched_mod
        from cron.jobs import create_job, get_job

        script = cron_env / "scripts" / "agent_gate.py"
        script.write_text("print('never')\n")
        job = create_job(
            prompt="report", schedule="every 5m", script="agent_gate.py"
        )
        agent = MagicMock()
        monkeypatch.setitem(sys.modules, "run_agent", SimpleNamespace(AIAgent=agent))
        monkeypatch.setattr(
            sched_mod,
            "_run_job_script",
            MagicMock(side_effect=sched_mod.CronScriptCleanupError(
                "TimeoutExpired; cleanup: invalid RESULT"
            )),
        )
        monkeypatch.setattr(sched_mod, "_notify_provider_jobs_changed", MagicMock())
        try:
            success, doc, final, error = sched_mod.run_job(job)
            stored = get_job(job["id"])
            assert success is False
            assert final == ""
            assert "cleanup unverified" in doc
            assert error == stored["last_error"] == stored["paused_reason"]
            assert stored["enabled"] is False and stored["state"] == "paused"
            agent.assert_not_called()
        finally:
            with sched_mod._running_lock:
                sched_mod._cleanup_unverified_jobs.pop(job["id"], None)

    def test_all_job_aware_script_callers_use_pause_wrapper(self):
        import inspect
        from cron import scheduler as sched_mod

        assert inspect.getsource(sched_mod.run_job).count(
            "_run_scheduled_job_script(job, script_path)"
        ) == 2
        assert inspect.getsource(sched_mod._build_job_prompt).count(
            "_run_scheduled_job_script(job, script_path)"
        ) == 1

    def test_invalid_protocol_kills_birth_matched_target_before_owner(self, monkeypatch):
        from cron import scheduler as sched_mod

        events = []
        process = MagicMock(pid=40)
        process.poll.return_value = None
        process.terminate.side_effect = lambda: events.append("owner-term-request")
        process.wait.side_effect = [subprocess.TimeoutExpired("supervisor", 2), None]
        process.kill.side_effect = lambda: events.append("owner-kill")
        monkeypatch.setattr(
            sched_mod, "_linux_process_probe", MagicMock(side_effect=["LIVE", "LIVE", "GONE"])
        )
        monkeypatch.setattr(sched_mod.os, "getpgid", MagicMock(return_value=50))
        monkeypatch.setattr(sched_mod.os, "killpg", MagicMock(
            side_effect=lambda *_args: events.append("target-group-kill")
        ))
        monkeypatch.setattr(sched_mod, "_read_supervisor_status", MagicMock(return_value=b""))

        with pytest.raises(sched_mod.CronScriptCleanupError, match="supervisor result"):
            sched_mod._cleanup_linux_supervisor(process, (50, 60), 15)

        assert events == ["owner-term-request", "target-group-kill", "owner-kill"]

    def test_fallback_rejects_reused_target_identity(self, monkeypatch):
        from cron import scheduler as sched_mod

        process = MagicMock(pid=40)
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired("supervisor", 2), None]
        monkeypatch.setattr(sched_mod, "_linux_process_probe", MagicMock(return_value="GONE"))
        monkeypatch.setattr(sched_mod, "_read_supervisor_status", MagicMock(return_value=b""))
        killpg = MagicMock()
        monkeypatch.setattr(sched_mod.os, "killpg", killpg)

        with pytest.raises(sched_mod.CronScriptCleanupError, match="supervisor result"):
            sched_mod._cleanup_linux_supervisor(process, (50, 60), 15)

        killpg.assert_not_called()
        process.kill.assert_called_once()

    def test_supervisor_exit_124_cleanup_failure_is_not_accepted(self, monkeypatch):
        from cron import scheduler as sched_mod

        process = MagicMock(pid=40, returncode=124)
        process.poll.return_value = 124
        process.wait.return_value = 124
        monkeypatch.setattr(
            sched_mod,
            "_read_supervisor_status",
            MagicMock(return_value=b"CLEANUP UNKNOWN\n"),
        )
        monkeypatch.setattr(
            sched_mod, "_linux_process_probe", MagicMock(return_value="GONE")
        )

        with pytest.raises(sched_mod.CronScriptCleanupError, match="supervisor result"):
            sched_mod._cleanup_linux_supervisor(process, (50, 60), 15)

    def test_supervisor_complete_cleanup_protocol_is_accepted(self, monkeypatch):
        from cron import scheduler as sched_mod

        process = MagicMock(pid=40, returncode=124)
        process.poll.return_value = 124
        process.wait.return_value = 124
        monkeypatch.setattr(
            sched_mod,
            "_read_supervisor_status",
            MagicMock(return_value=b"CLEANUP COMPLETE\n"),
        )
        monkeypatch.setattr(
            sched_mod, "_linux_process_probe", MagicMock(return_value="GONE")
        )

        assert sched_mod._cleanup_linux_supervisor(process, (50, 60), 15) == (
            b"CLEANUP COMPLETE\n"
        )

    def test_result_protocol_cannot_override_live_target(self, monkeypatch):
        from cron import scheduler as sched_mod

        process = MagicMock(pid=40, returncode=0)
        process.poll.return_value = 0
        process.wait.return_value = 0
        monkeypatch.setattr(
            sched_mod,
            "_read_supervisor_status",
            MagicMock(return_value=b"RESULT 0\n"),
        )
        monkeypatch.setattr(
            sched_mod,
            "_linux_process_probe",
            MagicMock(side_effect=["LIVE", "LIVE", "LIVE", "GONE"]),
        )
        monkeypatch.setattr(sched_mod.os, "getpgid", MagicMock(return_value=50))
        killpg = MagicMock()
        monkeypatch.setattr(sched_mod.os, "killpg", killpg)

        with pytest.raises(sched_mod.CronScriptCleanupError, match="remained live"):
            sched_mod._cleanup_linux_supervisor(process, (50, 60), 15)

        killpg.assert_called_once_with(50, signal.SIGKILL)

    def test_owner_local_census_error_is_unknown(self, monkeypatch):
        from cron import script_supervisor as supervisor

        monkeypatch.setattr(
            supervisor,
            "_task_children",
            MagicMock(return_value=(supervisor.Probe.UNKNOWN, set())),
        )

        state, identities = supervisor._owned_census()
        assert state is supervisor.Probe.UNKNOWN
        assert identities == []

    def test_child_stat_error_is_unknown_not_empty(self, monkeypatch):
        from cron import script_supervisor as supervisor

        root = os.getpid()
        monkeypatch.setattr(
            supervisor,
            "_task_children",
            MagicMock(return_value=(supervisor.Probe.PRESENT, {43210})),
        )
        monkeypatch.setattr(
            supervisor,
            "_read_identity",
            MagicMock(return_value=(supervisor.Probe.UNKNOWN, None)),
        )

        state, identities = supervisor._owned_census()
        assert root != 43210
        assert state is supervisor.Probe.UNKNOWN
        assert identities == []

    def test_signal_error_yields_unknown_cleanup(self, monkeypatch):
        from cron import script_supervisor as supervisor

        identity = supervisor.ProcessIdentity(51, 100, os.getpid(), "S")
        monkeypatch.setattr(supervisor, "_CLEANUP_SECONDS", 0.03)
        monkeypatch.setattr(
            supervisor,
            "_owned_census",
            MagicMock(return_value=(supervisor.Probe.PRESENT, [identity])),
        )
        monkeypatch.setattr(
            supervisor,
            "_signal_identity",
            MagicMock(return_value=supervisor.Probe.UNKNOWN),
        )
        monkeypatch.setattr(
            supervisor,
            "_reap_direct",
            MagicMock(return_value=supervisor.Probe.PRESENT),
        )

        assert supervisor._cleanup(MagicMock(pid=50)) is supervisor.Cleanup.UNKNOWN

    def test_reused_pid_is_never_signaled(self, monkeypatch):
        from cron import script_supervisor as supervisor

        observed = supervisor.ProcessIdentity(51, 100, os.getpid(), "S")
        reused = supervisor.ProcessIdentity(51, 101, os.getpid(), "S")
        monkeypatch.setattr(
            supervisor,
            "_read_identity",
            MagicMock(return_value=(supervisor.Probe.PRESENT, reused)),
        )
        kill = MagicMock()
        monkeypatch.setattr(supervisor.os, "kill", kill)

        assert supervisor._signal_identity(observed, signal.SIGKILL) is supervisor.Probe.GONE
        kill.assert_not_called()

    def test_supervisor_stops_tree_before_killing_for_fork_race(self, monkeypatch):
        from cron import script_supervisor as supervisor

        events = []

        parent = supervisor.ProcessIdentity(51, 100, os.getpid(), "S")
        late_child = supervisor.ProcessIdentity(52, 101, 51, "S")
        monkeypatch.setattr(supervisor, "_owned_census", MagicMock(side_effect=[
            (supervisor.Probe.PRESENT, [parent]),
            (supervisor.Probe.PRESENT, [parent, late_child]),
            (supervisor.Probe.PRESENT, []),
            (supervisor.Probe.PRESENT, []),
        ]))
        monkeypatch.setattr(
            supervisor,
            "_signal_identity",
            MagicMock(side_effect=lambda ident, sig: (
                events.append((ident.pid, sig)) or supervisor.Probe.PRESENT
            )),
        )
        monkeypatch.setattr(
            supervisor,
            "_reap_direct",
            MagicMock(return_value=supervisor.Probe.PRESENT),
        )
        target = MagicMock(pid=50)

        assert supervisor._cleanup(target) is supervisor.Cleanup.COMPLETE
        assert events == [
            (51, signal.SIGSTOP),
            (52, signal.SIGKILL),
            (51, signal.SIGKILL),
        ]

    def test_normal_path_contains_no_host_wide_process_polling(self):
        import inspect
        from cron import scheduler as sched_mod
        from cron import script_supervisor as supervisor

        source = inspect.getsource(sched_mod._run_script_process)
        source += inspect.getsource(sched_mod._cleanup_linux_supervisor)
        source += inspect.getsource(sched_mod._kill_known_target_group)
        source += inspect.getsource(sched_mod._linux_process_probe)
        source += inspect.getsource(supervisor)
        assert "process_iter" not in source
        assert "psutil" not in source
        assert "_ScriptProcessTracker" not in inspect.getsource(sched_mod)
        assert "/proc/self/task" in source
        assert 'f"/proc/{pid}/task"' in source

    @pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux subreaper")
    @pytest.mark.live_system_guard_bypass
    def test_real_supervisor_crash_after_start_rejects_and_kills_live_target(
        self, cron_env, monkeypatch
    ):
        """Missing RESULT after helper death cannot accept a still-live target."""
        from cron import scheduler as sched_mod
        from cron.scheduler import _run_job_script

        monkeypatch.setattr(sched_mod, "_SCRIPT_TIMEOUT", 1)
        target_path = cron_env / "scripts" / "crashed_owner_target.identity"
        script = cron_env / "scripts" / "crash_owner.py"
        script.write_text(textwrap.dedent(f"""\
            import os
            import pathlib
            import signal
            import time

            stat = pathlib.Path(f"/proc/{{os.getpid()}}/stat").read_text()
            birth = stat.rsplit(")", 1)[1].split()[19]
            pathlib.Path({str(target_path)!r}).write_text(f"{{os.getpid()}}:{{birth}}")
            os.kill(os.getppid(), signal.SIGKILL)
            time.sleep(30)
        """))

        identity = None
        try:
            with pytest.raises(sched_mod.CronScriptCleanupError) as caught:
                _run_job_script(str(script))
            assert "TimeoutExpired" in str(caught.value)
            assert "supervisor result was missing" in str(caught.value)
            identity = self._read_identity(target_path)
            self._assert_identity_exits(identity)
        finally:
            identity = identity or self._read_identity_if_present(target_path)
            if identity is not None:
                self._kill_identity_if_live(identity)

    def test_script_json_output(self, cron_env):
        """Scripts can output structured JSON for the LLM to parse."""
        from cron.scheduler import _run_job_script

        script = cron_env / "scripts" / "json_out.py"
        script.write_text(textwrap.dedent("""\
            import json
            data = {"new_prs": [{"number": 42, "title": "Fix bug"}]}
            print(json.dumps(data, indent=2))
        """))

        success, output = _run_job_script(str(script))
        assert success is True
        parsed = json.loads(output)
        assert parsed["new_prs"][0]["number"] == 42


class TestBuildJobPromptWithScript:
    """Test that script output is injected into the prompt."""

    def test_script_output_injected(self, cron_env):
        from cron.scheduler import _build_job_prompt

        script = cron_env / "scripts" / "data.py"
        script.write_text('print("new PR: #123 fix typo")\n')

        job = {
            "prompt": "Report any notable changes.",
            "script": str(script),
        }
        prompt = _build_job_prompt(job)
        assert "## Script Output" in prompt
        assert "new PR: #123 fix typo" in prompt
        assert "Report any notable changes." in prompt

    def test_script_error_injected(self, cron_env):
        from cron.scheduler import _build_job_prompt

        job = {
            "prompt": "Report status.",
            "script": "nonexistent_monitor.py",
        }
        prompt = _build_job_prompt(job)
        assert "## Script Error" in prompt
        assert "not found" in prompt.lower()
        assert "Report status." in prompt

    def test_no_script_unchanged(self, cron_env):
        from cron.scheduler import _build_job_prompt

        job = {"prompt": "Simple job."}
        prompt = _build_job_prompt(job)
        assert "## Script Output" not in prompt
        assert "Simple job." in prompt



class TestCronjobToolScript:
    """Test the cronjob tool's script parameter."""

    def test_create_with_script(self, cron_env, monkeypatch):
        monkeypatch.setenv("HERMES_INTERACTIVE", "1")
        from tools.cronjob_tools import cronjob

        result = json.loads(cronjob(
            action="create",
            schedule="every 1h",
            prompt="Monitor things",
            script="monitor.py",
        ))
        assert result["success"] is True
        assert result["job"]["script"] == "monitor.py"

    def test_update_script(self, cron_env, monkeypatch):
        monkeypatch.setenv("HERMES_INTERACTIVE", "1")
        from tools.cronjob_tools import cronjob

        create_result = json.loads(cronjob(
            action="create",
            schedule="every 1h",
            prompt="Monitor things",
        ))
        job_id = create_result["job_id"]

        update_result = json.loads(cronjob(
            action="update",
            job_id=job_id,
            script="new_script.py",
        ))
        assert update_result["success"] is True
        assert update_result["job"]["script"] == "new_script.py"

    def test_clear_script(self, cron_env, monkeypatch):
        monkeypatch.setenv("HERMES_INTERACTIVE", "1")
        from tools.cronjob_tools import cronjob

        create_result = json.loads(cronjob(
            action="create",
            schedule="every 1h",
            prompt="Monitor things",
            script="some_script.py",
        ))
        job_id = create_result["job_id"]

        update_result = json.loads(cronjob(
            action="update",
            job_id=job_id,
            script="",
        ))
        assert update_result["success"] is True
        assert "script" not in update_result["job"]

    def test_list_shows_script(self, cron_env, monkeypatch):
        monkeypatch.setenv("HERMES_INTERACTIVE", "1")
        from tools.cronjob_tools import cronjob

        cronjob(
            action="create",
            schedule="every 1h",
            prompt="Monitor things",
            script="data_collector.py",
        )

        list_result = json.loads(cronjob(action="list"))
        assert list_result["success"] is True
        assert len(list_result["jobs"]) == 1
        assert list_result["jobs"][0]["script"] == "data_collector.py"


class TestScriptPathContainment:
    """Regression tests for path containment bypass in _run_job_script().

    Prior to the fix, absolute paths and ~-prefixed paths bypassed the
    scripts_dir containment check entirely, allowing arbitrary script
    execution through the cron system.
    """

    def test_absolute_path_outside_scripts_dir_blocked(self, cron_env):
        """Absolute paths outside ~/.hermes/scripts/ must be rejected."""
        from cron.scheduler import _run_job_script

        # Create a script outside the scripts dir
        outside_script = cron_env / "outside.py"
        outside_script.write_text('print("should not run")\n')

        success, output = _run_job_script(str(outside_script))
        assert success is False
        assert "blocked" in output.lower() or "outside" in output.lower()

    def test_absolute_path_tmp_blocked(self, cron_env):
        """Absolute paths to /tmp must be rejected."""
        from cron.scheduler import _run_job_script

        success, output = _run_job_script("/tmp/evil.py")
        assert success is False
        assert "blocked" in output.lower() or "outside" in output.lower()

    def test_tilde_path_blocked(self, cron_env):
        """~ prefixed paths must be rejected (expanduser bypasses check)."""
        from cron.scheduler import _run_job_script

        success, output = _run_job_script("~/evil.py")
        assert success is False
        assert "blocked" in output.lower() or "outside" in output.lower()

    def test_tilde_traversal_blocked(self, cron_env):
        """~/../../../tmp/evil.py must be rejected."""
        from cron.scheduler import _run_job_script

        success, output = _run_job_script("~/../../../tmp/evil.py")
        assert success is False
        assert "blocked" in output.lower() or "outside" in output.lower()

    def test_relative_traversal_still_blocked(self, cron_env):
        """../../etc/passwd style traversal must still be blocked."""
        from cron.scheduler import _run_job_script

        success, output = _run_job_script("../../etc/passwd")
        assert success is False
        assert "blocked" in output.lower() or "outside" in output.lower()

    def test_relative_path_inside_scripts_dir_allowed(self, cron_env):
        """Relative paths within the scripts dir should still work."""
        from cron.scheduler import _run_job_script

        script = cron_env / "scripts" / "good.py"
        script.write_text('print("ok")\n')

        success, output = _run_job_script("good.py")
        assert success is True
        assert output == "ok"

    def test_subdirectory_inside_scripts_dir_allowed(self, cron_env):
        """Relative paths to subdirectories within scripts/ should work."""
        from cron.scheduler import _run_job_script

        subdir = cron_env / "scripts" / "monitors"
        subdir.mkdir()
        script = subdir / "check.py"
        script.write_text('print("sub ok")\n')

        success, output = _run_job_script("monitors/check.py")
        assert success is True
        assert output == "sub ok"

    def test_absolute_path_inside_scripts_dir_allowed(self, cron_env):
        """Absolute paths that resolve WITHIN scripts/ should work."""
        from cron.scheduler import _run_job_script

        script = cron_env / "scripts" / "abs_ok.py"
        script.write_text('print("abs ok")\n')

        success, output = _run_job_script(str(script))
        assert success is True
        assert output == "abs ok"

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Symlinks require elevated privileges on Windows",
    )
    def test_symlink_escape_blocked(self, cron_env, tmp_path):
        """Symlinks pointing outside scripts/ must be rejected."""
        from cron.scheduler import _run_job_script

        # Create a script outside the scripts dir
        outside = tmp_path / "outside_evil.py"
        outside.write_text('print("escaped")\n')

        # Create a symlink inside scripts/ pointing outside
        link = cron_env / "scripts" / "sneaky.py"
        link.symlink_to(outside)

        success, output = _run_job_script("sneaky.py")
        assert success is False
        assert "blocked" in output.lower() or "outside" in output.lower()


class TestCronjobToolScriptValidation:
    """Test API-boundary validation of cron script paths in cronjob_tools."""

    def test_create_with_absolute_script_rejected(self, cron_env, monkeypatch):
        monkeypatch.setenv("HERMES_INTERACTIVE", "1")
        from tools.cronjob_tools import cronjob

        result = json.loads(cronjob(
            action="create",
            schedule="every 1h",
            prompt="Monitor things",
            script="/home/user/evil.py",
        ))
        assert result["success"] is False
        assert "relative" in result["error"].lower() or "absolute" in result["error"].lower()

    def test_create_with_tilde_script_rejected(self, cron_env, monkeypatch):
        monkeypatch.setenv("HERMES_INTERACTIVE", "1")
        from tools.cronjob_tools import cronjob

        result = json.loads(cronjob(
            action="create",
            schedule="every 1h",
            prompt="Monitor things",
            script="~/monitor.py",
        ))
        assert result["success"] is False
        assert "relative" in result["error"].lower() or "absolute" in result["error"].lower()

    def test_create_with_traversal_script_rejected(self, cron_env, monkeypatch):
        monkeypatch.setenv("HERMES_INTERACTIVE", "1")
        from tools.cronjob_tools import cronjob

        result = json.loads(cronjob(
            action="create",
            schedule="every 1h",
            prompt="Monitor things",
            script="../../etc/passwd",
        ))
        assert result["success"] is False
        assert "escapes" in result["error"].lower() or "traversal" in result["error"].lower()

    def test_create_with_relative_script_allowed(self, cron_env, monkeypatch):
        monkeypatch.setenv("HERMES_INTERACTIVE", "1")
        from tools.cronjob_tools import cronjob

        result = json.loads(cronjob(
            action="create",
            schedule="every 1h",
            prompt="Monitor things",
            script="monitor.py",
        ))
        assert result["success"] is True
        assert result["job"]["script"] == "monitor.py"

    def test_update_with_absolute_script_rejected(self, cron_env, monkeypatch):
        monkeypatch.setenv("HERMES_INTERACTIVE", "1")
        from tools.cronjob_tools import cronjob

        create_result = json.loads(cronjob(
            action="create",
            schedule="every 1h",
            prompt="Monitor things",
        ))
        job_id = create_result["job_id"]

        update_result = json.loads(cronjob(
            action="update",
            job_id=job_id,
            script="/tmp/evil.py",
        ))
        assert update_result["success"] is False
        assert "relative" in update_result["error"].lower() or "absolute" in update_result["error"].lower()

    def test_update_clear_script_allowed(self, cron_env, monkeypatch):
        """Clearing a script (empty string) should always be permitted."""
        monkeypatch.setenv("HERMES_INTERACTIVE", "1")
        from tools.cronjob_tools import cronjob

        create_result = json.loads(cronjob(
            action="create",
            schedule="every 1h",
            prompt="Monitor things",
            script="monitor.py",
        ))
        job_id = create_result["job_id"]

        update_result = json.loads(cronjob(
            action="update",
            job_id=job_id,
            script="",
        ))
        assert update_result["success"] is True
        assert "script" not in update_result["job"]

    def test_windows_absolute_path_rejected(self, cron_env, monkeypatch):
        monkeypatch.setenv("HERMES_INTERACTIVE", "1")
        from tools.cronjob_tools import cronjob

        result = json.loads(cronjob(
            action="create",
            schedule="every 1h",
            prompt="Monitor things",
            script="C:\\Users\\evil\\script.py",
        ))
        assert result["success"] is False


class TestRunJobEnvVarCleanup:
    """Test that run_job() env vars are cleaned up even on early failure."""

    def test_env_vars_cleaned_on_early_error(self, cron_env, monkeypatch):
        """Origin env vars must be cleaned up even if run_job fails early."""
        # Ensure env vars are clean before test
        for key in (
            "HERMES_SESSION_PLATFORM",
            "HERMES_SESSION_CHAT_ID",
            "HERMES_SESSION_CHAT_NAME",
        ):
            monkeypatch.delenv(key, raising=False)

        # Build a job with origin info that will fail during execution
        # (no valid model, no API key — will raise inside try block)
        job = {
            "id": "test-envleak",
            "name": "env-leak-test",
            "prompt": "test",
            "schedule_display": "every 1h",
            "origin": {
                "platform": "telegram",
                "chat_id": "12345",
                "chat_name": "Test Chat",
            },
        }

        from cron.scheduler import run_job

        # Expect it to fail (no model/API key), but env vars must be cleaned
        try:
            run_job(job)
        except Exception:
            pass

        # Verify env vars were cleaned up by the finally block
        assert os.environ.get("HERMES_SESSION_PLATFORM") is None
        assert os.environ.get("HERMES_SESSION_CHAT_ID") is None
        assert os.environ.get("HERMES_SESSION_CHAT_NAME") is None
