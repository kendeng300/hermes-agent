from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from hermes_constants import reset_hermes_home_override, set_hermes_home_override
from hermes_temp import (
    TempAuthorityCleanupError,
    TempAuthorityConfigurationError,
    TempAuthorityError,
    TempAuthoritySecurityError,
    resolve_temp_authority,
)


NONCE = "1" * 32
MANIFEST = "a" * 64


def _authority(home: Path):
    token = set_hermes_home_override(home)
    try:
        authority = resolve_temp_authority(
            scope="test", run_nonce=NONCE, env={}
        )
    except Exception:
        reset_hermes_home_override(token)
        raise
    return token, authority


def test_v1_allocations_are_profile_owned_and_receipt_is_exact(tmp_path: Path) -> None:
    home = tmp_path / "profile"
    token, authority = _authority(home)
    try:
        with authority:
            owned_dir = authority.mkdir("parallel-test")
            descriptor, owned_file = authority.mkstemp("evidence", ".json")
            os.write(descriptor, b"{}")
            os.close(descriptor)
            owned_dir.verify()
            owned_file.verify()
            assert owned_dir.path.parent == home / "tmp"
            assert owned_file.path.parent == home / "tmp"
            assert oct(owned_dir.path.stat().st_mode & 0o777) == "0o700"
            assert oct(owned_file.path.stat().st_mode & 0o777) == "0o600"
            receipt = authority.receipt()
            assert receipt == json.loads(json.dumps(receipt, sort_keys=True))
            assert receipt["schema"] == "hermes.temp-authority"
            assert receipt["version"] == 1
            assert receipt["run_nonce"] == NONCE
            assert receipt["manifest_sha256"] is None
            child = authority.child_environment()
            assert {child[name] for name in ("HERMES_TEMP_ROOT", "TMPDIR", "TEMP", "TMP")} == {
                str(home / "tmp")
            }
            owned_file.cleanup()
            owned_dir.cleanup()
    finally:
        reset_hermes_home_override(token)


def test_v1_rejects_system_home_and_mismatched_root() -> None:
    token = set_hermes_home_override(Path("/tmp") / "forbidden-hermes")
    try:
        with pytest.raises(TempAuthorityError, match="system temporary"):
            resolve_temp_authority(scope="production", env={})
    finally:
        reset_hermes_home_override(token)


def test_v1_rejects_missing_binding_relative_home_and_root_identity(tmp_path: Path) -> None:
    token = set_hermes_home_override(tmp_path / "profile")
    try:
        with pytest.raises(TempAuthorityConfigurationError, match="run nonce"):
            resolve_temp_authority(scope="test", env={})
        with resolve_temp_authority(
            scope="test", run_nonce=NONCE, env={}
        ) as authority:
            inherited = authority.child_environment()
        wrong_root = dict(inherited)
        wrong_root["HERMES_TEMP_ROOT"] = str(tmp_path / "elsewhere")
        with pytest.raises(TempAuthorityError, match="does not match"):
            resolve_temp_authority(scope="test", env=wrong_root)
        wrong_identity = dict(inherited)
        wrong_identity["HERMES_TEMP_ROOT_IDENTITY"] = "v1:1:2"
        with pytest.raises(TempAuthorityError, match="ROOT_IDENTITY|identity mismatch"):
            resolve_temp_authority(scope="test", env=wrong_identity)
    finally:
        reset_hermes_home_override(token)
    token = set_hermes_home_override(Path("relative-home"))
    try:
        with pytest.raises(TempAuthorityError, match="absolute"):
            resolve_temp_authority(scope="production", env={})
    finally:
        reset_hermes_home_override(token)


