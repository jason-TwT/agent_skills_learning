#!/bin/bash
# 启动管理器（负责拉起/重启服务）
if ! lsof -nP -iTCP:8010 -sTCP:LISTEN >/dev/null 2>&1; then
  python3 backend/scripts/manager.py &
  MANAGER_PID=$!
fi

# 确保脚本退出时清理服务
cleanup() {
  if [ -n "$MANAGER_PID" ]; then
    kill $MANAGER_PID >/dev/null 2>&1
  fi
  lsof -ti tcp:8000 | xargs kill >/dev/null 2>&1
  if [ -n "$APP_PROFILE_DIR" ] && [ -d "$APP_PROFILE_DIR" ]; then
    rm -rf "$APP_PROFILE_DIR"
  fi
}
trap cleanup EXIT

# 等待服务器启动（最多 10 秒）
for i in {1..50}; do
  if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

if ! lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Server did not start on port 8000."
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
