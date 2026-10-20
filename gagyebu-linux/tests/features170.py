"""1.7.0 기능 화면 점검: 계산기 금액 칸 · 자주 쓰는 내역 · 문자 붙여넣기 · 사진 · 예산 막대/알림/예산 정하기 ·
통장끼리 이체 · 저축 목표 · 빌려준 돈/빌린 돈 · 이달 리포트 · 태그 · 달력 무지출 표시.
테마마다 화면을 PNG로 저장하고 동작을 확인한다.
사용: QT_QPA_PLATFORM=offscreen python3 tests/features170.py <출력폴더> [테마…]"""
import datetime as dt
import os
import sys
import tempfile
import traceback

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QEvent, QTimer, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from gagyebu import db  # noqa: E402
from gagyebu.services import assets as A  # noqa: E402
from gagyebu.services import attach as AT  # noqa: E402
from gagyebu.services import goals as G  # noqa: E402
from gagyebu.services import ledger as L  # noqa: E402
from gagyebu.services import reports as RP  # noqa: E402

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
tmp = tempfile.mkdtemp()
os.environ['XDG_CONFIG_HOME'] = os.path.join(tmp, 'config')
path = os.path.join(tmp, 'g.sqlite3')
con = db.connect(path)
db.set_meta(con, 'password', None)
lid = L.first_ledger_id(con)
T = dt.date.today()
ms = T.replace(day=1)
pm = (ms - dt.timedelta(days=1)).replace(day=1)
for i, (item, amt, code, memo) in enumerate([('장보기', 64000, '30', ''), ('점심', 9000, '31', '#회사'),
                                             ('버스', 1500, '40', ''), ('기차표', 59800, '40', '#여행 #부산'),
                                             ('숙소', 120000, '80', '#여행'), ('커피', 4500, '31', '')]):
    d = ms + dt.timedelta(days=min(i * 2, max(0, (T - ms).days - 2)))
    L.add_entry(con, lid, {'date': d, 'item': item, 'expense': amt, 'code': code, 'memo': memo}, commit=False)
for i in range(8):
    L.add_entry(con, lid, {'date': pm + dt.timedelta(days=i * 3), 'item': '장보기', 'expense': 31000, 'code': '30'},
                commit=False)
L.add_entry(con, lid, {'date': ms, 'item': '급여', 'income': 3200000, 'code': '00'}, commit=False)
con.commit()
ym = f'{T:%Y-%m}'
RP.set_budgets(con, lid, [ym], {'30': 150000, '31': 60000, '40': 70000, '80': 100000})
L.save_favorite(con, lid, {'item': '지하철', 'expense': 1500, 'code': '40'})
L.save_favorite(con, lid, {'item': '점심', 'expense': 9000, 'code': '31', 'memo': '#회사'})
b1 = A.save_account(con, 'bank', {'name': '월급통장', 'company': '국민', 'opening': 1500000})
b2 = A.save_account(con, 'bank', {'name': '비상금', 'company': '카카오', 'opening': 0})
g1 = G.save_goal(con, {'name': '여행 자금', 'target': 1200000, 'due': T + dt.timedelta(days=150)})
G.add_goal_tx(con, g1, T - dt.timedelta(days=30), 300000)
G.add_goal_tx(con, g1, T, 150000)
d1 = G.save_debt(con, {'kind': 'lend', 'person': '철수', 'amount': 50000, 'date': T - dt.timedelta(days=20),
                       'due': T - dt.timedelta(days=2)})
G.add_payment(con, d1, T - dt.timedelta(days=5), 20000)
G.save_debt(con, {'kind': 'borrow', 'person': '영희', 'amount': 30000, 'date': T - dt.timedelta(days=3)})
eid = con.execute("SELECT id FROM entry WHERE item='숙소'").fetchone()[0]
con.close()

from gagyebu import theme as TH  # noqa: E402
from gagyebu.app import MainWindow  # noqa: E402
from gagyebu.ui import extras as X  # noqa: E402

app = QApplication(sys.argv[:1])
TH.apply(app)


