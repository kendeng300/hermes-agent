"""Prepared references hydrate existing native delegation, not a new runner."""
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from tools import delegate_tool as delegate


def reference(path, text):
    raw = text.encode("utf-8") if isinstance(text, str) else text
    path.write_bytes(raw)
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


@pytest.fixture
def local_backend(monkeypatch):
    from tools import terminal_tool
    monkeypatch.setattr(terminal_tool, "_active_environments", {})
    monkeypatch.setattr(terminal_tool, "_task_env_overrides", {})
    monkeypatch.setattr(terminal_tool, "_get_env_config", lambda: {"env_type": "local"})


@pytest.fixture
def runtime():
    started = time.monotonic()
    return {"job_id": "synthetic", "run_id": "synthetic-run", "dispatch_monotonic": started,
            "deadline_monotonic": started + 600, "max_elapsed_seconds": 600,
            "max_concurrent_children": 7, "leaf_only": True, "publication_authority": "advisory"}


@pytest.fixture
def native_path(monkeypatch, local_backend):
    import run_agent
    agent_dispatch = run_agent.AIAgent._dispatch_delegate_task
    builds, constructors, requests, credential_calls, closed = [], [], [], [], []
    parent = SimpleNamespace(_delegate_depth=0, _active_children=[],
        _active_children_lock=threading.Lock(), _current_task_id="synthetic-parent",
        model="synthetic-model", provider="openai", base_url="https://example.invalid/v1",
        api_key="synthetic", api_mode="responses", platform="cron", enabled_toolsets=["file"])
    monkeypatch.setattr(delegate, "is_spawn_paused", lambda: False)
    monkeypatch.setattr(delegate, "_load_config", lambda: {"max_iterations": 20})
    monkeypatch.setattr(delegate, "_resolve_effective_delegation_model", lambda **kwargs: (None, None))

    def credentials(*args):
        credential_calls.append(True)
        return {"model": None, "provider": None, "base_url": None, "api_key": None,
                "api_mode": None, "request_overrides": None, "max_output_tokens": None,
                "command": None, "args": None}

    real_build = delegate._build_child_agent

    def agent(**kwargs):
        constructors.append(kwargs)
        index = int(kwargs["log_prefix"].removeprefix("[subagent-").removesuffix("]"))

        def conversation(**call):
            requests.append((index, call))
            return {"final_response": "Synthetic independent review", "completed": True, "api_calls": 1}

        return SimpleNamespace(run_conversation=conversation, close=lambda: closed.append(index),
            _interrupt_requested=False,
            _active_children=[], _active_tool_threads=[], _active_tool_threads_lock=threading.Lock(),
            session_id="synthetic-child", tool_progress_callback=None)

    def build(**kwargs):
        builds.append(kwargs)
        return real_build(**kwargs)

    monkeypatch.setattr(delegate, "_resolve_delegation_credentials", credentials)
    monkeypatch.setattr(delegate, "_resolve_child_credential_pool", lambda *args: None)
    monkeypatch.setattr(delegate, "_build_child_agent", build)
    monkeypatch.setattr(run_agent, "AIAgent", agent)
    return SimpleNamespace(parent=parent, builds=builds, requests=requests,
                           credential_calls=credential_calls, closed=closed, constructors=constructors,
                           agent_dispatch=agent_dispatch)


def read_ref(ref, limit=4096):
    return delegate._read_prepared_reference(ref, max_bytes=limit, task_id="synthetic-parent")


def test_exact_complete_utf8_not_paginated_or_normalized(tmp_path, local_backend):
    text = "Required instructions\r\n" + ("完整 supplied evidence\n" * 600)
    ref = reference(tmp_path / "input.txt", text)
    assert read_ref(ref, limit=65536) == text


@pytest.mark.parametrize("fault", ["missing", "extra", "bool_bytes", "negative_bytes", "zero_bytes",
                                   "wrong_size", "hash", "short_hash", "uppercase_hash", "relative", "null"])
