#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/kliniassist}"
HOOK_PATH="$APP_DIR/.git/hooks/post-merge"

cd "$APP_DIR"

mkdir -p "$(dirname "$HOOK_PATH")"
cat > "$HOOK_PATH" <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/kliniassist}"
cd "$APP_DIR"

if [ -x scripts/vps-post-deploy.sh ]; then
  scripts/vps-post-deploy.sh
else
  bash scripts/vps-post-deploy.sh
fi
HOOK

chmod +x "$HOOK_PATH"
echo "Installed VPS post-merge deploy hook at $HOOK_PATH"
