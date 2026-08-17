"""Shared prepare/commit/rollback transaction for live model switches.

Preparation is immutable and performs profile rendering plus hard admission before
any active runtime field changes. Commit wraps the established provider/client
swap in one compensation boundary so failures after client construction restore
the prompt, compressor, primary runtime, fallback state, and transport cache.
"""
from __future__ import annotations

import copy
import errno
import hashlib
import json
import os
import stat
import threading
import time
import uuid
from pathlib import Path
from dataclasses import replace
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from .budget import PromptAdmission, evaluate_admission
from .registry import PromptProfileError, PromptProfileSpec, find_profile
from .renderer import RenderedPromptProfile, render_profile
from .tokenizer import get_token_counter
from agent.system_prompt import build_system_prompt_candidate

_MISSING = object()
_RUNTIME_FIELDS = (
    "model", "provider", "base_url", "api_mode", "api_key", "client",
    "_anthropic_client", "_anthropic_api_key", "_anthropic_base_url",
    "_is_anthropic_oauth", "_config_context_length", "_credential_pool",
    "_cached_system_prompt", "_system_prompt_breakdown", "_prompt_profile",
    "_prompt_profile_rendered", "_use_prompt_caching", "_use_native_cache_layout",
    "_primary_runtime", "_fallback_activated", "_fallback_index",
    "_fallback_chain", "_fallback_model", "_client_kwargs", "_transport_cache",
)
_COMPRESSOR_FIELDS = (
    "model", "provider", "base_url", "api_key", "api_mode", "context_length",
    "threshold_tokens", "threshold_percent", "max_tokens", "max_output_tokens",
)


def _copy_value(value: Any) -> Any:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return list(value)
    if isinstance(value, set):
        return set(value)
    if isinstance(value, tuple):
        return tuple(value)
    return value


@dataclass(frozen=True)
class ModelSwitchSnapshot:
    runtime: Mapping[str, Any]
    compressor: Mapping[str, Any]
    old_client: Any


@dataclass(frozen=True)
class PreparedModelSwitch:
    provider: str
    model: str
    api_key: Any
    base_url: str
    api_mode: str
    profile: PromptProfileSpec | None
    rendered_profile: RenderedPromptProfile | None
    admission: PromptAdmission | None
    effective_window: int | None
    old_identity: tuple[Any, Any, Any]
    final_prompt: str = ""
    candidate_client: Any = None
    runtime_updates: Mapping[str, Any] | None = None
    durable_mutations: tuple["DurableMutation", ...] = ()
    old_state_version: Any = None
    transaction_id: str | None = None
    journal_path: str | None = None
    session_id: str | None = None
    hermes_home: str | None = None


@dataclass(frozen=True)
class DurableMutation:
    """A fallible durable write paired with its strict compensation."""

    apply: Callable[[], Any]
    compensate: Callable[[], Any]
    label: str


