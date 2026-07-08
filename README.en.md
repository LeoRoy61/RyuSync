# RyuSync

[![Italiano](https://img.shields.io/badge/lang-Italiano-green)](README.md)
[![Version](https://img.shields.io/badge/version-1.0.0-green)](https://github.com/ryusync/ryusync)
[![Platform](https://img.shields.io/badge/platform-Windows-blue?logo=windows)](https://github.com/ryusync/ryusync)
[![Python](https://img.shields.io/badge/python-3.10%2B-yellow?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://github.com/ryusync/ryusync/actions/workflows/tests.yml/badge.svg)](https://github.com/ryusync/ryusync/actions)

> **Safe backup and synchronization of Ryujinx data across multiple Windows PCs**

RyuSync is a CLI tool for **safe, additive backup** of [Ryujinx](https://ryujinx.org/) (Nintendo Switch emulator) configurations and save data to cloud storage (Google Drive, OneDrive, Mega) or local/network storage. It integrates with **Windows Task Scheduler** — no persistent daemon, no tray icon: it launches, does its job, and exits cleanly.

![RyuSync CLI — interactive menu](docs/ryusync_cli.jpg)

---

## ✨ Key Features

- 🛡️ **Never deletes anything** — additive-only, no automatic overwriting
- ⚡ **Auto-detection** of Ryujinx installations (portable + AppData)
- ☁️ **Cloud via rclone** (Google Drive, OneDrive, Mega) + local and SMB storage
- 🔄 **Additive bidirectional sync** — only missing or newer files
- ⚠️ **Conflict management** — both versions saved with `_CONFLICT_PC1/_CONFLICT_PC2`
- 📋 **Timestamped logs** for every operation
- 🔔 **Windows desktop notifications** (optional)
- 🗜️ **Optional .zip compression** before upload
- ♻️ **Configurable retention** (keep last N versions)
- ✅ **Integrity verification** via SHA-256 or mtime+size
- 🏃 **Dry-run mode** — preview what would happen without executing
- 📅 **Task Scheduler** — intervals from minutes to months, including Ryujinx-close trigger

---

## 📋 Requirements

| Requirement | Version |
|-------------|---------|
| Python | 3.10 or higher |
| Windows | 10/11 (64-bit) |
| [rclone](https://rclone.org/downloads/) | Latest stable version |

---

## 🚀 Installation

### 1. Clone the repository

```bash
git clone https://github.com/ryusync/ryusync.git
cd ryusync
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install rclone

Download rclone from the official website: **https://rclone.org/downloads/**

Extract `rclone.exe` and add it to your Windows PATH, or copy it to the RyuSync folder.

Verify installation:
```bash
rclone version
```

---

## ⚙️ Configuring rclone (Step-by-Step)

### Google Drive

```bash
rclone config
```

Follow these steps in the interactive menu:

1. Choose `n` → **New remote**
2. Name: `gdrive` (or any name you prefer)
3. Storage: type `drive` and press Enter
4. Client ID and Secret: leave empty (press Enter)
5. Scope: `1` (full access)
6. Root folder ID: leave empty
7. Service account: leave empty
8. Edit advanced config: `n`
9. Use auto config: `y` → browser will open for Google OAuth authentication
10. Team Drive: `n`
11. Confirm with `y`

Verify:
```bash
rclone listremotes
# Expected output: gdrive:
```

> **💡 Minimal OAuth permissions recommended**: instead of granting access to your entire Google Drive,
> you can restrict rclone to a dedicated folder (e.g. `RyuSync/`).
> At step 6, specify the **Root folder ID** of your backup folder (visible in the Google Drive URL).
> This way rclone can ONLY access that specific folder.

### OneDrive

```bash
rclone config
# Storage: onedrive
# Follow OAuth instructions in the browser
```

### Mega

```bash
rclone config
# Storage: mega
# Enter your Mega email and password
```

### Quick Test

```bash
rclone lsd gdrive:
# Lists folders on your Google Drive
```

---

## 🎮 Usage

### Interactive mode (first run)

```bash
python ryusync.py
```

The menu will guide you through:
1. **Action**: Backup / Restore / Bidirectional Sync
2. **Contents**: saves, Mii, system, config, mods, ROMs (optional), shader cache (excluded by default)
3. **Destination**: Google Drive, OneDrive, Mega, local SSD, SMB
4. **Scheduling**: after the first successful backup, you can set up automatic backups

### Dry-run mode (preview without executing)

```bash
python ryusync.py --dry-run
```

### Automatic backup (Task Scheduler)

Configured automatically at the end of the first interactive backup.
You can also launch it manually:

```bash
python ryusync.py --mode=incremental --silent
```

### Remove scheduling

```bash
python ryusync.py --unschedule
```

### Help

```bash
python ryusync.py --help
```

---

## 📅 Automatic Scheduling — Available Frequencies

After the first successful backup, RyuSync asks whether you want to schedule automatic backups.
Choose the frequency that best fits your needs:

| # | Frequency | Windows Implementation |
|---|-----------|----------------------|
| 1 | Every hour | `schtasks /sc HOURLY /mo 1` |
| 2 | Every 6 hours | `schtasks /sc HOURLY /mo 6` |
| 3 | Once a day | `schtasks /sc DAILY /mo 1 /st 03:00` |
| 4 | Every 3 days | `schtasks /sc DAILY /mo 3 /st 03:00` |
| 5 | Once a week | `schtasks /sc WEEKLY /mo 1 /st 03:00` |
| 6 | Once a month | `schtasks /sc MONTHLY /mo 1 /st 03:00` |
| 7 | On PC startup | `schtasks /sc ONSTART` |
| 8 | On Ryujinx close | Watcher task every 5 min via psutil |
| 9 | Custom | e.g. every 10 days → `/sc DAILY /mo 10` |
| 10 | No scheduling | — |

**Custom example**: "every 10 days" →
```
Value: 10
Unit: days
→ schtasks /sc DAILY /mo 10 /st 03:00
```

> **Why Task Scheduler instead of a persistent process?**
> A Windows scheduled task launches, does its work and **exits completely**.
> It consumes no background RAM, doesn't interfere with Ryujinx during gameplay,
> and survives reboots without additional configuration.
> It's the most robust and least invasive approach for automatic backups on Windows.

---

## 🏗️ Project Structure

```
RyuSync/
├── ryusync.py          # Main entry point
├── detector.py         # Ryujinx automatic detection
├── backup_engine.py    # Backup/sync/conflict/integrity logic
├── scheduler.py        # Windows Task Scheduler integration
├── config.yaml         # Persistent configuration (auto-generated)
├── requirements.txt    # Python dependencies
├── .gitignore
├── LICENSE             # MIT
├── README.md           # Italian guide
├── README.en.md        # This guide (English)
├── logs/               # Operation logs (auto-generated)
├── tests/
│   ├── conftest.py     # pytest fixtures
│   ├── test_detector.py
│   └── test_backup_engine.py
└── .github/
    └── workflows/
        └── tests.yml   # CI on Windows (Python 3.10-3.13)
```

---

## 🛡️ Safety Principle

RyuSync is designed with a fundamental principle:

> **Never delete anything. Never overwrite automatically.**

| Scenario | Behavior |
|----------|----------|
| File missing at destination | ✅ Copy |
| Identical file at destination | ⏭️ Skip |
| Newer local file | ✅ Copy |
| Newer remote file | ⚠️ Warn, ask for confirmation |
| File with different content (conflict) | 💾 Save both versions with `_CONFLICT_` |
| File present only at destination | 🔒 Never touched |

---

## 🔒 Securing rclone Credentials

> ⚠️ **Critical point often overlooked**: `rclone.conf` stores OAuth tokens and API keys in
> plain text or with minimal obfuscation. Anyone who can access this file can use your cloud accounts.

### Check if rclone.conf is encrypted

RyuSync automatically warns you at startup if your `rclone.conf` is not encrypted.
You can also check manually:

```bash
# Find where your rclone.conf is:
rclone config file

# If the file starts with sections like [gdrive], [onedrive]...
# → It is NOT encrypted. Follow the guide below.

# If it starts with "# Encrypted rclone configuration File"
# → Great! You are protected.
```

### Enable AES-256 encryption on rclone.conf

```bash
rclone config
# In the main menu, choose: s) Set configuration password
# Enter a strong password and confirm it
# The file will be encrypted with AES-256 (GCM)
```

After setting the password, rclone will ask for it on every run.
For use with Task Scheduler (no interactive prompt), set it as an environment variable:

```powershell
# In PowerShell (current session)
$env:RCLONE_CONFIG_PASS = "your-password"

# Persistently (current user only)
[System.Environment]::SetEnvironmentVariable("RCLONE_CONFIG_PASS", "your-password", "User")
```

### Minimal OAuth Permissions

Instead of granting access to your entire Google Drive:

1. Create a dedicated folder on Google Drive (e.g. `RyuSync_Backup`)
2. Copy its **folder ID** from the URL: `drive.google.com/drive/folders/`**`1ABC...XYZ`**
3. During `rclone config`, at the "Root folder ID" step, paste this ID
4. rclone will be able to access **only** that folder

### Local Config File Protection

RyuSync automatically applies restricted permissions to `config.yaml` via `icacls`.
Verify your files are protected:

```powershell
# Check config.yaml permissions
icacls config.yaml

# Check rclone.conf permissions
icacls "%APPDATA%\rclone\rclone.conf"
```

---

## 🔧 Configuration (config.yaml)

After the first interactive run, `config.yaml` is automatically created with restricted permissions (only the current user can read it).

Main parameters:

```yaml
ryujinx_path: "C:\\Users\\Name\\AppData\\Roaming\\Ryujinx"
pc_name: "Gaming-PC"
destination_type: "gdrive"
destination_path: "gdrive:RyuSync"

contents:
  saves: true
  mii: true
  system: true
  config: true
  mods: true
  roms: false           # Optional, warns if >5GB
  shader_cache: false   # Excluded by default (regeneratable)

integrity_method: "mtime_size"   # or "sha256"
compress_before_upload: false
keep_versions: 3
size_warning_threshold_gb: 5.0
desktop_notifications: true
```

---

## 🧪 Running the Tests

```bash
python -m pytest tests/ -v
```

Expected output: **48 tests PASSED** ✅

---

## 📊 Ryujinx Data Structure Handled

| Path | Content | Default |
|------|---------|---------|
| `bis/user/save/` | Save data by title ID | ✅ included |
| `bis/user/save/*/mii/` | Mii data | ✅ included |
| `bis/system/` | System data and accounts | ✅ included |
| `Config.json` | General settings | ✅ included |
| `mods/` | Game mods | ✅ included |
| `games/` (or path from Config) | ROMs/ISOs | ❌ excluded (optional) |
| Shader cache | Shader cache | ❌ excluded (regeneratable) |

---

## 🗺️ Roadmap

### v1.0 (current) — Windows only
- ✅ Additive backup (no deletion)
- ✅ Multi-PC conflict management
- ✅ rclone cloud + local/SMB storage
- ✅ Windows Task Scheduler
- ✅ Windows desktop notifications
- ✅ Test suite (48 tests)

### v2.0 (future) — If the project gains traction

**Linux** and **macOS** support is planned for a future version.
The codebase is already architected with `detect_ryujinx_path(os_name)` and `create_scheduled_task(os_name, frequency)` functions that currently only handle `"windows"`, but are ready to receive `"linux"` and `"darwin"` branches without rewriting the core logic.

**Linux**: detection in `~/.config/Ryujinx`, scheduling via systemd timer or crontab.
**macOS**: detection in `~/Library/Application Support/Ryujinx`, scheduling via launchd.

> 💡 Want to contribute Linux/macOS support? Open an issue or PR on GitHub!

---

## 📝 License

MIT — see [LICENSE](LICENSE)

---

## 🤝 Contributing

See the full guide in [CONTRIBUTING.md](CONTRIBUTING.md).

1. Fork the repository
2. Create a branch: `git checkout -b feature/feature-name`
3. Add tests for new functionality
4. Open a Pull Request

Tests must pass on Windows with Python 3.10+ before merging.

---

## 📅 Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full version history.
