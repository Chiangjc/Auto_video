#!/bin/bash
# 啟動 auto_video 本機網頁介面(背景執行,不佔用終端機視窗)。
# 由桌面的 Auto_video.app 呼叫,也可以自己在終端機直接跑。
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# 從桌面 .app 啟動時,AppleScript 給的 PATH 很精簡(不含 Homebrew),
# 會導致找不到 ffmpeg / ffprobe。這裡補回常見安裝路徑。
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

URL="http://127.0.0.1:5001"
LOG="${TMPDIR:-/tmp}/auto_video_webui.log"

# 已經在跑就直接結束
if curl -s -o /dev/null --max-time 2 "$URL"; then
  echo "already-running"
  exit 0
fi

if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
else
  echo "找不到 python3,也沒有 .venv" >&2
  exit 1
fi

# nohup + & 讓伺服器脫離父行程,關掉 app 之後仍持續執行
nohup "$PY" webui/app.py >> "$LOG" 2>&1 &
echo "started pid $! (log: $LOG)"
