"""Regression tests for gateway inline-keyboard model-picker persistence.

#49066 made the typed ``/model <name>`` command persist the selected model to
``config.yaml`` by default. But the inline-keyboard picker callback
(``_on_model_selected`` in ``gateway/slash_commands.py``) was left session-only:
it hard-coded ``is_global=False`` and never wrote ``config.yaml``, so *tapping* a
model in the Telegram/Discord picker silently reverted on the next launch while
*typing* the same model persisted — a contradiction the same PR introduced.

After the fix (#49176), the picker callback honors the resolved
``persist_global`` (defaults to ``True``, still respects ``--session``) and runs
the same read-modify-write block the text path uses, so a tapped model survives
across sessions like a typed one.

These tests drive the real ``_handle_model_command`` with a fake picker-capable
adapter that captures the ``on_model_selected`` callback, then invoke that
callback and assert ``config.yaml`` is (or isn't) updated — exercising the exact
closure the PR changed, against a real temp ``HERMES_HOME``.
"""

import asyncio
import types
import threading
from unittest.mock import AsyncMock, Mock, call

import yaml
import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session import SessionSource


class _FakePickerAdapter:
    """Minimal adapter that looks picker-capable and captures the callback.

    ``_handle_model_command`` gates the picker path on
    ``getattr(type(adapter), "send_model_picker", None) is not None``, so the
    method must exist on the class, not just the instance.
    """

    def __init__(self):
        self.captured_callback = None

    async def send_model_picker(self, *, on_model_selected, **kwargs):
        # Stash the closure the handler built so the test can fire a "tap".
        self.captured_callback = on_model_selected
        return types.SimpleNamespace(success=True)


def _make_runner(adapter):
    runner = object.__new__(GatewayRunner)
    runner.adapters = {Platform.TELEGRAM: adapter}
    runner._voice_mode = {}
    runner._session_model_overrides = {}
    runner._pending_model_notes = {}
    runner._running_agents = {}
    runner._agent_cache = {}
    runner._agent_cache_lock = threading.Lock()
    entry = types.SimpleNamespace(
        session_id="picker-session", model="old-model"
    )
    session_db = types.SimpleNamespace(update_session_model=AsyncMock())
    session_store = types.SimpleNamespace(
        get_or_create_session=Mock(return_value=entry),
        set_model_override=AsyncMock(),
    )
    runner.session_store = session_store
    runner._session_db = types.SimpleNamespace(_db=session_db)
    runner._test_session_entry = entry
    runner._test_session_db = session_db
    runner._test_session_store = session_store
    runner._test_evicted = []

    def _evict(session_key):
        runner._test_evicted.append(session_key)
        with runner._agent_cache_lock:
            runner._agent_cache.pop(session_key, None)

    runner._evict_cached_agent = _evict
    return runner


def _shutdown_runner(runner):
    executor = getattr(runner, "_executor", None)
    threads = tuple(getattr(executor, "_threads", ()))
    runner._shutdown_executor()
    for thread in threads:
        thread.join(timeout=1)
    assert all(not thread.is_alive() for thread in threads)


def _make_event(text):
    return MessageEvent(
        text=text,
        message_type=MessageType.TEXT,
        source=SessionSource(platform=Platform.TELEGRAM, chat_id="12345", chat_type="dm"),
    )


def _fake_switch_result(new_model="gpt-5.5"):
    """A successful ModelSwitchResult that bypasses real provider resolution."""
    from hermes_cli.model_switch import ModelSwitchResult

    return ModelSwitchResult(
        success=True,
        new_model=new_model,
        target_provider="openrouter",
        provider_changed=True,
        api_key="sk-test",
        base_url="https://openrouter.ai/api/v1",
        api_mode="chat_completions",
        provider_label="OpenRouter",
        is_global=True,
    )


