"""1.8.0 점검: 설정 → 카테고리에서 세부 카테고리 지우기(안 쓴 것 / 옮기고 삭제 / 내역까지 삭제) · 카테고리 지우기,
그리고 바뀐 이름(카테고리·통계·고정 수입·지출·내용 …)이 화면에 나오는지. 테마마다 카테고리 화면을 PNG로 저장.
사용: QT_QPA_PLATFORM=offscreen python3 tests/category_delete.py <출력폴더>"""
import datetime as dt
import os
import sys
import tempfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication, QGroupBox, QLabel, QMessageBox, QPushButton  # noqa: E402

from gagyebu import db  # noqa: E402
from gagyebu.services import ledger as L  # noqa: E402
from gagyebu.services import recurring as R  # noqa: E402
from gagyebu.services import reports as RP  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp()
os.makedirs(out, exist_ok=True)
tmp = tempfile.mkdtemp()
os.environ['XDG_CONFIG_HOME'] = os.path.join(tmp, 'config')
path = os.path.join(tmp, 'g.sqlite3')
con = db.connect(path)
db.set_meta(con, 'password', None)
lid = L.first_ledger_id(con)
T = dt.date.today()
# 시험용 카테고리 'x' (세부: x1 안 씀, x2 내역 2건·고정 1건·예산, x3 내역 1건)
L.set_group(con, lid, 'x', '시험')
for c, n in (('x1', '안씀'), ('x2', '옮길것'), ('x3', '다지울것')):
    L.set_category(con, lid, c, n)
for item, code in (('가', 'x2'), ('나', 'x2'), ('다', 'x3')):
    L.add_entry(con, lid, {'date': T, 'item': item, 'expense': 1000, 'code': code})
R.save_rule(con, lid, {'item': '고정', 'expense': 500, 'code': 'x2', 'day': 1, 'start': T, 'end': None, 'memo': ''})
RP.set_budgets(con, lid, [f'{T:%Y-%m}'], {'x2': 10000})
L.save_favorite(con, lid, {'item': '즐겨', 'expense': 1000, 'code': 'x2'})
con.close()

from gagyebu import theme as TH  # noqa: E402
from gagyebu.app import MainWindow  # noqa: E402
from gagyebu.ui import settings_page as SP  # noqa: E402

app = QApplication(sys.argv[:1])
TH.apply(app)
w = MainWindow(path)
w.resize(1360, 860)
w.show()
fails = []
asked = []


def check(name, cond, extra=''):
    print(('  ✓ ' if cond else '  ✗ ') + name + (f'  ({extra})' if extra and not cond else ''))
    if not cond:
        fails.append(name)


answer = {'q': True}
QMessageBox.question = staticmethod(lambda p, t, text, *a, **k: asked.append(text) or (
    QMessageBox.StandardButton.Yes if answer['q'] else QMessageBox.StandardButton.No))
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok)
warned = []
QMessageBox.warning = staticmethod(lambda p, t, text, *a, **k: warned.append(text) or QMessageBox.StandardButton.Ok)


def with_dialog(act):
    """다음에 뜨는 MoveCategoryDialog 안에서 act(dlg) 실행 (확인/취소는 act 가 함)"""
    def inside():
        dlg = app.activeModalWidget()
        if not isinstance(dlg, SP.MoveCategoryDialog):
            QTimer.singleShot(20, inside)
            return
        box['dlg'] = dlg
        box['label'] = ' '.join(lb.text() for lb in dlg.findChildren(QLabel))
        box['items'] = [dlg.combo.itemData(i) for i in range(dlg.combo.count())]
        dlg.grab().save(os.path.join(out, f'삭제창_{len(shots)}.png'))
        shots.append(1)
        act(dlg)
    box = {}
    QTimer.singleShot(30, inside)
    return box


