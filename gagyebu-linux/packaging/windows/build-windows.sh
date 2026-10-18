#!/usr/bin/env bash
# 윈도우판 만들기 (우분투에서): 설치 프로그램(setup.exe) + 휴대용 zip
#   packaging/windows/build-windows.sh <python-3.12.x-embed-amd64.zip> [출력폴더]
# 필요: mingw-w64, nsis, python3(+pip, Pillow), zip  — mdbtools 윈도우판이 없으면 build-mdbtools-win.sh 도 실행
# 임베디드 파이썬 zip 은 python.org 의 "Windows embeddable package (64-bit)"
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
EMBED="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
OUT="$(mkdir -p "${2:-$ROOT/dist-windows}" && cd "${2:-$ROOT/dist-windows}" && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/gagyebu/__init__.py")"
IFS=. read -r V1 V2 V3 <<< "$VERSION"
B="$OUT/build"
mkdir -p "$B"

echo "[1/6] PyQt6 윈도우 휠 받기"
# 1.1.1 배포판을 만든 버전으로 고정 (바꾸려면 환경변수로)
PYQT6_VERSION="${PYQT6_VERSION:-6.11.0}"
PYQT6_QT6_VERSION="${PYQT6_QT6_VERSION:-6.11.2}"
PYQT6_SIP_VERSION="${PYQT6_SIP_VERSION:-13.13.0}"
mkdir -p "$B/wheels"
ls "$B"/wheels/pyqt6-*.whl >/dev/null 2>&1 || python3 -m pip download -q --no-deps --only-binary=:all: \
    --platform win_amd64 --python-version 3.12 --implementation cp -d "$B/wheels" \
    "PyQt6==$PYQT6_VERSION" "PyQt6-Qt6==$PYQT6_QT6_VERSION" "PyQt6-sip==$PYQT6_SIP_VERSION"
ls "$B/wheels"

echo "[2/6] mdbtools 윈도우판"
[ -f "$B/mdbtools/mdb-export.exe" ] || bash "$HERE/build-mdbtools-win.sh" "$B/mdbtools"

echo "[3/6] 실행기(우리집가계부.exe)"
python3 - "$ROOT/gagyebu/assets/icon.png" "$B/gagyebu.ico" <<'EOF'
import sys
from PIL import Image
Image.open(sys.argv[1]).convert('RGBA').save(sys.argv[2], sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
EOF
cp "$HERE/app.manifest" "$B/"
sed -e "s/@V1@/$V1/g; s/@V2@/$V2/g; s/@V3@/$V3/g; s/@VERSION@/$VERSION/g" "$HERE/launcher.rc.in" > "$B/launcher.rc"
(cd "$B" && x86_64-w64-mingw32-windres -O coff -i launcher.rc -o launcher.res)
x86_64-w64-mingw32-gcc -municode -mwindows -O2 -Wall -s "$HERE/launcher.c" "$B/launcher.res" -o "$B/우리집가계부.exe"

echo "[4/6] 폴더 만들기"
python3 "$HERE/assemble.py" --embed "$EMBED" --wheels "$B/wheels" --mdbtools "$B/mdbtools" \
    --launcher "$B/우리집가계부.exe" --guide "$ROOT/사용가이드.txt" --out "$B/Gagyebu"

echo "[5/6] 설치 프로그램 (NSIS)"
LC_ALL=C.UTF-8 makensis -V2 -INPUTCHARSET UTF8 -DVERSION="$VERSION" -DSRC="$B/Gagyebu" -DICON="$B/gagyebu.ico" \
    -DOUTFILE="$OUT/우리집가계부-윈도우판-$VERSION-setup.exe" "$HERE/installer.nsi"

echo "[6/6] 휴대용 zip (설치 없이 압축만 풀어 실행)"
rm -rf "$B/portable" && mkdir -p "$B/portable"
cp -a "$B/Gagyebu" "$B/portable/우리집가계부-윈도우판-$VERSION"
# 파이썬 zipfile 로 묶음: 한글 파일 이름에 UTF-8 표시가 붙어 윈도우 기본 압축 풀기에서도 이름이 안 깨짐
# (zip 명령은 환경에 따라 이 표시를 안 붙임)
rm -f "$OUT/우리집가계부-윈도우판-$VERSION-휴대용.zip"
python3 - "$B/portable" "$OUT/우리집가계부-윈도우판-$VERSION-휴대용.zip" <<'EOF'
import os
import sys
import zipfile
src, dst = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for root, dirs, files in os.walk(src):
        dirs.sort()
        for name in dirs + sorted(files):
            p = os.path.join(root, name)
            z.write(p, os.path.relpath(p, src))
EOF
ls -la "$OUT"
