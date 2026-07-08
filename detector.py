"""
detector.py — RyuSync v1.0

Rilevamento automatico della cartella dati di Ryujinx.
Versione corrente: supporto SOLO Windows.

Architettura estendibile: la funzione principale detect_ryujinx_path(os_name)
accetta un parametro os_name per consentire il supporto multipiattaforma
in versioni future senza modificare la logica core.

TODO (v2.0): aggiungere supporto Linux e macOS nei branch indicati.
"""

from __future__ import annotations

import os
import sys
import winreg
from pathlib import Path
from typing import Optional

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# ---------------------------------------------------------------------------
# Sottocartelle che devono esistere per considerare valida un'installazione
# ---------------------------------------------------------------------------
REQUIRED_SUBDIRS = ["bis"]
OPTIONAL_INDICATORS = ["Config.json", "mods", "sdcard"]

# Dimensione minima della cartella "bis" per essere considerata valida (bytes)
MIN_BIS_SIZE_BYTES = 0  # 0 = accetta anche installazioni vuote/nuove


# ---------------------------------------------------------------------------
# Funzione principale — entry point per il rilevamento multipiattaforma
# ---------------------------------------------------------------------------

def detect_ryujinx_path(os_name: str) -> list[Path]:
    """
    Rileva le installazioni valide di Ryujinx per il sistema operativo specificato.

    Args:
        os_name: Identificatore SO — 'windows' | 'linux' (TODO) | 'darwin' (TODO)

    Returns:
        Lista di Path a cartelle dati Ryujinx valide trovate.
        Lista vuota se nessuna installazione è rilevata automaticamente.

    Raises:
        ValueError: Se os_name non è supportato in questa versione.
    """
    if os_name == "windows":
        return _detect_windows()

    # TODO (v2.0 — Linux): aggiungere rilevamento per Linux
    # Percorsi tipici su Linux:
    #   - ~/.config/Ryujinx  (installazione standard)
    #   - Cartella "portable" accanto all'eseguibile AppImage
    # Implementazione suggerita:
    #   return _detect_linux()
    elif os_name == "linux":
        raise ValueError(
            "Supporto Linux non ancora implementato. "
            "Pianificato per RyuSync v2.0. "
            "Contribuisci su GitHub se vuoi accelerare lo sviluppo!"
        )

    # TODO (v2.0 — macOS): aggiungere rilevamento per macOS
    # Percorsi tipici su macOS:
    #   - ~/Library/Application Support/Ryujinx  (installazione standard)
    #   - Cartella "portable" accanto all'app .app
    # Implementazione suggerita:
    #   return _detect_macos()
    elif os_name == "darwin":
        raise ValueError(
            "Supporto macOS non ancora implementato. "
            "Pianificato per RyuSync v2.0. "
            "Contribuisci su GitHub se vuoi accelerare lo sviluppo!"
        )

    else:
        raise ValueError(
            f"Sistema operativo '{os_name}' non supportato. "
            f"Valori validi: 'windows' (altri in arrivo in v2.0)."
        )


# ---------------------------------------------------------------------------
# Implementazione Windows
# ---------------------------------------------------------------------------

def _detect_windows() -> list[Path]:
    """
    Rileva installazioni Ryujinx su Windows controllando in ordine:
    1. Modalità portable: cartella 'portable' accanto all'eseguibile Ryujinx
    2. Modalità default: %APPDATA%\\Ryujinx  (Roaming)

    Returns:
        Lista di Path validi trovati (può essere vuota).
    """
    found: list[Path] = []

    console.print("\n[bold cyan]🔍 Ricerca installazioni Ryujinx...[/bold cyan]")

    # --- 1. Modalità portable ---
    portable_paths = _find_portable_mode_windows()
    for p in portable_paths:
        if validate_ryujinx_dir(p) and p not in found:
            console.print(f"  [green]✓[/green] Trovata (portable): [dim]{p}[/dim]")
            found.append(p)

    # --- 2. Modalità default: %APPDATA%\Ryujinx ---
    appdata_path = _get_appdata_ryujinx_path()
    if appdata_path and validate_ryujinx_dir(appdata_path):
        if appdata_path not in found:
            console.print(f"  [green]✓[/green] Trovata (AppData): [dim]{appdata_path}[/dim]")
            found.append(appdata_path)

    return found


