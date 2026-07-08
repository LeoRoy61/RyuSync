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
# Output interattivo
# ---------------------------------------------------------------------------

def print_security_check() -> dict:
    """
    Esegue e stampa il risultato del controllo di sicurezza rclone.

    Returns:
        Il dict restituito da check_rclone_security().
    """
    result = check_rclone_security()

    if not result["found"]:
        console.print("[dim]rclone.conf non trovato — nessun controllo sicurezza eseguito.[/dim]")
        return result

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

    return result


def warn_if_unencrypted(silent: bool = False) -> bool:
    """
    Avvisa l'utente se rclone.conf non è cifrato.
    In modalità silent, logga solo senza stampare.

    Args:
        silent: Se True, non stampa output (solo logging).

    Returns:
        True se tutto è ok (cifrato o non trovato), False se a rischio.
    """
    import logging
    log = logging.getLogger("ryusync.security")

    result = check_rclone_security()

    if result["risk_level"] == "critical":
        if not silent:
            print_security_check()
        else:
            log.warning(
                f"SICUREZZA: rclone.conf non cifrato ({result['path']}). "
                "Esegui 'rclone config' e imposta una password di cifratura."
            )
        return False

    return True