def _setup_isolated_home(tmp_path, monkeypatch, model_yaml_value):
    """Write a config.yaml with the given ``model:`` value and stub heavy bits."""
    import gateway.run as gateway_run

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    cfg_path = hermes_home / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"model": model_yaml_value, "providers": {}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(gateway_run, "_hermes_home", hermes_home)
    monkeypatch.setattr(
        GatewayRunner,
        "_resolve_profile_home_for_source",
        lambda _runner, _source: hermes_home,
    )
    monkeypatch.setattr("agent.models_dev.fetch_models_dev", lambda: {})
    # The picker-setup path calls list_picker_providers, which otherwise hits
    # the network (OpenRouter model catalog). Stub it to a minimal list — these
    # tests capture and fire the on_model_selected callback and don't assert on
    # picker contents. The handler imports it as a local alias at call time, so
    # patching the source-module attribute takes effect.
    monkeypatch.setattr(
        "hermes_cli.model_switch.list_picker_providers",
        lambda **kw: [{"slug": "openrouter", "name": "OpenRouter", "models": ["gpt-5.5"]}],
    )
    # switch_model is imported as a local alias inside the handler
    # (`from hermes_cli.model_switch import switch_model as _switch_model`),
    # so patching the source-module attribute takes effect at call time.
    monkeypatch.setattr(
        "hermes_cli.model_switch.switch_model",
        lambda **kw: _fake_switch_result(),
    )
    # The confirmation builder resolves context length for display, which
    # otherwise makes real outbound HTTP calls (Ollama /api/show + the
    # OpenRouter models catalog). Stub it — these tests don't assert on the
    # displayed context, and the closure imports it lazily from this module.
    monkeypatch.setattr(
        "hermes_cli.model_switch.resolve_display_context_length",
        lambda *a, **k: 272000,
    )
    # save_config writes to ``get_hermes_home() / config.yaml`` — point it here.
    monkeypatch.setattr("hermes_constants.get_hermes_home", lambda: hermes_home)
    monkeypatch.setattr("hermes_cli.config.get_hermes_home", lambda: hermes_home)
    return cfg_path


async def _drive_picker(runner, event):
    """Run the handler (which sends the picker) then fire the captured tap."""
    sent = await runner._handle_model_command(event)
    # Bare /model returns None (picker sent); the adapter captured the callback.
    assert sent is None
    adapter = runner.adapters[Platform.TELEGRAM]
    assert adapter.captured_callback is not None, "picker callback was not wired"
    # Simulate the user tapping "gpt-5.5" under the openrouter provider.
    return await adapter.captured_callback("12345", "gpt-5.5", "openrouter")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "seed_model",
    [
        # Already-nested dict (common case).
        {
            "default": "old-model",
            "provider": "custom",
            "base_url": "https://api.custom.example/v1",
            "api_key": "sk-stale",
            "api_mode": "anthropic_messages",
        },
        # Flat-string model: must be coerced to a nested dict on a tap (same
        # scalar-``model:`` guard the text path has) instead of raising
        # ``TypeError`` on assignment.
        "deepseek-v4-flash",
    ],
    ids=["nested-dict", "flat-string"],
)
async def test_picker_tap_persists_by_default(tmp_path, monkeypatch, seed_model):
    """Tapping a model in the picker (bare /model) persists to config.yaml,
    matching the typed ``/model`` default — this is the #49176 fix. The written
    ``model:`` must always end up a nested dict regardless of the seed shape."""
    adapter = _FakePickerAdapter()
    cfg_path = _setup_isolated_home(tmp_path, monkeypatch, seed_model)

    runner = _make_runner(adapter)
    try:
        confirmation = await _drive_picker(runner, _make_event("/model"))
    finally:
        _shutdown_runner(runner)

    assert confirmation is not None
    assert "gpt-5.5" in confirmation
    written = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert isinstance(written["model"], dict), (
        "model: should be coerced to a dict, got %r" % (written["model"],)
    )
    assert written["model"]["default"] == "gpt-5.5"
    assert written["model"]["provider"] == "openrouter"
    assert "base_url" not in written["model"]
    assert "api_key" not in written["model"]
    assert "api_mode" not in written["model"]
    persisted = runner._test_session_store.set_model_override.await_args.args[1]
    assert "api_key" not in persisted
    assert "api_mode" not in persisted


@pytest.mark.asyncio
async def test_picker_tap_session_flag_does_not_persist(tmp_path, monkeypatch):
    """``/model --session`` then a picker tap stays in-memory only — config
    untouched, but the in-memory session override must still be applied (the
    switch worked, it just wasn't persisted)."""
    adapter = _FakePickerAdapter()
    cfg_path = _setup_isolated_home(
        tmp_path, monkeypatch, {"default": "old-model", "provider": "openai-codex"}
    )
    runner = _make_runner(adapter)

    try:
        confirmation = await _drive_picker(runner, _make_event("/model --session"))
    finally:
        _shutdown_runner(runner)

    assert confirmation is not None
    assert "gpt-5.5" in confirmation
    # The session override IS applied in-memory (proves the path didn't no-op).
    assert runner._session_model_overrides, "session override should be set"
    assert any(
        ov.get("model") == "gpt-5.5"
        for ov in runner._session_model_overrides.values()
    )
    # But config.yaml is untouched — the override is in-memory only.
    written = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert written["model"]["default"] == "old-model"
    assert written["model"]["provider"] == "openai-codex"


