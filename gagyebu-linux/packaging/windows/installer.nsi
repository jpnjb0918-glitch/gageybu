; 우리집 가계부 (윈도우판) 설치 프로그램 — NSIS 3 (리눅스의 makensis 로도 만들 수 있음)
;   makensis -DVERSION=1.1.0 -DSRC=<assemble.py 결과 폴더> -DOUTFILE=<setup.exe> -DICON=<gagyebu.ico> installer.nsi
; - 관리자 권한 없이 사용자 폴더(%LOCALAPPDATA%\Programs\Gagyebu)에 설치
; - 데이터(%APPDATA%\gagyebu)는 설치·업데이트·제거 어느 때도 건드리지 않음

Unicode true
!include "MUI2.nsh"

!define APPNAME "우리집 가계부"
!define SHORTCUT "우리집 가계부 (새 버전)"
!define EXE "우리집가계부.exe"
!define REGKEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\Gagyebu"

Name "${APPNAME} (윈도우판 ${VERSION})"
OutFile "${OUTFILE}"
InstallDir "$LOCALAPPDATA\Programs\Gagyebu"
InstallDirRegKey HKCU "Software\Gagyebu" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "${APPNAME} ${VERSION}"
VIProductVersion "${VERSION}.0"
VIAddVersionKey /LANG=1042 "ProductName" "${APPNAME} (윈도우판)"
VIAddVersionKey /LANG=1042 "FileDescription" "${APPNAME} 설치 프로그램"
VIAddVersionKey /LANG=1042 "FileVersion" "${VERSION}"
VIAddVersionKey /LANG=1042 "ProductVersion" "${VERSION}"
VIAddVersionKey /LANG=1042 "LegalCopyright" "개인 사용"

!define MUI_ICON "${ICON}"
!define MUI_UNICON "${ICON}"
!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TEXT "윈도우용 '우리집 가계부 v5.75'를 대신하는 새 프로그램을 설치합니다.$\r$\n$\r$\n\
- 예전 프로그램과 따로 설치되며, 예전 프로그램과 자료는 그대로 둡니다.$\r$\n\
- 예전 자료는 설치 후 [설정 → 자료 가져오기]에서 data 폴더를 고르면 옮겨집니다.$\r$\n\
- 처음 실행할 때 암호는 없습니다 (예전 자료를 가져오면 예전 암호, 바꾼 적 없으면 1111).$\r$\n$\r$\n\
자세한 내용은 설치 폴더의 '사용가이드.txt'를 보세요."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\${EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "지금 우리집 가계부 실행"
!define MUI_FINISHPAGE_SHOWREADME "$INSTDIR\사용가이드.txt"
!define MUI_FINISHPAGE_SHOWREADME_TEXT "사용 가이드 보기"
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Korean"

Section "install"
  ; 업데이트: 이전 버전의 프로그램 파일만 정리 (이 폴더에 우리 프로그램이 있을 때만)
  IfFileExists "$INSTDIR\${EXE}" 0 +4
    RMDir /r "$INSTDIR\runtime"
    RMDir /r "$INSTDIR\app"
    RMDir /r "$INSTDIR\tools"
  SetOutPath "$INSTDIR"
  File /r "${SRC}\*.*"
  WriteUninstaller "$INSTDIR\uninstall.exe"

  CreateDirectory "$SMPROGRAMS\${APPNAME}"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\${SHORTCUT}.lnk" "$INSTDIR\${EXE}"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\사용 가이드.lnk" "$INSTDIR\사용가이드.txt"
  CreateShortcut "$SMPROGRAMS\${APPNAME}\제거.lnk" "$INSTDIR\uninstall.exe"
  CreateShortcut "$DESKTOP\${SHORTCUT}.lnk" "$INSTDIR\${EXE}"

  WriteRegStr HKCU "Software\Gagyebu" "InstallDir" "$INSTDIR"
  WriteRegStr HKCU "${REGKEY}" "DisplayName" "${APPNAME} (윈도우판 새 버전)"
  WriteRegStr HKCU "${REGKEY}" "DisplayVersion" "${VERSION}"
  WriteRegStr HKCU "${REGKEY}" "Publisher" "${APPNAME}"
  WriteRegStr HKCU "${REGKEY}" "DisplayIcon" "$INSTDIR\${EXE}"
  WriteRegStr HKCU "${REGKEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${REGKEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
  WriteRegStr HKCU "${REGKEY}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
  WriteRegDWORD HKCU "${REGKEY}" "NoModify" 1
  WriteRegDWORD HKCU "${REGKEY}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\${SHORTCUT}.lnk"
  RMDir /r "$SMPROGRAMS\${APPNAME}"
  RMDir /r "$INSTDIR\runtime"
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\tools"
  RMDir /r "$INSTDIR\licenses"
  Delete "$INSTDIR\${EXE}"
  Delete "$INSTDIR\사용가이드.txt"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${REGKEY}"
  DeleteRegKey HKCU "Software\Gagyebu"
  ; 가계부 데이터(%APPDATA%\gagyebu)와 꾸미기 설정은 남겨 둠 — 다시 설치하면 그대로 이어서 사용
SectionEnd
