"""
tests/test_detector.py — RyuSync v1.0

Unit test per il modulo detector.py.
Simula il filesystem Windows senza richiedere un'installazione reale di Ryujinx.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Importa il modulo sotto test
import detector


# ---------------------------------------------------------------------------
# Test: validate_ryujinx_dir
# ---------------------------------------------------------------------------

class TestValidateRyujinxDir:
    """Test per la funzione validate_ryujinx_dir."""

    def test_valid_dir_with_bis(self, ryujinx_dir: Path) -> None:
        """Una cartella con bis/ è valida."""
        assert detector.validate_ryujinx_dir(ryujinx_dir) is True

    def test_valid_dir_with_config_only(self, tmp_path: Path) -> None:
        """Una cartella con solo Config.json (nuova installazione) è valida."""
        ryu = tmp_path / "ryujinx_new"
        ryu.mkdir()
        (ryu / "Config.json").write_text('{"version": "1.0"}')
        assert detector.validate_ryujinx_dir(ryu) is True

    def test_invalid_dir_empty(self, tmp_path: Path) -> None:
        """Una cartella vuota non è valida."""
        empty = tmp_path / "empty_dir"
        empty.mkdir()
        assert detector.validate_ryujinx_dir(empty) is False

    def test_invalid_dir_random_files(self, tmp_path: Path) -> None:
        """Una cartella con file casuali non è valida."""
        rnd = tmp_path / "random"
        rnd.mkdir()
        (rnd / "readme.txt").write_text("not ryujinx")
        (rnd / "game.exe").write_bytes(b"MZ")
        assert detector.validate_ryujinx_dir(rnd) is False

    def test_invalid_path_nonexistent(self, tmp_path: Path) -> None:
        """Un path inesistente non è valido."""
        assert detector.validate_ryujinx_dir(tmp_path / "does_not_exist") is False

    def test_invalid_path_is_file(self, tmp_path: Path) -> None:
        """Un file (non cartella) non è valido."""
        f = tmp_path / "file.txt"
        f.write_text("test")
        assert detector.validate_ryujinx_dir(f) is False

    def test_invalid_none_path(self) -> None:
        """None come path non è valido."""
        assert detector.validate_ryujinx_dir(None) is False  # type: ignore


# ---------------------------------------------------------------------------
# Test: detect_ryujinx_path — OS non supportati
# ---------------------------------------------------------------------------

class TestDetectOsName:
    """Test per la gestione del parametro os_name."""

    def test_linux_raises(self) -> None:
        """Linux non è supportato in v1.0."""
        with pytest.raises(ValueError, match="Linux"):
            detector.detect_ryujinx_path("linux")

    def test_darwin_raises(self) -> None:
        """macOS non è supportato in v1.0."""
        with pytest.raises(ValueError, match="macOS"):
            detector.detect_ryujinx_path("darwin")

    def test_unknown_os_raises(self) -> None:
        """Un OS sconosciuto deve sollevare ValueError."""
        with pytest.raises(ValueError, match="non supportato"):
            detector.detect_ryujinx_path("freebsd")


# ---------------------------------------------------------------------------
# Test: rilevamento Windows — modalità AppData
# ---------------------------------------------------------------------------

class TestDetectWindowsAppData:
    """Test per il rilevamento nella modalità AppData (default)."""

    def test_detects_appdata_ryujinx(self, ryujinx_dir: Path, monkeypatch) -> None:
        """
        Simula %APPDATA%\\Ryujinx esistente e valido.
        """
        # Crea una cartella Ryujinx in una temp dir che finge di essere AppData
        fake_appdata = ryujinx_dir.parent
        fake_ryujinx = fake_appdata / "Ryujinx"

        # ryujinx_dir è già fake_appdata/ryujinx ma rinominiamo per il test
        # Usa la fixture ryujinx_dir direttamente come fake AppData\Ryujinx
        monkeypatch.setenv("APPDATA", str(ryujinx_dir.parent))

        # Simula che "Ryujinx" esista in APPDATA
        (ryujinx_dir.parent / "Ryujinx").mkdir(exist_ok=True)
        (ryujinx_dir.parent / "Ryujinx" / "bis").mkdir(exist_ok=True)
        (ryujinx_dir.parent / "Ryujinx" / "Config.json").write_text("{}")

        # Mock _find_portable_mode_windows per non cercare in registro/PATH
        with patch.object(detector, "_find_portable_mode_windows", return_value=[]):
            results = detector.detect_ryujinx_path("windows")

        assert len(results) >= 1
        assert any("Ryujinx" in str(p) for p in results)

    def test_no_appdata_env(self, monkeypatch) -> None:
        """Senza APPDATA, il rilevamento AppData restituisce None senza crash."""
        monkeypatch.delenv("APPDATA", raising=False)
        result = detector._get_appdata_ryujinx_path()
        assert result is None

    def test_appdata_ryujinx_not_exists(self, monkeypatch, tmp_path) -> None:
        """APPDATA esiste ma Ryujinx non è installato → path non trovato."""
        monkeypatch.setenv("APPDATA", str(tmp_path))
        result = detector._get_appdata_ryujinx_path()
        assert result is None

    def test_appdata_ryujinx_exists_but_empty(self, monkeypatch, tmp_path) -> None:
        """Ryujinx in AppData esiste ma è vuoto → non valido."""
        appdata = tmp_path / "AppData"
        appdata.mkdir()
        ryu = appdata / "Ryujinx"
        ryu.mkdir()
        monkeypatch.setenv("APPDATA", str(appdata))

        with patch.object(detector, "_find_portable_mode_windows", return_value=[]):
            results = detector.detect_ryujinx_path("windows")

        # Cartella vuota non passa validate_ryujinx_dir → non inclusa
        assert len(results) == 0


# ---------------------------------------------------------------------------
# Test: rilevamento Windows — modalità portable
# ---------------------------------------------------------------------------

class TestDetectWindowsPortable:
    """Test per il rilevamento in modalità portable."""

    def test_detects_portable_dir(self, ryujinx_portable_dir, monkeypatch) -> None:
        """
        Simula Ryujinx.exe con cartella portable adiacente.
        """
        exe, portable_dir = ryujinx_portable_dir

        # Simula PATH che include la directory dell'exe
        monkeypatch.setenv("PATH", str(exe.parent))
        monkeypatch.delenv("APPDATA", raising=False)

        # Mock registro Windows per non cercare lì
        with patch("winreg.OpenKey", side_effect=FileNotFoundError):
            results = detector._find_portable_mode_windows()

        assert portable_dir in results

    def test_exe_without_portable_dir(self, tmp_path, monkeypatch) -> None:
        """Un exe senza cartella 'portable' adiacente non viene incluso."""
        install_dir = tmp_path / "RyujinxNonPortable"
        install_dir.mkdir()
        exe = install_dir / "Ryujinx.exe"
        exe.write_bytes(b"MZ_FAKE")
        # NON creare la cartella 'portable'

        monkeypatch.setenv("PATH", str(install_dir))
        monkeypatch.delenv("APPDATA", raising=False)

        with patch("winreg.OpenKey", side_effect=FileNotFoundError):
            results = detector._find_portable_mode_windows()

        assert not any(p == install_dir / "portable" for p in results)


# ---------------------------------------------------------------------------
# Test: get_ryujinx_structure
# ---------------------------------------------------------------------------

class TestGetRyujinxStructure:
    """Test per l'analisi della struttura Ryujinx."""

    def test_full_structure_detected(self, ryujinx_dir: Path) -> None:
        """Verifica che tutti i componenti vengano rilevati correttamente."""
        structure = detector.get_ryujinx_structure(ryujinx_dir)

        assert structure["saves"] is not None
        assert structure["system"] is not None
        assert structure["config"] is not None
        assert structure["mods"] is not None
        assert structure["shader_cache"] is not None

    def test_missing_components_are_none(self, tmp_path: Path) -> None:
        """Componenti mancanti restituiscono None senza crash."""
        # Crea solo il minimo indispensabile
        ryu = tmp_path / "minimal"
        ryu.mkdir()
        (ryu / "Config.json").write_text("{}")

        structure = detector.get_ryujinx_structure(ryu)

        assert structure["saves"] is None
        assert structure["mods"] is None
        assert structure["system"] is None

    def test_config_json_found(self, ryujinx_dir: Path) -> None:
        """Config.json viene rilevato correttamente."""
        structure = detector.get_ryujinx_structure(ryujinx_dir)
        assert structure["config"] == ryujinx_dir / "Config.json"

    def test_mods_path_detected(self, ryujinx_dir: Path) -> None:
        """La cartella mods/ viene rilevata."""
        structure = detector.get_ryujinx_structure(ryujinx_dir)
        assert structure["mods"] == ryujinx_dir / "mods"
