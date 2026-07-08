"""
scheduler.py — RyuSync v1.0

Gestione delle attività pianificate per l'esecuzione automatica di RyuSync.
Versione corrente: supporto SOLO Windows tramite schtasks.

Architettura estendibile: la funzione create_scheduled_task(os_name, frequency)
accetta un parametro os_name per consentire il supporto multipiattaforma
in versioni future senza modificare la logica core.

TODO (v2.0): aggiungere supporto Linux (systemd timer / crontab) e macOS (launchd).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import questionary
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()

# Nome del task pianificato (univoco in Windows Task Scheduler)
TASK_NAME = "RyuSync_AutoBackup"

# Nome del task secondario per il rilevamento chiusura Ryujinx
TASK_NAME_RYUJINX_WATCHER = "RyuSync_RyujinxCloseWatcher"

# Intervallo (minuti) del watcher per la chiusura di Ryujinx
RYUJINX_WATCHER_INTERVAL_MIN = 5

# File di stato per il watcher della chiusura di Ryujinx
STATE_FILE = Path(__file__).parent / "ryusync_state.json"


# ---------------------------------------------------------------------------
# Frequenze disponibili
# ---------------------------------------------------------------------------

FREQUENCY_CHOICES = [
    {"label": "Ogni ora",            "key": "hourly"},
    {"label": "Ogni 6 ore",          "key": "6h"},
    {"label": "Una volta al giorno", "key": "daily"},
    {"label": "Ogni 3 giorni",       "key": "3days"},
    {"label": "Una volta a settimana","key": "weekly"},
    {"label": "Una volta al mese",   "key": "monthly"},
    {"label": "All'avvio del PC",    "key": "boot"},
    {"label": "Alla chiusura di Ryujinx (via psutil)", "key": "ryujinx_close"},
    {"label": "Personalizzato (inserisci tu la cadenza)", "key": "custom"},
    {"label": "Non pianificare — farò i backup manualmente", "key": "none"},
]


# ---------------------------------------------------------------------------
# Funzione principale — entry point per il pianificatore multipiattaforma
# ---------------------------------------------------------------------------

def create_scheduled_task(
    os_name: str,
    frequency: str,
    custom: Optional[dict] = None,
    script_path: Optional[Path] = None,
    python_exe: Optional[str] = None,
) -> Optional[str]:
    """
    Crea un task pianificato per l'esecuzione automatica di RyuSync.

    Args:
        os_name:     Identificatore SO — 'windows' | 'linux' (TODO) | 'darwin' (TODO)
        frequency:   Chiave frequenza — vedi FREQUENCY_CHOICES
        custom:      Dict con 'value' (int) e 'unit' (str) per cadenza personalizzata
        script_path: Path assoluto di ryusync.py (default: rilevato automaticamente)
        python_exe:  Path assoluto di python.exe (default: sys.executable)

    Returns:
        Il comando schtasks generato (stringa), o None se l'utente annulla.

    Raises:
        ValueError: Se os_name non è supportato.
    """
    if os_name == "windows":
        return _create_task_windows(frequency, custom, script_path, python_exe)

    # TODO (v2.0 — Linux): aggiungere supporto per Linux
    # Implementazione suggerita con systemd user timer:
    #
    #   def _create_task_linux(frequency, custom, script_path, python_exe):
    #       unit_name = "ryusync-autobackup"
    #       service_content = f"""[Unit]
    #   Description=RyuSync Auto Backup
    #
    #   [Service]
    #   ExecStart={python_exe} {script_path} --mode=incremental --silent
    #   """
    #       timer_content = f"""[Unit]
    #   Description=RyuSync Auto Backup Timer
    #
    #   [Timer]
    #   OnCalendar={_frequency_to_systemd_oncalendar(frequency, custom)}
    #   Persistent=true
    #
    #   [Install]
    #   WantedBy=timers.target
    #   """
    #       # Scrive ~/.config/systemd/user/{unit_name}.service e .timer
    #       # Poi esegue: systemctl --user enable --now {unit_name}.timer
    #       ...
    #
    # Alternativa con crontab (più semplice, meno precisa):
    #   cron_expr = _frequency_to_cron(frequency, custom)
    #   cmd = f"{python_exe} {script_path} --mode=incremental --silent"
    #   # Legge crontab corrente, aggiunge riga, riscrive con `crontab -`
    #   ...
    elif os_name == "linux":
        raise ValueError(
            "Pianificazione su Linux non ancora implementata. "
            "Pianificata per RyuSync v2.0 (systemd timer / crontab)."
        )

    # TODO (v2.0 — macOS): aggiungere supporto per macOS
    # Implementazione suggerita con launchd plist:
    #
    #   def _create_task_macos(frequency, custom, script_path, python_exe):
    #       plist_name = "com.ryusync.autobackup"
    #       plist_path = Path.home() / "Library/LaunchAgents" / f"{plist_name}.plist"
    #       interval_seconds = _frequency_to_seconds(frequency, custom)
    #       plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
    #   ...
    #   <key>StartInterval</key><integer>{interval_seconds}</integer>
    #   ...
    #   """
    #       # Scrive il plist e poi: launchctl load {plist_path}
    #       ...
    elif os_name == "darwin":
        raise ValueError(
            "Pianificazione su macOS non ancora implementata. "
            "Pianificata per RyuSync v2.0 (launchd)."
        )

    else:
        raise ValueError(
            f"Sistema operativo '{os_name}' non supportato per la pianificazione. "
            f"Valori validi: 'windows' (altri in arrivo in v2.0)."
        )


