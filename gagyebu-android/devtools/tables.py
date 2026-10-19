"""테마별 표 점검 (결산 보고서 5가지 + 그래프 표) — 브라우저 + 가짜 NativeBridge.
  머리줄·첫 칸·대분류 이름이 밀어도 붙어 있는지, 소계 줄 색이 첫 칸까지 같은지, 줄무늬·0 흐리게·밑줄 없음,
  옆으로 더 있을 때 그늘/안내, 고친 포인트 색을 표 색이 따라가는지.
  python3 tables.py      → shots/tables/<테마>-<보고서>.png"""
import functools
import http.server
import json
import os
import re
import socketserver
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'devtools', 'shots', 'tables')
os.makedirs(OUT, exist_ok=True)
SEED = re.search(r'SEED = r"""(.*?)"""', open(os.path.join(ROOT, 'devtools', 'themes.py'), encoding='utf-8').read(), re.S).group(1)
# 지난달 내역도 (증감·년결산이 비지 않게)
SEED2 = r"""
() => {
  const lid = App.lid;
  const exp = DB.q("SELECT code FROM category WHERE ledger_id=? AND code NOT LIKE '0%' ORDER BY code", [lid]);
  const [y, m] = U.addMonths(...U.parts(U.today()), -1);
  for (let d = 1; d <= 20; d++) L.addEntry(lid, { date: U.iso(y, m, d), item: '지난달 ' + d, income: 0, expense: 3000 * d, code: exp[(d * 5) % exp.length].code, memo: '' });
  L.addEntry(lid, { date: U.iso(y, m, 1), item: '월급', income: 3200000, expense: 0, code: '00', memo: '' });
  App.dataChanged();
}
"""


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


THEMES = ['retro', 'basic', 'feed', 'feed_light', 'feed_dark', 'timeline', 'timeline_light', 'timeline_dark']
GEOM = """() => {
  const w = document.querySelector('.tablewrap'), r = w.getBoundingClientRect();
  const th = w.querySelector('th').getBoundingClientRect();
  const td = w.querySelector('tr:not(.grp) td:first-child').getBoundingClientRect();
  const g = w.querySelector('.gname'); const gr = g ? g.getBoundingClientRect() : null;
  return { wt: r.top, wl: r.left, tht: th.top, tdl: td.left, gl: gr ? gr.left : null };
}"""
BG = "e => getComputedStyle(e).backgroundColor"

