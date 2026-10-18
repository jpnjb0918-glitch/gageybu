"""화면 점검: 모든 화면을 띄워 PNG로 저장하고 주요 동작을 실행해 본다.
사용: QT_QPA_PLATFORM=offscreen python3 tests/gui_smoke.py <출력폴더> [원본mdb폴더]"""
import datetime as dt
import os
import sys
import tempfile
import traceback

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from PyQt6.QtWidgets import QApplication  # noqa: E402

from gagyebu import db  # noqa: E402
from gagyebu.services import assets as A  # noqa: E402
from gagyebu.services import calendar_svc as C  # noqa: E402
from gagyebu.services import importer as I  # noqa: E402
from gagyebu.services import ledger as L  # noqa: E402
from gagyebu.services import recurring as R  # noqa: E402
from gagyebu.services import reports as RP  # noqa: E402

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
tmp = tempfile.mkdtemp()
os.environ['XDG_CONFIG_HOME'] = os.path.join(tmp, 'config')   # 화면 꾸미기 설정을 실제 사용자 설정과 분리
path = os.path.join(tmp, 'g.sqlite3')
if len(sys.argv) > 2:
    print(I.import_folder(sys.argv[2], path).text())
con = db.connect(path)
db.set_meta(con, 'password', None)
lid = L.first_ledger_id(con)
T = dt.date.today()
cm = L.category_map(con, lid)
exp_codes = [c for c in cm if c[0] != '0']
import random  # noqa: E402
random.seed(7)
items = ['점심', '커피', '마트 장보기', '버스', '택시', '전기세', '휴대폰 요금', '학원비', '책', '영화']
for k in range(120):
    d = T - dt.timedelta(days=random.randint(0, 200))
    L.add_entry(con, lid, {'date': d, 'item': random.choice(items), 'expense': random.choice([3000, 4500, 12000, 35000, 52000]),
                           'code': random.choice(exp_codes)}, commit=False)
for m in range(7):
    y, mm = divmod(T.year * 12 + T.month - 1 - m, 12)
    L.add_entry(con, lid, {'date': dt.date(y, mm + 1, 10), 'item': '급여', 'income': 3200000, 'code': '00'}, commit=False)
con.commit()
RP.set_budget(con, lid, f'{T:%Y-%m}', exp_codes[0], 300000)
R.save_rule(con, lid, {'item': '월세', 'expense': 550000, 'code': exp_codes[-1], 'day': 25,
                       'start': T.replace(day=1) - dt.timedelta(days=40)})
bank = A.save_account(con, 'bank', {'company': '국민은행', 'name': '월급통장', 'owner': '홍길동', 'number': '123-45-678',
                                    'opening': 1500000, 'active': 1})
A.add_tx(con, bank, {'date': T, 'summary': '급여 입금', 'deposit': 3200000})
A.add_tx(con, bank, {'date': T, 'summary': '관리비', 'withdraw': 180000})
card = A.save_card(con, {'company': '신한카드', 'name': '생활카드', 'pay_day': 14, 'bill_from_month': -1,
                         'bill_from_day': 1, 'bill_to_month': -1, 'bill_to_day': 31, 'bank_account_id': bank})
A.add_card_purchase(con, card, T - dt.timedelta(days=35), '노트북', 1200000, months=6)
A.add_card_purchase(con, card, T - dt.timedelta(days=3), '마트', 85000)
A.save_account(con, 'securities', {'company': '키움증권', 'name': '주식계좌', 'valuation': 5300000, 'deposit': 120000})
A.save_account(con, 'insurance', {'company': '삼성생명', 'name': '실손보험', 'owner': '홍길동', 'x.status': '정상',
                                  'x.paid_total': 2400000, 'x.contract_date': '2020-03-01'})
