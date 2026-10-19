"""새 버전 알림·내려받기·설치 흐름 시험 (브라우저 + 가짜 NativeBridge: 릴리스 목록·내려받기·설치 화면은 흉내).
  python3 update_flow.py      → shots/update/*.png
실제 휴대폰의 내려받기 관리자·설치 화면은 이 시험으로 확인할 수 없음 (가짜가 기록만 함)."""
import functools
import http.server
import json
import os
import socketserver
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'devtools', 'shots', 'update')
os.makedirs(OUT, exist_ok=True)


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=ROOT))
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{srv.server_address[1]}/app/assets/www/index.html'
fails, errs = [], []
DL = 'https://github.com/jpnjb0918-glitch/gageybu/releases/download/'
SHA = 'ab' * 32


def rels(newest='9.9.0'):
    r = [{'tag_name': 'linux-v9.9.9', 'draft': False, 'prerelease': False, 'body': '## 업데이트 내용\n- PC 것', 'assets': []},
         {'tag_name': 'android-v99.0.0', 'draft': True, 'prerelease': False, 'body': '초안', 'assets': []}]
    if newest == '9.9.0':
        r += [{'tag_name': 'android-v9.9.0', 'draft': False, 'prerelease': False, 'html_url': 'https://github.com/x/page',
               'body': '## 업데이트 내용\n- 9.8.0: 테마 추가\n- 9.9.0: 업데이트 알림 추가\n\n안드로이드판입니다.',
               'assets': [{'name': 'gagyebu-android-9.9.0.apk', 'size': 2600000, 'digest': 'sha256:' + SHA,
                           'browser_download_url': DL + 'android-v9.9.0/gagyebu-android-9.9.0.apk'},
                          {'name': 'gagyebu-android-guide-9.9.0.md', 'size': 10, 'browser_download_url': DL + 'x.md'}]},
              {'tag_name': 'android-v9.8.0', 'draft': False, 'prerelease': False, 'body': '## 업데이트 내용\n- 9.8.0: 테마 추가', 'assets': []}]
    else:
        r += [{'tag_name': f'android-v{newest}', 'draft': False, 'prerelease': False, 'body': '## 업데이트 내용\n- 지금 것', 'assets': []}]
    return r


def check(name, cond, extra=''):
    print(('  ✓ ' if cond else '  ✗ ') + name + (f'  ({extra})' if extra and not cond else ''))
    if not cond:
        fails.append(name)


def dialog_text(pg):
    loc = pg.locator('.overlay.center .dialog .msg').last
    return loc.inner_text() if loc.count() else ''


def press(pg, label):
    pg.locator('.overlay.center .dialog .btns').last.get_by_role('button', name=label, exact=True).click()
    pg.wait_for_timeout(200)


def wait_dialog(pg, ms=6000):
    try:
        pg.wait_for_selector('.overlay.center .dialog', timeout=ms)
        return True
    except Exception:
        return False


def page(p, theme='retro', prefs=None, version='1.3.0', releases=None):
    ctx = p.chromium.launch().new_context(viewport={'width': 392, 'height': 820}, device_scale_factor=2, is_mobile=True, has_touch=True)
    ctx.add_init_script(path=os.path.join(ROOT, 'devtools', 'fake-native.js'))
    init = {'theme': theme}
    init.update(prefs or {})
    ctx.add_init_script(f"window.__fake && (Object.assign(window.__fake.prefs, {json.dumps(init)}), window.__fake.appVersion = {json.dumps(version)},"
                        f" window.__fake.releases = {json.dumps(releases if releases is not None else rels(), ensure_ascii=False)});")
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    pg.goto(URL)
    pg.wait_for_selector('.navbar', timeout=20000)
    return pg


def fake(pg, k):
    return pg.evaluate(f'window.__fake[{json.dumps(k)}]')


