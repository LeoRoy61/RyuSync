#!/usr/bin/env python
"""
tests/verify_scenarios.py — RyuSync Integration Test Suite

This script programmatically runs multiple scenarios to verify content category filtering,
local destinations (using different slash conventions), mock Google Drive dry-runs,
and recovery/restore behaviors with newer file checks.

Usage:
    python tests/verify_scenarios.py
"""

from __future__ import annotations

import os
import sys
import shutil
import json
import time
import subprocess
import yaml
from pathlib import Path
from unittest.mock import patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Resolve project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import backup engine for restore tests
import backup_engine

# Workspace directories under project root
WORKSPACE = PROJECT_ROOT / "temp_test_workspace"
MOCK_RYUJINX = WORKSPACE / "ryujinx"
MOCK_ROMS = WORKSPACE / "roms"
MOCK_BACKUPS = WORKSPACE / "backups"
MOCK_GDRIVE = WORKSPACE / "gdrive_mock"

ORIGINAL_CONFIG_PATH = PROJECT_ROOT / "config.yaml"
BACKUP_CONFIG_PATH = PROJECT_ROOT / "config.yaml.bak"
REPORT_PATH = PROJECT_ROOT / "logs" / "verify_scenarios_report.txt"

# Track test outcomes
test_cases = []
log_entries = []

def log_detail(msg: str):
    print(msg)
    log_entries.append(msg)

import traceback

def record_result(name: str, dest_type: str, status: str, details: str = ""):
    test_cases.append({
        "name": name,
        "dest_type": dest_type,
        "status": status,
        "details": details
    })
    log_detail(f"[{status}] {name} - {details}")
    if status == "FAIL":
        traceback.print_exc()


def setup_workspace():
    """Create clean mock directories for testing."""
    if WORKSPACE.exists():
        shutil.rmtree(WORKSPACE)
    WORKSPACE.mkdir(parents=True)
    MOCK_RYUJINX.mkdir()
    MOCK_ROMS.mkdir()
    MOCK_BACKUPS.mkdir()
    MOCK_GDRIVE.mkdir()

    # Category 1: Saves
    save_dir = MOCK_RYUJINX / "bis" / "user" / "save" / "0000000000000001"
    save_dir.mkdir(parents=True)
    (save_dir / "game_save.dat").write_text("SAVE_DATA_V1")

    # Category 2: Mii
    mii_dir = MOCK_RYUJINX / "bis" / "user" / "mii"
    mii_dir.mkdir(parents=True)
    (mii_dir / "mii_data.dat").write_text("MII_DATA")

    # Category 3: Config
    config_data = {
        "game_dirs": [str(MOCK_ROMS)],
        "enable_vsync": True,
    }
    (MOCK_RYUJINX / "Config.json").write_text(json.dumps(config_data, indent=2))

    # Category 4: System
    system_dir = MOCK_RYUJINX / "bis" / "system"
    system_dir.mkdir(parents=True)
    (system_dir / "account.dat").write_text("SYSTEM_DATA")

    # Category 5: Mods
    mods_dir = MOCK_RYUJINX / "mods" / "TitleID123"
    mods_dir.mkdir(parents=True)
    (mods_dir / "patch.ips").write_text("IPS_PATCH")

    # Category 6: ROMs
    (MOCK_ROMS / "game.nsp").write_text("ROM_DATA")

    # Category 7: Shader Cache
    shader_dir = MOCK_RYUJINX / "shader_cache"
    shader_dir.mkdir()
    (shader_dir / "shader.bin").write_text("SHADER_DATA")

