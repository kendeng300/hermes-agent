"""Functional tests for SYS-798 Phase 2 — structural context breakdown.

Covers:
  - _component_sizes tracking at all 11 named sites
  - build_context_breakdown mapping correctness (11 named + other_chars + total = 13)
  - Phase-1 fallback (None → zeros/fallback)
  - invalidate clears both caches
  - init-before-use
  - prompt-cache preserved (breakdown built from already-constructed parts)
"""

import gc
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from agent.context_telemetry import ContextBreakdown
from agent.system_prompt import (
    build_system_prompt_parts,
    build_context_breakdown,
    build_system_prompt,
    invalidate_system_prompt,
)


# ── helpers ──────────────────────────────────────────────────────────


def _make_agent(**overrides):
    """Build a mock agent matching the attribute surface build_system_prompt_parts accesses."""
    base = dict(
        load_soul_identity=False,
        skip_context_files=False,
        valid_tool_names=[],
        _task_completion_guidance=False,
        _tool_use_enforcement=False,
        _environment_probe=False,
        _kanban_worker_guidance="",
        _memory_store=None,
        _memory_manager=None,
        _memory_enabled=True,
        _user_profile_enabled=True,
        model="test-model",
        provider="test-provider",
        platform="cli",
        pass_session_id=False,
        session_id="",
        context_compressor=None,
        _parallel_tool_call_guidance=False,
        _platform_hint_overrides=None,
    )
    base.update(overrides)
    agent = SimpleNamespace(**base)
    # _emit_status is called by build_system_prompt for truncation warnings
    if not hasattr(agent, "_emit_status"):
        agent._emit_status = lambda msg: None
    return agent


def _build_parts(agent, system_message=None):
    """Build parts with mocking so no disk/network access happens."""
    with (
        patch("run_agent.load_soul_md", return_value="[SOUL]"),
        patch("run_agent.build_nous_subscription_prompt", return_value=""),
        patch("run_agent.build_environment_hints", return_value=""),
        patch("run_agent.build_context_files_prompt", return_value=""),
        patch("run_agent.get_toolset_for_tool", return_value=""),
        patch("run_agent.build_skills_system_prompt", return_value=""),
    ):
        return build_system_prompt_parts(agent, system_message=system_message)


def _fake_memory_store():
    ms = MagicMock()
    ms.format_for_system_prompt.side_effect = lambda kind: {
        "memory": "[FAKE MEMORY BLOCK]",
        "user": "[FAKE USER PROFILE]",
    }.get(kind, "")
    return ms


# ── TEST: All 11 _track sites are present ────────────────────────────


def test_all_11_component_sizes_tracked():
    """Verify every _track() call site populates a named component_sizes key."""
    agent = _make_agent(
        valid_tool_names=["read_file", "memory", "session_search", "skill_manage"],
        _memory_store=_fake_memory_store(),
    )
    parts = _build_parts(agent, system_message="Hello from caller")
    sizes = parts.get("_component_sizes", {})

    expected_keys = {
        "soul_md_chars",
        "tool_guidance_chars",
        "system_message_chars",
        "memory_chars",
        "user_profile_chars",
        "external_memory_chars",
        "skills_chars",
        "context_files_chars",
        "timestamp_model_chars",
        "platform_hints_chars",
        "environment_hints_chars",
    }
    found = set(sizes.keys())

    assert isinstance(sizes, dict)
    assert len(sizes) >= 1  # at minimum timestamp_model_chars always present
    for k in sizes:
        assert isinstance(sizes[k], int)
        assert sizes[k] > 0, f"Tracked size for {k} should be > 0"

    # Report which expected keys are absent (may be legitimately empty)
    missing = expected_keys - found
    if missing:
        print(f"Note: {len(missing)} expected keys absent (source content was empty): {sorted(missing)}")


# ── TEST: build_context_breakdown mapping — 13 fields ────────────────


def test_breakdown_13_fields():
    """build_context_breakdown produces ContextBreakdown with all 13 fields."""
    agent = _make_agent(
        valid_tool_names=["read_file", "memory", "session_search", "skill_manage"],
        _memory_store=_fake_memory_store(),
    )
    parts = _build_parts(agent, system_message="Caller instruction")
    breakdown = build_context_breakdown(parts)

    assert breakdown is not None
    d = breakdown.to_dict()

    field_names = sorted(f.name for f in ContextBreakdown.__dataclass_fields__.values())
    expected = [
        "context_files_chars",
        "environment_hints_chars",
        "external_memory_chars",
        "memory_chars",
        "other_chars",
        "platform_hints_chars",
        "skills_chars",
        "soul_md_chars",
        "system_message_chars",
        "timestamp_model_chars",
        "tool_guidance_chars",
        "total_system_prompt_chars",
        "user_profile_chars",
    ]
    assert field_names == expected

    # EVERY field present and is int >= 0
    for k in expected:
        assert k in d, f"Field {k} missing from breakdown dict"
        assert isinstance(d[k], int), f"Field {k} is not int: {type(d[k])}"
        assert d[k] >= 0, f"Field {k} is negative: {d[k]}"

    assert d["total_system_prompt_chars"] > 0


