"""Regression tests for gateway /model support of config.yaml custom_providers."""

import asyncio
import threading

import yaml
import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session import SessionSource


def _make_runner():
    runner = object.__new__(GatewayRunner)
    runner.adapters = {}
    runner._voice_mode = {}
    runner._session_model_overrides = {}
    return runner


def _make_event(text="/model"):
    return MessageEvent(
        text=text,
        message_type=MessageType.TEXT,
        source=SessionSource(platform=Platform.TELEGRAM, chat_id="12345", chat_type="dm"),
    )


@pytest.mark.asyncio
async def test_handle_model_command_lists_saved_custom_provider(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        yaml.safe_dump(
            {
                "model": {
                    "default": "gpt-5.4",
                    "provider": "openai-codex",
                    "base_url": "https://chatgpt.com/backend-api/codex",
                },
                "providers": {},
                "custom_providers": [
                    {
                        "name": "Local (127.0.0.1:4141)",
                        "base_url": "http://127.0.0.1:4141/v1",
                        "model": "rotator-openrouter-coding",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    import gateway.run as gateway_run

    monkeypatch.setattr(gateway_run, "_hermes_home", hermes_home)
    monkeypatch.setattr(
        GatewayRunner,
        "_resolve_profile_home_for_source",
        lambda _runner, _source: hermes_home,
    )
    monkeypatch.setattr("agent.models_dev.fetch_models_dev", lambda: {})

    runner = _make_runner()
    assert runner._resolve_profile_home_for_source(_make_event().source) == hermes_home
    try:
        result = await runner._handle_model_command(_make_event())
    finally:
        runner._shutdown_executor()

    assert result is not None
    assert "Local (127.0.0.1:4141)" in result
    assert "custom:local-(127.0.0.1:4141)" in result
    assert "rotator-openrouter-coding" in result


@pytest.mark.asyncio
async def test_direct_model_switch_uses_owned_executor(tmp_path, monkeypatch):
    """A direct `/model <name>` switch must route switch_model() through
    the runner-owned executor so a models.dev fetch cannot freeze the event
    loop or depend on the loop's default executor (#20525)."""

    from hermes_cli.model_switch import ModelSwitchResult

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        yaml.safe_dump(
            {"model": {"default": "gpt-5.4", "provider": "openrouter"}}
        ),
        encoding="utf-8",
    )

    import gateway.run as gateway_run

    monkeypatch.setattr(gateway_run, "_hermes_home", hermes_home)
    monkeypatch.setattr(
        GatewayRunner,
        "_resolve_profile_home_for_source",
        lambda _runner, _source: hermes_home,
    )

    # Fail the switch so the handler returns before _finish_switch (which needs
    # full runner state) — we only care that the offload happened.
    offloaded = []

    def _fake_switch(**kwargs):
        offloaded.append(threading.current_thread())
        return ModelSwitchResult(success=False, error_message="nope")

    monkeypatch.setattr("hermes_cli.model_switch.switch_model", _fake_switch)

    monkeypatch.setattr(
        asyncio,
        "to_thread",
        lambda *args, **kwargs: pytest.fail("unexpected default-executor fallback"),
    )
    runner = _make_runner()
    assert runner._resolve_profile_home_for_source(_make_event().source) == hermes_home
    try:
        result = await runner._handle_model_command(_make_event("/model gpt-5.4"))
    finally:
        runner._shutdown_executor()

    assert offloaded
    assert all(t is not threading.main_thread() for t in offloaded)
    assert all(t.name.startswith("hermes-gateway") for t in offloaded)
    assert result is not None and "nope" in result
