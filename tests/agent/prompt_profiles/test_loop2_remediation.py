from __future__ import annotations

import threading
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from tests.agent.prompt_profiles.test_systems_contract import (
    _install_parent_supported_core,
)


def _fake_deepseek_transformers(tmp_path: Path, monkeypatch, tokenizer: MagicMock):
    """Provide deterministic hash-verified tokenizer assets for this test."""
    from agent.prompt_profiles.tokenizer import DeepSeekTokenCounter

    assets = {
        "tokenizer.json": b"loop2 tokenizer asset",
        "tokenizer_config.json": b"loop2 tokenizer config asset",
    }
    for name, content in assets.items():
        (tmp_path / name).write_bytes(content)
    monkeypatch.setattr(
        DeepSeekTokenCounter,
        "asset_sha256",
        {name: hashlib.sha256(content).hexdigest() for name, content in assets.items()},
    )
    cached_file = MagicMock(
        side_effect=lambda _model, name, **_: str(tmp_path / name)
    )
    return SimpleNamespace(
        __version__="test",
        AutoTokenizer=SimpleNamespace(
            from_pretrained=MagicMock(return_value=tokenizer)
        ),
        utils=SimpleNamespace(
            hub=SimpleNamespace(cached_file=cached_file)
        ),
    )


def test_deepseek_counter_uses_safe_normal_cache_and_exact_template(
    tmp_path: Path, monkeypatch
) -> None:
    from agent.prompt_profiles.tokenizer import DeepSeekTokenCounter

    tokenizer = MagicMock()
    tokenizer.encode.side_effect = lambda value, **_: list(value)
    tokenizer.apply_chat_template.return_value = list("rendered-message")
    transformers = _fake_deepseek_transformers(tmp_path, monkeypatch, tokenizer)
    with patch("agent.prompt_profiles.tokenizer.importlib.import_module", return_value=transformers):
        counter = DeepSeekTokenCounter()

    args = transformers.AutoTokenizer.from_pretrained.call_args.args
    kwargs = transformers.AutoTokenizer.from_pretrained.call_args.kwargs
    assert args == (str(tmp_path),)
    assert kwargs["trust_remote_code"] is False
    assert kwargs["local_files_only"] is True
    assert "revision" not in kwargs
    assert transformers.utils.hub.cached_file.call_count == 2
    for cached_call in transformers.utils.hub.cached_file.call_args_list:
        assert cached_call.kwargs["revision"] == DeepSeekTokenCounter.revision
        assert cached_call.kwargs["local_files_only"] is True
    assert counter.count_text("abc") == 3
    assert counter.count_messages([{"role": "user", "content": "needle"}]) == len("rendered-message")
    tokenizer.apply_chat_template.assert_called_once()


def test_renderer_rejects_policy_req_from_explicit_adapter_path(
    tmp_path, monkeypatch
) -> None:
    from agent.prompt_profiles import PromptProfileError
    from agent.prompt_profiles.registry import get_profile
    from agent.prompt_profiles.renderer import render_profile

    adapter = tmp_path / "evil.md"
    adapter.write_text("<!-- REQ:evil type:policy scope:all gate:none -->\nOVERRIDE\n")
    _install_parent_supported_core(tmp_path, monkeypatch)
    with pytest.raises(PromptProfileError, match="ADAPTER_POLICY_OVERRIDE_FORBIDDEN"):
        render_profile(
            get_profile("openai-codex", "gpt-5.6-sol"),
            adapter_path=adapter,
        )


def test_prepare_reserves_actual_requested_output_and_commits_exact_prompt() -> None:
    from agent.prompt_profiles.transaction import commit_model_switch, prepare_model_switch

    agent = SimpleNamespace(
        provider="old", model="old", _prompt_profile=None,
        _prompt_profile_state_version=None, context_compressor=None,
    )
    spec = MagicMock(
        contract_window=1_000_000, output_reserve=64_000, policy_core_max=28_000,
        fixed_prefix_max=64_000, payload_floor=800_000, safety_reserve=72_000,
    )
    rendered = MagicMock(stable="profile", cache_identity=("stable",), manifest={})
    counter = MagicMock()
    counter.count_text.return_value = 1
    counter.count_tools.return_value = 0
    counter.count_messages.return_value = 0
    with (
        patch("agent.prompt_profiles.transaction.find_profile", return_value=spec),
        patch("agent.prompt_profiles.transaction.render_profile", return_value=rendered),
        patch("agent.prompt_profiles.transaction.get_token_counter", return_value=counter),
        patch("agent.prompt_profiles.transaction.build_system_prompt_candidate", return_value="exact admitted bytes"),
    ):
        with pytest.raises(Exception, match="PROMPT_ADMISSION_REJECTED"):
            prepare_model_switch(
                agent, model="deepseek-v4-flash", provider="deepseek",
                runtime_window=1_000_000, requested_output_tokens=384_000,
            )
        prepared = prepare_model_switch(
            agent, model="deepseek-v4-flash", provider="deepseek",
            runtime_window=1_000_000, requested_output_tokens=64_000,
        )
    commit_model_switch(agent, prepared)
    assert agent._cached_system_prompt == "exact admitted bytes"
    assert agent._persisted_system_prompt_sha256 == hashlib.sha256(b"exact admitted bytes").hexdigest()
    assert prepared.rendered_profile.cache_identity == ("stable",)


