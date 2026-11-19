#!/usr/bin/env bash
# ==============================================================================
# SoftEther VPN Log Panel - Production Update Script
# ==============================================================================

set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=l

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

INSTALL_DIR="/opt/softether-log-panel"
APP_USER="softether-panel"
SERVICE_NAME="softether-panel"

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[ERROR] This script must be run as root or with sudo.${NC}"
    exit 1
fi

echo -e "${BLUE}[*] Starting SoftEther Log Panel update...${NC}"

# 1. Automatic pre-update backup
echo -e "${BLUE}[1/5] Creating pre-update backup...${NC}"
bash "$INSTALL_DIR/deploy/backup.sh"

# 2. Update code (if in git repo)
echo -e "${BLUE}[2/5] Updating application code...${NC}"
if [ -d "$INSTALL_DIR/.git" ]; then
    sudo -u "$APP_USER" git -C "$INSTALL_DIR" pull --ff-only || {
        echo -e "${YELLOW}[!] Git pull failed or branch diverged. Continuing with local files.${NC}"
    }
fi

# 3. Update dependencies
echo -e "${BLUE}[3/5] Updating Python packages...${NC}"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# 4. Apply database schema upgrades
echo -e "${BLUE}[4/5] Updating database schema...${NC}"
sudo -u "$APP_USER" PYTHONPATH="$INSTALL_DIR" "$INSTALL_DIR/.venv/bin/python" -c "import sys; sys.path.insert(0, '$INSTALL_DIR'); from app.database import init_db; init_db()"

# 5. Restart service and verify health
echo -e "${BLUE}[5/5] Restarting service...${NC}"
systemctl restart "$SERVICE_NAME"
sleep 3

source "$INSTALL_DIR/.env"
if curl -s "http://127.0.0.1:${PORT:-8080}/health" | grep -q "ok" || curl -s "http://127.0.0.1:${PORT:-8080}/api/health" | grep -q "ok"; then
    echo -e "${GREEN}[+] Update completed and verified successfully!${NC}"
else
    echo -e "${RED}[WARNING] Service restarted, but health check failed.${NC}"
    echo -e "Check logs with: journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
fi
