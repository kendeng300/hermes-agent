"""Fail-closed prompt-profile budget admission."""
from __future__ import annotations

from dataclasses import dataclass

from .registry import PromptProfileError, PromptProfileSpec


@dataclass(frozen=True)
class PromptAdmission:
    runtime_window: int
    contract_window: int
    effective_window: int
    policy_core_tokens: int
    fixed_tokens: int
    conversation_tokens: int
    output_reserve: int
    safety_reserve: int
    payload_headroom: int
    payload_floor: int
    admitted: bool
    reason_code: str


def resolve_effective_window(runtime_window: int | None, contract_window: int) -> int:
    if runtime_window is None or isinstance(runtime_window, bool) or runtime_window <= 0:
        raise PromptProfileError("RUNTIME_WINDOW_UNKNOWN")
    if isinstance(contract_window, bool) or contract_window <= 0:
        raise PromptProfileError("CONTRACT_WINDOW_MISSING")
    return min(runtime_window, contract_window)


def evaluate_admission(
    spec: PromptProfileSpec,
    *,
    runtime_window: int | None,
    policy_core_tokens: int,
    fixed_tokens: int,
    conversation_tokens: int = 0,
    requested_output_tokens: int | None = None,
) -> PromptAdmission:
    effective = resolve_effective_window(runtime_window, spec.contract_window)
    output = spec.output_reserve if requested_output_tokens is None else max(
        requested_output_tokens, spec.output_reserve
    )
    values = (policy_core_tokens, fixed_tokens, conversation_tokens, output)
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in values):
        raise PromptProfileError("INVALID_TOKEN_ACCOUNTING")
    headroom = effective - fixed_tokens - output - spec.safety_reserve
    reason = "ADMITTED"
    admitted = True
    if policy_core_tokens > spec.policy_core_max:
        admitted, reason = False, "POLICY_CORE_LIMIT"
    elif fixed_tokens > spec.fixed_prefix_max:
        admitted, reason = False, "FIXED_PREFIX_LIMIT"
    elif headroom < spec.payload_floor:
        admitted, reason = False, "PAYLOAD_FLOOR"
    elif conversation_tokens > headroom:
        admitted, reason = False, "CONVERSATION_DOES_NOT_FIT"
    return PromptAdmission(
        runtime_window=effective if runtime_window is None else runtime_window,
        contract_window=spec.contract_window,
        effective_window=effective,
        policy_core_tokens=policy_core_tokens,
        fixed_tokens=fixed_tokens,
        conversation_tokens=conversation_tokens,
        output_reserve=output,
        safety_reserve=spec.safety_reserve,
        payload_headroom=max(0, headroom),
        payload_floor=spec.payload_floor,
        admitted=admitted,
        reason_code=reason,
    )
