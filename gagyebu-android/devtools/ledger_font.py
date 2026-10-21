"""기본 장부·장부 목록에서 새 장부 만들기·글자 크기(1px) 시험 (브라우저 + 가짜 NativeBridge).
  python3 ledger_font.py      → shots/ledger/*.png"""
import functools
import http.server
import json
import os
import socketserver
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'devtools', 'shots', 'ledger')
os.makedirs(OUT, exist_ok=True)


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=ROOT))
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{srv.server_address[1]}/app/assets/www/index.html'
fails, errs = [], []


def check(name, cond, extra=''):
    print(('  ✓ ' if cond else '  ✗ ') + name + (f'  ({extra})' if extra and not cond else ''))
    if not cond:
        fails.append(name)


def page(p, theme='feed', prefs=None):
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 392, 'height': 820}, device_scale_factor=2, is_mobile=True, has_touch=True)
    ctx.add_init_script(path=os.path.join(ROOT, 'devtools', 'fake-native.js'))
    init = {'theme': theme}
    init.update(prefs or {})
    ctx.add_init_script(f"window.__fake && Object.assign(window.__fake.prefs, {json.dumps(init)});")
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    pg.goto(URL)
    pg.wait_for_selector('.navbar', timeout=20000)
    pg.wait_for_timeout(500)
    return br, pg


fs = lambda pg: pg.evaluate("getComputedStyle(document.body).getPropertyValue('--fs').trim()")
names = lambda pg: pg.evaluate("L.ledgers().map(l => l.name)")

