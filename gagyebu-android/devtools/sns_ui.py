"""피드·타임라인 화면의 아이콘·탭·동그라미가 제 기능을 하는지 + 추가 글꼴 (브라우저 + 가짜 NativeBridge).
  python3 sns_ui.py      → shots/sns/ui-*.png"""
import functools
import http.server
import json
import os
import re
import socketserver
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'devtools', 'shots', 'sns')
os.makedirs(OUT, exist_ok=True)
SEED = re.search(r'SEED = r"""(.*?)"""', open(os.path.join(ROOT, 'devtools', 'themes.py'), encoding='utf-8').read(), re.S).group(1)


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


def page(p, theme, prefs=None):
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 412, 'height': 860}, device_scale_factor=2, is_mobile=True, has_touch=True)
    ctx.add_init_script(path=os.path.join(ROOT, 'devtools', 'fake-native.js'))
    init = {'theme': theme}
    init.update(prefs or {})
    ctx.add_init_script(f"window.__fake && Object.assign(window.__fake.prefs, {json.dumps(init)});")
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    pg.goto(URL)
    pg.wait_for_selector('.navbar', timeout=20000)
    pg.wait_for_timeout(400)
    pg.evaluate("() => document.querySelectorAll('.overlay').forEach(o => o.remove())")
    pg.evaluate(SEED)
    pg.wait_for_timeout(300)
    return br, pg


top_title = lambda pg: pg.locator('.overlay').last.locator('.sh .t').inner_text() if pg.locator('.overlay').count() else ''

