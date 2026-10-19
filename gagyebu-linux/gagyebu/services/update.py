"""새 버전 확인 · 내려받기 · 설치 (GitHub 릴리스).

- 가계부 자료는 어디에도 보내지 않는다. GitHub 의 공개 릴리스 목록(JSON)만 읽고, 설치 파일만 받는다.
- 릴리스 태그: PC판 = linux-v<버전> (윈도우판도 같은 릴리스), 안드로이드판 = android-v<버전>
- 받은 파일은 릴리스에 적힌 SHA-256 과 크기를 확인한 뒤에만 설치한다.
- 설치 방식별:
    windows-setup    : setup.exe /S 로 조용히 설치 → 프로그램 다시 실행 (이 프로그램이 끝난 뒤에)
    windows-portable : 자동 설치 없음 → 내려받기 페이지 열기
    deb / rpm        : pkexec 로 관리자 암호를 물어 apt-get / dnf(없으면 rpm) 로 설치 → 다시 실행
    other            : (압축 풀어 install.sh 로 설치 등) 내려받기 페이지 열기
"""
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

REPO = 'jpnjb0918-glitch/gageybu'
API = f'https://api.github.com/repos/{REPO}/releases?per_page=30'
PAGE = f'https://github.com/{REPO}/releases'
DOWNLOAD_PREFIX = f'https://github.com/{REPO}/releases/download/'
TAG_PREFIX = 'linux-v'
UA = 'gagyebu-pc-updater'
AUTO_KINDS = ('windows-setup', 'deb', 'rpm')        # 받아서 바로 설치할 수 있는 방식


def _api():
    return os.environ.get('GAGYEBU_UPDATE_API') or API           # 시험용으로 바꿔 끼움


def _allowed(url):
    extra = os.environ.get('GAGYEBU_UPDATE_DL')                  # 시험용 내려받기 주소
    return url.startswith(DOWNLOAD_PREFIX) or bool(extra and url.startswith(extra))


# ── 버전·릴리스 고르기 ──
def parse_ver(s):
    m = re.fullmatch(r'v?(\d+)\.(\d+)(?:\.(\d+))?', str(s or '').strip())
    return tuple(int(x or 0) for x in m.groups()) if m else None


def newer(a, b):
    """a 가 b 보다 새 버전이면 True (둘 중 하나라도 버전 꼴이 아니면 False)"""
    pa, pb = parse_ver(a), parse_ver(b)
    return bool(pa and pb and pa > pb)


def notes_of(body, limit=8):
    """릴리스 설명에서 '## 업데이트 내용' 바로 아래의 목록(- 로 시작하는 줄)만. 빈 줄이나 다른 글이 나오면 끝"""
    out, on = [], False
    for line in str(body or '').splitlines():
        t = line.strip()
        if not on:
            on = t.startswith('#') and '업데이트 내용' in t
            continue
        if t[:1] in ('-', '*', '·'):
            out.append(t.lstrip('-*· ').strip())
        elif out or t:
            break
    return out[:limit]


def pick_latest(releases, prefix=TAG_PREFIX):
    """릴리스 목록(JSON)에서 prefix 로 시작하는 정식 릴리스 중 가장 새 버전 → dict 또는 None"""
    best = None
    for r in releases or []:
        if not isinstance(r, dict) or r.get('draft') or r.get('prerelease'):
            continue
        tag = str(r.get('tag_name') or '')
        if not tag.startswith(prefix):
            continue
        ver = tag[len(prefix):]
        pv = parse_ver(ver)
        if not pv or (best and pv <= parse_ver(best['version'])):
            continue
        assets = {}
        for a in r.get('assets') or []:
            dg = str(a.get('digest') or '')
            assets[a.get('name')] = {'url': a.get('browser_download_url') or '', 'size': int(a.get('size') or 0),
                                     'sha256': dg[7:].lower() if dg.startswith('sha256:') else ''}
        best = {'version': ver, 'tag': tag, 'page': r.get('html_url') or PAGE, 'name': r.get('name') or tag,
                'notes': notes_of(r.get('body')), 'assets': assets}
    return best


def changes_since(releases, current, prefix=TAG_PREFIX, limit=10):
    """current 보다 새 정식 릴리스들의 '업데이트 내용'을 모아서 (오래된 것부터 차례로, 같은 줄은 한 번만, 너무 많으면 최근 것만)"""
    rows = []
    for r in releases or []:
        if not isinstance(r, dict) or r.get('draft') or r.get('prerelease'):
            continue
        tag = str(r.get('tag_name') or '')
        if tag.startswith(prefix) and newer(tag[len(prefix):], current):
            rows.append((parse_ver(tag[len(prefix):]), notes_of(r.get('body'), 20)))
    out = []
    for _v, notes in sorted(rows, key=lambda x: x[0]):
        for n in notes:
            if n not in out:
                out.append(n)
    return out[-limit:]


def _get(url, timeout):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/vnd.github+json'})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_latest(current, prefix=TAG_PREFIX, timeout=8):
    """GitHub 에서 가장 새 릴리스 (+ 지금 판 이후 바뀐 것 'changes'). 인터넷이 안 되면 OSError 등이 그대로 올라감"""
    with _get(_api(), timeout) as r:
        data = json.loads(r.read(4 * 1024 * 1024).decode('utf-8'))
    rel = pick_latest(data, prefix)
    if rel:
        rel['changes'] = changes_since(data, current, prefix) or rel['notes']
    return rel


# ── 이 컴퓨터의 설치 방식 ──
def app_root():
    """윈도우: 설치 폴더 (우리집가계부.exe, app\\, runtime\\ 가 있는 곳). 리눅스: gagyebu 패키지가 있는 폴더"""
    pkg = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # .../gagyebu
    base = os.path.dirname(pkg)                                                # .../app (윈도우) 또는 /usr/share/gagyebu-linux
    return os.path.dirname(base) if os.path.basename(base).lower() == 'app' else base


