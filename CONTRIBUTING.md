# Come Contribuire a RyuSync

Grazie per il tuo interesse nel contribuire a RyuSync! 🎮

Questo documento spiega come segnalare bug, proporre funzionalità e sottomettere Pull Request.

---

## 📋 Prima di aprire una Issue

- **Cerca prima** tra le [issue esistenti](https://github.com/ryusync/ryusync/issues) per evitare duplicati.
- Per bug, includi sempre: versione Python, versione Windows, output dell'errore.
- Per richieste di funzionalità, spiega il caso d'uso concreto.

---

## 🐛 Segnalare un Bug

Apri una issue usando il template "Bug Report" e includi:

```
**Versione RyuSync**: v1.0.x
**Python**: 3.x.x
**Windows**: 10/11 (build)
**Descrizione**: cosa hai fatto, cosa ti aspettavi, cosa è successo
**Output errore**: (copia il traceback completo)
**Log**: allega il file backup_log_YYYYMMDD_HHMM.txt se disponibile
```

---

## ✨ Proporre una Funzionalità

Apri una issue con etichetta `enhancement`. Prima di proporre:

- Controlla la [Roadmap](README.it.md#️-roadmap) — potrebbe essere già pianificata.
- Spiega perché la funzionalità sarebbe utile per più utenti, non solo per te.

---

## 🔧 Sottomettere una Pull Request

### Setup dell'ambiente

```bash
git clone https://github.com/ryusync/ryusync.git
cd ryusync
python -m venv venv
venv\Scripts\activate         # Windows
pip install -r requirements.txt
pip install ruff              # Linter opzionale
```

### Regole fondamentali

1. **I test devono passare**: `python -m pytest tests/ -v` — tutti i test devono essere GREEN.
2. **Aggiungi test**: ogni nuova funzionalità richiede almeno un test pytest.
3. **Non rompere il principio di sicurezza**: nessun codice che cancelli file o sovrascriva senza conferma.
4. **Un branch per feature**: `git checkout -b feature/nome-feature`.
5. **Commit atomici**: un commit = un cambiamento logico.

### Processo PR

1. Fork → branch → commit → push → Pull Request
2. Descrivi cosa hai cambiato e perché nel corpo della PR
3. Collega la issue corrispondente (`Closes #123`)
4. Attendi la review — rispondi ai commenti in modo costruttivo

### Aggiornamento CHANGELOG.md

Aggiungi una voce in `CHANGELOG.md` nella sezione `[Unreleased]` con il formato:

```markdown
### Aggiunto
- Descrizione della nuova funzionalità (#numero-issue)

### Corretto
- Descrizione del bug fix (#numero-issue)
```

---

## 🌐 Supporto Linux/macOS

Se vuoi aggiungere supporto a Linux o macOS, leggi i commenti `# TODO` in:
- `detector.py` → funzione `detect_ryujinx_path()`
- `scheduler.py` → funzione `create_scheduled_task()`

Il codice è già architetturato per accettare i branch `"linux"` e `"darwin"`.
Apri una issue prima di iniziare per coordinare l'implementazione.

---

## 📝 Standard di Codice

- **Stile**: PEP 8, con limite di 100 caratteri per riga
- **Type hints**: obbligatori per tutte le funzioni pubbliche
- **Docstring**: in italiano per funzioni pubbliche dei moduli principali
- **Linter**: `ruff check .` non deve produrre errori bloccanti

---

## 🔒 Sicurezza

Se scopri una vulnerabilità di sicurezza, **non aprire una issue pubblica**.
Contatta i maintainer privatamente via email o GitHub Security Advisories.

---

Grazie per contribuire! 🙏