A.save_account(con, 'property', {'name': '전세 보증금', 'valuation': 150000000, 'loan': 50000000, 'x.ptype': 1})
C.add_schedule(con, T, '병원 예약 10시', remind_days=1)
C.add_schedule(con, T + dt.timedelta(days=2), '스터디', repeat={'type': 'every', 'n': 1, 'unit': '주'},
               until=T + dt.timedelta(days=40))
C.simple_save(con, 'contact', {'name': '홍길동', 'mobile': '010-1234-5678', 'address': '서울시 용산구'})
C.simple_save(con, 'diary', {'date': T.isoformat(), 'weather': 1, 'title': '리눅스로 이사', 'content': '가계부를 옮겼다.'})
C.simple_save(con, 'memo', {'title': '장보기 목록', 'content': '우유\n계란', 'created': f'{dt.datetime.now():%Y-%m-%d %H:%M}', 'sort': 1})
con.commit()
con.close()

from gagyebu import theme as TH  # noqa: E402
from gagyebu.app import LoginDialog, MainWindow  # noqa: E402

app = QApplication(sys.argv[:1])
TH.apply(app)
assert TH.current() == ('retro', True), TH.current()          # 기본값: 미니홈피 + 도트 글꼴
lg = LoginDialog('x')
lg.show()
app.processEvents()
lg.grab().save(os.path.join(out, '00_암호창.png'))
lg.close()
w = MainWindow(path)
w.resize(1360, 860)
w.show()
w.data_changed()
errors = []


def shot(name):
    app.processEvents()
    w.grab().save(os.path.join(out, name + '.png'))


for i, p in enumerate(w.pages):
    try:
        w.nav.setCurrentRow(i)
        app.processEvents()
        shot(f'{i:02d}_{p.title}')
        if hasattr(p, 'tabs'):
            for k in range(1, p.tabs.count()):
                p.tabs.setCurrentIndex(k)
                app.processEvents()
                shot(f'{i:02d}_{p.title}_{k}_{p.tabs.tabText(k)}')
            p.tabs.setCurrentIndex(0)
    except Exception:
        errors.append((p.title, traceback.format_exc()))