with sync_playwright() as p:
    br = p.chromium.launch()
    for th in THEMES:
        print(th)
        ctx = br.new_context(viewport={'width': 412, 'height': 860}, device_scale_factor=2, is_mobile=True, has_touch=True)
        ctx.add_init_script(path=os.path.join(ROOT, 'devtools', 'fake-native.js'))
        ctx.add_init_script(f"window.__fake && Object.assign(window.__fake.prefs, {json.dumps({'theme': th})});")
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        pg.goto(URL)
        pg.wait_for_selector('.navbar', timeout=20000)
        pg.wait_for_timeout(300)
        pg.evaluate("() => document.querySelectorAll('.overlay').forEach(o => o.remove())")
        pg.evaluate(SEED)
        pg.evaluate(SEED2)
        pg.evaluate("App.go('report')")
        pg.wait_for_timeout(400)
        # 머리줄 고정: 표 안에서 아래로 밀어도 머리줄이 표 위에 붙어 있음
        g0 = pg.evaluate(GEOM)
        pg.evaluate("document.querySelector('.tablewrap').scrollTop = 400")
        pg.wait_for_timeout(100)
        g1 = pg.evaluate(GEOM)
        check('아래로 밀어도 머리줄이 위에 붙어 있음', abs(g1['tht'] - g1['wt']) <= 2 and abs(g0['tht'] - g1['tht']) <= 2, f"{g0} {g1}")
        pg.evaluate("document.querySelector('.tablewrap').scrollTop = 0")
        # 첫 칸·대분류 이름 고정 + 옆으로 더 있으면 그늘·안내
        wide = pg.evaluate("(() => { const w = document.querySelector('.tablewrap'); return w.scrollWidth > w.clientWidth + 2; })()")
        if wide:
            check('옆으로 더 있으면 오른쪽 그늘 + 안내 글', pg.evaluate("document.querySelector('.tbox').classList.contains('more') && !document.querySelector('.tbox-hint').hidden"))
            pg.evaluate("(() => { const w = document.querySelector('.tablewrap'); w.scrollLeft = w.scrollWidth; })()")
            pg.wait_for_timeout(150)
            g2 = pg.evaluate(GEOM)
            check('옆으로 밀어도 계정과목·대분류 이름은 왼쪽에 남음', abs(g2['tdl'] - g0['tdl']) <= 1 and g2['gl'] is not None and abs(g2['gl'] - g0['gl']) <= 2, f"{g0} {g2}")
            check('오른쪽 끝까지 밀면 그늘 사라짐', not pg.evaluate("document.querySelector('.tbox').classList.contains('more')"))
            pg.evaluate("document.querySelector('.tablewrap').scrollLeft = 0")
            pg.wait_for_timeout(100)
        # 색
        sub = pg.locator('tr.sub').first
        cells = sub.locator('td').evaluate_all(f"ts => ts.map({BG})")
        check('소계 줄은 첫 칸까지 같은 색', len(set(cells)) == 1, str(cells))
        foot = pg.locator('tr.foot').first.locator('td').first.evaluate(BG)
        cat = pg.locator('table.rep tr:not(.grp):not(.sub):not(.foot):not(.z)').nth(1).locator('td').nth(1).evaluate(BG)
        zeb = pg.locator('table.rep tr.z').first.locator('td').nth(1).evaluate(BG)
        grp = pg.locator('tr.grp td').first.evaluate(BG)
        check('계정 줄 · 줄무늬 · 대분류 · 소계 · 합계 색이 서로 다름', len({cat, zeb, grp, cells[0], foot}) == 5, str([cat, zeb, grp, cells[0], foot]))
        if th in ('retro', 'feed', 'timeline'):     # 미니홈피 색: PC판 미니홈피 표와 같은 하늘색 띠 머리줄·민트 줄무늬·살구색 소계
            hdr = pg.evaluate("getComputedStyle(document.querySelector('table.rep th')).backgroundImage")
            check('미니홈피 색 표: 머리줄 하늘색 띠 · 민트 줄무늬 · 살구색 소계 (PC와 같음)',
                  'rgb(143, 230, 230)' in hdr and 'rgb(75, 213, 213)' in hdr and zeb == 'rgb(240, 251, 250)' and cells[0] == 'rgb(253, 241, 227)',
                  f'{hdr} {zeb} {cells[0]}')
        sep = pg.evaluate("getComputedStyle(document.querySelector('tr.sub td')).borderBottomWidth")
        check('대분류 끝(소계) 아래 굵은 선', sep == '2px', sep)
        z0 = pg.locator('td.z0')
        if z0.count():
            col = z0.first.evaluate("e => getComputedStyle(e).color")
            ink = pg.evaluate("getComputedStyle(document.querySelector('tr.sub td:first-child')).color")
            check('소계·합계의 0 은 흐린 색', col != ink, col)
        deco = pg.locator('td.tap').first.evaluate("e => getComputedStyle(e).textDecorationLine")
        check('금액에 밑줄 없음', deco == 'none', deco)
        check('계정 줄 0 은 빈칸', pg.evaluate("Array.from(document.querySelectorAll('tr:not(.sub):not(.foot):not(.grp) td.tap')).every(td => td.textContent.trim() !== '0')"))
        pg.screenshot(path=os.path.join(OUT, f'{th}-monthly.png'))
        # 다른 보고서 (오류 없이 그려지고 표가 화면 밖으로 넘치지 않음)
        for kind in ('yearly', 'daily', 'custom', 'budget'):
            pg.locator(f'.seg [data-k={kind}]').click()
            pg.wait_for_timeout(250)
            ok = pg.evaluate("(() => { const b = document.querySelector('.tbox'); return !!b && b.getBoundingClientRect().right <= document.documentElement.clientWidth + 1; })()")
            check(f'{kind}: 표가 화면 안에', ok)
            if kind == 'yearly':
                pg.screenshot(path=os.path.join(OUT, f'{th}-yearly.png'))
        pg.evaluate("App.go('graph')")
        pg.wait_for_timeout(300)
        check('그래프 표도 같은 표 상자 (줄무늬)', pg.locator('.tbox table.rep').count() == 1 and pg.locator('table.rep tr.z').count() >= 1)
        ctx.close()

    print('고친 포인트 색을 따라가는지 (밝게 테마)')
    ctx = br.new_context(viewport={'width': 412, 'height': 860}, device_scale_factor=1)
    ctx.add_init_script(path=os.path.join(ROOT, 'devtools', 'fake-native.js'))
    ctx.add_init_script("window.__fake && Object.assign(window.__fake.prefs, {theme: 'feed_light'});")
    pg = ctx.new_page()
    pg.goto(URL)
    pg.wait_for_selector('.navbar', timeout=20000)
    a = pg.evaluate("document.body.style.getPropertyValue('--rep-sub')")
    pg.evaluate("App.setCustomColor('accent', '#22AA44')")
    b = pg.evaluate("document.body.style.getPropertyValue('--rep-sub')")
    check('포인트 색을 바꾸면 소계 줄 색도 바뀜', a and b and a != b and b.upper() == '#EBF7EE', f'{a} → {b}')
    pg.evaluate("App.setCustomColor('accent', null)")
    check('처음 색으로 되돌리면 표 색도 되돌아감', pg.evaluate("document.body.style.getPropertyValue('--rep-sub')") == a)
    ctx.close()
    br.close()

print()
if errs:
    print('콘솔 오류:', *errs[:10], sep='\n  ')
print('실패:', fails if fails else '없음')
raise SystemExit(1 if fails or errs else 0)
