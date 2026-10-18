#!/usr/bin/env bash
# .deb 패키지 만들기 (dpkg-deb 만 있으면 됨)
#   packaging/build-deb.sh [출력폴더]
# 같은 배치(stage)를 rpm 도구(packaging/rpm-builder)도 그대로 사용한다.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$HERE/dist}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$HERE/gagyebu/__init__.py")"
PKG=gagyebu-linux
STAGE="$OUT/stage"

rm -rf "$STAGE"
mkdir -p "$STAGE/usr/share/$PKG" "$STAGE/usr/bin" "$STAGE/usr/share/applications" "$STAGE/usr/share/doc/$PKG"

# 프로그램 (파이썬 패키지)
cp -r "$HERE/gagyebu" "$STAGE/usr/share/$PKG/"
find "$STAGE" -name '__pycache__' -prune -exec rm -rf {} +

# 실행 명령
cat > "$STAGE/usr/bin/gagyebu" <<'EOF'
#!/bin/sh
# 우리집 가계부 (리눅스판)
PYTHONPATH="/usr/share/gagyebu-linux${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
exec /usr/bin/python3 -m gagyebu "$@"
EOF

# 앱 메뉴 + 아이콘
cat > "$STAGE/usr/share/applications/$PKG.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=우리집 가계부 (리눅스판)
Comment=가계부·자산·일정 관리 (윈도우 우리집 가계부 대체)
Exec=gagyebu
Icon=gagyebu-linux
Categories=Office;Finance;
Terminal=false
StartupWMClass=gagyebu-linux
EOF
for n in 48 64 128 256; do
    mkdir -p "$STAGE/usr/share/icons/hicolor/${n}x${n}/apps"
    cp "$HERE/packaging/icons/$PKG-$n.png" "$STAGE/usr/share/icons/hicolor/${n}x${n}/apps/$PKG.png"
done

# 문서·저작권
cp "$HERE/README.md" "$STAGE/usr/share/doc/$PKG/README.md"
cp "$HERE/사용가이드.txt" "$STAGE/usr/share/doc/$PKG/사용가이드.txt"
cat > "$STAGE/usr/share/doc/$PKG/copyright" <<EOF
우리집 가계부 (리눅스판) $VERSION
윈도우용 '우리집 가계부'의 자료 구조·동작을 분석해 새로 작성한 프로그램입니다.

포함된 외부 코드·자료:
  gagyebu/vendor/korean_lunar_calendar.py — MIT License
$(sed 's/^/    /' "$HERE/gagyebu/vendor/LICENSE.korean_lunar_calendar")

  gagyebu/assets/fonts/Galmuri11*.ttf — 갈무리(Galmuri) 도트 글꼴, SIL Open Font License 1.1
    전문: /usr/share/gagyebu-linux/gagyebu/assets/fonts/OFL-Galmuri.txt

  gagyebu/assets/stickers/*.png, gagyebu/assets/icon.png — 사용자가 제공한 고양이 스티커 시트에서 오려 낸 그림.
    개인 사용 목적으로 넣은 것이며, 다른 사람에게 배포할 때의 이용 허락은 그림을 그린 분들께 확인 필요.
EOF

# 권한 정리 (파일 644, 폴더·실행파일 755)
find "$STAGE" -type d -exec chmod 755 {} +
find "$STAGE" -type f -exec chmod 644 {} +
chmod 755 "$STAGE/usr/bin/gagyebu"

# ── deb ──
DEB="$OUT/debroot"
rm -rf "$DEB"
cp -a "$STAGE" "$DEB"
mkdir -p "$DEB/DEBIAN"
SIZE=$(du -sk --exclude=DEBIAN "$DEB" | cut -f1)
cat > "$DEB/DEBIAN/control" <<EOF
Package: $PKG
Version: $VERSION
Section: misc
Priority: optional
Architecture: all
Installed-Size: $SIZE
Depends: python3 (>= 3.10), python3-pyqt6
Recommends: mdbtools, libqt6svg6, qt6-translations-l10n
Maintainer: gagyebu-linux local build <noreply@localhost>
Description: 우리집 가계부 (리눅스판) - 가계부·자산·일정 관리
 윈도우용 '우리집 가계부 v5.75'를 대체하는 리눅스 프로그램입니다.
 가계부(잔액·검색·결산 보고서·그래프·예산·예약 자동입력), 자산관리(통장·카드·
 증권·보험·부동산), 일정(음력·기념일), 주소록·일기장·메모장을 지원하며
 윈도우판의 data 폴더(*.mdb)를 가져올 수 있습니다 (mdbtools 필요).
 데이터는 사용자별로 ~/.local/share/gagyebu 에 저장되며 패키지를 지워도 남습니다.
EOF
cat > "$DEB/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q /usr/share/applications || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -q -t /usr/share/icons/hicolor || true
fi
exit 0
EOF
cp "$DEB/DEBIAN/postinst" "$DEB/DEBIAN/postrm"
sed -i 's/if \[ "\$1" = "configure" \]; then/if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then/' "$DEB/DEBIAN/postrm"
cat > "$DEB/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
# 실행 중 생긴 파이썬 캐시(__pycache__)는 패키지 파일이 아니라서 따로 지움
find /usr/share/gagyebu-linux -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
exit 0
EOF
chmod 755 "$DEB/DEBIAN/postinst" "$DEB/DEBIAN/postrm" "$DEB/DEBIAN/prerm"
dpkg-deb --root-owner-group --build "$DEB" "$OUT/${PKG}_${VERSION}_all.deb"
rm -rf "$DEB"
echo "만듦: $OUT/${PKG}_${VERSION}_all.deb"
