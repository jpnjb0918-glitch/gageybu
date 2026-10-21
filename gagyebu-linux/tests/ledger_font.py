"""기본 장부·장부 목록에서 새 장부 만들기·글자 크기(1px) 점검 (PC판).
사용: QT_QPA_PLATFORM=offscreen python3 tests/ledger_font.py <출력폴더>"""
import os
import sys
import tempfile
import traceback

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
out = sys.argv[1]
os.makedirs(out, exist_ok=True)
tmp = tempfile.mkdtemp()
os.environ['XDG_CONFIG_HOME'] = os.path.join(tmp, 'config')

from PyQt6.QtCore import QEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QDialog  # noqa: E402

from gagyebu import db  # noqa: E402
from gagyebu import theme as TH  # noqa: E402
from gagyebu.services import ledger as L  # noqa: E402

path = os.path.join(tmp, 'g.sqlite3')
con = db.connect(path)
db.set_meta(con, 'password', None)
con.commit()
con.close()

from gagyebu.app import MainWindow  # noqa: E402
from gagyebu.ui import widgets as W  # noqa: E402

app = QApplication(sys.argv[:1])
TH.apply(app)
fails = []
plan = []


def fake_run(dlg):
    return plan.pop(0)(dlg)


W.run_dialog = fake_run


def check(name, cond, extra=''):
    print(('  ✓ ' if cond else '  ✗ ') + name + (f'  ({extra})' if extra and not cond else ''))
    if not cond:
        fails.append(name)


def settle():
    for _ in range(3):
        app.processEvents()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