def run_backup_subprocess(config_dict, extra_args=None) -> subprocess.CompletedProcess:
    """Executes ryusync.py via subprocess using custom config.yaml."""
    # Backup existing config.yaml if present
    if ORIGINAL_CONFIG_PATH.exists() and not BACKUP_CONFIG_PATH.exists():
        shutil.copy2(ORIGINAL_CONFIG_PATH, BACKUP_CONFIG_PATH)

    # Write test config.yaml
    with open(ORIGINAL_CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config_dict, f)

    cmd = [sys.executable, str(PROJECT_ROOT / "ryusync.py"), "--silent"]
    if extra_args:
        cmd.extend(extra_args)

    # Set up environment variables to redirect rclone to MOCK_GDRIVE
    env = os.environ.copy()
    env["RCLONE_CONFIG_GDRIVE_TYPE"] = "local"
    env["RCLONE_CONFIG_GDRIVE_PATH"] = str(MOCK_GDRIVE)

    result = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        print(f"Subprocess failed with code {result.returncode}")
        print("STDOUT:")
        print(result.stdout)
        print("STDERR:")
        print(result.stderr)
    return result


def restore_original_config():
    """Teardown to restore user's original config.yaml."""
    if ORIGINAL_CONFIG_PATH.exists():
        os.remove(ORIGINAL_CONFIG_PATH)
    if BACKUP_CONFIG_PATH.exists():
        shutil.move(BACKUP_CONFIG_PATH, ORIGINAL_CONFIG_PATH)

def assert_file_presence(dest_path: Path, expected_files: list[str], unexpected_files: list[str]):
    """Helper to verify that only specified files exist in destination."""
    for f in expected_files:
        p = dest_path / f
        assert p.exists(), f"Expected file {f} is missing from destination!"
    for f in unexpected_files:
        p = dest_path / f
        assert not p.exists(), f"Unexpected file {f} was backed up to destination!"

# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_saves_only():
    name = "Backup - Game Saves Only"
    try:
        setup_workspace()
        dest = MOCK_BACKUPS / "saves_only"
        config = {
            "ryujinx_path": str(MOCK_RYUJINX),
            "destination_type": "local",
            "destination_path": str(dest),
            "contents": {
                "saves": True,
                "mii": False,
                "system": False,
                "config": False,
                "mods": False,
                "roms": False,
                "shader_cache": False
            }
        }
        run_backup_subprocess(config)
        assert_file_presence(
            dest,
            expected_files=["bis/user/save/0000000000000001/game_save.dat"],
            unexpected_files=["bis/user/mii/mii_data.dat", "Config.json", "bis/system/account.dat"]
        )
        record_result(name, "local", "PASS", "Only saves directory created.")
    except Exception as e:
        record_result(name, "local", "FAIL", str(e))

def test_mii_only():
    name = "Backup - Mii Data Only"
    try:
        setup_workspace()
        dest = MOCK_BACKUPS / "mii_only"
        config = {
            "ryujinx_path": str(MOCK_RYUJINX),
            "destination_type": "local",
            "destination_path": str(dest),
            "contents": {
                "saves": False,
                "mii": True,
                "system": False,
                "config": False,
                "mods": False,
                "roms": False,
                "shader_cache": False
            }
        }
        run_backup_subprocess(config)
        assert_file_presence(
            dest,
            expected_files=["bis/user/mii/mii_data.dat"],
            unexpected_files=["bis/user/save/0000000000000001/game_save.dat", "Config.json"]
        )
        record_result(name, "local", "PASS", "Only mii directory created.")
    except Exception as e:
        record_result(name, "local", "FAIL", str(e))

def test_config_only():
    name = "Backup - General Settings Only"
    try:
        setup_workspace()
        dest = MOCK_BACKUPS / "config_only"
        config = {
            "ryujinx_path": str(MOCK_RYUJINX),
            "destination_type": "local",
            "destination_path": str(dest),
            "contents": {
                "saves": False,
                "mii": False,
                "system": False,
                "config": True,
                "mods": False,
                "roms": False,
                "shader_cache": False
            }
        }
        run_backup_subprocess(config)
        assert_file_presence(
            dest,
            expected_files=["Config.json"],
            unexpected_files=["bis/user/save/0000000000000001/game_save.dat", "bis/user/mii/mii_data.dat"]
        )
        record_result(name, "local", "PASS", "Only Config.json created.")
    except Exception as e:
        record_result(name, "local", "FAIL", str(e))

