#!/usr/bin/env bash
# ==============================================================================
# SoftEther VPN Log Panel - Backup Script
# Backs up application database, settings, and metadata (NOT raw VPN logs)
# ==============================================================================

set -euo pipefail

INSTALL_DIR="/opt/softether-log-panel"
BACKUP_DIR="${INSTALL_DIR}/backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
ARCHIVE_NAME="backup_${TIMESTAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"

echo "[*] Creating SoftEther Log Panel backup..."

# Safe SQLite backup using SQLite backup API or copy if closed
TMP_BACKUP="/tmp/panel_backup_${TIMESTAMP}.db"
if [ -f "${INSTALL_DIR}/data/panel.db" ]; then
    sqlite3 "${INSTALL_DIR}/data/panel.db" ".backup '${TMP_BACKUP}'"
fi

tar -czf "${BACKUP_DIR}/${ARCHIVE_NAME}" \
    -C "${INSTALL_DIR}" .env \
    -C /tmp "panel_backup_${TIMESTAMP}.db" 2>/dev/null || \
tar -czf "${BACKUP_DIR}/${ARCHIVE_NAME}" \
    -C "${INSTALL_DIR}" .env data/panel.db 2>/dev/null

rm -f "$TMP_BACKUP"

chmod 600 "${BACKUP_DIR}/${ARCHIVE_NAME}"
chown softether-panel:softether-panel "${BACKUP_DIR}/${ARCHIVE_NAME}" 2>/dev/null || true

echo "[+] Backup created successfully: ${BACKUP_DIR}/${ARCHIVE_NAME}"
