"""새 버전 확인·내려받기·설치 흐름 점검 (PC판). 가짜 GitHub(이 컴퓨터 안 웹 서버)로 시험하고, 실제 설치 명령은 실행하지 않고 기록만 한다.
사용: QT_QPA_PLATFORM=offscreen python3 tests/update_flow.py <출력폴더>"""
import base64
import functools
import hashlib
import http.server
import json
import os
import socketserver
import sys
import tempfile
import threading
import traceback

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
out = sys.argv[1]
os.makedirs(out, exist_ok=True)
tmp = tempfile.mkdtemp()
os.environ['XDG_CONFIG_HOME'] = os.path.join(tmp, 'config')
os.environ['XDG_CACHE_HOME'] = os.path.join(tmp, 'cache')

# ── 가짜 GitHub ──
SITE = os.path.join(tmp, 'site')
os.makedirs(os.path.join(SITE, 'dl'))
FILES = {'gagyebu-linux_9.9.0_all.deb': b'DEB' * 50000, 'gagyebu-windows-9.9.0-setup.exe': b'EXE' * 70000,
         'gagyebu-linux-9.9.0-1.noarch.rpm': b'RPM' * 40000}
for n, b in FILES.items():
    open(os.path.join(SITE, 'dl', n), 'wb').write(b)
hits = []


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        hits.append(self.path)
        return super().do_GET()


srv = socketserver.ThreadingTCPServer(('127.0.0.1', 0), functools.partial(Q, directory=SITE))
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{srv.server_address[1]}'


def asset(n, bad=False):
    b = FILES[n]
    return {'name': n, 'size': len(b), 'browser_download_url': f'{BASE}/dl/{n}',
            'digest': 'sha256:' + (hashlib.sha256(b + (b'x' if bad else b'')).hexdigest())}


def write_releases(newest='9.9.0', bad=False):
    rel = [
        {'tag_name': 'android-v9.9.0', 'draft': False, 'prerelease': False, 'body': '## 업데이트 내용\n- 안드로이드 것', 'assets': []},
        {'tag_name': f'linux-v{newest}', 'draft': False, 'prerelease': False, 'html_url': f'{BASE}/page',
         'body': f'## 업데이트 내용\n- 9.8.0: 테마 추가\n- {newest}: 업데이트 알림 추가\n\n우리집 가계부 PC판입니다.',
         'assets': [asset(n, bad) for n in FILES]},
        {'tag_name': 'linux-v9.8.0', 'draft': False, 'prerelease': False, 'body': '## 업데이트 내용\n- 9.8.0: 테마 추가', 'assets': []},
        {'tag_name': 'linux-v99.0.0', 'draft': True, 'prerelease': False, 'body': '초안', 'assets': []},
        {'tag_name': 'linux-v1.0.0', 'draft': False, 'prerelease': False, 'body': '## 업데이트 내용\n- 옛날', 'assets': []},
    ]
    if newest != '9.9.0':                         # '최신' 시험: 지금 판보다 새 것이 없게
        rel = [r for r in rel if r['tag_name'] != 'linux-v9.8.0']
    open(os.path.join(SITE, 'releases'), 'w', encoding='utf-8').write(json.dumps(rel, ensure_ascii=False))


write_releases()
os.environ['GAGYEBU_UPDATE_API'] = f'{BASE}/releases'
os.environ['GAGYEBU_UPDATE_DL'] = f'{BASE}/dl/'

from PyQt6.QtCore import QEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from gagyebu import __version__, db  # noqa: E402
from gagyebu import theme as TH  # noqa: E402
from gagyebu.services import ledger as L  # noqa: E402
from gagyebu.services import update as U  # noqa: E402

path = os.path.join(tmp, 'g.sqlite3')
con = db.connect(path)
db.set_meta(con, 'password', None)
con.commit()
con.close()

from gagyebu.app import MainWindow  # noqa: E402
from gagyebu.ui import update_ui as UI  # noqa: E402

app = QApplication(sys.argv[:1])
TH.apply(app)
UI.SYNC = True
log = {'ask': [], 'info': [], 'url': [], 'cmd': [], 'spawn': [], 'quit': 0}
answers = []
rc_next = [0]


def fake_ask(parent, text, yes='예', no='아니요'):
    log['ask'].append(text)
    return answers.pop(0)


UI.ask = fake_ask
UI.info = lambda parent, text: log['info'].append(text)
UI.open_url = lambda url: log['url'].append(url)
UI.run_install = lambda cmd: (log['cmd'].append(cmd), rc_next[0])[1]
U.spawn_detached = lambda cmd: log['spawn'].append(cmd)
U.can_elevate = lambda: True
w = MainWindow(path)
w.resize(1360, 860)
w.show()
upd = w.updater
upd.quit_app = lambda: log.__setitem__('quit', log['quit'] + 1)
fails = []


