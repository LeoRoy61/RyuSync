"""
tests/test_security.py — RyuSync v1.0

Unit test per il modulo security.py.
Verifica il rilevamento della cifratura rclone.conf.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

import security


# ---------------------------------------------------------------------------
# Test: is_rclone_conf_encrypted
# ---------------------------------------------------------------------------

class TestIsRcloneConfEncrypted:
    """Test per il rilevamento della cifratura rclone.conf."""

    def test_encrypted_conf_detected(self, tmp_path: Path) -> None:
        """Un file che inizia con il marker rclone è riconosciuto come cifrato."""
        conf = tmp_path / "rclone.conf"
        conf.write_text(
            "# Encrypted rclone configuration File\n"
            "AQCAAAAAAAAAAAAAAAAA...(dati cifrati AES)...\n"
        )
        with patch.object(security, "get_rclone_conf_path", return_value=conf):
            assert security.is_rclone_conf_encrypted() is True

    def test_plaintext_conf_with_token(self, tmp_path: Path) -> None:
        """Un file con token OAuth in chiaro è riconosciuto come NON cifrato."""
        conf = tmp_path / "rclone.conf"
        conf.write_text(
            "[gdrive]\n"
            "type = drive\n"
            "token = {\"access_token\":\"ya29.XXXX\",\"token_type\":\"Bearer\"}\n"
        )
        with patch.object(security, "get_rclone_conf_path", return_value=conf):
            assert security.is_rclone_conf_encrypted() is False

    def test_plaintext_conf_with_section(self, tmp_path: Path) -> None:
        """Un file con sezioni rclone leggibili è riconosciuto come NON cifrato."""
        conf = tmp_path / "rclone.conf"
        conf.write_text("[onedrive]\ntype = onedrive\nclient_id = abc123\n")
        with patch.object(security, "get_rclone_conf_path", return_value=conf):
            assert security.is_rclone_conf_encrypted() is False

    def test_missing_conf_returns_none(self) -> None:
        """Se rclone.conf non esiste, restituisce None (non False)."""
        with patch.object(security, "get_rclone_conf_path", return_value=None):
            assert security.is_rclone_conf_encrypted() is None

    def test_empty_conf_returns_none(self, tmp_path: Path) -> None:
        """Un file vuoto restituisce None (stato sconosciuto)."""
        conf = tmp_path / "rclone.conf"
        conf.write_text("")
        with patch.object(security, "get_rclone_conf_path", return_value=conf):
            result = security.is_rclone_conf_encrypted()
            assert result is None


# ---------------------------------------------------------------------------
# Test: check_rclone_security
# ---------------------------------------------------------------------------

class TestCheckRcloneSecurity:
    """Test per check_rclone_security() e risk_level."""

    def test_risk_ok_when_encrypted(self, tmp_path: Path) -> None:
        """Conf cifrato → risk_level 'ok'."""
        conf = tmp_path / "rclone.conf"
        conf.write_text("# Encrypted rclone configuration File\nDATA\n")
        with patch.object(security, "get_rclone_conf_path", return_value=conf):
            result = security.check_rclone_security()
        assert result["risk_level"] == "ok"
        assert result["found"] is True
        assert result["encrypted"] is True

    def test_risk_critical_when_plaintext(self, tmp_path: Path) -> None:
        """Conf in chiaro → risk_level 'critical'."""
        conf = tmp_path / "rclone.conf"
        conf.write_text("[gdrive]\ntype = drive\ntoken = secret\n")
        with patch.object(security, "get_rclone_conf_path", return_value=conf):
            result = security.check_rclone_security()
        assert result["risk_level"] == "critical"
        assert result["encrypted"] is False

    def test_risk_unknown_when_not_found(self) -> None:
        """Conf non trovato → risk_level 'unknown', found=False."""
        with patch.object(security, "get_rclone_conf_path", return_value=None):
            result = security.check_rclone_security()
        assert result["risk_level"] == "unknown"
        assert result["found"] is False
        assert result["path"] is None

    def test_warn_if_unencrypted_returns_false(self, tmp_path: Path) -> None:
        """warn_if_unencrypted() ritorna False quando il conf è in chiaro."""
        conf = tmp_path / "rclone.conf"
        conf.write_text("[mega]\ntype = mega\nuser = test@test.com\npass = hashed\n")
        with patch.object(security, "get_rclone_conf_path", return_value=conf):
            assert security.warn_if_unencrypted(silent=True) is False

    def test_warn_if_unencrypted_returns_true_when_encrypted(self, tmp_path: Path) -> None:
        """warn_if_unencrypted() ritorna True quando il conf è cifrato."""
        conf = tmp_path / "rclone.conf"
        conf.write_text("# Encrypted rclone configuration File\nDATA\n")
        with patch.object(security, "get_rclone_conf_path", return_value=conf):
            assert security.warn_if_unencrypted(silent=True) is True

    def test_warn_if_unencrypted_returns_true_when_not_found(self) -> None:
        """warn_if_unencrypted() ritorna True quando non c'è conf (nessun rischio)."""
        with patch.object(security, "get_rclone_conf_path", return_value=None):
            assert security.warn_if_unencrypted(silent=True) is True