def test_v1_rejects_symlink_root_and_identity_swap(tmp_path: Path) -> None:
    home = tmp_path / "profile"
    home.mkdir(mode=0o700)
    home.chmod(0o700)
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    target.chmod(0o700)
    (home / "tmp").symlink_to(target, target_is_directory=True)
    token = set_hermes_home_override(home)
    try:
        with pytest.raises(TempAuthorityError, match="symlink"):
            resolve_temp_authority(scope="production", env={})
    finally:
        reset_hermes_home_override(token)

    home2 = tmp_path / "profile2"
    token, authority = _authority(home2)
    try:
        original = home2 / "tmp"
        moved = home2 / "old-tmp"
        original.rename(moved)
        original.mkdir(mode=0o700)
        with pytest.raises(TempAuthorityError, match="identity changed|unsafe"):
            authority.verify()
    finally:
        authority.close()
        reset_hermes_home_override(token)


def test_v1_exact_scope_binding_typed_errors_and_idempotent_cleanup(tmp_path: Path) -> None:
    token = set_hermes_home_override(tmp_path / "profile")
    try:
        with resolve_temp_authority(scope="production", env={}) as production:
            assert len(production.run_nonce or "") == 32
            assert production.manifest_sha256 is None
        with resolve_temp_authority(scope="production", run_nonce=NONCE, env={}) as inherited:
            assert inherited.run_nonce == NONCE
        with pytest.raises(TempAuthorityConfigurationError, match="forbids"):
            resolve_temp_authority(
                scope="test", run_nonce=NONCE, manifest_sha256=MANIFEST, env={}
            )
        for malformed in ("A" * 32, "g" * 32, "1" * 31, "1" * 33):
            with pytest.raises(TempAuthorityConfigurationError, match="nonce"):
                resolve_temp_authority(scope="test", run_nonce=malformed, env={})
        for scope in ("ci", "remote"):
            with resolve_temp_authority(
                scope=scope, run_nonce=NONCE, manifest_sha256=MANIFEST, env={}
            ) as authority:
                owned = authority.mkdir(f"{scope}-owned")
                owned.cleanup()
                owned.cleanup()
        assert issubclass(TempAuthorityConfigurationError, TempAuthorityError)
        assert issubclass(TempAuthoritySecurityError, TempAuthorityError)
        assert issubclass(TempAuthorityCleanupError, TempAuthorityError)
    finally:
        reset_hermes_home_override(token)


def test_v1_inherited_environment_is_exact_and_env_home_is_honored(tmp_path: Path) -> None:
    home = tmp_path / "env-home"
    with resolve_temp_authority(
        scope="ci", run_nonce=NONCE, manifest_sha256=MANIFEST,
        env={"HERMES_HOME": str(home)},
    ) as authority:
        inherited = authority.child_environment()
        assert authority.hermes_home == home
    with resolve_temp_authority(scope="ci", env=inherited) as reopened:
        assert reopened.identity == authority.identity
        assert reopened.run_nonce == NONCE
        assert reopened.manifest_sha256 == MANIFEST
    with pytest.raises(TempAuthorityConfigurationError, match="nonce conflicts"):
        resolve_temp_authority(scope="ci", run_nonce="2" * 32, env=inherited)
    with pytest.raises(TempAuthorityConfigurationError, match="manifest conflicts"):
        resolve_temp_authority(
            scope="ci", manifest_sha256="b" * 64, env=inherited
        )
    for missing in (
        "HERMES_TEMP_ROOT_IDENTITY", "TMPDIR", "TEMP", "TMP",
        "HERMES_TEMP_AUTHORITY_VERSION", "HERMES_TEMP_SCOPE",
        "HERMES_TEMP_RUN_NONCE", "HERMES_TEMP_MANIFEST_SHA256",
    ):
        malformed = dict(inherited)
        malformed.pop(missing)
        with pytest.raises(TempAuthorityError, match="incomplete"):
            resolve_temp_authority(
                scope="ci", run_nonce=NONCE, manifest_sha256=MANIFEST, env=malformed,
            )
    with pytest.raises(TempAuthorityConfigurationError, match="partial"):
        resolve_temp_authority(
            scope="test", run_nonce=NONCE,
            env={"HERMES_HOME": str(tmp_path / "partial"), "TMPDIR": str(tmp_path)},
        )


