#!/usr/bin/env bash
# APK + 가이드 + 원본 묶음(.tar.gz)을 dist/ 에 만든다
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$HERE/build-apk.sh" "$HERE/dist"
cp "$HERE/안드로이드_설치·사용가이드.md" "$HERE/dist/"
tar -C "$(dirname "$HERE")" -czf "$HERE/dist/gagyebu-android-원본.tar.gz" \
    --exclude='gagyebu-android/dist' --exclude='gagyebu-android/devtools/node_modules' \
    --exclude='gagyebu-android/devtools/shots' --exclude='gagyebu-android/devtools/compat/out' \
    --exclude='__pycache__' gagyebu-android
ls -la "$HERE/dist"
