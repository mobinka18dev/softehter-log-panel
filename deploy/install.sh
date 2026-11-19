#!/usr/bin/env bash
# ==============================================================================
# SoftEther VPN Log Panel - Production Installation Script for Ubuntu
# Target Server: Ubuntu Linux (192.168.5.6)
# ==============================================================================

set -euo pipefail

# Ensure non-interactive execution for apt and needrestart
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=l

# ANSI color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

INSTALL_DIR="/opt/softether-log-panel"
APP_USER="softether-panel"
APP_GROUP="softether-panel"
SERVICE_NAME="softether-panel"
LOG_DIR="/var/log/softether-panel"
DEFAULT_PORT=8080

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo -e "${BLUE}================================================================${NC}"
echo -e "${BLUE}        SoftEther VPN Log Panel - Ubuntu Installer              ${NC}"
echo -e "${BLUE}================================================================${NC}"

# 1. Root check
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[ERROR] This installer must be run as root or with sudo.${NC}"
    exit 1
fi

# 2. Ubuntu OS Check
if [ -f /etc/os-release ]; then
    . /etc/os-release
    if [[ "$ID" != "ubuntu" && "$ID_LIKE" != *"ubuntu"* ]]; then
        echo -e "${YELLOW}[WARNING] Detected OS: $NAME. This script is optimized for Ubuntu.${NC}"
    else
        echo -e "${GREEN}[+] Detected OS: Ubuntu ($VERSION_ID)${NC}"
    fi
else
    echo -e "${RED}[ERROR] Cannot determine OS distribution.${NC}"
    exit 1
fi

# 3. Install necessary prerequisites
echo -e "\n${BLUE}[1/8] Checking and installing dependencies...${NC}"
apt-get update -y -q
apt-get install -y -q python3 python3-venv python3-pip acl curl sqlite3

# 4. Create non-root application user
echo -e "\n${BLUE}[2/8] Creating dedicated system user '${APP_USER}'...${NC}"
if id "$APP_USER" &>/dev/null; then
    echo -e "${GREEN}[+] User '${APP_USER}' already exists.${NC}"
else
    useradd --system --user-group --no-create-home --shell /usr/sbin/nologin "$APP_USER"
    echo -e "${GREEN}[+] User '${APP_USER}' created.${NC}"
fi

# 5. Setup directories and copy project files
echo -e "\n${BLUE}[3/8] Setting up application directories...${NC}"
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/data"
mkdir -p "$INSTALL_DIR/backups"
mkdir -p "$LOG_DIR"

if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    echo -e "${GREEN}[+] Copying files from $SCRIPT_DIR to $INSTALL_DIR...${NC}"
    cp -r "$SCRIPT_DIR/app" "$INSTALL_DIR/"
    cp -r "$SCRIPT_DIR/deploy" "$INSTALL_DIR/"
    cp "$SCRIPT_DIR/manage.py" "$INSTALL_DIR/"
    cp "$SCRIPT_DIR/requirements.txt" "$INSTALL_DIR/"
    cp "$SCRIPT_DIR/pyproject.toml" "$INSTALL_DIR/" 2>/dev/null || true
    if [ -f "$SCRIPT_DIR/.env.example" ]; then
        cp "$SCRIPT_DIR/.env.example" "$INSTALL_DIR/"
    fi
fi

cd "$INSTALL_DIR"

# 6. Python virtualenv
echo -e "\n${BLUE}[4/8] Creating Python virtual environment...${NC}"
if [ ! -d "$INSTALL_DIR/.venv" ]; then
    python3 -m venv "$INSTALL_DIR/.venv"
fi
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# 7. Environment Configuration
echo -e "\n${BLUE}[5/8] Configuring application environment...${NC}"
if [ ! -f "$INSTALL_DIR/.env" ]; then
    RANDOM_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    
    # Prompt for SoftEther Log directory with auto-detection
    DEFAULT_SE_LOG="/root/vpnserver"
    if [ ! -d "/root/vpnserver" ]; then
        if [ -d "/usr/local/vpnserver" ]; then
            DEFAULT_SE_LOG="/usr/local/vpnserver"
        elif [ -d "/var/log/vpnserver" ]; then
            DEFAULT_SE_LOG="/var/log/vpnserver"
        fi
    fi
    if [ -n "${SOFTETHER_LOG_DIR:-}" ]; then
        DEFAULT_SE_LOG="${SOFTETHER_LOG_DIR}"
    fi

    echo -e "${YELLOW}Enter the path to your SoftEther VPN Server logs directory [Default: ${DEFAULT_SE_LOG}]:${NC}"
    read -r USER_SE_LOG
    SE_LOG_PATH="${USER_SE_LOG:-$DEFAULT_SE_LOG}"

    cat <<EOF > "$INSTALL_DIR/.env"
