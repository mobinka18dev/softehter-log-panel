#!/usr/bin/env bash
# ==============================================================================
# SoftEther VPN Log Panel - Restore Script
# Restores application database and settings from a backup archive
# ==============================================================================

set -euo pipefail

INSTALL_DIR="/opt/softether-log-panel"
SERVICE_NAME="softether-panel"

if [ "$EUID" -ne 0 ]; then
    echo "[ERROR] This script must be run as root or with sudo."
    exit 1
fi

if [ $# -lt 1 ]; then
    echo "Usage: sudo bash restore.sh <path_to_backup_archive.tar.gz>"
    echo "Available backups in ${INSTALL_DIR}/backups/:"
    ls -lh "${INSTALL_DIR}/backups/"*.tar.gz 2>/dev/null || echo "No backups found."
    exit 1
fi

BACKUP_ARCHIVE="$1"

if [ ! -f "$BACKUP_ARCHIVE" ]; then
    echo "[ERROR] Backup file not found: $BACKUP_ARCHIVE"
    exit 1
fi

echo "[*] Stopping ${SERVICE_NAME} service..."
systemctl stop "$SERVICE_NAME" || true

echo "[*] Restoring from $BACKUP_ARCHIVE..."
TMP_DIR=$(mktemp -d)
tar -xzf "$BACKUP_ARCHIVE" -C "$TMP_DIR"

if [ -f "$TMP_DIR/.env" ]; then
    cp "$TMP_DIR/.env" "$INSTALL_DIR/.env"
fi

if [ -f "$TMP_DIR/data/panel.db" ]; then
    cp "$TMP_DIR/data/panel.db" "$INSTALL_DIR/data/panel.db"
elif [ -f "$TMP_DIR/panel_backup_"*.db ]; then
    cp "$TMP_DIR/panel_backup_"*.db "$INSTALL_DIR/data/panel.db"
fi

rm -rf "$TMP_DIR"

chown -R softether-panel:softether-panel "$INSTALL_DIR"

echo "[*] Starting ${SERVICE_NAME} service..."
systemctl start "$SERVICE_NAME"
sleep 2

source "$INSTALL_DIR/.env"
if curl -s "http://127.0.0.1:${PORT:-8080}/health" | grep -q "ok"; then
    echo "[+] Restore completed and verified successfully!"
else
    echo "[WARNING] Service restarted, but health check failed. Check journalctl -u ${SERVICE_NAME}"
fi
