"""테마별 화면 시험: 예시 자료를 넣고 테마마다 모든 화면을 그려 오류·가로 넘침을 확인하고 사진을 찍는다.

  python3 themes.py            → shots/themes/<테마>-<화면>.png
"""
import functools
import http.server
import os
import socketserver
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'devtools', 'shots', 'themes')
os.makedirs(OUT, exist_ok=True)
THEMES = ['retro', 'basic', 'feed', 'timeline', 'timeline_dark']
WIDTHS = [360, 412]


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=ROOT))
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{srv.server_address[1]}/app/assets/www/index.html'

SEED = r"""
() => {
  const lid = App.lid;
  const cats = DB.q("SELECT code, name FROM category WHERE ledger_id=? ORDER BY code", [lid]);
  const inc = cats.filter(c => c.code.startsWith('0'));
  const exp = cats.filter(c => !c.code.startsWith('0'));
  const t = U.today(); const [y, m] = U.parts(t);
  const day = d => U.iso(y, m, Math.min(d, U.monthEnd(y, m)));
  const items = [['점심 김치찌개', 9000, '회사 앞 식당'], ['지하철 교통카드 충전', 50000, ''], ['편의점 간식', 4300, '아주 긴 메모를 써 보면 줄이 어떻게 바뀌는지 확인하려고 일부러 길게 적은 메모입니다'],
                 ['통신요금', 59000, '휴대폰'], ['마트 장보기 (채소·과일·우유·계란)', 87650, ''], ['카페', 5500, ''], ['병원', 12000, '감기'], ['책 구입', 18000, '']];
  let n = 0;
  for (let d = 1; d <= 12; d++) {
    for (let k = 0; k < 1 + (d % 3); k++) {
      const [it, amt, memo] = items[(d + k) % items.length];
      const c = exp[(d * 3 + k) % exp.length];
      L.addEntry(lid, { date: day(d), item: it, income: 0, expense: amt + d * 100, code: c.code, memo }); n++;
    }
  }
  L.addEntry(lid, { date: day(1), item: '월급', income: 3200000, expense: 0, code: inc[0].code, memo: '10월 급여' });
  L.addEntry(lid, { date: day(5), item: '용돈', income: 100000, expense: 0, code: inc[0].code, memo: '' });
  App.dataChanged();
  return n + 2;
}
"""

OVERFLOW = """
() => {
  const vw = document.documentElement.clientWidth;
  const bad = [];
  if (document.documentElement.scrollWidth > vw + 1) bad.push('page ' + document.documentElement.scrollWidth + '>' + vw);
  for (const el of document.querySelectorAll('.content, .topbar, .navbar, .sheet .sb')) {
    if (el.scrollWidth > el.clientWidth + 1) bad.push((el.className || el.tagName) + ' ' + el.scrollWidth + '>' + el.clientWidth);
  }
  return bad;
}
"""

fails, errors = [], []
with sync_playwright() as p:
    br = p.chromium.launch()
    for w in WIDTHS:
        for th in THEMES:
            ctx = br.new_context(viewport={'width': w, 'height': 800}, device_scale_factor=2, is_mobile=True, has_touch=True)
            ctx.add_init_script(path=os.path.join(ROOT, 'devtools', 'fake-native.js'))
            ctx.add_init_script(f"window.__fake && (window.__fake.prefs.theme = '{th}');")
            pg = ctx.new_page()
            pg.on('pageerror', lambda e, th=th: errors.append(f'{th}: {e}'))
            pg.on('console', lambda m, th=th: errors.append(f'{th}: {m.text}') if m.type == 'error' else None)
            pg.goto(URL)
            pg.wait_for_selector('.navbar', timeout=20000)
            pg.wait_for_timeout(500)
            pg.evaluate("() => document.querySelectorAll('.overlay').forEach(o => o.remove())")
            pg.evaluate(SEED)
            pg.wait_for_timeout(300)
            pages = [('ledger', "App.go('ledger')"), ('calendar', "App.go('calendar')"), ('report', "App.go('report')"),
                     ('assets', "App.go('assets')"), ('more', "App.go('more')"), ('search', "App.go('search', {}, true)"),
                     ('graph', "App.go('graph', {}, true)"), ('settings', "App.go('settings', {section:'deco'}, true)")]
            for name, js in pages:
                pg.evaluate(js)
                pg.wait_for_timeout(250)
                bad = pg.evaluate(OVERFLOW)
                if bad:
                    fails.append(f'{w}px {th} {name}: {bad}')
                if w == 412 or name == 'ledger':
                    pg.screenshot(path=os.path.join(OUT, f'{w}-{th}-{name}.png'))
            # 가계부 목록 아래로 내려 본 모습 + 내역 누르면 수정 창이 뜨는지 (기능 그대로인지)
            pg.evaluate("App.go('ledger')")
            pg.wait_for_timeout(200)
            pg.evaluate("document.querySelector('.content').scrollTop = 520")
            pg.wait_for_timeout(150)
            if w == 412:
                pg.screenshot(path=os.path.join(OUT, f'{w}-{th}-ledger-scrolled.png'))
            pg.locator('li[data-id]').first.click()
            pg.wait_for_timeout(300)
            title = pg.locator('.overlay .sheet .sh .t').first.text_content() if pg.locator('.overlay .sheet').count() else ''
            if title != '내역 수정':
                fails.append(f'{w}px {th}: 내역을 눌렀을 때 수정 창이 안 뜸 ({title!r})')
            bad = pg.evaluate(OVERFLOW)
            if bad:
                fails.append(f'{w}px {th} entry-sheet: {bad}')
            if w == 412:
                pg.screenshot(path=os.path.join(OUT, f'{w}-{th}-entry.png'))
            print(f'{w}px {th}: bars={pg.evaluate("window.__fake.bars")}, 목록 항목 {pg.locator("li[data-id]").count()}개')
            ctx.close()
    br.close()

print('\n'.join(errors) or 'NO CONSOLE ERRORS')
print('\n'.join(fails) or 'NO OVERFLOW / ALL OK')
