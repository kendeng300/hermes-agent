"""Synthetic adapter deadline and diagnostic contracts; no network or sleeps."""
import json
import threading
from types import SimpleNamespace

import httpx
import pytest

from agent import auxiliary_client as auxiliary
from agent import codex_responses_adapter as conversion


@pytest.fixture
def scenario(monkeypatch):
    state = SimpleNamespace(now=100.0, preparation=0.0, request=0.0, stream=0.0,
                            cleanup=0.0, decode=0.0, error=None, terminal="completed",
                            calls=[], timers=[], evicted=[], client_closes=0,
                            stream_closes=0, stream_started=0, after_terminal=False,
                            fire_timers=True, close_entered=None, close_release=None)

    def advance(seconds):
        state.now += seconds
        for timer in state.timers:
            if (state.fire_timers and timer.started and not timer.cancelled
                    and not timer.fired and state.now >= timer.at):
                timer.fired = True
                timer.callback()

    class Timer:
        def __init__(self, interval, callback):
            self.interval, self.callback = interval, callback
            self.started = self.cancelled = self.fired = False
            state.timers.append(self)

        def start(self):
            self.started = True
            self.at = state.now + self.interval

        def cancel(self):
            self.cancelled = True

    original_conversion = conversion._chat_messages_to_responses_input

    def convert(*args, **kwargs):
        advance(state.preparation)
        return original_conversion(*args, **kwargs)

    class Part:
        type = "output_text"

        @property
        def text(self):
            advance(state.decode)
            return "synthetic result"

    class Stream:
        def __iter__(self):
            state.stream_started += 1
            advance(state.stream)
            yield SimpleNamespace(type="response.output_item.done", item=SimpleNamespace(
                type="message", content=[Part()]))
            if state.terminal:
                yield SimpleNamespace(type="response." + state.terminal,
                                      response=SimpleNamespace(status=state.terminal, usage=None))
                state.after_terminal = True
                raise AssertionError("consumer must stop at the terminal frame")

        def close(self):
            state.stream_closes += 1
            advance(state.cleanup)

    def create(**kwargs):
        state.calls.append(kwargs)
        advance(state.request)
        if state.error is not None:
            raise state.error
        return Stream()

    def close_client():
        state.client_closes += 1
        if state.close_entered is not None:
            state.close_entered.set()
            assert state.close_release.wait(2.0), "synthetic close must be released"

    client = SimpleNamespace(base_url="https://fixture.invalid/codex",
                             responses=SimpleNamespace(create=create), close=close_client)
    state.client = client
    state.adapter = auxiliary._CodexCompletionsAdapter(client, "configured-model")
    monkeypatch.setattr(auxiliary, "time", SimpleNamespace(monotonic=lambda: state.now))
    monkeypatch.setattr(auxiliary, "threading", SimpleNamespace(
        Event=threading.Event, Lock=threading.Lock, Timer=Timer))
    monkeypatch.setattr(auxiliary, "_evict_cached_client_instance", state.evicted.append)
    monkeypatch.setattr(conversion, "_chat_messages_to_responses_input", convert)
    monkeypatch.setattr("tools.interrupt.is_interrupted", lambda: False)
    return state


def invoke(state, timeout=10.0):
    return state.adapter.create(messages=[{"role": "user", "content": "synthetic input"}],
                                timeout=timeout)


def assert_safe_timing(value):
    timing = value.codex_call_timing
    assert timing["schema_version"] == 1
    assert timing["phase"] in {"preparation", "request", "stream", "cleanup", "decode", "complete"}
    assert timing["outcome"] in {"returned", "deadline_exhausted", "failed", "interrupted"}
    assert timing["terminal_event"] in {"none", "completed", "incomplete", "failed"}
    assert type(timing["timeout_fired"]) is bool
    assert timing["cause_type"] in {"none", "TimeoutError", "APITimeoutError", "APIConnectionError",
                                     "ReadTimeout", "ReadError", "RuntimeError", "InterruptedError", "OtherError"}
    numeric = {"elapsed_ms", "preparation_ms", "request_ms", "stream_ms", "cleanup_ms", "decode_ms"}
    for name in numeric | ({"first_event_ms"} if "first_event_ms" in timing else set()):
        assert type(timing[name]) is int and 0 <= timing[name] <= 2_147_483_647
    assert set(timing) <= numeric | {"schema_version", "phase", "outcome", "first_event_ms",
                                    "terminal_event", "timeout_fired", "cause_type"}
    assert "private" not in json.dumps(timing, allow_nan=False)
    return timing


@pytest.mark.parametrize("preparation", [10.0, 11.0])
def test_exhausted_preparation_never_dispatches_or_starts_fresh_timer(scenario, preparation):
    scenario.preparation = preparation
    with pytest.raises(TimeoutError) as caught:
        invoke(scenario)
    assert not scenario.calls and not scenario.timers
    timing = assert_safe_timing(caught.value)
    assert timing["phase"] == "preparation"
    assert timing["outcome"] == "deadline_exhausted"
    assert timing["preparation_ms"] == int(preparation * 1000)
    assert timing["request_ms"] == 0 and not timing["timeout_fired"]


def test_dispatch_and_timer_receive_only_original_remaining_allowance(scenario):
    scenario.preparation, scenario.request, scenario.stream = 4.0, 1.0, 1.0
    result = invoke(scenario)
    assert scenario.calls[0]["timeout"] == 6.0
    assert scenario.timers[0].interval == 6.0 and scenario.timers[0].cancelled
    assert result.choices[0].message.content == "synthetic result"
    timing = assert_safe_timing(result)
    assert timing["phase"] == "complete" and timing["outcome"] == "returned"
    assert timing["elapsed_ms"] == timing["first_event_ms"] == 6000
    assert timing["preparation_ms"] == 4000 and timing["request_ms"] == timing["stream_ms"] == 1000
    assert timing["terminal_event"] == "completed"
    assert not scenario.after_terminal and scenario.stream_closes == 1


