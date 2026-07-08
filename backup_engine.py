"""
backup_engine.py — RyuSync v1.0

Logica core per backup, sincronizzazione additiva, gestione conflitti e
verifica integrità dei dati Ryujinx.

PRINCIPIO FONDAMENTALE:
  - MAI cancellare file (né locali né remoti)
  - MAI sovrascrivere automaticamente file diversi
  - Aggiungi SOLO file mancanti o effettivamente più nuovi
  - Conflitti → salva ENTRAMBE le versioni con suffisso, logga, chiedi conferma

Motore di trasferimento cloud: rclone (subprocess)
Motore locale: shutil
"""

from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

console = Console()
logger = logging.getLogger("ryusync.backup_engine")


# ---------------------------------------------------------------------------
# Enumerazioni e tipi
# ---------------------------------------------------------------------------

class FileStatus(Enum):
    """Stato di un file locale rispetto alla destinazione."""
    IDENTICAL = "identical"           # Stesso contenuto → salta
    NEWER_LOCAL = "newer_local"       # Locale più nuovo → copia
    NEWER_REMOTE = "newer_remote"     # Remoto più nuovo → potenziale conflitto
    CONFLICT = "conflict"             # Stesso nome, contenuto diverso, ambedue modificati
    MISSING_REMOTE = "missing_remote" # Non esiste a destinazione → copia
    MISSING_LOCAL = "missing_local"   # Non esiste in locale (solo remoto)
    ERROR = "error"                   # Errore di lettura/comparazione


@dataclass
class FileMeta:
    """Metadati di un file per la comparazione."""
    path: Path
    size: int = 0
    mtime: float = 0.0
    sha256: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "size": self.size,
            "mtime": self.mtime,
            "sha256": self.sha256,
        }


@dataclass
class BackupResult:
    """Risultato di un'operazione di backup/sync."""
    copied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total_bytes_copied: int = 0
    dry_run: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))

    @property
    def has_changes(self) -> bool:
        return bool(self.copied or self.conflicts)

    @property
    def summary(self) -> str:
        status = "[DRY-RUN] " if self.dry_run else ""
        return (
            f"{status}Copiati: {len(self.copied)} | "
            f"Saltati: {len(self.skipped)} | "
            f"Conflitti: {len(self.conflicts)} | "
            f"Errori: {len(self.errors)} | "
            f"Dati: {_format_bytes(self.total_bytes_copied)}"
        )


# ---------------------------------------------------------------------------
# Comparazione file
# ---------------------------------------------------------------------------

def get_local_meta(path: Path, compute_hash: bool = False) -> FileMeta:
    """
    Raccoglie i metadati di un file locale.

    Args:
        path: Percorso del file.
        compute_hash: Se True, calcola anche il SHA-256.

    Returns:
        FileMeta con size, mtime ed eventuale hash.
    """
    meta = FileMeta(path=path)
    try:
        stat = path.stat()
        meta.size = stat.st_size
        meta.mtime = stat.st_mtime
        if compute_hash:
            meta.sha256 = _compute_sha256(path)
    except (OSError, PermissionError) as e:
        logger.warning(f"Impossibile leggere metadati di {path}: {e}")
    return meta


