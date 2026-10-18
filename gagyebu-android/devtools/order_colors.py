"""순서 바꾸기·색 바꾸기 시험 (브라우저 + 가짜 NativeBridge). 화면을 끌고 눌러서 확인하고 사진을 찍는다.

  python3 order_colors.py      → shots/order/*.png
"""
import functools
import http.server
import json
import os
import socketserver
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'devtools', 'shots', 'order')
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


OVERFLOW = """() => { const vw = document.documentElement.clientWidth; const bad = [];
  if (document.documentElement.scrollWidth > vw + 1) bad.push('page');
  for (const el of document.querySelectorAll('.content, .sheet .sb, .topbar')) if (el.scrollWidth > el.clientWidth + 1) bad.push(el.className);
  return bad; }"""


def drag(pg, src, dst_y_of):
    """src(☰ 손잡이)를 잡고 dst_y_of 위치까지 끌기 (마우스 = 포인터 이벤트)"""
    b = src.bounding_box()
    pg.mouse.move(b['x'] + b['width'] / 2, b['y'] + b['height'] / 2)
    pg.mouse.down()
    y0 = b['y'] + b['height'] / 2
    for k in range(1, 9):
        pg.mouse.move(b['x'] + b['width'] / 2, y0 + (dst_y_of - y0) * k / 8)
        pg.wait_for_timeout(20)
    pg.mouse.up()
    pg.wait_for_timeout(150)


def sheet_btn(pg, label):
    pg.locator('.overlay').last.locator('.sf').get_by_role('button', name=label, exact=True).click()
    pg.wait_for_timeout(250)


