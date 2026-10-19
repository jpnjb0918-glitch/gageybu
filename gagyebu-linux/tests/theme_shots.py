"""테마별 화면 점검: 테마마다 모든 화면을 그려 PNG로 저장하고, 가계부 목록의 선택·수정·삭제가 그대로 되는지 확인한다.
사용: QT_QPA_PLATFORM=offscreen python3 tests/theme_shots.py <출력폴더>"""
import datetime as dt
import os
import random
import sys
import tempfile
import time
import traceback

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from PyQt6.QtWidgets import QApplication  # noqa: E402

from gagyebu import db  # noqa: E402
from gagyebu.services import calendar_svc as C  # noqa: E402
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
cm = L.category_map(con, lid)
exp_codes = [c for c in cm if c[0] != '0']
random.seed(3)
items = [('점심 김치찌개', '회사 앞'), ('커피', ''), ('마트 장보기 (채소·과일·우유·계란)', ''), ('버스', ''),
         ('전기세', '9월분'), ('휴대폰 요금', ''), ('책', '아주 긴 메모를 써 보면 줄이 어떻게 바뀌는지 확인하려고 일부러 길게 적은 메모'),
         ('영화', '친구랑')]
for k in range(40):
    d = T.replace(day=1) + dt.timedelta(days=random.randint(0, 20))
    it, memo = random.choice(items)
    L.add_entry(con, lid, {'date': d, 'item': it, 'expense': random.choice([3000, 4500, 12000, 35000, 52000]),
                           'code': random.choice(exp_codes), 'memo': memo}, commit=False)
L.add_entry(con, lid, {'date': T.replace(day=1), 'item': '급여', 'income': 3200000, 'code': '00', 'memo': '월급'}, commit=False)
con.commit()
RP.set_budget(con, lid, f'{T:%Y-%m}', exp_codes[0], 300000)
C.add_schedule(con, T, '병원 예약 10시', remind_days=1)
C.add_schedule(con, T + dt.timedelta(days=2), '스터디', bg='#FFE3EC')
con.commit()
con.close()

from gagyebu import theme as TH  # noqa: E402
from gagyebu.app import MainWindow  # noqa: E402
import gagyebu.ui.ledger_page as LPmod  # noqa: E402

LPmod.confirm = lambda *a, **k: True          # 삭제 확인 창 대신 '예'
app = QApplication(sys.argv[:1])
TH.apply(app)
w = MainWindow(path)
w.resize(1360, 860)
w.show()
w.data_changed()
errors = []


def shot(name):
    from PyQt6.QtCore import QEvent
    app.processEvents()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)    # 바뀐 칸 위젯 정리 (실제 앱은 이벤트 루프가 함)
    app.processEvents()
    w.grab().save(os.path.join(out, name + '.png'))


for th in TH.THEMES:
    try:
        TH.set_pref('theme', th)
        w.apply_theme()
        app.processEvents()
        lp = w.goto('LedgerPage')
        app.processEvents()
        shot(f'{th}_01_가계부')
        t = lp.table
        sns = th in TH.SNS_THEMES
        # 표 모양: SNS 테마면 품목 칸만 보이고 줄이 높음, 아니면 원래 표
        visible = [c for c in range(t.columnCount()) if not t.isColumnHidden(c)]
        assert visible == ([1] if sns else list(range(7))), (th, visible)
        assert (t.rowHeight(0) >= 60) == sns, (th, t.rowHeight(0))
        assert lp.stories.isVisible() == (TH.layout_of(th) == 'feed'), th
        # 한 줄 고르면 입력칸에 그 내역이 들어오는지 (수정 기능)
        t.clearSelection()
        t.selectRow(2)
        app.processEvents()
        e = L.get_entry(w.con, lp.editing)
        assert e and lp.form.item.text() == e['item'], (th, lp.editing)
        shot(f'{th}_02_가계부_선택')
        # 수정 저장
        lp.form.memo.setText(f'{th} 수정')
        lp.save()
        assert L.get_entry(w.con, e['id'])['memo'] == f'{th} 수정', th
        # 여러 줄 골라 삭제
        n0 = w.con.execute('SELECT COUNT(*) FROM entry').fetchone()[0]
        t.clearSelection()
        t.selectRow(0)
        from PyQt6.QtCore import QItemSelectionModel
        t.selectionModel().select(t.model().index(1, 1), QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        lp.delete()
        assert w.con.execute('SELECT COUNT(*) FROM entry').fetchone()[0] == n0 - 2, th
        # 전체 기간 (줄 높이 다시 계산) 시간
        t0 = time.time()
        lp.all_chk.setChecked(True)
        app.processEvents()
        dt_all = time.time() - t0
        lp.all_chk.setChecked(False)
        # 다른 화면
        for i, p in enumerate(w.pages):
            if p.title in ('달력', '결산 보고서', '그래프 분석', '자산 관리', '환경 설정', '설정', '검색') or i in (2, 3, 5, 6, 10):
                w.nav.setCurrentRow(i)
                shot(f'{th}_{i:02d}_{p.title}')
        print(f'OK {th}: 칸 {visible}, 첫 줄 높이 {t.rowHeight(0)}, 선택·수정·여러 줄 삭제 정상, 전체 기간 {dt_all:.2f}초')
    except Exception:
        errors.append((th, traceback.format_exc()))

TH.set_pref('theme', 'retro')
w.apply_theme()
for th, tb in errors:
    print('FAIL', th, tb)
print('결과:', '통과' if not errors else f'실패 {len(errors)}')
sys.exit(1 if errors else 0)
