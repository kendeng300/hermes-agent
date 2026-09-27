"""Exercise the real shell wrapper's environment boundary without nested pytest."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX shell wrapper")
@pytest.mark.parametrize("configured", [True, False], ids=["temps-set", "temps-unset"])
def test_shell_wrapper_preserves_temp_paths_and_strips_credentials(tmp_path, configured):
    repo = tmp_path / "fixture repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    source = Path(__file__).resolve().parents[1] / "scripts" / "run_tests.sh"
    wrapper = scripts / "run_tests.sh"
    shutil.copyfile(source, wrapper)

    # The wrapper only checks activate's presence before selecting this Python.
    # Use the running interpreter; do not create/install a virtual environment.
    venv_bin = repo / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "activate").write_text("", encoding="utf-8")
    (venv_bin / "python").symlink_to(sys.executable)
    runner = scripts / "run_tests_parallel.py"
    runner.write_text(
        textwrap.dedent("""\
            import json
            import os
            import sys

            # Report only selected inputs. No tempfile calls: the red baseline
            # must not create artifacts in a system temporary directory.
            print(json.dumps({
                "temps": {key: os.environ.get(key) for key in ("TMPDIR", "TEMP", "TMP")},
                "credential_present": "OPENAI_API_KEY" in os.environ,
                "argv": sys.argv[1:],
                "cwd": os.getcwd(),
                "runner": os.path.abspath(__file__),
                "python": sys.executable,
            }))
            """),
        encoding="utf-8",
    )

    home = tmp_path / "private home"
    home.mkdir(mode=0o700)
    env = {
        "PATH": os.environ["PATH"],
        "HOME": str(home),
        "OPENAI_API_KEY": "synthetic-wrapper-test-secret",
    }
    expected_temps = dict.fromkeys(("TMPDIR", "TEMP", "TMP"))
    if configured:
        for key in expected_temps:
            directory = tmp_path / f"{key.lower()} with spaces"
            directory.mkdir(mode=0o700)
            expected_temps[key] = str(directory)
            env[key] = str(directory)

    args = ["tests/example case.py", "-q", "--", "--tb=short"]
    result = subprocess.run(
        ["bash", str(wrapper), *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout.splitlines()[-1])
    assert report["temps"] == expected_temps
    assert report["credential_present"] is False
    assert report["argv"] == args
    assert Path(report["cwd"]) == repo
    assert Path(report["runner"]) == runner
    assert Path(report["python"]).resolve() == Path(sys.executable).resolve()