def test_reference_shape_is_strict(tmp_path, local_backend, fault):
    ref = reference(tmp_path / "input.txt", "Synthetic evidence")
    if fault == "missing": ref.pop("sha256")
    elif fault == "extra": ref["provider"] = "not-allowed"
    elif fault == "bool_bytes": ref["bytes"] = True
    elif fault == "negative_bytes": ref["bytes"] = -1
    elif fault == "zero_bytes": ref["bytes"] = 0
    elif fault == "wrong_size": ref["bytes"] += 1
    elif fault == "hash": ref["sha256"] = "0" * 64
    elif fault == "short_hash": ref["sha256"] = "abc"
    elif fault == "uppercase_hash": ref["sha256"] = ref["sha256"].upper()
    elif fault == "relative": ref["path"] = "input.txt"
    elif fault == "null": ref = None
    with pytest.raises(ValueError):
        read_ref(ref)


@pytest.mark.parametrize("fault", ["absent", "directory", "symlink", "directory_symlink", "fifo",
                                   "invalid_utf8", "nul", "overbound", "credential"])
def test_unsafe_or_incomplete_file_never_hydrates(tmp_path, local_backend, fault):
    ref = reference(tmp_path / "input.txt", "Synthetic evidence")
    path = Path(ref["path"])
    if fault == "absent": path.unlink()
    elif fault == "directory": path.unlink(); path.mkdir()
    elif fault == "symlink":
        target = tmp_path / "target.txt"
        path.rename(target)
        path.symlink_to(target)
    elif fault == "directory_symlink":
        directory = tmp_path / "real"
        directory.mkdir()
        path.rename(directory / "input.txt")
        (tmp_path / "alias").symlink_to(directory, target_is_directory=True)
        ref["path"] = str(tmp_path / "alias" / "input.txt")
    elif fault == "fifo": path.unlink(); os.mkfifo(path)
    elif fault == "invalid_utf8": ref = reference(path, b"\xff")
    elif fault == "nul": ref = reference(path, b"a\0b")
    elif fault == "overbound": ref = reference(path, "x" * 4097)
    elif fault == "credential": ref = reference(tmp_path / ".env", "SYNTHETIC=not-a-secret")
    with pytest.raises(ValueError):
        read_ref(ref)


def test_redaction_change_refuses_instead_of_claiming_different_verified_bytes(tmp_path, monkeypatch, local_backend):
    import agent.redact
    ref = reference(tmp_path / "input.txt", "Synthetic evidence")
    monkeypatch.setattr(agent.redact, "redact_sensitive_text", lambda text, **kwargs: "[redacted]")
    with pytest.raises(ValueError):
        read_ref(ref)


@pytest.mark.parametrize("backend", ["ssh", "docker", "unknown"])
def test_nonlocal_backend_never_opens_host_input(tmp_path, monkeypatch, local_backend, backend):
    from tools import terminal_tool
    ref = reference(tmp_path / "input.txt", "Synthetic evidence")
    monkeypatch.setattr(terminal_tool, "_get_env_config", lambda: {"env_type": backend})
    monkeypatch.setattr(os, "open", lambda *args, **kwargs: pytest.fail("host open forbidden"))
    with pytest.raises(ValueError):
        read_ref(ref)


@pytest.mark.parametrize("fault", ["config_error", "resolve_error", "active_unknown", "task_remote_override"])
def test_unresolved_or_task_remote_backend_fails_closed(tmp_path, monkeypatch, local_backend, fault):
    from tools import terminal_tool
    ref = reference(tmp_path / "input.txt", "Synthetic evidence")
    def failed(*args):
        raise RuntimeError("Synthetic configuration failure")
    if fault == "config_error": monkeypatch.setattr(terminal_tool, "_get_env_config", failed)
    elif fault == "resolve_error": monkeypatch.setattr(terminal_tool, "_resolve_container_task_id", failed)
    elif fault == "active_unknown": terminal_tool._active_environments["default"] = object()
    else: terminal_tool._task_env_overrides["synthetic-parent"] = {"env_type": "ssh"}
    monkeypatch.setattr(os, "open", lambda *args, **kwargs: pytest.fail("unresolved host open forbidden"))
    with pytest.raises(ValueError):
        read_ref(ref)


