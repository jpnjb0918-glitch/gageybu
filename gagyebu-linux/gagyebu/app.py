"""우리집 가계부 (리눅스판/윈도우판) — 진입점과 메인 창."""
import argparse
import datetime as dt
import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QScrollArea,
                             QStackedWidget, QVBoxLayout, QWidget)

from . import EDITION, __version__, db
from . import theme as TH
from .services import backup as B
from .services import calendar_svc as C
from .services import ledger as L
from .services import recurring as R
from .ui import hompy as H
from .util import check_password, fmt_money

HERE = os.path.dirname(os.path.abspath(__file__))


class LoginDialog(QDialog):
    def __init__(self, stored):
        super().__init__()
        self.stored = stored
        self.setWindowTitle('우리집 가계부 — 암호 입력')
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.msg = QLabel('암호를 입력하세요.')
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        form = QVBoxLayout()
        form.addWidget(self.msg)
        form.addWidget(self.pw)
        if TH.current()[0] == 'retro':                # 미니홈피 테마: 비밀 고양이 + 한마디
            hint = QLabel('쉿! 아무에게도 알려 주지 마세요 (^_^;)')
            hint.setObjectName('LoginHint')
            form.addWidget(hint)
            pic = QLabel()
            pic.setPixmap(TH.sticker_pixmap(TH.LOGIN_STICKER, 96))
            row = QHBoxLayout()
            row.addWidget(pic)
            row.addSpacing(8)
            row.addLayout(form, 1)
            lay = QVBoxLayout(self)
            lay.addLayout(row)
        else:
            lay = QVBoxLayout(self)
            lay.addLayout(form)
        lay.addWidget(bb)
        self.tries = 0

    def _ok(self):
        if check_password(self.pw.text(), self.stored):
            self.accept()
        else:
            self.tries += 1
            self.msg.setText(f'암호가 틀렸습니다 ({self.tries}회). 다시 입력하세요.')
            self.pw.selectAll()