def _compute_sha256(path: Path) -> Optional[str]:
    """Calcola l'hash SHA-256 di un file."""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def compare_files(
    local: Path,
    remote_meta: dict,
    method: str = "mtime_size",
) -> FileStatus:
    """
    Confronta un file locale con i metadati del corrispettivo remoto.

    Args:
        local: Path del file locale.
        remote_meta: Dict con 'size', 'mtime', opzionalmente 'sha256' del file remoto.
                     Se vuoto o None → MISSING_REMOTE.
        method: 'mtime_size' (veloce) | 'sha256' (accurato).

    Returns:
        FileStatus che descrive la relazione tra locale e remoto.
    """
    if not remote_meta:
        return FileStatus.MISSING_REMOTE

    if not local.exists():
        return FileStatus.MISSING_LOCAL

    try:
        local_stat = local.stat()
        local_size = local_stat.st_size
        local_mtime = local_stat.st_mtime
    except (OSError, PermissionError):
        return FileStatus.ERROR

    remote_size = remote_meta.get("size", -1)
    remote_mtime = remote_meta.get("mtime", 0.0)

    if method == "sha256":
        # Confronto hash — il più accurato
        if remote_size != local_size:
            # Dimensioni diverse → certamente diversi, determina chi è più nuovo
            if local_mtime > remote_mtime + 1:
                return FileStatus.NEWER_LOCAL
            elif remote_mtime > local_mtime + 1:
                return FileStatus.NEWER_REMOTE
            else:
                return FileStatus.CONFLICT

        local_hash = _compute_sha256(local)
        remote_hash = remote_meta.get("sha256")

        if local_hash and remote_hash and local_hash == remote_hash:
            return FileStatus.IDENTICAL

        # Hash diversi: stesso nome, contenuto diverso
        if local_mtime > remote_mtime + 1:
            return FileStatus.NEWER_LOCAL
        elif remote_mtime > local_mtime + 1:
            return FileStatus.NEWER_REMOTE
        else:
            return FileStatus.CONFLICT

    else:
        # Metodo mtime_size (default, veloce)
        if local_size == remote_size:
            # Tolleranza di 2 secondi per filesystem FAT/NTFS
            if abs(local_mtime - remote_mtime) <= 2.0:
                return FileStatus.IDENTICAL
            elif local_mtime > remote_mtime + 2:
                return FileStatus.NEWER_LOCAL
            elif remote_mtime > local_mtime + 2:
                return FileStatus.NEWER_REMOTE
            else:
                # Mtime quasi identico ma non uguale → considera identico
                return FileStatus.IDENTICAL
        else:
            # Size diverso → certamente diversi
            if local_mtime > remote_mtime + 1:
                return FileStatus.NEWER_LOCAL
            elif remote_mtime > local_mtime + 1:
                return FileStatus.NEWER_REMOTE
            else:
                return FileStatus.CONFLICT


# ---------------------------------------------------------------------------
# Stima spazio
# ---------------------------------------------------------------------------

def estimate_size(paths: list[Path]) -> int:
    """
    Stima la dimensione totale in byte di una lista di path (file o cartelle).

    Args:
        paths: Lista di Path da misurare.

    Returns:
        Dimensione totale in byte.
    """
    total = 0
    for p in paths:
        if p.is_file():
            try:
                total += p.stat().st_size
            except (OSError, PermissionError):
                pass
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    try:
                        total += f.stat().st_size
                    except (OSError, PermissionError):
                        pass
    return total


