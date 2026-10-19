"""화면 전체 가시성 점검 (1.5.1) — 테마 8개 × 360·412px. 잘림·흐린 글자·안 보이는 테두리를 고친 것이 그대로인지.
  python3 visibility.py      → shots/vis/<폭>-<테마>-<화면>.png"""
import functools
import http.server
import json
import os
import re
import socketserver
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'devtools', 'shots', 'vis')
os.makedirs(OUT, exist_ok=True)
SEED = re.search(r'SEED = r"""(.*?)"""', open(os.path.join(ROOT, 'devtools', 'themes.py'), encoding='utf-8').read(), re.S).group(1)


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=ROOT))
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{srv.server_address[1]}/app/assets/www/index.html'
fails, errs = [], []
THEMES = ['retro', 'basic', 'feed', 'feed_light', 'feed_dark', 'timeline', 'timeline_light', 'timeline_dark']
# 글자색·바탕색 대비 (WCAG) — 브라우저가 계산한 rgb() 로
CONTRAST = """([a, b]) => {
  const p = s => s.match(/[\\d.]+/g).slice(0, 3).map(Number);
  const L = c => { const v = c.map(x => { x /= 255; return x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4; }); return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
  const [x, y] = [L(p(a)), L(p(b))].sort((m, n) => n - m);
  return (x + 0.05) / (y + 0.05);
}"""


def check(name, cond, extra=''):
    print(('  ✓ ' if cond else '  ✗ ') + name + (f'  ({extra})' if extra and not cond else ''))
    if not cond:
        fails.append(name)


def bg_of(pg, sel):
    """요소의 실제 바탕색 (투명이면 부모로 올라가며)"""
    return pg.evaluate("""s => { let e = document.querySelector(s);
      while (e) { const c = getComputedStyle(e).backgroundColor; if (c && !/rgba\\(0, 0, 0, 0\\)|transparent/.test(c)) return c; e = e.parentElement; }
      return 'rgb(255, 255, 255)'; }""", sel)