# 동작 점검 ───────────────────────────────────────────
try:
    lp = w.goto('LedgerPage')
    n0 = w.con.execute('SELECT COUNT(*) FROM entry').fetchone()[0]
    lp.new()
    lp.form.item.setText('테스트 품목')
    lp.form.expense.setText('12,345')
    lp.form.code.set_code(exp_codes[0])
    lp.save()
    assert w.con.execute('SELECT COUNT(*) FROM entry').fetchone()[0] == n0 + 1, '내역 저장 실패'
    r = w.con.execute("SELECT * FROM entry WHERE item='테스트 품목'").fetchone()
    assert r['expense'] == 12345 and r['code'] == exp_codes[0]
    print('OK 가계부 저장')
    sp = w.goto('SearchPage')
    sp.c_text.setChecked(True)
    sp.text.setText('테스트')
    sp.run()
    assert sp.table.rowCount() == 1, sp.table.rowCount()
    shot('90_검색결과')
    print('OK 검색')
    ap = w.goto('AssetsPage')
    ap.tabs.setCurrentIndex(1)
    ct = ap.card_tab
    ct.refresh()
    ct.paid.setCurrentIndex(2)
    shot('91_카드')
    ids = [x['id'] for x in A.card_txs(w.con, card, None, 0)]
    A.pay_card(w.con, ids[:1], T, bank, lid, exp_codes[0])
    ap.refresh()
    print('OK 카드 결제', A.summary(w.con)['순자산'])
    rp = w.goto('ReportsPage')
    for k in range(5):
        rp.tabs.setCurrentIndex(k)
        app.processEvents()
        assert rp.tabs.currentWidget().view.table.rowCount() > 0, f'보고서 탭 {k} 비어 있음'
    print('OK 보고서 5종')
    gp = w.goto('GraphPage')
    gp.kind.setCurrentIndex(1)
    shot('92_막대그래프')
    from gagyebu.ui.recurring_page import PendingDialog
    due, later = R.pending(w.con, lid)
    dlg = PendingDialog(w, w.con, lid, due, later)
    dlg.show()
    app.processEvents()
    dlg.grab().save(os.path.join(out, '93_예약확인창.png'))
    from PyQt6.QtCore import Qt as _Qt
    month_start = T.replace(day=1)
    for k in range(dlg.t1.rowCount()):              # 이번 달 이전 것은 기본 체크 해제
        it = dlg.t1.item(k, 0)
        expect = _Qt.CheckState.Checked if due[k]['date'] >= month_start else _Qt.CheckState.Unchecked
        assert it.checkState() == expect, (due[k]['date'], it.checkState())
        it.setCheckState(_Qt.CheckState.Checked)     # 사용자가 모두 체크했다고 가정
    dlg.apply_checked()
    assert not R.pending(w.con, lid)[0], '예약 입력 후에도 남음'
    print(f'OK 예약 자동입력 {len(due)}건')
    from gagyebu.ui.calendar_page import AnniversaryDialog
    ad = AnniversaryDialog(w, w.con)
    ad.show()
    app.processEvents()
    ad.grab().save(os.path.join(out, '94_기념일.png'))
    from gagyebu.ui.widgets import FormDialog
    fd = FormDialog(w, '새 카드 만들기', A.CARD_FIELDS, {'pay_day': 14, 'bill_from_month': -1, 'bill_to_day': 31}, w.con)
    fd.show()
    app.processEvents()
    fd.grab().save(os.path.join(out, '95_카드입력창.png'))
    v = fd.values()
    assert v['bill_from_month'] == -1 and v['bank_account_id'] is None, v
    print('OK 입력창')
    # ── 검토에서 찾은 문제 재발 방지 ──
    import gagyebu.ui.ledger_page as LPmod
    msgs = []
    LPmod.error = lambda parent, text, title='오류': msgs.append(text)      # 알림창 대신 기록
    lp = w.goto('LedgerPage')
    lp.all_chk.setChecked(True)
    app.processEvents()
    # (1) 장부 1의 내역을 선택한 채 장부 2로 바꾸고 저장 → 장부 1 내역은 그대로, 장부 2에 새로 들어가야 함
    l2 = L.add_ledger(w.con, '모임 장부', copy_from=lid, codes_only=True)
    w.reload_ledgers()
    lp.table.selectRow(0)
    app.processEvents()
    victim = lp.editing
    before = dict(L.get_entry(w.con, victim))
    w.ledger_combo.setCurrentIndex(w.ledger_combo.findData(l2))
    w._ledger_selected(0)
    app.processEvents()
    assert lp.editing is None, '장부를 바꿨는데 수정 상태가 남음'
    lp.form.item.setText('회비')
    lp.form.expense.setText('1000')
    lp.save()
    assert dict(L.get_entry(w.con, victim)) == before, '다른 장부 내역이 덮어써짐'
    assert w.con.execute('SELECT COUNT(*) FROM entry WHERE ledger_id=?', (l2,)).fetchone()[0] == 1
    w.ledger_combo.setCurrentIndex(w.ledger_combo.findData(lid))
    w._ledger_selected(0)
    print('OK 장부 바꾼 뒤 저장해도 다른 장부를 덮어쓰지 않음')
    # (2) 계정 목록에 없는 코드의 내역을 메모만 고쳐 저장 → 코드 유지
    eid = L.add_entry(w.con, lid, {'date': T, 'item': '옛 자료', 'expense': 500, 'code': '9z'})
    lp.refresh()
    for k in range(lp.table.rowCount()):
        if lp.table.item(k, 0).data(_Qt.ItemDataRole.UserRole) == eid:
            lp.table.selectRow(k)
    app.processEvents()
    assert lp.editing == eid
    lp.refresh()                                  # 수정 중 화면이 새로 그려져도
    lp.form.memo.setText('메모만 수정')
    lp.save()
    e = L.get_entry(w.con, eid)
    assert e['code'] == '9z' and e['memo'] == '메모만 수정', dict(e)
    print('OK 목록에 없는 계정코드 유지')
    # (3) 이상한 금액 → 오류 안내만, 프로그램은 계속
    lp.new()
    lp.form.item.setText('x')
    lp.form.expense.setText('inf')
    n_before = w.con.execute('SELECT COUNT(*) FROM entry').fetchone()[0]
    lp.save()
    assert msgs and w.con.execute('SELECT COUNT(*) FROM entry').fetchone()[0] == n_before
    print('OK 잘못된 금액(inf) 거부:', msgs[-1])
    from gagyebu.services import backup as B
    before = w.con.execute('SELECT COUNT(*) FROM entry').fetchone()[0]
    bk = B.backup(w.con, tmp)
    w.con.execute("DELETE FROM entry WHERE item='테스트 품목'")
    w.con.commit()
    try:
        w.replace_db(w.db_path)                  # 지금 쓰는 파일로 복원 시도 → 거부, 데이터 그대로
        raise AssertionError('같은 파일 복원이 거부되지 않음')
    except ValueError:
        pass
    assert w.con.execute('SELECT COUNT(*) FROM entry').fetchone()[0] == before - 1
    kept = w.replace_db(bk)
    assert w.con.execute('SELECT COUNT(*) FROM entry').fetchone()[0] == before
    w.goto('LedgerPage')
    print('OK 백업→복원(연결 교체)', os.path.basename(kept))
