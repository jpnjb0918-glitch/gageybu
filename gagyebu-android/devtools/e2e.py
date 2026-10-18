"""화면을 직접 눌러 보는 시험 (브라우저 + 가짜 NativeBridge). 결과는 자료(DB)로 확인하고 화면도 찍어 둔다."""
import functools
import http.server
import json
import os
import socketserver
import sqlite3
import subprocess
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.path.join(ROOT, 'devtools', 'shots')
os.makedirs(SHOTS, exist_ok=True)


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


def new_page(browser, db_bytes=None):
    ctx = browser.new_context(viewport={'width': 392, 'height': 820}, device_scale_factor=2, is_mobile=True, has_touch=True)
    if db_bytes is not None:
        ctx.add_init_script(f'window.__initialDbBytes = new Uint8Array({json.dumps(list(db_bytes))});')
    ctx.add_init_script(path=os.path.join(ROOT, 'devtools', 'fake-native.js'))
    if os.environ.get('E2E_THEME'):        # 테마별로 같은 시험 돌리기: E2E_THEME=feed python3 e2e.py
        ctx.add_init_script(f"window.__fake && (window.__fake.prefs.theme = {json.dumps(os.environ['E2E_THEME'])});")
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
    pg.goto(URL)
    pg.wait_for_function('document.querySelector(".navbar") || document.querySelector(".login")', timeout=20000)
    pg.wait_for_timeout(500)
    return pg


def q(pg, sql, args=None):
    return pg.evaluate('([s, a]) => DB.q(s, a)', [sql, args or []])


def shot(pg, name):
    pg.screenshot(path=os.path.join(SHOTS, name + '.png'))


def sheet_btn(pg, label):
    pg.locator('.overlay').last.locator('.sf').get_by_role('button', name=label, exact=True).click()
    pg.wait_for_timeout(250)


def fill_sheet(pg, key, value):
    pg.locator('.overlay').last.locator(f'[data-k="{key}"]').fill(value)


