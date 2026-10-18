"""PC판 ↔ 안드로이드판 자료 호환 시험.
1) 안드로이드판 코드(브라우저+sql.js)로 표본 자료를 만들고, 같은 파일을 PC판 코드와 안드로이드판 코드로 각각 계산해 비교
2) PC판 코드로 표본 자료를 만들고, 같은 방식으로 비교
"""
import functools
import http.server
import json
import os
import socketserver
import subprocess
import sys
import threading

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT = os.path.join(HERE, 'out')
os.makedirs(OUT, exist_ok=True)


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


srv = socketserver.TCPServer(('127.0.0.1', 0), functools.partial(Q, directory=ROOT))
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f'http://127.0.0.1:{srv.server_address[1]}/app/assets/www/index.html'


def py(*args):
    subprocess.run([sys.executable, os.path.join(HERE, 'py_side.py'), *args], check=True)


def open_app(browser, db_bytes=None):
    ctx = browser.new_context(viewport={'width': 392, 'height': 820})
    if db_bytes is not None:
        ctx.add_init_script(f'window.__initialDbBytes = new Uint8Array({json.dumps(list(db_bytes))});')
    ctx.add_init_script(path=os.path.join(ROOT, 'devtools', 'fake-native.js'))
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(URL)
    pg.wait_for_function('window.App && (document.querySelector(".navbar") || document.querySelector(".login"))', timeout=20000)
    pg.add_script_tag(path=os.path.join(HERE, 'js_side.js'))
    return pg, errs


def diff(a, b, path=''):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                return f'{path}.{k}: 한쪽에만 있음 ({"PC" if k in a else "안드로이드"})'
            d = diff(a[k], b[k], f'{path}.{k}')
            if d:
                return d
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return f'{path}: 길이 {len(a)} != {len(b)}'
        for i, (x, y) in enumerate(zip(a, b)):
            d = diff(x, y, f'{path}[{i}]')
            if d:
                return d
        return None
    if isinstance(a, bool) or isinstance(b, bool):
        return None if a == b else f'{path}: {a!r} != {b!r}'
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return None if a == b else f'{path}: {a!r} != {b!r}'
    return None if a == b else f'{path}: {a!r} != {b!r}'


def compare(name, pyj, jsj):
    a = json.load(open(pyj, encoding='utf-8'))
    b = json.load(open(jsj, encoding='utf-8'))
    bad = []
    for r in (a, b):                                   # 화면 안내 문구만 다름 (PC: 두 번 눌러 / 폰: 눌러)
        for k in r:
            if k.endswith('.budget') and isinstance(r[k], dict):
                r[k].pop('note', None)
    for k in sorted(set(a) | set(b)):
        d = diff(a.get(k), b.get(k), k)
        if d:
            bad.append(d)
    print(f'[{name}] 항목 {len(a)}개 비교 — ' + ('모두 같음' if not bad else f'다름 {len(bad)}개'))
    for d in bad[:40]:
        print('   ', d[:300])
    return not bad


ok = True
with sync_playwright() as p:
    br = p.chromium.launch()
    # 1) 안드로이드판으로 만든 자료
    pg, errs = open_app(br)
    pg.evaluate('__compat.build()')
    js_db = bytes(pg.evaluate('window.__getDbBytes()'))
    open(os.path.join(OUT, 'js.sqlite3'), 'wb').write(js_db)
    json.dump(pg.evaluate('__compat.dump()'), open(os.path.join(OUT, 'js_on_js.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    if errs:
        print('페이지 오류:', errs)
        ok = False
    py('dump', os.path.join(OUT, 'js.sqlite3'), os.path.join(OUT, 'py_on_js.json'))
    ok &= compare('안드로이드판이 만든 자료', os.path.join(OUT, 'py_on_js.json'), os.path.join(OUT, 'js_on_js.json'))
    # 2) PC판으로 만든 자료
    py('build', os.path.join(OUT, 'py.sqlite3'))
    py('dump', os.path.join(OUT, 'py.sqlite3'), os.path.join(OUT, 'py_on_py.json'))
    pg2, errs2 = open_app(br, open(os.path.join(OUT, 'py.sqlite3'), 'rb').read())
    json.dump(pg2.evaluate('__compat.dump()'), open(os.path.join(OUT, 'js_on_py.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    print('PC판 자료를 열었을 때 화면:', '암호 입력 화면' if pg2.query_selector('.login') else '바로 열림')
    if errs2:
        print('페이지 오류:', errs2)
        ok = False
    ok &= compare('PC판이 만든 자료', os.path.join(OUT, 'py_on_py.json'), os.path.join(OUT, 'js_on_py.json'))
    br.close()
print('결과:', '통과' if ok else '실패')
sys.exit(0 if ok else 1)
