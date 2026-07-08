# Changelog

Tutte le modifiche notevoli a RyuSync vengono documentate in questo file.

Il formato segue [Keep a Changelog](https://keepachangelog.com/it/1.0.0/),
e questo progetto adotta il [Versionamento Semantico](https://semver.org/lang/it/).

---

## [Unreleased]

*(Nessuna modifica in sviluppo attivo al momento)*

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

[Unreleased]: https://github.com/ryusync/ryusync/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/ryusync/ryusync/releases/tag/v1.0.0
