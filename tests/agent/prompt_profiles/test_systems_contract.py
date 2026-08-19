from __future__ import annotations

from pathlib import Path
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


_TEST034_HERMES_CANDIDATE_PATHS = frozenset({
    ".github/pr-screenshots/39327/providers-collapsed.png",
    ".github/pr-screenshots/39327/providers-expanded.png",
    ".github/pr-screenshots/39327/tools-collapsed.png",
    ".github/pr-screenshots/39327/tools-expanded.png",
    ".github/workflows/deploy-site.yml",
    ".github/workflows/docker.yml",
    ".github/workflows/supply-chain-audit.yml",
    "MANIFEST.in",
    "acp_adapter/edit_approval.py",
    "agent/coding_context.py",
    "agent/conversation_compression.py",
    "agent/copilot_acp_client.py",
    "agent/learn_prompt.py",
    "agent/prompt_profiles/assets/o200k_base.tiktoken",
    "agent/prompt_profiles/renderer.py",
    "agent/prompt_profiles/tokenizer.py",
    "agent/secret_sources/bitwarden.py",
    "agent/verification_evidence.py",
    "agent/verification_stop.py",
    "cli.py",
    "gateway/platforms/qqbot/adapter.py",
    "gateway/platforms/signal.py",
    "gateway/platforms/weixin.py",
    "gateway/run.py",
    "gateway/slash_commands.py",
    "hermes_cli/cli_commands_mixin.py",
    "hermes_cli/gateway.py",
    "hermes_cli/journey.py",
    "hermes_cli/main.py",
    "hermes_cli/managed_uv.py",
    "hermes_cli/plugins_cmd.py",
    "hermes_cli/profile_distribution.py",
    "hermes_cli/profiles.py",
    "hermes_cli/tools_config.py",
    "hermes_cli/voice.py",
    "hermes_cli/web_server.py",
    "hermes_constants.py",
    "hermes_temp.py",
    "optional-skills/creative/pixel-art/scripts/pixel_art_video.py",
    "optional-skills/finance/excel-author/scripts/recalc.py",
    "optional-skills/productivity/here-now/scripts/drive.sh",
    "plugins/disk-cleanup/README.md",
    "plugins/disk-cleanup/__init__.py",
    "plugins/disk-cleanup/disk_cleanup.py",
    "plugins/memory/openviking/__init__.py",
    "plugins/platforms/discord/adapter.py",
    "plugins/platforms/line/adapter.py",
    "plugins/platforms/simplex/adapter.py",
    "plugins/platforms/slack/adapter.py",
    "plugins/teams_pipeline/meetings.py",
    "plugins/teams_pipeline/pipeline.py",
    "plugins/teams_pipeline/store.py",
    "pyproject.toml",
    "run_agent.py",
    "scripts/benchmark_browser_eval.py",
    "scripts/dev-sandbox.sh",
    "scripts/install.sh",
    "scripts/install_psutil_android.py",
    "scripts/lib/node-bootstrap.sh",
    "scripts/lib/temp-authority.sh",
    "scripts/run_tests.sh",
    "scripts/run_tests_parallel.py",
    "scripts/tool_search_livetest.py",
    "scripts/transaction_hooks/test034-pre-commit.sh",
    "scripts/transaction_hooks/test034-pre-push.sh",
    "setup-hermes.sh",
    "setup.py",
    "skills/creative/p5js/scripts/render.sh",
    "skills/productivity/powerpoint/scripts/office/pack.py",
    "tests/agent/prompt_profiles/fixtures.py",
    "tests/agent/prompt_profiles/test_loop2_remediation.py",
    "tests/agent/prompt_profiles/test_systems_contract.py",
    "tests/agent/test_coding_context.py",
    "tests/agent/test_verification_evidence.py",
    "tests/agent/test_verification_stop.py",
    "tests/conftest.py",
    "tests/gateway/test_model_command_async_offload.py",
    "tests/gateway/test_model_command_custom_providers.py",
    "tests/gateway/test_model_command_expensive_confirm.py",
    "tests/gateway/test_model_picker_persist.py",
    "tests/gateway/test_prompt_profile_switch_after_compression.py",
    "tests/gateway/test_send_voice_reply_notify.py",
    "tests/gateway/test_session_env.py",
    "tests/gateway/test_slack.py",
    "tests/plugins/test_disk_cleanup_plugin.py",
    "tests/scripts/test_candidate_hooks.py",
    "tests/scripts/test_run_tests_venv_selection.py",
    "tests/scripts/test_temp_authority_wrapper.py",
    "tests/stress/test_benchmarks.py",
    "tests/test_bitwarden_secrets.py",
    "tests/test_hermes_temp_authority.py",
    "tests/test_packaging_metadata.py",
    "tests/test_run_tests_parallel.py",
    "tests/test_temp_authority_h1_migrations.py",
    "tests/test_temp_authority_h2_migrations.py",
    "tests/tools/test_base_environment.py",
    "tests/tools/test_browser_orphan_reaper.py",
    "tests/tools/test_init_session_cwd_respect.py",
    "tests/tools/test_local_tempdir.py",
    "tests/tools/test_tool_result_storage.py",
    "tools/approval.py",
    "tools/browser_tool.py",
    "tools/code_execution_tool.py",
    "tools/computer_use/cua_backend.py",
    "tools/credential_files.py",
    "tools/environments/base.py",
    "tools/environments/daytona.py",
    "tools/environments/docker.py",
    "tools/environments/file_sync.py",
    "tools/environments/local.py",
    "tools/environments/managed_modal.py",
    "tools/environments/modal.py",
    "tools/environments/singularity.py",
    "tools/environments/ssh.py",
    "tools/image_source.py",
    "tools/lazy_deps.py",
    "tools/process_registry.py",
    "tools/tirith_security.py",
    "tools/tool_result_storage.py",
    "tools/transcription_tools.py",
    "tools/tts_tool.py",
    "tools/voice_mode.py",
    "trajectory_compressor.py",
    "tui_gateway/server.py",
    "uv.lock",
})
_TEST034_HERMES_EXECUTABLE_PATHS = frozenset({
    "optional-skills/productivity/here-now/scripts/drive.sh",
    "plugins/disk-cleanup/disk_cleanup.py",
    "scripts/dev-sandbox.sh",
    "scripts/install.sh",
    "scripts/install_psutil_android.py",
    "scripts/run_tests.sh",
    "scripts/run_tests_parallel.py",
    "scripts/transaction_hooks/test034-pre-commit.sh",
    "scripts/transaction_hooks/test034-pre-push.sh",
    "setup-hermes.sh",
    "skills/creative/p5js/scripts/render.sh",
})


