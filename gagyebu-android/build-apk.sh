#!/usr/bin/env bash
# 우리집 가계부 안드로이드판 APK 만들기 (Gradle 없이, 우분투 패키지만으로)
#   sudo apt install android-sdk-platform-23 aapt apksigner zipalign dalvik-exchange default-jdk
#   ./build-apk.sh [출력폴더]
# 서명 키(packaging/gagyebu-release.jks)는 처음 한 번 만들어지고, 업데이트할 때 같은 키가 있어야
# 휴대폰에 '덮어 설치'가 됩니다 (다른 키면 지웠다 다시 깔아야 하고 그때 자료가 지워짐). 꼭 보관하세요.
set -euo pipefail
unset JAVA_TOOL_OPTIONS || true

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="${1:-$HERE/dist}"
APP="$HERE/app"
AJ="${ANDROID_JAR:-/usr/lib/android-sdk/platforms/android-23/android.jar}"
VERSION="$(sed -n 's/.*android:versionName="\([^"]*\)".*/\1/p' "$APP/AndroidManifest.xml")"
KS="$HERE/packaging/gagyebu-release.jks"
PWFILE="$HERE/packaging/keystore-password.txt"
B="$OUT/build"

for t in aapt javac dalvik-exchange zipalign apksigner keytool; do
    command -v "$t" >/dev/null || { echo "필요한 도구가 없습니다: $t"; exit 1; }
done
[ -f "$AJ" ] || { echo "android.jar 가 없습니다: $AJ (android-sdk-platform-23 패키지)"; exit 1; }

rm -rf "$B"
mkdir -p "$B/gen" "$B/obj" "$OUT"

# 1) 자원 → R.java
aapt package -f -m -J "$B/gen" -M "$APP/AndroidManifest.xml" -S "$APP/res" -I "$AJ"
# 2) 자바 → 클래스 → dex
#    (API 26 에만 있는 클래스 이름은 stubs/ 의 빈 껍데기로 컴파일만 하고 dex 에는 넣지 않음)
mkdir -p "$B/stubs"
javac -Xlint:-options -source 8 -target 8 -encoding UTF-8 -bootclasspath "$AJ" -d "$B/stubs" \
      $(find "$APP/stubs" -name '*.java')
javac -Xlint:-options -source 8 -target 8 -encoding UTF-8 -bootclasspath "$AJ" -classpath "$B/stubs" -d "$B/obj" \
      $(find "$APP/src" "$B/gen" -name '*.java')
dalvik-exchange --dex --min-sdk-version=24 --output="$B/classes.dex" "$B/obj"
# 3) 묶기 (resources.arsc 는 압축하지 않음: 안드로이드 11+ 요구)
aapt package -f -M "$APP/AndroidManifest.xml" -S "$APP/res" -A "$APP/assets" -I "$AJ" -F "$B/unsigned.apk" -0 arsc
( cd "$B" && aapt add unsigned.apk classes.dex >/dev/null )
zipalign -f -p 4 "$B/unsigned.apk" "$B/aligned.apk"

# 4) 서명
mkdir -p "$HERE/packaging"
if [ ! -f "$KS" ]; then
    PW="$(head -c 18 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 20)"
    printf '%s\n' "$PW" > "$PWFILE"
    keytool -genkeypair -keystore "$KS" -storepass "$PW" -keypass "$PW" -alias gagyebu -keyalg RSA -keysize 3072 \
            -validity 36500 -dname "CN=Uri-jip Gagyebu (personal build)" >/dev/null 2>&1
    echo "새 서명 키를 만들었습니다: $KS (암호: $PWFILE)"
fi
PW="$(head -n1 "$PWFILE")"
APK="$OUT/우리집가계부-안드로이드-$VERSION.apk"
# (자바 도구는 한글 파일 이름을 깨뜨릴 수 있어 영문 이름으로 서명한 뒤 옮김)
apksigner sign --v4-signing-enabled false --ks "$KS" --ks-pass "pass:$PW" --key-pass "pass:$PW" --ks-key-alias gagyebu \
          --out "$B/signed.apk" "$B/aligned.apk"
apksigner verify "$B/signed.apk"
mv -f "$B/signed.apk" "$APK"
rm -rf "$B"
echo "만듦: $APK ($(du -h "$APK" | cut -f1))"