def test_v1_strict_names_symlinked_home_and_replacement_cleanup(tmp_path: Path) -> None:
    token, authority = _authority(tmp_path / "profile")
    try:
        for purpose in ("Upper", "has_underscore", "a" * 33):
            with pytest.raises(TempAuthorityConfigurationError, match="purpose"):
                authority.mkdir(purpose)
        for suffix in ("../x", "/x", "\\x", "x" * 33):
            with pytest.raises(TempAuthorityConfigurationError, match="suffix"):
                authority.mkstemp("strict-name", suffix)
        with authority.temporary_directory("owned-context") as owned:
            assert owned.path.is_dir()
            assert owned.identity == (owned.path.stat().st_dev, owned.path.stat().st_ino)
        victim = authority.mkdir("replace-check")
        moved = victim.path.with_name(victim.path.name + "-moved")
        victim.path.rename(moved)
        victim.path.mkdir(mode=0o700)
        with pytest.raises(TempAuthorityCleanupError, match="replaced"):
            victim.cleanup()
    finally:
        authority.close()
        reset_hermes_home_override(token)


def test_v1_quarantine_preserves_interposed_file_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    token, authority = _authority(tmp_path / "profile")
    descriptor, victim = authority.mkstemp("file-race")
    os.write(descriptor, b"owned")
    os.close(descriptor)
    moved = victim.path.with_name(victim.path.name + "-original")
    real_rename = os.rename
    interposed = False

    def replace_then_rename(src, dst, *args, **kwargs):
        nonlocal interposed
        if not interposed and src == victim.path.name:
            interposed = True
            real_rename(
                src, moved.name,
                src_dir_fd=kwargs["src_dir_fd"],
                dst_dir_fd=kwargs["dst_dir_fd"],
            )
            replacement = os.open(
                src, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600,
                dir_fd=kwargs["src_dir_fd"],
            )
            os.write(replacement, b"replacement")
            os.close(replacement)
        return real_rename(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "rename", replace_then_rename)
    try:
        with pytest.raises(TempAuthorityCleanupError, match="changed before cleanup"):
            victim.cleanup()
        assert victim.path.read_bytes() == b"replacement"
        assert moved.read_bytes() == b"owned"
    finally:
        monkeypatch.undo()
        victim.path.unlink(missing_ok=True)
        moved.unlink(missing_ok=True)
        authority.close()
        reset_hermes_home_override(token)


def test_v1_quarantine_preserves_interposed_directory_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    token, authority = _authority(tmp_path / "profile")
    victim = authority.mkdir("directory-race")
    (victim.path / "owned.txt").write_text("owned", encoding="utf-8")
    moved = victim.path.with_name(victim.path.name + "-original")
    real_rename = os.rename
    interposed = False

    def replace_then_rename(src, dst, *args, **kwargs):
        nonlocal interposed
        if not interposed and src == victim.path.name:
            interposed = True
            real_rename(
                src, moved.name,
                src_dir_fd=kwargs["src_dir_fd"],
                dst_dir_fd=kwargs["dst_dir_fd"],
            )
            os.mkdir(src, mode=0o700, dir_fd=kwargs["src_dir_fd"])
            replacement = os.open(
                f"{src}/replacement.txt",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=kwargs["src_dir_fd"],
            )
            os.write(replacement, b"replacement")
            os.close(replacement)
        return real_rename(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "rename", replace_then_rename)
    try:
        with pytest.raises(TempAuthorityCleanupError, match="changed before cleanup"):
            victim.cleanup()
        assert (victim.path / "replacement.txt").read_text(encoding="utf-8") == "replacement"
        assert (moved / "owned.txt").read_text(encoding="utf-8") == "owned"
    finally:
        monkeypatch.undo()
        for directory in (victim.path, moved):
            for child in directory.iterdir():
                child.unlink()
            directory.rmdir()
        authority.close()
        reset_hermes_home_override(token)

    real = tmp_path / "real-home"
    real.mkdir(mode=0o700)
    linked = tmp_path / "linked-home"
    linked.symlink_to(real, target_is_directory=True)
    token = set_hermes_home_override(linked)
    try:
        with pytest.raises(TempAuthoritySecurityError, match="symlink"):
            resolve_temp_authority(scope="production", env={})
    finally:
        reset_hermes_home_override(token)
