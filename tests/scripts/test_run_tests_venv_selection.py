"""Behavioral contracts for the canonical test-wrapper interpreter probe."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


def _write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def test_wrapper_skips_first_venv_when_pytest_is_unavailable(tmp_path: Path) -> None:
    """A stale `.venv` must not mask a healthy repository `venv`."""
    source_root = Path(__file__).resolve().parents[2]
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    wrapper = scripts / "run_tests.sh"
    shutil.copyfile(source_root / "scripts" / "run_tests.sh", wrapper)
    wrapper.chmod(0o755)

    # The wrapper only needs this path to exist; the selected fake interpreter
    # records that it was invoked instead of executing the parallel runner.
    (scripts / "run_tests_parallel.py").write_text("# fixture\n", encoding="utf-8")
    for name in (".venv", "venv"):
        (repo / name / "bin").mkdir(parents=True)
        (repo / name / "bin" / "activate").write_text("# fixture\n", encoding="utf-8")

    _write_executable(
        repo / ".venv" / "bin" / "python",
        "#!/bin/sh\n"
        "if [ \"$1\" = \"-c\" ]; then exit 1; fi\n"
        "exit 99\n",
    )
    marker = tmp_path / "selected-python.txt"
    healthy = repo / "venv" / "bin" / "python"
    _write_executable(
        healthy,
        "#!/bin/sh\n"
        "if [ \"$1\" = \"-c\" ]; then\n"
        "  case \"$2\" in\n"
        f"    *os.execve*) printf '%s\\n' \"$0\" > {str(marker)!r} ;;\n"
        "  esac\n"
        "  exit 0\n"
        "fi\n"
        f"printf '%s\\n' \"$0\" > {str(marker)!r}\n"
        "exit 0\n",
    )

    test_home = tmp_path / "home"
    test_home.mkdir()
    completed = subprocess.run(
        ["bash", str(wrapper)],
        cwd=repo,
        env={"HOME": str(test_home), "PATH": os.environ["PATH"]},
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "skipping unusable test virtualenv" in completed.stderr
    assert marker.read_text(encoding="utf-8").strip() == str(healthy)
