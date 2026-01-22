#!/bin/bash
# HuiYing Ledger Platform - Advanced Backup Script
# Usage: ./backup_to_cloud.sh

# Config
APP_DIR="/home/ubuntu/jishubot"
BACKUP_DIR="$APP_DIR/backups"
DB_FILE="$APP_DIR/huiying.db"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="huiying_$DATE.db"
BACKUP_PATH="$BACKUP_DIR/$BACKUP_FILE"

# S3 Config (AWS CLI must be configured on VPS)
S3_BUCKET="s3://your-bucket-name/backups/"

# 1. Local Backup
mkdir -p $BACKUP_DIR
echo "[$(date)] Starting local backup..."
sqlite3 $DB_FILE ".backup '$BACKUP_PATH'"

if [ $? -eq 0 ]; then
    echo "[$(date)] Local backup created: $BACKUP_PATH"
else
    echo "[$(date)] Local backup failed!"
    exit 1
fi

# 2. Compression
gzip $BACKUP_PATH
BACKUP_PATH_GZ="$BACKUP_PATH.gz"
echo "[$(date)] Compressed to $BACKUP_PATH_GZ"

# 3. Cloud Upload (Optional - Uncomment if AWS CLI is installed)
# echo "[$(date)] Uploading to S3..."
# aws s3 cp $BACKUP_PATH_GZ $S3_BUCKET
# if [ $? -eq 0 ]; then
#     echo "[$(date)] Upload successful."
# else
#     echo "[$(date)] Upload failed!"
# fi

# 4. Cleanup (Local: 7 days, Cloud: Lifecycle rules handled by S3)
find $BACKUP_DIR -name "huiying_*.db.gz" -type f -mtime +7 -exec rm {} \;
echo "[$(date)] Cleanup complete."
