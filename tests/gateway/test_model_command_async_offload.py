"""Regression tests for #41289: the Discord/Telegram ``/model`` slash command
must not run the blocking provider-listing on the gateway's async event loop.

``list_picker_providers`` / ``list_authenticated_providers`` are synchronous and
can fall through to a blocking ``urllib`` HTTP fetch when the on-disk provider
cache is stale. Running that directly on the event loop froze the gateway for
120-150s ("application did not respond" + delayed agent starts).

Fix (ported from #41304, which patched the old ``gateway/run.py`` location):
``_handle_model_command`` offloads BOTH provider-listing calls via the
GatewayRunner-owned executor so the loop stays responsive without depending
on asyncio's process-global default executor:

  * line ~1161 — picker path     -> ``list_picker_providers``
  * line ~1382 — text-fallback   -> ``list_authenticated_providers``

These tests assert the *owned offload contract* at the real handler seam.
"""

import asyncio
import concurrent.futures
import contextvars
import threading
from types import SimpleNamespace

import pytest

import gateway.slash_commands as slash_commands
from gateway.config import Platform
from gateway.platforms.base import MessageEvent, MessageType
from gateway.run import GatewayRunner
from gateway.session import SessionSource


# --------------------------------------------------------------------------- #
# Harness
# --------------------------------------------------------------------------- #
def _make_runner():
    runner = object.__new__(GatewayRunner)
    runner.adapters = {}
    runner._voice_mode = {}
    runner._session_model_overrides = {}
    runner._running_agents = {}
    return runner


def _make_event():
    """A bare ``/model`` (no args) — triggers the listing branch."""
    return MessageEvent(
        text="/model",
        message_type=MessageType.TEXT,
        source=SessionSource(platform=Platform.TELEGRAM, chat_id="12345", chat_type="dm"),
    )


@pytest.mark.asyncio
async def test_model_blocking_direct_submit_preserves_context_and_reuses_executor(
    monkeypatch,
):
    marker = contextvars.ContextVar("model-direct-submit-marker", default="missing")
    marker.set("bound")
    observed = []

    def _poison(*_args, **_kwargs):
        raise AssertionError("model blocking work used an asyncio executor bridge")

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "run_in_executor", _poison)
    monkeypatch.setattr(asyncio, "wrap_future", _poison)
    monkeypatch.setattr(slash_commands.asyncio, "to_thread", _poison)
    runner = _make_runner()

    def _read(index):
        thread = threading.current_thread()
        observed.append((index, marker.get(), thread.name, thread.ident))
        return index

    try:
        results = [await runner._run_model_blocking(_read, index) for index in range(3)]
    finally:
        runner._shutdown_executor()

    assert results == [0, 1, 2]
    assert [(index, value) for index, value, _, _ in observed] == [
        (0, "bound"), (1, "bound"), (2, "bound"),
    ]
    assert all(name.startswith("hermes-gateway") for _, _, name, _ in observed)


@pytest.mark.asyncio
async def test_model_blocking_deadline_cancels_queued_work_without_entry():
    runner = _make_runner()
    runner._executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="hermes-gateway"
    )
    blocker_started = threading.Event()
    release_blocker = threading.Event()
    called = []

    def _blocker():
        blocker_started.set()
        release_blocker.wait(timeout=2)

    blocker = runner._submit_in_executor_with_context(_blocker)
    try:
        while not blocker_started.is_set():
            await asyncio.sleep(0.001)
        with pytest.raises(
            slash_commands.GatewayExecutorUnavailable,
            match="exceeded its deadline",
        ):
            await runner._run_model_blocking(
                lambda: called.append("entered"), _deadline_seconds=0.02,
            )
    finally:
        release_blocker.set()
        blocker.result(timeout=2)
        runner._shutdown_executor()

    assert called == []


@pytest.mark.asyncio
async def test_model_blocking_cancellation_cancels_queued_work_without_entry():
    runner = _make_runner()
    runner._executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix="hermes-gateway"
    )
    blocker_started = threading.Event()
    release_blocker = threading.Event()
    called = []

    def _blocker():
        blocker_started.set()
        release_blocker.wait(timeout=2)

    blocker = runner._submit_in_executor_with_context(_blocker)
    task = None
    try:
        while not blocker_started.is_set():
            await asyncio.sleep(0.001)
        task = asyncio.create_task(
            runner._run_model_blocking(
                lambda: called.append("entered"), _deadline_seconds=None,
            )
        )
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release_blocker.set()
        blocker.result(timeout=2)
        runner._shutdown_executor()

    assert called == []


