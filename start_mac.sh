#!/bin/bash
set -euo pipefail

# 默认仅绑定本机，避免 macOS 对本地网络监听的权限限制
export SERVER_HOST="${SERVER_HOST:-127.0.0.1}"
LOG_DIR="backend/logs"
LOG_FILE="${LOG_DIR}/server.log"
MANAGER_PID=""
SERVER_PID=""
APP_PROFILE_DIR="${APP_PROFILE_DIR:-}"
mkdir -p "${LOG_DIR}"

# 启动管理器（负责拉起/重启服务）
is_listening() {
  local port="$1"
  lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
}

wait_port() {
  local port="$1"
  local retries="${2:-50}"
  for _ in $(seq 1 "${retries}"); do
    if is_listening "${port}"; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

trigger_restart() {
  python3 - <<'PY' >/dev/null 2>&1 || true
import urllib.request, time
for _ in range(3):
    try:
        req = urllib.request.Request("http://127.0.0.1:8010/restart", method="POST")
        urllib.request.urlopen(req, timeout=2).read()
        break
    except Exception:
        time.sleep(0.5)
PY
}

ensure_manager() {
  if ! is_listening 8010; then
    python3 backend/scripts/manager.py &
    MANAGER_PID=$!
  fi
  wait_port 8010 20 || true
}

ensure_server() {
  if is_listening 8000; then
    return 0
  fi
  trigger_restart
  if wait_port 8000 50; then
    return 0
  fi
  echo "Server did not start on port 8000 (via manager)."
  echo "Fallback: starting server directly..."
  python3 backend/scripts/server.py --no-browser > "${LOG_FILE}" 2>&1 &
  SERVER_PID=$!
  wait_port 8000 50
}

ensure_manager
ensure_server || true

# 确保脚本退出时清理服务
cleanup() {
  if [ -n "$MANAGER_PID" ]; then
    kill $MANAGER_PID >/dev/null 2>&1
  fi
  if [ -n "$SERVER_PID" ]; then
    kill $SERVER_PID >/dev/null 2>&1
  fi
  lsof -ti tcp:8000 | xargs kill >/dev/null 2>&1
  if [ -n "$APP_PROFILE_DIR" ] && [ -d "$APP_PROFILE_DIR" ]; then
    rm -rf "$APP_PROFILE_DIR"
  fi
}
trap cleanup EXIT

if ! is_listening 8000; then
  echo "Server did not start on port 8000."
  echo "Tip: macOS 可能限制监听 0.0.0.0，已默认使用 SERVER_HOST=127.0.0.1"
  if [ -f "${LOG_FILE}" ]; then
    echo "---- server.log ----"
    tail -n 50 "${LOG_FILE}"
    echo "--------------------"
  fi
  exit 1
fi

APP_URL="http://localhost:8000"

# 直接用默认浏览器打开
python3 -c "import webbrowser; webbrowser.open('${APP_URL}')"

# 保持脚本运行，直到用户手动结束
if [ -n "$MANAGER_PID" ]; then
  wait $MANAGER_PID
else
  tail -f /dev/null
fi