with sync_playwright() as p:
    br = p.chromium.launch()
    pg = new_page(br)
    today = pg.evaluate('U.today()')
    print('■ 가계부 입력')
    pg.click('.fab')
    pg.wait_for_selector('.sheet')
    fill_sheet(pg, 'expense', '12000')
    check('금액 칸 쉼표', pg.locator('.overlay [data-k=expense]').input_value() == '12,000')
    fill_sheet(pg, 'item', '점심')
    pg.locator('.overlay [data-k=code]').select_option('31')
    shot(pg, '10-entry-form')
    sheet_btn(pg, '저장 후 계속')
    pg.click('.overlay .toggle2 button[data-m=in]')
    fill_sheet(pg, 'income', '3,000,000')
    fill_sheet(pg, 'item', '급여')
    check('수입으로 바꾸면 수입 계정', pg.locator('.overlay [data-k=code]').input_value() == '00')
    sheet_btn(pg, '저장 후 계속')
    pg.click('.overlay .toggle2 button[data-m=out]')
    fill_sheet(pg, 'expense', '5000')
    pg.locator('.overlay [data-k=item]').fill('')
    pg.locator('.overlay [data-k=item]').type('점')
    pg.wait_for_timeout(150)
    chips = pg.locator('.overlay .suggest .chip').all_inner_texts()
    check('품목 자동완성에 "점심"', '점심' in chips, str(chips))
    pg.locator('.overlay .suggest .chip', has_text='점심').click()
    check('예전 품목이면 계정 자동 선택(31)', pg.locator('.overlay [data-k=code]').input_value() == '31')
    sheet_btn(pg, '저장')
    rows = q(pg, 'SELECT item, income, expense, code, date FROM entry ORDER BY id')
    check('내역 3건 저장', len(rows) == 3, str(rows))
    check('첫 내역 값', rows[0] == {'item': '점심', 'income': 0, 'expense': 12000, 'code': '31', 'date': today}, str(rows[0]))
    check('급여 내역', rows[1]['income'] == 3000000 and rows[1]['code'] == '00')
    words = q(pg, 'SELECT name, count FROM item_word ORDER BY name')
    check('품목 사용 횟수(점심 2회)', {'name': '점심', 'count': 2} in words, str(words))
    shot(pg, '11-ledger-list')
    print('■ 수정·삭제')
    pg.locator('li[data-id]').filter(has_text='급여').click()
    fill_sheet(pg, 'income', '3,100,000')
    sheet_btn(pg, '수정 저장')
    check('수정 저장', q(pg, "SELECT income FROM entry WHERE item='급여'")[0]['income'] == 3100000)
    pg.locator('li[data-id]').filter(has_text='급여').click()
    sheet_btn(pg, '삭제')
    pg.locator('.dialog button', has_text='삭제').click()
    pg.wait_for_timeout(200)
    check('삭제', not q(pg, "SELECT 1 AS x FROM entry WHERE item='급여'"))
    check('뒤로 버튼: 열린 창 없으면 가계부 탭에서 false', pg.evaluate('App.onBack()') is False)

    print('■ 예약 입력')
    pg.evaluate("App.go('recurring', {}, true)")
    pg.click('.fab')
    fill_sheet(pg, 'item', '월세')
    fill_sheet(pg, 'expense', '500000')
    pg.locator('.overlay [data-k=code]').select_option('10')
    fill_sheet(pg, 'day', '1')
    fill_sheet(pg, 'start', '2026-09-01')
    sheet_btn(pg, '저장')
    check('예약 저장', len(q(pg, 'SELECT * FROM recurring')) == 1)
    pg.click('button[data-now]')
    pg.wait_for_selector('.sheet')
    boxes = pg.locator('.overlay input[data-i]')
    states = [boxes.nth(i).is_checked() for i in range(boxes.count())]
    shot(pg, '12-recurring-pending')
    check('지난달 것은 체크 해제, 이달 것은 체크 (PC판과 같음)', states == [False, True], str(states))
    sheet_btn(pg, '체크한 것 입력')
    ent = q(pg, "SELECT date, expense, origin FROM entry WHERE item='월세'")
    check('예약 입력 → 장부에 1건', len(ent) == 1 and ent[0]['date'].endswith('-01') and ent[0]['origin'].startswith('recurring:'), str(ent))
    check('뒤로 버튼: 하위 화면 닫기', pg.evaluate('App.onBack()') is True and pg.evaluate('App.st.page') == 'ledger')

    print('■ 달력·일정')
    pg.click('.navbar button[data-tab=calendar]')
    pg.click(f'td[data-d="{today}"]')
    pg.wait_for_selector('.sheet')
    shot(pg, '13-calendar-day')
    sheet_btn(pg, '＋ 일정')
    fill_sheet(pg, 'text', '수영')
    pg.locator('.overlay [data-k=rtype]').select_option('every')
    fill_sheet(pg, 'n', '1')
    pg.locator('.overlay [data-k=unit]').select_option('주')
    fill_sheet(pg, 'until', pg.evaluate('U.addDays(U.today(), 28)'))
    sheet_btn(pg, '저장')
    n = q(pg, "SELECT COUNT(*) AS n, COUNT(DISTINCT group_id) AS g FROM schedule WHERE text='수영'")[0]
    check('매주 반복 일정 5개 (한 묶음)', n == {'n': 5, 'g': 1}, str(n))
    shot(pg, '14-calendar-month')
    check('기념일(개천절) 표시', pg.locator('td[data-d="2026-10-03"] .an').count() == 1 if today.startswith('2026-10') else True)

    print('■ 결산·예산')
    pg.click('.navbar button[data-tab=report]')
    pg.wait_for_selector('table.rep')
    shot(pg, '15-report-monthly')
    row = pg.locator('table.rep tr').filter(has_text='31 외식')
    row.locator('td').nth(4).click()          # 0=이름, 1~5 = 값 → 4번째 값(이번달 예산)
    fill_sheet(pg, 'amount', '100000')
    sheet_btn(pg, '저장')
    b = q(pg, 'SELECT ym, code, amount FROM budget')
    check('예산 입력', b == [{'ym': today[:7], 'code': '31', 'amount': 100000}], str(b))
    pg.click('.seg button[data-k=yearly]')
    pg.wait_for_timeout(200)
    shot(pg, '16-report-yearly')

    print('■ 자산: 통장')
    pg.click('.navbar button[data-tab=assets]')
    pg.click('.fab')
    fill_sheet(pg, 'company', '국민')
    fill_sheet(pg, 'name', '월급통장')
    fill_sheet(pg, 'opening', '1000000')
    sheet_btn(pg, '저장')
    pg.locator('li[data-id]').first.click()
    pg.wait_for_timeout(200)
    pg.click('.fab')
    fill_sheet(pg, 'summary', '장보기')
    fill_sheet(pg, 'withdraw', '50000')
    pg.locator('.overlay [data-k=to_ledger]').check()
    pg.locator('.overlay [data-k=code]').select_option('30')
    sheet_btn(pg, '저장')
    bal = pg.evaluate("A.accountBalance(A.accounts('bank')[0].id)")
    check('통장 잔액 950,000', bal == 950000, str(bal))
    e = q(pg, "SELECT expense, code, origin FROM entry WHERE item='장보기'")
    check('장부에도 동시 저장', e and e[0]['expense'] == 50000 and e[0]['code'] == '30', str(e))
    shot(pg, '17-account')
    pg.evaluate('App.onBack()')

    print('■ 자산: 카드')
    pg.click('.seg button[data-k=card]')
    pg.click('.fab')
    fill_sheet(pg, 'company', '현대')
    fill_sheet(pg, 'name', 'M카드')
    pg.locator('.overlay [data-k=bank_account_id]').select_option(index=1)
    sheet_btn(pg, '저장')
    pg.locator('li[data-id]').first.click()
    pg.wait_for_timeout(200)
    pg.click('.fab')
    fill_sheet(pg, 'summary', '노트북')
    fill_sheet(pg, 'total', '300000')
    fill_sheet(pg, 'months', '3')
    sheet_btn(pg, '저장')
    ct = q(pg, 'SELECT seq, amount, pay_date FROM card_tx ORDER BY seq')
    check('할부 3회차로 나눠 저장', [x['amount'] for x in ct] == [100000] * 3, str(ct))
    pg.click('button[data-all]')
    pg.click('button[data-pay]')
    sheet_btn(pg, '저장')
    paid = q(pg, 'SELECT paid, paid_account_tx_id FROM card_tx WHERE seq=1')[0]
    check('결제 처리 + 통장 출금 기록', paid['paid'] == 1 and paid['paid_account_tx_id'], str(paid))
    shot(pg, '18-card')
    summ = pg.evaluate('A.summary()')
    check('자산 요약: 카드 미결제 200,000', summ['카드'] == 200000, str(summ))
    pg.evaluate('App.onBack()')

    print('■ 주소록·일기·메모')
    for page, fields in [('contacts', {'name': '홍길동', 'mobile': '010-1111-2222'}), ('diary', {'title': '첫 일기', 'content': '안녕'}),
                         ('memo', {'title': '장보기', 'content': '우유'})]:
        pg.evaluate(f"App.go('{page}', {{}}, true)")
        pg.click('.fab')
        for k, v in fields.items():
            fill_sheet(pg, k, v)
        sheet_btn(pg, '저장')
        tbl = {'contacts': 'contact', 'diary': 'diary', 'memo': 'memo'}[page]
        check(f'{page} 저장', len(q(pg, f'SELECT * FROM {tbl}')) == 1)
        pg.evaluate('App.onBack()')

    print('■ CSV 불러오기')
    pg.evaluate("window.__openText = '날짜,품목,수입,지출,계정코드\\n2026-10-01,버스,0,1500,40\\n2026.10.02,택시,0,\"12,000\",40\\n2026-10-03,오류,0,1000,99\\n'")
    pg.evaluate("App.go('settings', {}, true)")
    pg.click('button[data-a=csvin]')
    pg.wait_for_selector('.sheet')
    sheet_btn(pg, '2건 넣기')
    c = q(pg, "SELECT item, expense FROM entry WHERE origin='csv' ORDER BY date")
    check('CSV 2건 (오류 1건 제외)', c == [{'item': '버스', 'expense': 1500}, {'item': '택시', 'expense': 12000}], str(c))

    print('■ 화면 꾸미기')
    pg.locator('[data-p=theme]').select_option('basic')
    check('기본 테마 적용', pg.evaluate("document.body.classList.contains('basic')"))
    shot(pg, '19-settings-basic')
    pg.locator('[data-p=theme]').select_option('retro')
    pg.locator('[data-st=b05]').click()
    check('미니미 바뀜', pg.evaluate("document.querySelector('.minimi img').src.endsWith('b05.png')"))

    print('■ 암호')
    pg.click('button[data-a=pw]')
    fill_sheet(pg, 'pw1', '1234')
    fill_sheet(pg, 'pw2', '1234')
    sheet_btn(pg, '저장')
    stored = pg.evaluate("DB.getMeta('password')")
    check('암호 저장 형식 pbkdf2$소금$해시', stored and stored.startswith('pbkdf2$') and len(stored.split('$')[2]) == 64, str(stored))
    print('■ 내보내기 → PC판 코드로 열기')
    pg.click('button[data-a=export]')
    pg.wait_for_timeout(400)
    exported = pg.evaluate('window.__fake.exported')
    check('내보내기 파일 이름', exported and exported['name'].startswith('gagyebu-') and exported['name'].endswith('.sqlite3'), str(exported and exported['name']))
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, 'exported.sqlite3')
    open(path, 'wb').write(bytes(exported['bytes']))
    code = r'''
import sys; sys.path.insert(0, sys.argv[2])
from gagyebu import db, util
from gagyebu.services import ledger as L, assets as A, reports as RP
con = db.connect(sys.argv[1], seed=False)
lid = L.first_ledger_id(con)
print(len(con.execute('SELECT * FROM entry').fetchall()), A.summary(con)['카드'], util.check_password('1234', db.get_meta(con, 'password')))
'''
    out = subprocess.run([sys.executable, '-c', code, path, os.path.abspath(os.path.join(ROOT, '..', 'gagyebu-linux'))],
                         capture_output=True, text=True)
    n_js = pg.evaluate('DB.val("SELECT COUNT(*) AS v FROM entry")')
    check('PC판 코드로 열림 (내역 수·카드 미결제·암호 같음)', out.stdout.split() == [str(n_js), '200000', 'True'], out.stdout + out.stderr)

    print('■ 다시 열기 → 암호 화면')
    db_bytes = bytes(pg.evaluate('window.__getDbBytes()'))
    pg2 = new_page(br, db_bytes)
    check('암호 화면', pg2.locator('.login').count() == 1)
    shot(pg2, '20-login')
    pg2.fill('.login input', '9999')
    pg2.click('[data-ok]')
    pg2.wait_for_timeout(2500)
    check('틀린 암호 안내', '틀렸습니다' in pg2.inner_text('.login .msg'))
    pg2.fill('.login input', '1234')
    pg2.click('[data-ok]')
    pg2.wait_for_selector('.navbar', timeout=15000)
    check('맞는 암호 → 들어감', pg2.locator('.navbar').count() == 1)
    pg2.wait_for_timeout(900)
    check('시작할 때 남은 예약 입력 창 (PC판과 같음)', pg2.locator('.sheet .sh .t', has_text='예약된 수입·지출 자동입력').count() == 1)
    pg2.evaluate('while (UI.closeTop()) {}')

    print('■ 가져오기 (PC판 표본 자료)')
    pyfile = os.path.join(ROOT, 'devtools', 'compat', 'out', 'py.sqlite3')
    pg2.evaluate(f'window.__importBytes = new Uint8Array({json.dumps(list(open(pyfile, "rb").read()))})')
    pg2.evaluate("App.go('settings', {}, true)")
    pg2.click('button[data-a=import]')
    pg2.locator('.dialog button', has_text='파일 고르기').click()
    pg2.wait_for_timeout(800)
    names = [x['name'] for x in q(pg2, 'SELECT name FROM ledger ORDER BY id')]
    check('PC판 자료로 바뀜 (장부 2개)', names == ['가계부 장부', '비상금 장부'], str(names))
    shot(pg2, '21-after-import')
    check('가져온 뒤 알림', '가져왔습니다' in ' '.join(pg2.locator('.dialog .msg').all_inner_texts()))
    pg2.evaluate("window.__importBytes = new Uint8Array([1,2,3,4])")
    pg2.evaluate('while (UI.closeTop()) {}')
    pg2.evaluate("App.go('settings', {}, true)")
    pg2.click('button[data-a=import]')
    pg2.locator('.dialog button', has_text='파일 고르기').click()
    pg2.wait_for_timeout(500)
    msg = pg2.inner_text('.dialog .msg') if pg2.locator('.dialog').count() else ''
    check('엉뚱한 파일은 거부하고 지금 자료 유지', '지금 자료는 그대로' in msg and len(q(pg2, 'SELECT * FROM ledger')) == 2, msg)
    print('■ 자료 파일이 망가졌을 때')
    pg3 = new_page(br, b'not a sqlite file at all' * 50)
    check('되살리기 화면 (PC 백업 가져오기 버튼)', pg3.locator('[data-imp]').count() == 1)
    shot(pg3, '22-recovery')
    errs[:] = [e for e in errs if 'not a database' not in e and 'file is not' not in e]
    br.close()

print('\n페이지 오류:', errs if errs else '없음')
print('결과:', '통과' if not fails and not errs else f'실패 {len(fails)}건: {fails}')
sys.exit(1 if fails or errs else 0)