def check(name, cond, extra=''):
    print(('  ✓ ' if cond else '  ✗ ') + name + (f'  ({extra})' if extra and not cond else ''))
    if not cond:
        fails.append(name)


def settle():
    for _ in range(3):
        app.processEvents()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def reset():
    for k in ('ask', 'info', 'url', 'cmd', 'spawn'):
        log[k].clear()
    log['quit'] = 0
    answers.clear()


try:
    print('릴리스 고르기')
    data = json.loads(open(os.path.join(SITE, 'releases'), encoding='utf-8').read())
    rel = U.pick_latest(data)
    check('linux-v 정식 릴리스 중 최신 (초안·안드로이드 제외)', rel['version'] == '9.9.0', str(rel and rel['version']))
    check('업데이트 내용은 목록 줄만', rel['notes'] == ['9.8.0: 테마 추가', '9.9.0: 업데이트 알림 추가'], str(rel['notes']))
    check('지금 판 이후 바뀐 것 모으기 (같은 줄 한 번)', U.changes_since(data, __version__) == ['9.8.0: 테마 추가', '9.9.0: 업데이트 알림 추가'],
          str(U.changes_since(data, __version__)))
    check('버전 비교', U.newer('1.10.0', '1.9.9') and not U.newer('1.3.0', '1.3.0') and not U.newer('dev', '1.0.0'))
    try:
        U.download('x.deb', {'url': 'https://example.com/x.deb', 'size': 1, 'sha256': ''})
        check('다른 사이트 주소 거부', False)
    except ValueError:
        check('다른 사이트 주소 거부', True)

    print('자동 확인 (deb) → 아니요')
    upd.kind = 'deb'
    reset()
    answers.append(False)
    upd.check(manual=False)
    settle()
    check('새 버전 묻기', len(log['ask']) == 1 and '업데이트하시겠습니까?' in log['ask'][0])
    check('업데이트 내용을 간단히 보여 줌', '업데이트 내용' in log['ask'][0] and '· 9.9.0: 업데이트 알림 추가' in log['ask'][0]
          and '· 9.8.0: 테마 추가' in log['ask'][0], log['ask'][0] if log['ask'] else '')
    check('아니요 → 설정에서 직접 할 수 있다는 안내', log['info'] == [UI.HINT], str(log['info']))
    check('내려받지 않음', not [h for h in hits if '/dl/' in h])

    print('자동 확인을 끄면')
    UI.set_auto(False)
    reset()
    upd.check_later(0)
    settle()
    app.processEvents()
    check('설정에서 끄면 켤 때 확인 안 함', not log['ask'] and UI.auto_enabled() is False)
    UI.set_auto(True)

    print('설정 → 업데이트: 확인 → 예 → 내려받기 → 설치는 나중에')
    sp = w.goto('SettingsPage')
    settle()
    from gagyebu.ui.settings_page import UpdateTab
    tab = next(p for p in sp.parts if isinstance(p, UpdateTab))
    sp.tabs.setCurrentWidget(tab)
    settle()
    check('설정에 업데이트 탭 (자동 확인 체크 켜짐)', sp.tabs.tabText(sp.tabs.indexOf(tab)) == '업데이트' and tab.auto.isChecked())
    tab.auto.setChecked(False)
    check('탭에서 자동 확인 끄기', UI.auto_enabled() is False)
    tab.auto.setChecked(True)
    reset()
    answers.extend([True, False])
    n0 = len(hits)
    tab.check_btn.click()
    settle()
    got = os.path.join(U.download_dir(), 'gagyebu-linux_9.9.0_all.deb')
    check('수동 확인도 업데이트 내용과 함께 묻기', len(log['ask']) == 2 and '업데이트 내용' in log['ask'][0])
    check('내려받음 (SHA-256 확인)', os.path.isfile(got) and U.sha256_of(got) == hashlib.sha256(FILES['gagyebu-linux_9.9.0_all.deb']).hexdigest())
    check('내려받은 뒤 설치할지 묻기', len(log['ask']) == 2 and '지금 설치할까요?' in log['ask'][1] and '관리자 암호' in log['ask'][1])
    check('설치 아니요 → 나중에 설치 안내', log['info'] and '나중에 설치' in log['info'][-1], str(log['info']))
    check('설치 명령은 아직 안 함', not log['cmd'])
    tab.refresh()
    check('탭: 업데이트 내용 표시', '9.9.0: 업데이트 알림 추가' in tab.notes.text() and tab.notes.isVisible() is not False)
    check('탭: [내려받은 새 버전 9.9.0 설치] 켜짐, 내려받기는 꺼짐', tab.inst_btn.isEnabled() and '9.9.0' in tab.inst_btn.text()
          and not tab.dl_btn.isEnabled())
    tab.grab().save(os.path.join(out, 'update-tab.png'))

    print('같은 파일은 다시 받지 않음')
    n1 = len([h for h in hits if '/dl/' in h])
    p2 = U.download('gagyebu-linux_9.9.0_all.deb', upd.latest['assets']['gagyebu-linux_9.9.0_all.deb'])
    check('이미 받은 파일(크기·SHA-256 일치) 재사용', p2 == got and len([h for h in hits if '/dl/' in h]) == n1)

    print('내려받은 새 버전 설치 (deb) — 관리자 암호 취소')
    reset()
    answers.append(True)
    rc_next[0] = 126
    tab.inst_btn.click()
    settle()
    check('설치 명령: pkexec apt-get install', log['cmd'] == [['pkexec', 'apt-get', 'install', '-y', '--allow-downgrades', got]], str(log['cmd']))
    check('취소 안내, 프로그램은 그대로', log['info'] and '취소' in log['info'][-1] and log['quit'] == 0 and not log['spawn'])
    check('받은 파일은 그대로 기억', upd.downloaded() == (got, '9.9.0'))

    print('다시 설치 — 성공')
    reset()
    answers.append(True)
    rc_next[0] = 0
    tab.inst_btn.click()
    settle()
    check('설치 끝 → 다시 실행 명령 + 프로그램 닫기', log['quit'] == 1 and log['spawn'] and log['spawn'][0][:2] == ['sh', '-c']
          and 'sleep 2' in log['spawn'][0][2], str(log['spawn']))
    check('설치 끝나면 받은 파일 기억 지움', upd.downloaded() is None)

    print('rpm 설치 명령')
    cmd = U.install_command('rpm', '/tmp/a.rpm')
    check('rpm: pkexec dnf(없으면 rpm -U)', cmd[0] == 'pkexec' and (cmd[1:3] == ['dnf', 'install'] or cmd[1:3] == ['rpm', '-U']), str(cmd))

    print('윈도우 설치판')
    upd.kind = 'windows-setup'
    reset()
    answers.extend([True, True])
    upd.check(manual=True)
    settle()
    setup = os.path.join(U.download_dir(), 'gagyebu-windows-9.9.0-setup.exe')
    check('setup.exe 받음', os.path.isfile(setup))
    check('설치 묻는 글: 닫혔다가 다시 열림', len(log['ask']) == 2 and '다시 열립니다' in log['ask'][1])
    sp_cmd = log['spawn'][0] if log['spawn'] else []
    ps = base64.b64decode(sp_cmd[-1]).decode('utf-16-le') if sp_cmd else ''
    check('파워셸: 이 프로그램이 끝나길 기다렸다가 setup /S → 다시 실행', sp_cmd[:1] == ['powershell'] and f'Wait-Process -Id {os.getpid()}' in ps
          and setup in ps and "'/S'" in ps and '우리집가계부.exe' in ps, ps)
    check('그리고 프로그램 닫기', log['quit'] == 1)

    print('윈도우 휴대용 → 내려받기 페이지')
    upd.kind = 'windows-portable'
    reset()
    answers.append(True)
    upd.check(manual=False)
    settle()
    check('자동 설치 안 되는 방식 안내 + 업데이트 내용', log['ask'] and '내려받기 페이지' in log['ask'][0] and '업데이트 내용' in log['ask'][0])
    check('예 → 릴리스 페이지 열기', log['url'] == [f'{BASE}/page'], str(log['url']))

    print('받은 파일이 릴리스와 다르면')
    upd.kind = 'rpm'
    write_releases(bad=True)
    reset()
    answers.extend([True, True])
    upd.check(manual=True)
    settle()
    check('SHA-256 이 다르면 설치 묻지 않고 오류 안내', len(log['ask']) == 1 and log['info'] and 'SHA-256' in log['info'][-1], str(log['info']))
    check('틀린 파일은 남기지 않음', not os.path.exists(os.path.join(U.download_dir(), 'gagyebu-linux-9.9.0-1.noarch.rpm')))

    print('최신일 때 / 인터넷 안 될 때')
    write_releases(newest=__version__)
    reset()
    upd.check(manual=True)
    settle()
    check('수동: 최신이라고 알림', log['info'] and '최신' in log['info'][-1] and not log['ask'], str(log['info']))
    reset()
    upd.check(manual=False)
    settle()
    check('자동: 최신이면 아무것도 안 띄움', not log['info'] and not log['ask'])
    os.environ['GAGYEBU_UPDATE_API'] = 'http://127.0.0.1:9/none'
    reset()
    upd.check(manual=True)
    settle()
    check('수동: 확인 못 하면 안내', log['info'] and '확인하지 못했습니다' in log['info'][-1])
    reset()
    upd.check(manual=False)
    settle()
    check('자동: 인터넷 안 되면 조용히', not log['info'] and not log['ask'])
    check('설치 방식 이름', U.KIND_LABEL[U.install_kind()] in ('직접 설치', 'deb 패키지', 'rpm 패키지'))
except Exception:
    traceback.print_exc()
    fails.append('예외')

print()
print('실패:', fails if fails else '없음')
sys.exit(1 if fails else 0)
