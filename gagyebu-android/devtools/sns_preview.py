"""피드·타임라인 테마 미리보기 사진 (가계부 위·아래, 더보기, 달력)  python3 sns_preview.py [테마…] → shots/sns/"""
import functools
import http.server
import os
import re
import socketserver
import sys
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'devtools', 'shots', 'sns')
os.makedirs(OUT, exist_ok=True)
SEED = re.search(r'SEED = r"""(.*?)"""', open(os.path.join(ROOT, 'devtools', 'themes.py'), encoding='utf-8').read(), re.S).group(1)
THEMES = sys.argv[1:] or ['feed', 'timeline', 'feed_light', 'timeline_light', 'feed_dark', 'timeline_dark']


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=ROOT))
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{srv.server_address[1]}/app/assets/www/index.html'
errs = []
with sync_playwright() as p:
    br = p.chromium.launch()
    for th in THEMES:
        ctx = br.new_context(viewport={'width': 412, 'height': 860}, device_scale_factor=2, is_mobile=True, has_touch=True)
        ctx.add_init_script(path=os.path.join(ROOT, 'devtools', 'fake-native.js'))
        ctx.add_init_script(f"window.__fake && Object.assign(window.__fake.prefs, {{theme: '{th}', motto: '이번 달은 커피 줄이기 ☕'}});")
        pg = ctx.new_page()
        pg.on('pageerror', lambda e, th=th: errs.append(f'{th}: {e}'))
        pg.on('console', lambda m, th=th: errs.append(f'{th}: {m.text}') if m.type == 'error' else None)
        pg.goto(URL)
        pg.wait_for_selector('.navbar', timeout=20000)
        pg.wait_for_timeout(400)
        pg.evaluate("() => document.querySelectorAll('.overlay').forEach(o => o.remove())")
        pg.evaluate(SEED)
        pg.wait_for_timeout(300)
        pg.screenshot(path=os.path.join(OUT, f'{th}-1-ledger.png'))
        pg.evaluate("document.querySelector('.content').scrollTop = 640")
        pg.wait_for_timeout(200)
        pg.screenshot(path=os.path.join(OUT, f'{th}-2-ledger-down.png'))
        for name, js in [('3-more', "App.go('more')"), ('4-calendar', "App.go('calendar')"), ('5-search', "App.go('search', {}, true)")]:
            pg.evaluate(js)
            pg.wait_for_timeout(250)
            pg.screenshot(path=os.path.join(OUT, f'{th}-{name}.png'))
        ctx.close()
    br.close()
print('\n'.join(errs) or 'NO ERRORS')