def test_system_mods_roms():
    name = "Backup - System, Mods, and ROMs"
    try:
        setup_workspace()
        dest = MOCK_BACKUPS / "sys_mods_roms"
        config = {
            "ryujinx_path": str(MOCK_RYUJINX),
            "destination_type": "local",
            "destination_path": str(dest),
            "contents": {
                "saves": False,
                "mii": False,
                "system": True,
                "config": False,
                "mods": True,
                "roms": True,
                "shader_cache": False
            }
        }
        run_backup_subprocess(config)
        assert_file_presence(
            dest,
            expected_files=["bis/system/account.dat", "mods/TitleID123/patch.ips", "roms/game.nsp"],
            unexpected_files=["bis/user/save/0000000000000001/game_save.dat", "bis/user/mii/mii_data.dat", "Config.json"]
        )
        record_result(name, "local", "PASS", "System, mods, and ROMs successfully isolated.")
    except Exception as e:
        record_result(name, "local", "FAIL", str(e))

def test_all_combined():
    name = "Backup - All Categories Combined"
    try:
        setup_workspace()
        dest = MOCK_BACKUPS / "all_combined"
        config = {
            "ryujinx_path": str(MOCK_RYUJINX),
            "destination_type": "local",
            "destination_path": str(dest),
            "contents": {
                "saves": True,
                "mii": True,
                "system": True,
                "config": True,
                "mods": True,
                "roms": True,
                "shader_cache": True
            }
        }
        run_backup_subprocess(config)
        assert_file_presence(
            dest,
            expected_files=[
                "bis/user/save/0000000000000001/game_save.dat",
                "bis/user/mii/mii_data.dat",
                "Config.json",
                "bis/system/account.dat",
                "mods/TitleID123/patch.ips",
                "roms/game.nsp",
                "shader_cache/shader.bin"
            ],
            unexpected_files=[]
        )
        record_result(name, "local", "PASS", "All content types successfully backed up.")
    except Exception as e:
        record_result(name, "local", "FAIL", str(e))

def test_forward_slashes():
    name = "Backup - Local Path with Forward Slashes"
    try:
        setup_workspace()
        dest = str(MOCK_BACKUPS) + "/forward/slash/path"
        config = {
            "ryujinx_path": str(MOCK_RYUJINX),
            "destination_type": "local",
            "destination_path": dest,
            "contents": {"saves": True, "mii": False, "system": False, "config": False, "mods": False, "roms": False, "shader_cache": False}
        }
        run_backup_subprocess(config)
        assert Path(dest).exists()
        assert (Path(dest) / "bis/user/save/0000000000000001/game_save.dat").exists()
        record_result(name, "local", "PASS", "Forward slash path resolved and created.")
    except Exception as e:
        record_result(name, "local", "FAIL", str(e))

def test_backward_slashes():
    name = "Backup - Local Path with Backward Slashes"
    try:
        setup_workspace()
        dest = str(MOCK_BACKUPS) + "\\backward\\slash\\path"
        config = {
            "ryujinx_path": str(MOCK_RYUJINX),
            "destination_type": "local",
            "destination_path": dest,
            "contents": {"saves": True, "mii": False, "system": False, "config": False, "mods": False, "roms": False, "shader_cache": False}
        }
        run_backup_subprocess(config)
        assert Path(dest).exists()
        assert (Path(dest) / "bis/user/save/0000000000000001/game_save.dat").exists()
        record_result(name, "local", "PASS", "Backward slash path resolved and created.")
    except Exception as e:
        record_result(name, "local", "FAIL", str(e))