def _find_portable_mode_windows() -> list[Path]:
    """
    Cerca eseguibili Ryujinx.exe nel sistema tramite:
    1. PATH di sistema
    2. Cartelle comuni di installazione
    3. Registro di Windows (App Paths)

    Per ogni eseguibile trovato, verifica se esiste una sottocartella 'portable'.
    """
    candidates: list[Path] = []
    ryujinx_exe_paths: list[Path] = []

    # Cerca in PATH
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    for dir_str in path_dirs:
        exe = Path(dir_str) / "Ryujinx.exe"
        if exe.exists():
            ryujinx_exe_paths.append(exe)

    # Cerca in cartelle comuni Windows
    common_dirs = [
        Path(os.environ.get("ProgramFiles", "C:\\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
        Path.home() / "AppData" / "Local" / "Programs",
        Path.home() / "Downloads",
        Path("C:\\Ryujinx"),
        Path("D:\\Ryujinx"),
        Path("E:\\Ryujinx"),
    ]
    for common_dir in common_dirs:
        try:
            if common_dir.exists():
                # Check depth 0: directly in the common directory
                exe0 = common_dir / "Ryujinx.exe"
                try:
                    if exe0.is_file() and exe0 not in ryujinx_exe_paths:
                        ryujinx_exe_paths.append(exe0)
                except (OSError, PermissionError):
                    pass

                # Check depth 1 and depth 2 using iterdir()
                try:
                    for entry in common_dir.iterdir():
                        try:
                            if entry.is_dir():
                                # Depth 1: entry / "Ryujinx.exe"
                                exe1 = entry / "Ryujinx.exe"
                                if exe1.is_file() and exe1 not in ryujinx_exe_paths:
                                    ryujinx_exe_paths.append(exe1)

                                # Depth 2: entry / "publish" / "Ryujinx.exe" or entry / "ryujinx-publish" / "Ryujinx.exe"
                                for pub_name in ("publish", "ryujinx-publish"):
                                    pub_dir = entry / pub_name
                                    try:
                                        if pub_dir.is_dir():
                                            exe2 = pub_dir / "Ryujinx.exe"
                                            if exe2.is_file() and exe2 not in ryujinx_exe_paths:
                                                ryujinx_exe_paths.append(exe2)
                                    except (OSError, PermissionError):
                                        pass
                        except (OSError, PermissionError):
                            pass
                except (OSError, PermissionError):
                    pass
        except (OSError, PermissionError):
            pass

    # Cerca nel registro Windows (App Paths)
    try:
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Ryujinx.exe"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
            exe_path_str, _ = winreg.QueryValueEx(key, "")
            exe_path = Path(exe_path_str)
            if exe_path.exists() and exe_path not in ryujinx_exe_paths:
                ryujinx_exe_paths.append(exe_path)
    except (FileNotFoundError, OSError):
        pass

    # Per ogni eseguibile trovato, controlla se esiste 'portable'
    for exe in ryujinx_exe_paths:
        portable_dir = exe.parent / "portable"
        if portable_dir.exists():
            candidates.append(portable_dir)

    return candidates


def _get_appdata_ryujinx_path() -> Optional[Path]:
    """
    Restituisce il path della cartella Ryujinx in AppData\\Roaming.
    """
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    path = Path(appdata) / "Ryujinx"
    return path if path.exists() else None


# ---------------------------------------------------------------------------
# Validazione
# ---------------------------------------------------------------------------

def validate_ryujinx_dir(path: Path) -> bool:
    """
    Verifica che la cartella sia una valida installazione Ryujinx controllando
    la presenza delle sottocartelle/file richiesti.

    Args:
        path: Percorso da validare.

    Returns:
        True se la cartella contiene la struttura dati Ryujinx attesa.
    """
    if not path or not path.exists() or not path.is_dir():
        return False

    # Deve avere almeno una delle strutture richieste
    for subdir in REQUIRED_SUBDIRS:
        subpath = path / subdir
        if subpath.exists():
            return True

    # Oppure avere Config.json (installazione nuova senza salvataggi)
    if (path / "Config.json").exists():
        return True

    return False


def get_ryujinx_structure(ryujinx_path: Path) -> dict[str, Optional[Path]]:
    """
    Analizza la struttura di una cartella Ryujinx e restituisce i path
    dei componenti principali trovati.

    Args:
        ryujinx_path: Path base dell'installazione Ryujinx.

    Returns:
        Dict con chiavi: saves, mii, system, config, mods, shader_cache, roms
    """
    structure: dict[str, Optional[Path]] = {
        "saves": None,
        "mii": None,
        "system": None,
        "config": None,
        "mods": None,
        "shader_cache": None,
        "roms": None,
    }

    # Salvataggi utente
    saves_path = ryujinx_path / "bis" / "user" / "save"
    if saves_path.exists():
        structure["saves"] = saves_path

    # Dati Mii (possono essere in più posizioni)
    mii_candidates = [
        ryujinx_path / "bis" / "user" / "save" / "mii",
        ryujinx_path / "bis" / "user" / "mii",
        ryujinx_path / "mii",
    ]
    for mii_path in mii_candidates:
        if mii_path.exists():
            structure["mii"] = mii_path
            break

    # Dati di sistema
    system_path = ryujinx_path / "bis" / "system"
    if system_path.exists():
        structure["system"] = system_path

    # Config.json
    config_path = ryujinx_path / "Config.json"
    if config_path.exists():
        structure["config"] = config_path

    # Mod
    mods_path = ryujinx_path / "mods"
    if mods_path.exists():
        structure["mods"] = mods_path

    # Shader cache
    shader_path = ryujinx_path / "bis" / "user" / "Contents" / "registered"
    if not shader_path.exists():
        shader_path = ryujinx_path / "shader_cache"
    if shader_path.exists():
        structure["shader_cache"] = shader_path

    # ROM: prova a leggerlo da Config.json
    roms_path = _get_roms_path_from_config(ryujinx_path)
    if roms_path and roms_path.exists():
        structure["roms"] = roms_path

    return structure


def _get_roms_path_from_config(ryujinx_path: Path) -> Optional[Path]:
    """
    Legge il percorso delle ROM dal Config.json di Ryujinx.
    """
    import json
    config_file = ryujinx_path / "Config.json"
    if not config_file.exists():
        return None
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        # Prova varie chiavi tipiche di Ryujinx
        for key in ["game_dirs", "GameDirs", "gameDirs"]:
            if key in config_data:
                dirs = config_data[key]
                if isinstance(dirs, list) and dirs:
                    return Path(dirs[0])
    except (json.JSONDecodeError, OSError, KeyError):
        pass
    return None


# ---------------------------------------------------------------------------
# Selezione interattiva (quando trovate più installazioni)
# ---------------------------------------------------------------------------

def select_ryujinx_path(found_paths: list[Path]) -> Optional[Path]:
    """
    Chiede all'utente di scegliere tra più installazioni trovate,
    oppure di inserire un path manuale se non ne viene trovata nessuna.

    Args:
        found_paths: Lista di path rilevati automaticamente.

    Returns:
        Path selezionato dall'utente, o None se l'utente annulla.
    """
    if len(found_paths) == 1:
        path = found_paths[0]
        console.print(f"\n[bold green]✅ Usata installazione: [/bold green][dim]{path}[/dim]")
        return path

    if len(found_paths) > 1:
        console.print(
            Panel(
                f"[yellow]Trovate {len(found_paths)} installazioni di Ryujinx.[/yellow]\n"
                "Seleziona quella da usare per il backup:",
                title="[bold]Selezione Installazione[/bold]",
                border_style="yellow",
            )
        )

        choices = [str(p) for p in found_paths] + ["➕ Inserisci manualmente un percorso diverso"]
        answer = questionary.select(
            "Quale installazione Ryujinx vuoi usare?",
            choices=choices,
        ).ask()

        if answer is None:
            return None

        if answer == choices[-1]:
            return _prompt_manual_path()

        return Path(answer)

    # Nessuna installazione trovata
    console.print("\n[bold yellow]⚠️  Nessuna installazione Ryujinx rilevata automaticamente.[/bold yellow]")
    return _prompt_manual_path()


def _prompt_manual_path() -> Optional[Path]:
    """
    Chiede all'utente di inserire manualmente il percorso della cartella dati Ryujinx
    e lo valida prima di accettarlo.
    """
    console.print(
        "\n[dim]Inserisci il percorso completo della cartella dati di Ryujinx.[/dim]\n"
        "[dim]Esempio: C:\\Users\\TuoNome\\AppData\\Roaming\\Ryujinx[/dim]\n"
        "[dim]         C:\\Games\\Ryujinx\\portable[/dim]\n"
    )

    while True:
        raw = questionary.text(
            "Percorso cartella dati Ryujinx:",
            validate=lambda x: len(x.strip()) > 0 or "Inserisci un percorso valido.",
        ).ask()

        if raw is None:
            return None

        path = Path(raw.strip())

        if not path.exists():
            console.print(f"[red]✗ La cartella non esiste: {path}[/red]")
            retry = questionary.confirm("Vuoi riprovare?", default=True).ask()
            if not retry:
                return None
            continue

        if not validate_ryujinx_dir(path):
            console.print(
                f"[yellow]⚠️  La cartella esiste ma non sembra contenere dati Ryujinx validi[/yellow]\n"
                f"[dim]   (manca la sottocartella 'bis/' o il file 'Config.json')[/dim]"
            )
            # Mostra cosa c'è nella cartella per aiutare l'utente
            try:
                items = list(path.iterdir())[:10]
                if items:
                    console.print("[dim]Contenuto trovato:[/dim]")
                    for item in items:
                        icon = "📁" if item.is_dir() else "📄"
                        console.print(f"  {icon} {item.name}")
            except PermissionError:
                pass

            force = questionary.confirm(
                "Vuoi usare comunque questo percorso?",
                default=False,
            ).ask()
            if force:
                return path

            retry = questionary.confirm("Vuoi inserire un percorso diverso?", default=True).ask()
            if not retry:
                return None
            continue

        console.print(f"[green]✓ Percorso valido: {path}[/green]")
        return path


# ---------------------------------------------------------------------------
# Utility: stampa riepilogo struttura rilevata
# ---------------------------------------------------------------------------

def print_ryujinx_structure(ryujinx_path: Path) -> None:
    """Stampa un riepilogo della struttura Ryujinx rilevata."""
    structure = get_ryujinx_structure(ryujinx_path)

    table = Table(title=f"Struttura Ryujinx: {ryujinx_path}", show_header=True)
    table.add_column("Componente", style="cyan")
    table.add_column("Stato", justify="center")
    table.add_column("Percorso", style="dim")

    icons = {
        "saves": "💾 Salvataggi",
        "mii": "👤 Dati Mii",
        "system": "⚙️  Sistema",
        "config": "📋 Config.json",
        "mods": "🎮 Mod",
        "shader_cache": "🎨 Shader Cache",
        "roms": "💿 ROM",
    }

    for key, label in icons.items():
        path = structure.get(key)
        if path:
            status = "[green]✓ Trovato[/green]"
            path_str = str(path)
        else:
            status = "[dim]✗ Non trovato[/dim]"
            path_str = "—"
        table.add_row(label, status, path_str)

    console.print(table)


# ---------------------------------------------------------------------------
# Punto di ingresso standalone (per test rapido)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    current_os = sys.platform
    if current_os == "win32":
        os_name = "windows"
    elif current_os == "linux":
        os_name = "linux"
    elif current_os == "darwin":
        os_name = "darwin"
    else:
        os_name = current_os

    try:
        paths = detect_ryujinx_path(os_name)
        selected = select_ryujinx_path(paths)
        if selected:
            print_ryujinx_structure(selected)
    except ValueError as e:
        console.print(f"[red]Errore: {e}[/red]")
        sys.exit(1)
