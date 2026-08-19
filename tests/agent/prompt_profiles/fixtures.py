"""Hermetic prompt-profile fixtures shared by the focused contract tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any


def install_approved_test_core(tmp_path: Path, monkeypatch: Any) -> tuple[str, Path]:
    """Install a deterministic approved core under the test HERMES_HOME.

    Production keeps a fail-closed digest for the deployed canonical core. Unit
    tests need the same integrity behavior without reading the operator's live
    profile, so this fixture binds the approval constants to a synthetic core
    for the lifetime of one test.
    """
    from agent.prompt_profiles import renderer

    protected = (
        "TRUTH MANDATE",
        "SELF-POLICING BAN",
        "CODE TRACEABILITY MANDATE",
        "HONEST BLOCKER REPORT IS VALID COMPLETION",
        "BYPASS ESCALATION PROHIBITION",
    )
    reqs = [
        f"<!-- REQ:test-{index:03d} type:constraint "
        f"scope:universal gate:test-gate-{index:03d} -->"
        for index in range(150)
    ]
    core = "\n".join(("Truth is the absolute priority.", *protected, *reqs)) + "\n"
    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    core_path = hermes_home / "SOUL.md"
    core_path.write_text(core, encoding="utf-8")
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    manifest = [list(match) for match in renderer._REQ_RE.findall(core)]
    monkeypatch.setattr(
        renderer,
        "_APPROVED_CANONICAL_CORE_SHA256",
        hashlib.sha256(core.encode("utf-8")).hexdigest(),
    )
    monkeypatch.setattr(
        renderer,
        "_APPROVED_REQ_MANIFEST_SHA256",
        hashlib.sha256(
            json.dumps(
                manifest, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest(),
    )
    monkeypatch.setattr(renderer, "_APPROVED_REQ_COUNT", len(manifest))
    return core, core_path


def fake_deepseek_transformers(
    tmp_path: Path, tokenizer: Any
) -> tuple[SimpleNamespace, dict[str, str], Path]:
    """Return hash-verifiable local tokenizer assets and a fake loader."""
    snapshot = tmp_path / "hf-cache" / "snapshots" / "reviewed"
    snapshot.mkdir(parents=True)
    payloads = {
        "tokenizer.json": b'{"fixture":"tokenizer"}\n',
        "tokenizer_config.json": b'{"fixture":"config"}\n',
    }
    digests: dict[str, str] = {}
    for name, payload in payloads.items():
        (snapshot / name).write_bytes(payload)
        digests[name] = hashlib.sha256(payload).hexdigest()

    def cached_file(model_id: str, name: str, **kwargs: Any) -> str:
        assert model_id == "deepseek-ai/DeepSeek-V3.1"
        assert kwargs == {
            "revision": "c0781d039fb7a1ba2abc4add0bdc293e92d2b8db",
            "local_files_only": True,
        }
        return str(snapshot / name)

    transformers = SimpleNamespace(
        __version__="test",
        AutoTokenizer=SimpleNamespace(
            from_pretrained=lambda *args, **kwargs: tokenizer
        ),
        utils=SimpleNamespace(hub=SimpleNamespace(cached_file=cached_file)),
    )
    return transformers, digests, snapshot
