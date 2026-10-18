#!/usr/bin/env bash
# 윈도우용 mdbtools(mdb-export.exe, mdb-tables.exe) 만들기 — 우분투에서 MinGW 로 교차 빌드
#   packaging/windows/build-mdbtools-win.sh <출력폴더>
# 필요: sudo apt install mingw-w64 win-iconv-mingw-w64-dev autoconf automake libtool bison flex pkg-config dpkg-dev
#       + /etc/apt/sources.list.d/ubuntu.sources 의 Types 에 deb-src (apt-get source 용)
# 바꾼 점(mdbtools-win.patch): 표준출력 바이너리 모드(줄바꿈 변환 없음), 표를 "#번호"로 지정(한글 이름을 명령줄로 안 넘김),
#                             MinGW 에서 링크 시험이 깨지는 -no-undefined 제거
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$(mkdir -p "$1" && cd "$1" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"
apt-get source --download-only mdbtools >/dev/null
dpkg-source -x mdbtools_*.dsc src >/dev/null
cd src
patch -p1 < "$HERE/mdbtools-win.patch"
autoreconf -i -f >/dev/null 2>&1
./configure --host=x86_64-w64-mingw32 --disable-glib --disable-man --enable-static --disable-shared >/dev/null
grep -q 'HAVE_ICONV_H 1\|#define HAVE_ICONV 1' config.h include/mdbtools.h 2>/dev/null || echo "경고: iconv 를 찾지 못함 (한글이 깨질 수 있음)"
make -C src/libmdb -j"$(nproc)" CFLAGS="-O2 -Wall" >/dev/null
make -C src/util -j"$(nproc)" CFLAGS="-O2 -Wall" LDFLAGS="-static -static-libgcc -all-static" mdb-export.exe mdb-tables.exe >/dev/null
for f in mdb-export mdb-tables; do x86_64-w64-mingw32-strip -o "$OUT/$f.exe" "src/util/$f.exe"; done
cp COPYING.LIB "$OUT/COPYING.LIB.txt"
echo "만듦: $OUT/mdb-export.exe, mdb-tables.exe"