def remove_scheduled_task(os_name: str) -> bool:
    """
    Rimuove il task pianificato di RyuSync.

    Args:
        os_name: 'windows' | 'linux' (TODO) | 'darwin' (TODO)

    Returns:
        True se rimosso con successo.
    """
    if os_name == "windows":
        return _remove_task_windows()

    # TODO (v2.0 — Linux): rimuovere timer systemd o crontab entry
    # systemctl --user disable --now ryusync-autobackup.timer
    # rm ~/.config/systemd/user/ryusync-autobackup.{service,timer}
    # systemctl --user daemon-reload
    elif os_name == "linux":
        raise ValueError("Rimozione task Linux non ancora implementata.")

    # TODO (v2.0 — macOS): rimuovere launchd plist
    # launchctl unload ~/Library/LaunchAgents/com.ryusync.autobackup.plist
    # rm ~/Library/LaunchAgents/com.ryusync.autobackup.plist
    elif os_name == "darwin":
        raise ValueError("Rimozione task macOS non ancora implementata.")

    else:
        raise ValueError(f"SO '{os_name}' non supportato.")


# ---------------------------------------------------------------------------
# Implementazione Windows — schtasks
# ---------------------------------------------------------------------------

def _create_task_windows(
    frequency: str,
    custom: Optional[dict],
    script_path: Optional[Path],
    python_exe: Optional[str],
) -> Optional[str]:
    """
    Crea un task pianificato Windows tramite schtasks.
    Mostra il comando all'utente prima di eseguirlo e chiede conferma.
    """
    # Risolvi path
    if script_path is None:
        script_path = Path(__file__).parent / "ryusync.py"
    if python_exe is None:
        python_exe = sys.executable

    # Comando da eseguire nel task
    task_cmd = f'"{python_exe}" "{script_path}" --mode=incremental --silent'

    if frequency == "ryujinx_close":
        return _create_ryujinx_watcher_windows(task_cmd, python_exe, script_path)

    if frequency == "none":
        console.print("[dim]Nessuna pianificazione configurata. I backup saranno manuali.[/dim]")
        return None

    # Costruisci parametri schtasks
    sc_params = _frequency_to_schtasks_params(frequency, custom)
    if sc_params is None:
        return None

    # Costruisci il comando schtasks completo
    schtasks_cmd = [
        "schtasks", "/create",
        "/tn", TASK_NAME,
        "/tr", task_cmd,
        "/sc", sc_params["sc"],
        "/f",  # Forza (sovrascrive se esiste già)
    ]

    # Aggiungi parametri opzionali in base alla frequenza
    if "mo" in sc_params:
        schtasks_cmd.extend(["/mo", str(sc_params["mo"])])
    if "st" in sc_params:
        schtasks_cmd.extend(["/st", sc_params["st"]])
    if "d" in sc_params:
        schtasks_cmd.extend(["/d", sc_params["d"]])
    if "m" in sc_params:
        schtasks_cmd.extend(["/m", sc_params["m"]])

    # Mostra il comando all'utente per revisione
    cmd_str = " ".join(f'"{p}"' if " " in str(p) else str(p) for p in schtasks_cmd)

    console.print(
        Panel(
            Syntax(cmd_str, "bash", theme="monokai", word_wrap=True),
            title="[bold]Comando schtasks che verrà eseguito[/bold]",
            border_style="yellow",
        )
    )
    console.print(
        f"\n[dim]Task name: {TASK_NAME}[/dim]\n"
        f"[dim]Frequenza: {_frequency_label(frequency, custom)}[/dim]\n"
        f"[dim]Comando:   {task_cmd}[/dim]"
    )

    confirm = questionary.confirm(
        "Vuoi creare questo task pianificato?",
        default=True,
    ).ask()

    if not confirm:
        console.print("[dim]Pianificazione annullata.[/dim]")
        return None

    # Esegui schtasks
    try:
        proc = subprocess.run(
            schtasks_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            console.print(
                f"\n[bold green]✅ Task pianificato creato con successo![/bold green]\n"
                f"[dim]Nome task: {TASK_NAME}[/dim]\n"
                f"[dim]Frequenza: {_frequency_label(frequency, custom)}[/dim]\n"
                f"[dim]Per verificare: Task Scheduler → RyuSync_AutoBackup[/dim]"
            )
            return cmd_str
        else:
            console.print(f"[bold red]❌ Errore schtasks:[/bold red]\n{proc.stderr.strip()}")
            if "Access is denied" in proc.stderr:
                console.print(
                    "[yellow]Suggerimento: prova ad eseguire il terminale come Amministratore.[/yellow]"
                )
            return None
    except FileNotFoundError:
        console.print("[red]❌ schtasks non trovato. Assicurati di essere su Windows.[/red]")
        return None
    except subprocess.TimeoutExpired:
        console.print("[red]❌ Timeout durante la creazione del task.[/red]")
        return None


def _frequency_to_schtasks_params(
    frequency: str,
    custom: Optional[dict],
) -> Optional[dict]:
    """
    Converte una chiave frequenza nei parametri schtasks (/sc, /mo, /st, ecc.).

    Returns:
        Dict con i parametri schtasks, o None se frequenza non valida.
    """
    # Orario di default per task giornalieri/settimanali/mensili (3:00 di notte)
    default_time = "03:00"

    mapping = {
        "hourly": {"sc": "HOURLY",  "mo": 1},
        "6h":     {"sc": "HOURLY",  "mo": 6},
        "daily":  {"sc": "DAILY",   "mo": 1,  "st": default_time},
        "3days":  {"sc": "DAILY",   "mo": 3,  "st": default_time},
        "weekly": {"sc": "WEEKLY",  "mo": 1,  "st": default_time, "d": "MON"},
        "monthly":{"sc": "MONTHLY", "mo": 1,  "st": default_time, "m": "1"},
        "boot":   {"sc": "ONSTART"},
    }

    if frequency in mapping:
        return mapping[frequency]

    if frequency == "custom" and custom:
        unit = custom.get("unit", "days").lower()
        value = int(custom.get("value", 1))

        if unit in ("minutes", "minuti", "minute"):
            return {"sc": "MINUTE", "mo": value}
        elif unit in ("hours", "ore", "hour"):
            return {"sc": "HOURLY", "mo": value}
        elif unit in ("days", "giorni", "day"):
            return {"sc": "DAILY", "mo": value, "st": default_time}
        elif unit in ("weeks", "settimane", "week"):
            return {"sc": "WEEKLY", "mo": value, "st": default_time, "d": "MON"}
        elif unit in ("months", "mesi", "month"):
            return {"sc": "MONTHLY", "mo": value, "st": default_time, "m": "1"}
        else:
            console.print(f"[red]Unità '{unit}' non riconosciuta. Usa: minuti/ore/giorni/settimane/mesi[/red]")
            return None

    console.print(f"[red]Frequenza '{frequency}' non riconosciuta.[/red]")
    return None


def _create_ryujinx_watcher_windows(
    main_cmd: str,
    python_exe: str,
    script_path: Path,
) -> Optional[str]:
    """
    Crea un task pianificato leggero che ogni N minuti controlla
    se Ryujinx.exe è appena terminato (tramite psutil + file di stato).

    Il watcher legge/scrive ryusync_state.json per persistere lo stato
    del processo tra un'esecuzione e l'altra.
    """
    # Script watcher inline (viene passato come comando)
    watcher_script = script_path.parent / "ryujinx_watcher.py"

    # Crea lo script watcher
    watcher_content = '''"""
ryujinx_watcher.py — RyuSync v1.0
Script leggero eseguito dal Task Scheduler ogni pochi minuti.
Controlla se Ryujinx.exe è terminato dall'ultimo controllo.
Se sì, avvia ryusync.py --mode=incremental --silent.

Il file di stato ryusync_state.json persiste lo stato tra le esecuzioni
(non in RAM, per compatibilità con il paradigma "lancia e termina").
"""
import json
import subprocess
import sys
from pathlib import Path

import psutil

STATE_FILE = Path(__file__).parent / "ryusync_state.json"
RYUSYNC_SCRIPT = Path(__file__).parent / "ryusync.py"


def load_state() -> dict:
    """Carica lo stato dal file JSON, gestendo corruzione."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            # File corrotto: ricrea
            pass
    return {"ryujinx_was_running": False}


def save_state(state: dict) -> None:
    """Salva lo stato nel file JSON."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        print(f"[WATCHER] Impossibile salvare lo stato: {e}")


def is_ryujinx_running() -> bool:
    """Controlla se Ryujinx.exe è in esecuzione tramite psutil."""
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info["name"] and "ryujinx" in proc.info["name"].lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return False


def main():
    state = load_state()
    was_running = state.get("ryujinx_was_running", False)
    now_running = is_ryujinx_running()

    if was_running and not now_running:
        # Ryujinx è appena terminato → avvia backup
        print("[WATCHER] Ryujinx terminato — avvio backup incrementale...")
        try:
            subprocess.Popen(
                [sys.executable, str(RYUSYNC_SCRIPT), "--mode=incremental", "--silent"],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception as e:
            print(f"[WATCHER] Errore avvio backup: {e}")

    # Aggiorna lo stato
    save_state({"ryujinx_was_running": now_running})


if __name__ == "__main__":
    main()
'''

    with open(watcher_script, "w", encoding="utf-8") as f:
        f.write(watcher_content)

    watcher_cmd = f'"{python_exe}" "{watcher_script}"'

    schtasks_cmd = [
        "schtasks", "/create",
        "/tn", TASK_NAME_RYUJINX_WATCHER,
        "/tr", watcher_cmd,
        "/sc", "MINUTE",
        "/mo", str(RYUJINX_WATCHER_INTERVAL_MIN),
        "/f",
    ]

    cmd_str = " ".join(str(p) for p in schtasks_cmd)

    console.print(
        Panel(
            Syntax(cmd_str, "bash", theme="monokai", word_wrap=True),
            title="[bold]Task Watcher Chiusura Ryujinx[/bold]",
            border_style="yellow",
        )
    )
    console.print(
        f"\n[dim]Il watcher si avvia ogni {RYUJINX_WATCHER_INTERVAL_MIN} minuti.[/dim]\n"
        f"[dim]Se rileva che Ryujinx.exe è terminato, avvia il backup automaticamente.[/dim]\n"
        f"[dim]Lo stato è persistito in: {STATE_FILE}[/dim]"
    )

    confirm = questionary.confirm(
        "Vuoi creare il task watcher per la chiusura di Ryujinx?",
        default=True,
    ).ask()

    if not confirm:
        return None

    try:
        proc = subprocess.run(schtasks_cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0:
            console.print(f"[bold green]✅ Task watcher creato: {TASK_NAME_RYUJINX_WATCHER}[/bold green]")
            return cmd_str
        else:
            console.print(f"[red]❌ Errore: {proc.stderr.strip()}[/red]")
            return None
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        console.print(f"[red]❌ {e}[/red]")
        return None


def _remove_task_windows() -> bool:
    """
    Rimuove i task pianificati RyuSync da Windows Task Scheduler.
    """
    success = True

    for task_name in [TASK_NAME, TASK_NAME_RYUJINX_WATCHER]:
        cmd = ["schtasks", "/delete", "/tn", task_name, "/f"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if proc.returncode == 0:
                console.print(f"[green]✓ Task rimosso: {task_name}[/green]")
            else:
                # Il task potrebbe non esistere
                if "cannot find" in proc.stderr.lower() or "non esiste" in proc.stderr.lower():
                    console.print(f"[dim]Task non trovato (già rimosso?): {task_name}[/dim]")
                else:
                    console.print(f"[red]❌ Errore rimozione {task_name}: {proc.stderr.strip()}[/red]")
                    success = False
        except FileNotFoundError:
            console.print("[red]❌ schtasks non trovato.[/red]")
            return False
        except subprocess.TimeoutExpired:
            console.print(f"[red]❌ Timeout rimozione {task_name}.[/red]")
            success = False

    # Rimuovi anche lo script watcher se esiste
    watcher_script = Path(__file__).parent / "ryujinx_watcher.py"
    if watcher_script.exists():
        try:
            watcher_script.unlink()
            console.print(f"[dim]Script watcher rimosso: {watcher_script.name}[/dim]")
        except OSError:
            pass

    return success


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _frequency_label(frequency: str, custom: Optional[dict]) -> str:
    """Restituisce una descrizione leggibile della frequenza."""
    labels = {
        "hourly": "ogni ora",
        "6h": "ogni 6 ore",
        "daily": "ogni giorno alle 03:00",
        "3days": "ogni 3 giorni alle 03:00",
        "weekly": "ogni lunedì alle 03:00",
        "monthly": "il 1° di ogni mese alle 03:00",
        "boot": "all'avvio del PC",
        "ryujinx_close": "alla chiusura di Ryujinx",
        "none": "nessuna pianificazione",
    }
    if frequency == "custom" and custom:
        return f"ogni {custom.get('value', '?')} {custom.get('unit', '?')}"
    return labels.get(frequency, frequency)


def prompt_schedule_frequency() -> tuple[str, Optional[dict]]:
    """
    Chiede interattivamente all'utente la frequenza di backup desiderata.

    Returns:
        Tupla (frequency_key, custom_dict_or_None)
    """
    choices = [c["label"] for c in FREQUENCY_CHOICES]
    answer = questionary.select(
        "Con quale frequenza vuoi eseguire il backup automatico?",
        choices=choices,
    ).ask()

    if answer is None:
        return "none", None

    # Trova la chiave corrispondente
    key = next(
        (c["key"] for c in FREQUENCY_CHOICES if c["label"] == answer),
        "none",
    )

    if key == "custom":
        # Chiedi valore e unità
        value_str = questionary.text(
            "Ogni quanti? (inserisci un numero intero):",
            validate=lambda x: x.isdigit() and int(x) > 0 or "Inserisci un numero intero positivo.",
        ).ask()

        unit = questionary.select(
            "Unità di tempo:",
            choices=["minuti", "ore", "giorni", "settimane", "mesi"],
        ).ask()

        if value_str and unit:
            return "custom", {"value": int(value_str), "unit": unit}
        return "none", None

    return key, None


def check_existing_task() -> bool:
    """Verifica se esiste già un task pianificato RyuSync."""
    try:
        proc = subprocess.run(
            ["schtasks", "/query", "/tn", TASK_NAME],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
