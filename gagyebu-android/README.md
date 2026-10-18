# 우리집 가계부 — 안드로이드판 (원본 묶음)

PC판 `gagyebu-linux`(파이썬·PyQt6)와 같은 SQLite 자료 파일을 쓰는 안드로이드 앱입니다.

- **화면**: 앱 안의 웹 페이지(`app/assets/www`)로 그립니다.
- **자료 저장**: `NativeBridge.java`가 안드로이드 SQLite 파일 `gagyebu.sqlite3`에 저장합니다.
- **계산 규칙**: PC판 `gagyebu/services/*.py`를 그대로 옮겼습니다 (`www/js/svc.js`).

## 폴더

| 경로 | 내용 |
|---|---|
| `app/AndroidManifest.xml`, `app/res/` | 앱 정보·아이콘·테마 (최소 API 24, 대상 API 34) |
| `app/src/kr/gagyebu/mobile/MainActivity.java` | 웹 화면 띄우기, 뒤로 버튼, 파일 선택 결과 전달 |
| `app/src/kr/gagyebu/mobile/NativeBridge.java` | JS가 부르는 기능: SQL 실행, 묶음 저장, 암호 계산, 파일 내보내기·가져오기, 자동 보관, 기기 설정 |
| `app/stubs/` | 컴파일할 때만 쓰는 빈 껍데기 (API 26 클래스 이름) — APK에는 안 들어감 |
| `app/src/kr/gagyebu/mobile/Pure.java` | 안드로이드에 기대지 않는 계산 (PBKDF2, 문자셋) — PC 자바로 시험 가능 |
| `app/assets/www/js/db.js` | 표 구조(PC판 `db.py`와 같음)·처음 자료·설정 값 |
| `app/assets/www/js/svc.js` | 장부·예약·결산·자산·일정·CSV·암호 (PC판 서비스 이식) |
| `app/assets/www/js/pages-*.js` | 화면들 |
| `app/assets/www/js/lib/korean-lunar-calendar.js` | 음력 계산 (MIT, PC판과 같은 저자·자료) |
| `app/assets/www/fonts/` | 갈무리11 글꼴 (OFL, 한글·영문만 남기고 줄인 woff2) |
| `app/assets/www/img/stickers/` | 고양이 스티커 (PC판과 같음) |
| `build-apk.sh` | APK 만들기 (Gradle 없이) |
| `packaging/gagyebu-release.jks`, `keystore-password.txt` | 서명 키 — **업데이트하려면 꼭 보관**. git 저장소에는 올리지 않음(`.gitignore`) |
| `devtools/` | 시험 도구 (APK에는 안 들어감) |

## APK 만들기 (우분투·쿠분투)

```sh
sudo apt install default-jdk android-sdk-platform-23 aapt apksigner zipalign dalvik-exchange
./build-apk.sh            # → dist/우리집가계부-안드로이드-<버전>.apk
```

- 버전은 `app/AndroidManifest.xml`의 `versionCode`·`versionName`에서 정합니다. 업데이트할 때 `versionCode`를 1씩 올리세요.
- 서명 키가 없으면 새로 만듭니다. 그러면 이미 설치된 앱 위에 덮어 설치가 안 됩니다.

## 시험

```sh
cd devtools && npm install sql.js korean-lunar-calendar     # 시험용 SQLite(웹어셈블리)
python3 smoke.py              # 모든 화면이 오류 없이 그려지는지 + 화면 사진(shots/)
python3 e2e.py                # 화면을 눌러 입력·수정·예약·카드·내보내기·가져오기·암호 확인
python3 compat/run.py         # PC판 파이썬 코드와 계산 결과 비교 (../gagyebu-linux 필요)
```

- 브라우저 시험은 `devtools/fake-native.js`가 `NativeBridge`와 같은 함수들을 sql.js로 흉내 냅니다.
- 시험에는 Playwright(파이썬)와 크로미움이 필요합니다.
