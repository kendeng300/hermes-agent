"""PROMPT-813: tiered routing tests — reasoning_required flag, flash detection,
anti-fabrication preamble, delegation_model telemetry.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.delegate_tool import (
    _ANTI_FABRICATION_PREAMBLE,
    _FLASH_MODEL_PATTERNS,
    _REASONING_MODEL,
    _REASONING_PROVIDER,
    _is_flash_model,
    _is_reasoning_heavy_task,
    _resolve_effective_delegation_model,
)


# ── Routing tests ─────────────────────────────────────────────────────────

def test_reasoning_required_routes_to_sol():
    """reasoning_required=true forces gpt-5.6-sol / openai-codex."""
    model, provider = _resolve_effective_delegation_model(
        "deepseek-v4-flash", "deepseek", True, "summarize this")
    assert model == _REASONING_MODEL
    assert provider == _REASONING_PROVIDER


def test_reasoning_required_false_uses_default():
    """reasoning_required=false (default) uses configured model."""
    model, provider = _resolve_effective_delegation_model(
        "deepseek-v4-flash", "deepseek", False, "summarize this")
    assert model == "deepseek-v4-flash"
    assert provider == "deepseek"


def test_heuristic_detects_reasoning_heavy():
    """Goals containing reasoning keywords trigger heuristic routing."""
    for goal in [
        "Adversarial code review of the fix",
        "DMAIC root cause analysis",
        "Panel review of the design",
        "Postmortem for the incident",
        "Calibration analysis of the model",
        "Design review of the architecture",
        "Root cause investigation",
    ]:
        assert _is_reasoning_heavy_task(goal), f"expected heuristic match: {goal}"


def test_heuristic_no_false_positive():
    """Normal goals do NOT trigger heuristic routing."""
    for goal in [
        "Research X and write a summary",
        "Fetch the latest prices",
        "Convert this file to PDF",
        "Summarize the meeting notes",
    ]:
        assert not _is_reasoning_heavy_task(goal), f"unexpected heuristic match: {goal}"


def test_heuristic_fallback_only_when_no_model():
    """Heuristic only applies when configured_model is None (inherit parent)."""
    model, _ = _resolve_effective_delegation_model(
        "deepseek-v4-flash", "deepseek", False,
        "Adversarial code review of the fix")
    # configured model present → heuristic does NOT override
    assert model == "deepseek-v4-flash"


# ── Flash detection tests ─────────────────────────────────────────────────

def test_flash_model_detection():
    """Flash/fast model variants are detected."""
    for model in ["deepseek-v4-flash", "gpt-5.4-mini", "gpt-5.4-nano", "grok-3-mini-fast"]:
        assert _is_flash_model(model), f"expected flash detection: {model}"


def test_non_flash_model_detection():
    """Reasoning models are NOT detected as flash."""
    for model in ["gpt-5.6-sol", "deepseek-v4-pro", "gpt-5.6", None, ""]:
        assert not _is_flash_model(model), f"unexpected flash detection: {model}"


def test_flash_patterns_complete():
    """The pattern tuple covers the known flash families."""
    assert "flash" in _FLASH_MODEL_PATTERNS
    assert "nano" in _FLASH_MODEL_PATTERNS
    assert "mini" in _FLASH_MODEL_PATTERNS
    assert "fast" in _FLASH_MODEL_PATTERNS


# ── Preamble tests ────────────────────────────────────────────────────────

def test_anti_fabrication_preamble_exact_text():
    """The preamble uses the exact mandated text."""
    assert _ANTI_FABRICATION_PREAMBLE == (
        "You optimize for CORRECTNESS, not closure. "
        "Never declare success with unresolved symptoms."
    )


def test_anti_fabrication_preamble_injected_for_flash():
    """Flash sub-agents get the preamble in their system prompt."""
    from tools.delegate_tool import _build_child_system_prompt
    prompt = _build_child_system_prompt(
        "Summarize the output", effective_model="deepseek-v4-flash")
    assert _ANTI_FABRICATION_PREAMBLE in prompt
    assert prompt.index(_ANTI_FABRICATION_PREAMBLE) < prompt.index("QUALITY MANDATE")


def test_anti_fabrication_preamble_skipped_for_reasoning():
    """Reasoning models do NOT get the flash preamble (they have QUALITY MANDATE)."""
    from tools.delegate_tool import _build_child_system_prompt
    prompt = _build_child_system_prompt(
        "Summarize the output", effective_model="gpt-5.6-sol")
    assert _ANTI_FABRICATION_PREAMBLE not in prompt
    assert "QUALITY MANDATE" in prompt


# ── Telemetry tests ───────────────────────────────────────────────────────

def test_delegation_model_attr_set_on_child(tmp_path, monkeypatch):
    """_delegation_model is stashed on the child agent for telemetry."""
    from unittest.mock import MagicMock
    from tests.agent.prompt_profiles.test_systems_contract import (
        _install_parent_supported_core,
    )
    from tools.delegate_tool import _build_child_agent

    _install_parent_supported_core(tmp_path, monkeypatch)
    encoding = SimpleNamespace(encode=lambda value, **_: [0] if value else [])
    monkeypatch.setitem(
        sys.modules,
        "tiktoken",
        SimpleNamespace(
            __version__="test",
            get_encoding=lambda _name: encoding,
        ),
    )
    parent = MagicMock()
    parent.model = "gpt-5.6"
    parent.platform = "cli"
    parent.base_url = "https://api.example.com"
    parent.api_key = "test-key"
    parent._session_db = None
    parent.session_id = "parent-session"
    parent.request_overrides = {}
    parent._print_fn = None
    parent._delegate_depth = 0
    parent.provider = "openai"
    parent.api_mode = "chat_completions"

    child = _build_child_agent(
        task_index=0,
        goal="Adversarial code review",
        context=None,
        toolsets=None,
        model="gpt-5.6-sol",
        max_iterations=10,
        task_count=1,
        parent_agent=parent,
        override_provider="openai-codex",
    )
    assert getattr(child, "_delegation_model", None) == "gpt-5.6-sol"