@pytest.mark.asyncio
async def test_model_blocking_deadline_drains_running_work_before_failure():
    runner = _make_runner()
    started = threading.Event()
    release = threading.Event()
    trace = []

    def _work():
        trace.append("entry")
        started.set()
        release.wait(timeout=2)
        trace.append("exit")

    async def _release_after_deadline():
        while not started.is_set():
            await asyncio.sleep(0.001)
        await asyncio.sleep(0.04)
        release.set()

    releaser = asyncio.create_task(_release_after_deadline())
    try:
        with pytest.raises(
            slash_commands.GatewayExecutorUnavailable,
            match="exceeded its deadline",
        ):
            await runner._run_model_blocking(_work, _deadline_seconds=0.01)
        await releaser
    finally:
        release.set()
        runner._shutdown_executor()

    assert trace == ["entry", "exit"]


@pytest.mark.asyncio
async def test_model_blocking_repeated_cancel_waits_for_running_work():
    runner = _make_runner()
    started = threading.Event()
    release = threading.Event()
    trace = []

    def _work():
        trace.append("entry")
        started.set()
        release.wait(timeout=2)
        trace.append("exit")

    task = asyncio.create_task(
        runner._run_model_blocking(_work, _deadline_seconds=None)
    )
    try:
        while not started.is_set():
            await asyncio.sleep(0.001)
        task.cancel()
        await asyncio.sleep(0.02)
        task.cancel()
        await asyncio.sleep(0.02)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        runner._shutdown_executor()

    assert trace == ["entry", "exit"]


@pytest.mark.asyncio
async def test_model_blocking_cancel_wins_over_running_callable_error():
    runner = _make_runner()
    started = threading.Event()
    release = threading.Event()

    def _work():
        started.set()
        release.wait(timeout=2)
        raise ValueError("late callable failure")

    task = asyncio.create_task(
        runner._run_model_blocking(_work, _deadline_seconds=None)
    )
    try:
        while not started.is_set():
            await asyncio.sleep(0.001)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        runner._shutdown_executor()


@pytest.mark.asyncio
async def test_model_transaction_barrier_defers_cancel_until_new_state_is_sealed():
    runner = _make_runner()
    started = threading.Event()
    release = threading.Event()
    state = {"model": "old"}

    def _commit():
        started.set()
        release.wait(timeout=2)
        state["model"] = "new"

    async def _transaction():
        await runner._run_model_blocking(_commit, _deadline_seconds=None)

    task = asyncio.create_task(
        runner._run_model_transaction_barrier(_transaction())
    )
    try:
        while not started.is_set():
            await asyncio.sleep(0.001)
        task.cancel()
        await asyncio.sleep(0.02)
        task.cancel()
        assert state == {"model": "old"}
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        runner._shutdown_executor()

    assert state == {"model": "new"}


@pytest.mark.asyncio
async def test_model_transaction_cancel_wins_over_late_transaction_error(caplog):
    runner = _make_runner()
    started = asyncio.Event()
    release = asyncio.Event()

    async def _transaction():
        started.set()
        await release.wait()
        raise ValueError("late transaction failure")

    task = asyncio.create_task(
        runner._run_model_transaction_barrier(_transaction())
    )
    await started.wait()
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert "failed while outer cancellation was deferred" in caplog.text


@pytest.fixture
def _isolated_config(tmp_path, monkeypatch):
    """Point the handler at an empty isolated home so config loading is cheap
    and deterministic (no real provider creds / network)."""
    import gateway.run as gateway_run

    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text("model:\n  default: gpt-x\n  provider: openrouter\nproviders: {}\n", encoding="utf-8")
    monkeypatch.setattr(gateway_run, "_hermes_home", hermes_home)
    monkeypatch.setattr("agent.models_dev.fetch_models_dev", lambda: {})
    return hermes_home


