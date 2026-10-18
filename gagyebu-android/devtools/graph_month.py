"""그래프 종류 바꾸기·연월 바로 고르기 시험 (브라우저 + 가짜 NativeBridge). 눌러서 확인하고 사진을 찍는다.

  python3 graph_month.py      → shots/graph/*.png
"""
import functools
import http.server
import os
import socketserver
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'devtools', 'shots', 'graph')
os.makedirs(OUT, exist_ok=True)


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=ROOT))
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{srv.server_address[1]}/app/assets/www/index.html'
fails, errs = [], []
KINDS = ['line', 'bar', 'stack', 'area', 'cum', 'hbar', 'pie', 'donut']


def check(name, cond, extra=''):
    print(('  ✓ ' if cond else '  ✗ ') + name + (f'  ({extra})' if extra and not cond else ''))
    if not cond:
        fails.append(name)


OVERFLOW = """() => { const vw = document.documentElement.clientWidth; const bad = [];
  if (document.documentElement.scrollWidth > vw + 1) bad.push('page');
  for (const el of document.querySelectorAll('.content, .sheet .sb, .topbar')) if (el.scrollWidth > el.clientWidth + 1) bad.push(el.className);
  return bad; }"""

SEED = """() => {
  const lid = App.lid, y = Number(U.today().slice(0, 4));
  const cats = L.categories(lid);
  const ex = ['1', '3', '4', '5'].map(g => cats.find(c => c.code[0] === g).code);   // 대분류 4개 (+수입)
  const inc = cats.find(c => c.code[0] === '0').code;
  for (let m = 1; m <= 10; m++) {
    const d = dd => U.iso(y, m, dd);
    L.addEntry(lid, { date: d(25), item: '월급', income: 2500000, code: inc });
    L.addEntry(lid, { date: d(3), item: '장보기', expense: 300000 + m * 20000, code: ex[0] });
    L.addEntry(lid, { date: d(10), item: '교통', expense: 150000, code: ex[1] });
    L.addEntry(lid, { date: d(15), item: '외식', expense: m % 3 ? 80000 : 220000, code: ex[2] });
  }
  L.addEntry(lid, { date: U.iso(y, 4, 20), item: '환불', expense: -20000, code: ex[3] });
  App.dataChanged();
  return { ex, inc };
}"""


def sheet(pg):
    return pg.locator('.overlay').last


