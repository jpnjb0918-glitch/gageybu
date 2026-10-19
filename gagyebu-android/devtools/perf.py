"""속도 재기 (브라우저 + 가짜 NativeBridge): 켜기, 테마마다 가계부 그리기(이번 달·전체 기간), 화면 이동, 검색·결산.
  python3 perf.py [내역 수=10000]
  가짜 NativeBridge 는 sql.js(웹어셈블리)라 DB 시간은 실제 휴대폰(안드로이드 SQLite)과 다름 — 화면 그리기 비교용."""
import functools
import http.server
import json
import os
import socketserver
import sys
import threading
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
N = int(sys.argv[1]) if len(sys.argv) > 1 else 10000


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=ROOT))
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{srv.server_address[1]}/app/assets/www/index.html'
SEED = """n => {
  const lid = App.lid;
  const codes = DB.q("SELECT code FROM category WHERE ledger_id=? AND code NOT LIKE '0%'", [lid]).map(r => r.code);
  const items = ['점심', '커피', '마트 장보기', '버스', '전기세', '책', '영화', '택시', '약국', '편의점'];
  const t = U.today(), days = Math.floor(n / 6);
  const [y, m, d] = U.parts(t);
  const base = new Date(y, m - 1, d);
  let seed = 7; const rnd = k => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % k; };
  DB.tx(() => { for (let k = 0; k < n; k++) {
    const dt = new Date(base.getTime() - rnd(days) * 86400000);
    const iso = U.iso(dt.getFullYear(), dt.getMonth() + 1, dt.getDate());
    DB.run('INSERT INTO entry(ledger_id,date,item,income,expense,code,memo) VALUES(?,?,?,?,?,?,?)',
      [lid, iso, items[rnd(items.length)], 0, [3000, 4500, 12000, 35000][rnd(4)], codes[rnd(codes.length)], k % 5 ? '' : '메모']);
  } });
  App.dataChanged();
}"""
TIME = """js => { const t = performance.now(); eval(js); return performance.now() - t; }"""
res = []


def step(pg, name, js, repeat=3):
    best = min(pg.evaluate(TIME, js) for _ in range(repeat))
    pg.wait_for_timeout(30)
    res.append((name, best))


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 412, 'height': 860}, device_scale_factor=2, is_mobile=True, has_touch=True)
    ctx.add_init_script(path=os.path.join(ROOT, 'devtools', 'fake-native.js'))
    ctx.add_init_script("window.__fake && Object.assign(window.__fake.prefs, {theme: 'retro'});")
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    t = time.perf_counter()
    pg.goto(URL)
    pg.wait_for_selector('.navbar', timeout=30000)
    res.append(('켜기 (빈 자료, 첫 화면까지)', (time.perf_counter() - t) * 1000))
    pg.evaluate("() => document.querySelectorAll('.overlay').forEach(o => o.remove())")
    t = time.perf_counter()
    pg.evaluate(SEED, N)
    seed_ms = (time.perf_counter() - t) * 1000
    for th in ['retro', 'basic', 'feed', 'feed_light', 'feed_dark', 'timeline', 'timeline_light', 'timeline_dark']:
        step(pg, f'테마 바꾸기 → {th}', f"App.setPref('theme', '{th}'); App.applyTheme(); App.render()", 1)
        step(pg, f'  가계부 이번 달 ({th})', "App.go('ledger')")
        step(pg, f'  가계부 전체 기간 ({th})', "Pages.ledger.state.all = true; App.render()")
        pg.evaluate("Pages.ledger.state.all = false")
    pg.evaluate("App.setPref('theme', 'retro'); App.applyTheme(); App.render()")
    for page in ('calendar', 'report', 'assets', 'more', 'graph', 'settings', 'recurring', 'diary', 'memo', 'contacts'):
        step(pg, f'화면 이동 → {page}', f"App.go('{page}', {{}}, true)")
    step(pg, '검색 (전체 기간)', "App.go('search', {}, true); Pages.search.openWith({start: '2000-01-01', end: '2100-12-31', codes: []})")
    step(pg, '결산 년결산', "App.go('report'); document.querySelector('.seg [data-k=yearly]').click()")
    step(pg, '결산 일일', "document.querySelector('.seg [data-k=daily]').click()")
    br.close()

print(f'\n내역 {N}건 (넣기 {seed_ms:.0f}ms)')
for name, el in res:
    print(f'{el:8.0f} ms  {name}')
if errs:
    print('오류:', errs[:5])
