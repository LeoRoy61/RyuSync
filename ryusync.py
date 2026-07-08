"""
ryusync.py — RyuSync v1.0 — Entry Point

Backup e sincronizzazione sicura dei dati Ryujinx tra più PC Windows.

Utilizzo:
  python ryusync.py                          # Modalità interattiva
  python ryusync.py --mode=incremental --silent  # Backup automatico (Task Scheduler)
  python ryusync.py --dry-run               # Mostra senza eseguire
  python ryusync.py --unschedule            # Rimuovi task pianificato
  python ryusync.py --help                  # Mostra aiuto

Versione: 1.0 — Solo Windows
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Optional

# Verifica Python 3.10+
if sys.version_info < (3, 10):
    print("❌ RyuSync richiede Python 3.10 o superiore.")
    sys.exit(1)

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text
import questionary

# Importa moduli RyuSync
import detector
import backup_engine
import scheduler
import security

# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------

VERSION = "1.0.0"
CONFIG_FILE = Path(__file__).parent / "config.yaml"
LOG_DIR = Path(__file__).parent / "logs"

BANNER = """
██████╗ ██╗   ██╗██╗   ██╗███████╗██╗   ██╗███╗   ██╗ ██████╗
██╔══██╗╚██╗ ██╔╝██║   ██║██╔════╝╚██╗ ██╔╝████╗  ██║██╔════╝
██████╔╝ ╚████╔╝ ██║   ██║███████╗ ╚████╔╝ ██╔██╗ ██║██║
██╔══██╗  ╚██╔╝  ██║   ██║╚════██║  ╚██╔╝  ██║╚██╗██║██║
██║  ██║   ██║   ╚██████╔╝███████║   ██║   ██║ ╚████║╚██████╗
╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚══════╝   ╚═╝   ╚═╝  ╚═══╝ ╚═════╝
"""

console = Console()
logger = logging.getLogger("ryusync")


# ---------------------------------------------------------------------------
# Configurazione
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "ryujinx_path": "",
    "pc_name": socket.gethostname(),
    "destination_type": "",
    "destination_path": "",
    "contents": {
        "saves": True,
        "mii": True,
        "system": True,
        "config": True,
        "mods": True,
        "roms": False,
        "shader_cache": False,
    },
    "integrity_method": "mtime_size",
    "compress_before_upload": False,
    "compression_level": 6,
    "keep_versions": 3,
    "size_warning_threshold_gb": 5.0,
    "desktop_notifications": True,
    "schedule_frequency": "",
    "schedule_custom_value": None,
    "schedule_custom_unit": None,
    "dry_run": False,
    "log_dir": "logs",
}


def load_config() -> dict:
    """
    Carica config.yaml. Se non esiste, restituisce la configurazione di default.
    """
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            # Merge con default per gestire chiavi mancanti
            merged = dict(DEFAULT_CONFIG)
            merged.update(loaded)
            if "contents" in loaded:
                merged["contents"] = dict(DEFAULT_CONFIG["contents"])
                merged["contents"].update(loaded["contents"])
            return merged
        except yaml.YAMLError as e:
            console.print(f"[red]❌ Errore lettura config.yaml: {e}[/red]")
    return dict(DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    """
    Salva config.yaml con permessi ristretti (solo utente corrente su Windows).
    """
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

        # Applica permessi ristretti su Windows tramite icacls
        _restrict_config_permissions_windows(CONFIG_FILE)
        logger.info(f"Config salvata: {CONFIG_FILE}")

    except (OSError, yaml.YAMLError) as e:
        console.print(f"[red]❌ Errore salvataggio config: {e}[/red]")


def _restrict_config_permissions_windows(config_path: Path) -> None:
    """
    Restringe i permessi di config.yaml su Windows tramite icacls.
    Solo l'utente corrente avrà accesso.

    TODO (v2.0 — Linux/macOS): usare os.chmod(config_path, 0o600)
    """
    username = os.environ.get("USERNAME", os.environ.get("USER", ""))
    if not username:
        return

    try:
        # Rimuove ereditarietà e accesso per tutti
        subprocess.run(
            ["icacls", str(config_path), "/inheritance:d"],
            capture_output=True, timeout=10,
        )
        # Rimuove accesso per Everyone e altri
        subprocess.run(
            ["icacls", str(config_path), "/remove", "Everyone"],
            capture_output=True, timeout=10,
        )
        # Garantisce accesso solo all'utente corrente
        subprocess.run(
            ["icacls", str(config_path), "/grant", f"{username}:(F)"],
            capture_output=True, timeout=10,
        )
        logger.info(f"Permessi config.yaml ristretti a: {username}")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning("icacls non disponibile: permessi config.yaml non ristretti.")


# ---------------------------------------------------------------------------
# Argomenti CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parsa gli argomenti da riga di comando."""
    parser = argparse.ArgumentParser(
        prog="ryusync",
        description="RyuSync — Backup sicuro dei dati Ryujinx",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempi:
  python ryusync.py                            Avvia la CLI interattiva
  python ryusync.py --dry-run                  Mostra cosa farebbe senza eseguire
  python ryusync.py --mode=incremental --silent  Backup automatico (Task Scheduler)
  python ryusync.py --unschedule               Rimuovi il task pianificato
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["interactive", "incremental"],
        default="interactive",
        help="Modalità di esecuzione (default: interactive)",
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Nessun menu interattivo (usa config.yaml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra le azioni senza eseguirle",
    )
    parser.add_argument(
        "--unschedule",
        action="store_true",
        help="Rimuovi il task pianificato da Windows Task Scheduler",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"RyuSync v{VERSION}",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Verifica dipendenze
# ---------------------------------------------------------------------------

def check_dependencies() -> bool:
    """Verifica che tutte le dipendenze critiche siano disponibili."""
    ok = True

    # Verifica rclone
    if not backup_engine.check_rclone():
        console.print(
            "[yellow]⚠️  rclone non trovato nel PATH.[/yellow]\n"
            "[dim]Il backup cloud non sarà disponibile. "
            "Scarica rclone da: https://rclone.org/downloads/[/dim]"
        )
        # Non blocca: si può fare backup locale senza rclone

    return ok


def guide_rclone_setup() -> Optional[str]:
    """
    Guida l'utente nella configurazione di rclone se non è configurato.
    Restituisce il remote selezionato, o None.
    """
    remotes = backup_engine.list_rclone_remotes()

    if remotes:
        console.print(f"\n[green]✓ rclone configurato. Remote disponibili:[/green]")
        for r in remotes:
            console.print(f"  • [cyan]{r}[/cyan]")
        return questionary.select(
            "Seleziona il remote da usare:",
            choices=remotes + ["➕ Configura nuovo remote"],
        ).ask()

    # Nessun remote configurato
    console.print(
        Panel(
            "[yellow]rclone non ha remote configurati.[/yellow]\n\n"
            "Per configurare Google Drive, esegui:\n"
            "  [cyan]rclone config[/cyan]\n\n"
            "Guida passo-passo:\n"
            "  1. [dim]Scegli 'n' (new remote)[/dim]\n"
            "  2. [dim]Nome: es. 'gdrive'[/dim]\n"
            "  3. [dim]Storage: 'drive' (Google Drive)[/dim]\n"
            "  4. [dim]Segui le istruzioni per l'autenticazione OAuth[/dim]\n\n"
            "Documentazione: [link=https://rclone.org/drive/]https://rclone.org/drive/[/link]",
            title="[bold]Configurazione rclone richiesta[/bold]",
            border_style="yellow",
        )
    )

    open_guide = questionary.confirm(
        "Vuoi aprire la documentazione rclone nel browser?",
        default=True,
    ).ask()

    if open_guide:
        import webbrowser
        webbrowser.open("https://rclone.org/docs/")

    run_config = questionary.confirm(
        "Vuoi eseguire 'rclone config' ora?",
        default=True,
    ).ask()

    if run_config:
        try:
            subprocess.run(["rclone", "config"], timeout=300)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            console.print("[red]❌ Impossibile avviare rclone config.[/red]")

    return None


# ---------------------------------------------------------------------------
# Selezione contenuti
# ---------------------------------------------------------------------------

def prompt_contents(current_config: dict) -> list[str]:
    """Chiede all'utente quali contenuti includere nel backup."""
    choices_map = {
        "💾 Salvataggi (bis/user/save/)": "saves",
        "👤 Dati Mii": "mii",
        "⚙️  Dati di sistema (bis/system/)": "system",
        "📋 Configurazione (Config.json)": "config",
        "🎮 Mod (mods/)": "mods",
        "💿 ROM/ISO (opzionale, avvisa se >5GB)": "roms",
        "🎨 Shader Cache (esclusa di default, pesante)": "shader_cache",
    }

    current_contents = current_config.get("contents", DEFAULT_CONFIG["contents"])

    # Pre-seleziona in base a config corrente
    defaults = [
        label for label, key in choices_map.items()
        if current_contents.get(key, False)
    ]

    selected = questionary.checkbox(
        "Seleziona i contenuti da includere:",
        choices=list(choices_map.keys()),
        default=defaults,
    ).ask()

    if selected is None:
        return []

    return [choices_map[label] for label in selected]


# ---------------------------------------------------------------------------
# Selezione destinazione
# ---------------------------------------------------------------------------

def prompt_destination(config: dict) -> tuple[str, str]:
    """
    Chiede all'utente la destinazione del backup.

    Returns:
        Tupla (destination_type, destination_path)
    """
    dest_choices = [
        "☁️  Google Drive (via rclone)",
        "☁️  OneDrive (via rclone)",
        "☁️  Mega (via rclone)",
        "💽 SSD/HDD locale (secondo drive Windows)",
        "🌐 Cartella di rete SMB",
    ]

    answer = questionary.select(
        "Dove vuoi salvare il backup?",
        choices=dest_choices,
    ).ask()

    if answer is None:
        return "", ""

    # Cloud via rclone
    if "rclone" in answer or "Drive" in answer or "OneDrive" in answer or "Mega" in answer:
        remote = guide_rclone_setup()
        if remote:
            remote = remote.rstrip(":")
            subfolder = questionary.text(
                f"Sottocartella su {remote} (es. RyuSync/PC1):",
                default="RyuSync",
            ).ask() or "RyuSync"

            dst_type = (
                "gdrive" if "Google" in answer
                else "onedrive" if "OneDrive" in answer
                else "mega"
            )
            return dst_type, f"{remote}:{subfolder}"
        return "", ""

    # Storage locale
    if "locale" in answer:
        path = questionary.text(
            "Percorso destinazione locale (es. D:\\RyuSync):",
            validate=lambda x: len(x.strip()) > 0 or "Inserisci un percorso.",
        ).ask()
        return "local", path.strip() if path else ""

    # SMB
    if "SMB" in answer:
        path = questionary.text(
            "Percorso SMB (es. \\\\server\\share\\RyuSync):",
            validate=lambda x: len(x.strip()) > 0 or "Inserisci un percorso.",
        ).ask()
        return "smb", path.strip() if path else ""

    return "", ""


# ---------------------------------------------------------------------------
# Notifiche desktop
# ---------------------------------------------------------------------------

def send_notification(title: str, message: str) -> None:
    """Invia una notifica desktop su Windows tramite plyer."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="RyuSync",
            timeout=10,
        )
    except Exception:
        # Notifica non critica: fallisce silenziosamente
        logger.debug("Notifica desktop non inviata (plyer non disponibile o errore).")


# ---------------------------------------------------------------------------
# Modalità interattiva
# ---------------------------------------------------------------------------

def run_interactive(config: dict, dry_run: bool = False) -> None:
    """
    Avvia il flusso interattivo completo: azione → contenuti → destinazione → backup.
    """
    # 1. Azione
    action = questionary.select(
        "Cosa vuoi fare?",
        choices=[
            "💾 [1] Backup (locale → cloud/storage)",
            "🔄 [2] Ripristino (cloud/storage → locale)",
            "↔️  [3] Sync bidirezionale (solo file mancanti/nuovi)",
        ],
    ).ask()

    if action is None:
        return

    action_key = "backup" if "[1]" in action else "restore" if "[2]" in action else "sync"

    # 2. Rilevamento Ryujinx
    os_name = "windows"  # v1.0: solo Windows
    ryujinx_paths = detector.detect_ryujinx_path(os_name)
    ryujinx_path = detector.select_ryujinx_path(ryujinx_paths)

    if not ryujinx_path:
        console.print("[red]❌ Nessuna cartella Ryujinx selezionata. Uscita.[/red]")
        return

    config["ryujinx_path"] = str(ryujinx_path)

    # Analizza struttura
    ryujinx_structure = detector.get_ryujinx_structure(ryujinx_path)
    detector.print_ryujinx_structure(ryujinx_path)

    # 3. Selezione contenuti
    contents = prompt_contents(config)
    if not contents:
        console.print("[yellow]Nessun contenuto selezionato. Uscita.[/yellow]")
        return

    # Aggiorna config
    for key in DEFAULT_CONFIG["contents"]:
        config["contents"][key] = key in contents

    # 4. Selezione destinazione
    if action_key in ("backup", "sync"):
        dst_type, dst_path = prompt_destination(config)
        if not dst_path:
            console.print("[yellow]Nessuna destinazione selezionata. Uscita.[/yellow]")
            return
        config["destination_type"] = dst_type
        config["destination_path"] = dst_path
    else:
        # Ripristino: la sorgente è la destinazione attuale
        dst_path = config.get("destination_path", "")
        if not dst_path:
            dst_path = questionary.text(
                "Percorso/remote sorgente per il ripristino:",
            ).ask() or ""

    # 5. Nome PC
    if not config.get("pc_name"):
        config["pc_name"] = questionary.text(
            "Nome identificativo di questo PC (es. PC-Gaming, Laptop):",
            default=socket.gethostname(),
        ).ask() or socket.gethostname()

    # 6. Esecuzione
    setup_logging_session(config)

    if action_key == "backup":
        result = backup_engine.backup_additive(
            src=ryujinx_path,
            dst=dst_path,
            contents=contents,
            ryujinx_structure=ryujinx_structure,
            pc_name=config["pc_name"],
            dry_run=dry_run,
            integrity_method=config.get("integrity_method", "mtime_size"),
            size_warning_gb=config.get("size_warning_threshold_gb", 5.0),
        )

        # Compressione opzionale
        if config.get("compress_before_upload") and not dry_run:
            zip_path = backup_engine.compress_backup(
                ryujinx_path,
                Path(config.get("log_dir", "logs")).parent / "backups",
                compression_level=config.get("compression_level", 6),
            )
            backup_engine.apply_retention(
                zip_path.parent,
                n=config.get("keep_versions", 3),
            )

        # Verifica integrità
        if result.copied and not dry_run:
            verify = questionary.confirm(
                "Vuoi verificare l'integrità dei file copiati?",
                default=True,
            ).ask()
            if verify:
                backup_engine.verify_backup_integrity(
                    src=ryujinx_path,
                    dst=dst_path,
                    ryujinx_structure=ryujinx_structure,
                    contents=contents,
                    method=config.get("integrity_method", "mtime_size"),
                )

        # Notifica
        if config.get("desktop_notifications") and result.has_changes and not dry_run:
            send_notification(
                "RyuSync — Backup completato",
                result.summary,
            )

        # Pianificazione (se backup riuscito)
        if result.copied and not dry_run:
            _offer_scheduling(config)

    elif action_key == "restore":
        backup_engine.restore(
            src=dst_path,
            dst=ryujinx_path,
            dry_run=dry_run,
            integrity_method=config.get("integrity_method", "mtime_size"),
        )

    elif action_key == "sync":
        # Sync bidirezionale: backup → poi controlla remoto per file più nuovi
        console.print("\n[bold cyan]↔️  Sync bidirezionale in due fasi...[/bold cyan]")
        console.print("[dim]Fase 1: Carica file locali mancanti/nuovi...[/dim]")
        result = backup_engine.backup_additive(
            src=ryujinx_path,
            dst=dst_path,
            contents=contents,
            ryujinx_structure=ryujinx_structure,
            pc_name=config["pc_name"],
            dry_run=dry_run,
            integrity_method=config.get("integrity_method", "mtime_size"),
            size_warning_gb=config.get("size_warning_threshold_gb", 5.0),
        )

        if config.get("desktop_notifications") and result.has_changes and not dry_run:
            send_notification("RyuSync — Sync completato", result.summary)

    # Salva config aggiornata
    save_config(config)


def _offer_scheduling(config: dict) -> None:
    """Propone di pianificare backup automatici dopo un backup manuale riuscito."""
    if scheduler.check_existing_task():
        modify = questionary.confirm(
            "Un task RyuSync è già pianificato. Vuoi modificare la pianificazione?",
            default=False,
        ).ask()
        if not modify:
            return

    want_schedule = questionary.confirm(
        "\n✅ Backup completato! Vuoi pianificare backup automatici?",
        default=True,
    ).ask()

    if not want_schedule:
        return

    freq, custom = scheduler.prompt_schedule_frequency()

    if freq != "none":
        cmd = scheduler.create_scheduled_task(
            os_name="windows",
            frequency=freq,
            custom=custom,
        )
        if cmd:
            config["schedule_frequency"] = freq
            if custom:
                config["schedule_custom_value"] = custom.get("value")
                config["schedule_custom_unit"] = custom.get("unit")


# ---------------------------------------------------------------------------
# Modalità incrementale silenziosa
# ---------------------------------------------------------------------------

def run_incremental_silent(config: dict, dry_run: bool = False) -> None:
    """
    Modalità automatica per Task Scheduler.
    Non mostra menu interattivi. Usa config.yaml.
    Trasferisce solo file mancanti/nuovi. Non risolve conflitti automaticamente.
    Se nulla di nuovo → termina silenziosamente.
    """
    # Setup logging su file (senza output console ricco)
    log_path = LOG_DIR / f"backup_log_{backup_engine.BackupResult().timestamp}.txt"
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8")],
    )

    # Controllo sicurezza (solo log, nessun output interattivo)
    security.warn_if_unencrypted(silent=True)

    ryujinx_path_str = config.get("ryujinx_path", "")
    if not ryujinx_path_str:
        logger.error("[SILENT] ryujinx_path non configurato in config.yaml")
        sys.exit(1)

    ryujinx_path = Path(ryujinx_path_str)
    if not detector.validate_ryujinx_dir(ryujinx_path):
        logger.error(f"[SILENT] Cartella Ryujinx non valida: {ryujinx_path}")
        sys.exit(1)

    dst_path = config.get("destination_path", "")
    if not dst_path:
        logger.error("[SILENT] destination_path non configurato in config.yaml")
        sys.exit(1)

    contents_cfg = config.get("contents", DEFAULT_CONFIG["contents"])
    contents = [k for k, v in contents_cfg.items() if v]

    if not contents:
        logger.info("[SILENT] Nessun contenuto selezionato. Uscita.")
        sys.exit(0)

    ryujinx_structure = detector.get_ryujinx_structure(ryujinx_path)
    pc_name = config.get("pc_name", socket.gethostname())

    logger.info(f"[SILENT] Avvio backup incrementale | PC: {pc_name} | Dst: {dst_path}")

    result = backup_engine.backup_additive(
        src=ryujinx_path,
        dst=dst_path,
        contents=contents,
        ryujinx_structure=ryujinx_structure,
        pc_name=pc_name,
        dry_run=dry_run,
        integrity_method=config.get("integrity_method", "mtime_size"),
        size_warning_gb=999.0,  # No warning in modalità silent
        log_path=log_path,
    )

    # Nessuna notifica se nulla di nuovo
    if not result.has_changes:
        logger.info("[SILENT] Nessuna modifica rilevata. Uscita silenziosa.")
        sys.exit(0)

    logger.info(f"[SILENT] Completato: {result.summary}")

    # Notifica solo se ci sono modifiche e notifiche abilitate
    if config.get("desktop_notifications") and not dry_run:
        send_notification(
            "RyuSync — Backup automatico completato",
            result.summary,
        )

    sys.exit(0)


# ---------------------------------------------------------------------------
# Setup logging di sessione
# ---------------------------------------------------------------------------

def setup_logging_session(config: dict) -> Path:
    """Configura logging per la sessione interattiva."""
    from datetime import datetime
    log_dir = Path(config.get("log_dir", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"backup_log_{timestamp}.txt"
    backup_engine.setup_logging(log_path)
    return log_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point principale."""
    args = parse_args()

    # --- Rimozione task pianificato ---
    if args.unschedule:
        console.print("[bold]🗑 Rimozione task pianificato RyuSync...[/bold]")
        success = scheduler.remove_scheduled_task("windows")
        sys.exit(0 if success else 1)

    # Carica configurazione
    config = load_config()

    # Override dry-run da argomento
    if args.dry_run:
        config["dry_run"] = True
    dry_run = config.get("dry_run", False)

    # --- Modalità incrementale silenziosa ---
    if args.mode == "incremental" or args.silent:
        run_incremental_silent(config, dry_run=dry_run)
        return

    # --- Modalità interattiva ---

    # Banner
    console.print(f"[bold cyan]{BANNER}[/bold cyan]")
    console.print(
        Panel(
            f"[bold]v{VERSION}[/bold] — Backup sicuro dei dati Ryujinx\n"
            f"[dim]Piattaforma: Windows v1.0 | Python {sys.version.split()[0]}[/dim]",
            border_style="cyan",
            expand=False,
        )
    )

    if dry_run:
        console.print(
            Panel(
                "[bold yellow]MODALITÀ DRY-RUN ATTIVA[/bold yellow]\n"
                "[dim]Verranno mostrate le azioni senza eseguirle.[/dim]",
                border_style="yellow",
                expand=False,
            )
        )

    # Verifica dipendenze
    console.print(Rule("[dim]Verifica dipendenze[/dim]"))
    check_dependencies()

    # Controllo sicurezza credenziali rclone
    security.warn_if_unencrypted(silent=False)

    # Avvia flusso interattivo
    console.print(Rule("[dim]Avvio[/dim]"))
    run_interactive(config, dry_run=dry_run)

    console.print(
        f"\n[bold green]✅ RyuSync completato.[/bold green]\n"
        f"[dim]Log salvato in: {config.get('log_dir', 'logs')}/[/dim]"
    )


if __name__ == "__main__":
    main()
