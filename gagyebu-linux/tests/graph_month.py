"""그래프 종류 바꾸기·연월 바로 고르기 점검 (PC판). 창은 사람 대신 이 시험이 조작한다.
사용: QT_QPA_PLATFORM=offscreen python3 tests/graph_month.py <출력폴더>"""
import datetime as dt
import os
import sys
import tempfile
import traceback

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QEvent, Qt  # noqa: E402
from PyQt6.QtGui import QImage, QPainter  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QPushButton  # noqa: E402

from gagyebu import db  # noqa: E402
from gagyebu.services import ledger as L  # noqa: E402

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
tmp = tempfile.mkdtemp()
os.environ['XDG_CONFIG_HOME'] = os.path.join(tmp, 'config')
path = os.path.join(tmp, 'g.sqlite3')
con = db.connect(path)
db.set_meta(con, 'password', None)
lid = L.first_ledger_id(con)
T0 = dt.date.today()
Y = T0.year
inc = L.categories(con, lid, '0')[0]['code']
ex = [L.categories(con, lid, g)[0]['code'] for g in ('1', '3', '4', '5')]
for m in range(1, 11):
    L.add_entry(con, lid, {'date': dt.date(Y, m, 25), 'item': '월급', 'income': 2500000, 'code': inc})
    L.add_entry(con, lid, {'date': dt.date(Y, m, 3), 'item': '장보기', 'expense': 300000 + m * 20000, 'code': ex[0]})
    L.add_entry(con, lid, {'date': dt.date(Y, m, 10), 'item': '교통', 'expense': 150000, 'code': ex[1]})
    L.add_entry(con, lid, {'date': dt.date(Y, m, 15), 'item': '외식', 'expense': 80000 if m % 3 else 220000, 'code': ex[2]})
L.add_entry(con, lid, {'date': dt.date(Y, 4, 20), 'item': '환불', 'expense': -20000, 'code': ex[3]})
con.commit()
con.close()

from gagyebu import theme as TH  # noqa: E402
from gagyebu.app import MainWindow  # noqa: E402
from gagyebu.ui import graph_page as GP  # noqa: E402
from gagyebu.ui import widgets as W  # noqa: E402

app = QApplication(sys.argv[:1])
TH.apply(app)
w = MainWindow(path)
w.resize(1360, 860)
w.show()
w.data_changed()
fails = []
plan = []                # run_dialog 가 차례로 꺼내 쓰는 조작
seen = []                # 열린 창 기록


def fake_run(dlg):
    seen.append(dlg)
    plan.pop(0)(dlg)
    return 1


W.run_dialog = fake_run


def check(name, cond, extra=''):
    print(('  ✓ ' if cond else '  ✗ ') + name + (f'  ({extra})' if extra and not cond else ''))
    if not cond:
        fails.append(name)


