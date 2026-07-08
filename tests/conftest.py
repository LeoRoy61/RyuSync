"""
tests/conftest.py — RyuSync v1.0

Fixtures pytest condivise per simulare filesystem Ryujinx senza installazione reale.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

# Aggiungi la root del progetto al path per importare i moduli
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Fixture: struttura Ryujinx simulata
# ---------------------------------------------------------------------------

@pytest.fixture
def ryujinx_dir(tmp_path: Path) -> Path:
    """
    Crea una struttura Ryujinx completa in una directory temporanea.

    Struttura:
    ryujinx/
    ├── bis/
    │   ├── user/
    │   │   └── save/
    │   │       └── 0000000000000001/
    │   │           └── game_save.dat
    │   └── system/
    │       └── account.dat
    ├── Config.json
    ├── mods/
    │   └── TitleID123/
    │       └── patch.ips
    └── shader_cache/
        └── shader.bin
    """
    ryu_dir = tmp_path / "ryujinx"

    # bis/user/save
    save_dir = ryu_dir / "bis" / "user" / "save" / "0000000000000001"
    save_dir.mkdir(parents=True)
    (save_dir / "game_save.dat").write_bytes(b"SAVE_DATA_V1_" + b"\x00" * 100)
    (save_dir / "game_save_2.dat").write_bytes(b"SAVE_DATA_V2_" + b"\x00" * 200)

    # bis/system
    system_dir = ryu_dir / "bis" / "system"
    system_dir.mkdir(parents=True)
    (system_dir / "account.dat").write_bytes(b"ACCOUNT_DATA" + b"\x00" * 50)

    # Config.json
    import json
    config_data = {
        "game_dirs": [str(tmp_path / "roms")],
        "enable_vsync": True,
        "graphicsBackend": "Vulkan",
    }
    (ryu_dir / "Config.json").write_text(json.dumps(config_data, indent=2))

    # mods
    mods_dir = ryu_dir / "mods" / "TitleID123"
    mods_dir.mkdir(parents=True)
    (mods_dir / "patch.ips").write_bytes(b"IPS_PATCH_DATA")

    # shader_cache
    shader_dir = ryu_dir / "shader_cache"
    shader_dir.mkdir()
    (shader_dir / "shader.bin").write_bytes(b"SHADER_BIN" + b"\x00" * 1000)

    return ryu_dir


@pytest.fixture
def ryujinx_portable_dir(tmp_path: Path) -> tuple[Path, Path]:
    """
    Simula un'installazione portable: Ryujinx.exe + cartella 'portable'.
    Restituisce (exe_path, portable_dir).
    """
    install_dir = tmp_path / "RyujinxPortable"
    install_dir.mkdir()

    # Exe simulato (file vuoto)
    exe = install_dir / "Ryujinx.exe"
    exe.write_bytes(b"MZ_FAKE_EXE")

    # Cartella portable
    portable_dir = install_dir / "portable"
    portable_dir.mkdir()

    # Struttura minima in portable
    (portable_dir / "bis").mkdir()
    (portable_dir / "Config.json").write_text('{"note": "portable mode"}')

    return exe, portable_dir


@pytest.fixture
def backup_dst(tmp_path: Path) -> Path:
    """Cartella di destinazione per i test di backup."""
    dst = tmp_path / "backup_dst"
    dst.mkdir()
    return dst


@pytest.fixture
def two_files_identical(tmp_path: Path) -> tuple[Path, Path]:
    """Due file con contenuto identico."""
    content = b"IDENTICAL_CONTENT_" + b"\xAA" * 100
    f1 = tmp_path / "file1.dat"
    f2 = tmp_path / "file2.dat"
    f1.write_bytes(content)
    f2.write_bytes(content)
    # Imposta stesso mtime
    mtime = time.time() - 100
    os.utime(f1, (mtime, mtime))
    os.utime(f2, (mtime, mtime))
    return f1, f2


@pytest.fixture
def two_files_different(tmp_path: Path) -> tuple[Path, Path]:
    """Due file con contenuto diverso ma stesso nome concettuale."""
    f1 = tmp_path / "save.dat"
    f2 = tmp_path / "save_remote.dat"
    f1.write_bytes(b"LOCAL_VERSION_ABC")
    f2.write_bytes(b"REMOTE_VERSION_XYZ")
    return f1, f2
