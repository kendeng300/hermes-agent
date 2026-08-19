"""Offline Slack regression for compressed-session prompt-profile switches.

Only provider discovery and network transports are faked.  Gateway dispatch,
compression, AIAgent.switch_model, durable SessionDB/SessionStore writes,
cache eviction, persisted reload, fresh construction, and request assembly are
production boundaries.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from gateway.config import Platform
from gateway.platforms.base import MessageEvent, MessageType
from gateway.session import SessionSource


class _Counter:
    tokenizer_id = "offline-exact-boundary"
    tokenizer_version = "test"

    @staticmethod
    def count_text(text: str) -> int:
        return max(1, len(text.encode("utf-8")) // 4)

    def count_tools(self, tools) -> int:
        return self.count_text(json.dumps(list(tools), sort_keys=True)) if tools else 0

    def count_messages(self, messages) -> int:
        return sum(
            self.count_text(str(message.get("role", "")))
            + self.count_text(str(message.get("content", "")))
            + 3
            for message in messages
        )


class _CompletionsTransport:
    __slots__ = ("_callback", "last_aggregator_slot")

    def __init__(self, callback):
        self._callback = callback
        self.last_aggregator_slot = None

    def create(self, **kwargs):
        return self._callback(**kwargs)


class _ChatTransport:
    __slots__ = ("completions",)

    def __init__(self, callback):
        self.completions = _CompletionsTransport(callback)


class _OfflineTransport:
    __slots__ = ("chat",)

    def __init__(self, callback):
        self.chat = _ChatTransport(callback)

    def close(self) -> None:
        return None


def _response(text: str):
    return SimpleNamespace(
        output=[],
        output_text=text,
        status="completed",
        incomplete_details=None,
        model="offline-model",
        choices=[SimpleNamespace(
            message=SimpleNamespace(
                role="assistant", content=text, tool_calls=None,
                reasoning=None, reasoning_content=None, reasoning_details=None,
            ),
            finish_reason="stop",
        )],
        usage=SimpleNamespace(
            prompt_tokens=100, completion_tokens=5, total_tokens=105,
            prompt_tokens_details=None, completion_tokens_details=None,
        ),
    )


def _event(command: str) -> MessageEvent:
    return MessageEvent(
        text=command,
        message_type=MessageType.TEXT,
        source=SessionSource(
            platform=Platform.SLACK,
            chat_id="C-context-regression",
            user_id="U-context-regression",
            chat_type="channel",
            thread_id="T-context-regression",
            profile="test034-profile",
        ),
    )


def _assert_alternating(messages: list[dict]) -> None:
    replay = [message for message in messages if message.get("role") != "system"]
    for previous, current in zip(replay, replay[1:]):
        assert previous.get("role") != current.get("role"), (
            f"same-role neighbors reached transport: {previous.get('role')}"
        )


def test_gateway_fresh_agent_receives_normalized_history_before_profile_activation() -> None:
    """Pin the ordering keyword on every main gateway AIAgent construction."""
    from gateway import run as gateway_run

    tree = ast.parse(textwrap.dedent(
        inspect.getsource(gateway_run.GatewayRunner._run_agent_inner)
    ))
    constructors = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "AIAgent"
    ]
    assert constructors
    main = next(
        node for node in constructors
        if any(
            keyword.arg == "gateway_session_key"
            for keyword in node.keywords
        )
    )
    history_kw = next(
        (keyword for keyword in main.keywords
         if keyword.arg == "initial_conversation_history"),
        None,
    )
    assert history_kw is not None
    assert isinstance(history_kw.value, ast.Name)
    assert history_kw.value.id == "agent_history"

    from agent.conversation_compression import _continuation_model_config

    class AuthorityDB:
        def __init__(self, state):
            self.state = state

        def get_model_switch_state(self, _session_id):
            return self.state

    base = {
        "generation": 1, "transaction_id": "tx-1",
        "provider": "deepseek", "model": "deepseek-v4-flash",
    }
    malformed = (
        {**base, "generation": True},
        {**base, "transaction_id": None},
        {**base, "provider": None},
        {**base, "model": None},
        {**base, "extra": "unreviewed"},
        {**base, "generation": 0},
        {**base, "generation": 0, "transaction_id": None},
        {**base, "generation": 0, "transaction_id": None, "provider": None,
         "model": "wrong-model"},
    )
    for state in malformed:
        agent = SimpleNamespace(
            _session_init_model_config={}, _session_db=AuthorityDB(state),
            provider="deepseek", model="deepseek-v4-flash",
        )
        with pytest.raises(RuntimeError, match="SWITCH_STATE_AMBIGUOUS"):
            _continuation_model_config(agent, "parent")
    valid_zero = SimpleNamespace(
        _session_init_model_config={"max_tokens": 1},
        _session_db=AuthorityDB({
            "generation": 0, "transaction_id": None, "provider": None,
            "model": "deepseek-v4-flash",
        }),
        provider="deepseek", model="deepseek-v4-flash",
    )
    assert _continuation_model_config(valid_zero, "parent") == {
        "max_tokens": 1, "_switch_generation": 0,
    }


_OPENAI = (
    "openai-codex", "gpt-5.6-sol", "codex_responses",
    "https://offline.invalid/codex",
)
_DEEPSEEK = (
    "deepseek", "deepseek-v4-flash", "chat_completions",
    "https://offline.invalid/deepseek",
)


@pytest.mark.parametrize("compression_in_place", [True, False], ids=["in-place", "rotate"])
@pytest.mark.parametrize(
    ("start", "other"),
    [(_OPENAI, _DEEPSEEK), (_DEEPSEEK, _OPENAI)],
    ids=["openai-deepseek-openai", "deepseek-openai-deepseek"],
)
@pytest.mark.asyncio
async def test_real_gateway_compressed_switch_round_trip_and_fresh_reload(
    monkeypatch,
    request,
    start,
    other,
    compression_in_place: bool,
) -> None:
    from agent.prompt_profiles import transaction
    from gateway import run as gateway_run
    from gateway.config import GatewayConfig
    from gateway.session import SessionStore
    import hermes_state
    from hermes_cli.model_switch import ModelSwitchResult
    from hermes_constants import get_hermes_home
    from hermes_temp import current_temp_authority
    from run_agent import AIAgent
    from tests.agent.prompt_profiles.fixtures import install_approved_test_core

    authority = current_temp_authority()
    try:
        owned_runtime = authority.mkdir("profile-switch")
    finally:
        authority.close()
    request.addfinalizer(owned_runtime.cleanup)
    runtime_root = owned_runtime.path
    _core, core_path = install_approved_test_core(runtime_root, monkeypatch)
    hermes_home = core_path.parent
    # hermes_state is imported by gateway.session during collection, before
    # this case installs its private HERMES_HOME. Bind the production SessionDB
    # default to this case's home so the four parameterized cases cannot share
    # durable switch generations through the wrapper process.
    monkeypatch.setattr(hermes_state, "DEFAULT_DB_PATH", hermes_home / "state.db")
    config_path = hermes_home / "config.yaml"
    config_path.write_text(
        yaml.safe_dump({
            "model": {
                "default": start[1],
                "provider": start[0],
                "base_url": start[3],
            },
            "providers": {},
        }),
        encoding="utf-8",
    )
    load_config = lambda: yaml.safe_load(config_path.read_text(encoding="utf-8"))
    monkeypatch.setattr(gateway_run, "_load_gateway_config", load_config)
    monkeypatch.setattr(transaction, "get_token_counter", lambda *_args: _Counter())
    monkeypatch.setattr(
        "agent.model_metadata.get_model_context_length",
        lambda model, **_kwargs: 1_000_000 if "deepseek" in model else 257_000,
    )
    monkeypatch.setattr(
        "hermes_cli.timeouts.get_provider_request_timeout", lambda *_args: None,
    )
    monkeypatch.setattr("agent.credential_pool.load_pool", lambda *_args: None)
    monkeypatch.setattr(
        "hermes_cli.model_cost_guard.expensive_model_warning",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "gateway.slash_commands._model_switch_skew_guard", lambda: None,
    )
    monkeypatch.setattr(
        "hermes_cli.model_switch.resolve_display_context_length",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "hermes_cli.context_switch_guard.enrich_model_switch_warnings_for_gateway",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "tools.tirith_security.ensure_installed", lambda **_kwargs: False,
    )

    captured: list[tuple[str, str, dict]] = []

    def fake_client(self, _kwargs, *, reason, shared):
        def create(**api_kwargs):
            captured.append((self.provider, self.model, api_kwargs))
            return _response(f"reply from {self.provider}")
        return _OfflineTransport(create)

    def fake_codex_stream(self, api_kwargs, **_kwargs):
        captured.append((self.provider, self.model, api_kwargs))
        return _response("reply from openai-codex")

    monkeypatch.setattr(AIAgent, "_create_openai_client", fake_client)
    monkeypatch.setattr(AIAgent, "_run_codex_stream", fake_codex_stream)

    gateway_config = GatewayConfig(
        sessions_dir=hermes_home / "sessions",
        multiplex_profiles=True,
    )
    runner = gateway_run.GatewayRunner(gateway_config)
    monkeypatch.setattr(runner, "_is_user_authorized", lambda _source: True)
    monkeypatch.setattr(runner, "_check_slash_access", lambda *_args: None)
    monkeypatch.setattr(
        runner, "_resolve_profile_home_for_source", lambda _source: hermes_home,
    )

    source = _event("/model").source
    entry = runner.session_store.get_or_create_session(source)
    session_key = runner._session_key_for_source(source)
    session_db = runner.session_store._db
    assert session_db is not None
    # The fixture begins on an already-authoritative route, as a restarted
    # gateway would.  This prevents initial construction from manufacturing a
    # model switch before the behavior under test; both /model transitions
    # below still cross the real journal/CAS/durability boundary.
    initial_authority = session_db.get_model_switch_state(entry.session_id)
    assert initial_authority == {
        "generation": 0, "transaction_id": None, "provider": None, "model": None,
    }, initial_authority
    assert session_db.compare_and_swap_model_switch(
        entry.session_id,
        expected_generation=0,
        generation=1,
        transaction_id="test034-initial-route",
        provider=start[0],
        model=start[1],
    )

    history = []
    for index in range(18):
        role = "user" if index % 2 == 0 else "assistant"
        message = {
            "role": role,
            "content": f"turn-{index} " + ("context " * 80),
        }
        if role == "assistant" and start[0] == "openai-codex":
            message["codex_reasoning_items"] = [
                {"type": "reasoning", "id": f"rs_{index}"},
            ]
        history.append(message)
        session_db.append_message(
            entry.session_id,
            role,
            message["content"],
            codex_reasoning_items=message.get("codex_reasoning_items"),
        )

    def construct(identity, restored_history):
        provider, model, api_mode, base_url = identity
        agent = AIAgent(
            api_key=f"offline-{provider}",
            base_url=base_url,
            provider=provider,
            api_mode=api_mode,
            model=model,
            max_iterations=2,
            enabled_toolsets=[],
            quiet_mode=True,
            skip_context_files=True,
            skip_memory=True,
            session_db=session_db,
            session_id=entry.session_id,
            initial_conversation_history=restored_history,
            platform="slack",
            gateway_session_key=session_key,
        )
        agent.tools = []
        agent.valid_tool_names = set()
        agent._disable_streaming = True
        return agent

    agent = construct(start, history)
    assert agent._prompt_profile[:2] == start[:2]
    agent.compression_in_place = compression_in_place
    agent.context_compressor.tail_token_budget = 100
    agent.context_compressor.protect_last_n = 3
    agent.context_compressor._generate_summary = (
        lambda _messages, focus_topic=None: "Durable compressed diagnosis."
    )
    # Auxiliary provider discovery is the offline transport boundary.  The
    # real compressor below still selects/assembles/persists the compaction.
    agent._compression_feasibility_checked = True
    original_session_id = agent.session_id
    compressed, compressed_prompt = agent._compress_context(
        list(history), agent._cached_system_prompt,
        approx_tokens=200_000, force=True,
    )
    assert len(compressed) < len(history)
    assert agent.context_compressor.compression_count == 1
    assert (agent.session_id == original_session_id) is compression_in_place
    if not compression_in_place:
        rotated_authority = session_db.get_model_switch_state(agent.session_id)
        assert rotated_authority == {
            "generation": 1,
            "transaction_id": "test034-initial-route",
            "provider": start[0],
            "model": start[1],
        }
    assert session_db.get_session(agent.session_id)["system_prompt_sha256"] == (
        __import__("hashlib").sha256(compressed_prompt.encode("utf-8")).hexdigest()
    )
    agent.conversation_history = list(compressed)
    entry.session_id = agent.session_id
    runner._agent_cache[session_key] = (agent, "profile-switch-test")

    scoped_homes = []
    resolved = []

    def resolve_switch(**kwargs):
        scoped_homes.append(get_hermes_home())
        target_provider = kwargs["explicit_provider"]
        identity = other if target_provider == other[0] else start
        resolved.append(identity[:2])
        return ModelSwitchResult(
            success=True,
            new_model=identity[1],
            target_provider=identity[0],
            provider_changed=True,
            api_key=f"offline-{identity[0]}",
            base_url=identity[3],
            api_mode=identity[2],
            warning_message="",
            provider_label=identity[0],
            resolved_via_alias=False,
            capabilities=None,
            model_info=None,
            is_global=False,
        )

    # The slash dispatcher imports this resolver when the command is invoked;
    # provider discovery is the only non-hermetic boundary in this step.
    monkeypatch.setattr("hermes_cli.model_switch.switch_model", resolve_switch)

    async def dispatch(identity):
        event = _event(
            f"/model {identity[1]} --provider {identity[0]} --session"
        )
        task = asyncio.create_task(runner._handle_message(event))
        deadline = asyncio.get_running_loop().time() + 10
        # Production gateways have timers and watcher tasks waking the loop.
        # Poll here so worker-completion delivery is deterministic even in a
        # minimal test loop, while keeping the real executor boundaries.
        while not task.done() and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        if not task.done():
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            pytest.fail("real GatewayRunner /model dispatch exceeded 10s")
        return await task

    reply = await dispatch(other)
    assert other[1] in reply
    assert (agent.provider, agent.model) == other[:2]
    assert session_key not in runner._agent_cache
    assert scoped_homes[-1] == hermes_home

    reloaded_store = SessionStore(hermes_home / "sessions", gateway_config)
    reloaded_entry = reloaded_store.get_or_create_session(source)
    assert reloaded_entry.session_id == agent.session_id
    assert reloaded_store.get_model_override(session_key) == {
        "model": other[1], "provider": other[0], "base_url": other[3],
    }

    def run_fresh(identity, prompt):
        persisted = session_db.get_messages_as_conversation(agent.session_id)
        fresh = construct(identity, persisted)
        assert fresh._prompt_profile[:2] == identity[:2]
        result = fresh.run_conversation(
            prompt,
            conversation_history=persisted,
            task_id=f"slack-context-{identity[0]}",
        )
        provider, model, request = captured[-1]
        assert (provider, model) == identity[:2]
        wire = request.get("input", request.get("messages"))
        assert isinstance(wire, list)
        _assert_alternating(wire)
        if identity[0] == "deepseek":
            assert not any("codex_reasoning_items" in row for row in wire)
        return fresh, result

    fresh_other, other_result = run_fresh(other, f"Continue on {other[0]}.")
    fresh_other.conversation_history = list(other_result["messages"])
    runner._agent_cache[session_key] = (fresh_other, "profile-switch-test")

    reply_back = await dispatch(start)
    assert start[1] in reply_back
    assert (fresh_other.provider, fresh_other.model) == start[:2]
    assert session_key not in runner._agent_cache
    assert scoped_homes[-1] == hermes_home

    fresh_start, _start_result = run_fresh(start, f"Continue on {start[0]}.")
    switch_state = session_db.get_model_switch_state(fresh_start.session_id)
    assert (switch_state["provider"], switch_state["model"]) == start[:2]
    assert resolved == [other[:2], start[:2]]

    for live_agent in (agent, fresh_other, fresh_start):
        live_agent.release_clients()

    # pytest's minimal asyncio loop has no gateway watcher timers.  Drain its
    # worker pool while a bounded poll keeps thread-completion notifications
    # serviceable; production performs the analogous drain during shutdown.
    loop = asyncio.get_running_loop()
    shutdown = asyncio.create_task(loop.shutdown_default_executor())
    deadline = loop.time() + 5
    while not shutdown.done() and loop.time() < deadline:
        await asyncio.sleep(0.01)
    assert shutdown.done(), "default executor did not drain after gateway case"
    await shutdown
