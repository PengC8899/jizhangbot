#!/bin/bash
# Backup Script for HuiYing Ledger
# Usage: ./backup_db.sh

# Config
APP_DIR="/home/ubuntu/jishubot"
BACKUP_DIR="$APP_DIR/backups"
DB_FILE="$APP_DIR/huiying.db"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/huiying_$DATE.db"

# Create Backup Dir
mkdir -p $BACKUP_DIR

# Copy DB (using sqlite3 .backup command is safer but simple copy works if WAL is enabled, better to vacuum into backup)
# Simplest approach for SQLite in production without stopping service:
sqlite3 $DB_FILE ".backup '$BACKUP_FILE'"

if [ $? -eq 0 ]; then
    echo "[$(date)] Backup successful: $BACKUP_FILE"
else
    echo "[$(date)] Backup failed!"
    exit 1
fi

# Cleanup older than 7 days
find $BACKUP_DIR -name "huiying_*.db" -type f -mtime +7 -exec rm {} \;
echo "[$(date)] Cleaned up old backups."