@pytest.mark.parametrize("phase", ["cleanup", "decode"])
@pytest.mark.parametrize("duration", [6.0, 7.0])
def test_terminal_does_not_authorize_late_cleanup_or_decode_success(scenario, phase, duration):
    scenario.request = scenario.stream = 2.0
    setattr(scenario, phase, duration)
    with pytest.raises(TimeoutError) as caught:
        invoke(scenario)
    timing = assert_safe_timing(caught.value)
    assert timing["phase"] == phase and timing["outcome"] == "deadline_exhausted"
    assert timing["terminal_event"] == "completed"
    assert timing[phase + "_ms"] == int(duration * 1000)
    assert scenario.client_closes == len(scenario.evicted) == 1
    assert scenario.timers[0].cancelled


@pytest.mark.parametrize("phase", ["request", "stream"])
def test_timeout_reports_originating_phase_and_retains_eviction(scenario, phase):
    setattr(scenario, phase, 11.0)
    if phase == "request":
        scenario.error = RuntimeError("private bearer response")
    scenario.cleanup = 2.0
    with pytest.raises(TimeoutError) as caught:
        invoke(scenario)
    timing = assert_safe_timing(caught.value)
    assert timing["phase"] == phase and timing["timeout_fired"]
    assert timing["outcome"] == "deadline_exhausted"
    assert timing["cause_type"] == ("RuntimeError" if phase == "request" else "TimeoutError")
    assert timing["cleanup_ms"] == (0 if phase == "request" else 2000)
    assert scenario.client_closes == len(scenario.evicted) == 1
    assert scenario.timers[0].cancelled


@pytest.mark.parametrize("error", [RuntimeError("private response"), InterruptedError("private interrupt")])
def test_early_errors_keep_type_and_safe_failure_evidence(scenario, error):
    scenario.request, scenario.error = 2.0, error
    with pytest.raises(type(error)) as caught:
        invoke(scenario)
    assert caught.value is error
    timing = assert_safe_timing(error)
    assert timing["phase"] == "request" and not timing["timeout_fired"]
    assert timing["outcome"] == ("interrupted" if isinstance(error, InterruptedError) else "failed")
    assert not scenario.evicted and scenario.timers[0].cancelled


@pytest.mark.parametrize("timeout", [None, httpx.Timeout(12.5)])
def test_unset_and_timeout_objects_keep_their_existing_transport_contract(scenario, timeout):
    result = invoke(scenario, timeout=timeout)
    assert not scenario.timers
    if timeout is None:
        assert "timeout" not in scenario.calls[0]
    else:
        assert scenario.calls[0]["timeout"] is timeout
    assert assert_safe_timing(result)["outcome"] == "returned"


def test_eof_with_usable_content_keeps_existing_completion_policy(scenario):
    scenario.terminal = None
    result = invoke(scenario)
    assert result.choices[0].message.content == "synthetic result"
    assert assert_safe_timing(result)["terminal_event"] == "none"


def test_timer_callback_already_scheduled_before_cancel_cannot_close_successful_client(scenario):
    invoke(scenario)
    timer = scenario.timers[0]
    assert timer.cancelled
    scenario.now = 111.0
    timer.callback()  # Callback delivery after cancel; no real thread or sleep.
    assert scenario.client_closes == 0 and not scenario.evicted


def test_timeout_callback_owns_close_and_eviction_once(scenario):
    scenario.stream = 11.0
    with pytest.raises(TimeoutError):
        invoke(scenario)
    scenario.timers[0].callback()  # Second contender after the timeout owner.
    assert scenario.client_closes == len(scenario.evicted) == 1


@pytest.mark.parametrize("duration", [10.0, 11.0])
def test_late_create_return_is_closed_without_starting_stream_iteration(scenario, duration):
    scenario.request, scenario.cleanup = duration, 2.0
    with pytest.raises(TimeoutError) as caught:
        invoke(scenario)
    assert scenario.stream_started == 0 and scenario.stream_closes == 1
    timing = assert_safe_timing(caught.value)
    assert timing["phase"] == "request" and timing["stream_ms"] == 0
    assert timing["request_ms"] == int(duration * 1000) and timing["cleanup_ms"] == 2000
    assert "first_event_ms" not in timing and timing["terminal_event"] == "none"


def test_original_deadline_classifies_error_even_when_timer_callback_is_delayed(scenario):
    scenario.fire_timers = False
    scenario.request, scenario.error = 11.0, RuntimeError("private lower-level response")
    with pytest.raises(TimeoutError) as caught:
        invoke(scenario)
    assert caught.value.__cause__ is scenario.error
    timing = assert_safe_timing(caught.value)
    assert timing["phase"] == "request" and timing["outcome"] == "deadline_exhausted"
    assert timing["cause_type"] == "RuntimeError"
    assert scenario.client_closes == len(scenario.evicted) == 1


def test_timeout_identity_is_evicted_before_a_blocking_close(scenario):
    scenario.stream = 11.0
    scenario.close_entered, scenario.close_release = threading.Event(), threading.Event()
    errors = []

    def run():
        try:
            invoke(scenario)
        except Exception as exc:
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert scenario.close_entered.wait(2.0), "timeout must enter the synthetic close"
        evicted_before_release = list(scenario.evicted)
    finally:
        scenario.close_release.set()
        worker.join(2.0)
    assert not worker.is_alive()
    assert evicted_before_release == [scenario.client]
    assert scenario.client_closes == 1 and len(errors) == 1 and isinstance(errors[0], TimeoutError)