def test_path_replacement_during_descriptor_read_is_rejected(tmp_path, monkeypatch, local_backend):
    path = tmp_path / "input.txt"
    ref = reference(path, "Synthetic evidence")
    replacement = tmp_path / "replacement.txt"
    replacement.write_text("Synthetic evidence")
    original = os.read
    changed = []

    def replacing(fd, size):
        data = original(fd, size)
        if not changed:
            replacement.replace(path)
            changed.append(True)
        return data

    monkeypatch.setattr(os, "read", replacing)
    with pytest.raises(ValueError):
        read_ref(ref)


@pytest.mark.parametrize("fault", ["in_place", "read_error"])
def test_mutation_and_read_errors_never_become_verified_input(tmp_path, monkeypatch, local_backend, fault):
    path = tmp_path / "input.txt"
    ref = reference(path, "Synthetic complete input")
    original = os.read
    def changed_read(fd, size):
        if fault == "read_error":
            raise OSError("Synthetic private failure details")
        data = original(fd, size)
        path.write_bytes(b"x" * ref["bytes"])
        return data
    monkeypatch.setattr(os, "read", changed_read)
    with pytest.raises(ValueError) as caught:
        read_ref(ref)
    assert "Synthetic private failure details" not in str(caught.value)


def test_no_reference_keeps_existing_first_message_and_system_inputs(native_path):
    case = native_path
    result = json.loads(delegate.delegate_task(goal="Unchanged goal", context="Unchanged context", parent_agent=case.parent))
    assert result["results"][0]["status"] == "completed"
    assert case.builds[0]["goal"] == "Unchanged goal"
    assert case.builds[0]["context"] == "Unchanged context"
    assert case.requests[0][1]["user_message"] == "Unchanged goal"
    assert not case.parent._active_children


def test_prepared_bytes_only_enter_initial_user_message(tmp_path, native_path):
    case = native_path
    text = "Complete prepared instructions\nComplete synthetic evidence\n"
    ref = reference(tmp_path / "input.txt", text)
    result = json.loads(delegate.delegate_task(goal="Review independently", context="Role contract",
        prepared_input_reference=ref, parent_agent=case.parent))
    assert result["results"][0]["status"] == "completed"
    assert case.builds[0]["goal"] == "Review independently"
    assert case.builds[0]["context"] == "Role contract"
    assert len(case.requests) == 1
    message = case.requests[0][1]["user_message"]
    assert message.startswith("Review independently") and message.count(text) == 1
    assert ref["sha256"] in message
    system = case.constructors[0]["ephemeral_system_prompt"]
    assert "Review independently" in system and "Role contract" in system and text not in system
    assert case.constructors[0]["provider"] == "openai"
    assert not case.parent._active_children and case.closed == [0]


def test_referenced_bundle_reaches_all_seven_existing_native_workers(tmp_path, native_path, runtime):
    case = native_path
    texts = [f"Full instructions and independent synthetic seat evidence {index}\n" for index in range(7)]
    tasks = [{"goal": f"Independent seat {index}", "context": f"Role {index}", "role": "orchestrator",
              "prepared_input_reference": reference(tmp_path / f"input{index}.txt", text)}
             for index, text in enumerate(texts)]
    bundle = reference(tmp_path / "tasks.json", json.dumps({"tasks": tasks}))
    with delegate.job_runtime_scope(runtime):
        result = json.loads(delegate.delegate_task(tasks_reference=bundle, parent_agent=case.parent,
                                                 deadline_elapsed_seconds=270))
    assert len(result["results"]) == len(case.builds) == len(case.requests) == 7
    assert all(row["role"] == "leaf" and row["max_iterations"] == 20 for row in case.builds)
    assert {index for index, _ in case.requests} == set(range(7))
    for index, call in case.requests:
        assert call["user_message"].count(texts[index]) == 1
        assert all(text not in call["user_message"] for i, text in enumerate(texts) if i != index)
    assert runtime["max_elapsed_seconds"] == 600


