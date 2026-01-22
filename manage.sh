#!/bin/bash

# HuiYing Ledger Platform - Deployment & Management Script

APP_NAME="jishubot"
PYTHON_CMD="python3"

# VPS Configuration (Auto-filled)
VPS_IP="52.193.196.41"
VPS_USER="ubuntu"
VPS_KEY="./jizhang.pem"
VPS_PATH="/home/ubuntu/jishubot" # Default path for ubuntu user

function show_help {
    echo "Usage: ./manage.sh [command]"
    echo "Commands:"
    echo "  start       Start the application locally"
    echo "  deploy      Deploy code to VPS (Auto-connect)"
    echo "  restart_vps Restart service on VPS (Auto-connect)"
    echo "  ssh         SSH into VPS"
    echo "  logs        View VPS logs"
    echo "  migrate     Run DB migrations on VPS"
    echo "  setup_cron  Setup auto-backup cron on VPS"
}

function start_local {
    echo "Starting local server on port 8000..."
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
}

function deploy {
    echo "Deploying to $VPS_USER@$VPS_IP:$VPS_PATH ..."
    
    # Upload Code & Scripts
    rsync -avz -e "ssh -i $VPS_KEY -o StrictHostKeyChecking=no" \
        --exclude '__pycache__' --exclude '*.db' --exclude '.git' --exclude '.env' --exclude '*.pem' \
        ./app ./requirements.txt ./alembic.ini ./alembic ./scripts "$VPS_USER@$VPS_IP:$VPS_PATH/"
        
    echo "Code uploaded."
    
    # Install Deps & Restart
    ssh -i "$VPS_KEY" -o StrictHostKeyChecking=no "$VPS_USER@$VPS_IP" \
        "cd $VPS_PATH && pip3 install -r requirements.txt && chmod +x scripts/*.sh && sudo systemctl restart $APP_NAME"
    
    echo "Deployment complete! (Don't forget to run './manage.sh migrate' if DB schema changed)"
}

function restart_vps {
    echo "Restarting $APP_NAME on $VPS_IP..."
    ssh -i "$VPS_KEY" -o StrictHostKeyChecking=no "$VPS_USER@$VPS_IP" "sudo systemctl restart $APP_NAME"
    echo "Done."
}

function ssh_vps {
    echo "Connecting to VPS..."
    ssh -i "$VPS_KEY" -o StrictHostKeyChecking=no "$VPS_USER@$VPS_IP"
}

function logs_vps {
    echo "Fetching logs..."
    ssh -i "$VPS_KEY" -o StrictHostKeyChecking=no "$VPS_USER@$VPS_IP" "journalctl -u $APP_NAME -f"
}

function migrate_db {
    echo "Running Alembic Migrations on VPS..."
    ssh -i "$VPS_KEY" -o StrictHostKeyChecking=no "$VPS_USER@$VPS_IP" \
        "cd $VPS_PATH && python3 -m alembic upgrade head"
    echo "Migration complete."
}

function setup_cron {
    echo "Setting up Cron job for Auto-Backup..."
    CRON_CMD="0 3 * * * $VPS_PATH/scripts/backup_to_cloud.sh >> /tmp/backup.log 2>&1"
    
    # Check if cron already exists to avoid duplicates (simple check)
    ssh -i "$VPS_KEY" -o StrictHostKeyChecking=no "$VPS_USER@$VPS_IP" \
        "(crontab -l 2>/dev/null | grep -F '$VPS_PATH/scripts/backup_to_cloud.sh') || (crontab -l 2>/dev/null; echo '$CRON_CMD') | crontab -"
        
    echo "Cron job installed (Daily at 3:00 AM)."
}

if [ "$1" == "start" ]; then
    start_local
elif [ "$1" == "deploy" ]; then
    deploy
elif [ "$1" == "restart_vps" ]; then
    restart_vps
elif [ "$1" == "ssh" ]; then
    ssh_vps
elif [ "$1" == "logs" ]; then
    logs_vps
elif [ "$1" == "migrate" ]; then
    migrate_db
elif [ "$1" == "setup_cron" ]; then
    setup_cron
else
    show_help
fi
