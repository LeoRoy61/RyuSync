"""
security.py — RyuSync v1.0

Controlli di sicurezza per le credenziali rclone e la configurazione RyuSync.

rclone.conf contiene token OAuth e chiavi API in chiaro o leggermente offuscati.
Questo modulo aiuta l'utente a rilevare configurazioni insicure e a proteggerle.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel

console = Console()


# ---------------------------------------------------------------------------
# Percorsi standard di rclone.conf per OS
# ---------------------------------------------------------------------------

def get_rclone_conf_path() -> Optional[Path]:
    """
    Restituisce il percorso standard di rclone.conf per il SO corrente.

    Returns:
        Path a rclone.conf se trovato, None altrimenti.
    """
    # Windows: %APPDATA%\rclone\rclone.conf
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidate = Path(appdata) / "rclone" / "rclone.conf"
        if candidate.exists():
            return candidate

    # TODO (v2.0 — Linux): ~/.config/rclone/rclone.conf
    # xdg_config = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    # candidate = Path(xdg_config) / "rclone" / "rclone.conf"
    # if candidate.exists(): return candidate

    # TODO (v2.0 — macOS): ~/Library/Application Support/rclone/rclone.conf
    # candidate = Path.home() / "Library" / "Application Support" / "rclone" / "rclone.conf"
    # if candidate.exists(): return candidate

    # Fallback: cerca tramite `rclone config file`
    try:
        proc = subprocess.run(
            ["rclone", "config", "file"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if proc.returncode == 0:
            for line in proc.stdout.splitlines():
                line = line.strip()
                if line and Path(line).exists():
                    return Path(line)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


# ---------------------------------------------------------------------------
# Verifica cifratura rclone.conf
# ---------------------------------------------------------------------------

def is_rclone_conf_encrypted() -> Optional[bool]:
    """
    Verifica se rclone.conf è cifrato con password (rclone config password).

    rclone cifra il file con AES-256 quando viene impostata una password.
    Un file cifrato inizia con una riga "# Encrypted rclone configuration File"
    seguita da dati cifrati, non da sezioni leggibili come [gdrive].

    Returns:
        True  → file cifrato
        False → file NON cifrato (credenziali in chiaro)
        None  → rclone.conf non trovato
    """
    conf_path = get_rclone_conf_path()
    if conf_path is None:
        return None

    try:
        with open(conf_path, "r", encoding="utf-8", errors="replace") as f:
            first_lines = [f.readline() for _ in range(5)]

        content_start = "".join(first_lines)

        # Indicatori di file cifrato
        if "# Encrypted rclone configuration File" in content_start:
            return True

        # Indicatori di file in chiaro (sezioni rclone standard)
        if any(marker in content_start for marker in ["[", "type =", "token =", "client_id ="]):
            return False

        # File vuoto o formato sconosciuto
        return None

    except (OSError, PermissionError):
        return None


def check_rclone_security() -> dict:
    """
    Esegue un controllo di sicurezza completo su rclone.conf.

    Returns:
        Dict con:
            'found': bool — rclone.conf trovato
            'encrypted': bool|None — True=cifrato, False=in chiaro, None=sconosciuto
            'path': Path|None — percorso del file
            'risk_level': 'ok'|'warning'|'critical'|'unknown'
    """
    conf_path = get_rclone_conf_path()
    encrypted = is_rclone_conf_encrypted()

    if conf_path is None:
        return {
            "found": False,
            "encrypted": None,
            "path": None,
            "risk_level": "unknown",
        }

    if encrypted is True:
        risk_level = "ok"
    elif encrypted is False:
        risk_level = "critical"
    else:
        risk_level = "warning"

    return {
        "found": True,
        "encrypted": encrypted,
        "path": conf_path,
        "risk_level": risk_level,
    }


# ---------------------------------------------------------------------------
# Output interattivo e controlli di esposizione dati
# ---------------------------------------------------------------------------

def _are_notifications_enabled() -> bool:
    """Verifica se le notifiche desktop sono abilitate in config.yaml."""
    try:
        config_path = Path(__file__).parent / "config.yaml"
        if config_path.exists():
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
                return bool(cfg.get("desktop_notifications", True))
    except Exception:
        pass
    return True


def _send_desktop_notification(title: str, message: str) -> None:
    """Invia una notifica desktop se abilitata nelle impostazioni."""
    if not _are_notifications_enabled():
        return
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="RyuSync",
            timeout=10,
        )
    except Exception:
        pass


def check_sensitive_data_exposure(base_dir: Optional[Path] = None) -> list[str]:
    """
    Scansiona ryusync_state.json e i file di log in logs/ alla ricerca di informazioni
    sensibili locali (come username, hostname o percorsi assoluti del profilo utente).

    Returns:
        Lista di messaggi di avviso per ogni file che contiene dati sensibili.
    """
    import socket
    import re
    warnings = []
    if base_dir is None:
        base_dir = Path(__file__).parent

    # File da controllare
    files_to_check: list[Path] = []

    state_file = base_dir / "ryusync_state.json"
    if state_file.exists():
        files_to_check.append(state_file)

    logs_dir = base_dir / "logs"
    if logs_dir.exists() and logs_dir.is_dir():
        try:
            for f in logs_dir.glob("*.txt"):
                files_to_check.append(f)
            for f in logs_dir.glob("*.log"):
                files_to_check.append(f)
        except Exception:
            pass

    # Prepara pattern di dati sensibili
    patterns = []
    username = os.environ.get("USERNAME") or os.environ.get("USER")
    if username and len(username) > 2:
        patterns.append(re.escape(username))

    compname = os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or socket.gethostname()
    if compname and len(compname) > 2:
        patterns.append(re.escape(compname))

    try:
        home_str = str(Path.home())
        if home_str and len(home_str) > 5:
            patterns.append(re.escape(home_str))
            patterns.append(re.escape(home_str.replace("/", "\\")))
            patterns.append(re.escape(home_str.replace("\\", "/")))
    except Exception:
        pass

    if not patterns:
        return warnings

    # Regex per corrispondenza dei pattern
    pattern_regex = re.compile("|".join(patterns), re.IGNORECASE)
    # Regex per percorsi Windows/POSIX tipici sotto Users/home (esclude parentesi o apici per evitare falsi positivi)
    path_regex = re.compile(r"([a-zA-Z]:[\\/]+[Uu]sers[\\/]+[^\\/\s\n\(\)\{\}\[\]\:\;\'\"]+|[\\/]+[Uu]sers[\\/]+[^\\/\s\n\(\)\{\}\[\]\:\;\'\"]+)")

    for fp in files_to_check:
        try:
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            has_sensitive = False
            reasons = []

            # Verifica presenza dei pattern sensibili
            if pattern_regex.search(content):
                has_sensitive = True
                reasons.append("nome utente o computer locale")
            # Verifica presenza di pattern di percorsi assoluti sensibili
            elif path_regex.search(content):
                has_sensitive = True
                reasons.append("percorso assoluto del profilo utente")

            if has_sensitive:
                try:
                    rel_path = fp.relative_to(base_dir)
                except ValueError:
                    rel_path = fp.name
                warnings.append(f"Il file '{rel_path}' contiene informazioni sensibili ({', '.join(reasons)}).")
        except Exception:
            pass

    return warnings


def print_security_check(base_dir: Optional[Path] = None) -> dict:
    """
    Esegue e stampa il risultato del controllo di sicurezza rclone e dati sensibili.

    Returns:
        Il dict restituito da check_rclone_security().
    """
    result = check_rclone_security()

    if not result["found"]:
        console.print("[dim]rclone.conf non trovato — nessun controllo sicurezza eseguito.[/dim]")
    else:
        conf_path = result["path"]
        risk = result["risk_level"]

        if risk == "ok":
            console.print(
                f"[bold green]🔒 rclone.conf cifrato (AES-256)[/bold green]\n"
                f"[dim]   {conf_path}[/dim]"
            )

        elif risk == "critical":
            console.print(
                Panel(
                    f"[bold red]⚠️  ATTENZIONE: rclone.conf NON è cifrato![/bold red]\n\n"
                    f"Il file [bold]{conf_path}[/bold] contiene token OAuth e chiavi API\n"
                    f"in formato leggibile. Chiunque acceda a questo file può usare\n"
                    f"i tuoi account cloud (Google Drive, OneDrive, Mega).\n\n"
                    f"[bold yellow]Soluzione consigliata:[/bold yellow]\n"
                    f"  [cyan]rclone config[/cyan]\n"
                    f"  → Seleziona 's' (Set configuration password)\n"
                    f"  → Inserisci una password sicura\n"
                    f"  → Il file verrà cifrato con AES-256\n\n"
                    f"[dim]Nota: dopo aver impostato la password, rclone la chiederà\n"
                    f"ad ogni esecuzione. Puoi impostarla anche via env:\n"
                    f"  set RCLONE_CONFIG_PASS=tuapassword[/dim]",
                    title="[bold red]Sicurezza Credenziali rclone[/bold red]",
                    border_style="red",
                )
            )

        else:  # warning / unknown
            console.print(
                f"[yellow]⚠️  Stato cifratura rclone.conf non determinabile.[/yellow]\n"
                f"[dim]   {conf_path}[/dim]\n"
                f"[dim]   Verifica manualmente con: rclone config[/dim]"
            )

    # Controlla ed espone avvisi su dati sensibili
    sens_warnings = check_sensitive_data_exposure(base_dir=base_dir)
    if sens_warnings:
        console.print(
            Panel(
                "[bold yellow]⚠️  AVVISO: Informazioni sensibili rilevate nei log o nello stato[/bold yellow]\n\n" +
                "\n".join(f"  • [yellow]{w}[/yellow]" for w in sens_warnings) + "\n\n"
                "[dim]Se questi file vengono sincronizzati sul cloud insieme ad un file rclone.conf\n"
                "non cifrato, potrebbero esporre dettagli sul tuo ambiente locale.[/dim]",
                title="[bold yellow]Analisi Esposizione Dati[/bold yellow]",
                border_style="yellow",
            )
        )

    return result


def warn_if_unencrypted(silent: bool = False, base_dir: Optional[Path] = None) -> bool:
    """
    Avvisa l'utente se rclone.conf non è cifrato o se ci sono esposizioni di dati.
    In modalità silent, logga ed invia notifiche desktop se abilitate.

    Args:
        silent: Se True, non stampa output su console (solo logging e desktop notification).
        base_dir: Percorso opzionale in cui cercare logs/ e ryusync_state.json (usato nei test).

    Returns:
        True se rclone.conf è cifrato o non trovato (nessun rischio critico), False se a rischio.
    """
    import logging
    log = logging.getLogger("ryusync.security")

    result = check_rclone_security()
    sens_warnings = check_sensitive_data_exposure(base_dir=base_dir)

    has_risk = False

    # 1. Controllo rclone.conf
    if result["risk_level"] == "critical":
        has_risk = True
        if not silent:
            print_security_check(base_dir=base_dir)
        else:
            log.warning(
                f"SICUREZZA: rclone.conf non cifrato ({result['path']}). "
                "Esegui 'rclone config' e imposta una password di cifratura."
            )
            _send_desktop_notification(
                "RyuSync Security Warning",
                "rclone.conf is not encrypted! Run 'rclone config' to set a password."
            )

    # 2. Controllo dati sensibili esposti
    if sens_warnings:
        if silent:
            for w in sens_warnings:
                log.warning(f"SICUREZZA (Esposizione dati): {w}")
            # Se combinato con rclone.conf critico, manda notifica dedicata
            if result["risk_level"] == "critical":
                _send_desktop_notification(
                    "RyuSync Security Warning",
                    "Sensitive paths/info exposed in logs while rclone.conf is unencrypted!"
                )
        else:
            # Se non silent, ma rclone.conf non era critical,
            # print_security_check non è stato chiamato sopra. Chiamiamolo ora.
            if result["risk_level"] != "critical":
                print_security_check(base_dir=base_dir)

    return not has_risk