@pytest.mark.asyncio
async def test_picker_apply_failure_compensates_every_authority(
    tmp_path, monkeypatch,
):
    adapter = _FakePickerAdapter()
    cfg_path = _setup_isolated_home(
        tmp_path,
        monkeypatch,
        {"default": "old-model", "provider": "openrouter"},
    )
    runner = _make_runner(adapter)
    store_calls = []
    config_before = cfg_path.read_bytes()
    config_save_calls = []
    monkeypatch.setattr(
        "hermes_cli.config.save_config",
        lambda config: config_save_calls.append(config),
    )

    async def _fail_new_override(_session_key, override):
        store_calls.append(override)
        if len(store_calls) == 1:
            raise RuntimeError("injected store apply failure")

    runner._test_session_store.set_model_override.side_effect = _fail_new_override
    try:
        result = await _drive_picker(runner, _make_event("/model"))
    finally:
        _shutdown_runner(runner)

    assert "failed" in result.lower()
    assert runner._session_model_overrides == {}
    assert runner._pending_model_notes == {}
    assert runner._test_evicted == []
    assert runner._test_session_db.update_session_model.await_args_list == [
        call("picker-session", "gpt-5.5"),
        call("picker-session", "old-model"),
    ]
    assert store_calls[-1] is None
    assert config_save_calls == []
    assert cfg_path.read_bytes() == config_before
    written = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert written["model"] == {
        "default": "old-model", "provider": "openrouter",
    }


@pytest.mark.asyncio
async def test_uncached_picker_failed_compensation_is_ambiguous_and_evicts(
    tmp_path, monkeypatch,
):
    adapter = _FakePickerAdapter()
    _setup_isolated_home(
        tmp_path,
        monkeypatch,
        {"default": "old-model", "provider": "openrouter"},
    )
    runner = _make_runner(adapter)

    async def _reject_apply_and_compensation(_session_key, _override):
        raise RuntimeError("injected persistent store failure")

    runner._test_session_store.set_model_override.side_effect = (
        _reject_apply_and_compensation
    )
    try:
        result = await _drive_picker(runner, _make_event("/model"))
    finally:
        _shutdown_runner(runner)

    session_key = runner._session_key_for_source(_make_event("/model").source)
    assert "ambiguous" in result
    assert "recovery is required" in result
    assert "staying on old-model" not in result
    assert runner._test_evicted == [session_key]


@pytest.mark.asyncio
async def test_picker_late_cached_failure_compensates_old_state(
    tmp_path, monkeypatch,
):
    adapter = _FakePickerAdapter()
    cfg_path = _setup_isolated_home(
        tmp_path,
        monkeypatch,
        {"default": "old-model", "provider": "openrouter"},
    )
    runner = _make_runner(adapter)
    source = _make_event("/model").source
    session_key = runner._session_key_for_source(source)
    old_override = {"model": "old-model", "provider": "openrouter"}
    runner._session_model_overrides[session_key] = dict(old_override)
    runner._pending_model_notes[session_key] = "old-note"
    assert runner._resolve_profile_home_for_source(source) == cfg_path.parent

    class _LateFailingAgent:
        conversation_history = [{"role": "user", "content": "resume"}]

        def switch_model(self, **kwargs):
            mutation = kwargs["durable_mutations"][0]
            mutation.apply()
            mutation.compensate()
            raise RuntimeError("late cached failure")

    runner._agent_cache[session_key] = (_LateFailingAgent(),)
    try:
        result = await _drive_picker(runner, _make_event("/model"))
    finally:
        _shutdown_runner(runner)

    assert "late cached failure" in result
    assert runner._session_model_overrides[session_key] == old_override
    assert runner._pending_model_notes[session_key] == "old-note"
    assert runner._test_evicted == []
    assert runner._test_session_db.update_session_model.await_args_list == [
        call("picker-session", "gpt-5.5"),
        call("picker-session", "old-model"),
    ]
    persisted_calls = runner._test_session_store.set_model_override.await_args_list
    assert persisted_calls[-1] == call(session_key, old_override)
    assert "api_key" not in persisted_calls[0].args[1]
    written = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert written["model"] == {
        "default": "old-model", "provider": "openrouter",
    }