def test_switch_reserves_largest_live_output_cap() -> None:
    from agent.agent_runtime_helpers import switch_model

    agent = SimpleNamespace(
        provider="old", model="old", max_tokens=128_000,
        _ephemeral_max_output_tokens=384_000,
        context_compressor=SimpleNamespace(max_tokens=256_000),
        tools=(),
    )
    with (
        patch("agent.prompt_profiles.transaction.prepare_model_switch") as prepare,
        patch("agent.prompt_profiles.transaction.commit_model_switch"),
        patch("agent.agent_runtime_helpers._switch_model_runtime"),
    ):
        prepare.return_value = MagicMock()
        switch_model(agent, "new", "provider")
    assert prepare.call_args.kwargs["requested_output_tokens"] == 384_000


def test_persisted_prompt_rejects_body_tamper_with_out_of_band_digest() -> None:
    from agent.conversation_loop import _stored_prompt_matches_runtime

    body = "Profile-ID: p\nCanonical-Core-SHA256: c\nAdapter-SHA256: a\nStable-Render-SHA256: r\nModel: m\nProvider: pvd\nBODY"
    agent = SimpleNamespace(
        provider="pvd", model="m", _prompt_profile=("pvd", "m", "p", "c", "a", "r"),
        _persisted_system_prompt_sha256=hashlib.sha256(body.encode()).hexdigest(),
    )
    assert _stored_prompt_matches_runtime(agent, body)
    assert not _stored_prompt_matches_runtime(agent, body + " TAMPER")


def test_switch_journal_recovery_rejects_generation_conflict_and_secret(tmp_path) -> None:
    from agent.prompt_profiles.transaction import SwitchJournal

    journal = SwitchJournal(tmp_path / "switch.json", secret_values=("canary-secret",))
    payload = {"transaction_id": "tx", "session_id": "session", "old": {"provider": "old", "model": "old"}, "new": {"provider": "new", "model": "next"}}
    journal.transition("PREPARED", generation=4, payload=payload)
    with pytest.raises(Exception, match="GENERATION_CONFLICT"):
        journal.transition("CONFIG_APPLIED", generation=3, payload=payload)
    with pytest.raises(Exception, match="SECRET_BOUNDARY_VIOLATION"):
        journal.transition("CONFIG_APPLIED", generation=4, payload={**payload, "transaction_id": "canary-secret"})
    recovered = journal.recover(expected_generation=4)
    assert recovered["state"] == "PREPARED"
    assert json.loads((tmp_path / "switch.json").read_text())["generation"] == 4


def test_deepseek_counter_fails_closed_for_malformed_template(
    tmp_path: Path, monkeypatch
) -> None:
    from agent.prompt_profiles import TokenizerUnavailable
    from agent.prompt_profiles.tokenizer import DeepSeekTokenCounter

    tokenizer = MagicMock()
    tokenizer.apply_chat_template.side_effect = ValueError("bad template")
    transformers = _fake_deepseek_transformers(tmp_path, monkeypatch, tokenizer)
    with patch("agent.prompt_profiles.tokenizer.importlib.import_module", return_value=transformers):
        counter = DeepSeekTokenCounter()
    with pytest.raises(TokenizerUnavailable, match="chat template"):
        counter.count_messages([{"role": "user", "content": "needle"}])


def test_candidate_prompt_counts_entire_eventual_prompt_without_mutation() -> None:
    from agent.system_prompt import build_system_prompt_candidate

    agent = SimpleNamespace(_cached_system_prompt="live", _system_prompt_breakdown={"live": True})
    rendered = SimpleNamespace(stable="canonical + adapter")
    with patch("agent.system_prompt.build_system_prompt", side_effect=lambda candidate, system_message=None: (
        candidate._prompt_profile_rendered.stable + "\n\nuniversal\n\nskills\n\nmemory\n\ncontext\n\nenvironment\n\nvolatile"
    )):
        candidate = build_system_prompt_candidate(agent, rendered)

    assert candidate.endswith("volatile")
    assert agent._cached_system_prompt == "live"
    assert agent._system_prompt_breakdown == {"live": True}
    assert not hasattr(agent, "_prompt_profile_rendered")


