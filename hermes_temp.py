"""Hermes-owned temporary storage authority.

Version 1 deliberately never consults :mod:`tempfile` or the host temporary
directory.  Temporary state belongs to the active profile's
``HERMES_HOME/tmp`` directory and is resolved at call time so gateway profile
ContextVars cannot bleed state across profiles.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Iterator, Mapping

from hermes_constants import get_hermes_home, get_hermes_home_override


AUTHORITY_SCHEMA = "hermes.temp-authority"
AUTHORITY_VERSION = 1
_SCOPES = frozenset({"production", "test", "ci", "remote"})
_PURPOSE = re.compile(r"[a-z][a-z0-9-]{0,31}\Z")
_NONCE = re.compile(r"[0-9a-f]{32}\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_FORBIDDEN_POSIX_ROOTS = tuple(Path(item) for item in (
    "/tmp", "/var/tmp", "/dev/shm", "/private/tmp", "/private/var/tmp",
))
_AUTHORITY_ENV = frozenset({
    "HERMES_TEMP_ROOT", "HERMES_TEMP_ROOT_IDENTITY", "HERMES_TEMP_SCOPE",
    "HERMES_TEMP_RUN_NONCE", "HERMES_TEMP_MANIFEST_SHA256",
    "HERMES_TEMP_AUTHORITY_VERSION", "TMPDIR", "TEMP", "TMP",
})


class TempAuthorityError(RuntimeError):
    """The requested temporary-storage authority is unsafe or inconsistent."""


class TempAuthorityConfigurationError(TempAuthorityError):
    """The caller supplied an invalid or incomplete authority contract."""


class TempAuthoritySecurityError(TempAuthorityError):
    """Filesystem state does not satisfy the authority security contract."""


class TempAuthorityCleanupError(TempAuthorityError):
    """An owned temporary object cannot be reaped without weakening custody."""


def _canonical(path: Path, *, must_exist: bool) -> Path:
    try:
        return path.expanduser().resolve(strict=must_exist)
    except (OSError, RuntimeError) as exc:
        raise TempAuthorityConfigurationError(f"cannot resolve temporary authority path: {path}") from exc


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _validate_purpose(purpose: str) -> str:
    if not isinstance(purpose, str) or not _PURPOSE.fullmatch(purpose):
        raise TempAuthorityConfigurationError("temporary purpose is invalid")
    return purpose


def _reject_symlink_ancestors(path: Path) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        if not current.exists() and not current.is_symlink():
            continue
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise TempAuthoritySecurityError(f"cannot inspect authority ancestor: {current}") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise TempAuthoritySecurityError(f"authority ancestor is a symlink: {current}")


def _clear_directory_fd(descriptor: int) -> None:
    try:
        entries = list(os.scandir(descriptor))
    except OSError as exc:
        raise TempAuthorityCleanupError("cannot enumerate owned temporary directory") from exc
    for entry in entries:
        try:
            metadata = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(metadata.st_mode):
                flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
                child = os.open(entry.name, flags, dir_fd=descriptor)
                try:
                    pinned = os.fstat(child)
                    if (pinned.st_dev, pinned.st_ino) != (metadata.st_dev, metadata.st_ino):
                        raise TempAuthorityCleanupError("owned child directory was replaced")
                    _clear_directory_fd(child)
                finally:
                    os.close(child)
                os.rmdir(entry.name, dir_fd=descriptor)
            else:
                os.unlink(entry.name, dir_fd=descriptor)
        except TempAuthorityCleanupError:
            raise
        except OSError as exc:
            raise TempAuthorityCleanupError("owned temporary child cleanup failed") from exc


def _validate_binding(
    scope: str, run_nonce: str | None, manifest_sha256: str | None,
) -> tuple[str, str | None]:
    if scope not in _SCOPES:
        raise TempAuthorityConfigurationError("temporary authority scope is invalid")
    if scope == "production":
        if manifest_sha256 is not None:
            raise TempAuthorityConfigurationError("production authority forbids manifest binding")
        if run_nonce is None:
            return secrets.token_hex(16), None
        if not isinstance(run_nonce, str) or not _NONCE.fullmatch(run_nonce):
            raise TempAuthorityConfigurationError("production authority nonce is invalid")
        return run_nonce, None
    if not isinstance(run_nonce, str) or not _NONCE.fullmatch(run_nonce):
        raise TempAuthorityConfigurationError(
            f"{scope} temporary authority requires a valid run nonce"
        )
    if scope in {"ci", "remote"}:
        if not isinstance(manifest_sha256, str) or not _SHA256.fullmatch(manifest_sha256):
            raise TempAuthorityConfigurationError(
                f"{scope} temporary authority requires a manifest SHA-256"
            )
        return run_nonce, manifest_sha256
    if manifest_sha256 is not None:
        raise TempAuthorityConfigurationError("test temporary authority forbids a manifest binding")
    return run_nonce, None


def _validate_dir(path: Path, *, mode: int, identity: tuple[int, int] | None = None) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise TempAuthoritySecurityError(f"temporary authority directory is unavailable: {path}") from exc
    expected_uid = os.geteuid()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != expected_uid
        or stat.S_IMODE(metadata.st_mode) != mode
        or metadata.st_nlink < 2
        or (identity is not None and (metadata.st_dev, metadata.st_ino) != identity)
    ):
        raise TempAuthoritySecurityError(f"temporary authority directory is unsafe: {path}")
    return metadata


def _open_owned_root(root: Path, identity: tuple[int, int]) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(root, flags)
        metadata = os.fstat(descriptor)
    except OSError as exc:
        raise TempAuthorityCleanupError("owned temporary root is unavailable") from exc
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_nlink < 2
        or (metadata.st_dev, metadata.st_ino) != identity
    ):
        os.close(descriptor)
        raise TempAuthorityCleanupError("owned temporary root identity changed")
    return descriptor


def _quarantine_owned_name(root_fd: int, name: str) -> str:
    """Atomically move an owned leaf to an unpredictable name in its root."""
    for _attempt in range(16):
        quarantine = f".hermes-reap-{secrets.token_hex(16)}"
        try:
            os.stat(quarantine, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            try:
                os.rename(
                    name,
                    quarantine,
                    src_dir_fd=root_fd,
                    dst_dir_fd=root_fd,
                )
            except OSError as exc:
                raise TempAuthorityCleanupError(
                    "owned temporary object could not be quarantined"
                ) from exc
            return quarantine
    raise TempAuthorityCleanupError("could not reserve a cleanup quarantine name")


def _restore_quarantined_name(root_fd: int, quarantine: str, name: str) -> None:
    """Restore a rejected quarantine without overwriting a newer object."""
    try:
        os.stat(name, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise TempAuthorityCleanupError(
            "cannot verify original name before quarantine restoration"
        ) from exc
    else:
        raise TempAuthorityCleanupError(
            "cannot restore quarantined object without overwriting a replacement"
        )
    try:
        os.rename(
            quarantine,
            name,
            src_dir_fd=root_fd,
            dst_dir_fd=root_fd,
        )
    except OSError as exc:
        raise TempAuthorityCleanupError("cannot restore quarantined object") from exc


@dataclass
class OwnedTempDir:
    path: Path
    identity: tuple[int, int]
    root: Path
    root_identity: tuple[int, int]
    creator_pid: int
    _cleaned: bool = False

    def verify(self) -> None:
        if os.getpid() != self.creator_pid:
            raise TempAuthorityCleanupError("only the creator process may manage this directory")
        descriptor = _open_owned_root(self.root, self.root_identity)
        try:
            metadata = os.stat(self.path.name, dir_fd=descriptor, follow_symlinks=False)
        except OSError as exc:
            raise TempAuthorityCleanupError("owned temporary directory is unavailable") from exc
        finally:
            os.close(descriptor)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or metadata.st_nlink < 2
            or (metadata.st_dev, metadata.st_ino) != self.identity
        ):
            raise TempAuthorityCleanupError("owned temporary directory identity changed")

    def cleanup(self) -> None:
        if os.getpid() != self.creator_pid:
            raise TempAuthorityCleanupError("only the creator process may reap this directory")
        descriptor = _open_owned_root(self.root, self.root_identity)
        try:
            try:
                metadata = os.stat(self.path.name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                if self._cleaned:
                    return
                raise TempAuthorityCleanupError("owned temporary directory disappeared")
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o700
                or metadata.st_nlink < 2
                or (metadata.st_dev, metadata.st_ino) != self.identity
            ):
                raise TempAuthorityCleanupError("owned temporary directory was replaced")
            quarantine = _quarantine_owned_name(descriptor, self.path.name)
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            try:
                leaf = os.open(quarantine, flags, dir_fd=descriptor)
            except OSError as exc:
                _restore_quarantined_name(descriptor, quarantine, self.path.name)
                raise TempAuthorityCleanupError(
                    "cannot pin quarantined temporary directory"
                ) from exc
            try:
                pinned = os.fstat(leaf)
                if (
                    not stat.S_ISDIR(pinned.st_mode)
                    or pinned.st_uid != os.geteuid()
                    or stat.S_IMODE(pinned.st_mode) != 0o700
                    or pinned.st_nlink < 2
                    or (pinned.st_dev, pinned.st_ino) != self.identity
                ):
                    _restore_quarantined_name(descriptor, quarantine, self.path.name)
                    raise TempAuthorityCleanupError(
                        "owned temporary directory changed before cleanup"
                    )
                _clear_directory_fd(leaf)
            finally:
                os.close(leaf)
            final = os.stat(quarantine, dir_fd=descriptor, follow_symlinks=False)
            if (final.st_dev, final.st_ino) != self.identity:
                _restore_quarantined_name(descriptor, quarantine, self.path.name)
                raise TempAuthorityCleanupError(
                    "owned temporary directory changed during cleanup"
                )
            os.rmdir(quarantine, dir_fd=descriptor)
            self._cleaned = True
        except TempAuthorityCleanupError:
            raise
        except OSError as exc:
            raise TempAuthorityCleanupError("owned temporary directory cleanup failed") from exc
        finally:
            os.close(descriptor)

    def __fspath__(self) -> str:
        return str(self.path)


@dataclass
class OwnedTempFile:
    path: Path
    identity: tuple[int, int]
    root: Path
    root_identity: tuple[int, int]
    creator_pid: int
    _cleaned: bool = False

    def verify(self) -> None:
        if os.getpid() != self.creator_pid:
            raise TempAuthorityCleanupError("only the creator process may manage this file")
        descriptor = _open_owned_root(self.root, self.root_identity)
        try:
            metadata = os.stat(self.path.name, dir_fd=descriptor, follow_symlinks=False)
        except OSError as exc:
            raise TempAuthorityCleanupError(f"owned temporary file is unavailable: {self.path}") from exc
        finally:
            os.close(descriptor)
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
            or (metadata.st_dev, metadata.st_ino) != self.identity
        ):
            raise TempAuthorityCleanupError(f"owned temporary file identity changed: {self.path}")

    def cleanup(self) -> None:
        if os.getpid() != self.creator_pid:
            raise TempAuthorityCleanupError("only the creator process may reap this file")
        descriptor = _open_owned_root(self.root, self.root_identity)
        try:
            try:
                metadata = os.stat(self.path.name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                if self._cleaned:
                    return
                raise TempAuthorityCleanupError("owned temporary file disappeared")
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
                or (metadata.st_dev, metadata.st_ino) != self.identity
            ):
                raise TempAuthorityCleanupError("owned temporary file was replaced")
            quarantine = _quarantine_owned_name(descriptor, self.path.name)
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            try:
                pinned_fd = os.open(quarantine, flags, dir_fd=descriptor)
            except OSError as exc:
                _restore_quarantined_name(descriptor, quarantine, self.path.name)
                raise TempAuthorityCleanupError(
                    "cannot pin quarantined temporary file"
                ) from exc
            try:
                pinned = os.fstat(pinned_fd)
                if (
                    not stat.S_ISREG(pinned.st_mode)
                    or pinned.st_uid != os.geteuid()
                    or stat.S_IMODE(pinned.st_mode) != 0o600
                    or pinned.st_nlink != 1
                    or (pinned.st_dev, pinned.st_ino) != self.identity
                ):
                    _restore_quarantined_name(descriptor, quarantine, self.path.name)
                    raise TempAuthorityCleanupError(
                        "owned temporary file changed before cleanup"
                    )
            finally:
                os.close(pinned_fd)
            final = os.stat(quarantine, dir_fd=descriptor, follow_symlinks=False)
            if (final.st_dev, final.st_ino) != self.identity:
                _restore_quarantined_name(descriptor, quarantine, self.path.name)
                raise TempAuthorityCleanupError(
                    "owned temporary file changed during cleanup"
                )
            os.unlink(quarantine, dir_fd=descriptor)
            self._cleaned = True
        except TempAuthorityCleanupError:
            raise
        except OSError as exc:
            raise TempAuthorityCleanupError("owned temporary file cleanup failed") from exc
        finally:
            os.close(descriptor)

    def __fspath__(self) -> str:
        return str(self.path)


@dataclass
class TempAuthority:
    scope: str
    hermes_home: Path
    root: Path
    run_nonce: str | None
    manifest_sha256: str | None
    identity: tuple[int, int]
    _root_fd: int

    def verify(self) -> None:
        metadata = _validate_dir(self.root, mode=0o700, identity=self.identity)
        descriptor = os.fstat(self._root_fd)
        if (
            not stat.S_ISDIR(descriptor.st_mode)
            or descriptor.st_uid != os.geteuid()
            or (descriptor.st_dev, descriptor.st_ino) != self.identity
            or (metadata.st_dev, metadata.st_ino) != self.identity
        ):
            raise TempAuthorityError("temporary authority descriptor identity changed")

    def close(self) -> None:
        if self._root_fd >= 0:
            os.close(self._root_fd)
            self._root_fd = -1

    def __enter__(self) -> "TempAuthority":
        self.verify()
        return self

    def __exit__(self, _kind: object, _value: object, _traceback: object) -> None:
        self.close()

    def _name(self, purpose: str, suffix: str = "") -> str:
        purpose = _validate_purpose(purpose)
        if (
            not isinstance(suffix, str) or "/" in suffix or "\\" in suffix
            or "\x00" in suffix or ".." in suffix or len(suffix) > 32
        ):
            raise TempAuthorityConfigurationError("temporary suffix is invalid")
        return f"{purpose}-{secrets.token_hex(12)}{suffix}"

    def mkdir(self, purpose: str) -> OwnedTempDir:
        self.verify()
        for _attempt in range(16):
            name = self._name(purpose)
            try:
                os.mkdir(name, mode=0o700, dir_fd=self._root_fd)
            except FileExistsError:
                continue
            path = self.root / name
            metadata = _validate_dir(path, mode=0o700)
            return OwnedTempDir(
                path, (metadata.st_dev, metadata.st_ino),
                self.root, self.identity, os.getpid(),
            )
        raise TempAuthorityError("could not reserve a unique temporary directory")

    def mkstemp(self, purpose: str, suffix: str = "") -> tuple[int, OwnedTempFile]:
        self.verify()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        for _attempt in range(16):
            name = self._name(purpose, suffix)
            try:
                descriptor = os.open(name, flags, 0o600, dir_fd=self._root_fd)
            except FileExistsError:
                continue
            metadata = os.fstat(descriptor)
            owned = OwnedTempFile(
                self.root / name, (metadata.st_dev, metadata.st_ino),
                self.root, self.identity, os.getpid(),
            )
            owned.verify()
            return descriptor, owned
        raise TempAuthorityError("could not reserve a unique temporary file")

    @contextlib.contextmanager
    def temporary_directory(self, purpose: str) -> Iterator[OwnedTempDir]:
        owned = self.mkdir(purpose)
        try:
            yield owned
        finally:
            owned.cleanup()

    @contextlib.contextmanager
    def named_temporary_file(
        self,
        purpose: str,
        *,
        mode: str = "w+b",
        suffix: str = "",
        delete: bool = True,
        encoding: str | None = None,
    ) -> Iterator[IO[object]]:
        descriptor, owned = self.mkstemp(purpose, suffix)
        stream: IO[object] | None = None
        try:
            stream = os.fdopen(descriptor, mode, encoding=encoding)
            descriptor = -1
            yield stream
        finally:
            if stream is not None and not stream.closed:
                stream.close()
            elif descriptor >= 0:
                os.close(descriptor)
            if delete:
                owned.cleanup()

    def child_environment(self) -> dict[str, str]:
        self.verify()
        root = str(self.root)
        values = {
            "HERMES_HOME": str(self.hermes_home),
            "HERMES_TEMP_ROOT": root,
            "HERMES_TEMP_ROOT_IDENTITY": f"v1:{self.identity[0]}:{self.identity[1]}",
            "HERMES_TEMP_SCOPE": self.scope,
            "HERMES_TEMP_AUTHORITY_VERSION": str(AUTHORITY_VERSION),
            "TMPDIR": root,
            "TEMP": root,
            "TMP": root,
        }
        if self.run_nonce is not None:
            values["HERMES_TEMP_RUN_NONCE"] = self.run_nonce
        if self.manifest_sha256 is not None:
            values["HERMES_TEMP_MANIFEST_SHA256"] = self.manifest_sha256
        return values

    def receipt(self) -> dict[str, object]:
        self.verify()
        return {
            "schema": AUTHORITY_SCHEMA,
            "version": AUTHORITY_VERSION,
            "scope": self.scope,
            "hermes_home": str(self.hermes_home),
            "root": str(self.root),
            "run_nonce": self.run_nonce,
            "manifest_sha256": self.manifest_sha256,
            "owner": {"kind": "posix-uid", "id": os.geteuid()},
            "identity": {
                "device": self.identity[0],
                "inode": self.identity[1],
                "mode": "0700",
            },
        }

    def receipt_sha256(self) -> str:
        payload = json.dumps(self.receipt(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(payload).hexdigest()


def resolve_temp_authority(
    *,
    scope: str,
    run_nonce: str | None = None,
    manifest_sha256: str | None = None,
    env: Mapping[str, str] | None = None,
) -> TempAuthority:
    """Resolve and open the active profile's exact temporary authority."""
    if os.name != "posix" or not hasattr(os, "geteuid"):
        raise TempAuthorityConfigurationError("TempAuthority v1 requires POSIX ownership semantics")
    environment = os.environ if env is None else env
    configured = str(environment.get("HERMES_TEMP_ROOT", "")).strip()
    observed_authority = {
        name: str(environment.get(name, "")).strip() for name in _AUTHORITY_ENV
    }
    if not configured:
        bootstrap_fields = {
            "HERMES_TEMP_RUN_NONCE", "HERMES_TEMP_MANIFEST_SHA256",
        }
        if any(
            value for name, value in observed_authority.items()
            if name not in bootstrap_fields
        ):
            raise TempAuthorityConfigurationError(
                "partial inherited temporary authority is forbidden"
            )
        inherited_nonce = observed_authority["HERMES_TEMP_RUN_NONCE"] or None
        inherited_manifest = observed_authority["HERMES_TEMP_MANIFEST_SHA256"] or None
        if inherited_nonce is not None and inherited_nonce != run_nonce:
            raise TempAuthorityConfigurationError(
                "bootstrap run nonce conflicts with the explicit binding"
            )
        if inherited_manifest is not None and inherited_manifest != manifest_sha256:
            raise TempAuthorityConfigurationError(
                "bootstrap manifest conflicts with the explicit binding"
            )
    if configured:
        required_inherited = {
            "HERMES_TEMP_ROOT_IDENTITY", "HERMES_TEMP_SCOPE",
            "HERMES_TEMP_RUN_NONCE", "HERMES_TEMP_AUTHORITY_VERSION",
            "TMPDIR", "TEMP", "TMP",
        }
        if scope in {"ci", "remote"}:
            required_inherited.add("HERMES_TEMP_MANIFEST_SHA256")
        missing = sorted(
            name for name in required_inherited if not observed_authority[name]
        )
        if not str(environment.get("HERMES_HOME", "")).strip():
            missing.insert(0, "HERMES_HOME")
        if missing:
            raise TempAuthorityConfigurationError(
                "incomplete inherited temporary authority: " + ", ".join(missing)
            )
        inherited_nonce = observed_authority["HERMES_TEMP_RUN_NONCE"] or None
        inherited_manifest = observed_authority["HERMES_TEMP_MANIFEST_SHA256"] or None
        if run_nonce is None:
            run_nonce = inherited_nonce
        elif inherited_nonce != run_nonce:
            raise TempAuthorityConfigurationError(
                "explicit run nonce conflicts with inherited temporary authority"
            )
        if manifest_sha256 is None:
            manifest_sha256 = inherited_manifest
        elif inherited_manifest != manifest_sha256:
            raise TempAuthorityConfigurationError(
                "explicit manifest conflicts with inherited temporary authority"
            )
    run_nonce, manifest_sha256 = _validate_binding(scope, run_nonce, manifest_sha256)
    override = get_hermes_home_override()
    configured_home = str(environment.get("HERMES_HOME", "")).strip()
    raw_home = Path(override) if override else (
        Path(configured_home) if configured_home else get_hermes_home()
    )
    if not raw_home.is_absolute():
        raise TempAuthorityConfigurationError("HERMES_HOME must be absolute")
    _reject_symlink_ancestors(raw_home.expanduser())
    home = _canonical(raw_home, must_exist=False)
    for forbidden in _FORBIDDEN_POSIX_ROOTS:
        if _is_within(home, forbidden):
            raise TempAuthorityConfigurationError("HERMES_HOME cannot be under a system temporary root")
    try:
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError as exc:
        raise TempAuthoritySecurityError(f"cannot create HERMES_HOME: {home}") from exc
    _reject_symlink_ancestors(home)
    home_metadata = home.lstat()
    if (
        stat.S_ISLNK(home_metadata.st_mode)
        or not stat.S_ISDIR(home_metadata.st_mode)
        or home_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(home_metadata.st_mode) & 0o022
    ):
        raise TempAuthoritySecurityError("HERMES_HOME is not a private owned directory")
    root = home / "tmp"
    if configured:
        configured_path = Path(configured)
        if not configured_path.is_absolute() or _canonical(configured_path, must_exist=False) != root:
            raise TempAuthorityConfigurationError("HERMES_TEMP_ROOT does not match active HERMES_HOME/tmp")
    try:
        root.mkdir(mode=0o700, exist_ok=True)
    except OSError as exc:
        raise TempAuthoritySecurityError(f"cannot create temporary authority root: {root}") from exc
    _reject_symlink_ancestors(root)
    metadata = _validate_dir(root, mode=0o700)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        root_fd = os.open(root, flags)
    except OSError as exc:
        raise TempAuthoritySecurityError("cannot open temporary authority root") from exc
    identity = (metadata.st_dev, metadata.st_ino)
    authority = TempAuthority(scope, home, root, run_nonce, manifest_sha256, identity, root_fd)
    try:
        authority.verify()
    except Exception:
        authority.close()
        raise
    if configured:
        expected = authority.child_environment()
        required = {
            "HERMES_TEMP_ROOT", "HERMES_TEMP_ROOT_IDENTITY", "HERMES_TEMP_SCOPE",
            "HERMES_TEMP_RUN_NONCE", "HERMES_TEMP_AUTHORITY_VERSION",
            "TMPDIR", "TEMP", "TMP",
        }
        if scope in {"ci", "remote"}:
            required.add("HERMES_TEMP_MANIFEST_SHA256")
        elif observed_authority["HERMES_TEMP_MANIFEST_SHA256"]:
            authority.close()
            raise TempAuthorityConfigurationError("scope forbids inherited manifest binding")
        for name in required:
            if observed_authority[name] != expected[name]:
                authority.close()
                raise TempAuthoritySecurityError(f"inherited temporary authority mismatch: {name}")
    return authority


def current_temp_authority(env: Mapping[str, str] | None = None) -> TempAuthority:
    """Resolve authority from the exact process scope and optional run binding."""
    environment = os.environ if env is None else env
    scope = str(environment.get("HERMES_TEMP_SCOPE", "production"))
    nonce = environment.get("HERMES_TEMP_RUN_NONCE")
    manifest = environment.get("HERMES_TEMP_MANIFEST_SHA256")
    return resolve_temp_authority(
        scope=scope,
        run_nonce=nonce,
        manifest_sha256=manifest,
        env=environment,
    )