def _test034_expected_modes() -> dict[str, str]:
    return {
        path: "100755" if path in _TEST034_HERMES_EXECUTABLE_PATHS else "100644"
        for path in _TEST034_HERMES_CANDIDATE_PATHS
    }


def _blob_oid(payload: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(payload)}\0".encode("ascii") + payload
    ).hexdigest()


def _entry(path: str, payload: bytes, *, mode: str = "100644") -> dict:
    return {
        "path": path,
        "mode": mode,
        "blob_oid": _blob_oid(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "dependency": None,
    }


def _dependency(path: str, label: str) -> dict:
    return {
        "path": path,
        "mode": "160000",
        "blob_oid": None,
        "sha256": None,
        "dependency": label,
    }


def _tree_digest(entries: list[dict]) -> str:
    payload = json.dumps(
        sorted(entries, key=lambda item: item["path"]),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _repository(label: str, entries: list[dict]) -> dict:
    project = "hermes-agent" if label == "hermes-agent" else "marketwatch"
    remote = "myfork" if label == "hermes-agent" else "origin"
    return {
        "canonical_url": f"https://github.com/kendeng300/{project}.git",
        "push_remote": remote,
        "branch": f"ci/test-034-{label}",
        "base_branch": "main",
        "base_ref_commit": "1" * 40,
        "base_commit": "1" * 40,
        "frozen_git_tree": "2" * 40,
        "tree_digest": _tree_digest(entries),
        "entries": entries,
        "merge_authority": {
            "version": 1,
            "mode": "github-branch-protection-strict-v1",
            "base_branch": "main",
            "required_checks": [{
                "context": "TEST-034 / mechanical",
                "app_id": 1,
                "app_slug": "test034-ci",
            }],
        },
    }


def _candidate_manifest(
    core_path: Path,
    config_candidate_root: Path,
    hermes_candidate_root: Path,
) -> dict:
    repository_root = Path(__file__).resolve().parents[3]
    hermes_entries = []
    for path in sorted(_TEST034_HERMES_CANDIDATE_PATHS):
        payload = (repository_root / path).read_bytes()
        destination = hermes_candidate_root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        mode = _test034_expected_modes()[path]
        destination.chmod(0o755 if mode == "100755" else 0o644)
        hermes_entries.append(_entry(path, payload, mode=mode))

    core_bytes = core_path.read_bytes()
    config_candidate_root.mkdir(parents=True, exist_ok=True)
    (config_candidate_root / "SOUL.md").write_bytes(core_bytes)
    content_payload = b'{"ticket":"TEST-034"}\n'
    content_path = "data/TEST-034-cross-layer-literal-manifest.json"
    config_entries = [
        _entry(content_path, content_payload),
        _entry("SOUL.md", core_bytes),
        _dependency("scripts", "scripts"),
        _dependency("hermes-agent", "hermes-agent"),
    ]
    scripts_entries = [
        _entry(
            "monitoring/ci_process_mechanical.py",
            b"# exact scripts candidate is validated by the mechanical loader\n",
        ),
    ]
    return {
        "version": 2,
        "ticket": "TEST-034",
        "run_nonce": "test034_candidate_policy_0123456789abcdef",
        "issued_at": "2026-08-17T00:00:00+00:00",
        "expires_at": "2026-08-17T01:00:00+00:00",
        "content_manifest": {
            "path": content_path,
            "sha256": hashlib.sha256(content_payload).hexdigest(),
        },
        "repositories": {
            "scripts": _repository("scripts", scripts_entries),
            "config": _repository("config", config_entries),
            "hermes-agent": _repository("hermes-agent", hermes_entries),
        },
    }


def _assert_test034_candidate_custody(manifest: dict) -> None:
    assert set(manifest["repositories"]) == {"config", "scripts", "hermes-agent"}
    config_entries = manifest["repositories"]["config"]["entries"]
    dependencies = {
        entry["dependency"]: entry["path"]
        for entry in config_entries
        if entry["dependency"] is not None
    }
    assert dependencies == {"scripts": "scripts", "hermes-agent": "hermes-agent"}
    repository = manifest["repositories"]["hermes-agent"]
    assert repository["canonical_url"] == "https://github.com/kendeng300/hermes-agent.git"
    paths = [entry["path"] for entry in repository["entries"]]
    assert len(paths) == len(set(paths))
    assert len(paths) == 125
    assert set(paths) == _TEST034_HERMES_CANDIDATE_PATHS
    repository_root = Path(__file__).resolve().parents[3]
    expected_modes = _test034_expected_modes()
    for entry in repository["entries"]:
        path = entry["path"]
        source = repository_root / path
        assert source.is_file()
        assert not source.is_symlink()
        assert entry["mode"] == expected_modes[path]
        assert entry["dependency"] is None
        payload = source.read_bytes()
        assert entry["blob_oid"] == _blob_oid(payload)
        assert entry["sha256"] == hashlib.sha256(payload).hexdigest()


def _write_manifest(path: Path, manifest: dict) -> str:
    path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_test034_candidate_custody_matches_renderer_and_current_tree() -> None:
    from agent.prompt_profiles.renderer import (
        _TEST034_HERMES_CANDIDATE_COUNT,
        _TEST034_HERMES_CANDIDATE_MODES,
    )

    repository_root = Path(__file__).resolve().parents[3]
    expected_modes = _test034_expected_modes()
    assert _TEST034_HERMES_CANDIDATE_COUNT == 125
    assert len(_TEST034_HERMES_CANDIDATE_PATHS) == 125
    assert dict(_TEST034_HERMES_CANDIDATE_MODES) == expected_modes
    for path in sorted(_TEST034_HERMES_CANDIDATE_PATHS):
        source = repository_root / path
        assert source.is_file(), path
        assert not source.is_symlink(), path
        payload = source.read_bytes()
        assert len(hashlib.sha256(payload).hexdigest()) == 64
        assert len(_blob_oid(payload)) == 40


def test_candidate_policy_approval_binds_exact_root_bytes_and_required_paths(
    tmp_path, monkeypatch,
) -> None:
    from agent.prompt_profiles import PromptProfileError
    from agent.prompt_profiles.renderer import verify_candidate_policy_approval
    from tests.agent.prompt_profiles.fixtures import install_approved_test_core

    _core, core_path = install_approved_test_core(tmp_path, monkeypatch)
    config_candidate_root = tmp_path / "config-candidate"
    hermes_candidate_root = tmp_path / "hermes-candidate"
    manifest = _candidate_manifest(
        core_path, config_candidate_root, hermes_candidate_root,
    )
    _assert_test034_candidate_custody(manifest)
    manifest_path = tmp_path / "candidate.json"
    digest = _write_manifest(manifest_path, manifest)

    approval = verify_candidate_policy_approval(
        manifest_path,
        manifest_sha256=digest,
        config_candidate_root=config_candidate_root,
        hermes_candidate_root=hermes_candidate_root,
    )
    assert approval["ticket"] == "TEST-034"
    assert approval["req_count"] == len(set(
        __import__("agent.prompt_profiles.renderer", fromlist=["_REQ_RE"])
        ._REQ_RE.findall(_core)
    ))
    assert approval["manifest_sha256"] == digest
    assert set(approval["hermes_candidate_sha256"]) == _TEST034_HERMES_CANDIDATE_PATHS
    hermes_entries = {
        entry["path"]: entry
        for entry in manifest["repositories"]["hermes-agent"]["entries"]
    }
    assert hermes_entries["plugins/platforms/slack/adapter.py"]["mode"] == "100644"
    assert hermes_entries["tests/gateway/test_slack.py"]["mode"] == "100644"
    assert hermes_entries["pyproject.toml"]["mode"] == "100644"
    assert hermes_entries["uv.lock"]["mode"] == "100644"
    assert hermes_entries["agent/prompt_profiles/tokenizer.py"]["mode"] == "100644"
    assert hermes_entries["agent/prompt_profiles/assets/o200k_base.tiktoken"]["mode"] == "100644"

    soul = next(
        entry for entry in manifest["repositories"]["config"]["entries"]
        if entry["path"] == "SOUL.md"
    )
    soul["sha256"] = "0" * 64
    tampered_digest = _write_manifest(manifest_path, manifest)
    with pytest.raises(PromptProfileError, match="CANDIDATE_POLICY_DIGEST_MISMATCH"):
        verify_candidate_policy_approval(
            manifest_path,
            manifest_sha256=tampered_digest,
            config_candidate_root=config_candidate_root,
            hermes_candidate_root=hermes_candidate_root,
        )


def test_test034_candidate_custody_rejects_each_missing_path(tmp_path, monkeypatch) -> None:
    from agent.prompt_profiles import PromptProfileError
    from agent.prompt_profiles.renderer import verify_candidate_policy_approval
    from tests.agent.prompt_profiles.fixtures import install_approved_test_core

    _core, core_path = install_approved_test_core(tmp_path, monkeypatch)
    config_candidate_root = tmp_path / "config-candidate"
    hermes_candidate_root = tmp_path / "hermes-candidate"
    manifest = _candidate_manifest(
        core_path, config_candidate_root, hermes_candidate_root,
    )
    manifest_path = tmp_path / "candidate.json"
    for missing in sorted(_TEST034_HERMES_CANDIDATE_PATHS):
        mutated = json.loads(json.dumps(manifest))
        mutated["repositories"]["hermes-agent"]["entries"] = [
            entry
            for entry in mutated["repositories"]["hermes-agent"]["entries"]
            if entry["path"] != missing
        ]
        digest = _write_manifest(manifest_path, mutated)
        with pytest.raises(PromptProfileError, match="CANDIDATE_POLICY_PATH_SET_MISMATCH"):
            verify_candidate_policy_approval(
                manifest_path,
                manifest_sha256=digest,
                config_candidate_root=config_candidate_root,
                hermes_candidate_root=hermes_candidate_root,
            )


def test_test034_candidate_custody_rejects_blob_or_candidate_byte_tamper(
    tmp_path, monkeypatch,
) -> None:
    from agent.prompt_profiles import PromptProfileError
    from agent.prompt_profiles.renderer import verify_candidate_policy_approval
    from tests.agent.prompt_profiles.fixtures import install_approved_test_core

    _core, core_path = install_approved_test_core(tmp_path, monkeypatch)
    config_candidate_root = tmp_path / "config-candidate"
    hermes_candidate_root = tmp_path / "hermes-candidate"
    manifest = _candidate_manifest(
        core_path, config_candidate_root, hermes_candidate_root,
    )
    manifest_path = tmp_path / "candidate.json"

    manifest["repositories"]["hermes-agent"]["entries"][0]["blob_oid"] = "0" * 40
    digest = _write_manifest(manifest_path, manifest)
    with pytest.raises(PromptProfileError, match="CANDIDATE_POLICY_BLOB_MISMATCH"):
        verify_candidate_policy_approval(
            manifest_path,
            manifest_sha256=digest,
            config_candidate_root=config_candidate_root,
            hermes_candidate_root=hermes_candidate_root,
        )

    manifest = _candidate_manifest(
        core_path, config_candidate_root, hermes_candidate_root,
    )
    victim = (
        hermes_candidate_root
        / manifest["repositories"]["hermes-agent"]["entries"][0]["path"]
    )
    victim.write_bytes(victim.read_bytes() + b"\n# tampered\n")
    digest = _write_manifest(manifest_path, manifest)
    with pytest.raises(PromptProfileError, match="CANDIDATE_POLICY_DIGEST_MISMATCH"):
        verify_candidate_policy_approval(
            manifest_path,
            manifest_sha256=digest,
            config_candidate_root=config_candidate_root,
            hermes_candidate_root=hermes_candidate_root,
        )


def test_test034_candidate_custody_helper_rejects_each_missing_path(tmp_path) -> None:
    core_path = tmp_path / "SOUL.md"
    core_path.write_text("candidate\n", encoding="utf-8")
    manifest = _candidate_manifest(
        core_path,
        tmp_path / "config-candidate",
        tmp_path / "hermes-candidate",
    )
    for missing in sorted(_TEST034_HERMES_CANDIDATE_PATHS):
        mutated = json.loads(json.dumps(manifest))
        mutated["repositories"]["hermes-agent"]["entries"] = [
            entry
            for entry in mutated["repositories"]["hermes-agent"]["entries"]
            if entry["path"] != missing
        ]
        with pytest.raises(AssertionError):
            _assert_test034_candidate_custody(mutated)


def test_candidate_policy_rejects_materialized_core_or_soul_path_tamper(
    tmp_path, monkeypatch,
) -> None:
    from agent.prompt_profiles import PromptProfileError
    from agent.prompt_profiles.renderer import verify_candidate_policy_approval
    from tests.agent.prompt_profiles.fixtures import install_approved_test_core

    _core, core_path = install_approved_test_core(tmp_path, monkeypatch)
    config_candidate_root = tmp_path / "config-candidate"
    hermes_candidate_root = tmp_path / "hermes-candidate"
    manifest = _candidate_manifest(
        core_path, config_candidate_root, hermes_candidate_root,
    )
    manifest_path = tmp_path / "candidate.json"
    digest = _write_manifest(manifest_path, manifest)

    materialized_core = config_candidate_root / "SOUL.md"
    materialized_core.write_bytes(materialized_core.read_bytes() + b"tampered\n")
    with pytest.raises(PromptProfileError, match="CANDIDATE_POLICY_DIGEST_MISMATCH"):
        verify_candidate_policy_approval(
            manifest_path,
            manifest_sha256=digest,
            config_candidate_root=config_candidate_root,
            hermes_candidate_root=hermes_candidate_root,
        )

    manifest = _candidate_manifest(
        core_path, config_candidate_root, hermes_candidate_root,
    )
    soul = next(
        entry for entry in manifest["repositories"]["config"]["entries"]
        if entry["path"] == "SOUL.md"
    )
    soul["path"] = "policy/SOUL.md"
    digest = _write_manifest(manifest_path, manifest)
    with pytest.raises(PromptProfileError, match="CANDIDATE_POLICY_ENTRY_MISSING"):
        verify_candidate_policy_approval(
            manifest_path,
            manifest_sha256=digest,
            config_candidate_root=config_candidate_root,
            hermes_candidate_root=hermes_candidate_root,
        )


def test_candidate_policy_rejects_noncanonical_v2_repository_topology(
    tmp_path, monkeypatch,
) -> None:
    from agent.prompt_profiles import PromptProfileError
    from agent.prompt_profiles.renderer import verify_candidate_policy_approval
    from tests.agent.prompt_profiles.fixtures import install_approved_test_core

    _core, core_path = install_approved_test_core(tmp_path, monkeypatch)
    config_candidate_root = tmp_path / "config-candidate"
    hermes_candidate_root = tmp_path / "hermes-candidate"
    original = _candidate_manifest(
        core_path, config_candidate_root, hermes_candidate_root,
    )
    manifest_path = tmp_path / "candidate.json"

    mutations = []

    missing_scripts = json.loads(json.dumps(original))
    missing_scripts["repositories"].pop("scripts")
    mutations.append((missing_scripts, "CANDIDATE_POLICY_REPOSITORY_INVALID"))

    unexpected_repository = json.loads(json.dumps(original))
    unexpected_repository["repositories"]["other"] = json.loads(
        json.dumps(unexpected_repository["repositories"]["scripts"])
    )
    mutations.append((unexpected_repository, "CANDIDATE_POLICY_REPOSITORY_INVALID"))

    wrong_scripts_remote = json.loads(json.dumps(original))
    wrong_scripts_remote["repositories"]["scripts"]["canonical_url"] = (
        "https://github.com/example/marketwatch.git"
    )
    mutations.append((wrong_scripts_remote, "CANDIDATE_POLICY_REPOSITORY_INVALID"))

    missing_scripts_gitlink = json.loads(json.dumps(original))
    missing_scripts_gitlink["repositories"]["config"]["entries"] = [
        entry
        for entry in missing_scripts_gitlink["repositories"]["config"]["entries"]
        if entry["dependency"] != "scripts"
    ]
    mutations.append((missing_scripts_gitlink, "CANDIDATE_POLICY_DEPENDENCY_INVALID"))

    wrong_hermes_gitlink = json.loads(json.dumps(original))
    hermes_gitlink = next(
        entry
        for entry in wrong_hermes_gitlink["repositories"]["config"]["entries"]
        if entry["dependency"] == "hermes-agent"
    )
    hermes_gitlink["path"] = "vendor/hermes-agent"
    mutations.append((wrong_hermes_gitlink, "CANDIDATE_POLICY_DEPENDENCY_INVALID"))

    for mutated, expected in mutations:
        digest = _write_manifest(manifest_path, mutated)
        with pytest.raises(PromptProfileError, match=expected):
            verify_candidate_policy_approval(
                manifest_path,
                manifest_sha256=digest,
                config_candidate_root=config_candidate_root,
                hermes_candidate_root=hermes_candidate_root,
            )


def test_frozen_test034_policy_approval_facts_are_exact() -> None:
    from agent.prompt_profiles import renderer

    assert renderer._APPROVED_CANONICAL_CORE_SHA256 == (
        "94075360d64c1bde30039428c3295c8721330043f03edf07bbb2d6cd55bd515e"
    )
    assert renderer._APPROVED_REQ_COUNT == 150
    assert renderer._APPROVED_REQ_MANIFEST_SHA256 == (
        "71c71b61aa36002e0c9d3bbdeff75860f7de275ebe2e075ca506aa2800bc5eaa"
    )


def test_profile_registry_and_effective_windows() -> None:
    from agent.prompt_profiles import get_profile, resolve_effective_window

    openai = get_profile("openai-codex", "gpt-5.6-sol")
    deepseek = get_profile("deepseek", "deepseek-v4-flash")

    assert openai.contract_window == 257_000
    assert deepseek.contract_window == 1_000_000
    assert resolve_effective_window(272_000, openai.contract_window) == 257_000
    assert resolve_effective_window(200_000, openai.contract_window) == 200_000


@pytest.mark.parametrize("runtime_window", [None, 0, -1])
def test_effective_window_rejects_unknown_runtime(runtime_window: int | None) -> None:
    from agent.prompt_profiles import PromptProfileError, resolve_effective_window

    with pytest.raises(PromptProfileError, match="RUNTIME_WINDOW_UNKNOWN"):
        resolve_effective_window(runtime_window, 257_000)


def test_loader_and_renderer_are_full_and_deterministic(
    tmp_path: Path, monkeypatch,
) -> None:
    from agent.prompt_profiles import get_profile, load_policy_core, render_profile
    from tests.agent.prompt_profiles.fixtures import install_approved_test_core

    core_path = tmp_path / "SOUL.md"
    adapter_path = tmp_path / "adapter.md"
    core_path.write_bytes(b"policy\r\n<!-- REQ:one type:constraint scope:universal gate:g -->\r\n")
    adapter_path.write_bytes(b"adapter\r\n")

    core = load_policy_core(core_path)
    approved_core, approved_path = install_approved_test_core(tmp_path, monkeypatch)
    assert load_policy_core() == approved_core
    rendered_1 = render_profile(
        get_profile("openai-codex", "gpt-5.6-sol"),
        adapter_path=adapter_path,
    )
    rendered_2 = render_profile(
        get_profile("openai-codex", "gpt-5.6-sol"),
        core_path=approved_path,
        adapter_path=adapter_path,
    )

    assert core == "policy\n<!-- REQ:one type:constraint scope:universal gate:g -->\n"
    assert rendered_1 == rendered_2
    assert rendered_1.stable.startswith(approved_core)
    assert "adapter\n" in rendered_1.stable
    assert "TRUNCATED" not in rendered_1.stable
    assert rendered_1.cache_identity[-1] == rendered_1.stable_sha256
    assert rendered_1.manifest["canonical_core_sha256"] == rendered_1.canonical_core_sha256


def test_renderer_rejects_truth_reversal_for_every_core_entrypoint(
    tmp_path: Path, monkeypatch,
) -> None:
    from agent.prompt_profiles import PromptProfileError, get_profile, load_policy_core, render_profile
    from tests.agent.prompt_profiles.fixtures import install_approved_test_core

    approved, _approved_path = install_approved_test_core(tmp_path, monkeypatch)
    mutated = approved.replace(
        "Truth is the absolute priority.",
        "Plausible completion is the absolute priority.",
        1,
    )
    assert mutated != approved
    path = tmp_path / "mutated-core.md"
    path.write_text(mutated, encoding="utf-8")
    spec = get_profile("openai-codex", "gpt-5.6-sol")
    for kwargs in ({"core": mutated}, {"core_path": path}):
        with pytest.raises(PromptProfileError, match="POLICY_INTEGRITY_FAILURE"):
            render_profile(spec, **kwargs)


def test_render_identity_is_named_as_stable_not_final_prompt_hash(
    tmp_path: Path, monkeypatch,
) -> None:
    from agent.prompt_profiles import get_profile, render_profile
    from tests.agent.prompt_profiles.fixtures import install_approved_test_core

    install_approved_test_core(tmp_path, monkeypatch)
    rendered = render_profile(get_profile("openai-codex", "gpt-5.6-sol"))
    assert rendered.manifest["stable_render_sha256"] == rendered.stable_sha256
    assert "final_prompt_sha256" not in rendered.manifest


def test_provider_counters_use_exact_installed_tokenizers(
    tmp_path: Path, monkeypatch,
) -> None:
    from agent.prompt_profiles import get_token_counter
    from agent.prompt_profiles.tokenizer import DeepSeekTokenCounter
    from tests.agent.prompt_profiles.fixtures import fake_deepseek_transformers

    counter = get_token_counter("openai-codex", "gpt-5.6-sol")
    assert counter.tokenizer_id == "o200k_base"
    assert counter.count_text("hello") == 1
    assert counter.count_text("<|endoftext|>") == 7

    tokenizer = MagicMock()
    tokenizer.encode.side_effect = lambda value, **_: list(value)
    tokenizer.apply_chat_template.side_effect = lambda rows, **_: list(
        "|".join(str(row.get("role", "")) + ":" + str(row.get("content", "")) for row in rows)
    )
    transformers, digests, snapshot = fake_deepseek_transformers(tmp_path, tokenizer)
    loader = MagicMock(return_value=tokenizer)
    transformers.AutoTokenizer.from_pretrained = loader
    monkeypatch.setattr(DeepSeekTokenCounter, "asset_sha256", digests)
    with patch(
        "agent.prompt_profiles.tokenizer.importlib.import_module",
        return_value=transformers,
    ):
        deepseek = get_token_counter("deepseek", "deepseek-v4-flash")
    messages = [{"role": "user", "content": "hello"}]
    expected = deepseek._tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True
    )
    assert deepseek.model_id == "deepseek-ai/DeepSeek-V3.1"
    assert deepseek.count_text("hello") == len(
        deepseek._tokenizer.encode("hello", add_special_tokens=False)
    )
    assert deepseek.count_messages(messages) == len(expected)
    loader.assert_called_once_with(
        str(snapshot), trust_remote_code=False, local_files_only=True,
    )


def test_openai_counter_uses_only_candidate_asset_with_empty_cache(
    tmp_path: Path, monkeypatch,
) -> None:
    from agent.prompt_profiles import tokenizer as module

    empty_cache = tmp_path / "empty-cache"
    empty_cache.mkdir()
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(empty_cache))
    with (
        patch("socket.getaddrinfo", side_effect=AssertionError("DNS forbidden")) as dns,
        patch("urllib.request.urlopen", side_effect=AssertionError("URL forbidden")) as urlopen,
        patch("requests.get", side_effect=AssertionError("HTTP forbidden")) as request,
    ):
        counter = module.OpenAITokenCounter()
        assert counter.count_text("hello") == 1
        assert counter.count_text("<|endoftext|>") == 7
    dns.assert_not_called()
    urlopen.assert_not_called()
    request.assert_not_called()
    assert list(empty_cache.iterdir()) == []
    assert counter._encoding._pat_str == module._O200K_PATTERN
    assert counter._encoding._special_tokens == module._O200K_SPECIAL_TOKENS


