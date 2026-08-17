from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


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


def test_loader_and_renderer_are_full_and_deterministic(tmp_path: Path) -> None:
    from agent.prompt_profiles import get_profile, load_policy_core, render_profile

    core_path = tmp_path / "SOUL.md"
    adapter_path = tmp_path / "adapter.md"
    core_path.write_bytes(b"policy\r\n<!-- REQ:one type:constraint scope:universal gate:g -->\r\n")
    adapter_path.write_bytes(b"adapter\r\n")

    core = load_policy_core(core_path)
    production_core = load_policy_core("/home/linux/.hermes/SOUL.md")
    rendered_1 = render_profile(
        get_profile("openai-codex", "gpt-5.6-sol"),
        core=production_core,
        adapter_path=adapter_path,
    )
    rendered_2 = render_profile(
        get_profile("openai-codex", "gpt-5.6-sol"),
        core=production_core,
        adapter_path=adapter_path,
    )

    assert core == "policy\n<!-- REQ:one type:constraint scope:universal gate:g -->\n"
    assert rendered_1 == rendered_2
    assert rendered_1.stable.startswith(production_core)
    assert "adapter\n" in rendered_1.stable
    assert "TRUNCATED" not in rendered_1.stable
    assert rendered_1.cache_identity[-1] == rendered_1.stable_sha256
    assert rendered_1.manifest["canonical_core_sha256"] == rendered_1.canonical_core_sha256


def test_renderer_rejects_truth_reversal_for_every_core_entrypoint(tmp_path: Path) -> None:
    from agent.prompt_profiles import PromptProfileError, get_profile, load_policy_core, render_profile

    approved = load_policy_core("/home/linux/.hermes/SOUL.md")
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


def test_render_identity_is_named_as_stable_not_final_prompt_hash() -> None:
    from agent.prompt_profiles import get_profile, render_profile

    rendered = render_profile(get_profile("openai-codex", "gpt-5.6-sol"))
    assert rendered.manifest["stable_render_sha256"] == rendered.stable_sha256
    assert "final_prompt_sha256" not in rendered.manifest


def test_provider_counters_use_exact_installed_tokenizers() -> None:
    from agent.prompt_profiles import get_token_counter

    counter = get_token_counter("openai-codex", "gpt-5.6-sol")
    assert counter.tokenizer_id == "o200k_base"
    assert counter.count_text("hello") == 1
    assert counter.count_text("<|endoftext|>") == 7

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


def test_admission_uses_effective_window_and_reserves() -> None:
    from agent.prompt_profiles import evaluate_admission, get_profile

    spec = get_profile("openai-codex", "gpt-5.6-sol")
    admitted = evaluate_admission(
        spec,
        runtime_window=272_000,
        policy_core_tokens=20_000,
        fixed_tokens=48_000,
        conversation_tokens=160_000,
        requested_output_tokens=32_000,
    )
    assert admitted.effective_window == 257_000
    assert admitted.admitted is True

    rejected = evaluate_admission(
        spec,
        runtime_window=272_000,
        policy_core_tokens=20_000,
        fixed_tokens=48_001,
        conversation_tokens=160_000,
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
