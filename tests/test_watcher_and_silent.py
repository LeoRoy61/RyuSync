"""
tests/test_watcher_and_silent.py — RyuSync v1.0
Unit tests covering:
- Watcher state file corruption and saving
- Silent mode execution & config loading error handling
- Sensitive data exposure in logs and state files
- Security warning notifications
"""

from __future__ import annotations

import json
import os
import sys
import logging
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

import security
import ryusync
import backup_engine
import detector

# Test state corruption & saving for Ryujinx Watcher
class TestRyujinxWatcherState:
    def test_watcher_load_state_missing(self, tmp_path: Path):
        state_file = tmp_path / "ryusync_state.json"
        
        def load_state() -> dict:
            if state_file.exists():
                try:
                    with open(state_file, "r") as f:
                        return json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass
            return {"ryujinx_was_running": False}

        assert load_state() == {"ryujinx_was_running": False}

    def test_watcher_load_state_corrupted(self, tmp_path: Path):
        state_file = tmp_path / "ryusync_state.json"
        state_file.write_text("{corrupt_json: ...")
        
        def load_state() -> dict:
            if state_file.exists():
                try:
                    with open(state_file, "r") as f:
                        return json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass
            return {"ryujinx_was_running": False}

        assert load_state() == {"ryujinx_was_running": False}

    def test_watcher_load_state_valid(self, tmp_path: Path):
        state_file = tmp_path / "ryusync_state.json"
        state_file.write_text(json.dumps({"ryujinx_was_running": True}))
        
        def load_state() -> dict:
            if state_file.exists():
                try:
                    with open(state_file, "r") as f:
                        return json.load(f)
                except (json.JSONDecodeError, OSError):
                    pass
            return {"ryujinx_was_running": False}

        assert load_state() == {"ryujinx_was_running": True}

    def test_watcher_save_state(self, tmp_path: Path):
        state_file = tmp_path / "ryusync_state.json"
        
        def save_state(state: dict) -> None:
            with open(state_file, "w") as f:
                json.dump(state, f, indent=2)

        save_state({"ryujinx_was_running": True})
        assert state_file.exists()
        with open(state_file, "r") as f:
            data = json.load(f)
        assert data["ryujinx_was_running"] is True


# Test sensitive data exposure
class TestSensitiveDataExposure:
    def test_check_sensitive_data_exposure_no_exposure(self, tmp_path: Path):
        base_dir = tmp_path
        
        state_file = base_dir / "ryusync_state.json"
        state_file.write_text(json.dumps({"ryujinx_was_running": False}))
        
        logs_dir = base_dir / "logs"
        logs_dir.mkdir()
        log_file = logs_dir / "backup_log_1.txt"
        log_file.write_text("RyuSync operation completed successfully. No sensitive data here.")
        
        with patch("pathlib.Path.home", return_value=Path("/tmp/cleanhome")), \
             patch.dict(os.environ, {"USERNAME": "cleanuser", "COMPUTERNAME": "cleanpc"}):
            warnings = security.check_sensitive_data_exposure(base_dir=base_dir)
            assert len(warnings) == 0

    def test_check_sensitive_data_exposure_detects_username(self, tmp_path: Path):
        base_dir = tmp_path
        logs_dir = base_dir / "logs"
        logs_dir.mkdir()
        log_file = logs_dir / "backup_log_1.txt"
        log_file.write_text("User folder is C:\\Users\\MySuperSecretUser\\AppData\\Roaming")
        
        with patch("pathlib.Path.home", return_value=Path("/tmp/cleanhome")), \
             patch.dict(os.environ, {"USERNAME": "MySuperSecretUser", "COMPUTERNAME": "cleanpc"}):
            warnings = security.check_sensitive_data_exposure(base_dir=base_dir)
            assert len(warnings) > 0
            assert any("MySuperSecretUser" in w or "informazioni sensibili" in w for w in warnings)

    def test_check_sensitive_data_exposure_detects_absolute_path(self, tmp_path: Path):
        base_dir = tmp_path
        logs_dir = base_dir / "logs"
        logs_dir.mkdir()
        log_file = logs_dir / "backup_log_1.txt"
        log_file.write_text("Failed to copy C:\\Users\\random_user\\Config.json")
        
        with patch("pathlib.Path.home", return_value=Path("/tmp/cleanhome")), \
             patch.dict(os.environ, {"USERNAME": "cleanuser", "COMPUTERNAME": "cleanpc"}):
            warnings = security.check_sensitive_data_exposure(base_dir=base_dir)
            assert len(warnings) > 0
            assert any("percorso assoluto del profilo utente" in w for w in warnings)


# Test security logging warnings
class TestSecurityWarningsLogging:
    def test_logs_warning_when_unencrypted_in_silent_mode(self, tmp_path: Path):
        conf = tmp_path / "rclone.conf"
        conf.write_text("[gdrive]\ntype=drive\ntoken=secret\n")
        
        with patch.object(security, "get_rclone_conf_path", return_value=conf):
            with patch("logging.Logger.warning") as mock_warn:
                security.warn_if_unencrypted(silent=True, base_dir=tmp_path)
                assert mock_warn.called
                args, _ = mock_warn.call_args
                assert "rclone.conf non cifrato" in args[0]


# Test Silent Mode configuration error handling
class TestSilentModeExecution:
    @patch("ryusync.logger")
    def test_silent_mode_exits_when_ryujinx_path_missing(self, mock_logger):
        config = {
            "ryujinx_path": "",
            "destination_path": "D:/Backup"
        }
        with pytest.raises(SystemExit) as exc_info:
            ryusync.run_incremental_silent(config)
        assert exc_info.value.code == 1
        mock_logger.error.assert_any_call("[SILENT] ryujinx_path non configurato in config.yaml")

    @patch("ryusync.logger")
    def test_silent_mode_exits_when_destination_path_missing(self, mock_logger, tmp_path: Path):
        config = {
            "ryujinx_path": str(tmp_path),
            "destination_path": ""
        }
        with patch("detector.validate_ryujinx_dir", return_value=True):
            with pytest.raises(SystemExit) as exc_info:
                ryusync.run_incremental_silent(config)
            assert exc_info.value.code == 1
            mock_logger.error.assert_any_call("[SILENT] destination_path non configurato in config.yaml")