def test_openai_counter_matches_official_o200k_constructor_offline(
    tmp_path: Path, monkeypatch,
) -> None:
    """The local reviewed ranks are byte-for-byte the official constructor input."""
    import tiktoken
    import tiktoken.load as tiktoken_load
    import tiktoken_ext.openai_public as official
    from agent.prompt_profiles import tokenizer as module

    calls = []

    def local_bytes(url: str, expected_hash: str):
        calls.append((url, expected_hash))
        return module._read_o200k_asset()

    # Keep the official load_tiktoken_bpe parser intact. Only replace its
    # byte-transport/cache seam with the reviewed candidate-owned payload.
    monkeypatch.setattr(tiktoken_load, "read_file_cached", local_bytes)
    assert tiktoken.__version__ == "0.12.0"
    with (
        patch("socket.getaddrinfo", side_effect=AssertionError("DNS forbidden")) as dns,
        patch("urllib.request.urlopen", side_effect=AssertionError("URL forbidden")) as urlopen,
        patch("requests.get", side_effect=AssertionError("HTTP forbidden")) as request,
    ):
        config = official.o200k_base()
        reference = tiktoken.Encoding(**config)
        candidate = module.OpenAITokenCounter()._encoding
        assert candidate._mergeable_ranks == reference._mergeable_ranks
        assert candidate._pat_str == reference._pat_str
        assert candidate._special_tokens == reference._special_tokens
        corpus = (
            "hello",
            "中文分词 日本語 العربية हिन्दी",
            "emoji: 👩🏽‍💻🚀",
            "controls:\x00\t\r\n and <|endoftext|>",
        )
        for text in corpus:
            assert candidate.encode(text, disallowed_special=()) == reference.encode(
                text, disallowed_special=()
            )
    assert calls == [(
        "https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken",
        module._O200K_ASSET_SHA256,
    )]
    dns.assert_not_called()
    urlopen.assert_not_called()
    request.assert_not_called()