def test_one_bad_reference_prevents_all_credential_resolution_and_children(tmp_path, native_path):
    case = native_path
    first = reference(tmp_path / "first.txt", "Valid complete input")
    second = reference(tmp_path / "second.txt", "Invalid digest input")
    second["sha256"] = "0" * 64
    result = json.loads(delegate.delegate_task(tasks=[
        {"goal": "First", "prepared_input_reference": first},
        {"goal": "Second", "prepared_input_reference": second}], parent_agent=case.parent))
    assert result.get("error") and not case.credential_calls and not case.builds and not case.requests


@pytest.mark.parametrize("text", [
    '{"tasks": [], "tasks": [{"goal":"shadow"}]}',
    '{"tasks": [{"goal":"a", "goal":"b"}]}',
    '{"tasks": [{"goal":"a", "reasoning_required":NaN}]}',
    '{"tasks": [{"goal":"a", "provider":"unapproved"}]}',
    '{"tasks": [{"goal":"a", "acp_command":"unapproved"}]}',
    '{"tasks": [{"goal":"a", "toolsets":["unapproved"]}]}',
    '{"tasks": [{"goal":false}]}',
    '{"tasks": [{"goal":"a", "context":{}}]}',
    '{"tasks": [{"goal":"a", "prepared_input_reference":null}]}',
    '{"tasks": [{"goal":"a", "tasks_reference":{}}]}',
    '{"tasks": [], "deadline_elapsed_seconds":900}',
    '{"tasks": []}',
])
def test_bundle_cannot_override_authority_or_hide_ambiguous_json(tmp_path, native_path, text):
    case = native_path
    bundle = reference(tmp_path / "tasks.json", text)
    result = json.loads(delegate.delegate_task(tasks_reference=bundle, parent_agent=case.parent))
    assert result.get("error") and not case.credential_calls and not case.builds


@pytest.mark.parametrize("inline", [{"goal": "ambiguous"}, {"tasks": [{"goal": "ambiguous"}]}, {"context": "ambiguous"}])
def test_bundle_and_inline_task_inputs_are_mutually_exclusive(tmp_path, native_path, inline):
    case = native_path
    bundle = reference(tmp_path / "tasks.json", '{"tasks":[{"goal":"Reference task"}]}')
    result = json.loads(delegate.delegate_task(tasks_reference=bundle, parent_agent=case.parent, **inline))
    assert result.get("error") and not case.credential_calls and not case.builds


def test_expired_original_phase_before_read_never_opens_input(tmp_path, native_path, runtime, monkeypatch):
    case = native_path
    ref = reference(tmp_path / "input.txt", "Complete input")
    runtime["dispatch_monotonic"] -= 300
    monkeypatch.setattr(os, "open", lambda *args, **kwargs: pytest.fail("expired input read"))
    with delegate.job_runtime_scope(runtime):
        result = json.loads(delegate.delegate_task(goal="Review", prepared_input_reference=ref,
            parent_agent=case.parent, deadline_elapsed_seconds=270))
    assert "deadline" in result["error"].lower() and not case.credential_calls and not case.builds


def test_reference_fields_reach_registered_and_agent_dispatch(monkeypatch):
    import run_agent
    from tools.registry import registry
    calls = []
    monkeypatch.setattr(delegate, "delegate_task", lambda **kwargs: calls.append(kwargs) or '{}')
    args = {"tasks_reference": {"path": "/synthetic/tasks.json", "sha256": "a"*64, "bytes": 10},
            "prepared_input_reference": None, "deadline_elapsed_seconds": 270}
    parent = SimpleNamespace(_delegate_depth=0)
    run_agent.AIAgent._dispatch_delegate_task(parent, args)
    registry.dispatch("delegate_task", args, parent_agent=parent)
    assert len(calls) == 2
    assert all(call["tasks_reference"] == args["tasks_reference"] and call["deadline_elapsed_seconds"] == 270 for call in calls)
    schema = delegate.DELEGATE_TASK_SCHEMA["parameters"]["properties"]
    assert "tasks_reference" in schema and "prepared_input_reference" in schema
    assert "prepared_input_reference" in schema["tasks"]["items"]["properties"]


