"""PROMPT-815: verify prefix alignment — dynamic content at volatile tail.

Verifies system_message and context_files are appended to volatile_parts,
never to context_parts or stable_parts.  Uses AST inspection of
build_system_prompt_parts (the sole assembly path).
"""
import ast
from pathlib import Path

import pytest

HERMES_AGENT_DIR = Path(__file__).resolve().parents[2]
SYSTEM_PROMPT_PATH = HERMES_AGENT_DIR / "agent" / "system_prompt.py"


class PrefixAlignmentVisitor(ast.NodeVisitor):
    """Walk build_system_prompt_parts to verify append targets."""

    def __init__(self):
        self._in_func = False
        self._context_parts_appends = 0
        self._volatile_system_message_appends = 0
        self._volatile_context_files_appends = 0
        self._stable_forbidden_appends = 0

    def _target_name(self, node) -> str:
        if isinstance(node, ast.Attribute):
            obj = node.value
            if isinstance(obj, ast.Name):
                return obj.id
        return ""

    def _is_system_message_append(self, node) -> bool:
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id == "system_message":
                return True
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                if "caller_instruction" in child.value:
                    return True
        return False

    def _is_context_files_append(self, node) -> bool:
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id == "context_files_prompt":
                return True
        return False

    def visit_FunctionDef(self, node):
        if node.name == "build_system_prompt_parts":
            self._in_func = True
            self.generic_visit(node)
            self._in_func = False

    def visit_Call(self, node):
        if not self._in_func:
            return
        if isinstance(node.func, ast.Attribute) and node.func.attr == "append":
            target = self._target_name(node.func)
            if target == "context_parts":
                self._context_parts_appends += 1
            elif target == "volatile_parts":
                if self._is_system_message_append(node):
                    self._volatile_system_message_appends += 1
                if self._is_context_files_append(node):
                    self._volatile_context_files_appends += 1
            elif target == "stable_parts":
                if (self._is_system_message_append(node)
                    or self._is_context_files_append(node)):
                    self._stable_forbidden_appends += 1
        self.generic_visit(node)


@pytest.fixture(scope="module")
def visitor():
    assert SYSTEM_PROMPT_PATH.is_file(), f"{SYSTEM_PROMPT_PATH} not found"
    tree = ast.parse(SYSTEM_PROMPT_PATH.read_text())
    v = PrefixAlignmentVisitor()
    v.visit(tree)
    return v


def test_no_context_parts_appends(visitor):
    """G3: context_parts must have zero appends."""
    assert visitor._context_parts_appends == 0, (
        f"context_parts has {visitor._context_parts_appends} append() calls — "
        "system_message/context_files must be in volatile_parts"
    )


def test_system_message_in_volatile(visitor):
    """G1: system_message appended to volatile_parts."""
    assert visitor._volatile_system_message_appends == 1, (
        f"expected 1 volatile_parts.append with system_message, got "
        f"{visitor._volatile_system_message_appends}"
    )


def test_context_files_in_volatile(visitor):
    """G2: context_files appended to volatile_parts."""
    assert visitor._volatile_context_files_appends == 1, (
        f"expected 1 volatile_parts.append with context_files_prompt, got "
        f"{visitor._volatile_context_files_appends}"
    )


def test_stable_no_dynamic_content(visitor):
    """G4: stable_parts never receives system_message/context_files."""
    assert visitor._stable_forbidden_appends == 0, (
        f"stable_parts has {visitor._stable_forbidden_appends} dynamic-content "
        "append() calls"
    )
