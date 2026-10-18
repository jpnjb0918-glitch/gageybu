#!/usr/bin/env bash
# 우리집 가계부 (리눅스판) 설치 — Kubuntu / Ubuntu 24.04 이상
#   ./install.sh                         설치
#   ./install.sh --import-data <폴더>    윈도우 '우리집 가계부\data' 폴더까지 가져오기
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APPDIR="${XDG_DATA_HOME:-$HOME/.local/share}/gagyebu-app"
BINDIR="$HOME/.local/bin"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
IMPORT_DIR=""
SKIP_APT=0

usage() {
  cat <<EOF
사용법: ./install.sh [--import-data <윈도우 data 폴더>] [--skip-apt]

  --import-data <폴더>  윈도우에서 쓰던 data 폴더(main.mdb 등)를 가져옴 (현재 데이터는 자동 보관)
  --skip-apt            필요한 패키지 설치를 건너뜀 (직접 설치한 경우)

필요한 패키지: python3-pyqt6 (화면), libqt6svg6 (아이콘), mdbtools (윈도우 자료 읽기)
데이터 위치: ~/.local/share/gagyebu/gagyebu.sqlite3  (다시 설치하거나 지워도 남음)
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --import-data) IMPORT_DIR="${2:-}"; [ -n "$IMPORT_DIR" ] || { echo "--import-data 뒤에 폴더를 적어주세요"; exit 1; }; shift 2 ;;
    --skip-apt) SKIP_APT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "알 수 없는 옵션: $1"; usage; exit 1 ;;
  esac
done

die() { printf '\n\033[31m오류: %s\033[0m\n' "$*" >&2; exit 1; }
step() { printf '\n\033[1m[%s] %s\033[0m\n' "$1" "$2"; }
[ "$(id -u)" != 0 ] || [ -n "${GAGYEBU_ALLOW_ROOT:-}" ] || die "sudo 없이 일반 사용자로 실행하세요: ./install.sh"

step 1/4 "필요한 패키지 확인"
pkg_ok() { dpkg-query -W -f='${Status}' "$1" 2>/dev/null | grep -q "install ok installed"; }
need=()
for p in python3 python3-pyqt6 libqt6svg6 qt6-translations-l10n mdbtools; do pkg_ok "$p" || need+=("$p"); done
# libqt6svg6: 아이콘(SVG) 표시, qt6-translations-l10n: 확인/취소 같은 기본 버튼 한국어
if [ ${#need[@]} -gt 0 ]; then
  if [ "$SKIP_APT" = 1 ]; then
    echo "  없는 패키지가 있지만 --skip-apt 라서 건너뜀: ${need[*]}"
  else
    echo "  설치할 패키지: ${need[*]}  (sudo 비밀번호를 물어볼 수 있습니다)"
    sudo apt-get update
    sudo apt-get install -y "${need[@]}"
  fi
else
  echo "  모두 설치되어 있음"
fi
python3 -c 'import PyQt6.QtWidgets, PyQt6.QtPrintSupport' 2>/dev/null \
  || die "python3 에서 PyQt6 를 불러올 수 없습니다. 'sudo apt install python3-pyqt6' 를 확인하세요."

step 2/4 "프로그램 복사: $APPDIR"
rm -rf "$APPDIR"
mkdir -p "$APPDIR"
cp -r "$HERE/gagyebu" "$APPDIR/"
find "$APPDIR" -name '__pycache__' -prune -exec rm -rf {} +
mkdir -p "$BINDIR"
cat > "$BINDIR/gagyebu" <<EOF
#!/usr/bin/env bash
# 우리집 가계부 (리눅스판) 실행
PYTHONPATH="$APPDIR" exec python3 -m gagyebu "\$@"
EOF
chmod +x "$BINDIR/gagyebu"
echo "  실행 명령: $BINDIR/gagyebu"

step 3/4 "앱 메뉴 등록"
mkdir -p "$APPS"
cat > "$APPS/gagyebu-linux.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=우리집 가계부 (리눅스판)
Comment=가계부·자산·일정 관리 (윈도우 우리집 가계부 대체)
Exec="$BINDIR/gagyebu"
Icon=$APPDIR/gagyebu/assets/icon.png
Categories=Office;Finance;
Terminal=false
StartupWMClass=gagyebu-linux
EOF
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" >/dev/null 2>&1 || true
echo "  앱 메뉴 → 사무 → 우리집 가계부 (리눅스판)"

step 4/4 "윈도우 자료 가져오기"
if [ -n "$IMPORT_DIR" ]; then
  [ -d "$IMPORT_DIR" ] || die "폴더가 없습니다: $IMPORT_DIR"
  "$BINDIR/gagyebu" --import-from "$IMPORT_DIR" --import-only
else
  echo "  지정 안 함 (나중에: 프로그램의 설정 → 자료 가져오기, 또는 ./install.sh --import-data <폴더>)"
fi

printf '\n\033[32m설치 완료.\033[0m 앱 메뉴에서 "우리집 가계부 (리눅스판)"을 실행하세요.\n'
case ":$PATH:" in *":$BINDIR:"*) ;; *) echo "(터미널에서 gagyebu 명령을 쓰려면 다시 로그인하세요)";; esac
