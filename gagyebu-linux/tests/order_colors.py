"""순서 바꾸기·색 바꾸기 점검 (PC판). 창은 사람 대신 이 시험이 조작한다.
사용: QT_QPA_PLATFORM=offscreen python3 tests/order_colors.py <출력폴더>"""
import datetime as dt
import os
import sys
import tempfile
import traceback

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QEvent, QModelIndex  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from gagyebu import db  # noqa: E402
from gagyebu.services import calendar_svc as C  # noqa: E402
from gagyebu.services import ledger as L  # noqa: E402
from gagyebu.services import order as O  # noqa: E402

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
tmp = tempfile.mkdtemp()
os.environ['XDG_CONFIG_HOME'] = os.path.join(tmp, 'config')
path = os.path.join(tmp, 'g.sqlite3')
con = db.connect(path)
db.set_meta(con, 'password', None)
lid = L.first_ledger_id(con)
T0 = dt.date.today()
D1 = T0.replace(day=1)
for item, exp in (('아침 빵', 3000), ('점심', 9000), ('저녁', 12000)):
    L.add_entry(con, lid, {'date': D1, 'item': item, 'expense': exp, 'code': '31'})
L.add_entry(con, lid, {'date': D1, 'item': '용돈', 'income': 50000, 'code': '01'})
L.add_entry(con, lid, {'date': D1 + dt.timedelta(days=1), 'item': '버스', 'expense': 1500, 'code': '40'})
for n in ('홍길동', '김철수', '박영희'):
    C.simple_save(con, 'contact', {'name': n})
C.simple_save(con, 'diary', {'date': T0.isoformat(), 'title': '첫 일기', 'content': ''})
C.simple_save(con, 'diary', {'date': T0.isoformat(), 'title': '둘째 일기', 'content': ''})
for i, t in enumerate(('장보기', '할 일', '책')):
    C.simple_save(con, 'memo', {'title': t, 'content': '', 'created': '', 'sort': i + 1})
con.commit()
con.close()

from gagyebu import theme as TH  # noqa: E402
from gagyebu.app import MainWindow  # noqa: E402
from gagyebu.ui import widgets as W  # noqa: E402
from gagyebu.ui.settings_page import CategoryTab, ThemeTab  # noqa: E402

app = QApplication(sys.argv[:1])
TH.apply(app)
w = MainWindow(path)
w.resize(1360, 860)
w.show()
w.data_changed()
fails = []
plan = []                # run_dialog 가 차례로 꺼내 쓰는 조작


def fake_run(dlg):
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


def shot(name):
    settle()
    w.grab().save(os.path.join(out, name + '.png'))


def move_to_top(key):
    def f(dlg):
        ks = dlg.keys()
        dlg.list.setCurrentRow(ks.index(str(key)))
        dlg.move(-999)
        dlg._save()
    return f


