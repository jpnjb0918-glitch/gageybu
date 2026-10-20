"""1.7.0 기능 화면 점검 (브라우저 + 가짜 NativeBridge): 계산기 금액 칸 · 자주 쓰는 내역 · 문자로 넣기 · 사진 ·
예산 막대/알림/예산 정하기 · 통장끼리 이체 · 저축 목표 · 빌려준 돈/빌린 돈 · 이달 리포트 · 태그 · 달력 무지출 ·
위젯 [＋ 입력]·문자 공유로 열기. 테마마다 화면을 찍는다.
  python3 features170.py      → shots/f170/<테마>-<화면>.png"""
import functools
import http.server
import json
import os
import socketserver
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'devtools', 'shots', 'f170')
os.makedirs(OUT, exist_ok=True)

SEED = r"""
() => {
  const lid = App.lid;
  const t = U.today(); const [y, m] = U.parts(t);
  const day = d => U.iso(y, m, Math.min(d, Number(t.slice(8))));
  const [py, pm] = U.addMonths(y, m, -1);
  const add = (d, item, exp, code, memo) => L.addEntry(lid, { date: d, item, income: 0, expense: exp, code, memo: memo || '' });
  add(day(1), '장보기', 64000, '30'); add(day(2), '점심', 9000, '31', '#회사'); add(day(3), '버스', 1500, '40');
  add(day(4), '기차표', 59800, '40', '#여행 #부산'); add(day(5), '숙소', 120000, '80', '#여행'); add(day(6), '커피', 4500, '31');
  for (let i = 0; i < 8; i++) add(U.iso(py, pm, 1 + i * 3), '장보기', 31000, '30');
  L.addEntry(lid, { date: day(1), item: '월급', income: 3200000, expense: 0, code: '00', memo: '' });
  Rep.setBudgets(lid, [U.ym(y, m)], { '30': 150000, '31': 60000, '40': 70000, '80': 100000 });
  L.saveFavorite(lid, { item: '지하철', expense: 1500, code: '40' });
  L.saveFavorite(lid, { item: '점심', expense: 9000, code: '31', memo: '#회사' });
  A.saveAccount('bank', { name: '월급통장', company: '국민', opening: 1500000, active: 1 });
  A.saveAccount('bank', { name: '비상금', company: '카카오', opening: 0, active: 1 });
  const g = Goal.saveGoal({ name: '여행 자금', target: 1200000, due: U.addDays(t, 150) });
  Goal.addGoalTx(g, U.addDays(t, -30), 300000); Goal.addGoalTx(g, t, 150000);
  const d1 = Goal.saveDebt({ kind: 'lend', person: '철수', amount: 50000, date: U.addDays(t, -20), due: U.addDays(t, -2) });
  Goal.addPayment(d1, U.addDays(t, -5), 20000);
  Goal.saveDebt({ kind: 'borrow', person: '영희', amount: 30000, date: U.addDays(t, -3) });
  const e = DB.val("SELECT id FROM entry WHERE item='숙소'");
  Att.add(e, window.__tinyJpeg, '영수증.jpg');
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
TINY = open(os.path.join(ROOT, 'devtools', 'fake-native.js'), encoding='utf-8').read().split("const TINY_JPEG = '")[1].split("'")[0]


def check(name, cond, extra=''):
    print(('  ✓ ' if cond else '  ✗ ') + name + (f'  ({extra})' if extra and not cond else ''))
    if not cond:
        fails.append(name)


THEMES = ['retro', 'basic', 'feed', 'feed_light', 'feed_dark', 'timeline', 'timeline_light', 'timeline_dark']


def page(br, th, launch=None):
    ctx = br.new_context(viewport={'width': 412, 'height': 860}, device_scale_factor=2, is_mobile=True, has_touch=True)
    ctx.add_init_script(path=os.path.join(ROOT, 'devtools', 'fake-native.js'))
    st = {'prefs': {'theme': th}}
    if launch:
        st['launch'] = json.dumps(launch, ensure_ascii=False)
    ctx.add_init_script(f"window.__tinyJpeg = {json.dumps(TINY)}; window.__fake && Object.assign(window.__fake.prefs, {json.dumps(st['prefs'])});"
                        + (f"window.__fake && (window.__fake.launch = {json.dumps(st['launch'])});" if launch else ''))
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: errs.append(f'{th}: {e}'))
    pg.on('console', lambda m: errs.append(f'{th}: {m.text}') if m.type == 'error' else None)
    pg.goto(URL)
    pg.wait_for_selector('.navbar', timeout=20000)
    pg.wait_for_timeout(300)
    return ctx, pg


def close_sheets(pg):
    pg.evaluate("() => { while (UI.closeTop()) {} }")


with sync_playwright() as p:
    br = p.chromium.launch()
    # ── 동작 (기본 테마) ──
    print('동작')
    ctx, pg = page(br, 'basic')
    close_sheets(pg)
    pg.evaluate(SEED)
    pg.wait_for_timeout(200)
    # 예산 막대
    check('예산 막대가 가계부 화면에', pg.locator('.bcard').count() == 1)
    pg.screenshot(path=os.path.join(OUT, 'basic-가계부.png'))
    check('사진 붙은 내역에 사진기 표시', pg.locator('li[data-id] .camk').count() == 1)
    # 새 내역: 계산기 칸 + 자주 쓰는 내역 + 예산 알림
    pg.evaluate("Entry.open({ date: U.today() })")
    pg.wait_for_timeout(300)
    check('자주 쓰는 내역 칩 2개', pg.locator('.favs .chip.fav').count() == 2)
    pg.locator('.favs .chip.fav').nth(1).click()
    pg.wait_for_timeout(100)
    vals = pg.evaluate("() => ({ item: UI.$('.sheet [data-k=item]').value, exp: UI.$('.sheet [data-k=expense]').value, code: UI.$('.sheet [data-k=code]').value })")
    check('자주 쓰는 내역으로 칸 채우기', vals == {'item': '점심', 'exp': '9,000', 'code': '31'}, str(vals))
    # 계산기
    pg.locator('.sheet .calcbtn').first.click()
    pg.wait_for_timeout(200)
    for k in ['C', '1', '2', '000', '+', '3', '5', '00']:
        pg.locator(f'.calcpad [data-k="{k}"]').click()
    res = pg.locator('.calcpad .cp-res').inner_text()
    check('계산기 결과 표시', '15,500' in res, res)
    pg.screenshot(path=os.path.join(OUT, 'basic-계산기.png'))
    pg.locator('.overlay .sf .btn.pri').last.click()
    pg.wait_for_timeout(150)
    check('계산기 [넣기] → 금액 칸', pg.evaluate("UI.$('.sheet [data-k=expense]').value") == '15,500')
    # 직접 계산식 입력
    pg.fill('.sheet [data-k=expense]', '45000+5000')
    pg.evaluate("UI.$('.sheet [data-k=expense]').dispatchEvent(new Event('blur'))")
    check('계산식 입력 → 칸을 벗어나면 계산', pg.evaluate("UI.$('.sheet [data-k=expense]').value") == '50,000')
    # 새 내역 사진 (앨범)
    pg.locator('.sheet [data-ph="album"]').click()
    pg.wait_for_timeout(200)
    check('새 내역 사진 미리보기', pg.locator('.sheet .phth').count() == 1)
    pg.screenshot(path=os.path.join(OUT, 'basic-새내역.png'))
    n0 = pg.evaluate("DB.val('SELECT COUNT(*) FROM entry')")
    pg.locator('.overlay .sf .btn.pri').last.click()
    pg.wait_for_timeout(300)
    check('저장', pg.evaluate("DB.val('SELECT COUNT(*) FROM entry')") == n0 + 1)
    toast = pg.locator('.toast').inner_text() if pg.locator('.toast').count() else ''
    check('예산 알림 (외식 100% 넘음)', '예산을 넘었어요' in toast, toast)
    eid = pg.evaluate("DB.val('SELECT MAX(id) FROM entry')")
    check('사진이 새 내역에 함께 저장', pg.evaluate(f"Att.listFor({eid}).length") == 1)
    check('위젯 새로 그리기 부탁', pg.evaluate("new Promise(r => setTimeout(() => r(window.__fake.widget || 0), 800))") >= 1)
    # 문자로 넣기
    t = pg.evaluate("U.today()")
    mmdd = t[5:7] + '/' + t[8:10]
    sms = (f'[Web발신]\n신한카드(1234)승인 홍*동 12,500원 일시불 {mmdd} 08:41 스타벅스 누적345,600원\n\n'
           f'[Web발신]\n롯데카드 승인취소 홍*동 4,500원 {mmdd} 09:10 커피빈\n\n[Web발신]\nKB국민카드 홍*동 9,800원 {mmdd} 12:10 GS25 역삼점')
    pg.evaluate(f"Extra.smsSheet({json.dumps(sms, ensure_ascii=False)})")
    pg.wait_for_timeout(300)
    check('문자 3건 읽음', pg.locator('.sms-c').count() == 3)
    codes = pg.evaluate("UI.$$('.sms-c [data-f=code]').map(x => x.value)")
    check('가게 이름으로 계정 짐작 (스타벅스→외식, GS25→식료품)', codes[0] == '31' and codes[2] == '30', str(codes))
    pg.screenshot(path=os.path.join(OUT, 'basic-문자로넣기.png'))
    n0 = pg.evaluate("DB.val('SELECT COUNT(*) FROM entry')")
    pg.locator('.overlay .sf .btn.pri').last.click()
    pg.wait_for_timeout(300)
    check('문자 3건 저장', pg.evaluate("DB.val('SELECT COUNT(*) FROM entry')") == n0 + 3)
    check('취소 문자는 지출 −', pg.evaluate("DB.val(\"SELECT expense FROM entry WHERE item='커피빈 (취소)'\")") == -4500)
    check('취소 내역은 +4,500 으로 (--4,500 아님)', '--' not in pg.locator('.ledger-list').inner_text())
    # 예산 정하기
    close_sheets(pg)
    pg.evaluate("App.go('ledger')")
    pg.wait_for_timeout(200)
    pg.locator('.bcard').click()
    pg.wait_for_timeout(200)
    pg.screenshot(path=os.path.join(OUT, 'basic-예산자세히.png'))
    pg.locator('.overlay .sf .btn.pri').last.click()            # 예산 정하기
    pg.wait_for_timeout(200)
    pg.fill('.bset [data-c="30"]', '200000')
    pg.select_option('.overlay [data-span]', '12')
    pg.screenshot(path=os.path.join(OUT, 'basic-예산정하기.png'))
    pg.locator('.overlay .sf .btn.pri').last.click()
    pg.wait_for_timeout(200)
    nxt = pg.evaluate("U.ym(...U.addMonths(...U.parts(U.today()).slice(0, 2), 1))")
    check('예산 12달 같게', pg.evaluate(f"Rep.budgets(App.lid, '{nxt}')['30']") == 200000)
    close_sheets(pg)
    # 자산: 이체·저축 목표·빌려준 돈
    pg.evaluate("App.go('assets')")
    pg.wait_for_timeout(200)
    check('자산 요약에 받을 돈', '받을 돈 30,000' in pg.locator('.content').inner_text())
    pg.locator('.amore [data-tr]').click()
    pg.wait_for_timeout(200)
    pg.fill('.overlay [data-k=amount]', '100000')
    pg.screenshot(path=os.path.join(OUT, 'basic-이체.png'))
    pg.locator('.overlay .sf .btn.pri').last.click()
    pg.wait_for_timeout(200)
    bal = pg.evaluate("A.accounts('bank').map(a => A.accountBalance(a.id))")
    check('이체 잔액', bal == [1400000, 100000], str(bal))
    pg.locator('.amore [data-go="goals"]').click()
    pg.wait_for_timeout(200)
    check('저축 목표 37%', '37%' in pg.locator('.content').inner_text())
    pg.screenshot(path=os.path.join(OUT, 'basic-저축목표.png'))
    pg.locator('.goall li').first.click()
    pg.wait_for_timeout(200)
    pg.fill('.overlay [data-k=amount]', '50000')
    pg.locator('.overlay [data-add="1"]').click()
    pg.wait_for_timeout(200)
    check('모은 돈 기록', pg.evaluate("Goal.goalStatus(Goal.goals()[0]).saved") == 500000)
    close_sheets(pg)
    pg.evaluate("App.go('debts', {}, true)")
    pg.wait_for_timeout(200)
    check('빌려준 돈 기한 지남', '기한 지남' in pg.locator('.content').inner_text())
    pg.screenshot(path=os.path.join(OUT, 'basic-빌려준돈.png'))
    # 결산: 리포트·태그
    pg.evaluate("App.go('report')")
    pg.wait_for_timeout(200)
    pg.locator('.seg [data-k="insight"]').click()
    pg.wait_for_timeout(200)
    txt = pg.locator('.ins').inner_text()
    check('이달 리포트', '썼어요' in txt and '많이 쓴 곳' in txt and '무지출' in txt, txt[:120])
    pg.screenshot(path=os.path.join(OUT, 'basic-이달리포트.png'), full_page=True)
    pg.locator('.seg [data-k="tags"]').click()
    pg.wait_for_timeout(200)
    tags = pg.evaluate("UI.$$('.tagl [data-tag]').map(x => x.dataset.tag)")
    check('태그', '여행' in tags and '회사' in tags, str(tags))
    pg.screenshot(path=os.path.join(OUT, 'basic-태그.png'))
    # 달력 무지출
    pg.evaluate("App.go('calendar')")
    pg.wait_for_timeout(200)
    if int(t[8:10]) > 7:
        check('달력 무지출 표시', pg.locator('.cal .nsp').count() >= 1)
    pg.screenshot(path=os.path.join(OUT, 'basic-달력.png'))
    # 화면 구성에 예산 막대
    check('화면 구성 목록에 예산 막대', 'budget' in pg.evaluate("App.ledgerLayout()"))
    pg.evaluate("App.setPref('ledger_layout', JSON.stringify(['monthnav','stats','opts','list']))")
    lay = pg.evaluate("App.ledgerLayout()")
    check('예전에 정한 순서: 예산 막대는 목록 바로 위', lay.index('budget') == lay.index('list') - 1, str(lay))
    ctx.close()

    # ── 위젯 [＋ 입력]·문자 공유로 열기 ──
    print('밖에서 열기')
    ctx, pg = page(br, 'basic', {'action': 'new'})
    pg.wait_for_timeout(600)
    check('위젯 [＋ 입력] → 새 내역 창', pg.locator('.sheet .sh .t').first.inner_text() == '새 내역 입력')
    ctx.close()
    ctx, pg = page(br, 'basic', {'action': 'sms', 'text': '[Web발신]\n삼성카드 홍*동 23,400원 10/13 18:30 올리브영'})
    pg.wait_for_timeout(700)
    check('문자 공유 → 문자로 넣기 창', pg.locator('.sms-c').count() == 1)
    ctx.close()

    # ── 테마마다 ──
    for th in THEMES:
        print(th)
        ctx, pg = page(br, th)
        close_sheets(pg)
        pg.evaluate(SEED)
        pg.wait_for_timeout(250)
        check(f'{th} 예산 막대', pg.locator('.bcard').count() == 1)
        pg.evaluate("document.querySelector('.bcard').scrollIntoView({block: 'center'})")
        pg.screenshot(path=os.path.join(OUT, f'{th}-가계부.png'))
        pg.evaluate("Entry.open({ date: U.today() })")
        pg.wait_for_timeout(300)
        pg.screenshot(path=os.path.join(OUT, f'{th}-새내역.png'))
        close_sheets(pg)
        pg.evaluate("Pages.report.openInsight(...U.parts(U.today()).slice(0, 2))")
        pg.wait_for_timeout(250)
        pg.screenshot(path=os.path.join(OUT, f'{th}-이달리포트.png'))
        pg.evaluate("App.go('goals', {}, true)")
        pg.wait_for_timeout(200)
        pg.screenshot(path=os.path.join(OUT, f'{th}-저축목표.png'))
        ctx.close()
    br.close()

errs = [e for e in errs if 'favicon' not in e]
for e in errs:
    print('오류:', e)
print('결과:', '통과' if not fails and not errs else f'실패 {len(fails)} · 오류 {len(errs)}')
raise SystemExit(1 if fails or errs else 0)
