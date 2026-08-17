"""Deterministic, result-neutral support for SYS-2977 acceptance runs."""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

PROMPT_GATES = (
    "prompt_context_budget", "prompt_integrity_manifest", "prompt_req_marker_survival",
    "prompt_model_variant_sync", "prompt_payload_headroom", "prompt_behavioral_parity",
    "prompt_gate_registry_sync",
)


@dataclass(frozen=True)
class NeedleCase:
    request_id: str
    label: str
    payload: str
    token_target: int


def build_needle_case(*, token_target: int, needle: str, seed: int) -> NeedleCase:
    """Build reproducible label-blind input; this never claims a live result."""
    if token_target <= 0 or not needle:
        raise ValueError("token_target and needle are required")
    rng = random.Random(seed)
    label = hashlib.sha256(f"{seed}:{token_target}".encode()).hexdigest()[:12]
    request_id = f"sys2977-{label}"
    words = [f"w{rng.randrange(1_000_000):06d}" for _ in range(max(1, token_target - 1))]
    words[len(words) // 2] = needle
    return NeedleCase(request_id=request_id, label=label, payload=" ".join(words), token_target=token_target)