def jpeg(color, w=900, hgt=1200):
    img = QImage(w, hgt, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    p = QPainter(img)
    p.setPen(QColor('#333'))
    for k in range(0, hgt, 60):
        p.drawLine(40, k, w - 40, k)
    p.end()
    return X.image_bytes(img)


w = MainWindow(path)
w.resize(1360, 860)
w.show()
AT.add(w.con, eid, jpeg('#fff8e0'), '영수증.jpg')
w.data_changed()
errors = []


def flush():
    app.processEvents()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    app.processEvents()


def shot(name, widget=None):
    flush()
    (widget or w).grab().save(os.path.join(out, name + '.png'))


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def run_dialog(make, act, name):
    """창을 열고(exec) 그 안에서 act(dlg) 를 한 뒤 사진 찍고 닫음"""
    box = {}

    def inside():
        dlg = app.activeModalWidget()
        if dlg is None:
            QTimer.singleShot(30, inside)
            return
        try:
            box['r'] = act(dlg)
            dlg.resize(dlg.size())
            shot(name, dlg)
        except Exception:
            box['e'] = traceback.format_exc()
        if dlg.isVisible():
            dlg.reject()
    QTimer.singleShot(50, inside)
    make()
    if 'e' in box:
        raise AssertionError(box['e'])
    return box.get('r')


# 정보창(QMessageBox)은 바로 닫기
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: errors.append(('경고창', str(a[2] if len(a) > 2 else a))) or
                                   QMessageBox.StandardButton.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)

