"""1.7.0(휴대폰) 기능 화면 점검 (브라우저 + 가짜 NativeBridge): 결제수단 · 외화로 적기 · 큰돈 나눠 적기 · 같은 곳 모아보기 ·
휴지통 · 한 달 전체 예산 · 주간 예산 · 매주/매년 고정 수입·지출 · 고정비 한눈에 · 통계(주별·결제수단·저축) · 카드 실적 ·
달력 결제일 · 카테고리 그림 · 검색 결제수단 · 매일 입력 알림. 테마마다 화면을 찍는다.
  python3 features180.py      → shots/f180/<테마>-<화면>.png"""
import functools
import http.server
import json
import os
import socketserver
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'devtools', 'shots', 'f180')
os.makedirs(OUT, exist_ok=True)

SEED = r"""
() => {
  const lid = App.lid;
  const t = U.today(); const [y, m] = U.parts(t);
  const ms = U.iso(y, m, 1);
  const day = d => U.iso(y, m, Math.min(d, Number(t.slice(8))));
  const cid = A.saveCard({ company: '신한', name: 'Deep Dream', pay_day: 14, bill_from_month: '-1', bill_from_day: 1, bill_to_month: '-1', bill_to_day: 31, 'x.perf': 300000 });
  A.addCardPurchase(cid, ms, '노트북', 600000, 0, 3);
  const add = (d, item, exp, code, pay) => L.addEntry(lid, { date: d, item, income: 0, expense: exp, code, memo: '', pay });
  add(day(1), '스타벅스', 4800, '31', `card:${cid}`); add(day(4), '장보기', 64000, '30', 'card');
  add(day(7), '스타벅스', 5200, '31', `card:${cid}`); add(day(10), '버스', 1500, '40', 'cash');
  add(day(13), '편의점', 3000, '30', 'pay'); add(day(16), '스타벅스', 4500, '31', 'cash');
  L.addEntry(lid, { date: ms, item: '급여', income: 3200000, expense: 0, code: '00', memo: '', pay: 'bank' });
  R.saveRule(lid, { item: '월세', expense: 500000, code: '10', day: 25, start: U.addDays(ms, -60) });
  R.saveRule(lid, { item: '용돈', expense: 30000, code: '80', start: U.addDays(ms, -60), cycle: 'W', wday: 4, pay: 'cash' });
  App.dataChanged();
  return cid;
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


def page(br, th, prefs=None):
    ctx = br.new_context(viewport={'width': 412, 'height': 860}, device_scale_factor=2, is_mobile=True, has_touch=True)
    ctx.add_init_script(path=os.path.join(ROOT, 'devtools', 'fake-native.js'))
    pr = dict({'theme': th}, **(prefs or {}))
    ctx.add_init_script(f"window.__fake && Object.assign(window.__fake.prefs, {json.dumps(pr)});")
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: errs.append(f'{th}: {e}'))
    pg.on('console', lambda m: errs.append(f'{th}: {m.text}') if m.type == 'error' else None)
    pg.goto(URL)
    pg.wait_for_selector('.navbar', timeout=20000)
    pg.wait_for_timeout(300)
    return ctx, pg


def close_sheets(pg):
    pg.evaluate("() => { while (UI.closeTop()) {} }")


def pri(pg):
    pg.locator('.overlay .sf .btn.pri').last.click()
    pg.wait_for_timeout(200)


def toast(pg):
    return pg.locator('.toast').inner_text() if pg.locator('.toast').count() else ''


def hscroll(pg):
    return pg.evaluate("() => { const c = document.querySelector('.content'); return Math.max(0, document.documentElement.scrollWidth - innerWidth, c ? c.scrollWidth - c.clientWidth : 0); }")


with sync_playwright() as p:
    br = p.chromium.launch()
    print('동작')
    ctx, pg = page(br, 'basic')
    close_sheets(pg)
    emap = pg.evaluate("Emo.map(App.lid)")
    check('처음 열면 카테고리 그림이 들어감 (식료품 🛒 · 외식 🍜)', emap.get('30') == '🛒' and emap.get('31') == '🍜', str(emap)[:80])
    cid = pg.evaluate(SEED)
    pg.wait_for_timeout(250)
    txt = pg.locator('.ledger-list').inner_text()
    check('가계부 목록: 카테고리 그림 · 결제수단 이름', '🍜 외식' in txt and '신한 Deep Dream' in txt and '현금' in txt, txt[:160])

    print('결제수단 입력')
    pg.evaluate("Entry.open({ date: U.today() })")
    pg.wait_for_timeout(300)
    opts = pg.evaluate("UI.$$('.sheet [data-k=pay] option').map(o => o.textContent)")
    check('결제수단 고르기: 안 정함·현금·카드·계좌이체·간편결제·💳 내 카드', opts[:5] == ['(안 정함)', '현금', '카드', '계좌이체', '간편결제'] and '💳 신한 Deep Dream' in opts, str(opts))
    copts = pg.evaluate("UI.$$('.sheet [data-k=code] option').map(o => o.textContent)")
    check('카테고리 고르기에도 그림', any('🛒 식료품' in o for o in copts), str(copts[:4]))
    pg.fill('.sheet [data-k=expense]', '9000')
    pg.fill('.sheet [data-k=item]', '점심')
    pg.select_option('.sheet [data-k=code]', '31')
    pg.select_option('.sheet [data-k=pay]', f'card:{cid}')
    pri(pg)
    check('저장하면 결제수단도 저장', pg.evaluate("DB.val(\"SELECT pay FROM entry WHERE item='점심'\")") == f'card:{cid}')

    print('같은 곳 모아보기')
    pg.evaluate("Entry.open({ date: U.today() })")
    pg.wait_for_timeout(300)
    pg.fill('.sheet [data-k=item]', '스타벅스')
    pg.wait_for_timeout(450)
    sl = pg.locator('.sheet [data-same]').inner_text()
    check("내용을 쓰면 '최근 3개월 3건' 줄", pg.locator('.sheet [data-same]:not(.hidden)').count() == 1 and '3건' in sl and '14,500원' in sl, sl)
    pg.locator('.sheet [data-same]').click()
    pg.wait_for_timeout(250)
    check('같은 곳 창: 3건 · 달마다 막대', pg.locator('.overlay').last.locator('li[data-id]').count() == 3 and pg.locator('.overlay').last.locator('.sp-m').count() >= 3)
    pg.screenshot(path=os.path.join(OUT, 'basic-같은곳.png'))
    pg.evaluate("UI.closeTop()")

    print('외화로 적기')
    pg.locator('.sheet [data-fx]').click()
    pg.wait_for_timeout(250)
    pg.select_option('.overlay:last-child [data-k=cur]', 'JPY')
    pg.fill('.overlay:last-child [data-k=amt]', '3500')
    pg.fill('.overlay:last-child [data-k=rate]', '935.2')
    res = pg.locator('.overlay:last-child [data-res]').inner_text()
    check('외화: 3,500엔 × 935.2/100 → 32,732원 (미리 보기)', res == '32,732원', res)
    pg.screenshot(path=os.path.join(OUT, 'basic-외화.png'))
    pri(pg)
    v = pg.evaluate("({ exp: UI.$('.sheet [data-k=expense]').value, memo: UI.$('.sheet [data-k=memo]').value })")
    check('외화 → 지출 칸 32,732 · 메모에 외화 금액', v['exp'] == '32,732' and 'JPY 3,500 × 935.2원/100' in v['memo'], str(v))
    check('환율을 기억 (자료 파일)', pg.evaluate("Fx.rates().JPY") == '935.2' and pg.evaluate("DB.getMeta('fx_last')") == 'JPY')
    close_sheets(pg)

    print('큰돈 나눠 적기')
    pg.evaluate("Entry.open({ date: U.today() })")
    pg.wait_for_timeout(300)
    pg.fill('.sheet [data-k=expense]', '1200005')
    pg.fill('.sheet [data-k=item]', '자동차보험')
    pg.select_option('.sheet [data-k=code]', '60')
    pg.locator('.sheet [data-split]').click()
    pg.wait_for_timeout(250)
    check('나눠 적기 미리 보기 12건', pg.locator('.sp-list li').count() == 12)
    pg.screenshot(path=os.path.join(OUT, 'basic-나눠적기.png'))
    pri(pg)
    rows = pg.evaluate("DB.q(\"SELECT expense FROM entry WHERE item LIKE '자동차보험 (%' ORDER BY date\").map(r => r.expense)")
    check('12달로 12건 (첫 달 100,005 · 나머지 100,000) · 입력 창 닫힘', len(rows) == 12 and rows[0] == 100005 and rows[1] == 100000
          and pg.locator('.sheet').count() == 0, str(rows[:3]))

    print('지우기 → 휴지통')
    eid = pg.evaluate("DB.val(\"SELECT id FROM entry WHERE item LIKE '자동차보험 (3/12)'\")")
    pg.evaluate(f"Entry.open({{ entry: L.getEntry({eid}) }})")
    pg.wait_for_timeout(250)
    pg.locator('.overlay .sf .btn.danger').click()
    pg.wait_for_timeout(200)
    msg = pg.locator('.dialog .msg').inner_text()
    check('나눠 적은 내역을 지우면 묶음째 지울지 물음', '함께 나눠 적은 11건' in msg, msg)
    pg.screenshot(path=os.path.join(OUT, 'basic-나눠적은것지우기.png'))
    pg.locator('.dialog .btn.danger').click()
    pg.wait_for_timeout(250)
    left = pg.evaluate("DB.val(\"SELECT COUNT(*) FROM entry WHERE item LIKE '자동차보험 (%'\")")
    check('모두 지우기 → 12건 휴지통으로', left == 0 and pg.evaluate("Trash.count(App.lid)") == 12, f'{left}')
    check('알림: 휴지통으로 옮겼어요', '휴지통으로 옮겼어요' in toast(pg), toast(pg))
    pg.evaluate("App.go('ledger')")
    pg.wait_for_timeout(200)
    check('가계부 머리에 휴지통 단추 (12)', pg.locator('.trashbtn .badge').inner_text() == '12')
    pg.locator('.trashbtn').click()
    pg.wait_for_timeout(250)
    check('휴지통 창: 12건', pg.locator('.trl li[data-t]').count() == 12)
    pg.locator('.trl li[data-t]').nth(0).click()
    pg.locator('.trl li[data-t]').nth(1).click()
    pg.screenshot(path=os.path.join(OUT, 'basic-휴지통.png'))
    pri(pg)
    check('체크한 2건 되살리기', pg.evaluate("Trash.count(App.lid)") == 10
          and pg.evaluate("DB.val(\"SELECT COUNT(*) FROM entry WHERE item LIKE '자동차보험 (%'\")") == 2)
    close_sheets(pg)

    print('예산 (전체 · 주간)')
    pg.evaluate("Extra.budgetSheet(App.lid, ...U.parts(U.today()).slice(0, 2))")
    pg.wait_for_timeout(250)
    pg.fill('.overlay [data-t=month]', '800000')
    pg.fill('.overlay [data-t=week]', '150000')
    pg.screenshot(path=os.path.join(OUT, 'basic-예산정하기.png'))
    pri(pg)
    check('한 달 전체 예산 · 주간 예산 저장', pg.evaluate("TBud.get(App.lid, U.today().slice(0, 7))") == 800000 and pg.evaluate("Week.budget(App.lid)") == 150000)
    bc = pg.locator('.bcard').inner_text()
    check("예산 막대: '전체 예산' + 이번 주 + 요일 막대", '전체 예산' in bc and '이번 주' in bc and pg.locator('.bcard .wdays .d').count() == 7, bc[:80])
    pg.evaluate("document.querySelector('.bcard').scrollIntoView({block: 'center'})")
    pg.screenshot(path=os.path.join(OUT, 'basic-가계부.png'))

    print('고정 수입·지출 (매주·매년 · 고정비)')
    pg.evaluate("App.go('recurring', {}, true)")
    pg.wait_for_timeout(250)
    chips = pg.evaluate("UI.$$('.content .list li .chip').map(x => x.textContent)")
    check('목록에 반복 주기 글 (매달 25일 · 매주 금요일)', '매달 25일' in chips and '매주 금요일' in chips, str(chips))
    fx = pg.locator('.fixedbox').inner_text()
    check("'이번 달 고정비 한눈에'", '고정 지출' in fx and '남을 돈' in fx, fx[:80])
    check('매주 규칙의 끝나는 날이 1900-01-01 로 보이지 않음', '1900' not in pg.locator('.content').inner_text())
    pg.locator('.fab').click()
    pg.wait_for_timeout(250)
    pg.fill('.overlay [data-k=item]', '자동차세')
    pg.fill('.overlay [data-k=expense]', '250000')
    pg.select_option('.overlay [data-k=code]', '60')
    pg.select_option('.overlay [data-k=cyc]', 'Y:1')
    vis = pg.evaluate("['ymonth','wday','day'].map(k => !UI.$(`.overlay [data-k=${k}]`).closest('.f').classList.contains('hidden'))")
    check('매년: 월·날 칸이 보이고 요일 칸은 숨김', vis == [True, False, True], str(vis))
    pg.select_option('.overlay [data-k=ymonth]', '6')
    pg.fill('.overlay [data-k=day]', '30')
    pg.screenshot(path=os.path.join(OUT, 'basic-고정추가.png'))
    pri(pg)
    r = pg.evaluate("DB.one(\"SELECT * FROM recurring WHERE item='자동차세'\")")
    check('매년 6월 30일 저장 (예전 판이 건너뛰게 end 막음)', r and r['cycle'] == 'Y' and r['ymonth'] == 6 and r['day'] == 30 and r['end'] == '1900-01-01', str(r))
    close_sheets(pg)
    pg.screenshot(path=os.path.join(OUT, 'basic-고정.png'))

    print('통계')
    pg.evaluate("App.go('report')")
    pg.wait_for_timeout(250)
    check('통계 탭 10개 (두 줄)', pg.locator('.seg.rows button').count() == 10)
    pg.locator('.seg [data-k="weekly"]').click()
    pg.wait_for_timeout(250)
    check('주별: 그 달을 주로 나눔 (주간 예산 막대)', pg.locator('.wkl li').count() >= 4 and pg.locator('.wkl .pbar').count() >= 4)
    pg.screenshot(path=os.path.join(OUT, 'basic-통계주별.png'))
    pg.locator('.seg [data-k="pay"]').click()
    pg.wait_for_timeout(250)
    labs = pg.evaluate("UI.$$('.payst li .main-t').map(x => x.textContent.trim())")
    check('결제수단별: 💳 신한 Deep Dream · 현금 (지출 많은 순, 미지정이 있으면 맨 뒤)', '💳 신한 Deep Dream' in labs and '현금' in labs
          and ('미지정' not in labs or labs[-1] == '미지정') and labs[0] == '카드', str(labs))
    perf = pg.locator('.perfl').inner_text() if pg.locator('.perfl').count() else ''
    check('카드 실적 (목표 30만원)', '300,000' in perf, perf)
    pg.screenshot(path=os.path.join(OUT, 'basic-통계결제수단.png'), full_page=True)
    pg.locator('.payst li').first.click()
    pg.wait_for_timeout(200)
    check('결제수단을 누르면 그 내역', pg.locator('.overlay li[data-id]').count() >= 1)
    close_sheets(pg)
    pg.locator('.seg [data-k="savings"]').click()
    pg.wait_for_timeout(250)
    check('저축: 12달', pg.locator('.savl li').count() == 12)
    pg.screenshot(path=os.path.join(OUT, 'basic-통계저축.png'))
    pg.locator('.seg [data-k="monthly"]').click()
    pg.wait_for_timeout(250)
    check('월별 통계 표에도 그림', '🍜' in pg.locator('table.rep').inner_text())
    pg.locator('.seg [data-k="insight"]').click()
    pg.wait_for_timeout(250)
    ins = pg.locator('.ins').inner_text()
    check('이달 리포트에 고정 수입·지출 · 카드 실적 · 전체 예산', '고정 수입·지출' in ins and '카드 실적' in ins and '전체 예산' in ins, ins[-200:])

    print('달력')
    pg.evaluate("App.go('calendar')")
    pg.wait_for_timeout(250)
    cal = pg.locator('.cal').inner_text()
    check('달력에 🔁 고정 수입·지출', '🔁' in cal)
    pg.screenshot(path=os.path.join(OUT, 'basic-달력.png'))
    pg.locator('.monthnav [data-d="1"]').click()
    pg.wait_for_timeout(250)
    check('다음 달 달력에 💳 카드 결제일', '💳' in pg.locator('.cal').inner_text())
    d14 = pg.evaluate("(() => { const [y, m] = U.addMonths(...U.parts(U.today()).slice(0, 2), 1); return U.iso(y, m, 14); })()")
    pg.locator(f'td[data-d="{d14}"]').click()
    pg.wait_for_timeout(250)
    check('그 날 창에 카드 결제 금액', '신한 Deep Dream 결제' in pg.locator('.overlay').last.inner_text())
    close_sheets(pg)
    pg.locator('[data-mon]').uncheck()
    pg.wait_for_timeout(200)
    check('[결제일·고정 보이기] 끄면 사라짐', '💳' not in pg.locator('.cal').inner_text() and pg.evaluate("App.pref('cal_money')") == 'false')
    pg.locator('[data-mon]').check()
    pg.wait_for_timeout(150)

    print('설정: 결제수단 · 휴지통 · 알림 · 카테고리 그림')
    pg.evaluate("App.go('settings')")
    pg.wait_for_timeout(250)
    check('설정에 결제수단 · 휴지통 · 매일 입력 알림', all(pg.locator(f'[data-a="{k}"]').count() == 1 for k in ('pays', 'trash', 'remind')))
    pg.locator('[data-a="pays"]').click()
    pg.wait_for_timeout(200)
    pri(pg)                                   # 추가
    pg.fill('.overlay:last-child [data-k=name]', '지역화폐')
    pri(pg)
    check('직접 만든 결제수단 추가', pg.evaluate("Pay.custom()") == ['지역화폐'])
    pg.locator('.payl [data-ren]').click()
    pg.wait_for_timeout(200)
    pg.fill('.overlay:last-child [data-k=name]', '온누리상품권')
    pri(pg)
    check('이름 바꾸기', pg.evaluate("Pay.custom()") == ['온누리상품권'])
    pg.screenshot(path=os.path.join(OUT, 'basic-설정결제수단.png'))
    close_sheets(pg)
    pg.locator('[data-a="remind"]').click()
    pg.wait_for_timeout(200)
    pg.locator('.overlay [data-k=on]').check()
    pg.fill('.overlay [data-k=time]', '21:30')
    pg.locator('.overlay [data-test]').click()
    pg.wait_for_timeout(300)
    check('알림 시험 보내기', 'test' in (pg.evaluate("window.__fake.notes") or []))
    pg.screenshot(path=os.path.join(OUT, 'basic-매일알림.png'))
    pri(pg)
    rm = pg.evaluate("window.__fake.reminder")
    check('매일 21:30 알림 예약 (권한 물어봄)', rm and rm['on'] and rm['h'] == 21 and rm['m'] == 30 and rm['ask'], str(rm))
    check('설정 줄에 매일 21:30', '매일 21:30' in pg.locator('[data-a="remind"]').inner_text())
    pg.evaluate("App.go('codes', {}, true)")
    pg.wait_for_timeout(250)
    check('카테고리 편집 목록에 그림', '🛒 식료품' in pg.locator('.content').inner_text())
    pg.locator('li[data-c="30"]').click()
    pg.wait_for_timeout(200)
    pg.locator('.overlay [data-emo]').click()
    pg.wait_for_timeout(200)
    pg.screenshot(path=os.path.join(OUT, 'basic-그림고르기.png'))
    pg.locator('.emogrid [data-e="🍎"]').click()
    pg.wait_for_timeout(200)
    check('세부 카테고리 그림 바꾸기 → 바로 저장', pg.evaluate("Emo.map(App.lid)['30']") == '🍎' and pg.locator('.overlay .emo-b').inner_text() == '🍎')
    close_sheets(pg)

    print('검색 · 자산 · 문자')
    pg.evaluate("App.go('search')")
    pg.wait_for_timeout(250)
    pg.select_option('.content [data-k=pay]', 'cash')
    pg.locator('.content [data-go]').click()
    pg.wait_for_timeout(250)
    n = pg.locator('.content li[data-id]').count()
    want = pg.evaluate("DB.val(\"SELECT COUNT(*) FROM entry WHERE ledger_id=? AND pay='cash'\", [App.lid])")
    check('검색: 결제수단이 현금인 것만', n == want and n >= 2, f'{n} {want}')
    pg.evaluate("App.go('assets')")
    pg.wait_for_timeout(200)
    pg.locator('.seg [data-k="card"]').click() if pg.locator('.seg [data-k="card"]').count() else None
    pg.wait_for_timeout(250)
    check('카드 목록에 이번 달 실적', '이번 달 실적' in pg.locator('.content').inner_text())
    pg.screenshot(path=os.path.join(OUT, 'basic-자산카드.png'))
    t = pg.evaluate("U.today()")
    mmdd = t[5:7] + '/' + t[8:10]
    sms = '[Web발신]\n신한카드(1234)승인 홍*동 12,500원 일시불 ' + mmdd + ' 08:41 꽃집 누적345,600원'
    pg.evaluate(f"Extra.smsSheet({json.dumps(sms, ensure_ascii=False)})")
    pg.wait_for_timeout(300)
    check('문자 결제수단 짐작: 신한카드 → 💳 신한 Deep Dream', pg.evaluate("UI.$('.sms-c [data-f=pay]').value") == f'card:{cid}')
    pri(pg)
    check('문자로 넣은 내역에 결제수단', pg.evaluate("DB.val(\"SELECT pay FROM entry WHERE item='꽃집'\")") == f'card:{cid}')
    ctx.close()

    print('켤 때 알림 다시 걸기')
    ctx, pg = page(br, 'basic', {'remind_on': 'true', 'remind_time': '08:05'})
    rm = pg.evaluate("window.__fake.reminder")
    check('앱을 켜면 알림을 다시 걸고 권한은 묻지 않음', rm and rm['on'] and rm['h'] == 8 and rm['m'] == 5 and not rm['ask'], str(rm))
    ctx.close()

    for th in THEMES:
        print(th)
        ctx, pg = page(br, th)
        close_sheets(pg)
        pg.evaluate(SEED)
        pg.evaluate("TBud.set(App.lid, [U.today().slice(0, 7)], 800000); Week.setBudget(App.lid, 150000); L.deleteEntries([DB.val('SELECT MAX(id) FROM entry')]); App.dataChanged()")
        pg.wait_for_timeout(250)
        check(f'{th}: 가계부 가로 넘침 없음', hscroll(pg) == 0, str(hscroll(pg)))
        pg.evaluate("document.querySelector('.bcard') && document.querySelector('.bcard').scrollIntoView({block: 'center'})")
        pg.screenshot(path=os.path.join(OUT, f'{th}-가계부.png'))
        pg.evaluate("Entry.open({ entry: DB.one(\"SELECT * FROM entry WHERE item='스타벅스' ORDER BY id LIMIT 1\") })")
        pg.wait_for_timeout(450)
        check(f'{th}: 입력 창 가로 넘침 없음', pg.evaluate("UI.$('.sheet .sb').scrollWidth <= UI.$('.sheet .sb').clientWidth + 1"))
        pg.screenshot(path=os.path.join(OUT, f'{th}-내역수정.png'))
        close_sheets(pg)
        pg.evaluate("App.go('report')")
        pg.wait_for_timeout(200)
        pg.locator('.seg [data-k="pay"]').click()
        pg.wait_for_timeout(250)
        check(f'{th}: 통계 가로 넘침 없음', hscroll(pg) == 0, str(hscroll(pg)))
        pg.screenshot(path=os.path.join(OUT, f'{th}-통계결제수단.png'))
        pg.evaluate("App.go('recurring', {}, true)")
        pg.wait_for_timeout(250)
        pg.screenshot(path=os.path.join(OUT, f'{th}-고정.png'))
        pg.evaluate("App.go('calendar')")
        pg.wait_for_timeout(250)
        pg.screenshot(path=os.path.join(OUT, f'{th}-달력.png'))
        pg.evaluate("Money.trashSheet()")
        pg.wait_for_timeout(250)
        pg.screenshot(path=os.path.join(OUT, f'{th}-휴지통.png'))
        ctx.close()
    br.close()

errs = [e for e in errs if 'favicon' not in e]
for e in errs:
    print('오류:', e)
print('결과:', '통과' if not fails and not errs else f'실패 {len(fails)} · 오류 {len(errs)}')
raise SystemExit(1 if fails or errs else 0)