@pytest.mark.asyncio
async def test_picker_post_cas_failure_reports_new_committed_and_evicts(
    tmp_path, monkeypatch,
):
    adapter = _FakePickerAdapter()
    cfg_path = _setup_isolated_home(
        tmp_path,
        monkeypatch,
        {"default": "old-model", "provider": "openrouter"},
    )
    runner = _make_runner(adapter)
    source = _make_event("/model").source
    session_key = runner._session_key_for_source(source)

    class _PostCasFailingAgent:
        conversation_history = []
        _prompt_profile_state_version = 4

        def switch_model(self, **kwargs):
            kwargs["durable_mutations"][0].apply()
            self._prompt_profile_state_version = 5
            raise RuntimeError("post-CAS cleanup failure")

    runner._agent_cache[session_key] = (_PostCasFailingAgent(),)
    try:
        result = await _drive_picker(runner, _make_event("/model"))
    finally:
        _shutdown_runner(runner)

    assert "gpt-5.5 committed" in result
    assert "cleanup is pending" in result
    assert "staying on old-model" not in result
    assert runner._session_model_overrides[session_key]["model"] == "gpt-5.5"
    assert runner._test_session_entry.model == "gpt-5.5"
    assert runner._test_evicted == [session_key]
    written = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert written["model"]["default"] == "gpt-5.5"


@pytest.mark.asyncio
async def test_picker_rollback_incomplete_reports_ambiguous_and_evicts(
    tmp_path, monkeypatch,
):
    adapter = _FakePickerAdapter()
    _setup_isolated_home(
        tmp_path,
        monkeypatch,
        {"default": "old-model", "provider": "openrouter"},
    )
    runner = _make_runner(adapter)
    source = _make_event("/model").source
    session_key = runner._session_key_for_source(source)

    class _RollbackIncompleteAgent:
        conversation_history = []
        _prompt_profile_state_version = 8

        def switch_model(self, **kwargs):
            kwargs["durable_mutations"][0].apply()
            raise RuntimeError("ROLLBACK_INCOMPLETE")

    runner._agent_cache[session_key] = (_RollbackIncompleteAgent(),)
    try:
        result = await _drive_picker(runner, _make_event("/model"))
    finally:
        _shutdown_runner(runner)

    assert "ambiguous" in result
    assert "recovery is required" in result
    assert "staying on old-model" not in result
    assert runner._test_evicted == [session_key]


@pytest.mark.asyncio
async def test_concurrent_picker_failure_rolls_back_to_first_coherent_winner(
    tmp_path, monkeypatch,
):
    adapter = _FakePickerAdapter()
    cfg_path = _setup_isolated_home(
        tmp_path,
        monkeypatch,
        {"default": "old-model", "provider": "openrouter"},
    )
    monkeypatch.setattr(
        "hermes_cli.model_switch.switch_model",
        lambda **kwargs: _fake_switch_result(kwargs["raw_input"]),
    )
    runner = _make_runner(adapter)
    runner._test_session_db.update_session_model = Mock()
    runner._session_db._db = runner._test_session_db
    runner._test_session_store.set_model_override = Mock()
    first_apply_entered = threading.Event()
    release_first_apply = threading.Event()
    db_models = []
    persisted_models = []

    def _update_session_model(_session_id, model):
        db_models.append(model)
        if model == "model-a" and db_models.count("model-a") == 1:
            first_apply_entered.set()
            release_first_apply.wait(timeout=2)

    def _set_model_override(_session_key, override):
        model = (override or {}).get("model")
        persisted_models.append(model)
        if model == "model-b":
            raise RuntimeError("injected second picker failure")

    runner._test_session_db.update_session_model.side_effect = _update_session_model
    runner._test_session_store.set_model_override.side_effect = _set_model_override
    try:
        assert await runner._handle_model_command(_make_event("/model")) is None
        callback = adapter.captured_callback
        first = asyncio.create_task(callback("12345", "model-a", "openrouter"))
        while not first_apply_entered.is_set():
            await asyncio.sleep(0.001)
        second = asyncio.create_task(callback("12345", "model-b", "openrouter"))
        await asyncio.sleep(0.02)
        assert "model-b" not in db_models
        release_first_apply.set()
        first_result, second_result = await asyncio.gather(first, second)
    finally:
        release_first_apply.set()
        _shutdown_runner(runner)

    session_key = runner._session_key_for_source(_make_event("/model").source)
    assert "model-a" in first_result
    assert "staying on model-a" in second_result
    assert runner._session_model_overrides[session_key]["model"] == "model-a"
    assert runner._test_session_entry.model == "model-a"
    assert db_models == ["model-a", "model-b", "model-a"]
    assert persisted_models == ["model-a", "model-b", "model-a"]
    written = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert written["model"]["default"] == "model-a"