def test_registered_handler_cannot_bypass_hidden_task_field_filter_via_bundle(tmp_path, native_path, runtime):
    from tools.registry import registry
    case = native_path
    bundle = reference(tmp_path / "tasks.json", '{"tasks":[{"goal":"Review","acp_command":"synthetic"}]}')
    with delegate.job_runtime_scope(runtime):
        result = json.loads(registry.dispatch("delegate_task", {"tasks_reference": bundle}, parent_agent=case.parent))
    assert result.get("error") and not case.credential_calls and not case.builds


@pytest.mark.parametrize("route", ["registry", "agent"])
def test_real_model_facing_dispatch_hydrates_first_native_request(tmp_path, native_path, runtime, route):
    from tools.registry import registry
    case = native_path
    text = "Complete instruction document\nComplete synthetic facts\n"
    prepared = reference(tmp_path / "input.txt", text)
    bundle = reference(tmp_path / "tasks.json", json.dumps({"tasks": [
        {"goal": "Independent review", "context": "Unchanged role", "prepared_input_reference": prepared}]}))
    args = {"tasks_reference": bundle, "deadline_elapsed_seconds": 270}
    with delegate.job_runtime_scope(runtime):
        result = json.loads(registry.dispatch("delegate_task", args, parent_agent=case.parent) if route == "registry"
                            else case.agent_dispatch(case.parent, args))
    assert result["results"][0]["status"] == "completed"
    assert len(case.requests) == len(case.builds) == 1
    assert text in case.requests[0][1]["user_message"]
    assert text not in case.constructors[0]["ephemeral_system_prompt"]
    assert not case.parent._active_children and case.closed == [0]


def test_bundle_and_top_level_prepared_reference_are_mutually_exclusive(tmp_path, native_path):
    prepared = reference(tmp_path / "input.txt", "Complete input")
    bundle = reference(tmp_path / "tasks.json", json.dumps({"tasks": [
        {"goal": "Review", "prepared_input_reference": prepared}]}))
    result = json.loads(delegate.delegate_task(tasks_reference=bundle, prepared_input_reference=prepared,
                                             parent_agent=native_path.parent))
    assert result.get("error") and not native_path.credential_calls and not native_path.builds


@pytest.mark.parametrize("inline", [
    {"tasks": [{"goal": "Batch"}]},
    {"goal": "Single", "tasks": [{"goal": "Batch"}]},
])
def test_top_level_prepared_input_cannot_be_misapplied_to_batch(tmp_path, native_path, inline):
    ref = reference(tmp_path / "input.txt", "Complete single input")
    result = json.loads(delegate.delegate_task(**inline, prepared_input_reference=ref, parent_agent=native_path.parent))
    assert result.get("error") and not native_path.credential_calls and not native_path.builds


def test_task_bundle_limit_is_independent_of_input_limit(tmp_path, native_path, monkeypatch):
    monkeypatch.setattr(delegate, "_PREPARED_TASKS_MAX_BYTES", 24, raising=False)
    bundle = reference(tmp_path / "tasks.json", '{"tasks":[{"goal":"Complete goal exceeds synthetic task-file cap"}]}')
    result = json.loads(delegate.delegate_task(tasks_reference=bundle, parent_agent=native_path.parent))
    assert result.get("error") and not native_path.credential_calls and not native_path.builds


def test_reference_batch_preserves_existing_three_task_limit(tmp_path, native_path, runtime):
    case = native_path
    runtime["max_concurrent_children"] = 3
    bundle = reference(tmp_path / "tasks.json", json.dumps({"tasks": [{"goal": f"Seat {i}"} for i in range(7)]}))
    with delegate.job_runtime_scope(runtime):
        result = json.loads(delegate.delegate_task(tasks_reference=bundle, parent_agent=case.parent))
    assert result.get("error") and not case.credential_calls and not case.builds
    assert runtime["max_concurrent_children"] == 3


