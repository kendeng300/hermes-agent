import pytest
from unittest.mock import patch

from hermes_temp import TempAuthorityConfigurationError, current_temp_authority

from tools.environments.local import LocalEnvironment


class TestLocalTempDir:
    def test_rejects_ambient_tmpdir_without_exact_binding(self, monkeypatch):
        monkeypatch.setenv("TMPDIR", "/data/data/com.termux/files/usr/tmp")
        monkeypatch.delenv("TMP", raising=False)
        monkeypatch.delenv("TEMP", raising=False)

        with patch.object(LocalEnvironment, "init_session", autospec=True, return_value=None), \
             pytest.raises(TempAuthorityConfigurationError):
            LocalEnvironment(cwd=".", timeout=10)

    def test_rejects_partial_backend_tmpdir_override(self, monkeypatch):
        monkeypatch.delenv("TMPDIR", raising=False)
        monkeypatch.delenv("TMP", raising=False)
        monkeypatch.delenv("TEMP", raising=False)

        with patch.object(LocalEnvironment, "init_session", autospec=True, return_value=None), \
             pytest.raises(TempAuthorityConfigurationError):
            LocalEnvironment(
                cwd=".",
                timeout=10,
                env={"TMPDIR": "/data/data/com.termux/files/home/.cache/hermes-tmp/"},
            )

    def test_uses_complete_bound_authority(self):
        with current_temp_authority() as authority, \
             patch.object(LocalEnvironment, "init_session", autospec=True, return_value=None):
            env = LocalEnvironment(cwd=".", timeout=10)
            expected = str(authority.root)
            assert env.get_temp_dir() == expected
            assert env._snapshot_path == f"{expected}/hermes-snap-{env._session_id}.sh"
            assert env._cwd_file == f"{expected}/hermes-cwd-{env._session_id}.txt"
