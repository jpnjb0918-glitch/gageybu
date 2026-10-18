#!/usr/bin/env bash
# .deb 와 .rpm 을 한 번에 만들기
#   packaging/build-packages.sh [출력폴더]      (기본: dist/)
# 필요: dpkg-deb (deb), cargo (rpm — rpmbuild 없이 rpm-builder 로 만듦)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$HERE/dist}"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$HERE/gagyebu/__init__.py")"

bash "$HERE/packaging/build-deb.sh" "$OUT"          # $OUT/stage 도 만들어 둠

if command -v cargo >/dev/null 2>&1; then
    cargo build --release -q --manifest-path "$HERE/packaging/rpm-builder/Cargo.toml" \
          --target-dir "$OUT/rpm-builder-target"
    "$OUT/rpm-builder-target/release/rpm-builder" build "$OUT/stage" "$VERSION" \
          "$OUT/gagyebu-linux-$VERSION-1.noarch.rpm"
else
    echo "cargo 가 없어 .rpm 은 건너뜀 (sudo apt install cargo)"
fi
rm -rf "$OUT/stage"