def test_persisted_prompt_requires_complete_profile_identity() -> None:
    from agent.conversation_loop import _stored_prompt_matches_runtime

    identity = ("openai-codex", "gpt-5.6-sol", "profile-v1", "core", "adapter", "render")
    agent = SimpleNamespace(provider="openai-codex", model="gpt-5.6-sol", _prompt_profile=identity)
    good = (
        "Profile-ID: profile-v1\nCanonical-Core-SHA256: core\nAdapter-SHA256: adapter\n"
        "Stable-Render-SHA256: render\nModel: gpt-5.6-sol\nProvider: openai-codex"
    )
    assert not _stored_prompt_matches_runtime(agent, good)
    agent._persisted_system_prompt_sha256 = hashlib.sha256(good.encode()).hexdigest()
    assert _stored_prompt_matches_runtime(agent, good)
    assert not _stored_prompt_matches_runtime(agent, good.replace("core", "tampered", 1))
    assert not _stored_prompt_matches_runtime(agent, "Model: gpt-5.6-sol\nProvider: openai-codex")


def test_commit_compensates_staged_durable_mutations_and_closes_candidate() -> None:
    from agent.prompt_profiles.transaction import (
        DurableMutation,
        PreparedModelSwitch,
        commit_model_switch,
    )

    events: list[str] = []
    old_client = MagicMock()
    candidate_client = MagicMock()
    agent = SimpleNamespace(provider="old", model="old", client=old_client, _prompt_profile=None)
    prepared = PreparedModelSwitch(
        provider="new", model="new", api_key="", base_url="", api_mode="",
        profile=None, rendered_profile=None, admission=None, effective_window=None,
        old_identity=("old", "old", None), old_state_version=None, candidate_client=candidate_client,
        runtime_updates={"provider": "new", "model": "new", "client": candidate_client},
        durable_mutations=(
            DurableMutation(lambda: events.append("apply-1"), lambda: events.append("undo-1"), "one"),
            DurableMutation(lambda: (_ for _ in ()).throw(RuntimeError("persist failed")), lambda: None, "two"),
        ),
    )
    with pytest.raises(RuntimeError, match="persist failed"):
        commit_model_switch(agent, prepared)
    assert events == ["apply-1", "undo-1"]
    assert agent.provider == "old" and agent.model == "old" and agent.client is old_client
    candidate_client.close.assert_called_once()


def test_prepare_uses_explicit_cli_history_and_stages_candidate_before_commit() -> None:
    from agent.prompt_profiles.transaction import prepare_model_switch

    agent = SimpleNamespace(provider="old", model="old", _prompt_profile=None, conversation_history=[])
    counter = MagicMock()
    counter.count_text.return_value = 10
    counter.count_tools.return_value = 5
    counter.count_messages.return_value = 123
    candidate_client = MagicMock()
    with (
        patch("agent.prompt_profiles.transaction.find_profile", return_value=MagicMock(
            contract_window=257_000, output_reserve=1, policy_core_max=1000,
            fixed_prefix_max=1000, payload_floor=1, safety_reserve=1,
        )),
        patch("agent.prompt_profiles.transaction.render_profile", return_value=MagicMock(stable="profile")),
        patch("agent.prompt_profiles.transaction.get_token_counter", return_value=counter),
        patch("agent.prompt_profiles.transaction.build_system_prompt_candidate", return_value="full prompt"),
    ):
        prepared = prepare_model_switch(
            agent, model="new", provider="new", runtime_window=1000,
            messages=({"role": "user", "content": "cli history"},), tools=(),
            candidate_client_factory=lambda: candidate_client,
        )
    counter.count_messages.assert_called_once_with(({"role": "user", "content": "cli history"},))
    assert prepared.candidate_client is candidate_client
    assert prepared.final_prompt == "full prompt"


@pytest.mark.parametrize("tokens,needle", [(160_000, "openai-needle"), (800_000, "deepseek-needle")])
def test_acceptance_needle_fixture_is_deterministic_label_blind(tokens: int, needle: str) -> None:
    from agent.prompt_profiles.acceptance import build_needle_case

    left = build_needle_case(token_target=tokens, needle=needle, seed=2977)
    right = build_needle_case(token_target=tokens, needle=needle, seed=2977)
    assert left == right
    assert left.request_id
    assert needle in left.payload
    assert "candidate" not in left.label.lower() and "baseline" not in left.label.lower()


def test_seven_prompt_gate_contract_names_are_exact() -> None:
    from agent.prompt_profiles.acceptance import PROMPT_GATES

    assert PROMPT_GATES == (
        "prompt_context_budget", "prompt_integrity_manifest", "prompt_req_marker_survival",
        "prompt_model_variant_sync", "prompt_payload_headroom", "prompt_behavioral_parity",
        "prompt_gate_registry_sync",
    )