def test_aggregate_limit_is_checked_before_any_child(tmp_path, native_path, monkeypatch):
    case = native_path
    monkeypatch.setattr(delegate, "_PREPARED_BATCH_MAX_BYTES", 30, raising=False)
    tasks = [{"goal": f"Seat {i}", "prepared_input_reference": reference(tmp_path / f"seat{i}.txt", "x" * 20)}
             for i in range(2)]
    result = json.loads(delegate.delegate_task(tasks=tasks, parent_agent=case.parent))
    assert result.get("error") and not case.credential_calls and not case.builds


def test_verified_input_is_not_reopened_by_workers(tmp_path, native_path, monkeypatch):
    case = native_path
    path = tmp_path / "input.txt"
    text = "Verified complete initial input"
    ref = reference(path, text)
    original_build = delegate._build_child_agent
    def mutate_after_preflight(**kwargs):
        path.write_text("Changed after successful preflight")
        return original_build(**kwargs)
    monkeypatch.setattr(delegate, "_build_child_agent", mutate_after_preflight)
    result = json.loads(delegate.delegate_task(goal="Review", prepared_input_reference=ref, parent_agent=case.parent))
    assert result["results"][0]["status"] == "completed"
    assert text in case.requests[0][1]["user_message"]
    assert "Changed after" not in case.requests[0][1]["user_message"]


@pytest.mark.parametrize("stage", ["read", "build"])
def test_original_phase_expiry_during_input_or_construction_is_not_renewed(tmp_path, native_path, runtime, monkeypatch, stage):
    case = native_path
    ref = reference(tmp_path / "input.txt", "Complete input")
    def expire():
        delegate._DELEGATION_DEADLINE.set((runtime["job_id"], runtime["run_id"], time.monotonic() - 1))
    if stage == "read":
        saved = os.read
        def expired_read(*args):
            result = saved(*args)
            expire()
            return result
        monkeypatch.setattr(os, "read", expired_read)
    else:
        saved = delegate._build_child_agent
        def expired_build(**kwargs):
            result = saved(**kwargs)
            expire()
            return result
        monkeypatch.setattr(delegate, "_build_child_agent", expired_build)
    with delegate.job_runtime_scope(runtime):
        result = json.loads(delegate.delegate_task(goal="Review", prepared_input_reference=ref,
            parent_agent=case.parent, deadline_elapsed_seconds=270))
    assert "deadline" in result["error"].lower() and not case.requests
    if stage == "read": assert not case.credential_calls and not case.builds
    else: assert len(case.builds) == 1 and case.closed == [0] and not case.parent._active_children


@pytest.mark.parametrize("tasks", [
    pytest.param([{"goal": ""}], id="missing-goal"),
    pytest.param("[" * 1500 + "]" * 1500, id="deep-json"),
])
def test_no_reference_keeps_credential_error_before_old_task_validation(native_path, monkeypatch, tasks):
    def unavailable(*args):
        raise ValueError("Synthetic credential resolver unavailable")
    monkeypatch.setattr(delegate, "_resolve_delegation_credentials", unavailable)
    result = json.loads(delegate.delegate_task(tasks=tasks, parent_agent=native_path.parent))
    assert "Synthetic credential resolver unavailable" in result["error"]
    assert not native_path.builds


def test_secret_screening_cannot_be_disabled_by_logging_preference(tmp_path, native_path, monkeypatch):
    import agent.redact
    monkeypatch.setattr(agent.redact, "_REDACT_ENABLED", False)
    # Public synthetic fixture, not an actual credential.
    ref = reference(tmp_path / "input.txt", "Synthetic token sk-proj-abc123def456ghi789jkl012")
    result = json.loads(delegate.delegate_task(goal="Review", prepared_input_reference=ref,
                                             parent_agent=native_path.parent))
    assert result.get("error") and not native_path.credential_calls
    assert not native_path.builds and not native_path.requests