# --------------------------------------------------------------------------- #
# Text-fallback path  ->  list_authenticated_providers
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_text_fallback_offloads_list_authenticated_providers(_isolated_config, monkeypatch):
    """No picker-capable adapter registered => handler takes the text fallback,
    which must offload ``list_authenticated_providers`` to a worker thread."""
    observed_threads = []

    def _fake_list_authenticated_providers(**kwargs):
        observed_threads.append(threading.current_thread())
        return []

    monkeypatch.setattr(
        "hermes_cli.model_switch.list_authenticated_providers",
        _fake_list_authenticated_providers,
    )

    runner = _make_runner()  # no adapters -> has_picker is False
    try:
        result = await runner._handle_model_command(_make_event())
    finally:
        runner._shutdown_executor()

    assert result is not None  # text list rendered
    assert observed_threads
    assert all(t is not threading.main_thread() for t in observed_threads)
    assert all(t.name.startswith("hermes-gateway") for t in observed_threads)


# --------------------------------------------------------------------------- #
# Picker path  ->  list_picker_providers
# --------------------------------------------------------------------------- #
class _FakePickerResult:
    success = True


class _FakePickerAdapter:
    """Adapter whose *type* exposes ``send_model_picker`` (the gate the handler
    checks via ``getattr(type(adapter), 'send_model_picker', None)``)."""

    async def send_model_picker(self, **kwargs):
        return _FakePickerResult()

    def _thread_metadata(self, *a, **k):  # pragma: no cover - not exercised
        return None