def test_candidate_client_construction_finishes_before_live_or_durable_mutation() -> None:
    from agent.agent_runtime_helpers import switch_model
    from agent.prompt_profiles.transaction import DurableMutation

    events: list[str] = []
    old_client = MagicMock(name="old-client")
    new_client = MagicMock(name="new-client")
    agent = SimpleNamespace(
        provider="old-provider", model="old-model", client=old_client,
        _prompt_profile=None, _prompt_profile_state_version=None,
        _transport_cache={}, _client_kwargs={}, _primary_runtime={},
        _fallback_chain=[], context_compressor=None, tools=(),
    )

    def construct_on_candidate(candidate, *args, **kwargs):
        assert candidate is not agent
        assert (agent.provider, agent.model, agent.client) == (
            "old-provider", "old-model", old_client
        )
        events.append("candidate-constructed")
        candidate.provider = "new-provider"
        candidate.model = "new-model"
        candidate.client = new_client

    durable = DurableMutation(
        lambda: events.append("durable-applied"),
        lambda: events.append("durable-compensated"),
        "ordering probe",
    )
    with patch("agent.agent_runtime_helpers._switch_model_runtime", side_effect=construct_on_candidate):
        switch_model(agent, "new-model", "new-provider", durable_mutations=(durable,))

    assert events == ["candidate-constructed", "durable-applied"]
    assert (agent.provider, agent.model, agent.client) == (
        "new-provider", "new-model", new_client
    )


def test_cli_global_config_and_runtime_are_compensated_on_commit_failure(monkeypatch) -> None:
    import cli as cli_mod
    from hermes_cli.model_switch import ModelSwitchResult

    config_writes: list[tuple[str, object]] = []
    monkeypatch.setattr(cli_mod, "save_config_value", lambda key, value: config_writes.append((key, value)))
    monkeypatch.setattr(cli_mod, "_cprint", lambda *args, **kwargs: None)
    result = ModelSwitchResult(
        success=True, new_model="new-model", target_provider="new-provider",
        provider_changed=True, api_key="new-key", base_url="https://new.invalid",
        api_mode="chat_completions", warning_message="", provider_label="New",
        resolved_via_alias=False, capabilities=None, model_info=None, is_global=True,
    )

    class FailingAgent:
        _config_context_length = None

        def switch_model(self, **kwargs):
            mutation = kwargs["durable_mutations"][0]
            mutation.apply()
            mutation.compensate()
            raise RuntimeError("late commit failure")

    cli = SimpleNamespace(
        agent=FailingAgent(), conversation_history=[{"role": "user", "content": "resume"}],
        model="old-model", provider="old-provider", requested_provider="old-provider",
        _explicit_api_key="old-explicit-key", _explicit_base_url="https://old.invalid",
        api_key="old-key", base_url="https://old.invalid", api_mode="old-mode",
        _pending_model_switch_note="",
    )
    cli_mod.HermesCLI._apply_model_switch_result(cli, result, True)

    assert (cli.model, cli.provider, cli.api_key, cli.base_url, cli.api_mode) == (
        "old-model", "old-provider", "old-key", "https://old.invalid", "old-mode"
    )
    assert config_writes == [
        ("model.default", "new-model"), ("model.provider", "new-provider"),
        ("model.default", "old-model"), ("model.provider", "old-provider"),
    ]


def test_cli_without_agent_applies_durable_switch(monkeypatch) -> None:
    import cli as cli_mod
    from hermes_cli.model_switch import ModelSwitchResult

    writes = []
    monkeypatch.setattr(cli_mod, "save_config_value", lambda key, value: writes.append((key, value)))
    monkeypatch.setattr(cli_mod, "_cprint", lambda *args, **kwargs: None)
    result = ModelSwitchResult(
        success=True, new_model="new", target_provider="next", provider_changed=True,
        api_key="", base_url="", api_mode="", warning_message="", provider_label="Next",
        resolved_via_alias=False, capabilities=None, model_info=None, is_global=True,
    )
    cli = SimpleNamespace(
        agent=None, conversation_history=[], model="old", provider="prior",
        requested_provider="prior", _explicit_api_key="", _explicit_base_url="",
        api_key="", base_url="", api_mode="", _pending_model_switch_note="",
    )
    cli_mod.HermesCLI._apply_model_switch_result(cli, result, True)
    assert (cli.model, cli.provider) == ("new", "next")
    assert writes == [("model.default", "new"), ("model.provider", "next")]