shots = []
sp = w.goto('SettingsPage')
tab = sp.parts[0]
check("설정 첫 탭 이름 = '카테고리'", sp.tabs.tabText(0) == '카테고리', sp.tabs.tabText(0))
stabs = [sp.tabs.tabText(i) for i in range(sp.tabs.count())]
check('설정 탭: 가계부 관리 · 자주 쓴 내용', '가계부 관리' in stabs and '자주 쓴 내용' in stabs, str(stabs))
boxes = [b.title() for b in tab.findChildren(QGroupBox)]
check('카테고리 · 세부 카테고리 상자', boxes == ['카테고리', '세부 카테고리'], str(boxes))
for gb in tab.findChildren(QGroupBox):
    names = [b.text() for b in gb.findChildren(QPushButton)]
    check(f"'{gb.title()}'에 [추가][이름 바꾸기][삭제]", names[:3] == ['추가', '이름 바꾸기', '삭제'], str(names))


def select_group(g):
    tab.refresh()
    for r in range(tab.gt.rowCount()):
        if tab.gt.item(r, 0).text() == g:
            tab.gt.selectRow(r)
    app.processEvents()


def select_cat(c):
    for r in range(tab.ct.rowCount()):
        if tab.ct.item(r, 0).text() == c:
            tab.ct.selectRow(r)
    app.processEvents()


def cats():
    return [c['code'] for c in L.categories(w.con, w.lid, 'x')]


select_group('x')
check('세부 카테고리 표: 번호·세부 카테고리·내역 수', [tab.ct.horizontalHeaderItem(i).text() for i in range(3)] == ['번호', '세부 카테고리', '내역 수'])
w.grab().save(os.path.join(out, '카테고리_화면.png'))

# ① 안 쓴 것: 한 번 묻고 지움 (창 없음)
select_cat('x1')
asked.clear()
tab.del_cat()
check('안 쓴 세부 카테고리: 한 번 묻고 지움', 'x1' not in cats() and len(asked) == 1 and '안씀' in asked[0], str(asked))

# ② 쓴 것 → 옮기고 삭제: 같은 쪽(지출)이 먼저, 내역·고정·예산·자주 쓰는 내역이 따라감
select_group('x')
select_cat('x2')
asked.clear()
box = with_dialog(lambda d: (d.combo.setCurrentIndex(d.combo.findData('31')), d._ok()))
tab.del_cat()
check('쓴 세부 카테고리: 옮기기/삭제 창이 뜸', 'dlg' in box)
check('창에 쓴 곳 수 (내역 2 · 고정 1 · 예산 1)', '내역 2건' in box.get('label', '') and '고정 수입·지출 1건' in box.get('label', '')
      and '예산 1건' in box.get('label', ''), box.get('label'))
check('옮길 곳 목록: 지출 쪽 먼저, 수입(0x)은 뒤', bool(box.get('items')) and not box['items'][0].startswith('0')
      and 'x2' not in box['items'], str(box.get('items', [])[:4]))
n31 = w.con.execute("SELECT COUNT(*) FROM entry WHERE ledger_id=? AND item IN ('가','나') AND code='31'", (w.lid,)).fetchone()[0]
check('옮기고 삭제: x2 없어지고 내역 2건은 31로', 'x2' not in cats() and n31 == 2, f'{cats()} {n31}')
check('고정 수입·지출도 31로', w.con.execute("SELECT code FROM recurring WHERE item='고정'").fetchone()[0] == '31')
check('자주 쓰는 내역도 31로', [f['code'] for f in L.favorites(w.con, w.lid) if f['item'] == '즐겨'] == ['31'])
check('옮길 때는 더 묻지 않음', asked == [], str(asked))

