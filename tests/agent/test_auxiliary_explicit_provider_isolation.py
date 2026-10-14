"""Exercise real task/client routing; only transport/auth boundaries are mocked."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agent import auxiliary_client as auxiliary


TASKS = (
    "vision", "web_extract", "compression", "skills_hub", "approval", "mcp",
    "title_generation", "session_search", "flush_memories",
)
MODEL = "gpt-configured-test"


@pytest.fixture
def explicit_config(monkeypatch):
    config = {"model": {"provider": "openai-codex", "default": MODEL},
              "auxiliary": {task: {"provider": "openai-codex", "model": MODEL} for task in TASKS}}
    config["auxiliary"]["transient_retries"] = 0
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: config)
    monkeypatch.setattr(auxiliary, "_read_main_provider", lambda: "openai-codex")
    monkeypatch.setattr(auxiliary, "_read_main_model", lambda: MODEL)
    monkeypatch.setattr(auxiliary, "_peek_pool_entry", lambda *_: None)
    monkeypatch.setattr(auxiliary, "_recoverable_pool_provider", lambda *_, **__: None)
    monkeypatch.setattr(auxiliary, "_refresh_provider_credentials", lambda *_: False)
    monkeypatch.setattr(auxiliary, "_mark_provider_unhealthy", MagicMock())
    monkeypatch.setattr(auxiliary, "_client_cache", {})
    monkeypatch.setattr(auxiliary, "_aux_unhealthy_until", {})
    monkeypatch.setattr(auxiliary, "_to_async_client", lambda client, model, **_: (client, model))
    return config


def invoke(task, async_mode):
    kwargs = {"task": task, "messages": [{"role": "user", "content": "synthetic"}]}
    return asyncio.run(auxiliary.async_call_llm(**kwargs)) if async_mode else auxiliary.call_llm(**kwargs)


def fake_client(error, async_mode):
    create = AsyncMock(side_effect=error) if async_mode else MagicMock(side_effect=error)
    return SimpleNamespace(base_url="https://chatgpt.com/backend-api/codex", api_key="synthetic",
                           chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


@pytest.mark.parametrize("task", TASKS)
def test_explicit_task_pin_survives_config_resolution(task, explicit_config):
    provider, model, base_url, api_key, mode = auxiliary._resolve_task_provider_model(task)
    assert (provider, model) == ("openai-codex", MODEL)
    assert base_url is None and api_key is None and mode is None


@pytest.mark.parametrize("task", TASKS)
@pytest.mark.parametrize("async_mode", [False, True])
@pytest.mark.parametrize("status", [401, 402, 429, "timeout"])
def test_explicit_main_pin_does_not_discover_other_providers_on_failure(task, async_mode, status, explicit_config):
    error = TimeoutError("synthetic timeout") if status == "timeout" else RuntimeError("synthetic provider failure")
    if status != "timeout":
        error.status_code = status
    client = fake_client(error, async_mode)
    with (
        patch.object(auxiliary, "_build_codex_client", return_value=(client, MODEL)) as build,
        patch.object(auxiliary, "resolve_provider_client", wraps=auxiliary.resolve_provider_client) as resolve,
        patch.object(auxiliary, "_get_provider_chain", side_effect=AssertionError("unexpected provider discovery")) as discovery,
    ):
        with pytest.raises(type(error), match="synthetic"):
            invoke(task, async_mode)
    discovery.assert_not_called()
    assert resolve.call_count >= 1
    assert all(call.args[:2] == ("openai-codex", MODEL) for call in resolve.call_args_list)
    assert all(call.args == (MODEL,) for call in build.call_args_list)
    assert client.chat.completions.create.call_count >= 1


@pytest.mark.parametrize("async_mode", [False, True])
def test_unavailable_explicit_vision_provider_does_not_fall_into_auto_discovery(async_mode, explicit_config):
    with (
        patch.object(auxiliary, "_build_codex_client", return_value=(None, None)),
        patch.object(auxiliary, "resolve_provider_client", wraps=auxiliary.resolve_provider_client) as resolve,
        patch.object(auxiliary, "_try_openrouter", side_effect=AssertionError("unapproved aggregator")) as other,
    ):
        with pytest.raises(RuntimeError, match="No LLM provider configured"):
            invoke("vision", async_mode)
    other.assert_not_called()
    assert resolve.call_count == 1
    assert resolve.call_args.args[:2] == ("openai-codex", MODEL)


@pytest.mark.parametrize("async_mode", [False, True])
def test_quarantined_configured_fallback_does_not_authorize_unconfigured_provider(async_mode, explicit_config):
    task = "web_extract"
    fallback_spec = {"provider": "configured-secondary", "model": "secondary-model"}
    explicit_config["auxiliary"][task]["fallback_chain"] = [fallback_spec]
    primary_error = RuntimeError("primary capacity unavailable")
    primary_error.status_code = 402
    fallback_error = RuntimeError("Invalid bearer token")
    fallback_error.status_code = 401
    client = fake_client(primary_error, async_mode)
    fallback = fake_client(fallback_error, async_mode)
    fallback.base_url = "https://secondary.example/v1"
    with (
        patch.object(auxiliary, "_build_codex_client", return_value=(client, MODEL)),
        patch.object(auxiliary, "_resolve_fallback_entry", return_value=(fallback, "secondary-model")) as resolve_fallback,
        patch.object(auxiliary, "_get_provider_chain", side_effect=AssertionError("unexpected provider discovery")) as discovery,
    ):
        with pytest.raises(RuntimeError, match="primary capacity unavailable"):
            invoke(task, async_mode)
    resolve_fallback.assert_called_once_with(fallback_spec)
    discovery.assert_not_called()
    fallback.chat.completions.create.assert_called_once()
