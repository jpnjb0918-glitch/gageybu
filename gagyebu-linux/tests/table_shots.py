"""테마별 표 점검: 결산 보고서(5가지)·검색·자산·예약·설정·가계부 표를 테마마다 그려 PNG로 저장하고,
읽기 쉬운 모양(폭 채우기·0 흐리게·머리줄/소계/합계 구분·줄 높이)이 지켜지는지 확인한다.
사용: QT_QPA_PLATFORM=offscreen python3 tests/table_shots.py <출력폴더>"""
import datetime as dt
import os
import random
import sys
import tempfile
import traceback

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from PyQt6.QtWidgets import QApplication  # noqa: E402

from gagyebu import db  # noqa: E402
from gagyebu.services import assets as A  # noqa: E402
from gagyebu.services import ledger as L  # noqa: E402
from gagyebu.services import recurring as R  # noqa: E402
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
random.seed(5)
for back in range(0, 4):                       # 이번 달 + 지난 3달 (년결산·증감이 비지 않게)
    y, m = T.year, T.month - back
    while m < 1:
        y, m = y - 1, m + 12
    for k in range(30):
        d = dt.date(y, m, random.randint(1, 20 if back == 0 else 28))
        L.add_entry(con, lid, {'date': d, 'item': random.choice(['점심', '커피', '마트', '버스', '전기세', '책']),
                               'expense': random.choice([3000, 4500, 12000, 35000, 52000, 128000]),
                               'code': random.choice(exp_codes), 'memo': ''}, commit=False)
    L.add_entry(con, lid, {'date': dt.date(y, m, 1), 'item': '급여', 'income': 3200000, 'code': '00'}, commit=False)
L.add_entry(con, lid, {'date': T.replace(day=1), 'item': '환불', 'expense': -15000, 'code': exp_codes[1]}, commit=False)
con.commit()
RP.set_budget(con, lid, f'{T:%Y-%m}', exp_codes[0], 300000)
aid = A.save_account(con, 'bank', {'name': '생활비 통장', 'opening': 500000})
for k in range(8):
    A.add_tx(con, aid, {'date': T.replace(day=1) + dt.timedelta(days=k), 'summary': f'거래 {k + 1}',
                        'deposit': 100000 if k % 3 == 0 else 0, 'withdraw': 0 if k % 3 == 0 else 23000})
R.save_rule(con, lid, {'item': '월세', 'expense': 450000, 'code': exp_codes[0], 'day': 25, 'start': T.replace(day=1)})
con.commit()
con.close()

from gagyebu import theme as TH  # noqa: E402
from gagyebu.app import MainWindow  # noqa: E402
from gagyebu.ui import widgets as W  # noqa: E402

app = QApplication(sys.argv[:1])
TH.apply(app)
w = MainWindow(path)
w.resize(1360, 860)
w.show()
w.data_changed()
errors, notes = [], []


def shot(name):
    from PyQt6.QtCore import QEvent
    app.processEvents()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    app.processEvents()
    w.grab().save(os.path.join(out, name + '.png'))


def check(cond, msg):
    if not cond and not os.environ.get('NOCHECK'):     # NOCHECK=1: 고치기 전 모습만 찍을 때
        raise AssertionError(msg)


def fills(t, slack=4):
    """보이는 칸 폭의 합이 표 안쪽 폭을 (가로 스크롤이 없으면) 다 채우는지"""
    hh = t.horizontalHeader()
    used = sum(hh.sectionSize(c) for c in range(t.columnCount()) if not t.isColumnHidden(c))
    return used >= t.viewport().width() - slack or t.horizontalScrollBar().maximum() > 0


only = sys.argv[2:] or TH.THEMES
for th in only:
    try:
        TH.set_pref('theme', th)
        w.apply_theme()
        app.processEvents()
        tone = TH.tone(th)
        if th in ('retro', 'feed', 'timeline'):     # 미니홈피 색: 표 색을 미니홈피 테마와 하나로 (안드로이드판과도 같음)
            check(tone['subtotal_bg'] == '#fdf1e3' and tone['footer_bg'] == '#ece8f6' and tone['sep'].upper() == '#5CC6C6',
                  f'{th} 소계·합계·선 색 {tone}')
            if th != 'retro':
                check(TH.table_colors(th) == TH.MH_TABLE, f'{th} 머리줄·줄무늬 {TH.table_colors(th)}')
                qss = app.styleSheet()
                check('stop:0 #8FE6E6' in qss and 'alternate-background-color: #F0FBFA' in qss, f'{th} 스타일시트')
        rp = w.goto('ReportsPage')
        for i, name in enumerate(('월결산', '년결산', '일일결산', '사용자정의', '년예산')):
            rp.tabs.setCurrentIndex(i)
            app.processEvents()
            v = rp.tabs.currentWidget().view
            t = v.table
            check(fills(t), f'{th} {name}: 표가 폭을 다 채우지 않음')
            check(t.rowHeight(0) >= 26, f'{th} {name}: 줄 높이 {t.rowHeight(0)}')
            rows = v.report.rows
            # 0 은 흐린 색, 0 이 아닌 금액은 진한 색
            z = next(((r, c) for r, row in enumerate(rows) if row.kind == 'cat'
                      for c, val in enumerate(row.values) if val == 0), None)
            if z:
                fg = t.item(z[0], z[1] + 2).foreground().color().name()
                check(fg == getattr(W, 'ZERO_COLOR', W.INCOME_COLOR).name(), f'{th} {name}: 0 색 {fg}')
            if i == 0:
                shot(f'{th}_결산_{name}')
        lp = w.goto('LedgerPage')
        if th not in TH.SNS_THEMES:
            app.processEvents()
            check(lp.table.rowHeight(0) >= 26, f'{th} 가계부 줄 높이 {lp.table.rowHeight(0)}')
            shot(f'{th}_가계부')
        rp.tabs.setCurrentIndex(1)
        w.goto('ReportsPage')
        shot(f'{th}_결산_년결산')
        sp = w.goto('SearchPage')
        sp.c_date.setChecked(True)
        sp.start.set_date(T.replace(day=1) - dt.timedelta(days=40))
        sp.run()
        check(fills(sp.table), f'{th} 검색 표 폭')
        shot(f'{th}_검색')
        ap = w.goto('AssetsPage')
        ap.tabs.setCurrentIndex(0)
        app.processEvents()
        shot(f'{th}_자산')
        w.goto('RecurringPage')
        shot(f'{th}_예약')
        stp = w.goto('SettingsPage')
        stp.tabs.setCurrentIndex(0) if hasattr(stp, 'tabs') else None
        shot(f'{th}_설정_계정')
        print(f'OK {th}')
    except Exception:
        errors.append((th, traceback.format_exc()))

TH.set_pref('theme', 'retro')
w.apply_theme()
for th, tb in errors:
    print('FAIL', th, tb)
print('결과:', '통과' if not errors else f'실패 {len(errors)}')
sys.exit(1 if errors else 0)