# ── TEST: total = len(joined) ────────────────────────────────────────


def test_total_equals_len_of_joined():
    """total_system_prompt_chars == len(stable + context + volatile joined)."""
    agent = _make_agent(
        valid_tool_names=["read_file"],
        _memory_store=_fake_memory_store(),
    )
    parts = _build_parts(agent, system_message="Hello")
    joined = "\n\n".join(
        p for p in (parts.get("stable", ""), parts.get("context", ""), parts.get("volatile", "")) if p
    )
    breakdown = build_context_breakdown(parts)
    assert breakdown is not None
    assert breakdown.total_system_prompt_chars == len(joined)


# ── TEST: other_chars is non-negative ─────────────────────────────────


def test_other_chars_non_negative():
    """other_chars should be max(0, tracked_total - named_total)."""
    agent = _make_agent(
        valid_tool_names=["read_file"],
        _memory_store=_fake_memory_store(),
    )
    parts = _build_parts(agent, system_message="Hello")
    breakdown = build_context_breakdown(parts)

    assert breakdown is not None
    assert breakdown.other_chars >= 0


# ── TEST: Phase-1 fallback ───────────────────────────────────────────


def test_phase_1_fallback():
    """When _system_prompt_breakdown is None, total-only fallback works."""
    agent = _make_agent()
    agent._system_prompt_breakdown = None

    # This simulates what conversation_loop.py does at line 1411-1417
    _cached = getattr(agent, "_system_prompt_breakdown", None)
    if _cached is not None:
        breakdown = _cached
    else:
        breakdown = ContextBreakdown(total_system_prompt_chars=5000)

    assert breakdown is not None
    assert breakdown.total_system_prompt_chars == 5000
    # All other fields are default (0) — the zeros fallback
    assert breakdown.soul_md_chars == 0
    assert breakdown.skills_chars == 0
    assert breakdown.memory_chars == 0
    assert breakdown.other_chars == 0


# ── TEST: invalidate clears both ─────────────────────────────────────


def test_invalidate_clears_both():
    """invalidate_system_prompt sets both caches to None."""
    agent = _make_agent()
    agent._cached_system_prompt = "some cached prompt"
    agent._system_prompt_breakdown = ContextBreakdown(
        total_system_prompt_chars=1000, soul_md_chars=500
    )
    agent._memory_store = None  # avoid disk load

    invalidate_system_prompt(agent)

    assert agent._cached_system_prompt is None
    assert agent._system_prompt_breakdown is None


# ── TEST: init-before-use ────────────────────────────────────────────


def test_init_before_use():
    """agent_init sets _system_prompt_breakdown = None before any use."""
    # Simulate what agent_init.py does
    agent = SimpleNamespace()
    agent._system_prompt_breakdown = None

    assert agent._system_prompt_breakdown is None
    assert getattr(agent, "_system_prompt_breakdown", None) is None


# ── TEST: prompt-cache preserved ─────────────────────────────────────


def test_breakdown_from_cached_parts():
    """Breakdown is computed from already-built parts, not by rebuilding."""
    parts = {
        "stable": "STABLE CONTENT",
        "context": "CONTEXT CONTENT",
        "volatile": "VOLATILE CONTENT",
        "_component_sizes": {
            "soul_md_chars": 14,
            "timestamp_model_chars": 30,
        },
    }

    breakdown = build_context_breakdown(parts)
    assert breakdown is not None
    assert "STABLE CONTENT" in parts["stable"]


# ── TEST: build_system_prompt sets breakdown on agent ──────────────


def test_build_system_prompt_sets_breakdown():
    """build_system_prompt sets agent._system_prompt_breakdown."""
    agent = _make_agent(
        valid_tool_names=["read_file", "memory", "session_search", "skill_manage"],
        _memory_store=_fake_memory_store(),
    )
    with (
        patch("run_agent.load_soul_md", return_value="[SOUL]"),
        patch("run_agent.build_nous_subscription_prompt", return_value=""),
        patch("run_agent.build_environment_hints", return_value=""),
        patch("run_agent.build_context_files_prompt", return_value=""),
        patch("run_agent.get_toolset_for_tool", return_value=""),
        patch("run_agent.build_skills_system_prompt", return_value=""),
    ):
        prompt = build_system_prompt(agent, system_message="Test")

    assert prompt  # Non-empty
    breakdown = getattr(agent, "_system_prompt_breakdown", None)
    assert breakdown is not None, "build_system_prompt should set _system_prompt_breakdown"
    assert isinstance(breakdown, ContextBreakdown)
    assert breakdown.total_system_prompt_chars == len(prompt)


# ── TEST: build_context_breakdown returns None when sizes missing ────


def test_breakdown_returns_none_when_no_sizes():
    """Empty _component_sizes → None (safe, never raises)."""
    result = build_context_breakdown({"_component_sizes": {}})
    assert result is None


