"""Deterministic canonical-core plus model-adapter renderer."""
from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from .registry import PromptProfileError, PromptProfileSpec, default_core_path

_RENDERER_SCHEMA = 1
_REQ_RE = re.compile(r"<!-- REQ:(\S+) type:(\S+) scope:(\S+) gate:(\S+) -->")
_PROTECTED_BLOCKS = (
    "TRUTH MANDATE", "SELF-POLICING BAN", "CODE TRACEABILITY MANDATE",
    "HONEST BLOCKER REPORT IS VALID COMPLETION", "BYPASS ESCALATION PROHIBITION",
)
_APPROVED_REQ_MANIFEST_SHA256 = "71c71b61aa36002e0c9d3bbdeff75860f7de275ebe2e075ca506aa2800bc5eaa"
_APPROVED_CANONICAL_CORE_SHA256 = "94075360d64c1bde30039428c3295c8721330043f03edf07bbb2d6cd55bd515e"
_APPROVED_REQ_COUNT = 150
_TEST034_TICKET = "TEST-034"
_TEST034_CONFIG_URL = "https://github.com/kendeng300/marketwatch.git"
_TEST034_SCRIPTS_URL = "https://github.com/kendeng300/marketwatch.git"
_TEST034_HERMES_URL = "https://github.com/kendeng300/hermes-agent.git"
_TEST034_REPOSITORY_FIELDS = frozenset({
    "canonical_url", "push_remote", "branch", "base_branch",
    "base_ref_commit", "base_commit", "frozen_git_tree", "tree_digest",
    "entries", "merge_authority",
})
_TEST034_ENTRY_FIELDS = frozenset({
    "path", "mode", "blob_oid", "sha256", "dependency",
})
_TEST034_HERMES_CANDIDATE_COUNT = 125
_TEST034_HERMES_CANDIDATE_MODES = MappingProxyType({
    ".github/pr-screenshots/39327/providers-collapsed.png": "100644",
    ".github/pr-screenshots/39327/providers-expanded.png": "100644",
    ".github/pr-screenshots/39327/tools-collapsed.png": "100644",
    ".github/pr-screenshots/39327/tools-expanded.png": "100644",
    ".github/workflows/deploy-site.yml": "100644",
    ".github/workflows/docker.yml": "100644",
    ".github/workflows/supply-chain-audit.yml": "100644",
    "MANIFEST.in": "100644",
    "acp_adapter/edit_approval.py": "100644",
    "agent/coding_context.py": "100644",
    "agent/conversation_compression.py": "100644",
    "agent/copilot_acp_client.py": "100644",
    "agent/learn_prompt.py": "100644",
    "agent/prompt_profiles/assets/o200k_base.tiktoken": "100644",
    "agent/prompt_profiles/renderer.py": "100644",
    "agent/prompt_profiles/tokenizer.py": "100644",
    "agent/secret_sources/bitwarden.py": "100644",
    "agent/verification_evidence.py": "100644",
    "agent/verification_stop.py": "100644",
    "cli.py": "100644",
    "gateway/platforms/qqbot/adapter.py": "100644",
    "gateway/platforms/signal.py": "100644",
    "gateway/platforms/weixin.py": "100644",
    "gateway/run.py": "100644",
    "gateway/slash_commands.py": "100644",
    "hermes_cli/cli_commands_mixin.py": "100644",
    "hermes_cli/gateway.py": "100644",
    "hermes_cli/journey.py": "100644",
    "hermes_cli/main.py": "100644",
    "hermes_cli/managed_uv.py": "100644",
    "hermes_cli/plugins_cmd.py": "100644",
    "hermes_cli/profile_distribution.py": "100644",
    "hermes_cli/profiles.py": "100644",
    "hermes_cli/tools_config.py": "100644",
    "hermes_cli/voice.py": "100644",
    "hermes_cli/web_server.py": "100644",
    "hermes_constants.py": "100644",
    "hermes_temp.py": "100644",
    "optional-skills/creative/pixel-art/scripts/pixel_art_video.py": "100644",
    "optional-skills/finance/excel-author/scripts/recalc.py": "100644",
    "optional-skills/productivity/here-now/scripts/drive.sh": "100755",
    "plugins/disk-cleanup/README.md": "100644",
    "plugins/disk-cleanup/__init__.py": "100644",
    "plugins/disk-cleanup/disk_cleanup.py": "100755",
    "plugins/memory/openviking/__init__.py": "100644",
    "plugins/platforms/discord/adapter.py": "100644",
    "plugins/platforms/line/adapter.py": "100644",
    "plugins/platforms/simplex/adapter.py": "100644",
    "plugins/platforms/slack/adapter.py": "100644",
    "plugins/teams_pipeline/meetings.py": "100644",
    "plugins/teams_pipeline/pipeline.py": "100644",
    "plugins/teams_pipeline/store.py": "100644",
    "pyproject.toml": "100644",
    "run_agent.py": "100644",
    "scripts/benchmark_browser_eval.py": "100644",
    "scripts/dev-sandbox.sh": "100755",
    "scripts/install.sh": "100755",
    "scripts/install_psutil_android.py": "100755",
    "scripts/lib/node-bootstrap.sh": "100644",
    "scripts/lib/temp-authority.sh": "100644",
    "scripts/run_tests.sh": "100755",
    "scripts/run_tests_parallel.py": "100755",
    "scripts/tool_search_livetest.py": "100644",
    "scripts/transaction_hooks/test034-pre-commit.sh": "100755",
    "scripts/transaction_hooks/test034-pre-push.sh": "100755",
    "setup-hermes.sh": "100755",
    "setup.py": "100644",
    "skills/creative/p5js/scripts/render.sh": "100755",
    "skills/productivity/powerpoint/scripts/office/pack.py": "100644",
    "tests/agent/prompt_profiles/fixtures.py": "100644",
    "tests/agent/prompt_profiles/test_loop2_remediation.py": "100644",
    "tests/agent/prompt_profiles/test_systems_contract.py": "100644",
    "tests/agent/test_coding_context.py": "100644",
    "tests/agent/test_verification_evidence.py": "100644",
    "tests/agent/test_verification_stop.py": "100644",
    "tests/conftest.py": "100644",
    "tests/gateway/test_model_command_async_offload.py": "100644",
    "tests/gateway/test_model_command_custom_providers.py": "100644",
    "tests/gateway/test_model_command_expensive_confirm.py": "100644",
    "tests/gateway/test_model_picker_persist.py": "100644",
    "tests/gateway/test_prompt_profile_switch_after_compression.py": "100644",
    "tests/gateway/test_send_voice_reply_notify.py": "100644",
    "tests/gateway/test_session_env.py": "100644",
    "tests/gateway/test_slack.py": "100644",
    "tests/plugins/test_disk_cleanup_plugin.py": "100644",
    "tests/scripts/test_candidate_hooks.py": "100644",
    "tests/scripts/test_run_tests_venv_selection.py": "100644",
    "tests/scripts/test_temp_authority_wrapper.py": "100644",
    "tests/stress/test_benchmarks.py": "100644",
    "tests/test_bitwarden_secrets.py": "100644",
    "tests/test_hermes_temp_authority.py": "100644",
    "tests/test_packaging_metadata.py": "100644",
    "tests/test_run_tests_parallel.py": "100644",
    "tests/test_temp_authority_h1_migrations.py": "100644",
    "tests/test_temp_authority_h2_migrations.py": "100644",
    "tests/tools/test_base_environment.py": "100644",
    "tests/tools/test_browser_orphan_reaper.py": "100644",
    "tests/tools/test_init_session_cwd_respect.py": "100644",
    "tests/tools/test_local_tempdir.py": "100644",
    "tests/tools/test_tool_result_storage.py": "100644",
    "tools/approval.py": "100644",
    "tools/browser_tool.py": "100644",
    "tools/code_execution_tool.py": "100644",
    "tools/computer_use/cua_backend.py": "100644",
    "tools/credential_files.py": "100644",
    "tools/environments/base.py": "100644",
    "tools/environments/daytona.py": "100644",
    "tools/environments/docker.py": "100644",
    "tools/environments/file_sync.py": "100644",
    "tools/environments/local.py": "100644",
    "tools/environments/managed_modal.py": "100644",
    "tools/environments/modal.py": "100644",
    "tools/environments/singularity.py": "100644",
    "tools/environments/ssh.py": "100644",
    "tools/image_source.py": "100644",
    "tools/lazy_deps.py": "100644",
    "tools/process_registry.py": "100644",
    "tools/tirith_security.py": "100644",
    "tools/tool_result_storage.py": "100644",
    "tools/transcription_tools.py": "100644",
    "tools/tts_tool.py": "100644",
    "tools/voice_mode.py": "100644",
    "trajectory_compressor.py": "100644",
    "tui_gateway/server.py": "100644",
    "uv.lock": "100644",
})


