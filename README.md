# SoftEther VPN Log Panel

A modern, secure, and production-ready web application for analyzing, correlating, and reporting connection histories of **SoftEther VPN Server**.

---

## Key Features

- **Automated SoftEther Log Ingestion**: High-performance streaming parser for `server_log` and `security_log` with chunked reading supporting multi-gigabyte log files.
- **Accurate Session Correlation**: Pairs login and logout events, handles multi-device concurrent sessions per user, accounts for abrupt client drops and VPN server restarts without fabricating timestamps.
- **Data Quality & Confidence Reporting**: Explicit indicators for confirmed, active, and incomplete sessions.
- **Multi-Hub Support**: Automatically detects and separates multiple Virtual Hubs (`DEFAULT`, `VPN`, etc.).
- **Persian (Jalali) & Gregorian Calendars**: Full dual-calendar support with end-of-day precision and quick filter shortcuts (Today, Yesterday, Last 7 Days, Last 30 Days, This Month).
- **Professional Reports & Exports**: Multi-sheet formatted Excel (`.xlsx`) exports and Excel-compatible UTF-8 BOM CSV exports.
- **Security & User Management**: Role-based access control (`Super Administrator`, `Administrator`, `Read-only Viewer`), Argon2id password hashing, IP rate limiting, CSRF protection, and audit logging.
- **Air-Gapped & Offline Ready**: 100% self-contained frontend with zero external CDN dependencies.
- **Non-Invasive Deployment**: Runs as an isolated non-root user (`softether-panel`) on Ubuntu Linux with read-only ACL access to SoftEther logs. Never disrupts or reloads the VPN service.

---

## Architecture

```
SoftEther VPN Server
├── server_log/ (vpn_*.log) ───────┐
└── security_log/ (<HUB>/sec_*.log)──┼─► [Read-Only POSIX ACL]
                                    │
                         ┌──────────▼──────────┐
                         │   LogSynchronizer   │ (Byte-offset incremental tracking)
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │   SessionCorrelator │ (Deduplication & session state machine)
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │ SQLite WAL Database │ (Indexed events & correlated sessions)
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │ FastAPI REST Server │ (Port 8080, Argon2id, Audit Log)
                         └──────────┬──────────┘
                                    │
                         ┌──────────▼──────────┐
                         │ Single-Page Web UI  │ (Dark/Light themes, Jalali/Gregorian, RTL/LTR)
                         └─────────────────────┘
```

---

## Local Development (Windows)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/mobinka18dev/softehter-log-panel.git
   cd softehter-log-panel
   ```

2. **Create virtual environment and install dependencies:**
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
   ```

3. **Run automated tests:**
   ```powershell
   .\.venv\Scripts\python.exe -m pytest -v
   ```

4. **Sync sample logs and start the server:**
   ```powershell
   .\.venv\Scripts\python.exe manage.py sync-logs
   .\.venv\Scripts\python.exe manage.py run
   ```
   Open your browser at `http://127.0.0.1:8080`.

---

## Quick Install on Ubuntu (One-Click)

Run the following command directly on your Ubuntu 22.04 / 24.04 server (e.g. `192.168.5.6`):

```bash
git clone https://github.com/mobinka18dev/softehter-log-panel.git /opt/softether-log-panel
cd /opt/softether-log-panel
sudo bash deploy/install.sh
```

### Post-Install Security & Health Checks

Verify that security ACL boundaries and service status are correctly enforced:

```bash
# 1. Verify strict ACL block on /root and vpn_server.config (must return Permission Denied):
sudo -u softether-panel ls -la /root
sudo -u softether-panel cat /root/vpnserver/vpn_server.config

# 2. Verify read-only access to SoftEther log files (must list log files successfully):
sudo -u softether-panel ls -la /root/vpnserver/server_log

# 3. Verify service healthcheck:
curl -s http://127.0.0.1:8080/api/health
```

### Create Initial Super Administrator

```bash
sudo -u softether-panel /opt/softether-log-panel/.venv/bin/python /opt/softether-log-panel/manage.py create-admin
```
Then access the web interface at `http://192.168.5.6:8080` (or `http://127.0.0.1:8080`).

---

## Quick Update

To pull the latest updates and restart the service on Ubuntu:

```bash
cd /opt/softether-log-panel
sudo git pull origin main
sudo systemctl restart softether-panel
```
Or run the full automated update script with pre-update backup:
```bash
sudo bash /opt/softether-log-panel/deploy/update.sh
```

---

---

## Maintenance & Utilities

- **Update panel:** `sudo bash /opt/softether-log-panel/deploy/update.sh`
- **Backup database & settings:** `sudo bash /opt/softether-log-panel/deploy/backup.sh`
- **Restore from backup:** `sudo bash /opt/softether-log-panel/deploy/restore.sh <path_to_backup.tar.gz>`
- **Uninstall:** `sudo bash /opt/softether-log-panel/deploy/uninstall.sh`

For full Persian documentation, see [README_FA.md](README_FA.md).