def _format_bytes(n: int) -> str:
    """Formatta byte in formato leggibile."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


# ---------------------------------------------------------------------------
# Motore backup additivo
# ---------------------------------------------------------------------------

def backup_additive(
    src: Path,
    dst: str,
    contents: list[str],
    ryujinx_structure: dict,
    pc_name: str,
    dry_run: bool = False,
    integrity_method: str = "mtime_size",
    size_warning_gb: float = 5.0,
    log_path: Optional[Path] = None,
) -> BackupResult:
    """
    Esegue un backup additivo da una cartella Ryujinx verso una destinazione.

    Comportamento:
    - Copia solo file mancanti o più nuovi a destinazione
    - Non sovrascrive mai file identici
    - Gestisce i conflitti salvando entrambe le versioni
    - Non cancella mai nulla a destinazione

    Args:
        src: Path base Ryujinx locale.
        dst: Destinazione (rclone remote, es. "gdrive:RyuSync", o path locale).
        contents: Lista di categorie da includere (es. ["saves", "config"]).
        ryujinx_structure: Struttura rilevata da detector.get_ryujinx_structure().
        pc_name: Nome del PC corrente (per suffissi conflitto).
        dry_run: Se True, mostra senza eseguire.
        integrity_method: "mtime_size" | "sha256".
        size_warning_gb: Soglia (GB) oltre cui chiedere conferma.
        log_path: Path del file di log (None = usa default).

    Returns:
        BackupResult con riepilogo dell'operazione.
    """
    result = BackupResult(dry_run=dry_run)
    is_local_dst = _is_local_destination(dst)

    # Costruisci lista di path da includere
    src_paths = _build_content_paths(contents, ryujinx_structure)
    if not src_paths:
        console.print("[yellow]⚠️  Nessun contenuto selezionato da copiare.[/yellow]")
        return result

    # Stima spazio
    total_size = estimate_size(src_paths)
    total_size_gb = total_size / (1024 ** 3)
    if total_size_gb > size_warning_gb:
        import questionary as q
        console.print(
            f"\n[bold yellow]⚠️  Attenzione: dimensione stimata = "
            f"{_format_bytes(total_size)} ({total_size_gb:.1f} GB)[/bold yellow]\n"
            f"[dim]Soglia configurata: {size_warning_gb} GB[/dim]"
        )
        if not dry_run:
            confirm = q.confirm("Vuoi procedere comunque?", default=False).ask()
            if not confirm:
                console.print("[dim]Operazione annullata dall'utente.[/dim]")
                return result

    console.print(
        Panel(
            f"{'[bold yellow][DRY-RUN][/bold yellow] ' if dry_run else ''}"
            f"Backup da [cyan]{src}[/cyan]\n"
            f"Verso [green]{dst}[/green]\n"
            f"Dimensione stimata: [white]{_format_bytes(total_size)}[/white]",
            title="[bold]Avvio Backup Additivo[/bold]",
            border_style="blue",
        )
    )

    # Setup log
    if log_path is None:
        log_dir = Path(__file__).parent / "logs"
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / f"backup_log_{result.timestamp}.txt"

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Analisi e copia file...", total=len(src_paths))

        for src_item in src_paths:
            progress.update(task, advance=1, description=f"[cyan]{src_item.name}")

            if is_local_dst:
                _backup_local_item(
                    src_item, Path(dst), src, pc_name, dry_run, integrity_method, result
                )
            else:
                _backup_rclone_item(
                    src_item, dst, src, pc_name, dry_run, integrity_method, result
                )

    # Scrivi log
    _write_log(log_path, result, src, dst, contents, pc_name, dry_run)

    # Stampa riepilogo
    _print_backup_summary(result)

    return result


def _build_content_paths(contents: list[str], structure: dict) -> list[Path]:
    """Costruisce la lista di Path da copiare in base alla selezione."""
    paths = []
    for content in contents:
        p = structure.get(content)
        if p and Path(p).exists():
            paths.append(Path(p))
        elif content == "all":
            for v in structure.values():
                if v and Path(v).exists():
                    p = Path(v)
                    if p not in paths:
                        paths.append(p)
    return paths


def _is_local_destination(dst: str) -> bool:
    """Determina se la destinazione è locale (Windows drive letter o UNC path o path relativo)."""
    if not dst:
        return False
    dst_str = str(dst)
    if ":" not in dst_str:
        return True
    drive_or_remote = dst_str.split(":")[0]
    return len(drive_or_remote) == 1 and drive_or_remote.isalpha()



# ---------------------------------------------------------------------------
# Backup locale (shutil)
# ---------------------------------------------------------------------------

def _backup_local_item(
    src_item: Path,
    dst_base: Path,
    ryujinx_base: Path,
    pc_name: str,
    dry_run: bool,
    method: str,
    result: BackupResult,
) -> None:
    """Copia un file/cartella verso una destinazione locale."""
    # Calcola path relativo rispetto alla cartella Ryujinx
    try:
        rel = src_item.relative_to(ryujinx_base)
    except ValueError:
        # Il file non è sotto ryujinx_base (es. Config.json)
        rel = Path(src_item.name)

    if src_item.is_file():
        _copy_file_local(src_item, dst_base / rel, pc_name, dry_run, method, result)
    elif src_item.is_dir():
        for file in src_item.rglob("*"):
            if file.is_file():
                try:
                    file_rel = file.relative_to(ryujinx_base)
                except ValueError:
                    file_rel = Path(src_item.name) / file.relative_to(src_item)
                _copy_file_local(file, dst_base / file_rel, pc_name, dry_run, method, result)


def _copy_file_local(
    src: Path,
    dst: Path,
    pc_name: str,
    dry_run: bool,
    method: str,
    result: BackupResult,
) -> None:
    """Copia un singolo file locale rispettando il principio additivo."""
    remote_meta = {}
    if dst.exists():
        dst_stat = dst.stat()
        remote_meta = {
            "size": dst_stat.st_size,
            "mtime": dst_stat.st_mtime,
        }
        if method == "sha256":
            remote_meta["sha256"] = _compute_sha256(dst)

    status = compare_files(src, remote_meta, method=method)

    rel_path = str(src.name)
    logger.debug(f"File: {src} → Status: {status.value}")

    if status == FileStatus.IDENTICAL:
        result.skipped.append(str(src))
        logger.info(f"[SKIP] {src} → identico")

    elif status == FileStatus.MISSING_REMOTE or status == FileStatus.NEWER_LOCAL:
        if dry_run:
            console.print(f"  [dim][DRY-RUN] Copierebbe: {src.name}[/dim]")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            result.total_bytes_copied += src.stat().st_size
        result.copied.append(str(src))
        logger.info(f"[COPY] {src} → {dst}")

    elif status == FileStatus.CONFLICT:
        _handle_conflict_local(src, dst, pc_name, dry_run, result)

    elif status == FileStatus.NEWER_REMOTE:
        # Il remoto è più recente → segnala come potenziale conflitto
        result.conflicts.append(f"[REMOTO_PIÙ_RECENTE] {src}")
        logger.warning(f"[CONFLICT] Remoto più recente di {src}")
        console.print(f"  [yellow]⚠️  Remoto più recente: {src.name}[/yellow]")

    elif status == FileStatus.ERROR:
        result.errors.append(str(src))
        logger.error(f"[ERROR] Impossibile leggere: {src}")


def _handle_conflict_local(
    src: Path,
    dst: Path,
    pc_name: str,
    dry_run: bool,
    result: BackupResult,
) -> None:
    """Gestisce un conflitto locale salvando entrambe le versioni."""
    safe_pc_name = re.sub(r'[^\w\-]', '_', pc_name or "PC1")
    conflict_local = dst.with_name(f"{dst.stem}_CONFLICT_{safe_pc_name}{dst.suffix}")
    conflict_remote = dst.with_name(f"{dst.stem}_CONFLICT_REMOTE{dst.suffix}")

    if dry_run:
        console.print(
            f"  [bold yellow][DRY-RUN] Conflitto: {src.name}[/bold yellow]\n"
            f"    → Salverebbe: {conflict_local.name}\n"
            f"    → Salverebbe: {conflict_remote.name}"
        )
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        # Salva la versione locale con suffisso PC
        shutil.copy2(src, conflict_local)
        # La versione remota (dst) rimane intatta — copiala con suffisso REMOTE
        if dst.exists():
            shutil.copy2(dst, conflict_remote)

    result.conflicts.append(f"{src} ↔ {dst}")
    logger.warning(
        f"[CONFLICT] {src.name}: salvate entrambe le versioni → "
        f"{conflict_local.name} / {conflict_remote.name}"
    )
    console.print(
        f"  [bold yellow]⚠️  Conflitto: {src.name}[/bold yellow]\n"
        f"    [dim]Versione locale → {conflict_local.name}[/dim]\n"
        f"    [dim]Versione remota → {conflict_remote.name}[/dim]"
    )


# ---------------------------------------------------------------------------
# Backup cloud (rclone)
# ---------------------------------------------------------------------------

def _backup_rclone_item(
    src_item: Path,
    dst_remote: str,
    ryujinx_base: Path,
    pc_name: str,
    dry_run: bool,
    method: str,
    result: BackupResult,
) -> None:
    """
    Copia un file/cartella verso un remote rclone.
    Usa SEMPRE 'rclone copy' (mai 'rclone sync' distruttivo).
    """
    dst_remote = Path(dst_remote).as_posix()
    try:
        rel = src_item.relative_to(ryujinx_base)
    except ValueError:
        rel = Path(src_item.name)

    rel_posix = rel.as_posix()

    if src_item.is_dir():
        dst_path = f"{dst_remote}/{rel_posix}"
    else:
        dst_path = f"{dst_remote}/{rel.parent.as_posix()}" if rel.parent != Path(".") else dst_remote

    dst_path = Path(dst_path).as_posix()

    # Prima controlla lo stato del file sul remote
    if src_item.is_file():
        remote_meta = _get_rclone_file_meta(dst_remote, rel_posix, method)
        status = compare_files(src_item, remote_meta, method=method)

        if status == FileStatus.IDENTICAL:
            result.skipped.append(str(src_item))
            return

        if status == FileStatus.CONFLICT:
            _handle_conflict_rclone(src_item, dst_remote, rel_posix, pc_name, dry_run, result)
            return

        if status == FileStatus.NEWER_REMOTE:
            result.conflicts.append(f"[REMOTO_PIÙ_RECENTE] {src_item}")
            logger.warning(f"[CONFLICT] Remoto più recente: {src_item}")
            return


    # Esegui rclone copy
    cmd = ["rclone", "copy"]
    if dry_run:
        cmd.append("--dry-run")
    cmd.extend([
        str(src_item),
        dst_path,
        "--progress",
        "--no-update-modtime",
        "--check-first",
    ])

    if src_item.is_file():
        cmd.extend(["--include", src_item.name])

    logger.info(f"[RCLONE] {' '.join(cmd)}")

    if dry_run:
        console.print(f"  [dim][DRY-RUN] rclone copy: {src_item.name} → {dst_path}[/dim]")
        result.copied.append(str(src_item))
        return

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if proc.returncode == 0:
            result.copied.append(str(src_item))
            if src_item.is_file():
                result.total_bytes_copied += src_item.stat().st_size
            logger.info(f"[OK] rclone copy: {src_item}")
        else:
            result.errors.append(f"{src_item}: {proc.stderr.strip()}")
            logger.error(f"[ERROR] rclone: {proc.stderr.strip()}")
    except subprocess.TimeoutExpired:
        result.errors.append(f"{src_item}: timeout")
        logger.error(f"[TIMEOUT] rclone copy: {src_item}")
    except FileNotFoundError:
        result.errors.append(f"rclone non trovato nel PATH")
        logger.error("[ERROR] rclone non trovato. Installa da https://rclone.org/downloads/")


def _get_rclone_file_meta(remote: str, rel_path: str, method: str) -> dict:
    """
    Recupera metadati di un file su un remote rclone.
    Usa 'rclone lsjson' per ottenere size e mtime.
    """
    remote = Path(remote).as_posix()
    rel_path = Path(rel_path).as_posix()
    remote_file = f"{remote}/{rel_path}"
    cmd = ["rclone", "lsjson", "--files-only", remote_file]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0 and proc.stdout.strip():
            items = json.loads(proc.stdout)
            if items:
                item = items[0]
                meta: dict = {
                    "size": item.get("Size", 0),
                    "mtime": 0.0,
                }
                # Parse ModTime (es. "2024-01-15T10:30:00.000000000+01:00")
                mod_time_str = item.get("ModTime", "")
                if mod_time_str:
                    try:
                        # Normalizza il formato ISO
                        mod_time_str = re.sub(r'\.\d+', '', mod_time_str)
                        mod_time_str = re.sub(r'([+-]\d{2}):(\d{2})$', r'\1\2', mod_time_str)
                        dt = datetime.strptime(mod_time_str, "%Y-%m-%dT%H:%M:%S%z")
                        meta["mtime"] = dt.timestamp()
                    except (ValueError, AttributeError):
                        pass
                return meta
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass
    return {}  # File non trovato → MISSING_REMOTE


def _handle_conflict_rclone(
    local_file: Path,
    remote_base: str,
    rel_path: str,
    pc_name: str,
    dry_run: bool,
    result: BackupResult,
) -> None:
    """Gestisce un conflitto rclone salvando entrambe le versioni."""
    safe_pc_name = re.sub(r'[^\w\-]', '_', pc_name or "PC1")
    rel_path_pure = Path(rel_path)
    stem = rel_path_pure.stem
    suffix = rel_path_pure.suffix
    parent = rel_path_pure.parent.as_posix()
    prefix = f"{parent}/" if parent != "." else ""

    conflict_local_name = f"{prefix}{stem}_CONFLICT_{safe_pc_name}{suffix}"
    conflict_remote_name = f"{prefix}{stem}_CONFLICT_REMOTE{suffix}"


    if dry_run:
        console.print(
            f"  [bold yellow][DRY-RUN] Conflitto rclone: {local_file.name}[/bold yellow]\n"
            f"    → Copierebbe locale come: {conflict_local_name}\n"
            f"    → Rinominazione remota: {conflict_remote_name}"
        )
        result.conflicts.append(f"[DRY-RUN] {local_file} ↔ {remote_base}/{rel_path}")
        return

    # Copia la versione locale con suffisso PC
    cmd_copy_local = [
        "rclone", "copyto",
        str(local_file),
        f"{remote_base}/{conflict_local_name}",
    ]

    # Rinomina (copia + cancella no: usiamo copyto) la versione remota
    cmd_copy_remote = [
        "rclone", "copyto",
        f"{remote_base}/{rel_path}",
        f"{remote_base}/{conflict_remote_name}",
    ]

    for cmd in [cmd_copy_local, cmd_copy_remote]:
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                logger.error(f"[ERROR] Conflict copy: {proc.stderr}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error(f"[ERROR] Conflict copy exception: {e}")

    result.conflicts.append(f"{local_file} ↔ {remote_base}/{rel_path}")
    logger.warning(f"[CONFLICT] {local_file.name}: entrambe le versioni salvate")
    console.print(
        f"  [bold yellow]⚠️  Conflitto: {local_file.name}[/bold yellow]\n"
        f"    [dim]→ {conflict_local_name}[/dim]\n"
        f"    [dim]→ {conflict_remote_name}[/dim]"
    )


# ---------------------------------------------------------------------------
# Ripristino (restore)
# ---------------------------------------------------------------------------

def restore(
    src: str,
    dst: Path,
    dry_run: bool = False,
    integrity_method: str = "mtime_size",
) -> BackupResult:
    """
    Ripristina file da una sorgente (rclone remote o path locale) verso una cartella locale.

    ATTENZIONE: Prima di sovrascrivere file locali, confronta mtime+size e chiede conferma.
    Non cancella mai file locali.

    Args:
        src: Sorgente (rclone remote o path locale).
        dst: Cartella Ryujinx di destinazione.
        dry_run: Se True, mostra senza eseguire.
        integrity_method: Metodo di confronto.

    Returns:
        BackupResult con riepilogo.
    """
    import questionary as q

    result = BackupResult(dry_run=dry_run)
    is_local_src = _is_local_destination(src)

    console.print(
        Panel(
            f"{'[bold yellow][DRY-RUN][/bold yellow] ' if dry_run else ''}"
            f"Ripristino da [green]{src}[/green]\n"
            f"Verso [cyan]{dst}[/cyan]",
            title="[bold]Ripristino[/bold]",
            border_style="green",
        )
    )

    if not dry_run:
        confirm = q.confirm(
            "⚠️  Stai per ripristinare file sulla cartella Ryujinx locale. Continuare?",
            default=False,
        ).ask()
        if not confirm:
            console.print("[dim]Ripristino annullato.[/dim]")
            return result

    if is_local_src:
        _restore_local(Path(src), dst, dry_run, integrity_method, result)
    else:
        _restore_rclone(src, dst, dry_run, result)

    _print_backup_summary(result)
    return result


def _restore_local(
    src_dir: Path,
    dst: Path,
    dry_run: bool,
    method: str,
    result: BackupResult,
) -> None:
    """Ripristina da cartella locale."""
    import questionary as q

    for src_file in src_dir.rglob("*"):
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(src_dir)
        dst_file = dst / rel

        remote_meta = {}
        if dst_file.exists():
            stat = dst_file.stat()
            remote_meta = {"size": stat.st_size, "mtime": stat.st_mtime}
            if method == "sha256":
                remote_meta["sha256"] = _compute_sha256(dst_file)

        status = compare_files(src_file, remote_meta, method=method)

        if status == FileStatus.IDENTICAL:
            result.skipped.append(str(rel))
            continue

        if status in (FileStatus.NEWER_REMOTE, FileStatus.CONFLICT):
            console.print(
                f"  [yellow]⚠️  Il file locale è diverso/più recente del backup: {rel}[/yellow]"
            )
            if not dry_run:
                overwrite = q.confirm(
                    f"Sovrascrivere {rel} con la versione del backup?",
                    default=False,
                ).ask()
                if not overwrite:
                    result.skipped.append(str(rel))
                    continue

        if dry_run:
            console.print(f"  [dim][DRY-RUN] Ripristinerebbe: {rel}[/dim]")
        else:
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            result.total_bytes_copied += src_file.stat().st_size

        result.copied.append(str(rel))


def _restore_rclone(
    src_remote: str,
    dst: Path,
    dry_run: bool,
    result: BackupResult,
) -> None:
    """Ripristina da remote rclone."""
    src_remote = Path(src_remote).as_posix()
    dst_posix = Path(dst).as_posix()
    cmd = ["rclone", "copy"]
    if dry_run:
        cmd.append("--dry-run")
    cmd.extend([src_remote, dst_posix, "--progress", "--no-update-modtime"])

    logger.info(f"[RCLONE RESTORE] {' '.join(cmd)}")

    if dry_run:
        console.print(f"  [dim][DRY-RUN] rclone copy {src_remote} → {dst}[/dim]")
        result.copied.append(f"{src_remote} → {dst}")
        return

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if proc.returncode == 0:
            result.copied.append(f"{src_remote} → {dst}")
            logger.info(f"[OK] Ripristino rclone completato")
        else:
            result.errors.append(proc.stderr.strip())
            logger.error(f"[ERROR] rclone restore: {proc.stderr.strip()}")
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        result.errors.append(str(e))
        logger.error(f"[ERROR] rclone restore: {e}")


# ---------------------------------------------------------------------------
# Compressione
# ---------------------------------------------------------------------------

def compress_backup(
    src_path: Path,
    output_dir: Path,
    compression_level: int = 6,
) -> Path:
    """
    Comprime una cartella in un file .zip.

    Args:
        src_path: Cartella o file sorgente.
        output_dir: Dove salvare il .zip.
        compression_level: Livello compressione zlib (1-9).

    Returns:
        Path del file .zip creato.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"ryusync_backup_{timestamp}.zip"
    zip_path = output_dir / zip_name

    output_dir.mkdir(parents=True, exist_ok=True)
    console.print(f"[cyan]📦 Compressione → {zip_path.name}...[/cyan]")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=compression_level) as zf:
        if src_path.is_file():
            zf.write(src_path, src_path.name)
        elif src_path.is_dir():
            for file in src_path.rglob("*"):
                if file.is_file():
                    zf.write(file, file.relative_to(src_path.parent))

    size = zip_path.stat().st_size
    console.print(f"[green]✓ Archivio creato: {zip_path.name} ({_format_bytes(size)})[/green]")
    logger.info(f"[COMPRESS] {zip_path} ({_format_bytes(size)})")
    return zip_path