def _normalized_text(data: bytes, *, label: str) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PromptProfileError(f"INVALID_UTF8: {label}") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.rstrip("\n") + "\n"


def load_policy_core(path: Path | str | None = None) -> str:
    source = Path(path) if path is not None else default_core_path()
    try:
        return _normalized_text(source.read_bytes(), label="canonical policy core")
    except OSError as exc:
        raise PromptProfileError(f"POLICY_CORE_UNAVAILABLE: {source}") from exc


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _approved_core_facts(canonical: str) -> tuple[str, list[list[str]], str]:
    """Return the approved content facts or fail closed.

    Keeping this check in one function prevents the normal renderer and the
    cross-repository candidate verifier from drifting onto different policy
    definitions.
    """
    core_hash = _hash(canonical)
    if core_hash != _APPROVED_CANONICAL_CORE_SHA256:
        raise PromptProfileError("POLICY_INTEGRITY_FAILURE: unapproved canonical core body")
    reqs = [list(match) for match in _REQ_RE.findall(canonical)]
    req_keys = [tuple(row) for row in reqs]
    if len(req_keys) != _APPROVED_REQ_COUNT or len(set(req_keys)) != _APPROVED_REQ_COUNT:
        raise PromptProfileError(
            "POLICY_INTEGRITY_FAILURE: expected "
            f"{_APPROVED_REQ_COUNT} unique REQ tuples, got {len(req_keys)}"
        )
    missing = [block for block in _PROTECTED_BLOCKS if block not in canonical]
    if missing:
        raise PromptProfileError(
            "POLICY_INTEGRITY_FAILURE: missing protected blocks: " + ", ".join(missing)
        )
    req_manifest_hash = hashlib.sha256(
        json.dumps(reqs, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if req_manifest_hash != _APPROVED_REQ_MANIFEST_SHA256:
        raise PromptProfileError("POLICY_INTEGRITY_FAILURE: unapproved REQ manifest")
    return core_hash, reqs, req_manifest_hash


def _read_regular_file(path: Path | str, *, label: str) -> bytes:
    """Read one stable regular file without following its final symlink."""
    source = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        before = source.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise PromptProfileError(f"{label}_UNAVAILABLE")
        fd = os.open(source, flags)
        try:
            opened = os.fstat(fd)
            if not stat.S_ISREG(opened.st_mode) or (
                opened.st_dev,
                opened.st_ino,
            ) != (before.st_dev, before.st_ino):
                raise PromptProfileError(f"{label}_CHANGED_DURING_READ")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(fd)
            if (
                after.st_size != opened.st_size
                or after.st_mtime_ns != opened.st_mtime_ns
                or after.st_ctime_ns != opened.st_ctime_ns
            ):
                raise PromptProfileError(f"{label}_CHANGED_DURING_READ")
            return b"".join(chunks)
        finally:
            os.close(fd)
    except PromptProfileError:
        raise
    except OSError as exc:
        raise PromptProfileError(f"{label}_UNAVAILABLE") from exc


def _git_blob_oid(payload: bytes, *, width: int) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    if width == 40:
        return hashlib.sha1(header + payload).hexdigest()
    if width == 64:
        return hashlib.sha256(header + payload).hexdigest()
    raise PromptProfileError("CANDIDATE_POLICY_ENTRY_INVALID")


def _candidate_file(root: Path, relative: str) -> Path:
    """Resolve one manifest path inside an already materialized candidate."""
    try:
        resolved_root = root.resolve(strict=True)
        if root.is_symlink() or not resolved_root.is_dir():
            raise PromptProfileError("CANDIDATE_POLICY_REPOSITORY_INVALID")
        candidate = resolved_root.joinpath(*relative.split("/"))
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(resolved_root)
        # A materialized candidate must not redirect any path component.  The
        # final file is checked again with O_NOFOLLOW by _read_regular_file.
        cursor = resolved_root
        for component in relative.split("/"):
            cursor = cursor / component
            if cursor.is_symlink():
                raise PromptProfileError("CANDIDATE_POLICY_ENTRY_INVALID")
        if resolved != candidate:
            raise PromptProfileError("CANDIDATE_POLICY_ENTRY_INVALID")
        return candidate
    except PromptProfileError:
        raise
    except (OSError, ValueError) as exc:
        raise PromptProfileError("CANDIDATE_POLICY_ENTRY_INVALID") from exc


def _verify_candidate_entry(
    entry: Any,
    *,
    expected_path: str,
    expected_mode: str,
    payload: bytes,
) -> None:
    if (
        not isinstance(entry, dict)
        or set(entry) != _TEST034_ENTRY_FIELDS
        or entry.get("path") != expected_path
        or entry.get("mode") != expected_mode
        or entry.get("dependency") is not None
        or not isinstance(entry.get("blob_oid"), str)
        or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", entry["blob_oid"])
        or not isinstance(entry.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
    ):
        raise PromptProfileError("CANDIDATE_POLICY_ENTRY_INVALID")
    if hashlib.sha256(payload).hexdigest() != entry["sha256"]:
        raise PromptProfileError("CANDIDATE_POLICY_DIGEST_MISMATCH")
    if _git_blob_oid(payload, width=len(entry["blob_oid"])) != entry["blob_oid"]:
        raise PromptProfileError("CANDIDATE_POLICY_BLOB_MISMATCH")


def _candidate_repository(
    repositories: Mapping[str, Any],
    *,
    label: str,
    canonical_url: str,
) -> tuple[list[Any], dict[str, Any]]:
    """Return one exact canonical-v2 repository declaration."""
    repository = repositories.get(label)
    if (
        not isinstance(repository, dict)
        or set(repository) != _TEST034_REPOSITORY_FIELDS
        or repository.get("canonical_url") != canonical_url
        or not isinstance(repository.get("entries"), list)
        or not repository["entries"]
    ):
        raise PromptProfileError("CANDIDATE_POLICY_REPOSITORY_INVALID")
    entries = repository["entries"]
    paths = [
        entry.get("path")
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    ]
    if len(paths) != len(entries) or len(paths) != len(set(paths)):
        raise PromptProfileError("CANDIDATE_POLICY_PATH_SET_MISMATCH")
    return entries, repository


def _verify_candidate_dependency(
    entries: list[Any],
    *,
    dependency: str,
    expected_path: str,
) -> None:
    matches = [
        entry for entry in entries
        if isinstance(entry, dict) and entry.get("dependency") == dependency
    ]
    if (
        len(matches) != 1
        or set(matches[0]) != _TEST034_ENTRY_FIELDS
        or matches[0].get("path") != expected_path
        or matches[0].get("mode") != "160000"
        or matches[0].get("blob_oid") is not None
        or matches[0].get("sha256") is not None
    ):
        raise PromptProfileError("CANDIDATE_POLICY_DEPENDENCY_INVALID")


def verify_candidate_policy_approval(
    manifest_path: Path | str,
    *,
    manifest_sha256: str,
    config_candidate_root: Path | str,
    hermes_candidate_root: Path | str,
) -> Mapping[str, Any]:
    """Bind renderer approval to exact TEST-034 candidate bytes.

    The mechanical transaction supplies the digest of the already validated
    version-2 manifest.  The verifier then proves that its materialized config
    candidate contains the same ``SOUL.md`` bytes accepted by this renderer,
    and that config binds the scripts and Hermes child candidates with the
    canonical v2 gitlink topology.  It never consults the mutable worktree,
    index, or HEAD, so approval cannot silently move while the cross-repository
    candidate is being assembled.
    """
    if not re.fullmatch(r"[0-9a-f]{64}", manifest_sha256):
        raise PromptProfileError("CANDIDATE_POLICY_APPROVAL_INVALID")
    manifest_bytes = _read_regular_file(manifest_path, label="CANDIDATE_MANIFEST")
    if hashlib.sha256(manifest_bytes).hexdigest() != manifest_sha256:
        raise PromptProfileError("CANDIDATE_MANIFEST_DIGEST_MISMATCH")
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PromptProfileError("CANDIDATE_MANIFEST_INVALID") from exc
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {
            "version", "ticket", "run_nonce", "issued_at", "expires_at",
            "content_manifest", "repositories",
        }
        or manifest.get("version") != 2
        or manifest.get("ticket") != _TEST034_TICKET
        or not isinstance(manifest.get("repositories"), dict)
    ):
        raise PromptProfileError("CANDIDATE_MANIFEST_INVALID")
    repositories = manifest["repositories"]
    # The authoritative v2 loader always requires config+scripts and adds
    # hermes-agent only when config declares its gitlink.  Policy approval
    # necessarily binds Hermes bytes, so this candidate must contain all three.
    if set(repositories) != {"config", "scripts", "hermes-agent"}:
        raise PromptProfileError("CANDIDATE_POLICY_REPOSITORY_INVALID")
    config_entries, _config = _candidate_repository(
        repositories, label="config", canonical_url=_TEST034_CONFIG_URL,
    )
    _scripts_entries, _scripts = _candidate_repository(
        repositories, label="scripts", canonical_url=_TEST034_SCRIPTS_URL,
    )
    _verify_candidate_dependency(
        config_entries, dependency="scripts", expected_path="scripts",
    )
    _verify_candidate_dependency(
        config_entries, dependency="hermes-agent", expected_path="hermes-agent",
    )
    soul_entries = [
        entry for entry in config_entries
        if isinstance(entry, dict) and entry.get("path") == "SOUL.md"
    ]
    if len(soul_entries) != 1:
        raise PromptProfileError("CANDIDATE_POLICY_ENTRY_MISSING")
    soul = soul_entries[0]
    core_bytes = _read_regular_file(
        _candidate_file(Path(config_candidate_root), "SOUL.md"),
        label="CANDIDATE_POLICY_CORE",
    )
    _verify_candidate_entry(
        soul,
        expected_path="SOUL.md",
        expected_mode="100644",
        payload=core_bytes,
    )
    raw_core_sha256 = hashlib.sha256(core_bytes).hexdigest()

    entries, _hermes = _candidate_repository(
        repositories, label="hermes-agent", canonical_url=_TEST034_HERMES_URL,
    )
    indexed = {
        entry.get("path"): entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    if (
        len(_TEST034_HERMES_CANDIDATE_MODES) != _TEST034_HERMES_CANDIDATE_COUNT
        or len(indexed) != _TEST034_HERMES_CANDIDATE_COUNT
        or len(indexed) != len(entries)
        or set(indexed) != set(_TEST034_HERMES_CANDIDATE_MODES)
    ):
        raise PromptProfileError("CANDIDATE_POLICY_PATH_SET_MISMATCH")
    candidate_root = Path(hermes_candidate_root)
    candidate_digests: dict[str, str] = {}
    for relative, mode in _TEST034_HERMES_CANDIDATE_MODES.items():
        payload = _read_regular_file(
            _candidate_file(candidate_root, relative),
            label="CANDIDATE_POLICY_ENTRY",
        )
        _verify_candidate_entry(
            indexed[relative],
            expected_path=relative,
            expected_mode=mode,
            payload=payload,
        )
        candidate_digests[relative] = indexed[relative]["sha256"]
    canonical = _normalized_text(core_bytes, label="candidate canonical policy core")
    core_hash, reqs, req_manifest_hash = _approved_core_facts(canonical)
    return MappingProxyType({
        "ticket": _TEST034_TICKET,
        "manifest_sha256": manifest_sha256,
        "raw_core_sha256": raw_core_sha256,
        "canonical_core_sha256": core_hash,
        "req_manifest_sha256": req_manifest_hash,
        "req_count": len(reqs),
        "hermes_candidate_sha256": MappingProxyType(candidate_digests),
    })


def _adapter_text(spec: PromptProfileSpec, adapter_path: Path | str | None) -> tuple[str, Mapping[str, Any]]:
    if adapter_path is not None:
        path = Path(adapter_path)
        try:
            return _normalized_text(path.read_bytes(), label="adapter"), MappingProxyType({})
        except OSError as exc:
            raise PromptProfileError(f"ADAPTER_UNAVAILABLE: {path}") from exc
    module = importlib.import_module(spec.adapter_module)
    data = module.get_adapter()
    content = _normalized_text(str(data["content"]).encode("utf-8"), label="adapter")
    return content, MappingProxyType(dict(data))


@dataclass(frozen=True)
class RenderedPromptProfile:
    spec: PromptProfileSpec
    stable: str
    canonical_core_sha256: str
    adapter_sha256: str
    stable_sha256: str
    req_manifest_sha256: str
    cache_identity: tuple[str, str, str, str, str, str]
    manifest: Mapping[str, Any]
    adapter_metadata: Mapping[str, Any]

    @property
    def full_prompt(self) -> str:
        return self.stable


def render_profile(
    spec: PromptProfileSpec,
    *,
    core: str | None = None,
    core_path: Path | str | None = None,
    adapter_path: Path | str | None = None,
) -> RenderedPromptProfile:
    # Resolve the active profile at call time.  Path.home()/".hermes" bypasses
    # HERMES_HOME and context-local profile overrides, which made a gateway
    # session validate one profile's SOUL.md while reading another profile's
    # config/session state.  default_core_path() is the canonical resolver and
    # also keeps tests isolated by their temporary HERMES_HOME.
    canonical_path = core_path if core_path is not None else default_core_path()
    canonical = load_policy_core(canonical_path) if core is None else _normalized_text(
        core.encode("utf-8"), label="canonical policy core"
    )
    adapter, metadata = _adapter_text(spec, adapter_path)
    stable = canonical + "\n" + adapter
    core_hash, reqs, req_manifest_hash = _approved_core_facts(canonical)
    adapter_hash, stable_hash = _hash(adapter), _hash(stable)
    # Integrity is a property of content, not the filename it came from.  A
    # caller may override the profile-aware source path for validation/tests,
    # but may not bypass the production contract by doing so.
    if _REQ_RE.search(adapter) or any(block in adapter for block in _PROTECTED_BLOCKS):
        raise PromptProfileError("ADAPTER_POLICY_OVERRIDE_FORBIDDEN")
    identity = (
        spec.provider,
        spec.model,
        spec.profile_id,
        core_hash,
        adapter_hash,
        stable_hash,
    )
    manifest = MappingProxyType({
        "schema_version": _RENDERER_SCHEMA,
        "profile_id": spec.profile_id,
        "provider": spec.provider,
        "model": spec.model,
        "canonical_core_sha256": core_hash,
        "adapter_sha256": adapter_hash,
        "stable_render_sha256": stable_hash,
        "req_manifest_sha256": req_manifest_hash,
        "req_count": len(reqs),
        "cache_identity": list(identity),
    })
    return RenderedPromptProfile(
        spec=spec,
        stable=stable,
        canonical_core_sha256=core_hash,
        adapter_sha256=adapter_hash,
        stable_sha256=stable_hash,
        req_manifest_sha256=req_manifest_hash,
        cache_identity=identity,
        manifest=manifest,
        adapter_metadata=metadata,
    )


def serialize_manifest(rendered: RenderedPromptProfile) -> bytes:
    return (json.dumps(dict(rendered.manifest), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