@pytest.mark.parametrize("failure", ["missing", "corrupt", "symlink", "unreadable"])
def test_openai_counter_fails_closed_on_candidate_asset_fault(
    tmp_path: Path, monkeypatch, failure: str,
) -> None:
    from agent.prompt_profiles import tokenizer as module

    reviewed = module._O200K_ASSET
    candidate = tmp_path / "o200k_base.tiktoken"
    if failure == "missing":
        pass
    elif failure == "symlink":
        candidate.symlink_to(reviewed)
    else:
        candidate.write_bytes(reviewed.read_bytes())
        if failure == "corrupt":
            with candidate.open("r+b") as handle:
                handle.seek(0)
                handle.write(b"X")
        elif failure == "unreadable":
            candidate.chmod(0)
    monkeypatch.setattr(module, "_O200K_ASSET", candidate)

    with (
        patch("socket.getaddrinfo", side_effect=AssertionError("DNS forbidden")) as dns,
        patch("requests.get", side_effect=AssertionError("HTTP forbidden")) as request,
        pytest.raises(module.TokenizerUnavailable, match="TOKENIZER_UNAVAILABLE: o200k_base"),
    ):
        module.OpenAITokenCounter()
    dns.assert_not_called()
    request.assert_not_called()


def test_admission_uses_effective_window_and_reserves() -> None:
    from agent.prompt_profiles import evaluate_admission, get_profile

    spec = get_profile("openai-codex", "gpt-5.6-sol")
    admitted = evaluate_admission(
        spec,
        runtime_window=272_000,
        policy_core_tokens=20_000,
        fixed_tokens=56_000,
        conversation_tokens=152_000,
        requested_output_tokens=32_000,
    )
    assert admitted.effective_window == 257_000
    assert admitted.admitted is True

    rejected = evaluate_admission(
        spec,
        runtime_window=272_000,
        policy_core_tokens=20_000,
        fixed_tokens=56_001,
        conversation_tokens=152_000,
        requested_output_tokens=32_000,
    )
    assert rejected.admitted is False
    assert rejected.reason_code == "FIXED_PREFIX_LIMIT"