with sync_playwright() as p:
    print('피드')
    br, pg = page(p, 'feed')
    check('첫 화면: 손글씨 로고 · ⊕ 는 머리 줄 · 아래 탭은 아이콘', pg.locator('.banner .logo').count() == 1 and pg.locator('.banner .add-slot .fab').count() == 1
          and pg.locator('.navbar.icons svg').count() >= 4 and pg.locator('.navbar .me').count() == 1)
    check('프로필 머리가 맨 위 (화면 구성 기본 순서)', pg.evaluate("document.querySelector('.content').firstElementChild.className") == 'ig-prof')
    d0 = pg.evaluate("document.querySelector('.post').dataset.day")
    pg.locator('.post').first.locator('[data-add]').first.click()
    pg.wait_for_timeout(300)
    check('💬 → 그 날짜로 새 내역 창', top_title(pg) == '새 내역 입력' and pg.locator('.overlay [data-k=date]').input_value() == d0, d0)
    pg.evaluate('while (UI.closeTop()) {}')
    pg.locator('.post').first.locator('[data-cal]').click()
    pg.wait_for_timeout(300)
    check('📅 → 달력에서 그 날 (뒤로 가기 있음)', pg.locator('.banner .t').inner_text() == '달력' and pg.locator(f'.cal td.sel[data-d="{d0}"]').count() == 1
          and pg.locator('.banner .back').is_visible())
    pg.evaluate('App.onBack()')
    pg.wait_for_timeout(250)
    pg.locator('.post').first.locator('.pmenu').click()
    pg.wait_for_timeout(250)
    check('⋯ → 그 날 메뉴 (새 내역·달력)', '이 날 새 내역' in pg.locator('.overlay').last.inner_text())
    pg.evaluate('while (UI.closeTop()) {}')
    many = pg.locator('.post:has([data-more])')
    if many.count():
        hidden0 = many.first.locator('.pcap li.x').first.is_visible()
        many.first.locator('[data-more]').click()
        check('내역 5건 이상은 접힘 → [모두 보기]로 펼침', not hidden0 and many.first.locator('.pcap li.x').first.is_visible())
    code = pg.evaluate("document.querySelector('.ig-hl [data-code]').dataset.code")
    pg.locator('.ig-hl [data-code]').first.click()
    pg.wait_for_timeout(300)
    n = pg.evaluate(f"""() => {{ const s = U.parts(U.today()); return L.search(App.lid, {{start: U.iso(s[0], s[1], 1), end: U.iso(s[0], s[1], U.monthEnd(s[0], s[1])), codes: ['{code}'], amountSide: '수입+지출', amountOp: '같은 금액', order: 'date', desc: true}}).length; }}""")
    check('지출 많은 계정 동그라미 → 그 계정·이 달 검색 결과', pg.locator('.banner .t').inner_text() == '검색' and pg.locator('.content li[data-id]').count() == n > 0, str(n))
    pg.evaluate('App.onBack()')
    pg.wait_for_timeout(250)
    pg.locator('.ig-tabs [data-o=all]').click()
    pg.wait_for_timeout(250)
    check('탭 [전체 기간]', pg.evaluate('Pages.ledger.state.all') is True and pg.locator('.ig-tabs [data-o=all].on').count() == 1)
    pg.locator('.ig-tabs [data-o=month]').click()
    pg.locator('.ig-tabs [data-o=desc]').click()
    pg.wait_for_timeout(250)
    check('탭 [최근 것 위로] → 오래된 것 위로', pg.evaluate('Pages.ledger.state.desc') is False)
    pg.locator('.ig-tabs [data-o=desc]').click()
    pg.locator('.banner .add-slot .fab').click()
    pg.wait_for_timeout(250)
    check('머리 줄 ⊕ → 새 내역', top_title(pg) == '새 내역 입력')
    pg.evaluate('while (UI.closeTop()) {}')
    br.close()

    print('타임라인')
    br, pg = page(p, 'timeline')
    check('첫 화면: 왼쪽 내 동그라미 · 가운데 고양이 · 탭이 맨 위 · 쓰기 단추', pg.locator('.banner .tb-av').is_visible() and pg.locator('.banner .bimg').is_visible()
          and pg.evaluate("document.querySelector('.content').firstElementChild.className") == 'tw-tabs' and pg.locator('body > .fab').count() == 1)
    first = pg.evaluate("(() => { const li = document.querySelector('li.tw'); return L.getEntry(Number(li.dataset.id)); })()")
    pg.locator('li.tw').first.locator('[data-copy]').click()
    pg.wait_for_timeout(300)
    check('🔁 → 같은 내용을 오늘 날짜 새 내역으로 (다시 입력)', top_title(pg) == '다시 입력 (복사)' and pg.locator('.overlay [data-k=item]').input_value() == first['item']
          and pg.locator('.overlay [data-k=date]').input_value() == pg.evaluate('U.today()'))
    n0 = pg.evaluate("DB.val('SELECT COUNT(*) AS v FROM entry')")
    pg.locator('.overlay').last.locator('.sf .btn.pri').click()
    pg.wait_for_timeout(300)
    check('저장하면 새 내역 하나 더 (원래 내역은 그대로)', pg.evaluate("DB.val('SELECT COUNT(*) AS v FROM entry')") == n0 + 1
          and pg.evaluate(f"L.getEntry({first['id']}).date") == first['date'])
    pg.locator('li.tw').first.locator('[data-edit]').click()
    pg.wait_for_timeout(300)
    check('💬 → 수정 창', top_title(pg) == '내역 수정')
    pg.evaluate('while (UI.closeTop()) {}')
    pg.locator('.tw-trend [data-code]').first.click()
    pg.wait_for_timeout(300)
    check('많이 쓴 곳 → 검색', pg.locator('.banner .t').inner_text() == '검색' and pg.locator('.content li[data-id]').count() > 0)
    pg.evaluate('App.onBack()')
    pg.wait_for_timeout(200)
    pg.locator('.banner .tb-av').click()
    pg.wait_for_timeout(250)
    check('왼쪽 내 동그라미 → 더보기 (아이콘 목록)', pg.locator('.banner .t').inner_text() == '더보기' and pg.locator('.menu-list li').count() >= 5)
    br.close()

    print('글꼴 (무료 한글 글꼴)')
    br, pg = page(p, 'feed')
    pg.evaluate("App.go('settings', {section: 'deco'}, true)")
    pg.wait_for_timeout(300)
    opts = pg.evaluate("Array.from(document.querySelectorAll('[data-p=font] option')).map(o => o.value)")
    check('글꼴 고르기에 고운돋움·주아·개구·서툰이야기', opts == ['pixel', 'system', 'gowun', 'jua', 'gaegu', 'poorstory'], str(opts))
    for key, fam in (('gowun', 'Gowun Dodum'), ('jua', 'Jua'), ('gaegu', 'Gaegu'), ('poorstory', 'Poor Story')):
        pg.locator('[data-p=font]').select_option(key)
        pg.wait_for_timeout(300)
        used = pg.evaluate("getComputedStyle(document.querySelector('.banner .t')).fontFamily")
        loaded = pg.evaluate(f"document.fonts.check('16px \"{fam}\"', '가계부')")
        check(f'{key} → 화면 글꼴 {fam} (글꼴 파일 읽힘)', used.replace('"', '').startswith(fam) and loaded, f'{used} {loaded}')
    pg.evaluate("App.go('ledger')")
    pg.wait_for_timeout(400)
    pg.screenshot(path=os.path.join(OUT, 'ui-feed-poorstory.png'))
    pg.evaluate("App.setPref('theme', 'retro'); App.applyTheme(); App.render()")
    check('미니홈피 테마에서도 고른 글꼴', pg.evaluate("getComputedStyle(document.body).fontFamily").startswith('"Poor Story"'))
    pg.evaluate("App.setPref('font', 'pixel'); App.applyTheme()")
    check('도트 글꼴로 되돌리기', pg.evaluate("getComputedStyle(document.body).fontFamily").startswith("Galmuri11"))
    br.close()

print()
if errs:
    print('콘솔 오류:', *errs[:10], sep='\n  ')
print('실패:', fails if fails else '없음')
raise SystemExit(1 if fails or errs else 0)