# ③ 쓴 것 → 내역까지 삭제: 한 번 더 묻고, '아니요'면 그대로
select_group('x')
select_cat('x3')
answer['q'] = False
box = with_dialog(lambda d: (d.r_del.setChecked(True), d._ok()))
tab.del_cat()
check("내역까지 삭제 → 다시 묻고 '아니요'면 그대로", 'x3' in cats() and len(asked) == 1 and '되돌릴 수 없습니다' in asked[0], str(asked))
check('내역까지 삭제를 고르면 옮길 곳 목록이 꺼짐', 'dlg' in box and not box['dlg'].combo.isEnabled())
answer['q'] = True
asked.clear()
select_cat('x3')
with_dialog(lambda d: (d.r_del.setChecked(True), d._ok()))
tab.del_cat()
left = w.con.execute("SELECT COUNT(*) FROM entry WHERE ledger_id=? AND item='다'", (w.lid,)).fetchone()[0]
check("'예'면 세부 카테고리와 내역 모두 지움", 'x3' not in cats() and left == 0, f'{cats()} {left}')

# ④ 취소하면 아무것도 안 바뀜
L.set_category(w.con, w.lid, 'x4', '취소시험')
L.add_entry(w.con, w.lid, {'date': T, 'item': '라', 'expense': 1000, 'code': 'x4'})
select_group('x')
select_cat('x4')
with_dialog(lambda d: d.reject())
tab.del_cat()
check('창에서 취소하면 그대로', 'x4' in cats())

# ⑤ 카테고리 삭제: 쓴 세부 카테고리가 있으면 이름을 알려 주고 멈춤 → 옮긴 뒤엔 함께 지움
L.set_category(w.con, w.lid, 'x5', '빈칸')
select_group('x')
warned.clear()
asked.clear()
tab.del_group()
check('쓴 세부 카테고리가 있으면 카테고리 삭제 멈춤 (이름 안내)', 'x' in L.group_map(w.con, w.lid)
      and bool(warned) and '취소시험' in warned[0], str(warned))
check('카테고리 삭제 물음에 안의 세부 카테고리 수', bool(asked) and '세부 카테고리 2개' in asked[0], str(asked))
L.merge_category(w.con, w.lid, 'x4', '31')
select_group('x')
warned.clear()
tab.del_group()
check('안 쓴 세부 카테고리뿐이면 카테고리와 함께 지움', 'x' not in L.group_map(w.con, w.lid) and cats() == [] and not warned,
      f'{L.group_map(w.con, w.lid).get("x")} {cats()} {warned}')

# ⑥ 바뀐 이름: 메뉴 · 통계 탭 · 가계부 표 머리
titles = [w.nav.item(i).text() for i in range(w.nav.count())]
for want in ('가계부', '검색', '통계', '그래프', '고정 수입·지출', '자산', '달력'):
    check(f"메뉴에 '{want}'", want in titles, str(titles))
for old in ('결산 보고서', '예약 설정', '자산관리', '일정관리', '검색하기', '그래프 분석'):
    check(f"메뉴에 예전 이름 '{old}' 없음", old not in titles)
rp = w.goto('ReportsPage')
tabs = [rp.tabs.tabText(i) for i in range(rp.tabs.count())]
check('통계 탭: 월별·연간·일별·기간·예산', [t for t in tabs if t in ('월별', '연간', '일별', '기간', '예산')]
      == ['월별', '연간', '일별', '기간', '예산'], str(tabs))
lp = w.goto('LedgerPage')
head = [lp.table.horizontalHeaderItem(i).text() for i in range(lp.table.columnCount())]
check('가계부 표 머리: 내용 · 카테고리', '내용' in head and '카테고리' in head and '품목' not in head, str(head))
check("단추 '새 내역' · '최신순'", lp.new_btn.text() == '새 내역' and lp.desc_chk.text() == '최신순')
check("맨 위 '가계부:' 이름표", w.ledger_lbl.text().strip() == '가계부:', w.ledger_lbl.text())

# 테마마다 카테고리 화면
for th in TH.THEMES:
    TH.set_pref('theme', th)
    w.apply_theme()
    sp = w.goto('SettingsPage')
    sp.tabs.setCurrentIndex(0)
    app.processEvents()
    w.grab().save(os.path.join(out, f'{th}_카테고리.png'))
TH.set_pref('theme', 'retro')
print('실패:', ', '.join(fails) if fails else '없음')
sys.exit(1 if fails else 0)
