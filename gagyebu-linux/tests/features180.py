"""1.8.0 기능 화면 점검: 결제수단 · 큰돈 나눠 적기 · 외화 · 매주/매년 고정 수입·지출 · 같은 곳 모아보기 · 주간 예산 ·
통계(주별·결제수단·저축) · 카테고리 그림 · 고정비 한눈에 · 한 달 전체 예산 · 달력 결제일 · 카드 실적 · 휴지통.
테마마다 화면을 PNG로 저장하고 동작을 확인한다.
사용: QT_QPA_PLATFORM=offscreen python3 tests/features180.py <출력폴더>"""
import datetime as dt
import os
import sys
import tempfile
import traceback

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QEvent, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox, QScrollArea  # noqa: E402

from gagyebu import db  # noqa: E402
from gagyebu.services import assets as A  # noqa: E402
from gagyebu.services import catemoji as E  # noqa: E402
from gagyebu.services import ledger as L  # noqa: E402
from gagyebu.services import money as M  # noqa: E402
from gagyebu.services import recurring as R  # noqa: E402
from gagyebu.services import trash as TR  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
os.makedirs(out, exist_ok=True)
tmp = tempfile.mkdtemp()
os.environ['XDG_CONFIG_HOME'] = os.path.join(tmp, 'config')
path = os.path.join(tmp, 'g.sqlite3')
con = db.connect(path)
db.set_meta(con, 'password', None)
lid = L.first_ledger_id(con)
T = dt.date.today()
ms = T.replace(day=1)
cid = A.save_card(con, {'company': '신한', 'name': 'Deep Dream', 'pay_day': 14, 'x.perf': 300000})
A.add_card_purchase(con, cid, ms, '노트북', 600000, 0, 3)
for i, (item, amt, code, pay) in enumerate([('스타벅스', 4800, '31', f'card:{cid}'), ('장보기', 64000, '30', 'card'),
                                            ('스타벅스', 5200, '31', f'card:{cid}'), ('버스', 1500, '40', 'cash'),
                                            ('편의점', 3000, '30', 'pay'), ('스타벅스', 4500, '31', 'cash')]):
    d = ms + dt.timedelta(days=min(i * 3, max(0, (T - ms).days)))
    L.add_entry(con, lid, {'date': d, 'item': item, 'expense': amt, 'code': code, 'pay': pay})
L.add_entry(con, lid, {'date': ms, 'item': '급여', 'income': 3200000, 'code': '00', 'pay': 'bank'})
R.save_rule(con, lid, {'item': '월세', 'expense': 500000, 'code': '10', 'day': 25, 'start': ms - dt.timedelta(days=60)})
R.save_rule(con, lid, {'item': '용돈', 'expense': 30000, 'code': '80', 'start': ms - dt.timedelta(days=60), 'cycle': 'W',
                       'wday': 4, 'pay': 'cash'})
con.close()

from gagyebu import theme as TH  # noqa: E402
from gagyebu.app import MainWindow  # noqa: E402

app = QApplication(sys.argv[:1])
TH.apply(app)
w = MainWindow(path)
w.resize(1360, 860)
w.show()
fails = []


def check(name, cond, extra=''):
    print(('  ✓ ' if cond else '  ✗ ') + name + (f'  ({extra})' if extra and not cond else ''))
    if not cond:
        fails.append(name)


def flush():
    app.processEvents()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    app.processEvents()


def shot(name, widget=None):
    flush()
    (widget or w).grab().save(os.path.join(out, name + '.png'))


def hscroll(page):
    p = page.parentWidget()
    while p is not None and not isinstance(p, QScrollArea):
        p = p.parentWidget()
    return p.horizontalScrollBar().maximum() if p is not None else 0


def in_dialog(act, name=None):
    """다음에 뜨는 창에서 act(dlg) — act 가 창을 닫지 않으면 사진 찍고 닫음"""
    box = {}

    def inside():
        d = app.activeModalWidget()
        if d is None:
            QTimer.singleShot(30, inside)
            return
        try:
            if name:
                shot(name, d)
            box['r'] = act(d)
        except Exception:
            box['e'] = traceback.format_exc()
        if d.isVisible():
            d.reject()
    QTimer.singleShot(40, inside)
    return box


answer = {'q': QMessageBox.StandardButton.Yes}
QMessageBox.question = staticmethod(lambda *a, **k: answer['q'])
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
warned = []
QMessageBox.warning = staticmethod(lambda p, t, text, *a, **k: warned.append(text) or QMessageBox.StandardButton.Ok)

