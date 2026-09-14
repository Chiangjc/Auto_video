#!/bin/bash
# 停掉 auto_video 本機網頁介面。
set -euo pipefail

PIDS="$(pgrep -f 'webui/app.py' || true)"
if [ -z "$PIDS" ]; then
  echo "沒有在執行的 webui。"
  exit 0
fi

echo "$PIDS" | xargs kill
echo "已停止: $PIDS"