def run(theme, full):
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(viewport={'width': 360, 'height': 780}, device_scale_factor=2, is_mobile=True, has_touch=True)
        ctx.add_init_script(path=os.path.join(ROOT, 'devtools', 'fake-native.js'))
        ctx.add_init_script(f"window.__fake && (window.__fake.prefs.theme = '{theme}');")
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: errs.append(f'[{theme}] {e}'))
        pg.on('console', lambda m: errs.append(f'[{theme}] {m.text}') if m.type == 'error' else None)
        pg.goto(URL)
        pg.wait_for_selector('.navbar', timeout=20000)
        pg.wait_for_timeout(400)
        pg.evaluate("() => document.querySelectorAll('.overlay').forEach(o => o.remove())")
        seed = pg.evaluate(SEED)
        year = pg.evaluate("Number(U.today().slice(0, 4))")
        tm = pg.evaluate("Number(U.today().slice(5, 7))")

        # ── 그래프 종류 ──
        print(f'[{theme}] 그래프 종류')
        pg.evaluate("App.go('graph', {}, true)")
        pg.wait_for_timeout(300)
        chips = pg.evaluate("Array.from(document.querySelectorAll('.gkind .chip')).map(b => b.dataset.g)")
        check('종류 단추 8개', chips == KINDS, str(chips))
        check('처음은 꺾은선', pg.evaluate("document.querySelector('.gkind .chip.on').dataset.g") == 'line')
        n_series = pg.evaluate("document.querySelectorAll('.legend span').length")
        check('대분류 전체: 수입+지출 4개 = 5개 항목', n_series == 5, str(n_series))
        for k in KINDS if full else ['line', 'stack', 'hbar', 'donut']:
            pg.click(f'.gkind .chip[data-g={k}]')
            pg.wait_for_timeout(150)
            on = pg.evaluate("document.querySelector('.gkind .chip.on').dataset.g")
            svg = pg.evaluate("(document.querySelector('.gbox svg.chart') || {}).dataset?.kind")
            check(f'{k}: 단추 켜짐·그림 종류', on == k and svg == k, f'on={on} svg={svg}')
            pref = pg.evaluate("window.__fake.prefs.graph_kind")
            check(f'{k}: 휴대폰에 기억', pref == (None if k == 'line' else k), str(pref))
            check(f'{k}: 가로 넘침 없음', not pg.evaluate(OVERFLOW), str(pg.evaluate(OVERFLOW)))
            info = pg.evaluate("""() => { const s = document.querySelector('.gbox svg.chart'); const q = x => s.querySelectorAll(x).length;
              return { poly: q('polyline'), rect: q('rect'), polygon: q('polygon'), path: q('path'),
                ys: Array.from(s.querySelectorAll('polyline')).map(p => p.getAttribute('points').split(' ').map(t => Number(t.split(',')[1]))),
                names: Array.from(s.querySelectorAll('text.gv')).map(t => t.textContent),
                legend: Array.from(document.querySelectorAll('.gbox .legend span')).map(x => x.textContent),
                note: document.querySelector('.gbox .gnote').textContent,
                skip: Array.from(document.querySelectorAll('.gbox > .small.muted:not(.gnote)')).map(x => x.textContent).join('|'),
                tot: Array.from(document.querySelectorAll('table.rep tr')).slice(1).map(tr => [tr.cells[0].textContent, Number(tr.cells[tr.cells.length - 1].textContent.replace(/[^0-9-]/g, ''))]) }; }""")
            if k in ('line', 'cum'):
                check(f'{k}: 선 5개', info['poly'] == 5, str(info['poly']))
            if k == 'cum':
                ys = info['ys'][0]
                check('누계: 첫 항목은 계속 올라감(화면 y 줄어듦)', all(b <= a + 1e-6 for a, b in zip(ys, ys[1:])), str(ys))
            if k == 'area':
                check('영역: 칠한 면 5개 + 선 5개', info['polygon'] == 5 and info['poly'] == 5, str(info))
            if k == 'bar':
                check('막대: 0 이 아닌 값마다 막대 (10×4+1=41)', info['rect'] == 41, str(info['rect']))
            if k == 'stack':
                check('누적 막대: 0 이 아닌 값마다 조각 (41)', info['rect'] == 41, str(info['rect']))
                col = pg.evaluate("""() => { const s = document.querySelector('.gbox svg.chart');
                  const r = Array.from(s.querySelectorAll('rect')); const xs = {};
                  r.forEach(e => { const x = e.getAttribute('x'); (xs[x] = xs[x] || []).push([+e.getAttribute('y'), +e.getAttribute('height')]); });
                  return Object.values(xs).map(v => v.sort((a, b) => a[0] - b[0])); }""")
                gaps = [round(seg[i + 1][0] - (seg[i][0] + seg[i][1]), 1) for seg in col for i in range(len(seg) - 1)]
                check('누적 막대: 조각이 틈 없이 쌓임', all(abs(g) <= 0.2 for g in gaps), str(gaps[:8]))
            if k == 'hbar':
                check('가로 막대: 막대 5개', info['rect'] == 5, str(info['rect']))
                want = [n for n, _ in sorted(info['tot'], key=lambda x: -x[1])]
                check('가로 막대: 합계 큰 것부터', [n.rstrip('…') for n in info['names']] == [w[:len(n.rstrip('…'))] for w, n in zip(want, info['names'])], f"{info['names']} / {want}")
            if k in ('pie', 'donut'):
                pcts = [float(t.split()[-1].rstrip('%')) for t in info['legend']]
                check(f'{k}: 0보다 큰 4개 항목만, 비율 합 100%', len(pcts) == 4 and abs(sum(pcts) - 100) < 0.2, str(info['legend']))
                check(f'{k}: 뺀 항목 안내', '1개 항목은 비율에서 뺐어요' in info['skip'], info['skip'])
                check(f'{k}: 조각 4개', info['path'] == 4, str(info['path']))
                if k == 'donut':
                    check('도넛: 가운데 합계', len(info['names']) == 1 and info['names'][0].endswith('만'), str(info['names']))
            pg.screenshot(path=os.path.join(OUT, f'{theme}-{k}.png'), full_page=False)
        # 다시 그려도 기억
        pg.click('.gkind .chip[data-g=donut]')
        pg.evaluate("App.go('ledger', {}, true)")
        pg.wait_for_timeout(200)
        pg.evaluate("App.go('graph', {}, true)")
        pg.wait_for_timeout(300)
        check('다른 화면 갔다 와도 도넛', pg.evaluate("document.querySelector('.gkind .chip.on').dataset.g") == 'donut')

        # ── 연도 바로 고르기 (그래프) ──
        print(f'[{theme}] 연도 고르기')
        lbl = pg.locator('.monthnav .lbl').first
        check('연도 글자에 ▾ 표시', '▾' in lbl.inner_text(), lbl.inner_text())
        lbl.click()
        pg.wait_for_timeout(250)
        check('연도 고르기 창', sheet(pg).locator('.sh .t').inner_text() == '연도 고르기')
        check('달 격자는 없음', sheet(pg).locator('.mp-months').count() == 0)
        years = pg.evaluate("Array.from(document.querySelectorAll('.overlay:last-child .mp-years button')).map(b => +b.dataset.y)")
        check('올해 앞뒤로 12해', years == list(range(year - 5, year + 7)), str(years))
        if full:
            pg.screenshot(path=os.path.join(OUT, f'{theme}-pick-year.png'))
        sheet(pg).locator(f'.mp-years button[data-y="{year - 2}"]').click()
        pg.wait_for_timeout(300)
        check('창 닫힘', pg.locator('.overlay').count() == 0)
        check(f'{year - 2}년으로 이동', pg.locator('.monthnav .lbl').first.inner_text().startswith(f'{year - 2}년'),
              pg.locator('.monthnav .lbl').first.inner_text())
        check('그 해는 자료 없음 안내', pg.locator('.content .empty').count() == 1)
        pg.locator('.monthnav .lbl').first.click()
        pg.wait_for_timeout(250)
        sheet(pg).locator('.sf').get_by_role('button', name='올해', exact=True).click()
        pg.wait_for_timeout(300)
        check('올해로 돌아옴', pg.locator('.monthnav .lbl').first.inner_text().startswith(f'{year}년'))

        # ── 연·월 바로 고르기 (가계부·달력·결산·일기장·자산) ──
        print(f'[{theme}] 연·월 고르기')
        for page in ['ledger', 'calendar', 'report', 'diary'] if full else ['ledger']:
            pg.evaluate(f"App.go('{page}', {{}}, true)")
            pg.wait_for_timeout(300)
            lbl = pg.locator('.monthnav .lbl').first
            before = lbl.inner_text()
            lbl.click()
            pg.wait_for_timeout(250)
            check(f'{page}: 연·월 고르기 창', sheet(pg).locator('.sh .t').inner_text() == '연·월 고르기')
            on = pg.evaluate("Array.from(document.querySelectorAll('.overlay:last-child .mp-grid button.on')).map(b => b.textContent)")
            check(f'{page}: 지금 연·월이 표시됨', on == [str(year), f'{tm}월'], str(on))
            if page == 'ledger' and full:
                pg.screenshot(path=os.path.join(OUT, f'{theme}-pick-month.png'))
            sheet(pg).locator('[data-p="-1"]').click()
            pg.wait_for_timeout(100)
            rng = sheet(pg).locator('.mp-range').inner_text()
            check(f'{page}: ‹ 로 12해 앞', rng == f'{year - 17} ~ {year - 6}년', rng)
            sheet(pg).locator(f'.mp-years button[data-y="{year - 7}"]').click()
            pg.wait_for_timeout(100)
            check(f'{page}: 연도를 눌러도 아직 안 닫힘', pg.locator('.overlay').count() == 1)
            check(f'{page}: 고른 해 안내', sheet(pg).locator('.mp-sub').inner_text() == f'{year - 7}년의 몇 월로 갈까요?')
            sheet(pg).locator('.mp-months button[data-m="3"]').click()
            pg.wait_for_timeout(300)
            now = pg.locator('.monthnav .lbl').first.inner_text()
            check(f'{page}: {year - 7}년 3월로 이동', pg.locator('.overlay').count() == 0 and f'{year - 7}년 3월' in now, f'{before} → {now}')
            pg.locator('.monthnav [data-d="1"]').first.click()
            pg.wait_for_timeout(250)
            now = pg.locator('.monthnav .lbl').first.inner_text()
            check(f'{page}: ▶ 는 그대로 한 달씩', f'{year - 7}년 4월' in now, now)
            pg.locator('.monthnav .lbl').first.click()
            pg.wait_for_timeout(250)
            sheet(pg).locator('.sf').get_by_role('button', name='이번 달', exact=True).click()
            pg.wait_for_timeout(300)
            now = pg.locator('.monthnav .lbl').first.inner_text()
            check(f'{page}: 이번 달로', f'{year}년 {tm}월' in now, now)
        if full:
            # 자산 화면의 카드 달 (있으면)
            pg.evaluate("App.go('assets', {}, true)")
            pg.wait_for_timeout(300)
            check('자산 화면 오류 없음', not [e for e in errs if theme in e])
        br.close()


run('retro', True)
run('basic', False)
run('feed', False)
run('timeline_dark', True)
print()
if errs:
    print('콘솔 오류:', *errs[:10], sep='\n  ')
print('실패:', fails if fails else '없음')
raise SystemExit(1 if fails or errs else 0)
