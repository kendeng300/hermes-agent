"""Reviewed provider/model prompt-profile registry for SYS-2977."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class PromptProfileError(RuntimeError):
    """A prompt profile cannot be selected or admitted safely."""


@dataclass(frozen=True)
class PromptProfileSpec:
    profile_id: str
    provider: str
    model: str
    adapter_module: str
    tokenizer_id: str
    contract_window: int
    policy_core_max: int
    fixed_prefix_max: int
    payload_floor: int
    output_reserve: int
    safety_reserve: int

    @property
    def route(self) -> str:
        return f"{self.provider}/{self.model}"

    @property
    def cache_namespace(self) -> str:
        return self.profile_id


_PROFILES = {
    ("openai-codex", "gpt-5.6-sol"): PromptProfileSpec(
        profile_id="openai-gpt-5.6-sol-v1",
        provider="openai-codex",
        model="gpt-5.6-sol",
        adapter_module="agent.prompt_profiles.adapters.openai_sol",
        tokenizer_id="o200k_base",
        contract_window=257_000,
        policy_core_max=25_000,
        fixed_prefix_max=48_000,
        payload_floor=160_000,
        output_reserve=32_000,
        safety_reserve=17_000,
    ),
    ("deepseek", "deepseek-v4-flash"): PromptProfileSpec(
        profile_id="deepseek-v4-flash-v1",
        provider="deepseek",
        model="deepseek-v4-flash",
        adapter_module="agent.prompt_profiles.adapters.deepseek_v4",
        tokenizer_id="deepseek-v4",
        contract_window=1_000_000,
        policy_core_max=28_000,
        fixed_prefix_max=64_000,
        payload_floor=800_000,
        output_reserve=64_000,
        safety_reserve=72_000,
    ),
}


def _key(provider: str, model: str) -> tuple[str, str]:
    return ((provider or "").strip().lower(), (model or "").strip().lower())


def get_profile(provider: str, model: str) -> PromptProfileSpec:
    """Return the exact reviewed profile; aliases are resolved upstream."""
    try:
        return _PROFILES[_key(provider, model)]
    except KeyError as exc:
        raise PromptProfileError(f"PROFILE_UNAVAILABLE: {provider}/{model}") from exc


def find_profile(provider: str, model: str) -> PromptProfileSpec | None:
    """Return a registered profile, or ``None`` for legacy routes."""
    return _PROFILES.get(_key(provider, model))


def registered_profiles() -> tuple[PromptProfileSpec, ...]:
    return tuple(_PROFILES[key] for key in sorted(_PROFILES))


def default_core_path() -> Path:
    from hermes_constants import get_hermes_home
    return get_hermes_home() / "SOUL.md"
