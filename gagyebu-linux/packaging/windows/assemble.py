"""윈도우판 폴더 만들기 (리눅스에서 실행).

  python3 assemble.py --embed python-3.12.x-embed-amd64.zip --wheels <PyQt6 윈도우 휠 폴더>
                      --mdbtools <mdb-export.exe 폴더> --launcher 우리집가계부.exe --guide 사용가이드.txt --out <폴더>

만들어지는 배치:
  우리집가계부.exe          실행기 (runtime\\python312.dll 로 gagyebu 실행)
  runtime\\                 파이썬 3.12 (python.org 임베디드 배포판) + Lib\\site-packages\\PyQt6 (필요한 모듈만)
  app\\gagyebu\\             프로그램
  tools\\mdbtools\\          윈도우판 원본(.mdb) 읽기 도구
  사용가이드.txt, licenses\\
"""
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))

KEEP_PYQT = {'__init__.py', 'QtCore.pyd', 'QtGui.pyd', 'QtWidgets.pyd', 'QtPrintSupport.pyd'}
KEEP_QT_BIN = {'Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll', 'Qt6PrintSupport.dll'}
KEEP_PLUGINS = {'platforms/qwindows.dll', 'platforms/qoffscreen.dll', 'styles/qmodernwindowsstyle.dll',
                'imageformats/qico.dll', 'imageformats/qjpeg.dll', 'imageformats/qgif.dll',
                'imageformats/qwebp.dll'}      # 영수증 사진 (1.7.0): 휴대폰·웹에서 받은 webp 도 열리게
KEEP_TR = {'qtbase_ko.qm', 'qt_ko.qm'}
# 윈도우에 기본으로 있는 DLL (의존성 점검에서 제외)
SYSTEM_DLL = re.compile(r'^(api-ms-win-.*|ext-ms-.*|kernel32|user32|gdi32|advapi32|shell32|ole32|oleaut32|ws2_32|'
                        r'version|winmm|netapi32|userenv|mpr|authz|ntdll|uxtheme|dwrite|d3d11|d3d12|d3d9|dxgi|dwmapi|'
                        r'imm32|setupapi|shlwapi|wtsapi32|comdlg32|winspool|uiautomationcore|icuuc|icuin|crypt32|'
                        r'bcrypt|secur32|iphlpapi|rpcrt4|msvcrt|ucrtbase|comctl32|shcore|propsys|dbghelp|cfgmgr32|'
                        r'powrprof|wintrust|ncrypt|dnsapi|normaliz|cabinet|msi)\.(dll|drv)$', re.I)


def log(*a):
    print('  ', *a)


def copy_app(dst):
    src = os.path.join(ROOT, 'gagyebu')
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))


def install_wheels(wheels, site):
    for w in sorted(glob.glob(os.path.join(wheels, '*.whl'))):
        with zipfile.ZipFile(w) as z:
            z.extractall(site)
        log('휠 풀기:', os.path.basename(w))


def prune_pyqt(site):
    pq = os.path.join(site, 'PyQt6')
    removed = 0
    for name in os.listdir(pq):
        p = os.path.join(pq, name)
        if name == 'Qt6' or name in KEEP_PYQT or (name.startswith('sip.') and name.endswith('.pyd')):
            continue
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
        removed += 1
    qt = os.path.join(pq, 'Qt6')
    for name in os.listdir(qt):
        if name not in ('bin', 'plugins', 'translations'):
            shutil.rmtree(os.path.join(qt, name))
    for name in os.listdir(os.path.join(qt, 'bin')):
        keep = name in KEEP_QT_BIN or re.match(r'^(msvcp140.*|vcruntime140.*|concrt140)\.dll$', name, re.I)
        if not keep:
            os.remove(os.path.join(qt, 'bin', name))
    plug = os.path.join(qt, 'plugins')
    for dp, _dn, fn in os.walk(plug):
        for f in fn:
            rel = os.path.relpath(os.path.join(dp, f), plug).replace(os.sep, '/')
            if rel not in KEEP_PLUGINS:
                os.remove(os.path.join(dp, f))
    for dp, dn, _fn in os.walk(plug, topdown=False):
        if not os.listdir(dp):
            os.rmdir(dp)
    tr = os.path.join(qt, 'translations')
    for f in os.listdir(tr):
        if f not in KEEP_TR:
            os.remove(os.path.join(tr, f))
    for d in glob.glob(os.path.join(site, '*.dist-info')):
        shutil.rmtree(d)
    log('PyQt6 정리: 쓰지 않는 모듈 제거', removed, '개')


