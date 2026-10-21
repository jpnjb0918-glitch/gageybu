"""피드·타임라인 화면(아이콘 누르기)·백업(구글 드라이브 폴더·다른 곳·보내기)·추가 글꼴 점검 (PC판).
사용: QT_QPA_PLATFORM=offscreen python3 tests/sns_backup_font.py <출력폴더>"""
import datetime as dt
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
os.environ['HOME'] = tmp                                   # 구글 드라이브 폴더 찾기를 시험용 집 폴더에서
os.makedirs(os.path.join(tmp, 'Google Drive'))

from PyQt6.QtCore import QEvent, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from gagyebu import db  # noqa: E402
from gagyebu import theme as TH  # noqa: E402
from gagyebu.services import backup as B  # noqa: E402
from gagyebu.services import ledger as L  # noqa: E402
from gagyebu.services import catemoji as E  # noqa: E402

path = os.path.join(tmp, 'g.sqlite3')
con = db.connect(path)
db.set_meta(con, 'password', None)
lid = L.first_ledger_id(con)
T = dt.date.today()
cm = L.category_map(con, lid)
exp_codes = sorted(c for c in cm if c[0] != '0')
for k, (it, amt, memo) in enumerate([('점심', 9000, '회사 앞'), ('커피', 4500, ''), ('마트', 52000, '장보기'), ('버스', 1500, ''),
                                      ('책', 18000, '아주 긴 메모를 써 보면 줄이 어떻게 바뀌는지 확인하려고 일부러 길게 적은 메모')]):
    L.add_entry(con, lid, {'date': T.replace(day=1) + dt.timedelta(days=k // 2), 'item': it, 'expense': amt,
                           'code': exp_codes[k % 3], 'memo': memo}, commit=False)
L.add_entry(con, lid, {'date': T.replace(day=1), 'item': '급여', 'income': 3200000, 'code': '00', 'memo': ''}, commit=False)
con.commit()
con.close()

from gagyebu.app import MainWindow  # noqa: E402
import gagyebu.ui.settings_page as SPmod  # noqa: E402
import gagyebu.ui.ledger_page as LPmod  # noqa: E402

app = QApplication(sys.argv[:1])
TH.apply(app)
msgs = []
SPmod.info = lambda _p, m: msgs.append(m)
SPmod.error = lambda _p, m: msgs.append('ERR ' + m)
SPmod.confirm = lambda *a, **k: True
SPmod.QDesktopServices.openUrl = staticmethod(lambda u: msgs.append('OPEN ' + u.toLocalFile()) or True)
LPmod.info = lambda _p, m: msgs.append(m)
fails = []


def check(name, cond, extra=''):
    print(('  ✓ ' if cond else '  ✗ ') + name + (f'  ({extra})' if extra and not cond else ''))
    if not cond:
        fails.append(name)


def settle():
    for _ in range(3):
        app.processEvents()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def first_hit(lp, what):
    """그려진 표에서 그 아이콘 자리 (줄, 가운데 점)"""
    lp.table.viewport().grab()
    for row, hits in sorted(lp.sns_delegate.hits.items()):
        for r, w, _v in hits:
            if w == what:
                return row, r.center().toPoint()
    return None, None


try:
    w = MainWindow(path)
    w.resize(1360, 860)
    w.show()
    w.data_changed()
    settle()

    print('피드 (사진 SNS 모양)')
    TH.set_pref('theme', 'feed')
    w.apply_theme()
    lp = w.goto('LedgerPage')
    settle()
    check('왼쪽 줄: 로고·아이콘 메뉴·새 내역·장부 고르기·내 프로필', w.rail_logo.isVisible() and w.rail_create.isVisible()
          and w.rail_ledger.isVisible() and w.rail_chip.isVisible() and not w.nav.item(0).icon().isNull()
          and w.ledger_combo.parent() is w.rail_ledger)
    check('맨 위 미니홈피 줄 숨김, 가계부 화면은 제목 띠 없이 프로필 머리', not w.hompy_title.isVisible() and not w.sns_title.isVisible()
          and lp.sns_prof.isVisible() and lp.sns_hl.isVisible())
    w.grab().save(os.path.join(out, 'feed.png'))
    row, pt = first_hit(lp, 'add')
    d0 = lp.table.item(row, 0).text()
    QTest.mouseClick(lp.table.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pt)
    settle()
    check('게시물의 💬 아이콘 → 그 날짜로 새 내역 입력', lp.editing is None and lp.form.date.date_().isoformat() == d0, d0)
    row, pt = first_hit(lp, 'cal')
    QTest.mouseClick(lp.table.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pt)
    settle()
    cp = w.stack.currentWidget().widget()
    check('게시물의 📅 아이콘 → 일정관리에서 그 날', type(cp).__name__ == 'CalendarPage' and cp.sel.isoformat() == d0)
    lp = w.goto('LedgerPage')
    settle()
    asked = []
    LPmod.ask_order = lambda *a, **k: (asked.append(a[1]) or ('cancel', []))
    row, pt = first_hit(lp, 'order')
    QTest.mouseClick(lp.table.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pt)
    settle()
    check('게시물의 ⇅ 아이콘 → 그 날 순서 창', bool(asked) and asked[0].endswith('내역 순서'), str(asked))
    n_before = lp.table.rowCount()
    lp.sns_tabs.clicked.emit('all')
    settle()
    check('탭 [전체 기간] → 전체 기간 보기', lp.all_chk.isChecked())
    lp.sns_tabs.clicked.emit('month')
    lp.sns_tabs.clicked.emit('desc')
    settle()
    check('탭 [최근 것 위로] → 정렬 바뀜', not lp.desc_chk.isChecked() and lp.table.rowCount() == n_before)
    lp.desc_chk.setChecked(True)
    code = lp.sns_hl.items[0][0]
    lp.sns_hl.code_clicked.emit(code)
    settle()
    sp = w.stack.currentWidget().widget()
    labels = {sp.table.item(r, 4).text() for r in range(sp.table.rowCount())}
    want = w.con.execute('SELECT COUNT(*) FROM entry WHERE ledger_id=? AND code=? AND date BETWEEN ? AND ?',
                         (w.lid, code, T.replace(day=1).isoformat(), (T.replace(day=28) + dt.timedelta(days=4)).replace(day=1).isoformat())).fetchone()[0]
    check('지출 많은 계정 동그라미 → 그 계정·이 달만 검색', type(sp).__name__ == 'SearchPage' and sp.table.rowCount() == want > 0
          and labels == {E.deco(E.emoji_map(w.con, w.lid), code, L.code_label(L.category_map(w.con, w.lid), code))}, f'{code} {labels} {sp.table.rowCount()}/{want}')
    w.compose()
    settle()
    check('왼쪽 줄 [새 내역] → 가계부 입력하기', type(w.stack.currentWidget().widget()).__name__ == 'LedgerPage')

    print('타임라인 (짧은 글 SNS 모양)')
    TH.set_pref('theme', 'timeline')
    w.apply_theme()
    lp = w.goto('LedgerPage')
    settle()
    check('탭은 맨 위에 붙어 있고, 오른쪽에 많이 쓴 곳', lp.sns_center_lay.indexOf(lp.sns_tabs) == 0 and lp.sns_trends.isVisible()
          and w.rail_compose.isVisible() and w.sns_title.isVisible())
    w.grab().save(os.path.join(out, 'timeline.png'))
    row, pt = first_hit(lp, 'copy')
    src = L.get_entry(w.con, lp.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
    QTest.mouseClick(lp.table.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pt)
    settle()
    check('글의 🔁 아이콘 → 같은 내용을 오늘 날짜 새 내역으로', lp.editing is None and lp.form.item.text() == src['item']
          and lp.form.date.date_() == T and '다시 입력' in lp.mode_lbl.text())
    row, pt = first_hit(lp, 'edit')
    QTest.mouseClick(lp.table.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, pt)
    settle()
    check('글의 💬 아이콘 → 그 내역 수정', lp.editing == lp.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
    lp.new()

    print('백업')
    from gagyebu.ui.settings_page import GeneralTab
    stp = w.goto('SettingsPage')
    gt = next(p for p in stp.parts if isinstance(p, GeneralTab))
    stp.tabs.setCurrentWidget(gt)
    gt.refresh()
    settle()
    gd = os.path.join(tmp, 'Google Drive')
    check('구글 드라이브 폴더를 찾음 → [구글 드라이브에 저장]·[복원] 켜짐', gt._gdrive() == gd and gt.gd_save.isEnabled() and gt.gd_load.isEnabled())
    p = gt.backup_gdrive()
    check('구글 드라이브 폴더에 백업 (우리집가계부_백업/우리집가계부-백업-날짜.sqlite3)', p == os.path.join(gd, '우리집가계부_백업', B.backup_name())
          and B.validate_db(p), str(p))
    other = os.path.join(tmp, 'USB', '내 백업')
    SPmod.QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (other, ''))
    p2 = gt.backup_as()
    check('[다른 곳에 저장…] → 고른 곳에 저장 (.sqlite3 붙임)', p2 == other + '.sqlite3' and B.validate_db(p2), str(p2))
    p3 = gt.backup_send()
    urls = [u.toLocalFile() for u in QApplication.clipboard().mimeData().urls()]
    check('[카톡·디스코드로 보내기] → 파일을 클립보드에 복사 + 폴더 열기', p3 and urls == [p3] and B.validate_db(p3)
          and any(m.startswith('OPEN ') for m in msgs), str(urls))
    L.add_entry(w.con, w.lid, {'date': T, 'item': '복원 뒤 사라질 내역', 'expense': 1, 'code': exp_codes[0], 'memo': ''})
    SPmod.QFileDialog.getOpenFileName = staticmethod(lambda _p, _t, start, *_a: (p, '') if start == gd else ('', ''))
    gt.gd_load.click()
    settle()
    check('[구글 드라이브에서 복원…] → 드라이브 폴더에서 고른 백업으로 바뀜',
          not w.con.execute("SELECT 1 FROM entry WHERE item='복원 뒤 사라질 내역'").fetchone())

    print('글꼴 (무료 한글 글꼴)')
    from gagyebu.ui.settings_page import ThemeTab
    tt = next(p for p in w.goto('SettingsPage').parts if isinstance(p, ThemeTab))
    tt.refresh()
    labels = [tt.font.itemText(i) for i in range(tt.font.count())]
    check('글꼴 고르기에 고운돋움·주아·개구·서툰이야기', all(any(n in x for x in labels) for n in ('고운돋움', '주아', '개구', '서툰이야기')), str(labels))
    check('피드·타임라인 테마에서도 글꼴 고르기 켜짐', tt.font.isEnabled())
    for key, fam in (('gowun', 'Gowun Dodum'), ('jua', 'Jua'), ('gaegu', 'Gaegu'), ('poorstory', 'Poor Story')):
        tt.font.setCurrentIndex(tt.font.findData(key))
        settle()
        check(f'{key} → 화면 글꼴 {fam} (타임라인)', QApplication.font().family() == fam and lp.table.font().family() == fam,
              QApplication.font().family())
    w.grab().save(os.path.join(out, 'timeline-poorstory.png'))
    TH.set_pref('theme', 'retro')
    w.apply_theme()
    settle()
    check('미니홈피 테마에서도 고른 글꼴', QApplication.font().family() == 'Poor Story', QApplication.font().family())
    tt.refresh()
    tt.font.setCurrentIndex(tt.font.findData('pixel'))
    settle()
    check('도트 글꼴로 되돌리기', QApplication.font().family() == TH.PIXEL_FAMILY, QApplication.font().family())
except Exception:
    traceback.print_exc()
    fails.append('예외')

print()
print('실패:', fails if fails else '없음')
sys.exit(1 if fails else 0)
