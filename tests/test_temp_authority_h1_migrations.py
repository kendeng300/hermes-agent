"""Behavioral contracts for Hermes core/gateway temporary-storage migration."""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.copilot_acp_client import _resolve_home_dir
from agent.verification_stop import build_verify_on_stop_nudge
from hermes_constants import get_hermes_home
from hermes_temp import current_temp_authority


_MIGRATED = (
    "agent/coding_context.py",
    "agent/conversation_compression.py",
    "agent/copilot_acp_client.py",
    "agent/secret_sources/bitwarden.py",
    "agent/verification_evidence.py",
    "agent/verification_stop.py",
    "gateway/run.py",
    "gateway/platforms/qqbot/adapter.py",
    "gateway/platforms/signal.py",
    "gateway/platforms/weixin.py",
)
_IMPLICIT_TEMP_CALLS = {
    "gettempdir",
    "NamedTemporaryFile",
    "TemporaryDirectory",
    "mkdtemp",
}


def test_migrated_production_paths_have_no_implicit_temp_allocator() -> None:
    root = Path(__file__).resolve().parent.parent
    findings: list[str] = []
    for relative in _MIGRATED:
        tree = ast.parse((root / relative).read_text(encoding="utf-8"), relative)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.attr if isinstance(node.func, ast.Attribute)
                else node.func.id if isinstance(node.func, ast.Name)
                else ""
            )
            if name in _IMPLICIT_TEMP_CALLS:
                findings.append(f"{relative}:{node.lineno}:{name}")
    assert findings == []


def test_mock_config_cwd_is_existing_profile_private_directory(mock_config) -> None:
    cwd = Path(mock_config["terminal"]["cwd"])
    assert cwd.is_dir()
    assert cwd.is_relative_to(get_hermes_home())
    assert not str(cwd).startswith(("/tmp/", "/var/tmp/", "/dev/shm/"))


def test_no_suite_nudge_names_active_profile_authority(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "package.json").write_text("{}", encoding="utf-8")

    nudge = build_verify_on_stop_nudge(
        session_id="authority-nudge",
        changed_paths=[str(project / "src" / "app.ts")],
    )

    assert nudge is not None
    authority_root = get_hermes_home() / "tmp"
    assert str(authority_root) in nudge
    assert "Hermes-owned temporary path" in nudge


def test_copilot_home_fallback_uses_profile_not_system_temp(monkeypatch) -> None:
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.setattr(os.path, "expanduser", lambda _value: "~")
    monkeypatch.setitem(
        sys.modules,
        "pwd",
        SimpleNamespace(getpwuid=lambda _uid: SimpleNamespace(pw_dir="")),
    )

    resolved = Path(_resolve_home_dir())

    assert resolved == get_hermes_home()
    assert (resolved / "tmp").is_dir()
    assert not str(resolved).startswith(("/tmp/", "/var/tmp/", "/dev/shm/"))


@pytest.mark.asyncio
async def test_qq_stt_conversion_returns_owned_workspace(monkeypatch) -> None:
    from gateway.platforms.qqbot.adapter import QQAdapter

    adapter = object.__new__(QQAdapter)

    async def _no_silk(_src: str, _dst: str):
        return None

    async def _convert(_src: str, dst: str):
        Path(dst).write_bytes(b"RIFF" + b"\0" * 64)
        return dst

    monkeypatch.setattr(adapter, "_convert_silk_to_wav", _no_silk)
    monkeypatch.setattr(adapter, "_convert_ffmpeg_to_wav", _convert)

    converted = await adapter._convert_audio_to_wav_file(b"voice", "voice.amr")

    assert converted is not None
    converted_path, owned = converted
    assert Path(converted_path).is_file()
    assert Path(converted_path).is_relative_to(Path(os.environ["HERMES_TEMP_ROOT"]))
    owned.cleanup()
    assert not Path(converted_path).exists()


@pytest.mark.asyncio
async def test_qq_cached_conversion_reaps_authority_workspace(monkeypatch) -> None:
    import gateway.platforms.qqbot.adapter as qq_module
    from gateway.platforms.qqbot.adapter import QQAdapter

    adapter = object.__new__(QQAdapter)

    async def _convert(_src: str, dst: str):
        Path(dst).write_bytes(b"RIFF" + b"\1" * 64)
        return dst

    captured: dict[str, object] = {}

    def _cache(payload: bytes, name: str) -> str:
        captured.update(payload=payload, name=name)
        return "cache://qq-voice"

    monkeypatch.setattr(adapter, "_convert_ffmpeg_to_wav", _convert)
    monkeypatch.setattr(qq_module, "cache_document_from_bytes", _cache)
    with current_temp_authority() as authority:
        before = {entry.name for entry in authority.root.iterdir()}

    result = await adapter._convert_audio_to_wav(b"audio", "voice.mp3")

    with current_temp_authority() as authority:
        after = {entry.name for entry in authority.root.iterdir()}
    assert result == "cache://qq-voice"
    assert captured == {"payload": b"RIFF" + b"\1" * 64, "name": "qq_voice.wav"}
    assert after == before


def test_signal_remux_reaps_owned_source_when_initial_write_fails(monkeypatch) -> None:
    import gateway.platforms.signal as signal_module

    with current_temp_authority() as authority:
        before = {entry.name for entry in authority.root.iterdir()}
    monkeypatch.setattr(signal_module.shutil, "which", lambda _name: "/bin/false")

    def _fail_fdopen(*_args, **_kwargs):
        raise OSError("injected write-open failure")

    monkeypatch.setattr(signal_module.os, "fdopen", _fail_fdopen)

    assert signal_module._remux_aac_to_m4a(b"audio") is None
    with current_temp_authority() as authority:
        after = {entry.name for entry in authority.root.iterdir()}
    assert after == before