@pytest.mark.asyncio
async def test_gateway_db_session_override_and_config_are_compensated(monkeypatch) -> None:
    from gateway.slash_commands import GatewaySlashCommandsMixin
    from hermes_cli.model_switch import ModelSwitchResult

    source = SimpleNamespace(platform="test", chat_id="chat", user_id="user")
    event = SimpleNamespace(
        source=source,
        get_command_args=lambda: "new-model --provider new-provider --global",
    )
    result = ModelSwitchResult(
        success=True, new_model="new-model", target_provider="new-provider",
        provider_changed=True, api_key="new-key", base_url="https://new.invalid",
        api_mode="chat_completions", warning_message="", provider_label="New",
        resolved_via_alias=False, capabilities=None, model_info=None, is_global=True,
    )
    old_override = {"model": "old-model", "provider": "old-provider"}
    old_cfg = {"model": {"default": "old-model", "provider": "old-provider"}}
    config_writes: list[dict] = []
    session_db = SimpleNamespace(update_session_model=AsyncMock())
    session_store = SimpleNamespace(
        get_or_create_session=AsyncMock(return_value=SimpleNamespace(session_id="db-session")),
        set_model_override=AsyncMock(),
    )

    class FailingAgent:
        conversation_history = [{"role": "user", "content": "resume"}]

        def switch_model(self, **kwargs):
            mutation = kwargs["durable_mutations"][0]
            mutation.apply()
            mutation.compensate()
            raise RuntimeError("late gateway failure")

    runner = SimpleNamespace(
        adapters={}, _session_model_overrides={"session-key": dict(old_override)},
        _pending_model_notes={"session-key": "old-note"},
        _agent_cache={"session-key": (FailingAgent(),)}, _agent_cache_lock=threading.Lock(),
        _session_db=session_db, async_session_store=session_store,
        _normalize_source_for_session_key=lambda value: value,
        _session_key_for_source=lambda value: "session-key",
        _evict_cached_agent=lambda key: pytest.fail("failed switch must not evict"),
    )
    monkeypatch.setattr("gateway.run._load_gateway_config", lambda: old_cfg)
    monkeypatch.setattr("gateway.slash_commands._model_switch_skew_guard", lambda: None)
    monkeypatch.setattr("hermes_cli.model_switch.switch_model", lambda **kwargs: result)
    monkeypatch.setattr("hermes_cli.model_switch.resolve_display_context_length", lambda *a, **k: None)
    monkeypatch.setattr("hermes_cli.config.save_config", lambda cfg: config_writes.append(cfg))

    message = await GatewaySlashCommandsMixin._handle_model_command(runner, event)

    assert "late gateway failure" in message
    assert runner._session_model_overrides["session-key"] == old_override
    assert runner._pending_model_notes["session-key"] == "old-note"
    assert session_db.update_session_model.await_args_list == [
        call("db-session", "new-model"), call("db-session", "old-model")
    ]
    assert session_store.set_model_override.await_args_list == [
        call("session-key", {
            "model": "new-model", "provider": "new-provider", "api_key": "new-key",
            "base_url": "https://new.invalid", "api_mode": "chat_completions",
        }),
        call("session-key", old_override),
    ]
    assert config_writes[0]["model"]["default"] == "new-model"
    assert config_writes[-1] == old_cfg


@pytest.mark.asyncio
async def test_gateway_no_cached_agent_still_commits_durable_session_state(monkeypatch) -> None:
    from gateway.slash_commands import GatewaySlashCommandsMixin
    from hermes_cli.model_switch import ModelSwitchResult

    source = SimpleNamespace(platform="test", chat_id="chat", user_id="user")
    event = SimpleNamespace(source=source, get_command_args=lambda: "new-model --provider new-provider --session")
    result = ModelSwitchResult(
        success=True, new_model="new-model", target_provider="new-provider",
        provider_changed=True, api_key="runtime-only-secret", base_url="https://new.invalid",
        api_mode="chat_completions", warning_message="", provider_label="New",
        resolved_via_alias=False, capabilities=None, model_info=None, is_global=False,
    )
    entry = SimpleNamespace(session_id="db-session", was_auto_reset=True)
    session_db = SimpleNamespace(update_session_model=AsyncMock())
    session_store = SimpleNamespace(
        get_or_create_session=AsyncMock(return_value=entry), set_model_override=AsyncMock(),
    )
    evicted = []
    runner = SimpleNamespace(
        adapters={}, _session_model_overrides={}, _pending_model_notes={}, _agent_cache={},
        _agent_cache_lock=threading.Lock(), _session_db=session_db,
        async_session_store=session_store,
        _normalize_source_for_session_key=lambda value: value,
        _session_key_for_source=lambda value: "session-key",
        _evict_cached_agent=lambda key: evicted.append(key),
    )
    monkeypatch.setattr("gateway.run._load_gateway_config", lambda: {"model": {}})
    monkeypatch.setattr("gateway.slash_commands._model_switch_skew_guard", lambda: None)
    monkeypatch.setattr("hermes_cli.model_switch.switch_model", lambda **kwargs: result)
    monkeypatch.setattr("hermes_cli.model_switch.resolve_display_context_length", lambda *a, **k: None)

    message = await GatewaySlashCommandsMixin._handle_model_command(runner, event)

    assert "new-model" in message
    assert entry.was_auto_reset is False
    session_db.update_session_model.assert_awaited_once_with("db-session", "new-model")
    session_store.set_model_override.assert_awaited_once()
    assert runner._session_model_overrides["session-key"]["model"] == "new-model"
    assert evicted == ["session-key"]


