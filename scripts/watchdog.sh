#!/bin/bash

# JishuBot Watchdog Script
# This script checks if the local web server is responding.
# If not, it assumes the bot has hung/crashed and restarts the systemd service.

APP_URL="http://127.0.0.1:8000/"
SERVICE_NAME="jishubot.service"
LOG_FILE="/home/ubuntu/jishubot/watchdog.log"

# Perform curl request, timeout 10s
HTTP_STATUS=$(curl -o /dev/null -s -w "%{http_code}\n" -m 10 "$APP_URL")

if [ "$HTTP_STATUS" -ne 200 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Watchdog: Bot is unresponsive (HTTP $HTTP_STATUS). Restarting service..." >> "$LOG_FILE"
    sudo systemctl restart "$SERVICE_NAME"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Watchdog: Restart command issued." >> "$LOG_FILE"
fi