def dll_imports(path):
    out = subprocess.run(['x86_64-w64-mingw32-objdump', '-p', path], capture_output=True, text=True).stdout
    return [line.split()[-1] for line in out.splitlines() if 'DLL Name:' in line]


def check_deps(top):
    """모든 exe/dll/pyd 가 부르는 DLL 이 묶음 안이나 윈도우 기본 DLL 에 있는지 확인."""
    have = {}
    files = []
    for dp, _dn, fn in os.walk(top):
        for f in fn:
            if f.lower().endswith(('.dll', '.pyd', '.exe')):
                have.setdefault(f.lower(), os.path.join(dp, f))
                files.append(os.path.join(dp, f))
    missing = {}
    for f in files:
        for d in dll_imports(f):
            if d.lower() not in have and not SYSTEM_DLL.match(d):
                missing.setdefault(d, []).append(os.path.relpath(f, top))
    return len(files), missing


def main():
    ap = argparse.ArgumentParser()
    for k in ('embed', 'wheels', 'mdbtools', 'launcher', 'guide', 'out'):
        ap.add_argument('--' + k, required=True)
    a = ap.parse_args()
    out = a.out
    if os.path.exists(out):
        shutil.rmtree(out)
    rt = os.path.join(out, 'runtime')
    os.makedirs(rt)
    with zipfile.ZipFile(a.embed) as z:
        z.extractall(rt)
    pth = [f for f in os.listdir(rt) if f.endswith('._pth')]
    if len(pth) != 1:
        sys.exit('임베디드 파이썬의 ._pth 파일을 찾지 못했습니다')
    zipname = [f for f in os.listdir(rt) if re.match(r'python3\d+\.zip$', f)][0]
    with open(os.path.join(rt, pth[0]), 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(f'{zipname}\n.\nLib\\site-packages\n..\\app\n')      # site 는 쓰지 않음(격리)
    log('파이썬:', pth[0], '→', zipname, '. Lib\\site-packages ..\\app')
    site = os.path.join(rt, 'Lib', 'site-packages')
    os.makedirs(site)
    install_wheels(a.wheels, site)
    prune_pyqt(site)
    copy_app(os.path.join(out, 'app', 'gagyebu'))
    log('프로그램 복사: app\\gagyebu')
    td = os.path.join(out, 'tools', 'mdbtools')
    os.makedirs(td)
    for f in os.listdir(a.mdbtools):
        shutil.copy2(os.path.join(a.mdbtools, f), td)
    shutil.copy2(a.launcher, os.path.join(out, '우리집가계부.exe'))
    shutil.copy2(a.guide, os.path.join(out, '사용가이드.txt'))
    lic = os.path.join(out, 'licenses')
    os.makedirs(lic)
    shutil.copy2(os.path.join(rt, 'LICENSE.txt'), os.path.join(lic, 'Python-LICENSE.txt'))
    shutil.copy2(os.path.join(ROOT, 'gagyebu', 'assets', 'fonts', 'OFL-Galmuri.txt'), os.path.join(lic, 'Galmuri-OFL.txt'))
    shutil.copy2(os.path.join(ROOT, 'gagyebu', 'vendor', 'LICENSE.korean_lunar_calendar'),
                 os.path.join(lic, 'korean_lunar_calendar-MIT.txt'))
    with open(os.path.join(lic, 'README.txt'), 'w', encoding='utf-8-sig', newline='\r\n') as f:
        f.write('함께 들어 있는 외부 구성요소와 라이선스\n\n'
                '- Python 3.12 (python.org 임베디드 배포판): Python-LICENSE.txt\n'
                '- PyQt6 (GPL v3) / Qt 6 (LGPL v3): https://www.riverbankcomputing.com/software/pyqt/ , https://www.qt.io/\n'
                '- mdbtools (LGPL v2, tools\\mdbtools\\COPYING.LIB.txt): 윈도우용으로 다시 빌드, 바꾼 부분은 소스 묶음의\n'
                '  packaging/windows/mdbtools-win.patch\n'
                '- 갈무리 글꼴 (SIL OFL 1.1): Galmuri-OFL.txt\n'
                '- korean_lunar_calendar (MIT): korean_lunar_calendar-MIT.txt\n'
                '- 아늑단 이미지: 사용자가 제공한 스티커 시트 (개인 사용)\n')
    n, missing = check_deps(out)
    log(f'의존 DLL 점검: 실행 파일·라이브러리 {n}개', '— 빠진 것 없음' if not missing else f'— 빠진 DLL {missing}')
    if missing:
        sys.exit(1)
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _d, fn in os.walk(out) for f in fn)
    log(f'완성: {out} ({total / 1e6:.1f} MB)')


if __name__ == '__main__':
    main()