def test_tui_override_history_db_and_config_are_compensated(monkeypatch) -> None:
    from tui_gateway import server
    from hermes_cli.model_switch import ModelSwitchResult

    result = ModelSwitchResult(
        success=True, new_model="new-model", target_provider="new-provider",
        provider_changed=True, api_key="new-key", base_url="https://new.invalid",
        api_mode="chat_completions", warning_message="", provider_label="New",
        resolved_via_alias=False, capabilities=None, model_info=None, is_global=True,
    )
    db = MagicMock()
    db.get_session.return_value = {
        "model_config": "old-config", "model": "old-model", "system_prompt": "old-prompt"
    }

    class FailingAgent:
        model = "old-model"
        provider = "old-provider"
        base_url = "https://old.invalid"
        api_key = "old-key"
        api_mode = "old-mode"
        _config_context_length = None
        _session_db = db
        session_id = "db-session"

        def switch_model(self, **kwargs):
            from agent.prompt_profiles.transaction import DurableMutation, PreparedModelSwitch, commit_model_switch
            failure = DurableMutation(
                lambda: (_ for _ in ()).throw(RuntimeError("late TUI failure")),
                lambda: None,
                "injected post-persistence failure",
            )
            prepared = PreparedModelSwitch(
                provider=kwargs["new_provider"], model=kwargs["new_model"],
                api_key="", base_url="", api_mode="", profile=None,
                rendered_profile=None, admission=None, effective_window=None,
                old_identity=(self.provider, self.model, None), old_state_version=None,
                runtime_updates={"provider": kwargs["new_provider"], "model": kwargs["new_model"]},
                durable_mutations=tuple(kwargs["durable_mutations"]) + (failure,),
            )
            return commit_model_switch(self, prepared)

    session = {
        "agent": FailingAgent(), "session_key": "session-key",
        "history": [{"role": "user", "content": "resume"}], "history_version": 7,
        "model_override": {"model": "old-model", "provider": "old-provider"},
    }
    config_writes: list[tuple[str, object]] = []
    monkeypatch.setattr("hermes_cli.model_switch.switch_model", lambda **kwargs: result)
    monkeypatch.setattr("hermes_cli.model_cost_guard.expensive_model_warning", lambda *a, **k: None)
    monkeypatch.setattr(server, "_load_cfg", lambda: {"model": {
        "default": "old-model", "provider": "old-provider", "base_url": "https://old.invalid"
    }})
    def persist_runtime(sess, strict=False):
        assert (sess["agent"].provider, sess["agent"].model) == ("new-provider", "new-model")
        sess.update(history_version=8)
    monkeypatch.setattr(server, "_persist_live_session_runtime", persist_runtime)
    monkeypatch.setattr(server, "_persist_live_session_system_prompt", lambda sess, strict=False: None)
    marker = MagicMock()
    monkeypatch.setattr(server, "_append_model_switch_marker", marker)
    monkeypatch.setattr(server, "_persist_model_switch", lambda value: config_writes.append(("new", value.new_model)))
    monkeypatch.setattr("cli.save_config_value", lambda key, value: config_writes.append((key, value)))

    with pytest.raises(ValueError, match="late TUI failure"):
        server._apply_model_switch("sid", session, "new-model --provider new-provider")

    assert session["model_override"] == {"model": "old-model", "provider": "old-provider"}
    assert session["history"] == [{"role": "user", "content": "resume"}]
    assert session["history_version"] == 7
    marker.assert_not_called()
    db.update_session_meta.assert_called_once_with("session-key", "old-config", "old-model")
    db.update_system_prompt.assert_called_once_with("db-session", "old-prompt")
    assert config_writes == [
        ("new", "new-model"),
        ("model.default", "old-model"),
        ("model.provider", "old-provider"),
        ("model.base_url", "https://old.invalid"),
    ]


def test_initial_profile_admission_receives_resumed_history() -> None:
    from agent.prompt_profiles.transaction import activate_initial_profile

    history = ({"role": "user", "content": "resumed-history"},)
    agent = SimpleNamespace(
        provider="openai-codex", model="gpt-5.6-sol", api_key="", base_url="",
        api_mode="", tools=(), _prompt_profile=None,
    )
    prepared = MagicMock()
    with (
        patch("agent.prompt_profiles.transaction.find_profile", return_value=MagicMock()),
        patch("agent.prompt_profiles.transaction.prepare_model_switch", return_value=prepared) as prepare,
        patch("agent.prompt_profiles.transaction.commit_model_switch") as commit,
    ):
        returned = activate_initial_profile(agent, messages=history)

    assert returned is prepared
    assert prepare.call_args.kwargs["messages"] == history
    commit.assert_called_once_with(agent, prepared)


