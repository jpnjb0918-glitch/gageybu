"""1.7.0 점검 (브라우저 + 가짜 NativeBridge): 설정 → 카테고리에서 세부 카테고리 지우기
(안 쓴 것 / 옮기고 삭제 / 내역까지 삭제) · 카테고리 지우기, 그리고 바뀐 이름(카테고리·통계·고정 수입·지출·내용 …).
테마마다 카테고리 화면을 찍는다.
  python3 category_delete.py      → shots/catdel/<테마>-<화면>.png"""
import functools
import http.server
import os
import socketserver
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'devtools', 'shots', 'catdel')
os.makedirs(OUT, exist_ok=True)

SEED = r"""
() => {
  const lid = App.lid, t = U.today(), [y, m] = U.parts(t);
  L.setGroup(lid, 'x', '시험');
  L.setCategory(lid, 'x1', '안씀'); L.setCategory(lid, 'x2', '옮길것'); L.setCategory(lid, 'x3', '다지울것');
  for (const [item, code] of [['가', 'x2'], ['나', 'x2'], ['다', 'x3']])
    L.addEntry(lid, { date: t, item, income: 0, expense: 1000, code, memo: '' });
  R.saveRule(lid, { item: '고정', income: 0, expense: 500, code: 'x2', day: 1, start: t, end: '', memo: '' });
  Rep.setBudgets(lid, [U.ym(y, m)], { x2: 10000 });
  L.saveFavorite(lid, { item: '즐겨', expense: 1000, code: 'x2' });
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


def page(br, th):
    ctx = br.new_context(viewport={'width': 412, 'height': 860}, device_scale_factor=2, is_mobile=True, has_touch=True)
    ctx.add_init_script(path=os.path.join(ROOT, 'devtools', 'fake-native.js'))
    ctx.add_init_script(f"window.__fake && Object.assign(window.__fake.prefs, {{ theme: '{th}' }});")
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: errs.append(f'{th}: {e}'))
    pg.on('console', lambda m: errs.append(f'{th}: {m.text}') if m.type == 'error' else None)
    pg.goto(URL)
    pg.wait_for_selector('.navbar', timeout=20000)
    pg.wait_for_timeout(300)
    pg.evaluate("() => { while (UI.closeTop()) {} }")
    return ctx, pg


def cats(pg):
    return pg.evaluate("L.categories(App.lid, 'x').map(c => c.code)")


def open_cat(pg, code):
    pg.locator(f'li[data-c="{code}"]').click()
    pg.wait_for_timeout(150)


def sheet_btn(pg, label):
    pg.locator('.overlay').last.locator('.sf .btn', has_text=label).click()
    pg.wait_for_timeout(150)


def dialog_btn(pg, label):
    pg.locator('.dialog .btn', has_text=label).click()
    pg.wait_for_timeout(150)


with sync_playwright() as p:
    br = p.chromium.launch()
    print('동작')
    ctx, pg = page(br, 'basic')
    pg.evaluate(SEED)
    # 바뀐 이름: 아래 탭·더보기·설정
    tabs = pg.locator('.navbar').inner_text()
    check("아래 탭에 '통계' (예전 '결산' 없음)", '통계' in tabs and '결산' not in tabs, tabs.replace('\n', ' '))
    pg.evaluate("App.go('more')")
    pg.wait_for_timeout(150)
    more = pg.locator('.content').inner_text()
    check("더보기에 '고정 수입·지출' (예전 '예약 입력' 없음)", '고정 수입·지출' in more and '예약' not in more, more.replace('\n', ' ')[:200])
    pg.evaluate("App.go('settings')")
    pg.wait_for_timeout(150)
    st = pg.locator('.content').inner_text()
    for want in ('가계부 관리', '카테고리', '자주 쓴 내용', '월 시작일'):
        check(f"설정에 '{want}'", want in st)
    for old in ('계정과목', '장부 관리', '품목', '결산일'):
        check(f"설정에 예전 이름 '{old}' 없음", old not in st)
    # 카테고리 화면: 세부 카테고리 줄에도 '편집 ›'
    pg.evaluate("App.go('codes', {}, true)")
    pg.wait_for_timeout(200)
    check("화면 이름 '카테고리'", pg.locator('.banner .t').inner_text() == '카테고리')
    check("세부 카테고리 줄에도 '편집 ›'", pg.locator('li[data-c] .muted', has_text='편집 ›').count() == pg.locator('li[data-c]').count() > 0)
    check("'＋ 세부 카테고리 추가' 줄", pg.locator('li[data-add]', has_text='세부 카테고리 추가').count() >= 1)
    pg.locator('li[data-c="x1"]').scroll_into_view_if_needed()
    pg.screenshot(path=os.path.join(OUT, 'basic-카테고리.png'))

    # ① 안 쓴 것: 한 번 묻고 지움
    open_cat(pg, 'x1')
    check('세부 카테고리 창 제목', pg.locator('.overlay').last.locator('.sh .t').inner_text() == '세부 카테고리 x1')
    sheet_btn(pg, '삭제')
    msg = pg.locator('.dialog .msg').inner_text()
    check('안 쓴 것: 바로 삭제할지 물음', '안씀' in msg and pg.locator('.overlay').last.locator('[name=dm]').count() == 0, msg)
    dialog_btn(pg, '삭제')
    check('안 쓴 세부 카테고리 지워짐', 'x1' not in cats(pg) and pg.locator('.overlay').count() == 0, str(cats(pg)))

    # ② 쓴 것 → 옮기고 삭제
    open_cat(pg, 'x2')
    check('창에 쓴 곳 (내역 2 · 고정 1 · 예산 1)', '내역 2건 · 고정 수입·지출 1건 · 예산 1건' in pg.locator('.overlay').last.inner_text())
    sheet_btn(pg, '삭제')
    ov = pg.locator('.overlay').last
    check('쓴 것: 옮기고 삭제 / 모두 삭제 고르기 창', ov.locator('.sh .t').inner_text() == '세부 카테고리 삭제'
          and ov.locator('input[name=dm]').count() == 2)
    opts = ov.locator('select[data-to] option').evaluate_all('os => os.map(o => o.value)')
    check('옮길 곳: 지출 쪽 먼저, 수입(0x)은 뒤, 자기 자신 없음', bool(opts) and not opts[0].startswith('0') and 'x2' not in opts
          and opts[-1].startswith('0'), str(opts[:3] + opts[-2:]))
    pg.screenshot(path=os.path.join(OUT, 'basic-삭제창.png'))
    ov.locator('select[data-to]').select_option('31')
    sheet_btn(pg, '삭제')
    moved = pg.evaluate("DB.q(\"SELECT code FROM entry WHERE item IN ('가','나')\").map(r => r.code)")
    check('옮기고 삭제: x2 없어지고 내역 2건은 31로', 'x2' not in cats(pg) and moved == ['31', '31'], f'{cats(pg)} {moved}')
    check('고정 수입·지출·자주 쓰는 내역도 31로', pg.evaluate("DB.val(\"SELECT code FROM recurring WHERE item='고정'\")") == '31'
          and pg.evaluate("L.favorites(App.lid).find(f => f.item === '즐겨').code") == '31')
    check('창이 모두 닫힘', pg.locator('.overlay').count() == 0)

    # ③ 쓴 것 → 내역까지 삭제 (다시 묻고, 취소하면 그대로)
    open_cat(pg, 'x3')
    sheet_btn(pg, '삭제')
    ov = pg.locator('.overlay').last
    ov.locator('input[name=dm][value=all]').check()
    check('모두 삭제를 고르면 옮길 곳 목록이 꺼짐', ov.locator('select[data-to]').is_disabled())
    sheet_btn(pg, '삭제')
    msg = pg.locator('.dialog .msg').inner_text()
    check('모두 삭제: 한 번 더 확인', '되돌릴 수 없습니다' in msg, msg)
    dialog_btn(pg, '취소')
    check('확인에서 취소하면 그대로 (창도 남음)', 'x3' in cats(pg) and pg.locator('.overlay').count() == 2)
    sheet_btn(pg, '삭제')
    dialog_btn(pg, '모두 삭제')
    left = pg.evaluate("DB.val(\"SELECT COUNT(*) FROM entry WHERE item='다'\")")
    check('세부 카테고리와 내역 모두 지움, 창 닫힘', 'x3' not in cats(pg) and left == 0 and pg.locator('.overlay').count() == 0,
          f'{cats(pg)} {left}')

    # ④ 카테고리 지우기: 쓴 세부 카테고리가 있으면 멈춤, 안 쓴 것뿐이면 함께 지움
    pg.evaluate("() => { L.setCategory(App.lid, 'x4', '쓰는중'); L.setCategory(App.lid, 'x5', '빈칸');"
                " L.addEntry(App.lid, { date: U.today(), item: '라', income: 0, expense: 1000, code: 'x4', memo: '' }); App.dataChanged(); }")
    pg.wait_for_timeout(150)
    pg.locator('[data-g="x"]').click()
    pg.wait_for_timeout(150)
    sheet_btn(pg, '삭제')
    msg = pg.locator('.dialog .msg').inner_text()
    check('카테고리 삭제 물음에 안의 세부 카테고리 수', '세부 카테고리 2개' in msg, msg)
    dialog_btn(pg, '삭제')
    msg = pg.locator('.dialog .msg').inner_text()
    check('쓴 세부 카테고리가 있으면 이름을 알려 주고 멈춤', '쓰는중' in msg and pg.evaluate("'x' in L.groupMap(App.lid)"), msg)
    dialog_btn(pg, '확인')
    pg.evaluate("() => { while (UI.closeTop()) {} L.mergeCategory(App.lid, 'x4', '31'); App.dataChanged(); }")
    pg.wait_for_timeout(150)
    pg.locator('[data-g="x"]').click()
    pg.wait_for_timeout(150)
    sheet_btn(pg, '삭제')
    dialog_btn(pg, '삭제')
    check('안 쓴 세부 카테고리뿐이면 카테고리와 함께 지움', not pg.evaluate("'x' in L.groupMap(App.lid)") and cats(pg) == [])

    # ⑤ 가계부 새 내역 창·통계 탭 이름
    pg.evaluate("Entry.open({ date: U.today() })")
    pg.wait_for_timeout(200)
    labels = pg.locator('.overlay').last.locator('label.l').all_inner_texts()
    check('새 내역 창: 내용 · 카테고리', '내용' in labels and '카테고리' in labels and '품목' not in labels, str(labels))
    pg.evaluate("() => { while (UI.closeTop()) {} App.go('report'); }")
    pg.wait_for_timeout(200)
    seg = pg.locator('.seg').first.inner_text().replace('\n', ' ')
    check('통계 탭: 월별 · 연간 · 일별 · 기간 · 예산', all(k in seg for k in ('월별', '연간', '일별', '기간', '예산')), seg)
    ctx.close()

    # 테마마다 카테고리 화면
    for th in THEMES:
        ctx, pg = page(br, th)
        pg.evaluate("App.go('codes', {}, true)")
        pg.wait_for_timeout(250)
        pg.screenshot(path=os.path.join(OUT, f'{th}-카테고리.png'))
        pg.locator('li[data-c="31"]').click()
        pg.wait_for_timeout(200)
        pg.screenshot(path=os.path.join(OUT, f'{th}-세부편집.png'))
        ctx.close()
    br.close()
srv.shutdown()
for e in errs:
    print('  (오류 기록)', e)
    fails.append('콘솔 오류')
print('실패:', ', '.join(fails) if fails else '없음')
raise SystemExit(1 if fails else 0)
