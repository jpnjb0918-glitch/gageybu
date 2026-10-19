"""속도 재기 (가상 화면): 켜기·화면 전환·테마 바꾸기·많은 내역(기본 5년 × 하루 약 6건 ≈ 1만 건)에서 가계부·검색·결산·그래프.
사용: QT_QPA_PLATFORM=offscreen python3 tests/perf.py [내역 수] [--profile 이름]
  --profile 이름: 그 단계만 cProfile 로 재서 오래 걸린 함수 30개를 보여 줌"""
import cProfile
import datetime as dt
import os
import pstats
import random
import sys
import tempfile
import time

T_START = time.perf_counter()
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
args = [a for a in sys.argv[1:] if not a.startswith('--')]
N = int(args[0]) if args else 10000
PROF = sys.argv[sys.argv.index('--profile') + 1] if '--profile' in sys.argv else None

tmp = tempfile.mkdtemp()
os.environ['XDG_CONFIG_HOME'] = os.path.join(tmp, 'config')
from PyQt6.QtCore import QEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from gagyebu import db  # noqa: E402
from gagyebu.services import ledger as L  # noqa: E402

path = os.path.join(tmp, 'g.sqlite3')
con = db.connect(path)
db.set_meta(con, 'password', None)
lid = L.first_ledger_id(con)
cm = L.category_map(con, lid)
exp_codes = [c for c in cm if c[0] != '0']
random.seed(7)
today = dt.date.today()
start = today - dt.timedelta(days=int(N / 6))
items = ['점심', '커피', '마트 장보기', '버스', '전기세', '책', '영화', '택시', '약국', '편의점']
for k in range(N):
    d = start + dt.timedelta(days=random.randint(0, (today - start).days))
    L.add_entry(con, lid, {'date': d, 'item': random.choice(items), 'expense': random.choice([3000, 4500, 12000, 35000]),
                           'code': random.choice(exp_codes), 'memo': '메모' if k % 5 == 0 else ''}, commit=False)
con.commit()
con.close()
T_IMPORT0 = time.perf_counter()
from gagyebu import theme as TH  # noqa: E402
from gagyebu.app import MainWindow  # noqa: E402
T_IMPORT = time.perf_counter() - T_IMPORT0

app = QApplication(sys.argv[:1])
res = []


def settle():
    app.processEvents()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    app.processEvents()


def step(name, fn, repeat=1):
    """fn 을 재서 기록 (repeat 번 중 가장 빠른 값)"""
    best = None
    for _ in range(repeat):
        if PROF == name:
            pr = cProfile.Profile()
            pr.enable()
        t = time.perf_counter()
        fn()
        settle()
        el = time.perf_counter() - t
        if PROF == name:
            pr.disable()
            pstats.Stats(pr).sort_stats('cumulative').print_stats(30)
        best = el if best is None else min(best, el)
    res.append((name, best))
    return best


w = None


def make():
    global w
    TH.apply(app)
    w = MainWindow(path)
    w.resize(1360, 860)
    w.show()
    w.data_changed()


step('창 만들기·첫 화면', make)
for th in TH.THEMES:
    TH.set_pref('theme', th)
    step(f'테마 바꾸기 → {th}', w.apply_theme)
    lp = w.goto('LedgerPage')
    step(f'  가계부 이번 달 ({th})', lambda: lp.refresh(), 3)
    lp.all_chk.setChecked(True)
    step(f'  가계부 전체 기간 ({th})', lambda: lp.refresh(), 3)
    lp.all_chk.setChecked(False)
TH.set_pref('theme', 'retro')
w.apply_theme()
for page in ('SearchPage', 'ReportsPage', 'GraphPage', 'CalendarPage', 'AssetsPage', 'RecurringPage', 'SettingsPage'):
    step(f'화면 이동 → {page}', lambda p=page: w.goto(p))
sp = w.goto('SearchPage')
sp.c_date.setChecked(False)
step('검색 (조건 없이 전체)', sp.run, 3)
rp = w.goto('ReportsPage')
for i, nm in enumerate(('월결산', '년결산', '월별 일일결산', '사용자정의', '년예산')):
    rp.tabs.setCurrentIndex(i)
    step(f'결산 {nm}', rp.refresh, 3)
step('내역 하나 저장 후 전체 새로 고침 (data_changed)', w.data_changed, 3)

total = time.perf_counter() - T_START
print(f'\n내역 {N}건 · import {T_IMPORT:.2f}s')
for name, el in res:
    print(f'{el * 1000:8.0f} ms  {name}')
