"""Deterministic canonical-core plus model-adapter renderer."""
from __future__ import annotations

import hashlib
import importlib
import json
import re
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
_APPROVED_REQ_MANIFEST_SHA256 = "7963ac5a1f6bbc99c5d3fcb064ca50cc5062b729fe7135b3ea515cee69660f55"
_APPROVED_CANONICAL_CORE_SHA256 = "9175c49e20f242f42ca1d043486c5edae742628b0ed551ecf882e662e0fe1d24"
_APPROVED_CANONICAL_CORE_PATH = Path.home() / ".hermes" / "SOUL.md"


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
    canonical_path = core_path if core_path is not None else _APPROVED_CANONICAL_CORE_PATH
    canonical = load_policy_core(canonical_path) if core is None else _normalized_text(
        core.encode("utf-8"), label="canonical policy core"
    )
    adapter, metadata = _adapter_text(spec, adapter_path)
    stable = canonical + "\n" + adapter
    core_hash, adapter_hash, stable_hash = _hash(canonical), _hash(adapter), _hash(stable)
    if core_hash != _APPROVED_CANONICAL_CORE_SHA256:
        raise PromptProfileError("POLICY_INTEGRITY_FAILURE: unapproved canonical core body")
    reqs = [list(match) for match in _REQ_RE.findall(canonical)]
    # Integrity is a property of content, not the filename it came from.  A
    # caller may override the profile-aware source path for validation/tests,
    # but may not bypass the production contract by doing so.
    req_keys = [tuple(row) for row in reqs]
    if len(req_keys) != 152 or len(set(req_keys)) != 152:
        raise PromptProfileError(
            f"POLICY_INTEGRITY_FAILURE: expected 152 unique REQ tuples, got {len(req_keys)}"
        )
    missing = [block for block in _PROTECTED_BLOCKS if block not in canonical]
    if missing:
        raise PromptProfileError(
            "POLICY_INTEGRITY_FAILURE: missing protected blocks: " + ", ".join(missing)
        )
    if _REQ_RE.search(adapter) or any(block in adapter for block in _PROTECTED_BLOCKS):
        raise PromptProfileError("ADAPTER_POLICY_OVERRIDE_FORBIDDEN")
    req_manifest_hash = hashlib.sha256(
        json.dumps(reqs, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if req_manifest_hash != _APPROVED_REQ_MANIFEST_SHA256:
        raise PromptProfileError("POLICY_INTEGRITY_FAILURE: unapproved REQ manifest")
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