APP_NAME="SoftEther VPN Log Panel"
APP_ENV=production
DEBUG=false
HOST=0.0.0.0
PORT=${DEFAULT_PORT}
SECRET_KEY=${RANDOM_SECRET}
ACCESS_TOKEN_EXPIRE_MINUTES=480
DATABASE_PATH=${INSTALL_DIR}/data/panel.db
SOFTETHER_LOG_DIR=${SE_LOG_PATH}
SYNC_INTERVAL_SECONDS=15
AUTO_SYNC_ENABLED=true
MAX_LOG_LINE_BATCH=5000
CORS_ORIGINS="http://127.0.0.1:${DEFAULT_PORT},http://localhost:${DEFAULT_PORT},http://192.168.5.6:${DEFAULT_PORT}"
EOF
    chown "$APP_USER":"$APP_GROUP" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"
    echo -e "${GREEN}[+] Created .env with generated secure key.${NC}"
else
    echo -e "${GREEN}[+] Existing .env file preserved.${NC}"
fi

# 8. Grant Minimal Read-Only access strictly to SoftEther log directories
source "$INSTALL_DIR/.env"
echo -e "\n${BLUE}[6/8] Configuring Minimal Read-Only permissions for SoftEther logs...${NC}"

HAS_SERVER_LOG=false
HAS_SECURITY_LOG=false

if [ -d "$SOFTETHER_LOG_DIR/server_log" ]; then
    HAS_SERVER_LOG=true
fi
if [ -d "$SOFTETHER_LOG_DIR/security_log" ]; then
    HAS_SECURITY_LOG=true
fi

DIR_NAME=$(basename "$SOFTETHER_LOG_DIR")
if [ "$DIR_NAME" == "server_log" ] || [ "$DIR_NAME" == "security_log" ]; then
    HAS_SERVER_LOG=true
fi

if [ "$HAS_SERVER_LOG" = false ] && [ "$HAS_SECURITY_LOG" = false ]; then
    echo -e "${RED}[ERROR] Neither 'server_log' nor 'security_log' was safely identified under:${NC}"
    echo -e "${YELLOW}  ${SOFTETHER_LOG_DIR}${NC}"
    echo -e "${RED}Security policy: Refusing to apply permissions to the entire installation root.${NC}"
    echo -e "Please verify your SoftEther log directory and re-run installation."
    echo -e "Expected structure: ${SOFTETHER_LOG_DIR}/server_log/ and ${SOFTETHER_LOG_DIR}/security_log/"
    exit 1
fi

# Grant traverse-only (execute) permission on all parent folders up to root (e.g. /root)
PARENT_DIR="$(dirname "$SOFTETHER_LOG_DIR")"
while [ "$PARENT_DIR" != "/" ] && [ "$PARENT_DIR" != "." ]; do
    echo -e "${GREEN}[+] Applying traverse-only ACL (X) on parent: ${PARENT_DIR}...${NC}"
    setfacl -m "u:${APP_USER}:X" "$PARENT_DIR" 2>/dev/null || true
    PARENT_DIR="$(dirname "$PARENT_DIR")"
done

# Grant non-recursive read & execute ACL on SOFTETHER_LOG_DIR itself (e.g. /root/vpnserver)
echo -e "${GREEN}[+] Applying non-recursive read & execute ACL (rX) on: ${SOFTETHER_LOG_DIR}...${NC}"
setfacl -m "u:${APP_USER}:rX" "$SOFTETHER_LOG_DIR" 2>/dev/null || true

# Explicitly block access to sensitive configuration files
if [ -f "$SOFTETHER_LOG_DIR/vpn_server.config" ]; then
    echo -e "${GREEN}[+] Explicitly blocking read access to sensitive file: vpn_server.config...${NC}"
    setfacl -m "u:${APP_USER}:---" "$SOFTETHER_LOG_DIR/vpn_server.config" 2>/dev/null || true