def _agent_with_post_client_failure() -> SimpleNamespace:
    old_client = MagicMock(name="old_client")
    compressor = MagicMock(name="compressor")
    compressor.model = "old-model"
    compressor.provider = "openrouter"
    compressor.base_url = "https://old.example/v1"
    compressor.api_key = "old-key"
    compressor.api_mode = "chat_completions"
    compressor.context_length = 64_000
    compressor.threshold_tokens = 32_000
    compressor.update_model.side_effect = RuntimeError("post-client compressor failure")

    agent = SimpleNamespace(
        model="old-model",
        provider="openrouter",
        base_url="https://old.example/v1",
        api_key="old-key",
        api_mode="chat_completions",
        client=old_client,
        _client_kwargs={"api_key": "old-key", "base_url": "https://old.example/v1"},
        _anthropic_client=None,
        _anthropic_api_key="",
        _anthropic_base_url=None,
        _is_anthropic_oauth=False,
        _config_context_length=None,
        _credential_pool=None,
        _transport_cache={"old": object()},
        _cached_system_prompt="old prompt",
        _system_prompt_breakdown={"old": True},
        _prompt_profile="old-profile",
        _use_prompt_caching=False,
        _use_native_cache_layout=False,
        _primary_runtime={"model": "old-model"},
        _fallback_activated=True,
        _fallback_index=2,
        _fallback_chain=[{"provider": "legacy", "model": "fallback"}],
        _fallback_model={"provider": "legacy", "model": "fallback"},
        context_compressor=compressor,
        _session_db=None,
        session_id=None,
    )
    agent._anthropic_prompt_cache_policy = lambda **_kwargs: (True, True)
    agent._ensure_lmstudio_runtime_loaded = lambda: None
    agent._apply_client_headers_for_base_url = lambda _url: None
    agent._create_openai_client = lambda *_args, **_kwargs: MagicMock(name="candidate")
    return agent


