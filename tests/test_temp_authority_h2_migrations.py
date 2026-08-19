"""Behavioral contracts for non-agent/gateway TempAuthority migrations."""

from __future__ import annotations

import os
import importlib.util
import socket
import subprocess
import sys
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from hermes_constants import get_hermes_home, get_real_home
from hermes_temp import TempAuthorityCleanupError, current_temp_authority
from acp_adapter.edit_approval import (
    AUTO_APPROVE_WORKSPACE,
    EditProposal,
    should_auto_approve_edit,
)
from tools.browser_tool import _socket_safe_tmpdir
from tools.code_execution_tool import _rpc_socket_endpoints
from tools.environments.base import BaseEnvironment
from tools.environments.daytona import DaytonaEnvironment
from tools.environments.local import LocalEnvironment
from tools.tool_result_storage import _resolve_storage_dir
from tools.voice_mode import _allocate_voice_temp_file, cleanup_voice_temp_file


def test_local_consumers_share_exact_bound_authority() -> None:
    with current_temp_authority() as authority:
        expected = str(authority.root)
    local = LocalEnvironment.__new__(LocalEnvironment)
    local.env = {}
    assert local.get_temp_dir() == expected
    if len(expected.encode()) <= 72:
        assert _socket_safe_tmpdir() == expected
    else:
        with pytest.raises(RuntimeError, match="too long"):
            _socket_safe_tmpdir()
    assert _resolve_storage_dir(None) == f"{expected}/hermes-results"
    assert Path(expected).parent == get_hermes_home()


def test_result_storage_rejects_backend_without_temp_authority() -> None:
    with pytest.raises(RuntimeError, match="temporary authority"):
        _resolve_storage_dir(SimpleNamespace())


def test_code_rpc_long_path_uses_pinned_procfs_uds_or_fails_closed() -> None:
    with current_temp_authority() as authority:
        owned = authority.mkdir("rpc-endpoint")
        try:
            bind, client = _rpc_socket_endpoints(str(owned.path), authority._root_fd)
            assert not bind.startswith("tcp://")
            assert not client.startswith("tcp://")
            if len(os.fsencode(str(owned.path / "rpc.sock"))) > 103:
                assert bind.startswith("/proc/self/fd/")
                assert client.startswith(f"/proc/{os.getpid()}/fd/")
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                server.bind(bind)
            except PermissionError:
                # The outer test sandbox denies procfs magic-link socket
                # creation. This is the required fail-closed host outcome;
                # there is deliberately no AF_INET retry.
                server.close()
                assert bind.startswith("/proc/self/fd/")
                return
            server.listen(1)
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "import os,socket; s=socket.socket(socket.AF_UNIX); "
                    "s.connect(os.environ['ENDPOINT']); s.sendall(b'child'); "
                    "assert s.recv(8)==b'parent'; s.close()",
                ],
                env={"ENDPOINT": client},
                stdin=subprocess.DEVNULL,
            )
            connection, _ = server.accept()
            assert connection.recv(8) == b"child"
            connection.sendall(b"parent")
            connection.close()
            server.close()
            assert child.wait(timeout=5) == 0
        finally:
            owned.cleanup()


def test_code_rpc_rejects_unpinned_or_unavailable_procfs(monkeypatch, tmp_path: Path) -> None:
    other_parent = tmp_path / "other"
    other_parent.mkdir(mode=0o700)
    child = other_parent / "sandbox"
    child.mkdir(mode=0o700)
    with current_temp_authority() as authority:
        with pytest.raises(RuntimeError, match="root identity changed"):
            _rpc_socket_endpoints(str(child), authority._root_fd)
        monkeypatch.setattr("tools.code_execution_tool.os.path.isdir", lambda _path: False)
        long_child = authority.root / ("x" * 32)
        long_child.mkdir(mode=0o700)
        try:
            with pytest.raises(RuntimeError, match="procfs"):
                _rpc_socket_endpoints(str(long_child), authority._root_fd)
        finally:
            long_child.rmdir()


def test_acp_workspace_temp_admission_is_exact_authority_bound() -> None:
    with current_temp_authority() as authority:
        proposal = EditProposal("write_file", str(authority.root / "candidate.txt"), None, "x", {})
        assert should_auto_approve_edit(proposal, AUTO_APPROVE_WORKSPACE) is True
    host_global = EditProposal("write_file", "/var/tmp/not-owned.txt", None, "x", {})
    assert should_auto_approve_edit(host_global, AUTO_APPROVE_WORKSPACE) is False