# ---------------------------------------------------------------------------
# Retention (pulizia versioni vecchie)
# ---------------------------------------------------------------------------

def apply_retention(backup_dir: Path, n: int = 3) -> list[Path]:
    """
    Mantiene solo le ultime N versioni di backup nella cartella specificata.
    Rimuove SOLO file .zip locali — non tocca mai file cloud.

    Args:
        backup_dir: Cartella contenente i backup compressi.
        n: Numero di versioni da conservare.

    Returns:
        Lista dei file eliminati.
    """
    removed: list[Path] = []

    if not backup_dir.exists():
        return removed

    zip_files = sorted(
        [f for f in backup_dir.glob("ryusync_backup_*.zip") if f.is_file()],
        key=lambda f: f.stat().st_mtime,
    )

    if len(zip_files) > n:
        to_remove = zip_files[: len(zip_files) - n]
        for old_zip in to_remove:
            try:
                old_zip.unlink()
                removed.append(old_zip)
                console.print(f"[dim]🗑 Rimosso (retention): {old_zip.name}[/dim]")
                logger.info(f"[RETENTION] Rimosso: {old_zip}")
            except OSError as e:
                logger.warning(f"[RETENTION] Impossibile rimuovere {old_zip}: {e}")

    return removed


# ---------------------------------------------------------------------------
# Verifica integrità post-backup
# ---------------------------------------------------------------------------