@pytest.mark.asyncio
async def test_picker_path_offloads_list_picker_providers(_isolated_config, monkeypatch):
    """A picker-capable adapter => handler takes the picker branch, which must
    offload ``list_picker_providers`` to a worker thread."""
    # Non-empty providers so the handler proceeds to send_model_picker (and
    # returns None), proving we got past the offloaded listing call.
    observed_threads = []
    fake_providers = [{"slug": "openrouter", "name": "OpenRouter", "is_current": True,
                       "models": ["gpt-x"], "total_models": 1}]

    def _fake_list_picker_providers(**kwargs):
        observed_threads.append(threading.current_thread())
        return fake_providers

    monkeypatch.setattr(
        "hermes_cli.model_switch.list_picker_providers",
        _fake_list_picker_providers,
    )

    runner = _make_runner()
    runner.adapters = {Platform.TELEGRAM: _FakePickerAdapter()}
    # Stub the metadata/anchor helpers the picker branch calls before sending.
    monkeypatch.setattr(runner, "_thread_metadata_for_source", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(runner, "_reply_anchor_for_event", lambda *a, **k: None, raising=False)

    try:
        result = await runner._handle_model_command(_make_event())
    finally:
        runner._shutdown_executor()

    # Picker "sent" => handler returns None.
    assert result is None
    assert observed_threads
    assert all(t is not threading.main_thread() for t in observed_threads)
    assert all(t.name.startswith("hermes-gateway") for t in observed_threads)


@pytest.mark.asyncio
async def test_picker_path_requests_moa_presets(_isolated_config, monkeypatch):
    """Gateway /model pickers must opt into the virtual MoA preset provider."""
    captured = {}

    def _fake_list_picker_providers(**kwargs):
        captured.update(kwargs)
        return [{"slug": "moa", "name": "Mixture of Agents", "is_current": False,
                 "models": ["battle", "smart"], "total_models": 2}]

    monkeypatch.setattr(
        "hermes_cli.model_switch.list_picker_providers",
        _fake_list_picker_providers,
    )

    runner = _make_runner()
    runner.adapters = {Platform.TELEGRAM: _FakePickerAdapter()}
    monkeypatch.setattr(runner, "_thread_metadata_for_source", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(runner, "_reply_anchor_for_event", lambda *a, **k: None, raising=False)

    try:
        result = await runner._handle_model_command(_make_event())
    finally:
        runner._shutdown_executor()

    assert result is None
    assert captured["include_moa"] is True


@pytest.mark.asyncio
async def test_model_command_missing_owned_executor_fails_closed(
    _isolated_config, monkeypatch,
):
    called = []
    monkeypatch.setattr(
        "hermes_cli.model_switch.list_authenticated_providers",
        lambda **kwargs: called.append(kwargs),
    )
    runner = _make_runner()
    runner._submit_in_executor_with_context = None
    try:
        result = await runner._handle_model_command(_make_event())
    finally:
        runner._shutdown_executor()

    assert "Gateway executor unavailable; model switch was not applied" in result
    assert called == []
    assert runner._session_model_overrides == {}


@pytest.mark.asyncio
async def test_model_command_closing_owned_executor_fails_closed(
    _isolated_config, monkeypatch,
):
    called = []
    monkeypatch.setattr(
        "hermes_cli.model_switch.list_authenticated_providers",
        lambda **kwargs: called.append(kwargs),
    )
    runner = _make_runner()
    runner._executor_closing = True

    result = await runner._handle_model_command(_make_event())

    assert "Gateway executor unavailable; model switch was not applied" in result
    assert called == []
    assert runner._session_model_overrides == {}


@pytest.mark.asyncio
async def test_model_command_executor_submission_failure_fails_closed(
    _isolated_config, monkeypatch,
):
    class RejectingExecutor:
        _shutdown = False

        def submit(self, *args, **kwargs):
            raise RuntimeError("injected submission rejection")

        def shutdown(self, **kwargs):
            self._shutdown = True

    called = []
    monkeypatch.setattr(
        "hermes_cli.model_switch.list_authenticated_providers",
        lambda **kwargs: called.append(kwargs),
    )
    runner = _make_runner()
    runner._executor = RejectingExecutor()
    try:
        result = await runner._handle_model_command(_make_event())
    finally:
        runner._shutdown_executor()

    assert "Gateway executor unavailable; model switch was not applied" in result
    assert called == []
    assert runner._session_model_overrides == {}


@pytest.mark.asyncio
async def test_model_command_executor_transport_failure_fails_closed_without_mutation(
    _isolated_config,
):
    future = concurrent.futures.Future()
    future.set_exception(RuntimeError("injected executor transport failure"))
    runner = _make_runner()
    runner._submit_in_executor_with_context = lambda *_args: future

    result = await runner._handle_model_command(_make_event())

    assert "Gateway executor unavailable; model switch was not applied" in result
    assert runner._session_model_overrides == {}
    assert getattr(runner, "_pending_model_notes", {}) == {}


@pytest.mark.asyncio
async def test_model_command_owned_executor_works_with_closed_default_executor(
    _isolated_config, monkeypatch,
):
    """The model handler must not touch asyncio's closed default executor."""
    loop = asyncio.get_running_loop()
    original_default_executor = loop._default_executor
    closed_default_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    closed_default_executor.shutdown(wait=True)

    def _poison_bridge(*args, **kwargs):
        raise AssertionError("model command used an asyncio executor bridge")

    observed_threads = []

    def _fake_list_authenticated_providers(**kwargs):
        observed_threads.append(threading.current_thread())
        return []

    loop._default_executor = closed_default_executor
    monkeypatch.setattr(loop, "run_in_executor", _poison_bridge)
    monkeypatch.setattr(asyncio, "wrap_future", _poison_bridge)
    monkeypatch.setattr(slash_commands.asyncio, "to_thread", _poison_bridge)
    monkeypatch.setattr(
        "hermes_cli.model_switch.list_authenticated_providers",
        _fake_list_authenticated_providers,
    )
    runner = _make_runner()
    owned_threads = ()
    try:
        result = await runner._handle_model_command(_make_event())
    finally:
        executor = getattr(runner, "_executor", None)
        owned_threads = tuple(getattr(executor, "_threads", ()))
        runner._shutdown_executor()
        for thread in owned_threads:
            thread.join(timeout=1)
        loop._default_executor = original_default_executor

    assert result is not None
    assert observed_threads
    assert all(t.name.startswith("hermes-gateway") for t in observed_threads)
    assert all(not thread.is_alive() for thread in owned_threads)


@pytest.mark.asyncio
async def test_model_owned_executor_preserves_callable_exception():
    runner = _make_runner()

    def _raise_callable_error():
        raise ValueError("callable failure is not admission failure")

    try:
        with pytest.raises(ValueError, match="callable failure"):
            await runner._run_model_blocking(_raise_callable_error)
    finally:
        runner._shutdown_executor()