with sync_playwright() as p:
    print('기본 장부')
    br, pg = page(p)
    check('처음 열면 기본 장부 4개', names(pg) == ['가계부 장부', '생활비 장부', '용돈 장부', '비상금 장부', '여행 장부'], str(names(pg)))
    check('계정과목은 첫 장부에서 복사', pg.evaluate("""() => { const ls = L.ledgers(); const m = id => JSON.stringify(L.categories(id).map(c => [c.code, c.name]));
      return ls.slice(1).every(l => m(l.id) === m(ls[0].id)) && L.categories(ls[1].id).length > 3; }"""))
    check('자료 파일에 한 번 했다고 표시', pg.evaluate("DB.getMeta('default_ledgers')") == '1')
    gone = pg.evaluate("() => { const t = L.ledgers().find(l => l.name === '여행 장부'); L.deleteLedger(t.id); return t.id; }")
    check('지운 장부는 다시 안 생김', pg.evaluate("L.ensureDefaultLedgers().length") == 0 and '여행 장부' not in names(pg))
    check('지운 장부의 계정과목도 함께 지워짐', pg.evaluate(f"DB.q('SELECT 1 FROM cat_group WHERE ledger_id=?', [{gone}]).length") == 0)

    print('장부 고르기 창: 장부들 · 새 장부 만들기 · 장부 관리 (줄 높이 같게)')
    pg.evaluate("App.reloadLedgers()")
    check('맨 위 단추에 지금 장부 이름', pg.locator('.ledger-pick .lp-name').inner_text() == '가계부 장부')
    pg.locator('.ledger-pick').click()
    pg.wait_for_timeout(300)
    rows = pg.evaluate("""Array.from(document.querySelectorAll('.overlay:last-child .lp-list li')).map(li =>
      [li.dataset.lid ? 'lid' : (li.dataset.act || 'sep'), li.querySelector('b') ? li.querySelector('b').textContent : '', Math.round(li.getBoundingClientRect().height)])""")
    kinds = [r[0] for r in rows]
    check('장부 4개 → 구분선 → 새 장부 만들기 · 장부 관리', kinds == ['lid'] * 4 + ['sep', 'new', 'manage'], str(rows))
    hs = {r[2] for r in rows if r[0] != 'sep'}
    check('구분선 말고 모든 줄 높이가 같음', len(hs) == 1, str(rows))
    check('구분선은 얇은 선 (한 줄 차지 안 함)', [r[2] for r in rows if r[0] == 'sep'] == [1], str(rows))
    check('지금 장부에 ✓', pg.locator('.overlay:last-child .lp-list li.on .ck').inner_text() == '✓')
    pg.screenshot(path=os.path.join(OUT, 'feed-ledger-picker.png'))
    lid0 = pg.evaluate("App.lid")
    pg.locator('.overlay:last-child .lp-list li[data-act=new]').click()
    pg.wait_for_timeout(300)
    sh = pg.locator('.overlay').last
    check('[새 장부 만들기] → 새 장부 창', sh.locator('.sh .t').inner_text() == '새 가계부')
    pg.screenshot(path=os.path.join(OUT, 'feed-new-ledger.png'))
    sh.locator('input[data-k=name], [data-k=name] input, input').first.fill('모임 장부')
    sh.locator('.sf').get_by_role('button').last.click()
    pg.wait_for_timeout(300)
    new = pg.evaluate("(L.ledgers().find(l => l.name === '모임 장부') || {}).id")
    check('새 장부가 생기고 그 장부로 바뀜', bool(new) and pg.evaluate("App.lid") == new and pg.locator('.ledger-pick .lp-name').inner_text() == '모임 장부')
    check('기본 방법 = 지금 장부의 계정과목만 복사', bool(new) and pg.evaluate(f"L.categories({new}).length === L.categories({lid0}).length && L.entriesWithBalance({new}).length === 0"))
    pg.locator('.ledger-pick').click()
    pg.wait_for_timeout(250)
    pg.locator(f'.overlay:last-child .lp-list li[data-lid="{lid0}"]').click()
    pg.wait_for_timeout(250)
    check('창에서 다른 장부를 누르면 그 장부로', pg.evaluate("App.lid") == lid0)
    pg.locator('.ledger-pick').click()
    pg.wait_for_timeout(250)
    pg.locator('.overlay:last-child .lp-list li[data-act=manage]').click()
    pg.wait_for_timeout(300)
    check('[장부 관리] → 장부 관리 창 (모임 장부 보임)', pg.locator('.overlay').last.locator('.sh .t').inner_text() == '가계부 관리'
          and '모임 장부' in pg.locator('.overlay').last.inner_text())
    br.close()

    print('글자 크기 (1px)')
    br, pg = page(p, theme='retro')
    check('미니홈피 기본 14px', fs(pg) == '14px', fs(pg))
    pg.evaluate("App.go('settings', {section: 'deco'}, true)")
    pg.wait_for_timeout(400)
    check('설정에 글자 크기 막대와 px 표시', pg.locator('[data-fsr]').count() == 1 and pg.locator('.fs-v').inner_text() == '14px')
    pg.locator('[data-fs="1"]').click()
    check('＋ → 15px (1px)', fs(pg) == '15px' and pg.locator('.fs-v').inner_text() == '15px', fs(pg))
    pg.locator('[data-fs="-1"]').click()
    pg.locator('[data-fs="-1"]').click()
    check('－ 두 번 → 13px', fs(pg) == '13px', fs(pg))
    pg.evaluate("() => { const r = document.querySelector('[data-fsr]'); r.value = 20; r.dispatchEvent(new Event('input')); }")
    check('막대로 20px', fs(pg) == '20px' and pg.evaluate("window.__fake.prefs.fontpx") == '20', fs(pg))
    pg.locator('.fsz').scroll_into_view_if_needed()
    pg.screenshot(path=os.path.join(OUT, 'retro-font-20.png'))
    for _ in range(10):
        pg.locator('[data-fs="1"]').click()
    check('최대 26px 에서 멈춤', fs(pg) == '26px', fs(pg))
    pg.locator('[data-fs="0"]').click()
    check('[기본] → 14px, 저장 지움', fs(pg) == '14px' and 'fontpx' not in pg.evaluate("window.__fake.prefs"), fs(pg))
    pg.evaluate("App.setPref('theme', 'timeline'); App.applyTheme()")
    check('SNS 테마 기본 15px (휴대폰 글꼴)', fs(pg) == '15px', fs(pg))
    pg.evaluate("App.setFontPx(17)")
    check('SNS 테마에서도 정한 크기', fs(pg) == '17px', fs(pg))
    br.close()
    br, pg = page(p, theme='retro', prefs={'fontsize': 'l'})
    check('예전 설정(크게)은 같은 크기(16px)로', fs(pg) == '16px', fs(pg))
    br.close()

print()
if errs:
    print('콘솔 오류:', *errs[:10], sep='\n  ')
print('실패:', fails if fails else '없음')
raise SystemExit(1 if fails or errs else 0)