def verify_integrity(
    local: Path,
    remote_meta: dict,
    method: str = "mtime_size",
) -> bool:
    """
    Verifica che un file copiato sia integro confrontandolo con i metadati remoti.

    Args:
        local: File locale originale.
        remote_meta: Metadati del file alla destinazione.
        method: "mtime_size" | "sha256".

    Returns:
        True se il file è integro (identico alla destinazione).
    """
    status = compare_files(local, remote_meta, method=method)
    return status == FileStatus.IDENTICAL


def verify_backup_integrity(
    src: Path,
    dst: str,
    ryujinx_structure: dict,
    contents: list[str],
    method: str = "mtime_size",
) -> dict:
    """
    Verifica l'integrità di tutti i file copiati confrontando locale con destinazione.

    Returns:
        Dict con 'ok', 'failed', 'missing' liste di path.
    """
    report = {"ok": [], "failed": [], "missing": []}
    is_local = _is_local_destination(dst)
    src_paths = _build_content_paths(contents, ryujinx_structure)

    console.print("\n[cyan]🔍 Verifica integrità backup...[/cyan]")

    for src_item in src_paths:
        if src_item.is_file():
            files = [src_item]
        else:
            files = [f for f in src_item.rglob("*") if f.is_file()]

        for f in files:
            try:
                rel = f.relative_to(src)
            except ValueError:
                rel = Path(f.name)

            if is_local:
                dst_file = Path(dst) / rel
                if not dst_file.exists():
                    report["missing"].append(str(rel))
                    continue
                dst_stat = dst_file.stat()
                remote_meta = {"size": dst_stat.st_size, "mtime": dst_stat.st_mtime}
                if method == "sha256":
                    remote_meta["sha256"] = _compute_sha256(dst_file)
            else:
                remote_meta = _get_rclone_file_meta(dst, rel.as_posix(), method)
                if not remote_meta:
                    report["missing"].append(str(rel))
                    continue

            if verify_integrity(f, remote_meta, method):
                report["ok"].append(str(rel))
            else:
                report["failed"].append(str(rel))

    ok_count = len(report["ok"])
    fail_count = len(report["failed"])
    miss_count = len(report["missing"])

    console.print(
        f"[green]✓ OK: {ok_count}[/green] | "
        f"[red]✗ Falliti: {fail_count}[/red] | "
        f"[yellow]⚠ Mancanti: {miss_count}[/yellow]"
    )

    return report


