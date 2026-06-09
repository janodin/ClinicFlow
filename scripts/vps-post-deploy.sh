#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/kliniassist}"
SERVICE_NAME="${SERVICE_NAME:-kliniassist}"

cd "$APP_DIR"

echo 'Activating environment and installing Python dependencies...'
source venv/bin/activate
pip install -r requirements.txt

echo 'Running migrations...'
python manage.py migrate

echo 'Collecting static files...'
python manage.py collectstatic --noinput

echo 'Installing n8n workflow sync dependencies...'
if ! command -v npm >/dev/null 2>&1; then
  echo 'npm is required to sync the n8n workflow from source.' >&2
  exit 1
fi
npm install --omit=dev --no-audit --no-fund

echo 'Syncing n8n workflow from source...'
npm run sync:n8n

echo 'Restarting KliniAssist service...'
systemctl restart "$SERVICE_NAME"

echo 'Post-deploy hook complete.'