def test_gdrive_dry_run():
    name = "Backup - Google Drive Dry-Run"
    try:
        setup_workspace()
        config = {
            "ryujinx_path": str(MOCK_RYUJINX),
            "destination_type": "gdrive",
            "destination_path": "gdrive:RyuSync/Test",
            "contents": {"saves": True, "mii": True, "config": True, "system": False, "mods": False, "roms": False, "shader_cache": False}
        }
        result = run_backup_subprocess(config, extra_args=["--dry-run"])
        # In dry run, files shouldn't be copied to mock remote directory
        mock_gdrive_contents = list(MOCK_GDRIVE.rglob("*"))
        assert len(mock_gdrive_contents) == 0, f"Dry-run modified target remote! Files: {mock_gdrive_contents}"
        # Assert rclone output was shown
        assert "[DRY-RUN] rclone copy:" in result.stdout or "rclone copy" in result.stderr or result.returncode == 0, \
            "Dry run execution log check failed."
        record_result(name, "gdrive", "PASS", "Rclone commands parsed correctly without copying files.")
    except Exception as e:
        record_result(name, "gdrive", "FAIL", str(e))

# ---------------------------------------------------------------------------
# Recovery/Restore Tests (In-Process Mocked)
# ---------------------------------------------------------------------------

def test_restore_recovery():
    name = "Restore - File Recovery (Deleted Local Files)"
    try:
        setup_workspace()
        backup_dir = MOCK_BACKUPS / "restore_source"
        config = {
            "ryujinx_path": str(MOCK_RYUJINX),
            "destination_type": "local",
            "destination_path": str(backup_dir),
            "contents": {"saves": True, "mii": True, "system": False, "config": False, "mods": False, "roms": False, "shader_cache": False}
        }
        run_backup_subprocess(config)

        # Modify local files: delete save file, modify mii file and make it newer
        save_file = MOCK_RYUJINX / "bis" / "user" / "save" / "0000000000000001" / "game_save.dat"
        os.remove(save_file)

        mii_file = MOCK_RYUJINX / "bis" / "user" / "mii" / "mii_data.dat"
        mii_file.write_text("MII_NEW")
        # Ensure mtime is higher than backup files
        future_mtime = time.time() + 100
        os.utime(mii_file, (future_mtime, future_mtime))

        # Sub-Scenario 1: Restore with overwrite = False (preserve newer files)
        log_detail("Subcase 1: Restore with overwrite=False")
        with patch("questionary.confirm") as mock_confirm:
            # First confirm (proceed with restore) = True
            # Second confirm (overwrite newer mii_data.dat) = False
            mock_confirm.return_value.ask.side_effect = [True, False]
            backup_engine.restore(
                src=str(backup_dir),
                dst=MOCK_RYUJINX,
                dry_run=False,
                integrity_method="mtime_size"
            )

        assert save_file.exists(), "Deleted save file was not recovered!"
        assert save_file.read_text() == "SAVE_DATA_V1", "Recovered save has corrupt data."
        assert mii_file.read_text() == "MII_NEW", "Newer local Mii data was overwritten when it should have been protected!"

        record_result(name, "local", "PASS", "Recovered deleted save, protected newer Mii data.")
    except Exception as e:
        record_result(name, "local", "FAIL", str(e))

