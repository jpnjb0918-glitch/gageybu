#!/usr/bin/env bash
# 우리집 가계부 (리눅스판) 제거. 데이터는 기본으로 남겨 둡니다.
#   ./uninstall.sh           프로그램만 제거 (데이터 유지)
#   ./uninstall.sh --purge   데이터도 삭제 (먼저 홈 폴더에 백업 사본을 만듦)
set -euo pipefail
APPDIR="${XDG_DATA_HOME:-$HOME/.local/share}/gagyebu-app"
DATADIR="${XDG_DATA_HOME:-$HOME/.local/share}/gagyebu"
rm -rf "$APPDIR"
rm -f "$HOME/.local/bin/gagyebu" "${XDG_DATA_HOME:-$HOME/.local/share}/applications/gagyebu-linux.desktop"
echo "프로그램을 제거했습니다."
if [ "${1:-}" = "--purge" ] && [ -d "$DATADIR" ]; then
  BK="$HOME/우리집가계부_데이터_$(date +%Y%m%d-%H%M%S)"
  cp -a "$DATADIR" "$BK"
  rm -rf "$DATADIR"
  echo "데이터를 삭제했습니다. 백업 사본: $BK"
else
  echo "데이터는 그대로 있습니다: $DATADIR"
fi
