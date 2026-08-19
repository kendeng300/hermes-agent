from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TRANSACTION_HOOKS = {
    "pre-commit": "scripts/transaction_hooks/test034-pre-commit.sh",
    "pre-push": "scripts/transaction_hooks/test034-pre-push.sh",
}


def _git(repo: Path, *args: str, check: bool = True, env=None):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=check,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )


def _environment(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "private-home"
    hermes_home = home / "profile"
    temp = tmp_path / "private-tmp"
    for directory in (home, hermes_home, temp):
        directory.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": os.defpath,
        "HOME": str(home),
        "HERMES_HOME": str(hermes_home),
        "TMPDIR": str(temp),
        "TZ": "UTC",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "HERMES_TEST034_MANIFEST_SHA256": "b" * 64,
        "HERMES_TEST034_RUN_NONCE": "hermes_hook_test_0123456789abcdef",
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "candidate"
    remote = tmp_path / "remote.git"
    hooks = tmp_path / "deployed-hooks"
    repo.mkdir()
    remote.mkdir()
    hooks.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Hermes Hook Test")
    (repo / "agent.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "--", "agent.txt")
    _git(repo, "commit", "-q", "-m", "base")
    _git(remote, "init", "-q", "--bare")
    _git(repo, "remote", "add", "myfork", str(remote))
    for deployed_name, source_name in TRANSACTION_HOOKS.items():
        target = hooks / deployed_name
        shutil.copy2(REPOSITORY_ROOT / source_name, target)
        target.chmod(0o500)
    return repo, remote, hooks


def test_deployed_real_hooks_bind_commit_and_push_without_candidate_state(
    tmp_path: Path,
):
    repo, remote, hooks = _fixture(tmp_path)
    env = _environment(tmp_path)
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "push", "myfork", f"{base}:refs/heads/candidate")
    (repo / "agent.txt").write_text("candidate\n", encoding="utf-8")
    _git(repo, "add", "--", "agent.txt")

    committed = _git(
        repo,
        "-c",
        f"core.hooksPath={hooks}",
        "commit",
        "-m",
        "candidate",
        env=env,
    )
    candidate = _git(repo, "rev-parse", "HEAD").stdout.strip()
    pushed = _git(
        repo,
        "-c",
        f"core.hooksPath={hooks}",
        "push",
        "myfork",
        f"{candidate}:refs/heads/candidate",
        env=env,
    )

    assert "pre-commit integrity verified" in committed.stdout + committed.stderr
    assert pushed.returncode == 0
    assert _git(remote, "rev-parse", "refs/heads/candidate").stdout.strip() == candidate
    assert _git(repo, "status", "--porcelain=v1").stdout == ""
    assert not list(repo.glob(".last-*"))
    assert not list(repo.rglob("*hook*.log"))


def test_deployed_pre_push_rejects_non_fast_forward_and_missing_coordinator(
    tmp_path: Path,
):
    repo, remote, hooks = _fixture(tmp_path)
    env = _environment(tmp_path)
    base = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "push", "myfork", f"{base}:refs/heads/candidate")
    (repo / "agent.txt").write_text("first\n", encoding="utf-8")
    _git(repo, "add", "--", "agent.txt")
    _git(repo, "commit", "-q", "-m", "first")
    first = _git(repo, "rev-parse", "HEAD").stdout.strip()
    _git(repo, "push", "myfork", f"{first}:refs/heads/candidate")
    _git(repo, "checkout", "-q", "-b", "rewrite", base)
    (repo / "agent.txt").write_text("rewrite\n", encoding="utf-8")
    _git(repo, "add", "--", "agent.txt")
    _git(repo, "commit", "-q", "-m", "rewrite")
    rewrite = _git(repo, "rev-parse", "HEAD").stdout.strip()

    rejected = _git(
        repo,
        "-c",
        f"core.hooksPath={hooks}",
        "push",
        "--" + "force",
        "myfork",
        f"{rewrite}:refs/heads/candidate",
        check=False,
        env=env,
    )
    assert rejected.returncode != 0
    assert "not a fast-forward" in rejected.stderr
    assert _git(remote, "rev-parse", "refs/heads/candidate").stdout.strip() == first

    missing = env.copy()
    missing.pop("HERMES_TEST034_RUN_NONCE")
    (repo / "agent.txt").write_text("second\n", encoding="utf-8")
    _git(repo, "add", "--", "agent.txt")
    failed_commit = _git(
        repo,
        "-c",
        f"core.hooksPath={hooks}",
        "commit",
        "-m",
        "must fail",
        check=False,
        env=missing,
    )
    assert failed_commit.returncode != 0
    assert "missing or invalid sealed run nonce" in failed_commit.stderr


def test_candidate_hook_sources_are_relocatable_and_have_no_bypass_rails():
    forbidden = (
        "/home/linux/" + ".hermes",
        "~/" + ".hermes",
        "MECHANICAL" + "_MODE",
        "BACKUP" + "_MODE",
        "no" + "-verify",
        "requests" + ".post",
        "httpx" + ".",
        "slack" + "_sev1_webhook",
        ".last-pre" + "-commit-run",
        "tests/" + "test_data",
    )
    for relative_path in TRANSACTION_HOOKS.values():
        hook = REPOSITORY_ROOT / relative_path
        assert hook.stat().st_mode & 0o100
        source = hook.read_text(encoding="utf-8")
        assert not any(marker in source for marker in forbidden)
    assert not (REPOSITORY_ROOT / "pre-commit-gate.sh").exists()
    assert not (REPOSITORY_ROOT / "pre-push-gate.sh").exists()