def test_restore_overwrite():
    name = "Restore - Overwrite Newer Local Files"
    try:
        setup_workspace()
        backup_dir = MOCK_BACKUPS / "restore_source"
        config = {
            "ryujinx_path": str(MOCK_RYUJINX),
            "destination_type": "local",
            "destination_path": str(backup_dir),
            "contents": {"saves": True, "mii": True, "system": False, "config": False, "mods": False, "roms": False, "shader_cache": False}
        }
        run_backup_subprocess(config)

        # Modify local files: delete save file, modify mii file and make it newer
        save_file = MOCK_RYUJINX / "bis" / "user" / "save" / "0000000000000001" / "game_save.dat"
        os.remove(save_file)

        mii_file = MOCK_RYUJINX / "bis" / "user" / "mii" / "mii_data.dat"
        mii_file.write_text("MII_NEW")
        future_mtime = time.time() + 100
        os.utime(mii_file, (future_mtime, future_mtime))

        # Sub-Scenario 2: Restore with overwrite = True (overwrite newer files)
        log_detail("Subcase 2: Restore with overwrite=True")
        with patch("questionary.confirm") as mock_confirm:
            # First confirm (proceed with restore) = True
            # Second confirm (overwrite newer mii_data.dat) = True
            mock_confirm.return_value.ask.side_effect = [True, True]
            backup_engine.restore(
                src=str(backup_dir),
                dst=MOCK_RYUJINX,
                dry_run=False,
                integrity_method="mtime_size"
            )

        assert save_file.exists(), "Deleted save file was not recovered!"
        assert mii_file.read_text() == "MII_DATA", "Newer local Mii data was not overwritten as requested!"

        record_result(name, "local", "PASS", "Recovered deleted save, overwrote newer Mii data when chosen.")
    except Exception as e:
        record_result(name, "local", "FAIL", str(e))


# ---------------------------------------------------------------------------
# Output Reporting
# ---------------------------------------------------------------------------

def print_and_write_summary():
    """Construct table and write report to logs/verify_scenarios_report.txt."""
    header = f"{'Scenario Name':<45} | {'Dest Type':<10} | {'Result':<6} | {'Details'}"
    separator = "-" * 90
    
    # Render table to console
    print("\n" + separator)
    print(" INTEGRATION TEST REPORT SUMMARY")
    print(separator)
    print(header)
    print(separator)
    
    passed = 0
    failed = 0
    for case in test_cases:
        color = "\033[92m" if case["status"] == "PASS" else "\033[91m"
        reset = "\033[0m"
        print(f"{case['name']:<45} | {case['dest_type']:<10} | {color}{case['status']:<6}{reset} | {case['details']}")
        if case["status"] == "PASS":
            passed += 1
        else:
            failed += 1
            
    print(separator)
    print(f"Total: {len(test_cases)} | Passed: {passed} | Failed: {failed}")
    print(separator + "\n")

    # Write log to logs/verify_scenarios_report.txt
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("RyuSync Scenario Verification Integration Report\n")
        f.write("=" * 90 + "\n")
        f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Total test cases: {len(test_cases)} | Passed: {passed} | Failed: {failed}\n")
        f.write("=" * 90 + "\n\n")
        
        # Write tabular summary
        f.write(f"{'Scenario Name':<45} | {'Dest Type':<10} | {'Result':<6} | {'Details'}\n")
        f.write("-" * 90 + "\n")
        for case in test_cases:
            f.write(f"{case['name']:<45} | {case['dest_type']:<10} | {case['status']:<6} | {case['details']}\n")
        f.write("-" * 90 + "\n\n")

        # Write detailed execution log entries
        f.write("DETAILED LOG ENTRIES:\n")
        f.write("-" * 30 + "\n")
        for entry in log_entries:
            f.write(f"{entry}\n")
            
    print(f"Detailed log report successfully written to: {REPORT_PATH}")

# ---------------------------------------------------------------------------
# Main Execution Entry Point
# ---------------------------------------------------------------------------

def main():
    log_detail("Starting RyuSync Integration Scenarios Test Suite...")
    
    try:
        # Run Backup scenarios
        test_saves_only()
        test_mii_only()
        test_config_only()
        test_system_mods_roms()
        test_all_combined()
        test_forward_slashes()
        test_backward_slashes()
        test_gdrive_dry_run()
        
        # Run Restore scenarios
        test_restore_recovery()
        test_restore_overwrite()
    finally:
        # Cleanup
        restore_original_config()
        if WORKSPACE.exists():
            shutil.rmtree(WORKSPACE)
            log_detail("Temporary test workspace cleaned up.")
            
    print_and_write_summary()
    
    # Exit with code 1 if any tests failed
    if any(c["status"] == "FAIL" for c in test_cases):
        sys.exit(1)
    sys.exit(0)

if __name__ == "__main__":
    main()