def test_voice_file_custody_is_unique_idempotent_and_replacement_safe() -> None:
    first = _allocate_voice_temp_file(".wav")
    second = _allocate_voice_temp_file(".wav")
    assert first != second
    assert cleanup_voice_temp_file(first) is True
    assert cleanup_voice_temp_file(first) is False

    victim = Path(second)
    victim.unlink()
    victim.write_bytes(b"replacement")
    with pytest.raises(TempAuthorityCleanupError, match="replaced"):
        cleanup_voice_temp_file(second)
    assert victim.read_bytes() == b"replacement"
    victim.unlink()


def test_daytona_archive_uses_bound_remote_authority(monkeypatch, tmp_path: Path) -> None:
    commands: list[str] = []
    sandbox = SimpleNamespace(
        process=SimpleNamespace(exec=lambda command: commands.append(command)),
        fs=SimpleNamespace(download_file=lambda remote, local: commands.append(f"GET {remote}")),
    )
    environment = DaytonaEnvironment.__new__(DaytonaEnvironment)
    environment._sandbox = sandbox
    environment._bind_backend_temp_home("/home/daytona")
    environment._remote_home = "/home/daytona"
    monkeypatch.setattr("tools.environments.daytona.os.getpid", lambda: 321)

    environment._daytona_bulk_download(tmp_path / "archive.tar")

    assert commands[0].startswith("tar cf /home/daytona/.hermes/tmp/hermes-sync-321.tar ")
    assert commands[1] == "GET /home/daytona/.hermes/tmp/hermes-sync-321.tar"
    assert commands[2] == "rm -f /home/daytona/.hermes/tmp/hermes-sync-321.tar"
    assert all(" cf /tmp/" not in command for command in commands)
    assert all(not command.startswith("GET /tmp/") for command in commands)


def test_real_home_unknown_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr("hermes_constants._iter_real_home_candidates", lambda _env: [])
    with pytest.raises(RuntimeError, match="private real user home"):
        get_real_home({})


def test_remote_bootstrap_exports_exact_backend_authority() -> None:
    class CaptureEnvironment(BaseEnvironment):
        def __init__(self) -> None:
            self._bind_backend_temp_home("/remote/home")
            super().__init__(cwd="/remote/home", timeout=1)
            self.command = ""

        def _run_bash(self, command, **_kwargs):
            self.command = command
            return object()

        def _wait_for_process(self, _proc, timeout=1):
            del timeout
            return {
                "returncode": 0,
                "output": (
                    "\n__HERMES_TEMP_IDENTITY__12:34__HERMES_TEMP_IDENTITY__\n"
                    f"\n{self._cwd_marker}/remote/home{self._cwd_marker}\n"
                ),
            }

        def cleanup(self) -> None:
            return None

    environment = CaptureEnvironment()
    environment.init_session()
    assert environment._snapshot_ready is True
    assert "install -d -m 700 /remote/home/.hermes/tmp" in environment.command
    assert "while [ \"$__hermes_p\" != / ]" in environment.command
    assert "stat -Lc '%d:%i' /remote/home/.hermes/tmp" in environment.command
    assert "export TMPDIR=/remote/home/.hermes/tmp" in environment.command
    assert "TEMP=/remote/home/.hermes/tmp" in environment.command
    assert "TMP=/remote/home/.hermes/tmp" in environment.command
    wrapped = environment._wrap_command("true", "/remote/home")
    assert "test ! -L \"$__hermes_p\"" in wrapped
    assert "stat -Lc '%d:%i' /remote/home/.hermes/tmp" in wrapped
    assert "12:34" in wrapped