def test_initial_profile_reserves_largest_output_cap() -> None:
    from agent.prompt_profiles.transaction import activate_initial_profile

    agent = SimpleNamespace(
        provider="openai-codex", model="gpt-5.6-sol", api_key="", base_url="",
        api_mode="", tools=(), _prompt_profile=None, max_tokens=384_000,
        context_compressor=SimpleNamespace(max_tokens=64_000),
    )
    prepared = MagicMock()
    with (
        patch("agent.prompt_profiles.transaction.find_profile", return_value=MagicMock()),
        patch("agent.prompt_profiles.transaction.prepare_model_switch", return_value=prepared) as prepare,
        patch("agent.prompt_profiles.transaction.commit_model_switch"),
    ):
        activate_initial_profile(agent)

    assert prepare.call_args.kwargs["requested_output_tokens"] == 384_000


def test_initial_profile_same_authority_applies_locally_without_new_generation() -> None:
    from agent.prompt_profiles.transaction import activate_initial_profile

    agent = SimpleNamespace(
        provider="openai-codex", model="gpt-5.6-sol", api_key="", base_url="",
        api_mode="", tools=(), _prompt_profile=None, session_id="session-id",
        hermes_home=Path("/unused"),
    )
    authoritative = {
        "generation": 7, "transaction_id": "committed",
        "provider": "openai-codex", "model": "gpt-5.6-sol",
    }
    prepared = MagicMock()
    with (
        patch("agent.prompt_profiles.transaction.recover_model_switches"),
        patch("agent.prompt_profiles.transaction._read_commit_authority", return_value=authoritative),
        patch("agent.prompt_profiles.transaction.find_profile", return_value=MagicMock()),
        patch("agent.prompt_profiles.transaction.prepare_model_switch", return_value=prepared) as prepare,
        patch("agent.prompt_profiles.transaction._apply_prepared_runtime") as apply_local,
        patch("agent.prompt_profiles.transaction.commit_model_switch") as commit,
        patch("agent.prompt_profiles.transaction.capture_model_switch_snapshot"),
    ):
        returned = activate_initial_profile(agent)

    assert returned is prepared
    assert prepare.call_args.kwargs["durable"] is False
    apply_local.assert_called_once_with(agent, prepared, None)
    commit.assert_not_called()
    assert agent._prompt_profile_state_version == 7


def test_initial_profile_reconciles_completed_authority_to_current_route() -> None:
    from agent.prompt_profiles.transaction import activate_initial_profile

    agent = SimpleNamespace(
        provider="deepseek", model="deepseek-v4-flash", api_key="", base_url="",
        api_mode="", tools=(), _prompt_profile=None, session_id="session-id",
        hermes_home=Path("/unused"),
    )
    authoritative = {
        "generation": 3, "transaction_id": "committed",
        "provider": "openai-codex", "model": "gpt-5.6-sol",
    }
    prepared = MagicMock()
    with (
        patch("agent.prompt_profiles.transaction.recover_model_switches"),
        patch("agent.prompt_profiles.transaction._read_commit_authority", return_value=authoritative),
        patch("agent.prompt_profiles.transaction.find_profile", return_value=MagicMock()),
        patch("agent.prompt_profiles.transaction.prepare_model_switch", return_value=prepared) as prepare,
        patch("agent.prompt_profiles.transaction.commit_model_switch") as commit,
    ):
        returned = activate_initial_profile(agent)

    assert returned is prepared
    assert prepare.call_args.kwargs["durable"] is True
    assert prepare.call_args.kwargs["journal_old_identity"] == (
        "openai-codex", "gpt-5.6-sol",
    )
    commit.assert_called_once_with(agent, prepared)


def test_missing_session_db_row_uses_file_backed_switch_authority(tmp_path) -> None:
    from agent.prompt_profiles.transaction import commit_model_switch
    from tests.agent.prompt_profiles.test_switch_transaction_durability import (
        _agent, _prepared,
    )

    class MissingSessionDB:
        def get_session(self, session_id):
            return None

        def get_model_switch_state(self, session_id):
            raise AssertionError("missing DB rows must use file authority")

        def compare_and_swap_model_switch(self, *args, **kwargs):
            raise AssertionError("missing DB rows must use file authority")

    agent = _agent(tmp_path)
    agent._session_db = MissingSessionDB()
    commit_model_switch(agent, _prepared(agent))

    state = json.loads(
        (tmp_path / "state/model_switch_state/session-2977.json").read_text()
    )
    assert (state["generation"], state["provider"], state["model"]) == (
        1, "provider", "new",
    )


