# Changelog

Tutte le modifiche notevoli a RyuSync vengono documentate in questo file.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.0.0/),
e questo progetto adotta il [Versionamento Semantico](https://semver.org/lang/it/).

---

## [Unreleased]

### Modifiche apportate dal Team di Agenti AI

#### Agente 1 — Compatibilità e Ottimizzazione Rilevamento
- **R1 (Console UTF-8)**: Riconfigurazione forzata di stdout/stderr a UTF-8 su Windows all'avvio per prevenire crash con emoji e caratteri speciali su console legacy (CP1252).
- **R2 (Percorsi POSIX)**: Conversione di tutti i backslash (`\`) nei percorsi Windows in forward slash (`/`) prima di invocare `rclone`, prevenendo la creazione di cartelle con nomi corrotti sul cloud.
- **R3 (Destinazioni Locali)**: Normalizzazione del rilevamento delle destinazioni locali (es. `D:/Backup`) anche se non ancora esistenti su disco.
- **R4 (Percorsi Assoluti)**: Risoluzione dei percorsi di `logs/` e `backups/` in percorsi assoluti rispetto alla cartella dello script per evitare crash con Windows Task Scheduler (dove il working directory di default è `C:\Windows\System32`).
- **R5 (Performance Rilevamento)**: Limitazione a massimo 2 livelli di profondità per la ricerca di Ryujinx in cartelle comuni (es. Program Files, Downloads) per evitare freeze all'avvio.
- **R6 (Guida Google Drive)**: Correzione dell'ordine e dei passaggi nella guida interattiva per Google Drive nei file README (Root folder ID spostato sotto la configurazione avanzata).

#### Agente 2 — Menu Interattivo e Affidabilità
- **R7 (ValueError Checkbox)**: Risoluzione del crash di `questionary.checkbox` per la selezione dei valori di default usando oggetti `Choice(checked=...)` invece di semplici stringhe.
- **R8 (Timeout rclone)**: Estensione del timeout di copia `rclone` da 5 minuti ad 1 ora per permettere il backup di salvataggi pesanti (firmware/mods) su connessioni lente.

#### Agente 3 — Testing di Integrazione
- **Integrazione Scenari**: Creazione della suite di test di integrazione automatizzata `tests/verify_scenarios.py` per testare tutte le combinazioni di contenuti, dry-run, GDrive e scenari di ripristino/recovery reali.

#### Agente 4 — Audit di Sicurezza e QA (Questo Agent)
- **Scansione Dati Sensibili**: Aggiunto il controllo `check_sensitive_data_exposure()` per esaminare `ryusync_state.json` e i file in `logs/` ed avvisare se contengono dati sensibili del PC locale (username, hostname, percorsi di profilo).
- **Notifiche in Silent Mode**: Esteso `warn_if_unencrypted()` per inviare notifiche desktop e log di avviso in modalità silenziosa se viene rilevato un `rclone.conf` non cifrato o un'esposizione combinata di dati.
- **Deduplica Rilevamento**: Rilevamento Ryujinx (`detector.py`) ottimizzato per deduplicare logicamente i percorsi degli eseguibili (casing, slashes) tramite risoluzione dei percorsi canonici, eliminando doppi log o doppie ricerche.
- **Suite di Test Estesa**: Aggiunta di `tests/test_watcher_and_silent.py` con 11 nuovi test per coprire watcher state corruption, modalità silent error handling, sensitive data exposure e notifiche.
- **Aggiornamento QA**: Verifica e aggiornamento del numero di test passanti a **71** nei file `README.md` e `README.it.md`, e audit del workflow CI su GitHub Actions per assicurare il corretto funzionamento su Windows.

---

## [1.0.1] — 2024-07-08

### Aggiunto
- **Modulo `security.py`**: rilevamento automatico se `rclone.conf` è cifrato o in chiaro
- **Avviso all'avvio** se `rclone.conf` non è protetto da password AES-256
- **Sezione "Sicurezza delle credenziali"** in README.md e README.en.md con guida completa
- **Guida permessi OAuth minimi** per Google Drive (Root folder ID dedicato)
- **`CONTRIBUTING.md`**: guida completa per contribuire al progetto
- **`CHANGELOG.md`**: storico versioni in formato Keep a Changelog
- **Screenshot CLI** in `docs/ryusync_cli.jpg` nei README
- **11 nuovi test pytest** per `security.py` (totale: 59 test)

### Sicurezza
- `rclone.conf` e `rclone.conf.bak` aggiunti a `.gitignore`
- Avviso esplicito: mai committare `rclone.conf` in repository pubblici
- Guida `RCLONE_CONFIG_PASS` per uso con Task Scheduler (no prompt interattivo)

---

## [1.0.0] — 2024-07-08

### Aggiunto
- **Backup additivo sicuro**: copia solo file mancanti o più nuovi, mai cancellazioni
- **Rilevamento automatico Ryujinx** su Windows (modalità portable + AppData + winreg)
- **Supporto cloud via rclone**: Google Drive, OneDrive, Mega
- **Supporto storage locale**: SSD/HDD secondario, cartelle di rete SMB
- **Gestione conflitti multi-PC**: entrambe le versioni salvate con suffisso `_CONFLICT_`
- **CLI interattiva** con `rich` e `questionary`: azione / contenuti / destinazione
- **Modalità `--mode=incremental --silent`** per Windows Task Scheduler
- **Modalità `--dry-run`**: anteprima senza esecuzione
- **Flag `--unschedule`**: rimozione task pianificato
- **10 frequenze di pianificazione**: da minuti a mesi, inclusa chiusura Ryujinx
- **Watcher chiusura Ryujinx** via `psutil` + file di stato JSON
- **Verifica integrità** post-backup: SHA-256 o mtime+size (configurabile)
- **Compressione .zip** opzionale pre-upload
- **Retention configurabile**: mantieni le ultime N versioni (default: 3)
- **Notifiche desktop Windows** via `plyer` (disattivabili)
- **Log timestampato** per ogni operazione (`backup_log_YYYYMMDD_HHMM.txt`)
- **Permessi ristretti** su `config.yaml` tramite `icacls`
- **Controllo sicurezza credenziali rclone**: avviso se `rclone.conf` non è cifrato
- **48 test pytest** su Windows (Python 3.10–3.14)
- **GitHub Actions CI**: pytest su Windows con Python 3.10, 3.11, 3.12, 3.13
- **README.md** (italiano) e **README.en.md** (inglese) con guida rclone passo-passo
- **CONTRIBUTING.md** e **CHANGELOG.md**
- **Architettura estendibile**: hook TODO per Linux/macOS in `detector.py` e `scheduler.py`

### Sicurezza
- `rclone copy` usato sempre (mai `rclone sync` distruttivo)
- Confronto mtime+size prima di qualsiasi sovrascrittura
- Nessuna credenziale loggata nei file di log
- `config.yaml` e `rclone.conf` esclusi da `.gitignore`

---

## Note sui tipi di versione

| Tipo | Esempio | Quando |
|------|---------|--------|
| PATCH | 1.0.x | Bugfix retrocompatibili |
| MINOR | 1.x.0 | Nuove funzionalità retrocompatibili |
| MAJOR | x.0.0 | Cambiamenti che rompono la compatibilità |

---

[Unreleased]: https://github.com/LeoRoy61/RyuSync/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/LeoRoy61/RyuSync/releases/tag/v1.0.0
