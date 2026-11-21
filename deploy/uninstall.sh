#!/usr/bin/env bash
# ==============================================================================
# SoftEther VPN Log Panel - Clean Uninstall Script
# Safely removes the panel service and files without touching SoftEther VPN
# ==============================================================================

set -euo pipefail

INSTALL_DIR="/opt/softether-log-panel"
SERVICE_NAME="softether-panel"
APP_USER="softether-panel"

if [ "$EUID" -ne 0 ]; then
    echo "[ERROR] This uninstaller must be run as root or with sudo."
    exit 1
fi

echo "================================================================"
echo "      SoftEther VPN Log Panel - Uninstallation"
echo "================================================================"
echo "This will remove the panel service, application files, and user."
echo "Your SoftEther VPN Server and original log files will NOT be touched."
echo ""
read -p "Are you sure you want to proceed? [y/N]: " CONFIRM
if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    echo "Uninstallation canceled."
    exit 0
fi

# 1. Stop and disable systemd service
echo "[1/4] Stopping and disabling systemd service..."
systemctl stop "$SERVICE_NAME" 2>/dev/null || true
systemctl disable "$SERVICE_NAME" 2>/dev/null || true
rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
rm -f "/etc/logrotate.d/softether-panel"
rm -f "/etc/cron.d/softether-panel-acl"
systemctl daemon-reload

# 2. Backup or purge data
read -p "Do you want to delete application database and backups? [y/N]: " PURGE
if [[ "$PURGE" == "y" || "$PURGE" == "Y" ]]; then
    echo "[2/4] Removing application directory and all data..."
    rm -rf "$INSTALL_DIR"
    rm -rf "/var/log/softether-panel"
else
    echo "[2/4] Preserving data and backups in $INSTALL_DIR/backups/..."
    find "$INSTALL_DIR" -mindepth 1 -maxdepth 1 ! -name 'backups' ! -name 'data' -exec rm -rf {} +
fi

# 3. Remove application user
echo "[3/4] Removing system user '$APP_USER'..."
userdel "$APP_USER" 2>/dev/null || true

echo "[4/4] Finalizing cleanup..."
echo ""
echo "[+] SoftEther VPN Log Panel uninstalled cleanly."
echo "[+] SoftEther VPN Server remains running untouched."