def keys_in_sheet(pg):
    return pg.evaluate("Array.from(document.querySelectorAll('.overlay:last-child .reorder li')).map(li => li.dataset.key)")


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 360, 'height': 780}, device_scale_factor=2, is_mobile=True, has_touch=True)
    ctx.add_init_script(path=os.path.join(ROOT, 'devtools', 'fake-native.js'))
    ctx.add_init_script("window.__fake && (window.__fake.prefs.theme = 'feed');")
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    pg.goto(URL)
    pg.wait_for_selector('.navbar', timeout=20000)
    pg.wait_for_timeout(400)
    pg.evaluate("() => document.querySelectorAll('.overlay').forEach(o => o.remove())")
    pg.evaluate("""() => {
      const lid = App.lid, t = U.today();
      L.addEntry(lid, { date: t, item: '아침 빵', expense: 3000, code: '31' });
      L.addEntry(lid, { date: t, item: '점심', expense: 9000, code: '31' });
      L.addEntry(lid, { date: t, item: '용돈', income: 50000, code: '01' });
      ['홍길동', '김철수', '박영희'].forEach(n => Cal.simpleSave('contact', { name: n }));
      Cal.simpleSave('diary', { date: t, title: '첫 일기', content: '' });
      Cal.simpleSave('diary', { date: t, title: '둘째 일기', content: '' });
      ['장보기', '할 일', '책'].forEach((x, i) => Cal.simpleSave('memo', { title: x, content: '', sort: i + 1 }));
      App.go('ledger');
    }""")
    pg.wait_for_timeout(300)

    print('[같은 날 내역 순서]')
    day_ids = lambda: pg.evaluate("Array.from(document.querySelectorAll('.post')[0].querySelectorAll('li[data-id]')).map(li => Number(li.dataset.id))")
    before = day_ids()
    pg.locator('.dayord').first.click()
    pg.wait_for_timeout(300)
    pg.screenshot(path=os.path.join(OUT, '01-day-order-sheet.png'))
    check('순서 창이 넘치지 않음', not pg.evaluate(OVERFLOW), str(pg.evaluate(OVERFLOW)))
    grips = pg.locator('.overlay .reorder .grip')
    k0 = keys_in_sheet(pg)
    first_box = pg.locator('.overlay .reorder li').first.bounding_box()
    drag(pg, grips.nth(2), first_box['y'] + 4)            # 셋째를 맨 위로 끌기
    k = keys_in_sheet(pg)
    check('끌어서 옮겨짐 (셋째 → 맨 위)', k == [k0[2], k0[0], k0[1]], f'{k0} → {k}')
    sheet_btn(pg, '저장')
    after = day_ids()
    saved = pg.evaluate("Ord.dayOrders(App.lid)[U.today()]")
    check('자료 파일에 그 날 순서 저장', saved == [int(x) for x in k], f'{saved} vs {k}')
    # 화면은 '최근 것을 위로'(기본 켜짐)에서도 정한 순서 그대로
    check('화면 목록이 정한 순서', after == [int(x) for x in k], f'{after} vs {k}')
    bal = pg.evaluate("L.entriesWithBalance(App.lid, U.today(), U.today()).map(([r, b]) => [r.id, b])")
    check('잔액도 그 순서로 계산', [x[0] for x in bal] == [int(x) for x in k], str(bal))
    # ▲ 단추로도
    pg.locator('.dayord').first.click()
    pg.wait_for_timeout(250)
    pg.locator('.overlay .reorder li').nth(1).locator('[data-mv="-1"]').click()
    k2 = keys_in_sheet(pg)
    check('▲ 단추로 한 칸 위로', k2[0] == k[1] and k2[1] == k[0], str(k2))
    sheet_btn(pg, '기본 순서로')
    check('기본 순서로 되돌리면 저장값 지워짐', pg.evaluate("!(U.today() in Ord.dayOrders(App.lid))"))

    print('[메뉴 순서]')
    pg.evaluate("App.go('settings', {section:'deco'}, true)")
    pg.wait_for_timeout(300)
    pg.locator('[data-ord="nav"]').click()
    pg.wait_for_timeout(250)
    items = pg.locator('.overlay .reorder li')
    n = items.count()
    set_idx = keys_in_sheet(pg).index('settings')
    for _ in range(set_idx):                                # 설정을 ▲로 맨 위까지
        pg.locator('.overlay .reorder li[data-key="settings"] [data-mv="-1"]').click()
    pg.screenshot(path=os.path.join(OUT, '02-nav-order-sheet.png'))
    sheet_btn(pg, '저장')
    tabs = pg.evaluate("Array.from(document.querySelectorAll('.navbar button')).map(b => b.dataset.tab)")
    check('아래 탭 첫째가 설정', tabs[0] == 'settings' and tabs[-1] == 'more' and len(tabs) == 5, str(tabs))
    pg.evaluate("App.go('more')")
    pg.wait_for_timeout(200)
    tiles = pg.evaluate("Array.from(document.querySelectorAll('.tile')).map(b => b.dataset.p)")
    check('밀려난 화면(자산)이 더보기 맨 앞', tiles[0] == 'assets' and 'settings' not in tiles, str(tiles))
    pg.screenshot(path=os.path.join(OUT, '03-more-after-nav-order.png'))
    pg.evaluate("App.setPref('nav_order', null); App.drawNav()")

    print('[가계부 화면 구성]')
    pg.evaluate("App.go('ledger')")
    pg.wait_for_timeout(200)
    pg.locator('.banner .tools .iconbtn[title="화면 구성 순서"]').click()
    pg.wait_for_timeout(250)
    li_list = pg.locator('.overlay .reorder li[data-key="list"]')
    drag(pg, li_list.locator('.grip'), pg.locator('.overlay .reorder li').first.bounding_box()['y'] + 4)
    sheet_btn(pg, '저장')
    first = pg.evaluate("document.querySelector('.content').firstElementChild.className")
    check('내역 목록이 맨 위로', 'ledger-wrap' in first, first)
    pg.screenshot(path=os.path.join(OUT, '04-layout-list-first.png'))
    pg.evaluate("App.setPref('ledger_layout', null); App.render()")

    print('[계정과목 순서]')
    pg.evaluate("App.go('codes', {}, true)")
    pg.wait_for_timeout(250)
    pg.locator('[data-gord]').click()
    pg.wait_for_timeout(200)
    drag(pg, pg.locator('.overlay .reorder li[data-key="3"] .grip'), pg.locator('.overlay .reorder li').first.bounding_box()['y'] + 4)
    sheet_btn(pg, '저장')
    g = pg.evaluate("L.groups(App.lid).map(x => x.code)")
    check('대분류 3(식비)이 맨 앞', g[0] == '3', str(g))
    opt = pg.evaluate("UI.el('<select>' + UI.codeOptions(App.lid, '', 'out') + '</select>').querySelector('optgroup').label")
    check('입력할 때 고르는 목록도 그 순서', opt.startswith('(3)'), opt)
    pg.locator('[data-cord="3"]').click()
    pg.wait_for_timeout(200)
    k = keys_in_sheet(pg)
    drag(pg, pg.locator('.overlay .reorder .grip').last, pg.locator('.overlay .reorder li').first.bounding_box()['y'] + 4)
    k2 = keys_in_sheet(pg)
    sheet_btn(pg, '저장')
    cats = pg.evaluate("L.categories(App.lid, '3').map(x => x.code)")
    check('소분류 순서 저장 (sort 칸)', cats == k2 and k2[0] == k[-1], f'{cats} / {k2}')
    rep = pg.evaluate("Rep.monthly(App.lid, ...U.parts(U.today()).slice(0, 2), 1).rows.filter(r => r.kind === 'subtotal').map(r => r.group)")
    check('결산 보고서도 대분류 순서대로', bool(rep) and rep[0] == pg.evaluate("L.groups(App.lid)[0].name"), str(rep[:3]))
    pg.screenshot(path=os.path.join(OUT, '05-codes.png'))

    print('[주소록·일기·메모 순서]')
    pg.evaluate("App.go('contacts', {}, true)")
    pg.wait_for_timeout(250)
    names = lambda: pg.evaluate("Array.from(document.querySelectorAll('.content li[data-id] .main-t')).map(x => x.textContent.trim())")
    n0 = names()
    pg.locator('.banner .tools .btn', has_text='순서').click()
    pg.wait_for_timeout(200)
    pg.locator('.overlay .reorder li').last.locator('[data-mv="-1"]').click()
    pg.locator('.overlay .reorder li').nth(1).locator('[data-mv="-1"]').click()
    sheet_btn(pg, '저장')
    n1 = names()
    check('주소록 순서 바뀜', n1 == [n0[2], n0[0], n0[1]], f'{n0} → {n1}')
    pg.evaluate("App.go('diary', {}, true)")
    pg.wait_for_timeout(250)
    d0 = names()
    pg.locator('.banner .tools .btn', has_text='순서').click()
    pg.wait_for_timeout(200)
    pg.locator('.overlay .reorder li').last.locator('[data-mv="-1"]').click()
    sheet_btn(pg, '저장')
    check('일기 순서 바뀜', names() == d0[::-1], f'{d0} → {names()}')
    pg.evaluate("App.go('memo', {}, true)")
    pg.wait_for_timeout(250)
    m0 = names()
    pg.locator('.banner .tools .btn', has_text='순서').click()
    pg.wait_for_timeout(200)
    drag(pg, pg.locator('.overlay .reorder .grip').last, pg.locator('.overlay .reorder li').first.bounding_box()['y'] + 4)
    sheet_btn(pg, '저장')
    check('메모 순서 바뀜 (sort 칸)', names() == [m0[2], m0[0], m0[1]], f'{m0} → {names()}')

    print('[색 바꾸기]')
    pg.evaluate("App.go('settings', {section:'deco'}, true)")
    pg.wait_for_timeout(300)
    pg.locator('[data-ck="accent"]').click()
    pg.wait_for_timeout(250)
    pg.screenshot(path=os.path.join(OUT, '06-color-picker.png'))
    check('색 고르기 창이 넘치지 않음', not pg.evaluate(OVERFLOW), str(pg.evaluate(OVERFLOW)))
    pg.locator('.overlay [data-x]').last.fill('#00AA55')
    sheet_btn(pg, '이 색으로')
    v = pg.evaluate("document.body.style.getPropertyValue('--accent')")
    check('포인트 색 적용', v.strip().upper() == '#00AA55', v)
    bg = pg.evaluate("getComputedStyle(document.querySelector('.btn.pri')).backgroundColor")
    check('강조 단추 색이 바뀜', bg == 'rgb(0, 170, 85)', bg)
    check('설정에 저장 (이 테마만)', json.loads(pg.evaluate("App.pref('colors_feed')"))['accent'] == '#00AA55')
    pg.locator('[data-ck="bg"]').click()
    pg.wait_for_timeout(200)
    pg.locator('.overlay .cp-sw button[data-c="#FFF7EC"]').click()
    sheet_btn(pg, '이 색으로')
    pg.locator('[data-ck="out"]').click()
    pg.wait_for_timeout(200)
    pg.evaluate("""() => { const h = document.querySelector('.overlay:last-child [data-h]'); h.value = 270; h.dispatchEvent(new Event('input')); }""")
    hx = pg.evaluate("document.querySelector('.overlay:last-child .cp-hex').textContent")
    sheet_btn(pg, '이 색으로')
    check('막대로 고른 색이 지출 색으로', pg.evaluate("document.body.style.getPropertyValue('--out')").strip().upper() == hx.upper(), hx)
    pg.evaluate("App.go('ledger')")
    pg.wait_for_timeout(300)
    pg.screenshot(path=os.path.join(OUT, '07-feed-custom-colors.png'))
    check('바꾼 색에서도 넘침 없음', not pg.evaluate(OVERFLOW))
    # 다른 테마로 바꾸면 그 테마 원래 색, 다시 돌아오면 고른 색
    pg.evaluate("App.setPref('theme', 'timeline_dark'); App.applyTheme(); App.render()")
    check('다른 테마는 원래 색', pg.evaluate("document.body.style.getPropertyValue('--accent')") == '')
    pg.evaluate("App.setCustomColor('bg', '#101830'); App.setCustomColor('accent', '#FFB000'); App.render()")
    pg.wait_for_timeout(200)
    pg.screenshot(path=os.path.join(OUT, '08-dark-custom-colors.png'))
    pg.evaluate("App.setPref('theme', 'retro'); App.setCustomColor('bg', '#F3E6FF'); App.render()")
    pg.wait_for_timeout(200)
    fg = pg.evaluate("getComputedStyle(document.querySelector('.topbar')).color")
    check('미니홈피 바탕을 밝게 하면 맨 위 글자가 진하게', fg == 'rgb(26, 26, 26)', fg)
    pg.screenshot(path=os.path.join(OUT, '09-retro-custom-bg.png'))
    pg.evaluate("App.setPref('theme', 'feed'); App.applyTheme(); App.go('settings', {section:'deco'}, true)")
    pg.wait_for_timeout(300)
    pg.locator('[data-creset]').click()
    pg.wait_for_timeout(200)
    check('이 테마 색 모두 처음으로', pg.evaluate("document.body.style.getPropertyValue('--accent')") == '' and pg.evaluate("App.pref('colors_feed')") in (None, ''))
    check('상태 표시줄 색도 바뀜', pg.evaluate("window.__fake.bars") is not None, str(pg.evaluate("window.__fake.bars")))
    br.close()

print('페이지 오류:', errs or '없음')
print('결과:', '통과' if not fails and not errs else f'실패 {fails}')