try:
    TH.set_pref('theme', 'basic')
    w.apply_theme()
    print('카테고리 그림 (처음 열 때 이름 보고 넣음)')
    emap = E.emoji_map(w.con, w.lid)
    check('처음 열면 그림이 들어감 (식료품 🛒 · 외식 🍜)', emap.get('30') == '🛒' and emap.get('31') == '🍜', str(emap)[:80])
    lp = w.goto('LedgerPage')
    flush()
    cats = [lp.table.item(r, 5).text() for r in range(lp.table.rowCount())]
    check('가계부 표 카테고리 칸에 그림', any(c.startswith('🍜') for c in cats), str(cats[:3]))
    check("가계부 표에 '결제' 칸 · 카드 이름", lp.table.horizontalHeaderItem(7).text() == '결제'
          and any(lp.table.item(r, 7).text() == '신한 Deep Dream' for r in range(lp.table.rowCount())))
    combo = [lp.form.code.itemText(i) for i in range(lp.form.code.count())]
    check('카테고리 고르기에도 그림', any('🛒 식료품' in t for t in combo), str(combo[:4]))

    print('결제수단 입력')
    pays = [lp.form.pay.itemText(i) for i in range(lp.form.pay.count())]
    check('결제수단 고르기: 안 정함·현금·카드·계좌이체·간편결제·내 카드', pays[:5] == ['(안 정함)', '현금', '카드', '계좌이체', '간편결제']
          and '💳 신한 Deep Dream' in pays, str(pays))
    lp.new()
    lp.form.item.setText('점심')
    lp.form.expense.set_value(9000)
    lp.form.code.set_code('31')
    lp.form.pay.set_pay(f'card:{cid}')
    lp.save()
    e = w.con.execute("SELECT * FROM entry WHERE item='점심'").fetchone()
    check('저장하면 결제수단도 저장', e and e['pay'] == f'card:{cid}', str(dict(e) if e else None))
    shot('basic_가계부')

    print('같은 곳 모아보기')
    row = next(r for r in range(lp.table.rowCount()) if lp.table.item(r, 1).text() == '스타벅스')
    lp.table.selectRow(row)
    flush()
    check("고르면 '최근 3개월 n건' 단추", lp.same_btn.isVisible() and '3건' in lp.same_btn.text(), lp.same_btn.text())
    box = in_dialog(lambda d: d.findChildren(type(lp.table))[0].rowCount(), 'basic_같은곳')
    lp.same_place()
    check('모아보기 창: 같은 내용 3건', box.get('r') == 3, str(box))

    print('외화로 적기')
    lp.new()

    def fx(d):
        d.cur.setCurrentIndex(d.cur.findData('JPY'))
        d.amount.setText('3500')
        d.rate.setText('935.2')
        shot('basic_외화', d)
        d._ok()
    box = in_dialog(fx)
    lp.foreign()
    check('외화: 3,500엔 × 935.2/100 → 지출 32,732원, 메모에 외화', lp.form.expense.value() == 32732
          and 'JPY 3,500' in lp.form.memo.text(), f'{lp.form.expense.text()} {lp.form.memo.text()} {box}')
    check('환율을 기억 (자료 파일)', M.fx_rates(w.con).get('JPY') == '935.2')

    print('큰돈 나눠 적기')
    lp.new()
    lp.form.item.setText('자동차보험')
    lp.form.expense.set_value(1200005)
    lp.form.code.set_code('60')
    box = in_dialog(lambda d: (d.months.setValue(12), d._ok()), 'basic_나눠적기')
    lp.split_entry()
    rows = w.con.execute("SELECT * FROM entry WHERE item LIKE '자동차보험 (%' ORDER BY date").fetchall()
    check('12달로 나눠 12건 (첫 달 100,005 · 나머지 100,000)', len(rows) == 12 and rows[0]['expense'] == 100005
          and rows[1]['expense'] == 100000, str(len(rows)))
    # 나눠 적은 내역 하나 지우기 → 모두 지울지 물음 (모두 지우기)
    lp.all_chk.setChecked(True)
    flush()
    r1 = next(r for r in range(lp.table.rowCount()) if lp.table.item(r, 1).text().startswith('자동차보험'))
    lp.table.selectRow(r1)

    def pick_all(d):
        d.done(0)
        for b in d.buttons():
            if b.text().startswith('모두 지우기'):
                b.click()
    box = in_dialog(pick_all)
    lp.delete()
    left = w.con.execute("SELECT COUNT(*) FROM entry WHERE item LIKE '자동차보험 (%'").fetchone()[0]
    check('나눠 적은 것 하나를 지우면 묶음째 지울 수 있음 → 12건 모두 휴지통', left == 0 and TR.count(w.con, w.lid) == 12,
          f'{left} {TR.count(w.con, w.lid)}')
    lp.all_chk.setChecked(False)

    print('휴지통')
    check("[휴지통 12] 단추", lp.trash_btn.text() == '휴지통 12', lp.trash_btn.text())

    def restore_two(d):
        shot('basic_휴지통', d)
        d.table.selectRow(0)
        d.restore()
        return TR.count(w.con, w.lid)
    box = in_dialog(restore_two)
    lp.open_trash()
    check('휴지통에서 되살리기', box.get('r') == 11 and w.con.execute(
        "SELECT COUNT(*) FROM entry WHERE item LIKE '자동차보험 (%'").fetchone()[0] == 1, str(box))

    print('예산 (전체 · 주간)')
    from gagyebu.ui.extras import BudgetDialog
    box = in_dialog(lambda d: (d.month_total.set_value(800000), d.week_total.set_value(150000), d._ok()), 'basic_예산정하기')
    BudgetDialog(lp, w.con, w.lid, T.year, T.month).exec()
    w.data_changed()
    flush()
    check('한 달 전체 예산·주간 예산 저장', M.total_budget(w.con, w.lid, f'{T:%Y-%m}') == 800000 and M.week_budget(w.con, w.lid) == 150000)
    bc = lp.budget
    check("예산 막대: '전체 예산' + 이번 주", bc.total_lbl.text().startswith('전체 예산') and bc.week.isVisible()
          and '이번 주' in bc.week_lbl.text(), bc.total_lbl.text()[:30])
    shot('basic_가계부_예산', lp.box_w)

    print('고정 수입·지출 (매주·매년)')
    rp = w.goto('RecurringPage')
    flush()
    texts = [rp.table.item(r, 0).text() for r in range(rp.table.rowCount())]
    check('표에 반복 주기 글 (매달 25일 · 매주 금요일)', '매달 25일' in texts and '매주 금요일' in texts, str(texts))
    rp.new()
    rp.item.setText('자동차세')
    rp.expense.set_value(250000)
    rp.code.set_code('60')
    rp.cycle.setCurrentIndex(rp.cycle.findData('Y:1'))
    rp.ymonth.setValue(6)
    rp.day.setValue(30)
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.No)
    from gagyebu.ui import recurring_page as RPG
    RPG.PendingDialog.exec = lambda self: 0      # 넣을 것 확인 창은 띄우지 않음
    rp.save()
    QMessageBox.question = staticmethod(lambda *a, **k: answer['q'])
    r = w.con.execute("SELECT * FROM recurring WHERE item='자동차세'").fetchone()
    check('매년 6월 30일 저장 (예전 판이 건너뛰게 end 막음)', r and r['cycle'] == 'Y' and r['ymonth'] == 6 and r['end'] == R.BLOCK_END,
          str(dict(r) if r else None))
    check('매주일 때 요일 칸, 매년일 때 월 칸이 보임', (rp.cycle.setCurrentIndex(rp.cycle.findData('W:1')) or
                                              (rp.wday.isVisibleTo(rp) and not rp.day.isVisibleTo(rp))))
    check("'이번 달 고정비 한눈에'", '고정 지출' in rp.fixed_lbl.text() and '남을 돈' in rp.fixed_lbl.text(), rp.fixed_lbl.text()[:60])
    shot('basic_고정')

    print('통계 탭')
    sp = w.goto('ReportsPage')
    names = [sp.tabs.tabText(i) for i in range(sp.tabs.count())]
    check('통계 탭에 주별·저축·결제수단', all(n in names for n in ('주별', '저축', '결제수단')), str(names))
    sp.tabs.setCurrentWidget(sp.t_week)
    flush()
    check('주별: 그 달을 주로 나눔', sp.t_week.table.rowCount() >= 4)
    shot('basic_통계_주별')
    sp.tabs.setCurrentWidget(sp.t_pay)
    flush()
    labs = [sp.t_pay.table.item(r, 0).text() for r in range(sp.t_pay.table.rowCount())]
    check('결제수단별: 신한 Deep Dream · 현금 · 미지정은 맨 뒤', '신한 Deep Dream' in labs and '현금' in labs, str(labs))
    check('카드 실적 (목표 30만원)', '카드 실적' in sp.t_pay.perf.text() and '300,000' in sp.t_pay.perf.text(), sp.t_pay.perf.text()[:60])
    shot('basic_통계_결제수단')
    sp.tabs.setCurrentWidget(sp.t_save)
    flush()
    check('저축: 12달 + 합계', sp.t_save.table.rowCount() == 13)
    shot('basic_통계_저축')
    sp.tabs.setCurrentWidget(sp.t_month)
    flush()
    labels = [sp.t_month.view.table.item(r, 1).text() for r in range(sp.t_month.view.table.rowCount())
              if sp.t_month.view.table.item(r, 1)]
    check('월별 통계 세부 카테고리에도 그림', any(t.startswith('🍜') for t in labels), str(labels[:4]))
    sp.tabs.setCurrentWidget(sp.t_insight)
    flush()
    txt = sp.t_insight.view.toPlainText()
    check('이달 리포트에 고정 수입·지출 · 카드 실적', '고정 수입·지출' in txt and '카드 실적' in txt)

    print('달력: 결제일·고정')
    cp = w.goto('CalendarPage')
    flush()
    cells = ' '.join(cp.grid.cellWidget(r, c).text() for r in range(6) for c in range(7))
    check('달력에 🔁 고정 수입·지출 (월세)', '🔁' in cells and '월세' in cells)
    shot('basic_달력')
    cp.nav.shift(1)                               # 이번 달 산 할부는 다음 달 14일에 결제
    flush()
    cells = ' '.join(cp.grid.cellWidget(r, c).text() for r in range(6) for c in range(7))
    check('다음 달 달력에 💳 카드 결제 (신한 Deep Dream)', '💳' in cells and 'Deep' in cells, cells.count('💳'))
    shot('basic_달력_다음달')
    cp.nav.this_month()

    print('자산: 카드 실적 칸')
    ap = w.goto('AssetsPage')
    ap.tabs.setCurrentWidget(ap.card_tab)
    flush()
    cl = ap.card_tab.list
    perf = [cl.item(r, 6).text() for r in range(cl.rowCount())]
    check("카드 목록 '이번 달 실적' 칸 (14,500 / 300,000)", cl.horizontalHeaderItem(6).text() == '이번 달 실적'
          and any('300,000' in p for p in perf), str(perf))
    shot('basic_자산_카드', ap)

    print('설정: 결제수단 · 카테고리 그림')
    st = w.goto('SettingsPage')
    from gagyebu.ui.money_ui import PayTab
    pt = next(p for p in st.parts if isinstance(p, PayTab))
    st.tabs.setCurrentWidget(pt)
    from PyQt6.QtWidgets import QInputDialog
    QInputDialog.getText = staticmethod(lambda *a, **k: ('지역화폐', True))
    pt.add()
    check('직접 만든 결제수단 추가', M.custom_pays(w.con) == ['지역화폐'])
    QInputDialog.getText = staticmethod(lambda *a, **k: ('온누리상품권', True))
    pt.list.setCurrentRow(0)
    pt.rename()
    check('이름 바꾸기', M.custom_pays(w.con) == ['온누리상품권'])
    shot('basic_설정_결제수단')
    st.tabs.setCurrentIndex(0)
    ct = st.parts[0]
    ct.refresh()
    for r in range(ct.gt.rowCount()):
        if ct.gt.item(r, 0).text() == '3':
            ct.gt.selectRow(r)
    ct.load_cats(sel='30')
    check('세부 카테고리 고름', ct.code() == '30', str(ct.code()))
    box = in_dialog(lambda d: d._pick('🥕'))
    ct.emoji_cat()
    check('세부 카테고리 그림 바꾸기', E.emoji_map(w.con, w.lid).get('30') == '🥕')

    print('검색: 결제수단')
    se = w.goto('SearchPage')
    se.pay.set_pay('cash')
    se.c_pay.setChecked(True)
    se.run()
    got = [se.table.item(r, 6).text() for r in range(se.table.rowCount())]
    want = w.con.execute("SELECT COUNT(*) FROM entry WHERE ledger_id=? AND pay='cash' AND date BETWEEN ? AND ?",
                         (w.lid, se.start.date_().isoformat(), se.end.date_().isoformat())).fetchone()[0] \
        if se.c_date.isChecked() else w.con.execute("SELECT COUNT(*) FROM entry WHERE ledger_id=? AND pay='cash'",
                                                    (w.lid,)).fetchone()[0]
    check('결제수단이 현금인 것만 (자료 파일과 건수 같음)', got and set(got) == {'현금'} and len(got) == want, f'{got} {want}')

    # 테마마다
    for th in TH.THEMES:
        TH.set_pref('theme', th)
        w.apply_theme()
        lp = w.goto('LedgerPage')
        flush()
        check(f'{th}: 가계부 가로 스크롤 없음', hscroll(lp) == 0, str(hscroll(lp)))
        shot(f'{th}_가계부')
        rp = w.goto('RecurringPage')
        flush()
        shot(f'{th}_고정')
        sp = w.goto('ReportsPage')
        sp.tabs.setCurrentWidget(sp.t_pay)
        flush()
        shot(f'{th}_통계_결제수단')
        cp = w.goto('CalendarPage')
        flush()
        shot(f'{th}_달력')
    TH.set_pref('theme', 'retro')
    w.apply_theme()
except Exception:
    traceback.print_exc()
    fails.append('예외')
if warned:
    print('  (경고창)', warned)
print('실패:', ', '.join(fails) if fails else '없음')
sys.exit(1 if fails else 0)