class _ExecutableRemoteEnvironment(BaseEnvironment):
    def __init__(self, home: Path) -> None:
        self._bind_backend_temp_home(str(home))
        super().__init__(cwd=str(home), timeout=3)

    def _run_bash(self, command, **_kwargs):
        environment = dict(os.environ)
        environment["HOME"] = self._backend_home
        return subprocess.Popen(
            ["bash", "-c", command],
            cwd="/",
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    def cleanup(self) -> None:
        return None


def test_remote_authority_rejects_symlink_mode_owner_and_identity_changes(tmp_path: Path) -> None:
    real_home = tmp_path / "real-home"
    real_home.mkdir(mode=0o700)
    linked_home = tmp_path / "linked-home"
    linked_home.symlink_to(real_home, target_is_directory=True)
    with pytest.raises(RuntimeError, match="authority bootstrap"):
        _ExecutableRemoteEnvironment(linked_home).init_session()

    wrong_mode = tmp_path / "wrong-mode"
    wrong_mode.mkdir(mode=0o700)
    wrong_mode.chmod(0o770)
    with pytest.raises(RuntimeError, match="authority bootstrap"):
        _ExecutableRemoteEnvironment(wrong_mode).init_session()

    # /usr is a stable existing path not owned by the unprivileged runner;
    # the ownership check must stop before any .hermes creation attempt.
    if os.geteuid() != 0:
        with pytest.raises(RuntimeError, match="authority bootstrap"):
            _ExecutableRemoteEnvironment(Path("/usr")).init_session()

    healthy = tmp_path / "healthy-home"
    healthy.mkdir(mode=0o700)
    environment = _ExecutableRemoteEnvironment(healthy)
    environment.init_session()
    temp_root = healthy / ".hermes" / "tmp"
    original = healthy / ".hermes" / "tmp-original"
    temp_root.rename(original)
    temp_root.mkdir(mode=0o700)
    wrapped = environment._wrap_command("printf should-not-run", str(healthy))
    result = environment._wait_for_process(environment._run_bash(wrapped), timeout=3)
    assert result["returncode"] == 125
    assert "should-not-run" not in result["output"]


def test_ssh_constructor_failure_reaps_local_authority(monkeypatch) -> None:
    from tools.environments import ssh as ssh_module

    with current_temp_authority() as authority:
        before = set(authority.root.glob("ssh-control-*"))
    monkeypatch.setattr(ssh_module, "_ensure_ssh_available", lambda: None)
    monkeypatch.setattr(
        ssh_module.SSHEnvironment,
        "_establish_connection",
        lambda self: (_ for _ in ()).throw(RuntimeError("connect failed")),
    )
    with pytest.raises(RuntimeError, match="connect failed"):
        ssh_module.SSHEnvironment("example.invalid", "alice")
    with current_temp_authority() as authority:
        assert set(authority.root.glob("ssh-control-*")) == before


def test_ssh_sync_failure_still_reaps_local_authority() -> None:
    from tools.environments import ssh as ssh_module

    environment = ssh_module.SSHEnvironment.__new__(ssh_module.SSHEnvironment)
    environment.host = "example.invalid"
    environment.user = "alice"
    environment.control_socket = Path("/nonexistent/control.sock")
    environment._temp_authority = current_temp_authority()
    environment._control_dir_owner = environment._temp_authority.mkdir("ssh-control")
    owned_path = environment._control_dir_owner.path
    environment._sync_manager = SimpleNamespace(
        sync_back=lambda: (_ for _ in ()).throw(RuntimeError("sync failed"))
    )
    with pytest.raises(RuntimeError, match="sync failed"):
        environment._release_local_authority(sync_back=True)
    assert not owned_path.exists()
    assert environment._temp_authority is None


def test_python_temp_consumers_have_no_ambient_tempfile_calls() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = (
        root / "acp_adapter/edit_approval.py",
        root / "cli.py",
        root / "optional-skills/creative/pixel-art/scripts/pixel_art_video.py",
        root / "optional-skills/finance/excel-author/scripts/recalc.py",
    )
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "tempfile.gettempdir" not in source
        assert "tempfile.TemporaryDirectory" not in source


def test_excel_recalc_uses_owned_authority_directory(monkeypatch, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "optional-skills/finance/excel-author/scripts/recalc.py"
    spec = importlib.util.spec_from_file_location("_h2_excel_recalc", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = tmp_path / "book.xlsx"
    source.write_bytes(b"input")
    observed: dict[str, Path] = {}

    monkeypatch.setattr(module, "find_libreoffice", lambda: "/usr/bin/libreoffice")

    def fake_run(argv, **_kwargs):
        outdir = Path(argv[argv.index("--outdir") + 1])
        observed["outdir"] = outdir
        (outdir / source.name).write_bytes(b"recalculated")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    result = module.recalc(str(source))
    assert result["status"] == "success"
    assert source.read_bytes() == b"recalculated"
    assert not observed["outdir"].exists()


def test_lazy_constraints_retain_identity_custody_until_cleanup(monkeypatch) -> None:
    from tools import lazy_deps

    distribution = SimpleNamespace(metadata={"Name": "example-core"}, version="1.2.3")
    monkeypatch.setattr("importlib.metadata.distributions", lambda: [distribution])
    constraints = lazy_deps._core_constraints_file()
    assert constraints is not None
    assert constraints.path.read_text(encoding="utf-8") == "example-core==1.2.3\n"
    constraints.owned.verify()
    path = constraints.path
    constraints.cleanup()
    assert not path.exists()


def test_shell_temp_authority_allocates_private_bound_objects(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    helper = root / "scripts/lib/temp-authority.sh"
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    home.chmod(0o700)
    environment = {
        "HOME": str(home),
        "HERMES_HOME": str(home / ".hermes"),
        "PATH": "/usr/bin:/bin",
    }
    command = (
        f". {helper!s}; "
        "hermes_temp_file owned_file shell-proof .txt; "
        "hermes_temp_dir owned_dir shell-proof-dir; "
        "printf '%s\\n%s\\n' \"$owned_file\" \"$owned_dir\""
    )
    result = subprocess.run(
        ["bash", "-c", command],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    file_name, dir_name = result.stdout.splitlines()
    expected_root = home / ".hermes" / "tmp"
    owned_file = Path(file_name)
    owned_dir = Path(dir_name)
    assert owned_file.parent == expected_root
    assert owned_dir.parent == expected_root
    assert owned_file.stat().st_mode & 0o777 == 0o600
    assert owned_dir.stat().st_mode & 0o777 == 0o700
    assert expected_root.stat().st_mode & 0o777 == 0o700


def test_shell_temp_authority_rejects_partial_insecure_and_symlinked_roots(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[1]
    helper = root / "scripts/lib/temp-authority.sh"
    home = tmp_path / "home"
    home.mkdir(mode=0o700)
    home.chmod(0o700)
    hermes_home = home / ".hermes"
    base_environment = {
        "HOME": str(home),
        "HERMES_HOME": str(hermes_home),
        "PATH": "/usr/bin:/bin",
    }

    partial = dict(base_environment)
    partial["HERMES_TEMP_ROOT"] = str(hermes_home / "tmp")
    result = subprocess.run(
        ["bash", "-c", f". {helper!s}; hermes_temp_authority_init"],
        env=partial,
        check=False,
    )
    assert result.returncode == 125

    hermes_home.mkdir(mode=0o700)
    hermes_home.chmod(0o770)
    result = subprocess.run(
        ["bash", "-c", f". {helper!s}; hermes_temp_authority_init"],
        env=base_environment,
        check=False,
    )
    assert result.returncode == 125
    hermes_home.chmod(0o700)

    real = tmp_path / "real-hermes"
    real.mkdir(mode=0o700)
    hermes_home.rmdir()
    hermes_home.symlink_to(real, target_is_directory=True)
    result = subprocess.run(
        ["bash", "-c", f". {helper!s}; hermes_temp_authority_init"],
        env=base_environment,
        check=False,
    )
    assert result.returncode == 125


def test_shell_and_standalone_installer_reject_system_temp_roots_without_mutation() -> None:
    root = Path(__file__).resolve().parents[1]
    helper = root / "scripts/lib/temp-authority.sh"
    installer_source = (root / "scripts/install.sh").read_text(encoding="utf-8")
    installer_functions = installer_source[
        installer_source.index("_installer_temp_init()"):
        installer_source.index("# INSTALL_DIR is resolved")
    ]
    forbidden_roots = (
        Path("/tmp") / "hermes-authority-must-not-exist",
        Path("/var/tmp") / "hermes-authority-must-not-exist",
        Path("/dev/shm") / "hermes-authority-must-not-exist",
        Path("/private/tmp") / "hermes-authority-must-not-exist",
        Path("/private/var/tmp") / "hermes-authority-must-not-exist",
    )
    for forbidden in forbidden_roots:
        assert not forbidden.exists()
        environment = {
            "HOME": "/home/hermes-test",
            "HERMES_HOME": str(forbidden),
            "PATH": "/usr/bin:/bin",
        }
        helper_result = subprocess.run(
            ["bash", "-c", f". {helper!s}; hermes_temp_authority_init"],
            env=environment,
            check=False,
        )
        installer_result = subprocess.run(
            ["bash", "-c", installer_functions + "\n_installer_temp_init"],
            env=environment,
            check=False,
        )
        assert helper_result.returncode == 125
        assert installer_result.returncode == 125
        assert not forbidden.exists()

def test_owned_shell_and_workflow_sources_have_no_system_temp_fallbacks() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = (
        "scripts/lib/temp-authority.sh",
        "scripts/install.sh",
        "setup-hermes.sh",
        "scripts/dev-sandbox.sh",
        "scripts/lib/node-bootstrap.sh",
        "optional-skills/productivity/here-now/scripts/drive.sh",
        "skills/creative/p5js/scripts/render.sh",
        ".github/workflows/deploy-site.yml",
        ".github/workflows/docker.yml",
        ".github/workflows/supply-chain-audit.yml",
    )
    ambient_allocator = "mk" + "temp"
    system_sink = re.compile(
        r"(?:>|>>|\bmkdir\b|\btouch\b|\bcat\b)\s*[\"']?"
        r"/(?:tmp|var/tmp|dev/shm)(?:/|[\"']|\s|$)"
    )
    for relative in paths:
        source = (root / relative).read_text(encoding="utf-8")
        assert ambient_allocator not in source, relative
        assert system_sink.search(source) is None, relative


def test_skill_shell_consumers_resolve_packaged_temp_authority_location() -> None:
    root = Path(__file__).resolve().parents[1]
    helper = root / "scripts/lib/temp-authority.sh"
    consumers = (
        root / "skills/creative/p5js/scripts/render.sh",
        root / "optional-skills/productivity/here-now/scripts/drive.sh",
    )
    expected_source = 'HERMES_AGENT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"'
    for consumer in consumers:
        source = consumer.read_text(encoding="utf-8")
        assert expected_source in source
        resolved_root = consumer.parent.parents[3]
        resolved_helper = resolved_root / "scripts/lib/temp-authority.sh"
        assert resolved_helper == helper
        assert resolved_helper.read_bytes() == helper.read_bytes()


def test_workflow_runner_authorities_are_parsed_ordered_and_forbidden_root_safe() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow_paths = (
        root / ".github/workflows/deploy-site.yml",
        root / ".github/workflows/docker.yml",
        root / ".github/workflows/supply-chain-audit.yml",
    )
    writer_blocks: list[str] = []
    for workflow_path in workflow_paths:
        document = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        assert isinstance(document, dict)
        jobs = document.get("jobs")
        assert isinstance(jobs, dict) and jobs
        for job in jobs.values():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps", []):
                if not isinstance(step, dict):
                    continue
                block = step.get("run")
                if (
                    isinstance(block, str)
                    and 'case "${RUNNER_TEMP:?}"' in block
                    and 'test ! -e "$HERMES_HOME"' in block
                ):
                    writer_blocks.append(block)

    assert len(writer_blocks) == 5
    forbidden = Path("/tmp") / "workflow-authority-must-not-exist"
    assert not forbidden.exists()
    for block in writer_blocks:
        absolute = block.index('case "${RUNNER_TEMP:?}"')
        system_root = block.index('case "$RUNNER_TEMP/"', absolute)
        owned = block.index('test -d "$RUNNER_TEMP"', system_root)
        home = block.index('export HERMES_HOME=', owned)
        exclusive = block.index('test ! -e "$HERMES_HOME"', home)
        source = block.index('. scripts/lib/temp-authority.sh', exclusive)
        admission = block.index('hermes_temp_authority_init', source)
        first_write = min(
            position for position in (
                block.find('hermes_temp_dir ', admission),
                block.find('install -d -m 700 "$HERMES_TEMP_ROOT', admission),
                block.find('mkdir -m 700 "$HERMES_TEMP_ROOT', admission),
                block.find('printf \'%s\\n\'', admission),
            ) if position >= 0
        )
        assert absolute < system_root < owned < home < exclusive < source < admission < first_write

        validation_only = block[absolute:home]
        result = subprocess.run(
            ["bash", "-c", validation_only],
            env={"RUNNER_TEMP": str(forbidden), "PATH": "/usr/bin:/bin"},
            check=False,
        )
        assert result.returncode == 125
        assert not forbidden.exists()