# ---------------------------------------------------------------------------
# Verifica rclone
# ---------------------------------------------------------------------------

def check_rclone() -> bool:
    """Verifica che rclone sia installato e raggiungibile."""
    try:
        proc = subprocess.run(
            ["rclone", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def list_rclone_remotes() -> list[str]:
    """Elenca i remote rclone configurati."""
    try:
        proc = subprocess.run(
            ["rclone", "listremotes"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            return [r.strip() for r in proc.stdout.splitlines() if r.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return []


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(log_path: Path) -> None:
    """Configura il sistema di logging su file."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def _write_log(
    log_path: Path,
    result: BackupResult,
    src: Path,
    dst: str,
    contents: list[str],
    pc_name: str,
    dry_run: bool,
) -> None:
    """Scrive un log timestampato dettagliato dell'operazione."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"RyuSync Backup Log — {datetime.now().isoformat()}\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"PC: {pc_name}\n")
        f.write(f"Sorgente: {src}\n")
        f.write(f"Destinazione: {dst}\n")
        f.write(f"Contenuti: {', '.join(contents)}\n")
        f.write(f"Modalità: {'DRY-RUN' if dry_run else 'REALE'}\n\n")
        f.write(f"--- RIEPILOGO ---\n")
        f.write(f"{result.summary}\n\n")

        if result.copied:
            f.write(f"--- FILE COPIATI ({len(result.copied)}) ---\n")
            for item in result.copied:
                f.write(f"  + {item}\n")
            f.write("\n")

        if result.skipped:
            f.write(f"--- FILE SALTATI ({len(result.skipped)}) ---\n")
            for item in result.skipped:
                f.write(f"  = {item}\n")
            f.write("\n")

        if result.conflicts:
            f.write(f"--- CONFLITTI ({len(result.conflicts)}) [REVISIONE MANUALE RICHIESTA] ---\n")
            for item in result.conflicts:
                f.write(f"  ! {item}\n")
            f.write("\n")

        if result.errors:
            f.write(f"--- ERRORI ({len(result.errors)}) ---\n")
            for item in result.errors:
                f.write(f"  X {item}\n")
            f.write("\n")

    logger.info(f"[LOG] Scritto: {log_path}")


# ---------------------------------------------------------------------------
# Stampa riepilogo
# ---------------------------------------------------------------------------

def _print_backup_summary(result: BackupResult) -> None:
    """Stampa un riepilogo visivo dell'operazione."""
    table = Table(title="📊 Riepilogo Operazione", show_header=False, box=None)
    table.add_column("Campo", style="dim")
    table.add_column("Valore")

    table.add_row("Modalità", "[yellow]DRY-RUN[/yellow]" if result.dry_run else "[green]REALE[/green]")
    table.add_row("File copiati", f"[green]{len(result.copied)}[/green]")
    table.add_row("File saltati", f"[dim]{len(result.skipped)}[/dim]")
    table.add_row("Conflitti", f"[{'red' if result.conflicts else 'dim'}]{len(result.conflicts)}[/{'red' if result.conflicts else 'dim'}]")
    table.add_row("Errori", f"[{'red' if result.errors else 'dim'}]{len(result.errors)}[/{'red' if result.errors else 'dim'}]")
    table.add_row("Dati trasferiti", _format_bytes(result.total_bytes_copied))

    console.print("\n")
    console.print(table)

    if result.conflicts:
        console.print(
            "\n[bold yellow]⚠️  Conflitti rilevati![/bold yellow] "
            "Controlla i file con suffisso _CONFLICT_ e il log per risolvere manualmente."
        )

    if result.errors:
        console.print(f"\n[bold red]❌ {len(result.errors)} errori durante l'operazione.[/bold red]")