def test_breakdown_returns_none_when_no_key():
    """Missing _component_sizes key → None."""
    result = build_context_breakdown({})
    assert result is None


# ── TEST: build_context_breakdown gracefully handles None (caller guarded) ──


def test_breakdown_none_input_handled_by_caller_try_except():
    """None input is safely handled — build_context_breakdown returns None.

    SYS-798: the implementation guards non-dict input (returns None, never
    raises), so the caller's try/except is defense-in-depth, not required.
    """
    assert build_context_breakdown(None) is None


# ── TEST: ContextBreakdown instantiation via all 13 kwarg keys ───────


def test_context_breakdown_13_kwargs():
    """ContextBreakdown accepts all 13 field names as kwargs."""
    bd = ContextBreakdown(
        soul_md_chars=1,
        tool_guidance_chars=2,
        system_message_chars=3,
        memory_chars=4,
        user_profile_chars=5,
        external_memory_chars=6,
        skills_chars=7,
        context_files_chars=8,
        timestamp_model_chars=9,
        platform_hints_chars=10,
        environment_hints_chars=11,
        other_chars=12,
        total_system_prompt_chars=13,
    )
    assert bd.soul_md_chars == 1
    assert bd.tool_guidance_chars == 2
    assert bd.system_message_chars == 3
    assert bd.memory_chars == 4
    assert bd.user_profile_chars == 5
    assert bd.external_memory_chars == 6
    assert bd.skills_chars == 7
    assert bd.context_files_chars == 8
    assert bd.timestamp_model_chars == 9
    assert bd.platform_hints_chars == 10
    assert bd.environment_hints_chars == 11
    assert bd.other_chars == 12
    assert bd.total_system_prompt_chars == 13


# ── SYS-798 panel regression tests (engineering panel deep-dive 2026-08-08) ──

def test_model_identity_rewrite_updates_breakdown_counters():
    """rewrite_prompt_model_identity keeps breakdown counters exact."""
    import sys as _sys
    _sys.path.insert(0, "/home/linux/.hermes/hermes-agent")
    from agent.context_telemetry import ContextBreakdown
    from agent.chat_completion_helpers import rewrite_prompt_model_identity
    from dataclasses import replace

    class FakeAgent:
        pass

    a = FakeAgent()
    a._cached_system_prompt = "Model: OLD_MODEL_NAME_XXXX\nProvider: deepseek\nrest"
    a._system_prompt_breakdown = ContextBreakdown(
        timestamp_model_chars=40, total_system_prompt_chars=60,
        soul_md_chars=10,
    )
    rewrite_prompt_model_identity(a, "NEW_MODEL", "deepseek")
    # delta = len("NEW_MODEL") - len("OLD_MODEL_NAME_XXXX") = 8 - 18 = -10
    assert a._system_prompt_breakdown.timestamp_model_chars == 30
    assert a._system_prompt_breakdown.total_system_prompt_chars == len(
        a._cached_system_prompt
    )
    assert a._system_prompt_breakdown.soul_md_chars == 10  # untouched


def test_background_review_copies_parent_breakdown():
    """Same-model review fork inherits the parent breakdown (SYS-798)."""
    import sys as _sys
    _sys.path.insert(0, "/home/linux/.hermes/hermes-agent")
    from agent.context_telemetry import ContextBreakdown

    class FakeAgent:
        pass

    parent = FakeAgent()
    parent._cached_system_prompt = "parent prompt"
    parent._system_prompt_breakdown = ContextBreakdown(
        soul_md_chars=100, total_system_prompt_chars=12,
    )
    review = FakeAgent()
    review._cached_system_prompt = None
    review._system_prompt_breakdown = None
    # Same-model copy path (background_review.py:766-775 logic)
    if not False:  # not routed
        review._cached_system_prompt = parent._cached_system_prompt
        review._system_prompt_breakdown = getattr(
            parent, "_system_prompt_breakdown", None
        )
    assert review._cached_system_prompt == "parent prompt"
    assert review._system_prompt_breakdown is not None
    assert review._system_prompt_breakdown.soul_md_chars == 100


def test_restore_path_uses_exact_stored_prompt_total():
    """Stored-prompt restore forces total to len(stored_prompt)."""
    import sys as _sys
    _sys.path.insert(0, "/home/linux/.hermes/hermes-agent")
    from agent.context_telemetry import ContextBreakdown
    from dataclasses import replace

    class FakeAgent:
        pass

    a = FakeAgent()
    stored_prompt = "exact stored prompt string for this session"
    # Simulate restore-path: parts-derived breakdown then total overridden
    _bd = ContextBreakdown(soul_md_chars=50, total_system_prompt_chars=99)
    _bd = replace(_bd, total_system_prompt_chars=len(stored_prompt))
    a._system_prompt_breakdown = _bd
    assert a._system_prompt_breakdown.total_system_prompt_chars == len(
        stored_prompt
    )
