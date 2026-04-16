#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="/tmp/sikdorak-app.pid"
LOG_FILE="/tmp/sikdorak-app.log"

cd "$ROOT_DIR"

chmod +x "$ROOT_DIR/scripts/init-postgres.sh"
"$ROOT_DIR/scripts/init-postgres.sh"

if [[ ! -d node_modules ]]; then
  echo "Installing npm dependencies..."
  npm install
fi

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    kill "$old_pid" || true
  fi
  rm -f "$PID_FILE"
fi

# Guard against orphaned processes already bound to the app port.
if command -v lsof >/dev/null 2>&1; then
  port_pid="$(lsof -ti tcp:3100 || true)"
  if [[ -n "$port_pid" ]]; then
    kill "$port_pid" || true
  fi
else
  port_pid="$(ss -ltnp '( sport = :3100 )' 2>/dev/null | awk -F 'pid=' 'NR>1 {print $2}' | awk -F ',' 'NR==1 {print $1}')"
  if [[ -n "$port_pid" ]]; then
    kill "$port_pid" || true
  fi
fi

nohup npm start >"$LOG_FILE" 2>&1 &
new_pid="$!"
echo "$new_pid" > "$PID_FILE"

for i in {1..30}; do
  if curl -fsS http://127.0.0.1:3100/api/health >/dev/null; then
    break
  fi
  sleep 1
done

if ! curl -fsS http://127.0.0.1:3100/api/health >/dev/null; then
  echo "App startup failed. Check $LOG_FILE"
  exit 1
fi

echo "App started with PID $new_pid"
