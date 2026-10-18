"""브라우저(크로미움)에서 앱 화면을 띄워 오류 없이 그려지는지 확인하고 화면을 찍는다."""
import http.server, threading, socketserver, os, sys, json, functools
from playwright.sync_api import sync_playwright
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'devtools', 'shots')
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=ROOT))
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{port}/app/assets/www/index.html'
errors = []
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 392, 'height': 820}, device_scale_factor=2, is_mobile=True, has_touch=True, locale='ko-KR')
    ctx.add_init_script(path=os.path.join(ROOT, 'devtools', 'fake-native.js'))
    pg = ctx.new_page()
    pg.on('console', lambda m: errors.append(f'console.{m.type}: {m.text}') if m.type in ('error', 'warning') else None)
    pg.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))
    pg.goto(URL)
    pg.wait_for_selector('.navbar', timeout=15000)
    pg.wait_for_timeout(800)
    pg.screenshot(path=f'{OUT}/01-ledger-empty.png')
    for tab in ['calendar', 'report', 'assets', 'more']:
        pg.click(f'.navbar button[data-tab={tab}]')
        pg.wait_for_timeout(300)
        pg.screenshot(path=f'{OUT}/02-{tab}.png')
    for page in ['search', 'graph', 'recurring', 'anniv', 'contacts', 'diary', 'memo', 'settings', 'help', 'codes']:
        pg.evaluate(f"App.go('{page}', {{}}, true)")
        pg.wait_for_timeout(250)
        pg.screenshot(path=f'{OUT}/03-{page}.png')
    b.close()
print('\n'.join(errors) or 'NO ERRORS')
