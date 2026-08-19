"""Deploy-shaped contracts for test-wrapper temporary authority bootstrap."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from hermes_temp import resolve_temp_authority


NONCE = "1" * 32


def _wrapper_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = Path(__file__).resolve().parents[2]
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    wrapper = scripts / "run_tests.sh"
    shutil.copyfile(source / "scripts" / "run_tests.sh", wrapper)
    shutil.copyfile(source / "hermes_temp.py", repo / "hermes_temp.py")
    shutil.copyfile(source / "hermes_constants.py", repo / "hermes_constants.py")
    wrapper.chmod(0o755)

    marker = tmp_path / "runner-environment.json"
    (scripts / "run_tests_parallel.py").write_text(
        "import json, os\n"
        f"marker = {str(marker)!r}\n"
        "keys = ('HERMES_HOME', 'HERMES_TEMP_ROOT', "
        "'HERMES_TEMP_ROOT_IDENTITY', 'HERMES_TEMP_SCOPE', "
        "'HERMES_TEMP_RUN_NONCE', 'HERMES_TEMP_AUTHORITY_VERSION', "
        "'TMPDIR', 'TEMP', 'TMP', 'HERMES_TEST_ACTIVE', "
        "'HERMES_OFFLINE', 'OFFLINE', 'NO_NETWORK')\n"
        "open(marker, 'w', encoding='utf-8').write("
        "json.dumps({key: os.environ.get(key) for key in keys}, sort_keys=True))\n",
        encoding="utf-8",
    )
    venv_bin = repo / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text("# fixture\n", encoding="utf-8")
    # Use the reviewed test interpreter while retaining a deploy-shaped
    # wrapper probe. A symlink placed under this synthetic ``venv`` would
    # lose its original pyvenv.cfg and could silently drop pytest.
    _python = shlex.quote(sys.executable)
    (venv_bin / "python").write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"-c\" ] && [ \"$2\" = \"import pytest\" ]; then exit 0; fi\n"
        f"exec {_python} \"$@\"\n",
        encoding="utf-8",
    )
    (venv_bin / "python").chmod(0o755)
    return repo, wrapper, marker


def test_wrapper_bootstraps_complete_private_authority(tmp_path: Path) -> None:
    repo, wrapper, marker = _wrapper_fixture(tmp_path)
    home = tmp_path / "home"
    state = tmp_path / "state"
    home.mkdir(mode=0o700)
    state.mkdir(mode=0o700)

    completed = subprocess.run(
        ["bash", str(wrapper)],
        cwd=repo,
        env={
            "HOME": str(home),
            "PATH": os.environ["PATH"],
            "XDG_STATE_HOME": str(state),
        },
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    values = json.loads(marker.read_text(encoding="utf-8"))
    root = Path(values["HERMES_TEMP_ROOT"])
    assert root == Path(values["HERMES_HOME"]) / "tmp"
    assert root.is_relative_to(state)
    assert {values[key] for key in ("TMPDIR", "TEMP", "TMP")} == {str(root)}
    assert values["HERMES_TEMP_ROOT_IDENTITY"].startswith("v1:")
    assert values["HERMES_TEMP_SCOPE"] == "test"
    assert len(values["HERMES_TEMP_RUN_NONCE"]) == 32
    assert values["HERMES_TEMP_AUTHORITY_VERSION"] == "1"
    assert {
        values[key]
        for key in ("HERMES_TEST_ACTIVE", "HERMES_OFFLINE", "OFFLINE", "NO_NETWORK")
    } == {"1"}


def test_wrapper_rejects_partial_inherited_authority(tmp_path: Path) -> None:
    repo, wrapper, marker = _wrapper_fixture(tmp_path)
    home = tmp_path / "bound-home"
    root = home / "tmp"
    root.mkdir(parents=True, mode=0o700)
    home.chmod(0o700)
    root.chmod(0o700)

    completed = subprocess.run(
        ["bash", str(wrapper)],
        cwd=repo,
        env={
            "HOME": str(tmp_path / "home"),
            "PATH": os.environ["PATH"],
            "HERMES_HOME": str(home),
            "HERMES_TEMP_ROOT": str(root),
            "HERMES_TEMP_SCOPE": "test",
            "HERMES_TEMP_RUN_NONCE": NONCE,
        },
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode != 0
    assert "could not establish the Hermes test temporary authority" in completed.stderr
    assert not marker.exists()


def _direct_pytest_fixture(tmp_path: Path) -> tuple[Path, Path]:
    source = Path(__file__).resolve().parents[2]
    repo = tmp_path / "direct-repo"
    tests = repo / "tests"
    tests.mkdir(parents=True)
    shutil.copyfile(source / "tests" / "conftest.py", tests / "conftest.py")
    shutil.copyfile(source / "hermes_temp.py", repo / "hermes_temp.py")
    shutil.copyfile(source / "hermes_constants.py", repo / "hermes_constants.py")
    (tests / "test_probe.py").write_text("def test_probe(): assert True\n", encoding="utf-8")
    home = tmp_path / "direct-home"
    home.mkdir(mode=0o700)
    home.chmod(0o700)
    return repo, home


def _run_direct_pytest(
    repo: Path, home: Path, basetemp: Path | None
) -> subprocess.CompletedProcess[str]:
    authority = resolve_temp_authority(
        scope="test",
        run_nonce=NONCE,
        env={"HERMES_HOME": str(home)},
    )
    try:
        env = {
            "HOME": str(repo.parent),
            "PATH": os.environ["PATH"],
            "PYTHONDONTWRITEBYTECODE": "1",
            "HERMES_TEST_ACTIVE": "1",
            "HERMES_OFFLINE": "1",
            "OFFLINE": "1",
            "NO_NETWORK": "1",
            **authority.child_environment(),
        }
        argv = [sys.executable, "-m", "pytest", "tests/test_probe.py", "-q"]
        if basetemp is not None:
            argv.append(f"--basetemp={basetemp}")
        return subprocess.run(
            argv,
            cwd=repo,
            env=env,
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    finally:
        authority.close()


def test_direct_pytest_requires_precreated_authority_basetemp(tmp_path: Path) -> None:
    repo, home = _direct_pytest_fixture(tmp_path)

    missing = _run_direct_pytest(repo, home, None)
    foreign = tmp_path / "foreign-basetemp"
    foreign.mkdir(mode=0o700)
    foreign.chmod(0o700)
    outside = _run_direct_pytest(repo, home, foreign)

    assert missing.returncode != 0
    assert "requires an explicit authority-contained --basetemp" in missing.stderr
    assert outside.returncode != 0
    assert "outside the private temporary authority" in outside.stderr


def test_direct_pytest_accepts_precreated_authority_basetemp(tmp_path: Path) -> None:
    repo, home = _direct_pytest_fixture(tmp_path)
    root = home / "tmp"
    basetemp = root / "direct-pytest"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    basetemp.mkdir(mode=0o700)
    basetemp.chmod(0o700)

    completed = _run_direct_pytest(repo, home, basetemp)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "1 passed" in completed.stdout


def test_direct_pytest_rejects_missing_or_wrong_offline_contract(tmp_path: Path) -> None:
    repo, home = _direct_pytest_fixture(tmp_path)
    root = home / "tmp"
    root.mkdir(mode=0o700)
    root.chmod(0o700)

    authority = resolve_temp_authority(
        scope="test",
        run_nonce=NONCE,
        env={"HERMES_HOME": str(home)},
    )
    try:
        base_env = {
            "HOME": str(repo.parent),
            "PATH": os.environ["PATH"],
            "PYTHONDONTWRITEBYTECODE": "1",
            **authority.child_environment(),
        }
        required = {
            "HERMES_TEST_ACTIVE": "1",
            "HERMES_OFFLINE": "1",
            "OFFLINE": "1",
            "NO_NETWORK": "1",
        }
        malformed_contracts = []
        for name in required:
            missing = dict(required)
            missing.pop(name)
            malformed_contracts.append(missing)
            wrong = dict(required)
            wrong[name] = "0"
            malformed_contracts.append(wrong)
        for index, malformed in enumerate(malformed_contracts):
            basetemp = root / f"offline-contract-{index}"
            basetemp.mkdir(mode=0o700)
            basetemp.chmod(0o700)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_probe.py",
                    "-q",
                    f"--basetemp={basetemp}",
                ],
                cwd=repo,
                env={**base_env, **malformed},
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
            assert completed.returncode != 0
            assert "exact pre-collection offline test contract" in completed.stderr
    finally:
        authority.close()
