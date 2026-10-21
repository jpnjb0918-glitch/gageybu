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
| `app/src/kr/gagyebu/mobile/Pure.java` | 안드로이드에 기대지 않는 계산 (PBKDF2, 문자셋, 위젯의 월 시작일 기준 기간) — PC 자바로 시험 가능 |
| `app/src/kr/gagyebu/mobile/GagyebuWidget.java`, `app/res/layout/widget.xml`, `app/res/xml/widget_info.xml` | 홈 화면 위젯 '가계부 한눈에' (1.6.0) |
| `app/src/kr/gagyebu/mobile/CaptureProvider.java` | 영수증 사진 찍기: 사진기 앱이 사진을 써 넣을 곳 (1.6.0) |
| `app/src/kr/gagyebu/mobile/Reminder.java`, `ReminderReceiver.java`, `app/res/drawable/ic_notify.xml` | 매일 입력 알림: 알람 걸기·그날 내역 확인·알림 보내기, 휴대폰을 켜거나 업데이트하면 다시 걸기 (1.7.0) |
| `app/assets/www/js/db.js` | 표 구조(PC판 `db.py`와 같음)·처음 자료·설정 값 |
| `app/assets/www/js/svc.js` | 가계부·고정 수입·지출·통계·자산·일정·CSV·암호 (PC판 서비스 이식) |
| `app/assets/www/js/svc-extra.js` | 1.6.0 기능 계산: 문자 읽기·자주 쓰는 내역·태그·예산 진행/알림·이달 리포트·무지출·저축 목표·빌린 돈·사진 (PC판 smsparse·insights·goals·attach) |
| `app/assets/www/js/svc-money.js` | 1.7.0 기능 계산: 결제수단·나눠 적기·외화·같은 곳·주간 예산·저축 추이·고정비·전체 예산·달력 돈 일정·카드 실적·휴지통·카테고리 그림 (PC판 money·trash·catemoji) |
| `app/assets/www/js/pages-*.js` | 화면들 (`pages-money.js` = 1.7.0 기능 화면) |
| `app/assets/www/js/lib/korean-lunar-calendar.js` | 음력 계산 (MIT, PC판과 같은 저자·자료) |
| `app/assets/www/fonts/` | 갈무리11 글꼴 (OFL, 한글·영문만 남기고 줄인 woff2) |
| `app/assets/www/img/stickers/` | 아늑단 이미지 (PC판과 같음) |
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
python3 e2e.py                # 화면을 눌러 입력·수정·고정 수입·지출·카드·내보내기·가져오기·암호 확인
python3 themes.py             # 테마 8개 × 화면 여러 개 사진·가로 넘침 확인
python3 order_colors.py       # 순서 바꾸기(끌기·▲▼)·테마 색 바꾸기
python3 graph_month.py        # 그래프 종류 8가지·연월 바로 고르기 (shots/graph/)
python3 update_flow.py        # 새 버전 알림·내려받기·설치 흐름 (가짜 릴리스 목록, shots/update/)
python3 ledger_font.py        # 기본 가계부·목록에서 새 가계부·글자 크기 1px (shots/ledger/)
python3 sns_ui.py             # 피드·타임라인 아이콘·탭·동그라미, 무료 한글 글꼴 (shots/sns/)
python3 tables.py             # 테마별 표(통계·그래프): 머리줄·첫 칸 고정, 색·줄무늬·0 흐리게 (shots/tables/)
python3 visibility.py         # 화면 전체 가시성: 잘림·글자 대비·입력칸 테두리·＋ 단추·달력·그래프 (shots/vis/)
python3 features170.py        # 1.6.0 새 기능 12가지: 계산기·★·문자·사진·예산·이체·목표·빌린 돈·리포트·태그·무지출·위젯 열기 (shots/f170/)
python3 category_delete.py     # 1.7.0 세부 카테고리 지우기(안 쓴 것·옮기고 삭제·모두 삭제)·카테고리 지우기·바뀐 이름
python3 features180.py        # 1.7.0 사람들이 바란 기능 14가지: 결제수단·외화·나눠 적기·같은 곳·휴지통·전체/주간 예산·매주/매년·고정비·통계·달력·그림·알림 (shots/f180/)
python3 perf.py [내역 수]      # 속도: 켜기·테마마다 가계부·화면 이동·검색·통계 (가짜 저장소라 DB 시간은 실제와 다름)
python3 compat/run.py         # PC판 파이썬 코드와 계산 결과 비교 (../gagyebu-linux 필요)
```

- 브라우저 시험은 `devtools/fake-native.js`가 `NativeBridge`와 같은 함수들을 sql.js로 흉내 냅니다.
- 시험에는 Playwright(파이썬)와 크로미움이 필요합니다.
