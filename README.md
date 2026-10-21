# 우리집 가계부

윈도우용 **우리집 가계부 v5.75**(2009, VB6)를 새로 만든 프로그램 모음입니다. 세 판 모두 같은 자료 파일(`gagyebu.sqlite3`)을 씁니다.

| 폴더 | 내용 | 버전 |
|---|---|---|
| [`gagyebu-linux/`](gagyebu-linux/README.md) | PC판 (파이썬·PyQt6) — 리눅스 deb/rpm, 윈도우 설치 프로그램 | 1.8.0 |
| [`gagyebu-android/`](gagyebu-android/README.md) | 안드로이드판 (웹 화면 + 자바) — APK | 1.7.0 |

두 폴더는 나란히 있어야 합니다. 안드로이드판 호환 시험(`gagyebu-android/devtools/compat/run.py`)이 `../gagyebu-linux`의 PC판 코드로 계산 결과를 비교합니다.

## 저장소에 넣지 않는 것 (`.gitignore`)

| 무엇 | 왜 |
|---|---|
| `gagyebu-android/packaging/gagyebu-release.jks`, `keystore-password.txt` | 앱 서명 키. 남이 가지면 같은 앱인 척 업데이트를 만들 수 있음 → **따로 보관** |
| `dist/`, `dist-windows/`, `*.apk` `*.deb` `*.rpm` `*.exe` `*.zip` | 빌드 결과물 → GitHub **Releases**에 올림 |
| `*.sqlite3`, `*.mdb` | 개인 가계부 자료 |
| `node_modules/`, `__pycache__/`, 시험 화면 사진·출력 | 다시 만들 수 있는 것 |

서명 키가 없는 곳에서 `build-apk.sh`를 돌리면 새 키를 만듭니다. 그 APK는 이미 설치된 앱 위에 덮어 설치되지 않으니, 업데이트용 APK는 원래 키가 있는 곳에서 만드세요.

## GitHub Actions 로 배포 파일 만들기

| 작업 | 언제 | 결과 |
|---|---|---|
| 안드로이드 APK (`android-apk.yml`) | `main`에 `gagyebu-android/` 변경을 올릴 때 | **Artifacts**에 APK |
| | `android-v<버전>` 릴리스를 **Publish** 할 때 | 그 릴리스에 APK·가이드 |
| PC판 (`pc-packages.yml`) | `main`에 `gagyebu-linux/` 변경을 올릴 때 | **Artifacts**에 deb·rpm·윈도우 설치 프로그램·휴대용 zip |
| | `linux-v<버전>` 릴리스를 **Publish** 할 때 | 그 릴리스에 위 파일·사용가이드 |
| 둘 다 | Actions 화면에서 **Run workflow** | 태그를 넣으면 그 릴리스에 다시 붙임, 비우면 빌드만 |

- **첨부 파일 이름**: GitHub이 한글 파일 이름을 바꿔 버려서 영문 이름(`gagyebu-…`)으로 붙이고, 화면에 보이는 이름표를 한글로 붙입니다.
- **다시 붙일 때**: 그 릴리스의 기존 첨부 파일을 지우고 새로 붙입니다.

### 안드로이드 APK 서명

- **필요한 저장소 시크릿**: `ANDROID_KEYSTORE_BASE64`(서명 키를 base64로 바꾼 한 줄), `ANDROID_KEYSTORE_PASSWORD`(키 암호 첫 줄)
- **멈추는 경우**
  - 시크릿이 없을 때
  - 시크릿 값이 틀릴 때
  - 1.0.0과 다른 키로 서명되었을 때 (인증서 SHA-256 `872f5656…964b`로 비교)
  - 릴리스 태그가 `versionName`과 다를 때

## 버전 표시

| 판 | 버전을 정하는 곳 | 태그 |
|---|---|---|
| PC판 | `gagyebu-linux/gagyebu/__init__.py`의 `__version__` | `linux-v1.1.1` |
| 안드로이드판 | `gagyebu-android/app/AndroidManifest.xml`의 `versionName`·`versionCode` | `android-v1.0.0` |
