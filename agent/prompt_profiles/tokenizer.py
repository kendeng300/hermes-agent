"""Provider-qualified token counters used for hard prompt admission."""
from __future__ import annotations

import importlib
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


class TokenizerUnavailable(RuntimeError):
    """The reviewed tokenizer or its local assets are unavailable."""


@dataclass(frozen=True)
class TokenBreakdown:
    text: int
    messages: int
    tools: int

    @property
    def total(self) -> int:
        return self.text + self.messages + self.tools


class OpenAITokenCounter:
    tokenizer_id = "o200k_base"

    def __init__(self) -> None:
        try:
            import tiktoken
            self._encoding = tiktoken.get_encoding(self.tokenizer_id)
            self.tokenizer_version = getattr(tiktoken, "__version__", "unknown")
        except Exception as exc:
            raise TokenizerUnavailable("TOKENIZER_UNAVAILABLE: o200k_base") from exc

    def count_text(self, text: str) -> int:
        return len(self._encoding.encode(text, disallowed_special=()))

    def count_tools(self, tools: Sequence[Mapping[str, Any]]) -> int:
        payload = json.dumps(list(tools), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return self.count_text(payload) if tools else 0

    def count_messages(self, messages: Sequence[Mapping[str, Any]]) -> int:
        total = 0
        for message in messages:
            total += 3
            total += self.count_text(str(message.get("role", "")))
            content = message.get("content", "")
            if isinstance(content, str):
                total += self.count_text(content)
            else:
                total += self.count_text(json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return total + (3 if messages else 0)


class DeepSeekTokenCounter:
    tokenizer_id = "deepseek-v4"
    model_id = "deepseek-ai/DeepSeek-V3.1"
    revision = "c0781d039fb7a1ba2abc4add0bdc293e92d2b8db"
    asset_sha256 = {
        "tokenizer.json": "32b34a41212e92f62e859cbbea121ae705a1fabbf157d9acf22d134ecd8dcf70",
        "tokenizer_config.json": "f3d66f405ce0315c754a3cc041f13be863fefcd62c240068098efdbd1924f8b5",
    }

    def __init__(self) -> None:
        try:
            transformers = importlib.import_module("transformers")
            resolved = []
            for name, expected in self.asset_sha256.items():
                path = transformers.utils.hub.cached_file(
                    self.model_id, name, revision=self.revision, local_files_only=True,
                )
                if not path:
                    raise TokenizerUnavailable(f"TOKENIZER_FIXTURE_MISMATCH: missing {name}")
                actual = hashlib.sha256(open(path, "rb").read()).hexdigest()
                if actual != expected:
                    raise TokenizerUnavailable(f"TOKENIZER_FIXTURE_MISMATCH: {name}")
                resolved.append(path)
            # Loading by Hub model id can still make a metadata request in
            # recent Transformers releases even with ``local_files_only``.
            # Use the snapshot that we just hash-verified instead: admission
            # must remain usable after the initial assets are cached.
            self._tokenizer = transformers.AutoTokenizer.from_pretrained(
                str(Path(resolved[0]).parent),
                trust_remote_code=False,
                local_files_only=True,
            )
            self.tokenizer_version = getattr(transformers, "__version__", "unknown")
        except Exception as exc:
            raise TokenizerUnavailable(
                "TOKENIZER_UNAVAILABLE: official deepseek-ai/DeepSeek-V3.1 assets unavailable or malformed"
            ) from exc

    def count_text(self, text: str) -> int:
        return len(self._tokenizer.encode(text, add_special_tokens=False))

    def count_tools(self, tools: Sequence[Mapping[str, Any]]) -> int:
        if not tools:
            return 0
        probe = [{"role": "user", "content": ""}]
        try:
            without = self._tokenizer.apply_chat_template(
                probe, tokenize=True, add_generation_prompt=True
            )
            with_tools = self._tokenizer.apply_chat_template(
                probe, tools=list(tools), tokenize=True, add_generation_prompt=True
            )
        except Exception as exc:
            raise TokenizerUnavailable(
                "TOKENIZER_UNAVAILABLE: deepseek-v4 tool template failed"
            ) from exc
        if not isinstance(without, (list, tuple)) or not isinstance(with_tools, (list, tuple)):
            raise TokenizerUnavailable("TOKENIZER_UNAVAILABLE: malformed deepseek-v4 tool template")
        delta = len(with_tools) - len(without)
        if delta < 0:
            raise TokenizerUnavailable("TOKENIZER_UNAVAILABLE: malformed deepseek-v4 tool accounting")
        return delta

    def count_messages(self, messages: Sequence[Mapping[str, Any]]) -> int:
        if not messages:
            return 0
        try:
            rendered = self._tokenizer.apply_chat_template(
                list(messages), tokenize=True, add_generation_prompt=True
            )
        except Exception as exc:
            raise TokenizerUnavailable(
                "TOKENIZER_UNAVAILABLE: deepseek-v4 chat template failed"
            ) from exc
        if not isinstance(rendered, (list, tuple)):
            raise TokenizerUnavailable("TOKENIZER_UNAVAILABLE: malformed deepseek-v4 chat template")
        return len(rendered)


def get_token_counter(provider: str, model: str):
    key = ((provider or "").strip().lower(), (model or "").strip().lower())
    if key == ("openai-codex", "gpt-5.6-sol"):
        return OpenAITokenCounter()
    if key == ("deepseek", "deepseek-v4-flash"):
        return DeepSeekTokenCounter()
    raise TokenizerUnavailable(f"TOKENIZER_UNAVAILABLE: {provider}/{model}")
