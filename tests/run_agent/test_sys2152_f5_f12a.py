"""TDD tests for SYS-2152: F5 (broken cron guidance), F12a (Grok execution guidance).

These tests verify RED before implementation.
"""
import sys
from pathlib import Path

# Path to the checkout under test.
AGENT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AGENT_DIR))

import pytest


class TestCronGuidanceCompleteness:
    """F5: Verify cron platform hint and GOOGLE guidance are grammatically complete."""

    def test_cron_hint_not_ending_mid_sentence(self):
        """The cron platform hint must not end with a dangling 'or' or 'configured'."""
        from agent.prompt_builder import PLATFORM_HINTS

        cron_text = PLATFORM_HINTS.get("cron", "")
        assert cron_text, "cron hint must exist"

        # Verify the text doesn't contain a grammatical fragment like 'or ' followed by 
        # nothing before 'Your final response'
        assert "degraded, report the specific gap" in cron_text, (
            "F5 RED: Cron hint missing 'degraded, report the specific gap' — "
            "the sentence 'When data is missing, ambiguous, or ' is incomplete"
        )

        # Verify 'configured' is followed by 'destination'
        assert "configured destination" in cron_text, (
            "F5 RED: Cron hint missing 'destination' after 'configured' — "
            "the sentence 'delivered to the job's configured ' is incomplete"
        )

    def test_google_guidance_includes_verification_completion(self):
        """The GOOGLE guidance 'Include verification ' must have a continuation."""
        from agent.prompt_builder import GOOGLE_MODEL_OPERATIONAL_GUIDANCE

        google_text = GOOGLE_MODEL_OPERATIONAL_GUIDANCE
        assert google_text, "GOOGLE guidance must exist"

        # "Include verification " must be followed by something
        import re
        match = re.search(r'Include verification\s+(results|steps|details)', google_text)
        assert match, (
            "F5a RED: GOOGLE guidance 'Include verification ' is incomplete — "
            "must be followed by 'results', 'steps', or similar completion"
        )


class TestGrokExecutionGuidance:
    """F12a: Verify Grok (xAI) models get OPENAI_MODEL_EXECUTION_GUIDANCE."""

    def test_grok_gets_execution_guidance(self):
        """Grok must receive guidance in the active system-prompt builder."""
        import ast

        system_prompt_path = AGENT_DIR / "agent" / "system_prompt.py"
        source = system_prompt_path.read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                if "OPENAI_MODEL_EXECUTION_GUIDANCE" in ast.unparse(node):
                    compared_names = {
                        child.value
                        for child in ast.walk(node.test)
                        if isinstance(child, ast.Constant)
                        and isinstance(child.value, str)
                    }
                    if {"gpt", "codex", "grok"} <= compared_names:
                        return

        pytest.fail(
            "F12a RED: Grok is NOT in the OPENAI_MODEL_EXECUTION_GUIDANCE injection "
            "condition in agent/system_prompt.py. The condition must include "
            "'gpt', 'codex', and 'grok'."
        )

    def test_grok_in_enforcement_models(self):
        """Grok must be in TOOL_USE_ENFORCEMENT_MODELS."""
        # This test should PASS — grok is already in the tuple
        from agent.prompt_builder import TOOL_USE_ENFORCEMENT_MODELS
        assert "grok" in TOOL_USE_ENFORCEMENT_MODELS, (
            "Grok must be in TOOL_USE_ENFORCEMENT_MODELS"
        )