def _ok(cmd):
    try:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def install_kind():
    if sys.platform == 'win32':
        root = app_root()
        if os.path.exists(os.path.join(root, 'uninstall.exe')):
            return 'windows-setup'
        return 'windows-portable'
    here = os.path.abspath(__file__)
    if here.startswith('/usr/share/gagyebu-linux/'):
        if shutil.which('dpkg-query') and _ok(['dpkg-query', '-W', '-f=${Status}', 'gagyebu-linux']):
            return 'deb'
        if shutil.which('rpm') and _ok(['rpm', '-q', 'gagyebu-linux']):
            return 'rpm'
    return 'other'


KIND_LABEL = {'windows-setup': '윈도우 설치판', 'windows-portable': '윈도우 휴대용', 'deb': 'deb 패키지',
              'rpm': 'rpm 패키지', 'other': '직접 설치'}


def asset_name(kind, ver):
    return {'windows-setup': f'gagyebu-windows-{ver}-setup.exe', 'deb': f'gagyebu-linux_{ver}_all.deb',
            'rpm': f'gagyebu-linux-{ver}-1.noarch.rpm'}.get(kind)


def asset_for(rel, kind):
    name = asset_name(kind, rel['version'])
    a = rel['assets'].get(name) if name else None
    return (name, a) if a else (None, None)


# ── 내려받기 ──
def download_dir():
    if os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Local')
        return os.path.join(base, 'gagyebu', 'update')
    base = os.environ.get('XDG_CACHE_HOME') or os.path.join(os.path.expanduser('~'), '.cache')
    return os.path.join(base, 'gagyebu', 'update')


class Cancelled(Exception):
    pass


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def verify(path, asset):
    """크기·SHA-256 확인. 맞으면 True"""
    if not os.path.isfile(path):
        return False
    if asset.get('size') and os.path.getsize(path) != asset['size']:
        return False
    return not asset.get('sha256') or sha256_of(path) == asset['sha256']


def download(name, asset, progress=None, cancelled=None, timeout=20):
    """설치 파일 받기 → 파일 경로. progress(받은, 전체), cancelled() 가 True 면 멈춤.
    이미 받아 둔 같은 파일(크기·SHA-256 일치)이 있으면 다시 받지 않음."""
    url = asset['url']
    if not _allowed(url) or not re.fullmatch(r'[A-Za-z0-9._-]+', name or ''):
        raise ValueError('업데이트 파일 주소가 올바르지 않습니다.')
    d = download_dir()
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, name)
    if verify(path, asset):
        return path
    for f in os.listdir(d):                                   # 예전에 받은 설치 파일 정리
        if f != name:
            try:
                os.remove(os.path.join(d, f))
            except OSError:
                pass
    part = path + '.part'
    total = asset.get('size') or 0
    got = 0
    with _get(url, timeout) as r, open(part, 'wb') as out:
        total = total or int(r.headers.get('Content-Length') or 0)
        while True:
            if cancelled and cancelled():
                raise Cancelled()
            chunk = r.read(64 * 1024)
            if not chunk:
                break
            out.write(chunk)
            got += len(chunk)
            if progress:
                progress(got, total)
    if not verify(part, asset):
        os.remove(part)
        raise ValueError('받은 파일이 릴리스에 적힌 것과 다릅니다 (크기 또는 SHA-256). 다시 시도해 주세요.')
    os.replace(part, path)
    return path


# ── 설치 ──
def install_command(kind, path):
    """deb/rpm: 관리자 암호를 묻는 설치 명령. 다른 방식은 None"""
    if kind == 'deb':
        return ['pkexec', 'apt-get', 'install', '-y', '--allow-downgrades', os.path.abspath(path)]
    if kind == 'rpm':
        if shutil.which('dnf'):
            return ['pkexec', 'dnf', 'install', '-y', os.path.abspath(path)]
        return ['pkexec', 'rpm', '-U', '--replacepkgs', os.path.abspath(path)]
    return None


def can_elevate():
    return bool(shutil.which('pkexec'))


def relaunch_command():
    """설치 뒤 새 프로그램을 띄울 명령 (지금 프로그램이 끝나고 2초 뒤)"""
    exe = shutil.which('gagyebu') or ''
    run = f'exec "{exe}"' if exe else f'exec "{sys.executable}" -m gagyebu'
    return ['sh', '-c', f'sleep 2; {run}']


def windows_script(setup, pid, launcher):
    """이 프로그램(pid)이 끝나기를 기다렸다가 setup.exe /S 로 설치하고 다시 실행하는 파워셸 명령 (한글 경로 안전하게 base64)"""
    q = lambda s: "'" + str(s).replace("'", "''") + "'"
    ps = (f"Wait-Process -Id {int(pid)} -ErrorAction SilentlyContinue; "
          f"$p = Start-Process -FilePath {q(setup)} -ArgumentList '/S' -Wait -PassThru; "
          f"Start-Process -FilePath {q(launcher)}")
    enc = base64.b64encode(ps.encode('utf-16-le')).decode('ascii')
    return ['powershell', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-EncodedCommand', enc]


def windows_launcher():
    return os.path.join(app_root(), '우리집가계부.exe')


def spawn_detached(cmd):
    """지금 프로그램과 따로 도는 프로세스로 실행 (이 프로그램이 꺼져도 계속)"""
    if sys.platform == 'win32':
        flags = 0x00000008 | 0x00000200 | 0x08000000     # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        subprocess.Popen(cmd, creationflags=flags, close_fds=True)
    else:
        subprocess.Popen(cmd, start_new_session=True, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
