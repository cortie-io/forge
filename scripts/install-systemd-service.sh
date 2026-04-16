#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_SRC="$ROOT_DIR/scripts/sikdorak-app.service"
UNIT_DST="/etc/systemd/system/sikdorak-app.service"

if [[ ! -f "$UNIT_SRC" ]]; then
  echo "Unit file not found: $UNIT_SRC"
  exit 1
fi

echo "[1/5] Installing npm dependencies"
cd "$ROOT_DIR"
npm install

echo "[2/5] Installing systemd unit"
sudo cp "$UNIT_SRC" "$UNIT_DST"

echo "[3/5] Reloading systemd daemon"
sudo systemctl daemon-reload

echo "[4/5] Enabling and starting service"
sudo systemctl enable --now sikdorak-app.service

echo "[5/5] Service status"
sudo systemctl --no-pager --full status sikdorak-app.service

echo
echo "Health check:"
curl -fsS http://127.0.0.1:3100/api/health | cat