def test_tui_model_switch_exception_redacts_credential_canary(monkeypatch, caplog) -> None:
    from tui_gateway import server
    from hermes_cli.model_switch import ModelSwitchResult

    canary = "sk-live-SYS2977-ROUND4-CANARY-123456789"
    result = ModelSwitchResult(
        success=True, new_model="new-model", target_provider="new-provider",
        provider_changed=True, api_key=canary, base_url="https://new.invalid",
        api_mode="chat_completions", warning_message="", provider_label="New",
        resolved_via_alias=False, capabilities=None, model_info=None, is_global=False,
    )
    agent = MagicMock()
    agent.model = "old-model"
    agent.provider = "old-provider"
    agent.base_url = "https://old.invalid"
    agent.api_key = "old-key"
    agent.api_mode = ""
    agent._config_context_length = None
    agent._session_db = None
    agent.switch_model.side_effect = RuntimeError(f"upstream URL apiKey={canary}")
    session = {
        "agent": agent, "session_key": "session-key", "history": [],
        "history_version": 0,
    }
    monkeypatch.setattr("hermes_cli.model_switch.switch_model", lambda **kwargs: result)
    monkeypatch.setattr("hermes_cli.model_cost_guard.expensive_model_warning", lambda *a, **k: None)
    monkeypatch.setattr(server, "_load_cfg", lambda: {"model": {}})
    monkeypatch.setattr(server, "_get_db", lambda: None)

    with caplog.at_level("WARNING"), pytest.raises(ValueError) as raised:
        server._apply_model_switch("sid", session, "new-model --provider new-provider")

    assert canary not in str(raised.value)
    assert canary not in caplog.text
    assert "apiKey=" not in str(raised.value)
    assert "apiKey=" not in caplog.text


def test_stale_persisted_prompt_identity_forces_fresh_rebuild() -> None:
    from agent.conversation_loop import _restore_or_build_system_prompt

    identity = ("openai-codex", "gpt-5.6-sol", "profile-v1", "core", "adapter", "render")
    stale = (
        "Profile-ID: profile-v1\nCanonical-Core-SHA256: stale-core\nAdapter-SHA256: adapter\n"
        "Stable-Render-SHA256: render\nModel: gpt-5.6-sol\nProvider: openai-codex"
    )
    db = MagicMock()
    db.get_session.return_value = {"system_prompt": stale}
    agent = MagicMock()
    agent._cached_system_prompt = None
    agent.session_id = "session-id"
    agent.model = "gpt-5.6-sol"
    agent.provider = "openai-codex"
    agent.platform = "cli"
    agent._prompt_profile = identity
    agent._session_db = db
    agent._build_system_prompt = MagicMock(return_value="fresh-profile-prompt")

    _restore_or_build_system_prompt(agent, None, [{"role": "user", "content": "resumed"}])

    assert agent._cached_system_prompt == "fresh-profile-prompt"
    agent._build_system_prompt.assert_called_once_with(None)
    db.update_system_prompt.assert_called_once_with("session-id", "fresh-profile-prompt")


def test_admission_counts_full_assembled_prompt_and_tool_schema() -> None:
    from agent.prompt_profiles.transaction import prepare_model_switch

    assembled = "core\n\nadapter\n\nuniversal\n\nskills\n\nmemory\n\ncontext\n\nenvironment\n\nvolatile"
    spec = MagicMock(
        contract_window=257_000, output_reserve=100, policy_core_max=10_000,
        fixed_prefix_max=20_000, payload_floor=100, safety_reserve=100,
    )
    rendered = MagicMock(stable="core\n\n## MODEL ADAPTER\n\nadapter")
    counter = MagicMock()
    counter.count_text.side_effect = lambda text: 11 if text == "core" else 777
    counter.count_tools.return_value = 23
    counter.count_messages.return_value = 31
    admitted = MagicMock(admitted=True, effective_window=257_000)
    agent = SimpleNamespace(provider="old", model="old", _prompt_profile=None)

    with (
        patch("agent.prompt_profiles.transaction.find_profile", return_value=spec),
        patch("agent.prompt_profiles.transaction.render_profile", return_value=rendered),
        patch("agent.prompt_profiles.transaction.get_token_counter", return_value=counter),
        patch("agent.prompt_profiles.transaction.build_system_prompt_candidate", return_value=assembled),
        patch("agent.prompt_profiles.transaction.evaluate_admission", return_value=admitted) as evaluate,
    ):
        prepared = prepare_model_switch(
            agent, model="gpt-5.6-sol", provider="openai-codex", runtime_window=257_000,
            messages=({"role": "user", "content": "history"},),
            tools=({"type": "function", "function": {"name": "tool"}},),
        )

    assert prepared.final_prompt == assembled
    assert counter.count_text.call_args_list == [call("core"), call(assembled)]
    assert evaluate.call_args.kwargs["fixed_tokens"] == 800
    assert evaluate.call_args.kwargs["conversation_tokens"] == 31