with sync_playwright() as p:
    print('켤 때 자동 확인 → 아니요')
    pg = page(p)
    check('켤 때 새 버전 묻기', wait_dialog(pg))
    t = dialog_text(pg)
    check('묻는 글: 새 버전·지금 판·업데이트하시겠습니까', '새 버전 9.9.0' in t and '지금 1.3.0' in t and '업데이트하시겠습니까?' in t, t)
    check('업데이트 내용을 간단히 (지금 판 이후 것 모두)', '업데이트 내용' in t and '· 9.8.0: 테마 추가' in t and '· 9.9.0: 업데이트 알림 추가' in t and 'PC 것' not in t, t)
    pg.screenshot(path=os.path.join(OUT, 'retro-ask.png'))
    press(pg, '아니요')
    check('아니요 → 설정에서 직접 할 수 있다는 안내', '설정 → 업데이트에서 언제든 직접' in dialog_text(pg), dialog_text(pg))
    press(pg, '확인')
    check('내려받지 않음', not fake(pg, 'downloads'))
    check('릴리스 목록은 한 번만 읽음', fake(pg, 'updCalls') == 1, str(fake(pg, 'updCalls')))

    print('설정 → 업데이트: 확인 → 예 → 내려받기 → 설치는 나중에 → 설정에서 설치')
    pg.evaluate("App.go('settings', {section: 'update'}, true)")
    pg.wait_for_timeout(400)
    box = pg.locator('.updbox')
    check('설정에 업데이트 칸 (자동 확인 켜짐, 지금 판)', box.count() == 1 and box.locator('[data-u=auto]').is_checked() and '1.3.0' in box.inner_text())
    check('이미 확인한 새 버전과 업데이트 내용 표시', '9.9.0: 업데이트 알림 추가' in box.inner_text() and box.locator('[data-u=dl]').count() == 1, box.inner_text())
    box.locator('[data-u=check]').click()
    check('수동 확인도 업데이트 내용과 함께 묻기', wait_dialog(pg) and '업데이트 내용' in dialog_text(pg))
    pg.locator('.overlay.center .dialog .btns').last.get_by_role('button', name='예', exact=True).click()
    pg.wait_for_timeout(450)
    check('내려받기 창 (진행 막대가 차오름)', pg.locator('.upd-dl .upbar').count() == 1 and
          pg.evaluate("parseFloat(document.querySelector('.upd-dl .upbar i').style.width) > 0"), pg.locator('.uppct').inner_text() if pg.locator('.uppct').count() else '')
    pg.screenshot(path=os.path.join(OUT, 'retro-download.png'))
    check('설치할지 묻기', wait_dialog(pg) and '지금 설치할까요?' in dialog_text(pg), dialog_text(pg))
    d = (fake(pg, 'downloads') or [{}])[-1]
    check('정해진 주소·이름·크기·SHA-256 으로 받기', d.get('url') == DL + 'android-v9.9.0/gagyebu-android-9.9.0.apk' and d.get('name') == 'gagyebu-android-9.9.0.apk'
          and d.get('size') == '2600000' and d.get('sha') == SHA, str(d))
    pg.screenshot(path=os.path.join(OUT, 'retro-install-ask.png'))
    press(pg, '아니요')
    check('설치 아니요 → 나중에 설치 안내', '[내려받은 새 버전 설치]' in dialog_text(pg), dialog_text(pg))
    press(pg, '확인')
    check('설치 화면은 아직 안 엶', not fake(pg, 'installs'))
    pg.wait_for_timeout(200)
    box = pg.locator('.updbox')
    check('설정: [내려받은 새 버전 9.9.0 설치] 생김, 내려받기 단추는 사라짐', box.locator('[data-u=inst]').count() == 1 and '9.9.0' in box.locator('[data-u=inst]').inner_text()
          and box.locator('[data-u=dl]').count() == 0, box.inner_text())
    box.scroll_into_view_if_needed()
    pg.screenshot(path=os.path.join(OUT, 'retro-settings.png'))
    box.locator('[data-u=inst]').click()
    check('설정에서 설치 → 다시 설치 여부 묻기', wait_dialog(pg) and '지금 설치할까요?' in dialog_text(pg))
    press(pg, '예')
    check('예 → 안드로이드 설치 화면 열기', fake(pg, 'installs') == ['gagyebu-android-9.9.0.apk'], str(fake(pg, 'installs')))

    print('자동 확인 끄기')
    box.locator('[data-u=auto]').uncheck()
    check('끄면 휴대폰에 기억', fake(pg, 'prefs').get('update_auto') == 'false')
    box.locator('[data-u=auto]').check()
    check('다시 켜면 기본값', 'update_auto' not in fake(pg, 'prefs'))

    print('받은 파일이 릴리스와 다르면')
    pg.evaluate("window.__fake.dlResult = {ok: false, error: '받은 파일이 릴리스에 적힌 것과 다릅니다 (SHA-256)'}; window.__fake.files = {}")
    pg.evaluate("() => { App.checkUpdate(true); }")
    wait_dialog(pg)
    press(pg, '예')
    pg.wait_for_timeout(1200)
    check('오류 안내, 설치 묻지 않음', 'SHA-256' in dialog_text(pg) and '지금 설치할까요?' not in dialog_text(pg), dialog_text(pg))
    press(pg, '확인')
    pg.context.close()

    print('설정에서 끈 경우 켤 때 확인 안 함')
    pg = page(p, prefs={'update_auto': 'false'})
    pg.wait_for_timeout(4000)
    check('릴리스 목록을 읽지 않음, 창 없음', not fake(pg, 'updCalls') and pg.locator('.overlay.center').count() == 0)
    pg.context.close()

    print('최신 / 인터넷 안 됨 / 버전 없음')
    pg = page(p, releases=rels('1.3.0'))
    pg.wait_for_timeout(3500)
    check('자동: 최신이면 아무것도 안 띄움', fake(pg, 'updCalls') == 1 and pg.locator('.overlay.center').count() == 0)
    pg.evaluate("() => { App.checkUpdate(true); }")
    check('수동: 최신이라고 알림', wait_dialog(pg) and '최신' in dialog_text(pg), dialog_text(pg))
    press(pg, '확인')
    pg.evaluate("window.__fake.releases = 'fail'")
    pg.evaluate("() => { App.checkUpdate(true); }")
    check('수동: 인터넷 안 되면 안내', wait_dialog(pg) and '확인하지 못했습니다' in dialog_text(pg), dialog_text(pg))
    press(pg, '확인')
    pg.evaluate("() => { App.checkUpdate(false); }")
    pg.wait_for_timeout(500)
    check('자동: 인터넷 안 되면 조용히', pg.locator('.overlay.center').count() == 0)
    pg.context.close()
    pg = page(p, version='dev')
    pg.wait_for_timeout(3500)
    check('버전 없는 개발판: 자동 확인 안 함', not fake(pg, 'updCalls'))
    pg.context.close()

    print('다른 테마에서 모양')
    for th in ('feed', 'timeline_dark'):
        pg = page(p, theme=th)
        wait_dialog(pg)
        pg.screenshot(path=os.path.join(OUT, f'{th}-ask.png'))
        pg.context.close()

print()
if errs:
    print('콘솔 오류:', *errs[:10], sep='\n  ')
print('실패:', fails if fails else '없음')
raise SystemExit(1 if fails or errs else 0)