def settle():
    for _ in range(3):
        app.processEvents()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def legend_of(chart):
    """그림을 그려 보고 범례(이름, 글) 목록을 돌려받음"""
    img = QImage(chart.width(), chart.height(), QImage.Format.Format_ARGB32)
    p = QPainter(img)
    tn = TH.tone()
    box = (80, 40, chart.width() - min(240, max(130, chart.width() // 5)) - 10, chart.height() - 40)
    import PyQt6.QtGui as G
    cols = {n: G.QColor(GP.PALETTE[i % len(GP.PALETTE)]) for i, n in enumerate(chart.series)}
    fn = {'pie': chart._pie, 'donut': chart._pie, 'hbar': chart._hbar}.get(chart.kind, chart._xy)
    r = fn(p, tn, box, cols)
    p.end()
    return r


def by_text(dlg, text):
    return next(b for b in dlg.findChildren(QPushButton) if b.text() == text)


try:
    # ── 그래프 종류 ──
    print('그래프 종류')
    gp = w.goto('GraphPage')
    settle()
    keys = [gp.kind.itemData(i) for i in range(gp.kind.count())]
    check('종류 8가지 (열쇠가 안드로이드판과 같음)', keys == ['line', 'bar', 'stack', 'area', 'cum', 'hbar', 'pie', 'donut'], str(keys))
    check('처음은 꺾은선', gp.kind.currentData() == 'line')
    check('대분류 전체 = 수입+지출 4개 이상', len([1 for v in gp.chart.series.values() if any(v)]) == 5, str(list(gp.chart.series)))
    for i, k in enumerate(keys):
        gp.kind.setCurrentIndex(i)
        settle()
        saved = TH.settings().value('graph_kind')
        check(f'{k}: 그림 종류 바뀜·이 컴퓨터에 기억', gp.chart.kind == k and saved == (None if k == 'line' else k), f'{gp.chart.kind} {saved}')
        img = gp.chart.grab().toImage()
        colors = {img.pixel(x, y) for x in range(0, img.width(), 7) for y in range(0, img.height(), 7)}
        check(f'{k}: 그려짐 (색 여러 가지)', len(colors) > 8, str(len(colors)))
        gp.chart.grab().save(os.path.join(out, f'retro-{k}.png'))
        leg = legend_of(gp.chart)
        if k in ('pie', 'donut'):
            pcts = [float(t.split()[-1].rstrip('%')) for _, t in leg]
            check(f'{k}: 0보다 큰 4개 항목, 비율 합 100%', len(pcts) == 4 and abs(sum(pcts) - 100) < 0.2, str(leg))
            cx = int((10 + (gp.chart.width() - min(240, max(130, gp.chart.width() // 5)) - 10)) / 2)
            cy = int(gp.chart.height() / 2) - 8 + 20      # 가운데에서 조금 아래 (조각 경계선 피함)
            centre = img.pixelColor(cx, cy).name()
            bg = TH.tone()['chart_bg'].lower()
            check(f'{k}: 가운데가 {"비어 있음" if k == "donut" else "칠해짐"}', (centre == bg) == (k == 'donut'), f'{centre} vs {bg}')
        elif k == 'hbar':
            tots = [int(t.split()[-1].replace(',', '')) for _, t in leg]
            check('가로 막대: 합계 큰 것부터 5개', tots == sorted(tots, reverse=True) and len(tots) == 5, str(tots))
        elif k == 'cum':
            ends = {n: int(t.split()[-1].replace(',', '')) for n, t in leg}
            sums = {n: sum(v) for n, v in gp.chart.series.items()}
            check('누계: 마지막 값 = 1년 합계', ends == sums, f'{ends} / {sums}')
        else:
            check(f'{k}: 범례 = 항목 수', len(leg) == len(gp.chart.series))
    gp.kind.setCurrentIndex(keys.index('donut'))
    gp2 = GP.GraphPage(w)
    check('새로 열어도 도넛 (기억)', gp2.kind.currentData() == 'donut')
    gp2.deleteLater()
    gp.kind.setCurrentIndex(keys.index('hbar'))
    gp.monthly.setChecked(True)
    gp.month.setCurrentIndex(2)
    settle()
    check('월단위 달은 목록에서 바로 고름 (3월)', ' 3월 ' in gp.chart.title and len(gp.chart.labels) == 31, gp.chart.title)
    gp.monthly.setChecked(False)
    gp.kind.setCurrentIndex(keys.index('stack'))
    settle()

    # SNS 어두운 테마에서도 그림
    TH.set_pref('theme', 'timeline_dark')
    w.apply_theme()
    settle()
    for k in ('stack', 'hbar', 'donut', 'area'):
        gp.kind.setCurrentIndex(keys.index(k))
        settle()
        gp.chart.grab().save(os.path.join(out, f'dark-{k}.png'))
    TH.set_pref('theme', 'retro')
    w.apply_theme()
    settle()

    # ── 연·월 바로 고르기 ──
    print('연·월 고르기')
    lp = w.goto('LedgerPage')
    settle()
    nav = lp.nav
    check('가운데 글자에 ▼ (누를 수 있다는 표시)', nav.lbl.text().startswith(f'{Y}년 {T0.month}월<') and '▼' in nav.lbl.text(), nav.lbl.text())
    got = {}

    def pick_2019_3(dlg):
        got['title'] = dlg.windowTitle()
        got['checked0'] = [b.isChecked() for b in dlg.month_btns]
        got['bold0'] = [b.font().bold() for b in dlg.month_btns]
        dlg.year.setValue(Y - 7)
        got['checked1'] = [b.isChecked() for b in dlg.month_btns]
        dlg.month_btns[2].click()

    plan.append(pick_2019_3)
    QTest.mouseClick(nav.lbl, Qt.MouseButton.LeftButton)
    settle()
    check('글자를 누르면 고르기 창', got.get('title') == '연·월 고르기', str(got.get('title')))
    check('지금 보는 달이 눌린 모양', got['checked0'] == [i + 1 == T0.month for i in range(12)], str(got['checked0']))
    check('오늘이 있는 달은 굵게', got['bold0'] == [i + 1 == T0.month for i in range(12)])
    check('다른 해로 바꾸면 눌린 달 없음', not any(got['checked1']))
    check(f'{Y - 7}년 3월로 이동', (nav.y, nav.m) == (Y - 7, 3) and nav.lbl.text().startswith(f'{Y - 7}년 3월<'), nav.lbl.text())
    rows = lp.table.rowCount() if hasattr(lp, 'table') else None
    nav.shift(1)
    check('▶ 는 그대로 한 달씩', (nav.y, nav.m) == (Y - 7, 4))
    plan.append(lambda dlg: by_text(dlg, '이번 달').click())
    nav.lbl.setFocus()
    QTest.keyClick(nav.lbl, Qt.Key.Key_Return)
    settle()
    check('Enter 로도 열리고, 이번 달 단추로 오늘 달', (nav.y, nav.m) == (Y, T0.month), f'{nav.y}-{nav.m}')
    plan.append(lambda dlg: (dlg.year.setValue(2001), by_text(dlg, '닫기').click()))
    QTest.mouseClick(nav.lbl, Qt.MouseButton.LeftButton)
    settle()
    check('닫기는 그대로', (nav.y, nav.m) == (Y, T0.month))
    plan.append(lambda dlg: (by_text(dlg, '◀').click(), by_text(dlg, '◀').click(), dlg.month_btns[11].click()))
    QTest.mouseClick(nav.lbl, Qt.MouseButton.LeftButton)
    settle()
    check('창 안 ◀ 로 해 넘기기', (nav.y, nav.m) == (Y - 2, 12), f'{nav.y}-{nav.m}')
    nav.this_month()

    # 다른 화면의 달 이동도 같은 창
    for name, get in (('CalendarPage', lambda p: p.nav), ('DiaryPage', lambda p: p.nav),
                      ('ReportsPage', lambda p: p.m_nav), ('ReportsPage', lambda p: p.d_nav)):
        pg = w.goto(name)
        settle()
        n = get(pg)
        hit = []
        n.changed.connect(lambda y, m: hit.append((y, m)))
        plan.append(lambda dlg: (dlg.year.setValue(2020), dlg.month_btns[4].click()))
        QTest.mouseClick(n.lbl, Qt.MouseButton.LeftButton)
        settle()
        check(f'{name}: 2020년 5월로 (화면에 알림)', (n.y, n.m) == (2020, 5) and hit == [(2020, 5)], f'{n.y}-{n.m} {hit}')
        n.this_month()
    ap = w.goto('AssetsPage')
    settle()
    from gagyebu.ui.assets_page import CardTab
    ct = ap.findChild(CardTab)
    plan.append(lambda dlg: (dlg.year.setValue(2022), dlg.month_btns[0].click()))
    QTest.mouseClick(ct.nav.lbl, Qt.MouseButton.LeftButton)
    settle()
    check('자산 카드 달: 2022년 1월로', (ct.nav.y, ct.nav.m) == (2022, 1))
    check('창은 모두 시험이 조작한 것', len(plan) == 0 and all(isinstance(d, W.MonthPicker) for d in seen))

    # 창 모양 사진
    for th in ('retro', 'timeline_dark', 'basic'):
        TH.set_pref('theme', th)
        w.apply_theme()
        dlg = W.MonthPicker(w, Y, 3 if T0.month != 3 else 4)      # 보고 있는 달 ≠ 오늘 달 (두 표시가 다 보이게)
        dlg.show()
        settle()
        dlg.grab().save(os.path.join(out, f'picker-{th}.png'))
        dlg.close()
    TH.set_pref('theme', 'retro')
    w.apply_theme()
    lp = w.goto('LedgerPage')
    settle()
    w.grab().save(os.path.join(out, 'ledger-retro.png'))
except Exception:
    traceback.print_exc()
    fails.append('예외')

print()
print('실패:', fails if fails else '없음')
sys.exit(1 if fails else 0)
