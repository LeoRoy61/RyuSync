"""
tests/test_backup_engine.py — RyuSync v1.0

Unit test per il modulo backup_engine.py.
Verifica il principio fondamentale: SOLO aggiunta, MAI cancellazione/sovrascrittura.
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import backup_engine
from backup_engine import FileStatus, compare_files, BackupResult


# ---------------------------------------------------------------------------
# Test: compare_files — metodo mtime_size
# ---------------------------------------------------------------------------

class TestCompareFilesMtimeSize:
    """Test per la comparazione file con metodo mtime_size."""

    def test_identical_same_size_and_mtime(self, tmp_path: Path) -> None:
        """File con dimensione e mtime identici → IDENTICAL."""
        f = tmp_path / "file.dat"
        f.write_bytes(b"DATA" * 100)
        stat = f.stat()
        remote = {"size": stat.st_size, "mtime": stat.st_mtime}

        result = compare_files(f, remote, method="mtime_size")
        assert result == FileStatus.IDENTICAL

    def test_missing_remote_empty_dict(self, tmp_path: Path) -> None:
        """Remote meta dict vuoto → MISSING_REMOTE."""
        f = tmp_path / "file.dat"
        f.write_bytes(b"DATA")

        result = compare_files(f, {}, method="mtime_size")
        assert result == FileStatus.MISSING_REMOTE

    def test_missing_remote_none(self, tmp_path: Path) -> None:
        """None come remote meta → MISSING_REMOTE."""
        f = tmp_path / "file.dat"
        f.write_bytes(b"DATA")

        result = compare_files(f, None, method="mtime_size")  # type: ignore
        assert result == FileStatus.MISSING_REMOTE

    def test_newer_local(self, tmp_path: Path) -> None:
        """File locale più recente (mtime) → NEWER_LOCAL."""
        f = tmp_path / "file.dat"
        f.write_bytes(b"LOCAL_DATA" * 10)

        now = time.time()
        os.utime(f, (now, now))

        remote = {"size": f.stat().st_size, "mtime": now - 100}  # remoto molto più vecchio

        result = compare_files(f, remote, method="mtime_size")
        assert result == FileStatus.NEWER_LOCAL

    def test_newer_remote(self, tmp_path: Path) -> None:
        """File remoto più recente (mtime) → NEWER_REMOTE."""
        f = tmp_path / "file.dat"
        f.write_bytes(b"LOCAL_DATA")

        now = time.time()
        old_mtime = now - 200
        os.utime(f, (old_mtime, old_mtime))

        remote = {"size": f.stat().st_size, "mtime": now}  # remoto molto più recente

        result = compare_files(f, remote, method="mtime_size")
        assert result == FileStatus.NEWER_REMOTE

    def test_conflict_different_size_similar_mtime(self, tmp_path: Path) -> None:
        """Size diversi con mtime quasi identici → CONFLICT."""
        f = tmp_path / "file.dat"
        f.write_bytes(b"LOCAL" * 100)

        now = time.time()
        os.utime(f, (now, now))

        remote = {"size": 100, "mtime": now}  # size diverso, mtime simile

        result = compare_files(f, remote, method="mtime_size")
        assert result == FileStatus.CONFLICT

    def test_mtime_tolerance_within_2s(self, tmp_path: Path) -> None:
        """Differenza mtime ≤ 2 secondi + stesso size → IDENTICAL (tolleranza FAT/NTFS)."""
        f = tmp_path / "file.dat"
        content = b"SAME_CONTENT" * 50
        f.write_bytes(content)

        stat = f.stat()
        remote = {"size": stat.st_size, "mtime": stat.st_mtime + 1.5}  # +1.5s

        result = compare_files(f, remote, method="mtime_size")
        assert result == FileStatus.IDENTICAL

    def test_missing_local_file(self, tmp_path: Path) -> None:
        """File locale non esiste → MISSING_LOCAL."""
        nonexistent = tmp_path / "ghost.dat"
        remote = {"size": 100, "mtime": time.time()}

        result = compare_files(nonexistent, remote, method="mtime_size")
        assert result == FileStatus.MISSING_LOCAL


# ---------------------------------------------------------------------------
# Test: compare_files — metodo sha256
# ---------------------------------------------------------------------------

class TestCompareFilesSha256:
    """Test per la comparazione file con metodo SHA-256."""

    def test_identical_same_hash(self, tmp_path: Path) -> None:
        """File con stesso hash SHA-256 → IDENTICAL."""
        content = b"IDENTICAL_CONTENT" * 200
        f = tmp_path / "file.dat"
        f.write_bytes(content)

        sha = hashlib.sha256(content).hexdigest()
        stat = f.stat()
        remote = {"size": stat.st_size, "mtime": stat.st_mtime, "sha256": sha}

        result = compare_files(f, remote, method="sha256")
        assert result == FileStatus.IDENTICAL

    def test_different_hash_newer_local(self, tmp_path: Path) -> None:
        """Stesso size, hash diverso, locale più recente → NEWER_LOCAL."""
        f = tmp_path / "file.dat"
        f.write_bytes(b"LOCAL_VERSION_ABCDEFGH")

        now = time.time()
        os.utime(f, (now, now))

        stat = f.stat()
        remote = {
            "size": stat.st_size,
            "mtime": now - 100,
            "sha256": "aabbcc" + "0" * 58,  # hash diverso
        }

        result = compare_files(f, remote, method="sha256")
        assert result == FileStatus.NEWER_LOCAL

    def test_different_hash_similar_mtime_is_conflict(self, tmp_path: Path) -> None:
        """Hash diverso con mtime simili → CONFLICT."""
        f = tmp_path / "file.dat"
        f.write_bytes(b"CONTENT_A" * 10)

        now = time.time()
        os.utime(f, (now, now))

        stat = f.stat()
        remote = {
            "size": stat.st_size,
            "mtime": now,  # stesso mtime
            "sha256": "aabbcc" + "0" * 58,  # hash diverso
        }

        result = compare_files(f, remote, method="sha256")
        assert result == FileStatus.CONFLICT


# ---------------------------------------------------------------------------
# Test: backup additivo locale — principio no-overwrite
# ---------------------------------------------------------------------------

class TestBackupAdditiveLocal:
    """
    Test per la logica additiva: verifica che il backup non cancelli
    né sovrascriva automaticamente file esistenti.
    """

    def test_copies_missing_file(
        self, ryujinx_dir: Path, backup_dst: Path
    ) -> None:
        """File mancante a destinazione deve essere copiato."""
        structure = {
            "saves": ryujinx_dir / "bis" / "user" / "save",
            "system": None, "mii": None, "config": None,
            "mods": None, "shader_cache": None, "roms": None,
        }

        result = backup_engine.backup_additive(
            src=ryujinx_dir,
            dst=str(backup_dst),
            contents=["saves"],
            ryujinx_structure=structure,
            pc_name="TestPC",
            dry_run=False,
            integrity_method="mtime_size",
            size_warning_gb=999.0,
        )

        assert len(result.copied) > 0
        assert len(result.errors) == 0

        # Verifica che i file esistano a destinazione
        copied_files = list(backup_dst.rglob("*.dat"))
        assert len(copied_files) > 0

    def test_skips_identical_file(
        self, ryujinx_dir: Path, backup_dst: Path
    ) -> None:
        """File già presente e identico a destinazione NON deve essere ricopiato."""
        # Prima copia
        save_src = ryujinx_dir / "bis" / "user" / "save" / "0000000000000001" / "game_save.dat"
        save_rel = Path("bis/user/save/0000000000000001")
        dst_dir = backup_dst / save_rel
        dst_dir.mkdir(parents=True)
        import shutil
        shutil.copy2(save_src, dst_dir / "game_save.dat")

        structure = {
            "saves": ryujinx_dir / "bis" / "user" / "save",
            "system": None, "mii": None, "config": None,
            "mods": None, "shader_cache": None, "roms": None,
        }

        result = backup_engine.backup_additive(
            src=ryujinx_dir,
            dst=str(backup_dst),
            contents=["saves"],
            ryujinx_structure=structure,
            pc_name="TestPC",
            dry_run=False,
            integrity_method="mtime_size",
            size_warning_gb=999.0,
        )

        # Il file già presente NON deve essere nella lista dei copiati
        # (o se è copiato perché ci sono altri file, almeno il file identico è in skipped)
        # Verifica che game_save.dat sia skippato
        skipped_names = [Path(s).name for s in result.skipped]
        assert "game_save.dat" in skipped_names, (
            f"Il file identico dovrebbe essere in skipped, invece: "
            f"copied={result.copied}, skipped={result.skipped}"
        )

    def test_never_deletes_destination_files(
        self, ryujinx_dir: Path, backup_dst: Path
    ) -> None:
        """
        File presenti SOLO a destinazione NON devono essere cancellati.
        Questo è il test più critico del principio fondamentale.
        """
        # Crea un file SOLO a destinazione (non esiste in sorgente)
        dst_only_dir = backup_dst / "bis" / "user" / "save" / "DESTINATION_ONLY_GAME"
        dst_only_dir.mkdir(parents=True)
        dst_only_file = dst_only_dir / "precious_save.dat"
        dst_only_file.write_bytes(b"PRECIOUS_DATA_NEVER_DELETE")

        structure = {
            "saves": ryujinx_dir / "bis" / "user" / "save",
            "system": None, "mii": None, "config": None,
            "mods": None, "shader_cache": None, "roms": None,
        }

        backup_engine.backup_additive(
            src=ryujinx_dir,
            dst=str(backup_dst),
            contents=["saves"],
            ryujinx_structure=structure,
            pc_name="TestPC",
            dry_run=False,
            integrity_method="mtime_size",
            size_warning_gb=999.0,
        )

        # Il file solo-destinazione DEVE ancora esistere
        assert dst_only_file.exists(), (
            "❌ VIOLAZIONE DEL PRINCIPIO FONDAMENTALE: "
            "il file 'precious_save.dat' presente solo a destinazione è stato eliminato!"
        )
        assert dst_only_file.read_bytes() == b"PRECIOUS_DATA_NEVER_DELETE"

    def test_conflict_saves_both_versions(
        self, tmp_path: Path, ryujinx_dir: Path, backup_dst: Path
    ) -> None:
        """
        File con contenuto diverso → entrambe le versioni salvate con suffisso _CONFLICT_.
        NON viene sovrascritta nessuna versione.
        """
        # Crea file locale
        save_dir = ryujinx_dir / "bis" / "user" / "save" / "0000000000000001"
        local_file = save_dir / "game_save.dat"

        # Crea una versione DIVERSA già a destinazione
        dst_save_dir = backup_dst / "bis" / "user" / "save" / "0000000000000001"
        dst_save_dir.mkdir(parents=True)
        dst_file = dst_save_dir / "game_save.dat"
        dst_file.write_bytes(b"DIFFERENT_REMOTE_CONTENT_" + b"\xFF" * 50)

        # Modifica mtime per renderli "contemporanei" (trigger CONFLICT)
        now = time.time()
        os.utime(local_file, (now, now))
        os.utime(dst_file, (now, now))

        structure = {
            "saves": ryujinx_dir / "bis" / "user" / "save",
            "system": None, "mii": None, "config": None,
            "mods": None, "shader_cache": None, "roms": None,
        }

        result = backup_engine.backup_additive(
            src=ryujinx_dir,
            dst=str(backup_dst),
            contents=["saves"],
            ryujinx_structure=structure,
            pc_name="TestPC",
            dry_run=False,
            integrity_method="mtime_size",
            size_warning_gb=999.0,
        )

        # Deve esserci almeno un conflitto
        assert len(result.conflicts) >= 1

        # I file CONFLICT_ devono esistere
        conflict_files = list(dst_save_dir.glob("*CONFLICT*"))
        assert len(conflict_files) >= 1, (
            f"Nessun file _CONFLICT_ trovato in {dst_save_dir}. "
            f"Files: {list(dst_save_dir.iterdir())}"
        )

    def test_dry_run_does_not_copy(
        self, ryujinx_dir: Path, backup_dst: Path
    ) -> None:
        """In dry-run, nessun file deve essere effettivamente copiato."""
        structure = {
            "saves": ryujinx_dir / "bis" / "user" / "save",
            "system": None, "mii": None, "config": None,
            "mods": None, "shader_cache": None, "roms": None,
        }

        result = backup_engine.backup_additive(
            src=ryujinx_dir,
            dst=str(backup_dst),
            contents=["saves"],
            ryujinx_structure=structure,
            pc_name="TestPC",
            dry_run=True,  # ← dry run
            integrity_method="mtime_size",
            size_warning_gb=999.0,
        )

        # In dry-run, i "copiati" sono solo segnalati, non eseguiti
        assert result.dry_run is True
        # La destinazione deve essere VUOTA (nessuna copia reale)
        dst_files = list(backup_dst.rglob("*"))
        assert len(dst_files) == 0, (
            f"In dry-run non devono essere copiati file! Trovati: {dst_files}"
        )


# ---------------------------------------------------------------------------
# Test: estimate_size
# ---------------------------------------------------------------------------

class TestEstimateSize:
    """Test per la stima della dimensione."""

    def test_estimates_file_size(self, tmp_path: Path) -> None:
        """Stima corretta per file singolo."""
        f = tmp_path / "test.dat"
        data = b"X" * 1024
        f.write_bytes(data)

        size = backup_engine.estimate_size([f])
        assert size == 1024

    def test_estimates_directory_size(self, ryujinx_dir: Path) -> None:
        """Stima corretta per una directory."""
        size = backup_engine.estimate_size([ryujinx_dir])
        assert size > 0

    def test_empty_list(self) -> None:
        """Lista vuota → 0."""
        assert backup_engine.estimate_size([]) == 0

    def test_nonexistent_path(self, tmp_path: Path) -> None:
        """Path inesistente non causa crash."""
        ghost = tmp_path / "nonexistent"
        size = backup_engine.estimate_size([ghost])
        assert size == 0


# ---------------------------------------------------------------------------
# Test: apply_retention
# ---------------------------------------------------------------------------

class TestApplyRetention:
    """Test per la pulizia delle versioni vecchie."""

    def test_keeps_last_n_versions(self, tmp_path: Path) -> None:
        """Mantiene solo le ultime N versioni di backup."""
        # Crea 5 file zip simulati con mtime crescente
        for i in range(5):
            f = tmp_path / f"ryusync_backup_2024010{i+1}_120000.zip"
            f.write_bytes(b"FAKE_ZIP")
            mtime = time.time() - (5 - i) * 3600  # più recente = indice maggiore
            os.utime(f, (mtime, mtime))

        removed = backup_engine.apply_retention(tmp_path, n=3)

        remaining = list(tmp_path.glob("ryusync_backup_*.zip"))
        assert len(remaining) == 3
        assert len(removed) == 2

    def test_does_not_remove_if_within_limit(self, tmp_path: Path) -> None:
        """Nessun file rimosso se il numero è ≤ N."""
        for i in range(2):
            f = tmp_path / f"ryusync_backup_2024010{i+1}_120000.zip"
            f.write_bytes(b"ZIP")

        removed = backup_engine.apply_retention(tmp_path, n=3)
        assert len(removed) == 0

    def test_handles_nonexistent_dir(self, tmp_path: Path) -> None:
        """Directory inesistente non causa crash."""
        ghost_dir = tmp_path / "nonexistent_dir"
        removed = backup_engine.apply_retention(ghost_dir, n=3)
        assert removed == []


# ---------------------------------------------------------------------------
# Test: verify_integrity
# ---------------------------------------------------------------------------

class TestVerifyIntegrity:
    """Test per la verifica integrità post-backup."""

    def test_identical_file_passes(self, tmp_path: Path) -> None:
        """File identico supera la verifica."""
        f = tmp_path / "file.dat"
        f.write_bytes(b"VALID" * 100)
        stat = f.stat()
        remote_meta = {"size": stat.st_size, "mtime": stat.st_mtime}

        assert backup_engine.verify_integrity(f, remote_meta, method="mtime_size") is True

    def test_different_file_fails(self, tmp_path: Path) -> None:
        """File con size/mtime diversi non supera la verifica."""
        f = tmp_path / "file.dat"
        f.write_bytes(b"LOCAL" * 50)
        # Remote ha size diverso
        remote_meta = {"size": 9999, "mtime": 0.0}

        assert backup_engine.verify_integrity(f, remote_meta, method="mtime_size") is False

    def test_missing_remote_fails(self, tmp_path: Path) -> None:
        """File non presente a destinazione (meta vuoto) non supera la verifica."""
        f = tmp_path / "file.dat"
        f.write_bytes(b"DATA")

        assert backup_engine.verify_integrity(f, {}, method="mtime_size") is False


# ---------------------------------------------------------------------------
# Test: compress_backup e _format_bytes
# ---------------------------------------------------------------------------

class TestCompressBackup:
    """Test per la compressione."""

    def test_creates_zip_file(self, ryujinx_dir: Path, tmp_path: Path) -> None:
        """compress_backup crea un file .zip non vuoto."""
        output_dir = tmp_path / "backups"
        zip_path = backup_engine.compress_backup(
            src_path=ryujinx_dir / "bis" / "user" / "save",
            output_dir=output_dir,
            compression_level=1,
        )
        assert zip_path.exists()
        assert zip_path.suffix == ".zip"
        assert zip_path.stat().st_size > 0

    def test_format_bytes(self) -> None:
        """_format_bytes formatta correttamente le dimensioni."""
        assert "B" in backup_engine._format_bytes(500)
        assert "KB" in backup_engine._format_bytes(2048)
        assert "MB" in backup_engine._format_bytes(2 * 1024 * 1024)
        assert "GB" in backup_engine._format_bytes(3 * 1024 * 1024 * 1024)