except Exception:
    errors.append(('동작 점검', traceback.format_exc()))

# ── 화면 꾸미기: 스티커·글꼴 파일, 테마 바꾸기 ──
try:
    sl = TH.sticker_list()
    assert len(sl) == 62 and all(os.path.exists(TH.sticker_path(x['id'])) for x in sl), len(sl)
    for cls, (sid, _sub) in TH.PAGE_DECOR.items():
        assert not TH.sticker_pixmap(sid, 46).isNull(), sid
    assert TH.load_fonts() == 'Galmuri11', TH.load_fonts()
    from gagyebu.ui.hompy import StickerPicker
    sp_ = StickerPicker(w, 'b16')
    sp_.show()
    app.processEvents()
    assert sp_.selected() == 'b16' and sp_.list.count() == 62
    sp_.grab().save(os.path.join(out, '96_미니미고르기.png'))
    sp_.close()
    w.goto('LedgerPage')
    w.profile.motto.setPlainText('커피는 하루 한 잔!')
    w.profile._save_motto()
    assert TH.pref('motto') == '커피는 하루 한 잔!' and '커피는 하루 한 잔!' in w.marquee.text
    shot('97_미니홈피_가계부')
    w.profile.set_hidden(True)
    shot('98_프로필접기')
    w.profile.set_hidden(False)
    TH.set_pref('font', 'system')
    w.apply_theme()
    assert TH.current() == ('retro', False)
    shot('99_미니홈피_시스템글꼴')
    TH.set_pref('theme', 'basic')
    w.apply_theme()
    assert TH.current()[0] == 'basic' and not w.profile.isVisible() and w.body.indexOf(w.navwrap) == 0
    shot('99_기본테마')
    TH.set_pref('theme', 'retro')
    TH.set_pref('font', 'pixel')
    w.apply_theme()
    assert w.profile.isVisible() and w.body.indexOf(w.navwrap) == 1
    print('OK 화면 꾸미기 (스티커 62개, 갈무리 글꼴, 테마 바꾸기·되돌리기)')
except Exception:
    errors.append(('화면 꾸미기', traceback.format_exc()))

for t, e in errors:
    print('FAIL', t, '\n', e)
print('화면 오류', len(errors), '건')
sys.exit(1 if errors else 0)