with sync_playwright() as p:
    br = p.chromium.launch()
    for w in (360, 412):
        for th in THEMES:
            print(f'{w}px {th}')
            ctx = br.new_context(viewport={'width': w, 'height': 820}, device_scale_factor=2, is_mobile=True, has_touch=True)
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
            pg.evaluate("App.go('ledger')")
            pg.wait_for_timeout(300)
            sns = th not in ('retro', 'basic')
            # 1) 금액·제목이 '…' 로 잘리지 않음
            if th.startswith('feed'):
                cut = pg.evaluate("Array.from(document.querySelectorAll('.ig-stats b')).filter(b => b.scrollWidth > b.clientWidth + 1).map(b => b.textContent)")
                check('피드 프로필 금액이 잘리지 않음', not cut, str(cut))
                lg = pg.evaluate("""(() => { const l = document.querySelector('.banner .logo'), k = document.querySelector('.ledger-pick');
                  return l && k ? l.getBoundingClientRect().right <= k.getBoundingClientRect().left + 1 : true; })()""")
                check('로고가 장부 단추 뒤로 가려지지 않음', lg)
                st = pg.locator('.ptile .stamp').first
                if st.count():
                    c = pg.evaluate(CONTRAST, [st.evaluate("e => getComputedStyle(e).color"), 'rgb(75, 213, 213)'])
                    check('날짜 도장이 알약 바탕 위 (카드 색과 상관없이 읽힘)', st.evaluate("e => getComputedStyle(e).backgroundColor") != 'rgba(0, 0, 0, 0)')
            if th.startswith('timeline'):
                check('고정글 금액·낱말이 줄 가운데서 끊기지 않음', pg.evaluate("getComputedStyle(document.querySelector('.tw-pin .txt')).wordBreak") == 'keep-all'
                      and pg.evaluate("getComputedStyle(document.querySelector('.tw-pin .txt b')).whiteSpace") == 'nowrap')
            # 2) 보조 글자(흐린 회색) 대비
            mut = pg.evaluate("getComputedStyle(document.body).getPropertyValue('--muted').trim()")
            card = pg.evaluate("getComputedStyle(document.body).getPropertyValue('--card').trim()")
            c = pg.evaluate(CONTRAST, [pg.evaluate(f"(() => {{ const d = document.createElement('div'); d.style.color = '{mut}'; document.body.appendChild(d); const v = getComputedStyle(d).color; d.remove(); return v; }})()"),
                                       pg.evaluate(f"(() => {{ const d = document.createElement('div'); d.style.color = '{card}'; document.body.appendChild(d); const v = getComputedStyle(d).color; d.remove(); return v; }})()")])
            check('보조 글자색 대비 4.5:1 이상', c >= 4.5, f'{mut} {c:.2f}')
            # 3) 아래 탭: 고른 탭 표시
            if sns:
                dot = pg.evaluate("getComputedStyle(document.querySelector('.navbar button.on'), '::after').backgroundColor")
                check('아래 탭: 고른 탭 아래 포인트 색 점', dot not in ('rgba(0, 0, 0, 0)', ''), dot)
            # 4) ＋ 단추: 아래로 내리면 숨고 위로 올리면 다시
            if pg.locator('body > .fab').count():
                pg.evaluate("(() => { const c = document.querySelector('.content'); c.scrollTop = 300; c.dispatchEvent(new Event('scroll')); })()")
                pg.wait_for_timeout(300)
                away = pg.evaluate("document.body.classList.contains('fab-away') && getComputedStyle(document.querySelector('body > .fab')).opacity === '0'")
                pg.evaluate("(() => { const c = document.querySelector('.content'); c.scrollTop = 100; c.dispatchEvent(new Event('scroll')); })()")
                pg.wait_for_timeout(300)
                back = not pg.evaluate("document.body.classList.contains('fab-away')")
                check('＋ 단추: 내리면 숨고 올리면 다시', away and back, f'{away} {back}')
            if w == 360:
                pg.evaluate("document.querySelector('.content').scrollTop = 0")
                pg.screenshot(path=os.path.join(OUT, f'{w}-{th}-ledger.png'))
            # 5) 입력 창: 지출 탭 글자 대비, 입력칸 테두리
            pg.evaluate("Entry.open({})")
            pg.wait_for_timeout(300)
            on = pg.locator('.overlay .toggle2 button.on').first
            c = pg.evaluate(CONTRAST, [on.evaluate("e => getComputedStyle(e).color"), on.evaluate("e => getComputedStyle(e).backgroundColor")])
            check('입력 창 [지출] 탭 글자 대비 4.5:1 이상', c >= 4.5, f'{c:.2f}')
            inp = pg.locator('.overlay .form input[data-k=memo], .overlay .form [data-k=memo]').first
            bc = inp.evaluate("e => getComputedStyle(e).borderTopColor")
            c = pg.evaluate(CONTRAST, [bc, bg_of(pg, '.overlay .form [data-k=memo]')])
            check('입력칸 테두리가 바탕과 구분 (1.9:1 이상)', c >= 1.9, f'{bc} {c:.2f}')
            if w == 412:
                pg.screenshot(path=os.path.join(OUT, f'{w}-{th}-entry.png'))
            pg.evaluate('while (UI.closeTop()) {}')
            # 6) 달력: 공휴일 이름은 이름표, 칸 안 금액 글자 크기
            pg.evaluate("App.go('calendar')")
            pg.wait_for_timeout(300)
            if pg.locator('.cal .an.h').count():
                check('달력 공휴일 이름은 바탕 있는 이름표 (지출 금액과 구분)',
                      pg.locator('.cal .an.h').first.evaluate("e => getComputedStyle(e).backgroundColor") != 'rgba(0, 0, 0, 0)')
            if pg.locator('.cal .mo').count():
                fs = pg.locator('.cal .mo').first.evaluate("e => parseFloat(getComputedStyle(e).fontSize)")
                check('달력 칸 안 금액 9.5px 이상', fs >= 9.5, str(fs))
            if w == 412:
                pg.screenshot(path=os.path.join(OUT, f'{w}-{th}-calendar.png'))
            # 7) 그래프: 첫 줄(수입)은 파랑, 마지막 달 이름이 그림 안
            pg.evaluate("App.go('graph', {}, true)")
            pg.wait_for_timeout(300)
            first = pg.evaluate("(() => { const i = document.querySelector('.legend i'); return i ? getComputedStyle(i).backgroundColor : ''; })()")
            if first:
                r, g, b = [int(x) for x in re.findall(r'\d+', first)[:3]]
                check('그래프 첫 줄(수입)은 파랑', b > r and b > g, first)
            inside = pg.evaluate("""(() => { const s = document.querySelector('svg.chart'); if (!s) return true;
              const t = Array.from(s.querySelectorAll('text')).filter(x => x.textContent === '12월')[0]; if (!t) return true;
              return t.getBoundingClientRect().right <= s.getBoundingClientRect().right + 0.5; })()""")
            check('그래프 12월 글자가 그림 안', inside)
            ctx.close()
    br.close()

print()
if errs:
    print('콘솔 오류:', *errs[:10], sep='\n  ')
print('실패:', fails if fails else '없음')
raise SystemExit(1 if fails or errs else 0)