def test_post_client_failure_restores_complete_runtime_snapshot() -> None:
    from agent.agent_runtime_helpers import switch_model

    agent = _agent_with_post_client_failure()
    old = {
        "client": agent.client,
        "transport": dict(agent._transport_cache),
        "prompt": agent._cached_system_prompt,
        "breakdown": dict(agent._system_prompt_breakdown),
        "profile": agent._prompt_profile,
        "primary": dict(agent._primary_runtime),
        "fallback_chain": list(agent._fallback_chain),
    }

    with (
        patch("agent.model_metadata.get_model_context_length", return_value=272_000),
        patch("hermes_cli.timeouts.get_provider_request_timeout", return_value=None),
        pytest.raises(RuntimeError, match="post-client compressor failure"),
    ):
        switch_model(
            agent,
            "gpt-5.6-sol",
            "openai-codex",
            api_key="new-key",
            base_url="https://chatgpt.com/backend-api/codex",
            api_mode="codex_responses",
        )

    assert agent.model == "old-model"
    assert agent.provider == "openrouter"
    assert agent.client is old["client"]
    assert agent._transport_cache == old["transport"]
    assert agent._cached_system_prompt == old["prompt"]
    assert agent._system_prompt_breakdown == old["breakdown"]
    assert agent._prompt_profile == old["profile"]
    assert agent._primary_runtime == old["primary"]
    assert agent._fallback_chain == old["fallback_chain"]
    assert agent.context_compressor.model == "old-model"
    assert agent.context_compressor.context_length == 64_000