try:
    print('기본 장부')
    w = MainWindow(path)
    w.resize(1360, 860)
    w.show()
    settle()
    names = [r['name'] for r in L.ledgers(w.con)]
    check('처음 열면 기본 장부 4개가 더해짐', names == ['가계부 장부', '생활비 장부', '용돈 장부', '비상금 장부', '여행 장부'], str(names))
    first = L.first_ledger_id(w.con)
    ids = {r['name']: r['id'] for r in L.ledgers(w.con)}
    check('계정과목은 첫 장부에서 복사', all(L.category_map(w.con, ids[n]) == L.category_map(w.con, first) for n in L.DEFAULT_EXTRA_LEDGERS)
          and L.groups(w.con, ids['용돈 장부']) and len(L.categories(w.con, ids['용돈 장부'])) == len(L.categories(w.con, first)))
    check('자료 파일에 한 번 했다고 표시', db.get_meta(w.con, 'default_ledgers') == '1')
    L.delete_ledger(w.con, ids['여행 장부'])
    check('다시 불러도 지운 장부는 다시 안 생김', L.ensure_default_ledgers(w.con) == [] and '여행 장부' not in [r['name'] for r in L.ledgers(w.con)])
    c2 = db.connect(os.path.join(tmp, 'b.sqlite3'))
    L.add_ledger(c2, '생활비 장부', copy_from=L.first_ledger_id(c2), codes_only=True)
    added = L.ensure_default_ledgers(c2)
    n2 = [r['name'] for r in L.ledgers(c2)]
    check('같은 이름 장부가 이미 있으면 건너뜀', len(added) == 3 and n2.count('생활비 장부') == 1, str(n2))
    c2.close()

    print('장부 목록: 새 장부 만들기·장부 관리')
    w.reload_ledgers()
    cb = w.ledger_combo
    items = [(cb.itemText(i), cb.itemData(i)) for i in range(cb.count())]
    check('목록 끝에 [＋ 새 가계부 만들기…]·[가계부 관리…]', items[-2:] == [('＋ 새 가계부 만들기…', '__new'), ('가계부 관리…', '__manage')], str(items))
    shown = {}

    def fill(dlg):
        shown['title'] = dlg.windowTitle()
        shown['how'] = [dlg.w['how'].itemText(i) for i in range(dlg.w['how'].count())]
        shown['how_cur'] = dlg.w['how'].currentIndex()
        dlg.w['name'].setText('모임 장부')
        return QDialog.DialogCode.Accepted
    plan.append(fill)
    lid0 = w.lid
    cb.setCurrentIndex(cb.findData('__new'))
    w._ledger_selected(cb.currentIndex())
    settle()
    new = [r for r in L.ledgers(w.con) if r['name'] == '모임 장부']
    check('[＋ 새 장부 만들기…] → 이름·만드는 방법 창', shown.get('title') == '새 가계부' and len(shown.get('how', [])) == 3 and shown.get('how_cur') == 1, str(shown))
    check('새 장부가 생기고 그 장부로 바뀜', len(new) == 1 and w.lid == new[0]['id'] and cb.currentData() == new[0]['id'] and cb.currentText() == '모임 장부')
    check('기본 방법 = 지금 장부의 계정과목만 복사', new and L.category_map(w.con, new[0]['id']) == L.category_map(w.con, lid0)
          and w.con.execute('SELECT COUNT(*) FROM entry WHERE ledger_id=?', (new[0]['id'],)).fetchone()[0] == 0)
    plan.append(lambda dlg: QDialog.DialogCode.Rejected)
    n_before = len(L.ledgers(w.con))
    cb.setCurrentIndex(cb.findData('__new'))
    w._ledger_selected(cb.currentIndex())
    check('취소하면 아무것도 안 생기고 고른 칸은 지금 장부로', len(L.ledgers(w.con)) == n_before and cb.currentData() == w.lid)
    cb.setCurrentIndex(cb.findData('__manage'))
    w._ledger_selected(cb.currentIndex())
    settle()
    from gagyebu.ui.settings_page import LedgerTab
    sp = w.stack.currentWidget().widget()
    check('[장부 관리…] → 설정의 장부 관리 탭', type(sp).__name__ == 'SettingsPage' and isinstance(sp.tabs.currentWidget(), LedgerTab)
          and cb.currentData() == w.lid)
    w.grab().save(os.path.join(out, 'ledger-manage.png'))

    print('글자 크기 (1px)')
    from gagyebu.ui.settings_page import ThemeTab
    tt = next(p for p in sp.parts if isinstance(p, ThemeTab))
    sp.tabs.setCurrentWidget(tt)
    settle()
    base = QApplication.font().pixelSize()
    check('미니홈피 도트 글꼴 기본 12px', base == 12 and tt.fsize.value() == 12, str(base))
    tt.fsize.setValue(13)
    settle()
    check('1px 올리면 바로 13px', QApplication.font().pixelSize() == 13 and TH.font_px() == 13)
    tt.fsize.stepBy(5)
    settle()
    check('계속 1px씩 (18px)', QApplication.font().pixelSize() == 18 and tt.fsize.value() == 18)
    check('화면 글자에 실제로 적용 (메모 안내 글·장부 칸)', tt.note.fontInfo().pixelSize() == 18 and w.ledger_combo.fontInfo().pixelSize() == 18,
          f'{tt.note.fontInfo().pixelSize()} {w.ledger_combo.fontInfo().pixelSize()}')
    w.grab().save(os.path.join(out, 'font-18.png'))
    TH.set_pref('theme', 'feed')
    w.apply_theme()
    settle()
    check('다른 테마에서도 정한 크기', QApplication.font().pixelSize() == 18 and tt.note.fontInfo().pixelSize() == 18, str(tt.note.fontInfo().pixelSize()))
    TH.set_pref('theme', 'retro')
    w.apply_theme()
    sp.tabs.setCurrentWidget(tt)
    tt.refresh()
    tt._font_default()
    settle()
    check('[기본 크기] → 테마 기본(12px)으로', TH.font_px() == 0 and QApplication.font().pixelSize() == 12 and '기본' in tt.fsize_note.text()
          and tt.note.fontInfo().pixelSize() == 12, str(tt.note.fontInfo().pixelSize()))
    TH.set_pref('font_px', 99)
    check('범위 밖 값은 무시', TH.font_px() == 0)
    TH.set_pref('font_px', 0)
except Exception:
    traceback.print_exc()
    fails.append('예외')

print()
print('실패:', fails if fails else '없음')
sys.exit(1 if fails else 0)