fi

# Apply recursive read-only + directory default ACL strictly to server_log and security_log
if [ -d "$SOFTETHER_LOG_DIR/server_log" ]; then
    echo -e "${GREEN}[+] Granting read-only ACL to '${APP_USER}' on '${SOFTETHER_LOG_DIR}/server_log'...${NC}"
    setfacl -R -m "u:${APP_USER}:rX" "$SOFTETHER_LOG_DIR/server_log"
    find "$SOFTETHER_LOG_DIR/server_log" -type d -exec setfacl -d -m "u:${APP_USER}:rX" {} +
fi

if [ -d "$SOFTETHER_LOG_DIR/security_log" ]; then
    echo -e "${GREEN}[+] Granting read-only ACL to '${APP_USER}' on '${SOFTETHER_LOG_DIR}/security_log' (including Hub subdirectories)...${NC}"
    setfacl -R -m "u:${APP_USER}:rX" "$SOFTETHER_LOG_DIR/security_log"
    find "$SOFTETHER_LOG_DIR/security_log" -type d -exec setfacl -d -m "u:${APP_USER}:rX" {} +
fi

if [ "$DIR_NAME" == "server_log" ] || [ "$DIR_NAME" == "security_log" ]; then
    echo -e "${GREEN}[+] Granting read-only ACL to '${APP_USER}' on '${SOFTETHER_LOG_DIR}'...${NC}"
    setfacl -R -m "u:${APP_USER}:rX" "$SOFTETHER_LOG_DIR"
    find "$SOFTETHER_LOG_DIR" -type d -exec setfacl -d -m "u:${APP_USER}:rX" {} +
fi

echo -e "${GREEN}[+] Minimal read-only ACL configured safely. No write permissions or configuration files exposed.${NC}"

# Fix ownership and permissions before database initialization
chown -R "$APP_USER":"$APP_GROUP" "$INSTALL_DIR"
chown -R "$APP_USER":"$APP_GROUP" "$LOG_DIR"
chmod 750 "$INSTALL_DIR"
if [ -f "$INSTALL_DIR/.env" ]; then
    chown "$APP_USER":"$APP_GROUP" "$INSTALL_DIR/.env"
    chmod 600 "$INSTALL_DIR/.env"
fi

# 9. Initialize Database
echo -e "\n${BLUE}[7/8] Initializing database...${NC}"
(cd "$INSTALL_DIR" && sudo -u "$APP_USER" PYTHONPATH="$INSTALL_DIR" "$INSTALL_DIR/.venv/bin/python" -c "import sys; sys.path.insert(0, '$INSTALL_DIR'); from app.database import init_db; init_db()")

# 10. Install systemd service & logrotate
echo -e "\n${BLUE}[8/8] Installing and starting systemd service...${NC}"
cp "$INSTALL_DIR/deploy/softether-panel.service" /etc/systemd/system/
cp "$INSTALL_DIR/deploy/logrotate.conf" /etc/logrotate.d/softether-panel

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

# Wait for startup and check health
sleep 3
if curl -s "http://127.0.0.1:${PORT:-8080}/health" | grep -q "ok" || curl -s "http://127.0.0.1:${PORT:-8080}/api/health" | grep -q "ok"; then
    echo -e "\n${GREEN}================================================================${NC}"
    echo -e "${GREEN}  Installation completed successfully!                          ${NC}"
    echo -e "${GREEN}================================================================${NC}"
    echo -e "Panel status: ${GREEN}RUNNING${NC}"
    echo -e "Access URL:   ${BLUE}http://192.168.5.6:${PORT:-8080}${NC} or ${BLUE}http://127.0.0.1:${PORT:-8080}${NC}"
    echo -e "\nTo create your initial administrator account from CLI, run:"
    echo -e "${YELLOW}sudo -u ${APP_USER} ${INSTALL_DIR}/.venv/bin/python ${INSTALL_DIR}/manage.py create-admin${NC}"
    echo -e "(Or open the web panel in your browser to use the initial setup wizard)\n"
else
    echo -e "\n${RED}[WARNING] Service started, but health check failed. Check logs with:${NC}"
    echo -e "${YELLOW}journalctl -u ${SERVICE_NAME} -n 50 --no-pager${NC}"
fi