class SwitchJournal:
    """Crash-consistent, secret-free transaction state for startup recovery."""

    STATES = (
        "PREPARED", "CONFIG_APPLIED", "RUNTIME_STAGED", "COMMITTED",
        "CLEANUP_PENDING", "DONE", "ABORTED",
    )
    _EDGES = {
        "PREPARED": frozenset(("CONFIG_APPLIED", "ABORTED")),
        "CONFIG_APPLIED": frozenset(("RUNTIME_STAGED", "ABORTED")),
        "RUNTIME_STAGED": frozenset(("COMMITTED", "ABORTED")),
        "COMMITTED": frozenset(("CLEANUP_PENDING",)),
        "CLEANUP_PENDING": frozenset(("DONE",)),
        "DONE": frozenset(),
        "ABORTED": frozenset(),
    }
    _TOP_LEVEL_KEYS = frozenset(("schema_version", "state", "generation", "payload"))
    _PAYLOAD_KEYS = frozenset(("transaction_id", "session_id", "old", "new"))
    _IDENTITY_KEYS = frozenset(("provider", "model"))
    _MAX_GENERATION = (1 << 63) - 1

    def __init__(self, path: Path | str, *, secret_values: Sequence[str] = ()) -> None:
        self.path = Path(path)
        self.secret_values = tuple(value for value in secret_values if value)

    def _scan(self, value: Any) -> None:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"))
        if any(secret in encoded for secret in self.secret_values):
            raise PromptProfileError("SECRET_BOUNDARY_VIOLATION")

    def transition(self, state: str, *, generation: int, payload: Mapping[str, Any]) -> None:
        if state not in self.STATES:
            raise PromptProfileError("INVALID_SWITCH_JOURNAL_STATE")
        # Reject secret-bearing candidate bytes before comparing them with the
        # current record.  Payload mismatch must never mask the stronger
        # boundary violation, even though neither failure writes a byte.
        self._scan(payload)
        current = self.recover(expected_generation=None, missing_ok=True)
        if current:
            if generation != current["generation"]:
                raise PromptProfileError("GENERATION_CONFLICT")
            if state not in self._EDGES[current["state"]]:
                raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
            if dict(payload) != dict(current["payload"]):
                raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
        elif state != "PREPARED":
            # A journal that does not yet exist must begin at PREPARED.
            # Accepting CONFIG_APPLIED / RUNTIME_STAGED / COMMITTED /
            # CLEANUP_PENDING / DONE / ABORTED as a first state would let a
            # writer manufacture authority without the required preparation
            # record (and without the pre-write CAS/secret checks).
            raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
        record = {"schema_version": 1, "state": state, "generation": generation, "payload": dict(payload)}
        self._validate_record(record)
        self._scan(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        if self.path.is_symlink():
            raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(record, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    def recover(self, *, expected_generation: int | None, missing_ok: bool = False) -> Mapping[str, Any]:
        if ".." in self.path.parts:
            raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
        parent = self.path.parent.resolve(strict=False)
        try:
            leaf = self.path.lstat()
            if stat.S_ISLNK(leaf.st_mode) or not stat.S_ISREG(leaf.st_mode):
                raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
            if self.path.resolve(strict=True).parent != parent:
                raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(self.path, flags)
            try:
                opened = os.fstat(fd)
                if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (leaf.st_dev, leaf.st_ino):
                    raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
                with os.fdopen(fd, "r", encoding="utf-8") as handle:
                    fd = -1
                    record = json.load(handle)
            finally:
                if fd >= 0:
                    os.close(fd)
        except FileNotFoundError:
            if missing_ok:
                return {}
            raise PromptProfileError("SWITCH_JOURNAL_MISSING")
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS") from exc
        self._scan(record)
        self._validate_record(record)
        if expected_generation is not None and record.get("generation") != expected_generation:
            raise PromptProfileError("GENERATION_CONFLICT")
        return MappingProxyType(record)

    @classmethod
    def _validate_record(cls, record: Any) -> None:
        def safe_id(value: Any) -> bool:
            return isinstance(value, str) and bool(value) and len(value) <= 256 and ".." not in value and all(
                ch in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in value
            )
        if not isinstance(record, dict) or set(record) != cls._TOP_LEVEL_KEYS:
            raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
        generation = record.get("generation")
        payload = record.get("payload")
        if record.get("schema_version") != 1 or record.get("state") not in cls.STATES:
            raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
        if isinstance(generation, bool) or not isinstance(generation, int) or not 0 <= generation <= cls._MAX_GENERATION:
            raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
        if not isinstance(payload, dict) or set(payload) != cls._PAYLOAD_KEYS:
            raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
        if not safe_id(payload.get("transaction_id")) or not safe_id(payload.get("session_id")):
            raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
        for side in ("old", "new"):
            identity = payload.get(side)
            if not isinstance(identity, dict) or set(identity) != cls._IDENTITY_KEYS:
                raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
            if any(not isinstance(identity[key], str) or not identity[key] for key in cls._IDENTITY_KEYS):
                raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")

    def terminalize_recovery(self, state: str, *, generation: int, payload: Mapping[str, Any]) -> None:
        """Terminalize only after recovery independently validates authority."""
        if state not in {"DONE", "ABORTED"}:
            raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
        current = self.recover(expected_generation=generation)
        if current["state"] in {"DONE", "ABORTED"} or dict(current["payload"]) != dict(payload):
            raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
        record = {"schema_version": 1, "state": state, "generation": generation, "payload": dict(payload)}
        self._scan(record)
        self._validate_record(record)
        self._write_record(record)

    def _write_record(self, record: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        if self.path.is_symlink():
            raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        try:
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(record, handle, sort_keys=True, separators=(",", ":")); handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
            os.replace(tmp, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try: os.fsync(directory_fd)
            finally: os.close(directory_fd)
        finally:
            try: tmp.unlink()
            except FileNotFoundError: pass

    def remove(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return
        directory_fd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


class InterprocessSwitchLock:
    """Bounded OS-visible advisory lock used by all durable switch writers."""

    def __init__(self, path: Path | str, *, timeout: float = 5.0) -> None:
        self.path = Path(path)
        self.timeout = max(0.0, float(timeout))
        self._handle = None

    def __enter__(self):
        if os.name != "posix":
            raise PromptProfileError("SWITCH_LOCK_UNAVAILABLE")
        import fcntl

        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._handle = open(self.path, "a+b")
        os.chmod(self.path, 0o600)
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN):
                    self._handle.close()
                    raise
                if time.monotonic() >= deadline:
                    self._handle.close()
                    self._handle = None
                    raise PromptProfileError("SWITCH_LOCK_TIMEOUT")
                time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))

    def __exit__(self, exc_type, exc, tb):
        if self._handle is not None:
            import fcntl
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None


def _switch_home(agent: Any) -> Path | None:
    explicit = getattr(agent, "hermes_home", None)
    # Bare compatibility callers commonly use MagicMock agents.  Treat only
    # concrete filesystem values as an explicit journal root; coercing an
    # arbitrary mock/object through Path() can silently target the cwd.
    if isinstance(explicit, (str, Path)) and str(explicit):
        return Path(explicit)
    session_id = getattr(agent, "session_id", None)
    if not isinstance(session_id, (str, int)) or isinstance(session_id, bool):
        return None
    if isinstance(session_id, str) and not session_id:
        return None
    from hermes_constants import get_hermes_home
    return get_hermes_home()


def _safe_session_id(
    value: Any, *, fallback_identity: Sequence[Any] = (), session_root: Path | str | None = None,
) -> str:
    """Return a journal-safe, stable session identity.

    Existing string and numeric legacy IDs remain byte-for-byte compatible.
    A genuinely missing/non-concrete ID is derived only when the caller
    supplies stable session context.  User-supplied empty, whitespace,
    control-character, and traversal-like values remain fail-closed.
    """
    if isinstance(value, Path):
        if session_root is None:
            raise PromptProfileError("INVALID_SWITCH_SESSION_ID")
        root = Path(session_root).resolve(strict=False)
        resolved = value.resolve(strict=False)
        try:
            relative = resolved.relative_to(root)
        except ValueError as exc:
            raise PromptProfileError("INVALID_SWITCH_SESSION_ID") from exc
        if relative == Path(".") or any(part == ".." for part in relative.parts):
            raise PromptProfileError("INVALID_SWITCH_SESSION_ID")
        value = "path-" + hashlib.sha256(relative.as_posix().encode("utf-8")).hexdigest()[:32]
    elif value is None:
        if not fallback_identity:
            raise PromptProfileError("INVALID_SWITCH_SESSION_ID")
        seed = "\x00".join(str(part or "") for part in fallback_identity) or "default"
        value = "switch-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
    elif isinstance(value, bool) or not isinstance(value, (str, int)):
        raise PromptProfileError("INVALID_SWITCH_SESSION_ID")
    elif isinstance(value, int):
        value = str(value)

    if (
        not value
        or len(value) > 256
        or ".." in value
        or any(
            ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
            for ch in value
        )
    ):
        raise PromptProfileError("INVALID_SWITCH_SESSION_ID")
    return value


def _atomic_json(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _read_authoritative_state(home: Path, session_id: str) -> Mapping[str, Any]:
    path = home / "state" / "model_switch_state" / f"{session_id}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return MappingProxyType({"generation": 0, "transaction_id": None})
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PromptProfileError("SWITCH_STATE_AMBIGUOUS") from exc
    if not isinstance(value, dict) or not isinstance(value.get("generation"), int):
        raise PromptProfileError("SWITCH_STATE_AMBIGUOUS")
    return MappingProxyType(value)


def _publish_authoritative_state(home: Path, session_id: str, record: Mapping[str, Any]) -> None:
    _atomic_json(home / "state" / "model_switch_state" / f"{session_id}.json", record)


def _read_commit_authority(agent: Any, home: Path, session_id: str) -> Mapping[str, Any]:
    session_db = getattr(agent, "_session_db", None)
    reader = _explicit_bound_method(session_db, "get_model_switch_state")
    if callable(reader):
        try:
            return MappingProxyType(dict(reader(session_id)))
        except Exception as exc:
            raise PromptProfileError("SWITCH_STATE_AMBIGUOUS") from exc
    return _read_authoritative_state(home, session_id)


def _cas_commit_authority(
    agent: Any, home: Path, session_id: str, *, expected: int, record: Mapping[str, Any]
) -> None:
    session_db = getattr(agent, "_session_db", None)
    cas = _explicit_bound_method(session_db, "compare_and_swap_model_switch")
    if callable(cas):
        try:
            changed = cas(
                session_id, expected_generation=expected, generation=record["generation"],
                transaction_id=record["transaction_id"], provider=record["provider"],
                model=record["model"],
            )
        except Exception as exc:
            raise PromptProfileError("SWITCH_STATE_AMBIGUOUS") from exc
        if not changed:
            raise PromptProfileError("SWITCH_CONFLICT")
        return
    _publish_authoritative_state(home, session_id, record)


def _explicit_bound_method(instance: Any, name: str) -> Callable[..., Any] | None:
    """Return a method explicitly supplied by an authority implementation.

    Some session-store doubles and compatibility objects synthesize arbitrary
    attributes on access.  Treating those as a durable CAS interface selects a
    protocol they do not implement and can yield an empty authority record.
    """
    if instance is None:
        return None
    class_member = getattr(type(instance), name, None)
    if callable(class_member):
        return getattr(instance, name)
    instance_member = getattr(instance, "__dict__", {}).get(name)
    return instance_member if callable(instance_member) else None


def _observe_transition(agent: Any, state: str, record: Mapping[str, Any]) -> None:
    observer = getattr(agent, "_switch_transition_observer", None)
    if callable(observer):
        observer(state, record)


def capture_model_switch_snapshot(agent: Any) -> ModelSwitchSnapshot:
    runtime = {name: _copy_value(getattr(agent, name, _MISSING)) for name in _RUNTIME_FIELDS}
    compressor = getattr(agent, "context_compressor", None)
    compressor_state = {}
    if compressor is not None:
        compressor_state = {
            name: _copy_value(getattr(compressor, name, _MISSING))
            for name in _COMPRESSOR_FIELDS
        }
    return ModelSwitchSnapshot(
        runtime=runtime,
        compressor=compressor_state,
        old_client=getattr(agent, "client", None),
    )


def _current_identity(agent: Any) -> tuple[Any, Any, Any]:
    profile = getattr(agent, "_prompt_profile", None)
    if isinstance(profile, (tuple, list)):
        profile = tuple(profile)
    return (getattr(agent, "provider", None), getattr(agent, "model", None), profile)


def prepare_model_switch(
    agent: Any,
    *,
    model: str,
    provider: str,
    api_key: Any = "",
    base_url: str = "",
    api_mode: str = "",
    runtime_window: int | None = None,
    messages: Sequence[Mapping[str, Any]] = (),
    tools: Sequence[Mapping[str, Any]] = (),
    enforce_profile: bool = True,
    system_message: str | None = None,
    candidate_client_factory: Callable[[], Any] | None = None,
    runtime_updates: Mapping[str, Any] | None = None,
    durable_mutations: Sequence[DurableMutation] = (),
    requested_output_tokens: int | None = None,
) -> PreparedModelSwitch:
    """Validate and stage a candidate without mutating ``agent``.

    Legacy routes without an approved profile retain their established switch
    behavior. The two SYS-2977 routes are fail-closed on core, adapter,
    tokenizer, runtime-window, or admission failure.
    """
    spec = find_profile(provider, model) if enforce_profile else None
    rendered = None
    admission = None
    effective_window = None
    final_prompt = ""
    candidate_client = None
    if spec is not None:
        if runtime_window is None:
            from agent.model_metadata import get_model_context_length
            key = api_key if isinstance(api_key, str) else ""
            runtime_window = get_model_context_length(
                model,
                base_url=base_url,
                api_key=key,
                provider=provider,
                config_context_length=None,
                custom_providers=getattr(agent, "_custom_providers", None),
            )
        rendered = render_profile(spec)
        counter = get_token_counter(provider, model)
        core_tokens = counter.count_text(rendered.stable.split("\n\n## MODEL ADAPTER", 1)[0])
        final_prompt = build_system_prompt_candidate(agent, rendered, system_message)
        fixed_tokens = counter.count_text(final_prompt) + counter.count_tools(tools)
        conversation_tokens = counter.count_messages(messages)
        admission = evaluate_admission(
            spec,
            runtime_window=runtime_window,
            policy_core_tokens=core_tokens,
            fixed_tokens=fixed_tokens,
            conversation_tokens=conversation_tokens,
            requested_output_tokens=max(spec.output_reserve, requested_output_tokens or 0),
        )
        if not admission.admitted:
            raise PromptProfileError(f"PROMPT_ADMISSION_REJECTED: {admission.reason_code}")
        effective_window = admission.effective_window
    if candidate_client_factory is not None:
        # Client construction is deliberately last in prepare: no durable or
        # live state has changed, and all policy/admission checks have passed.
        candidate_client = candidate_client_factory()
    transaction_id = None
    journal_path = None
    session_id = getattr(agent, "session_id", None)
    home = _switch_home(agent)
    old_generation = getattr(agent, "_prompt_profile_state_version", None)
    if home is not None:
        session_id = _safe_session_id(
            session_id, fallback_identity=(provider, model),
        )
        transaction_id = str(uuid.uuid4())
        journal_path = str(home / "state" / "model_switch_journal" / f"{transaction_id}.json")
        journal = SwitchJournal(journal_path, secret_values=(api_key,) if isinstance(api_key, str) else ())
        payload = {
            "transaction_id": transaction_id,
            "session_id": session_id,
            "old": {
                "provider": getattr(agent, "provider", None),
                "model": getattr(agent, "model", None),
            },
            "new": {"provider": provider, "model": model},
        }
        journal.transition("PREPARED", generation=(old_generation or 0) + 1, payload=payload)
        _observe_transition(agent, "PREPARED", payload)
    return PreparedModelSwitch(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        api_mode=api_mode,
        profile=spec,
        rendered_profile=rendered,
        admission=admission,
        effective_window=effective_window,
        old_identity=_current_identity(agent),
        final_prompt=final_prompt,
        candidate_client=candidate_client,
        runtime_updates=dict(runtime_updates or {}),
        durable_mutations=tuple(durable_mutations),
        old_state_version=old_generation,
        transaction_id=transaction_id,
        journal_path=journal_path,
        session_id=session_id,
        hermes_home=str(home) if home is not None else None,
    )


def rollback_model_switch(agent: Any, snapshot: ModelSwitchSnapshot) -> tuple[str, ...]:
    failures: list[str] = []
    candidate = getattr(agent, "client", None)
    candidate_anthropic = getattr(agent, "_anthropic_client", None)
    old_anthropic = snapshot.runtime.get("_anthropic_client", _MISSING)
    for name, value in snapshot.runtime.items():
        if value is _MISSING:
            if hasattr(agent, name):
                try:
                    delattr(agent, name)
                except Exception as exc:
                    failures.append(f"delete {name}: {type(exc).__name__}")
            continue
        try:
            setattr(agent, name, _copy_value(value))
        except Exception as exc:
            failures.append(f"restore {name}: {type(exc).__name__}")
    compressor = getattr(agent, "context_compressor", None)
    if compressor is not None:
        for name, value in snapshot.compressor.items():
            if value is not _MISSING:
                try:
                    setattr(compressor, name, _copy_value(value))
                except Exception as exc:
                    failures.append(f"restore compressor.{name}: {type(exc).__name__}")
    if candidate is not None and candidate is not snapshot.old_client:
        close = getattr(candidate, "close", None)
        if callable(close):
            try:
                close()
            except Exception as exc:
                failures.append(f"close candidate client: {type(exc).__name__}")
    if (
        candidate_anthropic is not None
        and candidate_anthropic is not old_anthropic
        and candidate_anthropic is not candidate
    ):
        close = getattr(candidate_anthropic, "close", None)
        if callable(close):
            try:
                close()
            except Exception as exc:
                failures.append(f"close candidate anthropic client: {type(exc).__name__}")
    return tuple(failures)


def commit_model_switch(
    agent: Any,
    prepared: PreparedModelSwitch,
    apply_runtime: Callable[[], Any] | None = None,
) -> Any:
    lock = getattr(agent, "_model_switch_lock", None)
    if lock is None:
        lock = threading.RLock()
        agent._model_switch_lock = lock
    home = Path(prepared.hermes_home) if prepared.hermes_home else _switch_home(agent)
    session_id = prepared.session_id or getattr(agent, "session_id", None)
    if home is None:
        with lock:
            return _commit_model_switch_locked(agent, prepared, apply_runtime)
    session_id = _safe_session_id(
        session_id, fallback_identity=(prepared.provider, prepared.model),
    )
    os_lock = InterprocessSwitchLock(
        home / "locks" / f"model-switch-{hashlib.sha256(session_id.encode()).hexdigest()}.lock",
        timeout=float(getattr(agent, "_model_switch_lock_timeout", 5.0)),
    )
    with os_lock:
        with lock:
            return _commit_durable_model_switch_locked(
                agent, prepared, home, session_id, apply_runtime
            )


def _journal_payload(prepared: PreparedModelSwitch, session_id: str, transaction_id: str) -> dict[str, Any]:
    return {
        "transaction_id": transaction_id,
        "session_id": session_id,
        "old": {"provider": prepared.old_identity[0], "model": prepared.old_identity[1]},
        "new": {"provider": prepared.provider, "model": prepared.model},
    }


def _commit_durable_model_switch_locked(
    agent: Any,
    prepared: PreparedModelSwitch,
    home: Path,
    session_id: str,
    apply_runtime: Callable[[], Any] | None,
) -> Any:
    transaction_id = prepared.transaction_id or str(uuid.uuid4())
    generation = (prepared.old_state_version or 0) + 1
    journal = SwitchJournal(
        prepared.journal_path or home / "state" / "model_switch_journal" / f"{transaction_id}.json",
        secret_values=(prepared.api_key,) if isinstance(prepared.api_key, str) else (),
    )
    payload = _journal_payload(prepared, session_id, transaction_id)
    if not journal.path.exists():
        journal.transition("PREPARED", generation=generation, payload=payload)
        _observe_transition(agent, "PREPARED", payload)

    authoritative = _read_commit_authority(agent, home, session_id)
    expected = prepared.old_state_version or 0
    if authoritative["generation"] != expected:
        journal.transition("ABORTED", generation=generation, payload=payload)
        journal.remove()
        raise PromptProfileError("SWITCH_CONFLICT")
    if _current_identity(agent) != prepared.old_identity:
        journal.transition("ABORTED", generation=generation, payload=payload)
        journal.remove()
        raise PromptProfileError("STALE_PREPARED_SWITCH")
    snapshot = capture_model_switch_snapshot(agent)
    applied: list[DurableMutation] = []
    authority_committed = False
    try:
        journal.transition("CONFIG_APPLIED", generation=generation, payload=payload)
        _observe_transition(agent, "CONFIG_APPLIED", payload)

        result = _apply_prepared_runtime(agent, prepared, apply_runtime)
        journal.transition("RUNTIME_STAGED", generation=generation, payload=payload)
        _observe_transition(agent, "RUNTIME_STAGED", payload)

        # Durable adapters observe the fully staged NEW runtime and exact
        # admitted prompt. They run BEFORE CAS so an in-process failure here
        # compensates to OLD (the TUI "failed switch is a no-op" contract).
        # The durable ledger records each write so recovery fails closed
        # (RECOVERY_CONFLICT) instead of silently ABORTing when a crash
        # between a durable write and CAS may have left NEW durable state.
        for mutation in prepared.durable_mutations:
            _append_durable_ledger(home, transaction_id, mutation.label, generation)
            applied.append(mutation)
            mutation.apply()

        state = {
            "schema_version": 1,
            "session_id": session_id,
            "generation": generation,
            "transaction_id": transaction_id,
            "provider": prepared.provider,
            "model": prepared.model,
        }
        _cas_commit_authority(agent, home, session_id, expected=expected, record=state)
        authority_committed = True
        agent._prompt_profile_state_version = generation
        journal.transition("COMMITTED", generation=generation, payload=payload)
        _observe_transition(agent, "COMMITTED", payload)
    except BaseException as original:
        if authority_committed:
            # CAS is the authority boundary. Never manufacture an OLD runtime
            # or durable state after NEW became authoritative, and preserve the
            # journal as the recoverable conflict record.
            _apply_prepared_runtime(agent, prepared, None)
            agent._prompt_profile_state_version = generation
            raise
        compensation_failures: list[str] = []
        for mutation in reversed(applied):
            try:
                mutation.compensate()
            except Exception as exc:
                compensation_failures.append(f"compensate {mutation.label}: {type(exc).__name__}")
        failures = tuple(compensation_failures) + rollback_model_switch(agent, snapshot)
        try:
            journal.transition("ABORTED", generation=generation, payload=payload)
            journal.remove()
            _remove_durable_ledger(home, transaction_id)
        except Exception as exc:
            failures += (f"journal abort: {type(exc).__name__}",)
        if failures:
            raise PromptProfileError("ROLLBACK_INCOMPLETE: " + "; ".join(failures)) from original
        raise

    # Irreversible resource retirement is deliberately after durable COMMITTED.
    try:
        journal.transition("CLEANUP_PENDING", generation=generation, payload=payload)
        _observe_transition(agent, "CLEANUP_PENDING", payload)
        old_client = snapshot.old_client
        new_client = getattr(agent, "client", None)
        if old_client is not None and old_client is not new_client:
            close = getattr(old_client, "close", None)
            if callable(close):
                close()
        journal.transition("DONE", generation=generation, payload=payload)
        journal.remove()
        _remove_durable_ledger(home, transaction_id)
    except BaseException:
        # Authority/runtime/durable NEW state remains converged. The journal
        # records the exact unfinished finalization point for recovery.
        raise
    return result


def _apply_prepared_runtime(
    agent: Any,
    prepared: PreparedModelSwitch,
    apply_runtime: Callable[[], Any] | None,
) -> Any:
    result = apply_runtime() if apply_runtime is not None else None
    for name, value in (prepared.runtime_updates or {}).items():
        if name == "context_compressor":
            target = getattr(agent, "context_compressor", None)
            if target is not None and value is not None:
                for field in _COMPRESSOR_FIELDS:
                    if hasattr(value, field):
                        setattr(target, field, _copy_value(getattr(value, field)))
            continue
        if value is not _MISSING:
            setattr(agent, name, _copy_value(value))
    if prepared.candidate_client is not None:
        agent.client = prepared.candidate_client
    if prepared.rendered_profile is not None:
        agent._prompt_profile = prepared.rendered_profile.cache_identity
        agent._prompt_profile_rendered = prepared.rendered_profile
        agent._cached_system_prompt = prepared.final_prompt
        agent._persisted_system_prompt_sha256 = hashlib.sha256(prepared.final_prompt.encode("utf-8")).hexdigest()
        compressor = getattr(agent, "context_compressor", None)
        if compressor is not None and prepared.effective_window is not None:
            compressor.context_length = prepared.effective_window
    else:
        agent._prompt_profile = None
        agent._prompt_profile_rendered = None
        agent._cached_system_prompt = None
    return result


def _commit_model_switch_locked(
    agent: Any,
    prepared: PreparedModelSwitch,
    apply_runtime: Callable[[], Any] | None = None,
) -> Any:
    if _current_identity(agent) != prepared.old_identity:
        raise PromptProfileError("STALE_PREPARED_SWITCH")
    if getattr(agent, "_prompt_profile_state_version", None) != prepared.old_state_version:
        raise PromptProfileError("STALE_PREPARED_SWITCH")
    snapshot = capture_model_switch_snapshot(agent)
    applied: list[DurableMutation] = []
    try:
        result = apply_runtime() if apply_runtime is not None else None
        for name, value in (prepared.runtime_updates or {}).items():
            if name == "context_compressor":
                # Preserve the live compressor object's identity; callbacks
                # and plugins may retain it.  Copy the fully prepared state.
                target = getattr(agent, "context_compressor", None)
                if target is not None and value is not None:
                    for field in _COMPRESSOR_FIELDS:
                        if hasattr(value, field):
                            setattr(target, field, _copy_value(getattr(value, field)))
                continue
            if value is not _MISSING:
                setattr(agent, name, _copy_value(value))
        if prepared.candidate_client is not None:
            agent.client = prepared.candidate_client
        if prepared.rendered_profile is not None:
            agent._prompt_profile = prepared.rendered_profile.cache_identity
            agent._prompt_profile_rendered = prepared.rendered_profile
            agent._cached_system_prompt = prepared.final_prompt
            agent._persisted_system_prompt_sha256 = hashlib.sha256(
                prepared.final_prompt.encode("utf-8")
            ).hexdigest()
            compressor = getattr(agent, "context_compressor", None)
            if compressor is not None and prepared.effective_window is not None:
                compressor.context_length = prepared.effective_window
        else:
            # Never carry one model's adapter/profile identity into a legacy
            # route that has no registered profile.
            agent._prompt_profile = None
            agent._prompt_profile_rendered = None
            agent._cached_system_prompt = None
        for mutation in prepared.durable_mutations:
            applied.append(mutation)
            # Register first: apply may complete one of several writes before
            # raising, and its compensation owns that partial state too.
            mutation.apply()
        agent._prompt_profile_state_version = (
            (prepared.old_state_version or 0) + 1
            if isinstance(prepared.old_state_version, (int, type(None))) else 1
        )
        return result
    except BaseException as original:
        compensation_failures: list[str] = []
        for mutation in reversed(applied):
            try:
                mutation.compensate()
            except Exception as exc:
                compensation_failures.append(f"compensate {mutation.label}: {type(exc).__name__}")
        failures = tuple(compensation_failures) + rollback_model_switch(agent, snapshot)
        if failures:
            raise PromptProfileError(
                "ROLLBACK_INCOMPLETE: " + "; ".join(failures)
            ) from original
        raise


def _durable_ledger_path(home: Path, transaction_id: str) -> Path:
    return home / "state" / "model_switch_journal" / "ledgers" / f"{transaction_id}.json"


def _append_durable_ledger(home: Path, transaction_id: str, label: str, generation: int) -> None:
    """Append (fsync'd) a durable-write ledger entry BEFORE the write executes.

    Recovery uses this ledger to fail closed: a journal that reached a
    pre-CAS state with ledger entries may have left NEW durable state behind,
    which process-local compensation cannot repair across a crash.
    """
    path = _durable_ledger_path(home, transaction_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    if path.is_symlink():
        raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
    entries: list[dict[str, Any]] = []
    if path.exists():
        with open(path, "r", encoding="utf-8") as handle:
            try:
                loaded = json.load(handle)
            except (json.JSONDecodeError, OSError) as exc:
                raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS") from exc
            if isinstance(loaded, list):
                entries = [e for e in loaded if isinstance(e, dict)]
    entries.append({"label": label, "generation": generation, "at": time.time()})
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(entries, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _durable_ledger_entries(home: Path, transaction_id: str) -> list[dict[str, Any]]:
    path = _durable_ledger_path(home, transaction_id)
    if not path.exists() or path.is_symlink():
        return []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return []
    return [e for e in loaded if isinstance(e, dict)] if isinstance(loaded, list) else []


def _remove_durable_ledger(home: Path, transaction_id: str) -> None:
    try:
        _durable_ledger_path(home, transaction_id).unlink()
    except FileNotFoundError:
        pass


def recover_model_switches(
    home: Path | str, *, session_id: str | None = None, session_db: Any = None,
) -> list[dict[str, Any]]:
    """Resolve incomplete journals from authoritative durable generation state.

    The journal never overrides the state record. A journal/state disagreement
    outside the two mechanically decidable outcomes fails closed.
    """
    home = Path(home)
    journal_dir = home / "state" / "model_switch_journal"
    if not journal_dir.exists():
        return []
    try:
        journal_stat = journal_dir.lstat()
        resolved_home = home.resolve(strict=True)
        resolved_journal_dir = journal_dir.resolve(strict=True)
        resolved_journal_dir.relative_to(resolved_home)
    except (OSError, ValueError) as exc:
        raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS") from exc
    if stat.S_ISLNK(journal_stat.st_mode) or not stat.S_ISDIR(journal_stat.st_mode):
        raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
    results: list[dict[str, Any]] = []
    recovery_lock = InterprocessSwitchLock(home / "locks" / "model-switch-recovery.lock", timeout=5.0)
    with recovery_lock:
        # Validate the complete recovery set before changing any journal.  If a
        # later file is corrupt, or two live transactions claim one session
        # generation, resolving an earlier file would create a partial startup
        # recovery instead of failing closed.
        pending: list[tuple[SwitchJournal, Mapping[str, Any], str, str]] = []
        transaction_keys: set[tuple[str, int]] = set()
        for path in sorted(journal_dir.glob("*.json")):
            journal = SwitchJournal(path)
            record = journal.recover(expected_generation=None)
            payload = record["payload"]
            record_session = payload.get("session_id")
            if not isinstance(record_session, str):
                raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
            record_session = _safe_session_id(record_session)
            if session_id is not None and record_session != session_id:
                continue
            transaction_id = payload.get("transaction_id")
            if not isinstance(transaction_id, str):
                raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
            transaction_key = (record_session, record["generation"])
            if transaction_key in transaction_keys:
                raise PromptProfileError("SWITCH_JOURNAL_AMBIGUOUS")
            transaction_keys.add(transaction_key)
            pending.append((journal, record, record_session, transaction_id))

        for journal, record, record_session, transaction_id in pending:
            reader = getattr(session_db, "get_model_switch_state", None)
            if callable(reader):
                try:
                    state = MappingProxyType(dict(reader(record_session)))
                except Exception as exc:
                    raise PromptProfileError("SWITCH_STATE_AMBIGUOUS") from exc
            else:
                state = _read_authoritative_state(home, record_session)
            expected_new = record["generation"]
            if (
                state["generation"] == expected_new
                and state.get("transaction_id") == transaction_id
            ):
                outcome = "COMMITTED"
            elif (
                state["generation"] == expected_new - 1
                and state.get("transaction_id") != transaction_id
            ):
                # The authoritative state may legitimately retain the previous
                # generation's transaction ID.  Only this journal's ID at the
                # new generation can establish commit.
                if _durable_ledger_entries(home, transaction_id):
                    # Durable writes may have escaped before CAS.  Process-local
                    # compensation cannot repair them across a crash, so the
                    # honest outcome is a conflict requiring operator
                    # intervention — never a silent ABORTED that leaves the
                    # durable surface on the NEW route while authority says OLD.
                    raise PromptProfileError("RECOVERY_CONFLICT")
                outcome = "ABORTED"
            else:
                raise PromptProfileError("RECOVERY_CONFLICT")
            journal.terminalize_recovery(
                "DONE" if outcome == "COMMITTED" else "ABORTED",
                generation=expected_new,
                payload=record["payload"],
            )
            journal.remove()
            results.append({
                "outcome": outcome,
                "generation": state["generation"],
                "session_id": record_session,
                "transaction_id": transaction_id,
            })
    return results


def activate_initial_profile(agent: Any, *, messages=(), tools=None) -> PreparedModelSwitch | None:
    """Run the same render/admission transaction for construction/resume."""
    home = _switch_home(agent)
    session_id = getattr(agent, "session_id", None)
    if home is not None:
        session_id = _safe_session_id(
            session_id,
            fallback_identity=(
                getattr(agent, "provider", None), getattr(agent, "model", None),
            ),
        )
        session_db = getattr(agent, "_session_db", None)
        recover_model_switches(
            home, session_id=session_id, session_db=session_db,
        )
        authoritative = _read_commit_authority(agent, home, session_id)
        agent._prompt_profile_state_version = authoritative["generation"]
        if authoritative["generation"]:
            if (
                getattr(agent, "provider", None) != authoritative.get("provider")
                or getattr(agent, "model", None) != authoritative.get("model")
            ):
                raise PromptProfileError("RECOVERY_CONFLICT")
    if find_profile(getattr(agent, "provider", ""), getattr(agent, "model", "")) is None:
        agent._prompt_profile = None
        agent._prompt_profile_rendered = None
        return None
    prepared = prepare_model_switch(
        agent,
        model=agent.model,
        provider=agent.provider,
        api_key=getattr(agent, "api_key", ""),
        base_url=getattr(agent, "base_url", ""),
        api_mode=getattr(agent, "api_mode", ""),
        messages=tuple(messages or ()),
        tools=tuple(tools if tools is not None else (getattr(agent, "tools", ()) or ())),
        requested_output_tokens=max(
            value for value in (
                getattr(getattr(agent, "context_compressor", None), "max_tokens", None),
                getattr(getattr(agent, "context_compressor", None), "max_output_tokens", None),
                getattr(agent, "max_tokens", None),
                getattr(agent, "_ephemeral_max_output_tokens", None),
                0,
            ) if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        ),
    )
    commit_model_switch(agent, prepared)
    return prepared