class MainWindow(QMainWindow):
    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path
        self.con = db.ConProxy(db.connect(db_path))
        self.lid = L.first_ledger_id(self.con)
        self.setWindowTitle(f'우리집 가계부 ({EDITION} {__version__})')
        self.setWindowIcon(QIcon(TH.ICON))
        # 처음 크기: 1440x880, 화면이 더 작으면 화면에 맞춤 (노트북 1366x768 등)
        scr = QApplication.primaryScreen()
        avail = scr.availableGeometry() if scr else None
        self.resize(min(1440, avail.width()) if avail else 1440, min(880, avail.height()) if avail else 880)

        # ── 맨 위 줄: [TODAY|이달] ☆ 제목 ☆  ~~전광판~~  장부: [▼] ──
        self.ledger_lbl = QLabel('장부:')
        self.ledger_lbl.setObjectName('LedgerLabel')
        self.ledger_combo = QComboBox()
        self.ledger_combo.setMinimumWidth(200)
        self.ledger_combo.activated.connect(self._ledger_selected)
        self.today_lbl = QLabel()
        self.today_lbl.setObjectName('TodayLabel')
        self.today_lbl.setToolTip('TODAY = 오늘 지출, 이달 = 이번 달(1일~말일) 지출')
        self.hompy_title = QLabel('☆ 우리집 가계부 ☆')
        self.hompy_title.setObjectName('HompyTitle')
        self.hompy_caption = QLabel('~ 알뜰살뜰 미니홈피 ~')
        self.hompy_caption.setObjectName('HompyCaption')
        self.marquee = H.Marquee()
        self.marquee.setMaximumWidth(520)
        self.sns_avatar = QLabel()                    # 피드·타임라인 테마: 동그란 미니미
        self.sns_avatar.setObjectName('SnsAvatar')
        self.sns_avatar.setFixedSize(40, 40)
        self.sns_avatar.setToolTip('미니미 바꾸기: 설정 → 화면 꾸미기')
        top = QHBoxLayout()
        self.top_lay = top
        top.setSpacing(10)
        for w in (self.sns_avatar, self.today_lbl, self.hompy_title, self.hompy_caption):
            top.addWidget(w)
        top.addStretch(1)
        top.addWidget(self.marquee, 1)
        top.addWidget(self.ledger_lbl)
        top.addWidget(self.ledger_combo)

        from .ui.assets_page import AssetsPage
        from .ui.calendar_page import CalendarPage
        from .ui.graph_page import GraphPage
        from .ui.ledger_page import LedgerPage
        from .ui.misc_pages import AddressPage, DiaryPage, MemoPage
        from .ui.recurring_page import RecurringPage
        from .ui.reports_page import ReportsPage
        from .ui.search_page import SearchPage
        from .ui.settings_page import SettingsPage
        self.pages = [LedgerPage(self), SearchPage(self), ReportsPage(self), GraphPage(self), RecurringPage(self),
                      AssetsPage(self), CalendarPage(self), AddressPage(self), DiaryPage(self), MemoPage(self),
                      SettingsPage(self)]
        self.nav = QListWidget()
        self.nav.setObjectName('TabNav')
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.stack = QStackedWidget()
        self.nav_order = list(range(len(self.pages)))      # 메뉴 줄 번호 → 화면 번호 (메뉴 순서는 바꿀 수 있음)
        self.apply_nav_order(select=False)
        for p in self.pages:
            # 화면이 좁으면 창이 화면 밖으로 넘치지 않고 그 화면만 스크롤되게
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.Shape.NoFrame)
            sa.setWidget(p)
            self.stack.addWidget(sa)
        self.nav.currentRowChanged.connect(self._page_changed)

        # ── 가운데: 미니홈피 틀 [프로필 | 제목 띠 + 화면] + 오른쪽 탭 ──
        self.profile = H.ProfilePanel(self)
        self.profile.motto_changed.connect(self.update_hompy)
        self.banner = H.PageBanner()
        self.mainbox = QFrame()
        self.mainbox.setObjectName('MainBox')
        self.main_lay = QVBoxLayout(self.mainbox)
        self.main_lay.addWidget(self.banner)
        self.main_lay.addWidget(self.stack, 1)
        self.hompy = QFrame()
        self.hompy.setObjectName('Hompy')
        self.hompy_lay = QHBoxLayout(self.hompy)
        self.hompy_lay.addWidget(self.profile)
        self.hompy_lay.addWidget(self.mainbox, 1)
        self.navwrap = QWidget()
        self.nav_lay = QVBoxLayout(self.navwrap)
        self.nav_lay.addWidget(self.nav)
        self.nav_lay.addStretch(1)
        self.body = QHBoxLayout()
        self.body.setSpacing(0)
        self.body.addWidget(self.hompy, 1)
        self.body.addWidget(self.navwrap)
        self.backdrop = H.Backdrop()
        self.outer = QVBoxLayout(self.backdrop)
        self.outer.addLayout(top)
        self.outer.addLayout(self.body, 1)
        self.setCentralWidget(self.backdrop)
        self.dirty = set(range(len(self.pages)))
        self.reload_ledgers()
        self.apply_theme(refresh=False)
        self.nav.setCurrentRow(0)

    # ── 테마 ──
    def apply_theme(self, refresh=True):
        """설정의 테마(미니홈피/기본)를 적용: 스타일 + 배치(탭 위치·프로필·제목 띠) 바꾸기."""
        theme, _pixel = TH.apply()
        retro = theme == 'retro'
        sns = theme in TH.SNS_THEMES
        self.backdrop.retro = retro
        for w in (self.hompy_caption, self.profile, self.banner):
            w.setVisible(retro)
        for w in (self.today_lbl, self.hompy_title):
            w.setVisible(retro or sns)
        self.sns_avatar.setVisible(sns)
        if sns:
            self.sns_avatar.setPixmap(TH.avatar_pixmap(TH.pref('minimi'), 40, theme))
        self.hompy_title.setText('☆ 우리집 가계부 ☆' if retro else '우리집 가계부')
        # 미니홈피: [TODAY] 제목 / 피드·타임라인: (미니미) 제목 [TODAY]
        self.top_lay.removeWidget(self.today_lbl)
        i = self.top_lay.indexOf(self.hompy_title)
        self.top_lay.insertWidget(i + 1 if sns else i, self.today_lbl)
        self.marquee.setVisible(retro)
        self.marquee.set_running(retro and TH.pref('marquee'))
        self.ledger_lbl.setText('장부:' if retro else ' 장부: ')
        # 탭: 미니홈피는 틀 오른쪽에 붙은 탭, 기본은 왼쪽 목록
        self.body.removeWidget(self.navwrap)
        if retro:
            self.body.addWidget(self.navwrap)
            self.nav.setFixedWidth(92)
            self.nav_lay.setContentsMargins(0, 26, 0, 0)
            self.nav_lay.setStretch(0, 0)
            self.nav_lay.setStretch(1, 1)
            self.outer.setContentsMargins(12, 8, 4, 10)
            self.outer.setSpacing(8)
            self.hompy_lay.setContentsMargins(8, 8, 8, 8)
            self.hompy_lay.setSpacing(8)
            self.main_lay.setContentsMargins(8, 4, 8, 8)
            self.main_lay.setSpacing(6)
        else:
            self.body.insertWidget(0, self.navwrap)
            self.nav.setFixedWidth(170 if sns else 150)
            self.nav.setMinimumHeight(0)
            self.nav.setMaximumHeight(16777215)
            self.nav_lay.setContentsMargins(0, 0, 9, 0)
            self.nav_lay.setStretch(0, 1)
            self.nav_lay.setStretch(1, 0)
            self.outer.setContentsMargins(9, 6, 9, 9)
            self.outer.setSpacing(6)
            for lay in (self.hompy_lay, self.main_lay):
                lay.setContentsMargins(0, 0, 0, 0)
                lay.setSpacing(0)
        self.profile.load_prefs()
        if retro:
            self._fit_nav()
        self.backdrop.update()
        if refresh:
            self.data_changed()

    def apply_nav_order(self, select=True):
        """설정의 메뉴 순서대로 왼쪽(오른쪽) 메뉴를 다시 채움. 첫 줄이 처음 화면."""
        names = [type(p).__name__ for p in self.pages]
        order = [names.index(n) for n in TH.nav_order() if n in names]
        order += [i for i in range(len(self.pages)) if i not in order]
        cur = self.nav_order[self.nav.currentRow()] if 0 <= self.nav.currentRow() < len(self.nav_order) else None
        self.nav_order = order
        self.nav.blockSignals(True)
        self.nav.clear()
        for i in order:
            self.nav.addItem(QListWidgetItem(self.pages[i].title))
        self.nav.blockSignals(False)
        if select and cur is not None:
            self.nav.setCurrentRow(order.index(cur))

    def _fit_nav(self):
        """탭 목록 높이를 내용에 맞춤 (틀 옆에 탭만 붙어 보이게)."""
        self.nav.doItemsLayout()
        h = sum(max(self.nav.sizeHintForRow(i), 1) for i in range(self.nav.count()))
        h += 2 * self.nav.frameWidth() + 6
        self.nav.setFixedHeight(h if h > 40 else 11 * 36)

    def update_hompy(self):
        """프로필·맨 위 TODAY·전광판의 숫자를 지금 장부 기준으로 다시 씀."""
        today = dt.date.today()
        m0 = today.replace(day=1)
        m1 = (m0 + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
        bal = fmt_money(L.current_balance(self.con, self.lid, today))
        inc, exp = L.totals(self.con, self.lid, m0, m1)
        _ti, texp = L.totals(self.con, self.lid, today, today)
        name = self.ledger_name()
        self.profile.set_numbers(name, bal, fmt_money(inc), fmt_money(exp))
        self.today_lbl.setText(H.today_html(fmt_money(texp), fmt_money(exp)))
        motto = TH.pref('motto').replace('\n', ' ') or '오늘도 알뜰살뜰 (^-^)v'
        self.marquee.set_text(f'♬ {today:%Y년 %m월 %d일} ☆ {name} 잔액 {bal}원 ☆ 이번 달 수입 {fmt_money(inc)}원 · '
                              f'지출 {fmt_money(exp)}원 ☆ {motto} ☆')
        return bal

    # ── 장부 ──
    def reload_ledgers(self):
        self.ledger_combo.clear()
        for r in L.ledgers(self.con):
            self.ledger_combo.addItem(r['name'], r['id'])
        if self.ledger_combo.findData(self.lid) < 0:
            self.lid = L.first_ledger_id(self.con)
        self.ledger_combo.setCurrentIndex(max(0, self.ledger_combo.findData(self.lid)))

    def ledger_name(self):
        return self.ledger_combo.currentText()

    def reset_edit_state(self):
        """장부를 바꾸거나 DB를 교체하면 각 화면의 '수정 중' 상태를 지움 (다른 장부 내역을 덮어쓰지 않게)."""
        for p in self.pages:
            if hasattr(p, 'reset_state'):
                p.reset_state()

    def _ledger_selected(self, _i):
        lid = self.ledger_combo.currentData()
        if lid and lid != self.lid:
            self.lid = lid
            self.reset_edit_state()
            self.data_changed()
            self.check_recurring()

    def data_changed(self):
        self.dirty = set(range(len(self.pages)))
        self._page_changed(self.nav.currentRow())
        bal = self.update_hompy()
        self.statusBar().showMessage(f'{self.ledger_name()}  ·  현재 잔액(오늘까지) {bal}원')

    def _page_changed(self, row):
        if row < 0 or row >= len(self.nav_order):
            return
        i = self.nav_order[row]
        self.stack.setCurrentIndex(i)
        self.banner.set_page(self.pages[i])
        if i in self.dirty:
            self.dirty.discard(i)
            self.pages[i].refresh()

    def goto(self, page_cls_name):
        for i, p in enumerate(self.pages):
            if type(p).__name__ == page_cls_name:
                self.nav.setCurrentRow(self.nav_order.index(i))
                return p

    # ── DB 교체 (가져오기·복원) ──
    def replace_db(self, new_path):
        keep = os.path.join(os.path.dirname(self.db_path), 'auto-backup')
        tmp = B.prepare_replacement(self.db_path, new_path)   # 실패하면 여기서 끝 (현재 데이터 그대로)
        kept = B.keep_current(self.db_path, keep)
        self.con.close()
        try:
            B.swap_in(self.db_path, tmp)
        finally:
            self.con.swap(db.connect(self.db_path))           # 성공·실패 모두 다시 연결
        self.reset_edit_state()
        self.lid = L.first_ledger_id(self.con)
        self.reload_ledgers()
        self.data_changed()
        return kept

    # ── 시작 시 확인 ──
    def check_recurring(self):
        due, later = R.pending(self.con, self.lid)
        if due:
            from .ui.recurring_page import PendingDialog
            PendingDialog(self, self.con, self.lid, due, later).exec()
            self.data_changed()

    def check_reminders(self):
        rs = C.reminders(self.con)
        if rs:
            txt = '\n'.join(f"· {r['date']}  {r['text']}" for r in rs[:20])
            QMessageBox.information(self, '다가오는 일정', txt)

    def closeEvent(self, ev):
        folder = db.get_meta(self.con, 'backup_on_exit')
        if folder:
            try:
                path = B.backup(self.con, folder)
                self.statusBar().showMessage(f'백업: {path}')
            except OSError as e:
                QMessageBox.warning(self, '백업 실패', f'종료 시 자동 백업에 실패했습니다:\n{e}')
        self.con.close()
        super().closeEvent(ev)


def load_korean(app):
    """Qt 기본 버튼(확인/취소/예/아니오 등)을 한국어로 (qt6-translations-l10n 패키지)."""
    from PyQt6.QtCore import QLibraryInfo, QLocale, QTranslator
    tr = QTranslator(app)
    if tr.load(QLocale(QLocale.Language.Korean, QLocale.Country.SouthKorea), 'qtbase', '_',
               QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(tr)
        app._ko_translator = tr
        return True
    return False


def acquire_lock(db_path):
    """같은 데이터 파일을 두 프로그램이 동시에 쓰지 않도록 잠금. 이미 잠겨 있으면 None."""
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    f = open(db_path + '.lock', 'w')
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def install_error_dialog():
    """처리 못 한 오류가 나도 프로그램이 통째로 꺼지지 않고 알림창으로 보여 줌."""
    import traceback

    def hook(etype, value, tb):
        text = ''.join(traceback.format_exception(etype, value, tb))
        if sys.stderr:                                  # 윈도우 창 프로그램은 stderr 가 없음(None)
            sys.stderr.write(text)
        try:                                            # 데이터 폴더의 error.log 에도 남김 (문제 알릴 때 참고용)
            import datetime as _dt
            with open(os.path.join(os.path.dirname(db.default_db_path()), 'error.log'), 'a', encoding='utf-8') as f:
                f.write(f'--- {_dt.datetime.now():%Y-%m-%d %H:%M:%S}\n{text}\n')
        except OSError:
            pass
        try:
            QMessageBox.critical(None, '오류', f'처리하지 못한 오류가 났습니다. 방금 한 작업은 저장되지 않았을 수 있습니다.\n\n'
                                             f'{etype.__name__}: {value}')
        except Exception:
            pass
    sys.excepthook = hook


def main(argv=None):
    for s in (sys.stdout, sys.stderr):      # 윈도우에서 결과를 파일로 넘길 때 한글 때문에 멈추지 않게
        if s is not None and hasattr(s, 'reconfigure'):
            try:
                s.reconfigure(errors='replace')
            except (ValueError, OSError):
                pass
    ap = argparse.ArgumentParser(description=f'우리집 가계부 ({EDITION})')
    ap.add_argument('--db', default=db.default_db_path(), help='데이터 파일 경로')
    ap.add_argument('--import-from', metavar='DATA폴더',
                    help="윈도우 '우리집 가계부\\data' 폴더를 가져온 뒤 실행 (현재 데이터는 자동 보관)")
    ap.add_argument('--import-only', action='store_true', help='가져오기만 하고 창은 띄우지 않음')
    args, qt_args = ap.parse_known_args(argv)
    lock = acquire_lock(args.db)
    if lock is None:
        msg = '우리집 가계부가 이미 실행 중입니다. 열린 창을 쓰거나, 닫은 뒤 다시 실행하세요.'
        if args.import_from or args.import_only:
            print(msg, file=sys.stderr)
            return 1
        app = QApplication.instance() or QApplication([sys.argv[0]] + qt_args)
        load_korean(app)
        QMessageBox.information(None, '우리집 가계부', msg)
        return 1
    if args.import_from:
        import shutil
        import tempfile
        from .services import importer as I
        base = os.path.dirname(os.path.abspath(args.db))
        os.makedirs(base, exist_ok=True)
        tmpdir = tempfile.mkdtemp(prefix='gagyebu-import-', dir=base)
        try:
            rep = I.import_folder(args.import_from, os.path.join(tmpdir, 'import.sqlite3'))
            kept = B.replace_db(args.db, os.path.join(tmpdir, 'import.sqlite3'), os.path.join(base, 'auto-backup'))
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
        print(rep.text())
        if kept:
            print(f'\n이전 데이터 보관: {kept}')
        if args.import_only:
            return 0
    app = QApplication.instance() or QApplication([sys.argv[0]] + qt_args)
    app.setApplicationName('우리집 가계부')
    app.setDesktopFileName('gagyebu-linux')
    app.setWindowIcon(QIcon(TH.ICON))
    load_korean(app)
    install_error_dialog()
    TH.apply(app)                                   # 암호 창부터 테마 적용
    con = db.connect(args.db)
    stored = db.get_meta(con, 'password')
    con.close()
    if stored and LoginDialog(stored).exec() != QDialog.DialogCode.Accepted:
        return 0
    w = MainWindow(args.db)
    w.show()
    w.data_changed()
    w.check_reminders()
    w.check_recurring()
    rc = app.exec()
    w.deleteLater()            # 창을 먼저 정리한 뒤 종료 (종료 순서 문제로 인한 비정상 종료 방지)
    app.processEvents()
    del w
    return rc


if __name__ == '__main__':
    sys.exit(main())