# ── 동작 (기본 테마 한 번) ──
try:
    TH.set_pref('theme', 'basic')
    w.apply_theme()
    lp = w.goto('LedgerPage')
    flush()
    # 계산기
    lp.form.expense.setText('12000+3500')
    lp.form.expense.editingFinished.emit()
    check(lp.form.expense.text() == '15,500' and lp.form.expense.value() == 15500, f'계산기 {lp.form.expense.text()}')
    # 자주 쓰는 내역
    fav = L.favorites(w.con, w.lid)[1]
    lp.use_favorite(fav)
    check(lp.form.item.text() == '점심' and lp.form.expense.value() == 9000 and lp.form.code.code() == '31', '자주 쓰는 내역 채우기')
    # 예산 알림: 외식 예산 60000 에 지금 13500 → 50000 더 쓰면 100% 넘음
    lp.form.expense.set_value(50000)
    n0 = w.con.execute('SELECT COUNT(*) FROM entry').fetchone()[0]
    lp.save()
    check(w.con.execute('SELECT COUNT(*) FROM entry').fetchone()[0] == n0 + 1, '저장')
    check('예산을 넘었어요' in lp.mode_lbl.text(), f'예산 알림: {lp.mode_lbl.text()}')
    check(lp.budget.isVisible() and '%' in lp.budget.total_lbl.text(), '예산 막대')
    shot('basic_가계부_예산알림')
    # 새 내역 + 사진 (저장할 때 함께)
    lp.new()
    lp.pending_photos.append((jpeg('#e0f0ff'), 'a.jpg'))
    lp.form.item.setText('문구점')
    lp.form.expense.set_value(3000)
    lp.save()
    e2 = w.con.execute("SELECT id FROM entry WHERE item='문구점'").fetchone()[0]
    check(AT.counts(w.con, [e2]) == {e2: 1}, '새 내역 사진 함께 저장')
    check(lp.photo_btn.text() == '사진', '저장 뒤 사진 단추 비움')
    # 사진 창 (이미 있는 내역)
    for r in range(lp.table.rowCount()):
        if lp.table.item(r, 1).text() == '숙소':
            lp.table.selectRow(r)
    check(lp.photo_btn.text() == '사진 1', f'사진 단추 {lp.photo_btn.text()}')
    check(not lp.table.item(lp.table.currentRow(), 1).icon().isNull(), '목록에 사진기 표시')
    run_dialog(lp.photos, lambda d: check(d.list.count() == 1, '사진 창 1장'), 'basic_사진')
    # 문자 붙여넣기
    QApplication.clipboard().setText(f'[Web발신]\n신한카드(1234)승인 홍*동 12,500원 일시불 {T:%m/%d} 08:41 스타벅스 누적345,600원\n\n'
                                     f'[Web발신]\n롯데카드 승인취소 홍*동 4,500원 {T:%m/%d} 09:10 커피빈\n\n'
                                     f'[Web발신]\nKB국민카드 홍*동 9,000원 {T:%m/%d} 12:10 점심')

    def sms(d):
        check(d.table.rowCount() == 3, f'문자 {d.table.rowCount()}건')
        check(all(d.table.item(r, 0).checkState() == Qt.CheckState.Checked for r in range(3)), '모두 체크')
        check(d.table.item(0, X.C_ITEM).text() == '스타벅스' and d.table.item(1, X.C_OUT).text() == '-4,500', '문자 읽기')
        shot('basic_문자붙여넣기', d)
        d._save()
        return d.saved
    lp.table.clearSelection()
    lp.new()
    n0 = w.con.execute('SELECT COUNT(*) FROM entry').fetchone()[0]
    run_dialog(lp.paste_sms, sms, 'basic_문자붙여넣기_저장')
    check(w.con.execute('SELECT COUNT(*) FROM entry').fetchone()[0] == n0 + 3, '문자 3건 저장')
    # 예산 정하기
    def bud(d):
        d.edits['30'].setText('200000')
        d.span.setCurrentIndex(d.span.count() - 1)     # 12달 동안
        d._ok()
    run_dialog(lp.budget.edit, bud, 'basic_예산정하기')
    nm = T.month % 12 + 1
    nxt = f'{T.year + (T.month == 12):04d}-{nm:02d}'
    check(RP.budgets(w.con, w.lid, nxt).get('30') == 200000, '예산 12달 같게')
    # 이체
    ap = w.goto('AssetsPage')
    ap.tabs.setCurrentIndex(0)

    def tr(d):
        d.amount.setText('100000')
        d._ok()
    run_dialog(ap.bank.transfer, tr, 'basic_이체')
    check((A.account_balance(w.con, b1), A.account_balance(w.con, b2)) == (1400000, 100000), '이체 잔액')
    # 저축 목표·빌려준 돈
    ap.tabs.setCurrentWidget(ap.goals)
    flush()
    check(ap.goals.list.rowCount() == 1 and '37%' in ap.goals.list.item(0, 4).text(), '저축 목표 표')
    ap.goals.amount.setText('50000')
    ap.goals.add_tx(1)
    check(G.goal_status(w.con, G.goals(w.con)[0])['saved'] == 500000, '모은 돈 기록')
    shot('basic_저축목표')
    ap.tabs.setCurrentWidget(ap.debts)
    flush()
    check(ap.debts.list.rowCount() == 2, '빌려준 돈 표')
    check(any(ap.debts.list.item(r, 7).text() == '기한 지남' for r in range(2)), '기한 지남 표시')
    shot('basic_빌려준돈')
    check('받을 돈 30,000' in ap.sum_lbl.text() and '갚을 돈 30,000' in ap.sum_lbl.text(), f'자산 요약 {ap.sum_lbl.text()}')
    # 결산 보고서: 이달 리포트·태그
    rp = w.goto('ReportsPage')
    rp.tabs.setCurrentWidget(rp.t_insight)
    flush()
    txt = rp.t_insight.view.toPlainText()
    check('썼어요' in txt and '많이 쓴 곳' in txt and '무지출' in txt, f'이달 리포트: {txt[:200]}')
    shot('basic_이달리포트')
    rp.tabs.setCurrentWidget(rp.t_tags)
    flush()
    tags = [rp.t_tags.table.item(r, 0).text() for r in range(rp.t_tags.table.rowCount())]
    check('#여행' in tags and '#회사' in tags, f'태그 {tags}')
    shot('basic_태그')
    # 달력 무지출
    cp = w.goto('CalendarPage')
    flush()
    if T.day > 1:
        check('무지출' in cp.ns_lbl.text(), f'달력 무지출 {cp.ns_lbl.text()}')
    shot('basic_달력')
    print('OK 동작')
except Exception:
    errors.append(('동작', traceback.format_exc()))

# ── 테마마다 화면 ──
only = sys.argv[2:] or TH.THEMES
for th in only:
    try:
        TH.set_pref('theme', th)
        w.apply_theme()
        lp = w.goto('LedgerPage')
        flush()
        check(lp.budget.isVisible(), f'{th} 예산 막대')
        shot(f'{th}_가계부')
        rp = w.goto('ReportsPage')
        rp.tabs.setCurrentWidget(rp.t_insight)
        shot(f'{th}_이달리포트')
        ap = w.goto('AssetsPage')
        ap.tabs.setCurrentWidget(ap.goals)
        shot(f'{th}_저축목표')
        run_dialog(lambda: X.SmsDialog(w, w.con, w.lid).exec(), lambda d: None, f'{th}_문자붙여넣기')
        print(f'OK {th}')
    except Exception:
        errors.append((th, traceback.format_exc()))

TH.set_pref('theme', 'retro')
w.apply_theme()
for th, tb in errors:
    print('FAIL', th, tb)
print('결과:', '통과' if not errors else f'실패 {len(errors)}')
sys.exit(1 if errors else 0)
