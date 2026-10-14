"""Explicit auxiliary pins must not discover another credentialed provider."""

from unittest.mock import MagicMock, patch

import pytest

from agent import auxiliary_client as auxiliary


TASKS = (
    "vision", "web_extract", "compression", "skills_hub", "approval", "mcp",
    "title_generation", "session_search", "flush_memories",
)


@pytest.mark.parametrize("task", TASKS)
def test_explicit_task_pin_survives_config_resolution(task):
    config = {"auxiliary": {task: {"provider": "openai-codex", "model": "gpt-configured-test"}}}
    with patch("hermes_cli.config.load_config", return_value=config):
        provider, model, base_url, api_key, mode = auxiliary._resolve_task_provider_model(task)
    assert (provider, model) == ("openai-codex", "gpt-configured-test")
    assert base_url is None and api_key is None and mode is None


@pytest.mark.parametrize("task", TASKS)
def test_explicit_main_pin_does_not_discover_other_providers_on_capacity_failure(task):
    config = {"auxiliary": {task: {"provider": "openai-codex", "model": "gpt-configured-test"}}}
    client = MagicMock()
    client.base_url = "https://chatgpt.com/backend-api/codex"
    client.api_key = "synthetic"
    error = RuntimeError("Payment Required")
    error.status_code = 402
    client.chat.completions.create.side_effect = error
    with (
        patch("hermes_cli.config.load_config", return_value=config),
        patch.object(auxiliary, "_read_main_provider", return_value="openai-codex"),
        patch.object(auxiliary, "_read_main_model", return_value="gpt-configured-test"),
        patch.object(auxiliary, "_get_cached_client", return_value=(client, "gpt-configured-test")),
        patch.object(auxiliary, "resolve_vision_provider_client", return_value=("openai-codex", client, "gpt-configured-test")),
        patch.object(auxiliary, "_recoverable_pool_provider", return_value=None),
        patch.object(auxiliary, "_mark_provider_unhealthy"),
        patch.object(auxiliary, "_get_provider_chain", side_effect=AssertionError("unexpected provider discovery")) as discovery,
    ):
        with pytest.raises(RuntimeError, match="Payment Required"):
            auxiliary.call_llm(task=task, messages=[{"role": "user", "content": "synthetic"}])
    discovery.assert_not_called()
    client.chat.completions.create.assert_called_once()