try:
    lp = w.goto('LedgerPage')
    settle()
    print('[같은 날 내역 순서]')
    t = lp.table
    rows_d1 = [r for r in range(t.rowCount()) if t.item(r, 0).text() == D1.isoformat()]
    ids_before = [t.item(r, 0).data(W.ID_ROLE) for r in rows_d1]
    t.selectRow(rows_d1[0])
    settle()

    def drag_last_to_top(dlg):                      # 끌어다 놓기와 같은 동작: 모델에서 줄 옮기기
        n = dlg.list.count()
        dlg.list.model().moveRow(QModelIndex(), n - 1, QModelIndex(), 0)
        drag_last_to_top.keys = dlg.keys()
        drag_last_to_top.label0 = dlg.list.item(0).text()
        dlg._save()
    plan.append(drag_last_to_top)
    lp.day_order()
    settle()
    keys = [int(k) for k in drag_last_to_top.keys]
    check('끌어다 놓으면 순서가 바뀜', keys[0] == sorted(ids_before)[-1], str(keys))
    check('자료 파일에 그 날 순서 저장', O.day_orders(w.con, lid).get(D1.isoformat()) == keys, str(O.day_orders(w.con, lid)))
    shown = [t.item(r, 0).data(W.ID_ROLE) for r in range(t.rowCount()) if t.item(r, 0).text() == D1.isoformat()]
    check('목록이 정한 순서 (최근 것 위로 켜져 있어도)', shown == keys, f'{shown} vs {keys}')
    ewb = [r['id'] for r, _b in L.entries_with_balance(w.con, lid, D1, D1)]
    check('잔액 계산도 그 순서', ewb == keys, str(ewb))
    shot('01-ledger-day-order')
    t.selectRow([r for r in range(t.rowCount()) if t.item(r, 0).text() == D1.isoformat()][0])
    plan.append(lambda dlg: dlg._reset())
    lp.day_order()
    check('기본 순서로 → 저장값 지워짐', D1.isoformat() not in O.day_orders(w.con, lid))

    print('[메뉴 순서]')
    sp = w.goto('SettingsPage')
    tt = sp.findChild(ThemeTab)
    labels_seen = []

    def nav_plan(dlg):
        labels_seen.append(dlg.list.item(0).text())
        move_to_top('SettingsPage')(dlg)
    plan.append(nav_plan)
    tt.order_nav()
    settle()
    check('메뉴 첫 줄이 설정', w.nav.item(0).text() == '설정', w.nav.item(0).text())
    check('순서 창에 처음 화면 표시', '처음 화면' in labels_seen[0], labels_seen[0])
    w.nav.setCurrentRow(1)
    settle()
    check('메뉴 줄 ↔ 화면 연결이 맞음 (둘째 줄 = 가계부)', w.stack.currentWidget().widget() is w.pages[0])
    p = w.goto('MemoPage')
    check('이름으로 화면 찾기도 그대로', w.stack.currentWidget().widget() is p)
    shot('02-nav-settings-first')
    plan.append(lambda dlg: dlg._reset())
    tt.order_nav()
    check('메뉴 기본 순서로', w.nav.item(0).text() == '가계부')

    print('[가계부 화면 구성]')
    w.goto('SettingsPage')
    plan.append(move_to_top('table'))
    tt.order_layout()
    tt.side.setCurrentIndex(tt.side.findData('left'))
    lp = w.goto('LedgerPage')
    settle()
    check('내역 목록이 맨 위', lp.left_lay.itemAt(0).widget() is lp.table)
    check('입력 상자가 왼쪽', lp.split.widget(0) is lp.box_w)
    shot('03-ledger-layout')
    TH.set_ledger_layout(None)
    TH.set_input_side('right')
    w.data_changed()
    settle()
    check('되돌리면 원래 배치', lp.left_lay.itemAt(0).widget() is lp.parts['nav'] and lp.split.widget(0) is lp.left_w)

    print('[계정과목 순서]')
    w.goto('SettingsPage')
    ct = sp.findChild(CategoryTab)
    ct.refresh()
    plan.append(move_to_top('3'))
    ct.order_groups()
    check('대분류 3이 맨 앞', L.groups(w.con, lid)[0]['code'] == '3', str([g['code'] for g in L.groups(w.con, lid)]))
    for r in range(ct.gt.rowCount()):
        if ct.gt.item(r, 0).data(W.ID_ROLE) == '3':
            ct.gt.selectRow(r)
    cats3 = [c['code'] for c in L.categories(w.con, lid, '3')]
    plan.append(move_to_top(cats3[-1]))
    ct.order_cats()
    cats3b = [c['code'] for c in L.categories(w.con, lid, '3')]
    check('소분류 순서 저장', cats3b[0] == cats3[-1], f'{cats3} → {cats3b}')
    lp = w.goto('LedgerPage')
    combo = lp.form.code
    first_codes = [combo.itemData(i) for i in range(combo.count()) if combo.itemData(i)]
    check('입력할 때 고르는 목록도 그 순서', bool(first_codes) and (first_codes[0][:1] in ('3', '0')), str(first_codes[:4]))

    print('[주소록·일기·메모 순서]')
    ap = w.goto('AddressPage')
    names = lambda: [ap.table.item(r, 0).text() for r in range(ap.table.rowCount())]
    n0 = names()
    plan.append(move_to_top(ap.rows[-1]['id']))
    ap.order()
    check('주소록 순서 바뀜', names() == [n0[-1]] + n0[:-1], f'{n0} → {names()}')
    dp = w.goto('DiaryPage')
    d0 = [dp.list.item(r, 2).text() for r in range(dp.list.rowCount())]
    plan.append(move_to_top(dp.rows[-1]['id']))
    dp.order()
    d1 = [dp.list.item(r, 2).text() for r in range(dp.list.rowCount())]
    check('일기 순서 바뀜', d1 == d0[::-1], f'{d0} → {d1}')
    mp = w.goto('MemoPage')
    m0 = [mp.list.item(r, 0).text() for r in range(mp.list.rowCount())]
    mids = [mp.list.item(r, 0).data(W.ID_ROLE) for r in range(mp.list.rowCount())]
    plan.append(move_to_top(mids[-1]))
    mp.reorder()
    m1 = [mp.list.item(r, 0).text() for r in range(mp.list.rowCount())]
    check('메모 순서 바뀜 (sort 칸)', m1 == [m0[-1]] + m0[:-1], f'{m0} → {m1}')

    print('[색 바꾸기]')
    TH.set_pref('theme', 'feed')
    w.apply_theme()
    w.goto('SettingsPage')
    tt.refresh()
    W.pick_color = lambda parent, initial, title: '#00AA55'
    tt.pick_color('accent')
    check('포인트 색 저장 (이 테마만)', TH.custom_colors('feed') == {'accent': '#00AA55'}, str(TH.custom_colors('feed')))
    check('화면 스타일에 적용', '#00AA55' in app.styleSheet())
    check('견본 단추에 표시', tt.color_btns['accent'].text().startswith('#00AA55'))
    W.pick_color = lambda parent, initial, title: '#7B3FE4'
    tt.pick_color('out')
    check('지출 글자 색 → 표 색에도', W.EXPENSE_COLOR.name().upper() == '#7B3FE4', W.EXPENSE_COLOR.name())
    lp = w.goto('LedgerPage')
    shot('04-feed-custom')
    TH.set_pref('theme', 'timeline_dark')
    w.apply_theme()
    check('다른 테마는 원래 색', TH.sns_colors()['accent'] == TH.SNS['timeline_dark']['accent'])
    TH.set_custom_color('bg', '#101830')
    TH.set_custom_color('card', '#141C30')
    TH.set_custom_color('accent', '#FFB000')
    w.apply_theme()
    shot('05-dark-custom')
    check('어두운 카드면 어두운 테마로 계산', TH.sns_colors()['dark'] is True)
    TH.set_pref('theme', 'retro')
    TH.set_custom_color('bg', '#F3E6FF')
    w.apply_theme()
    check('미니홈피 밝은 바탕 → 제목 글자 진하게', TH.C['on_bg'] == '#1A1A1A' and TH.C['teal'] == '#F3E6FF', str(TH.C['on_bg']))
    shot('06-retro-custom')
    TH.set_pref('theme', 'basic')
    TH.set_custom_color('accent', '#E67E22')
    w.apply_theme()
    from PyQt6.QtGui import QPalette
    check('기본 테마도 포인트 색', app.palette().color(QPalette.ColorRole.Highlight).name().upper() == '#E67E22')
    w.goto('SettingsPage')
    tt.refresh()
    tt.reset_color(None)
    check('이 테마 색 모두 처음으로', TH.custom_colors('basic') == {})
    TH.set_pref('theme', 'retro')
    TH.set_custom_color(None, None)
    w.apply_theme()
    check('미니홈피 색 되돌리면 원래 C', TH.C['teal'] == TH.C_DEFAULT['teal'])
    shot('07-settings-theme-tab')
except Exception:
    fails.append(traceback.format_exc())
    print(traceback.format_exc())

print('결과:', '통과' if not fails else f'실패 {len(fails)}')
sys.exit(1 if fails else 0)
