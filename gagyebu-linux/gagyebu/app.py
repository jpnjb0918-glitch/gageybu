"""우리집 가계부 (리눅스판/윈도우판) — 진입점과 메인 창."""
import argparse
import datetime as dt
import os
import sys

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QScrollArea,
                             QStackedWidget, QVBoxLayout, QWidget)

from . import EDITION, __version__, db
from . import theme as TH
from .services import backup as B
from .services import calendar_svc as C
from .services import ledger as L
from .services import recurring as R
from .ui import hompy as H
from .ui import icons as IC
from .util import check_password, fmt_money

HERE = os.path.dirname(os.path.abspath(__file__))
# 피드·타임라인 테마의 왼쪽 메뉴 아이콘 (안드로이드판 main.js NAV_ICON 과 같은 그림)
NAV_ICON = {'LedgerPage': 'home', 'SearchPage': 'search', 'ReportsPage': 'report', 'GraphPage': 'chart', 'RecurringPage': 'repeat',
            'AssetsPage': 'wallet', 'CalendarPage': 'calendar', 'AddressPage': 'user', 'DiaryPage': 'book', 'MemoPage': 'note',
            'SettingsPage': 'gear'}


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
        L.ensure_default_ledgers(self.con)            # 생활비·용돈·비상금·여행 장부 (자료 파일마다 한 번만)
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
        from .ui.update_ui import Updater
        self.updater = Updater(self)                  # 새 버전 확인·내려받기·설치 (설정 → 업데이트 탭도 씀)
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
        self.sns_title = QLabel()                      # 피드·타임라인: 화면 이름 (짧은 글 SNS 의 가운데 칸 머리)
        self.sns_title.setObjectName('SnsTitle')
        self.main_lay.addWidget(self.sns_title)
        self.main_lay.addWidget(self.banner)
        self.main_lay.addWidget(self.stack, 1)
        self.hompy = QFrame()
        self.hompy.setObjectName('Hompy')
        self.hompy_lay = QHBoxLayout(self.hompy)
        self.hompy_lay.addWidget(self.profile)
        self.hompy_lay.addWidget(self.mainbox, 1)
        # 피드·타임라인: 왼쪽 줄 = 로고 · 아이콘 메뉴 · 새 내역(쓰기) · 장부 고르기 · 내 프로필
        self.rail_logo = QLabel('우리집 가계부')
        self.rail_logo.setObjectName('RailLogo')
        self.rail_create = QPushButton('새 내역')
        self.rail_create.setObjectName('RailCreate')
        self.rail_create.setToolTip('가계부 화면의 입력하기로')
        self.rail_create.clicked.connect(self.compose)
        self.rail_compose = QPushButton('입력하기')
        self.rail_compose.setObjectName('RailCompose')
        self.rail_compose.setToolTip('가계부 화면의 입력하기로')
        self.rail_compose.clicked.connect(self.compose)
        self.rail_ledger = QWidget()
        self.rail_ledger_lay = QVBoxLayout(self.rail_ledger)
        self.rail_ledger_lay.setContentsMargins(0, 0, 0, 0)
        self.rail_chip = QWidget()
        chip = QHBoxLayout(self.rail_chip)
        chip.setContentsMargins(6, 6, 6, 6)
        self.rail_avatar = QLabel()
        self.rail_avatar.setFixedSize(40, 40)
        self.rail_avatar.setToolTip('미니미 바꾸기: 설정 → 화면 꾸미기')
        self.rail_name = QLabel()
        self.rail_name.setObjectName('RailName')
        self.rail_sub = QLabel()
        self.rail_sub.setObjectName('RailSub')
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(self.rail_name)
        names.addWidget(self.rail_sub)
        chip.addWidget(self.rail_avatar)
        chip.addLayout(names, 1)
        self.navwrap = QWidget()
        self.navwrap.setObjectName('SnsRail')
        self.navwrap.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.nav_lay = QVBoxLayout(self.navwrap)
        for w in (self.rail_logo, self.nav, self.rail_create, self.rail_compose):
            self.nav_lay.addWidget(w)
        self.nav_lay.addStretch(1)
        self.nav_lay.addWidget(self.rail_ledger)
        self.nav_lay.addWidget(self.rail_chip)
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
        self.backdrop.dots_on = TH.sns_colors(theme)['bg'] if TH.variant_of(theme) == 'mh' else None
        self.backdrop.update()
        for w in (self.hompy_caption, self.profile, self.banner):
            w.setVisible(retro)
        for w in (self.today_lbl, self.hompy_title):
            w.setVisible(retro)
        self.sns_avatar.hide()
        self.hompy_title.setText('☆ 우리집 가계부 ☆' if retro else '우리집 가계부')
        self.marquee.setVisible(retro)
        self.marquee.set_running(retro and TH.pref('marquee'))
        self.ledger_lbl.setText('장부:' if retro else ' 장부: ')
        self.ledger_lbl.setVisible(not sns)
        self._place_rail(theme)
        # 탭: 미니홈피는 틀 오른쪽에 붙은 탭, 기본은 왼쪽 목록
        self.body.removeWidget(self.navwrap)
        if retro:
            self.body.addWidget(self.navwrap)
            self.nav.setFixedWidth(self._nav_width(92, 26))
            self.nav_lay.setContentsMargins(0, 26, 0, 0)
            self.nav_lay.setSpacing(6)
            self.nav_lay.setStretch(1, 0)
            self.nav_lay.setStretch(4, 1)
            self.outer.setContentsMargins(12, 8, 4, 10)
            self.outer.setSpacing(8)
            self.hompy_lay.setContentsMargins(8, 8, 8, 8)
            self.hompy_lay.setSpacing(8)
            self.main_lay.setContentsMargins(8, 4, 8, 8)
            self.main_lay.setSpacing(6)
        else:
            self.body.insertWidget(0, self.navwrap)
            self.nav.setFixedWidth(self._nav_width(206, 78) if sns else self._nav_width(150, 40))
            self.nav.setMinimumHeight(0)
            self.nav.setMaximumHeight(16777215)
            self.nav_lay.setStretch(1, 0 if sns else 1)
            self.nav_lay.setStretch(4, 1 if sns else 0)
            if sns:
                mh = TH.variant_of(theme) == 'mh'
                self.nav_lay.setContentsMargins(12, 18, 12, 14)
                self.nav_lay.setSpacing(6)
                self.outer.setContentsMargins(0, 8 if mh else 0, 0, 0)
                self.outer.setSpacing(0)
            else:
                self.nav_lay.setContentsMargins(0, 0, 9, 0)
                self.nav_lay.setSpacing(6)
                self.outer.setContentsMargins(9, 6, 9, 9)
                self.outer.setSpacing(6)
            for lay in (self.hompy_lay, self.main_lay):
                lay.setContentsMargins(0, 0, 0, 0)
                lay.setSpacing(0)
        self.profile.load_prefs()
        if retro or sns:
            self._fit_nav()                         # 메뉴 높이를 내용에 맞춤 (SNS: 바로 아래에 새 내역 단추)
        self.backdrop.update()
        if refresh:
            self.data_changed()

    def _place_rail(self, theme):
        """피드·타임라인: 왼쪽 줄(로고·아이콘 메뉴·쓰기·장부·내 프로필), 그 밖: 맨 위 줄에 장부 고르기"""
        sns = theme in TH.SNS_THEMES
        lay_ = TH.layout_of(theme)
        c = TH.sns_colors(theme) or {}
        for w in (self.rail_logo, self.rail_ledger, self.rail_chip):
            w.setVisible(sns)
        self.rail_create.setVisible(lay_ == 'feed')
        self.rail_compose.setVisible(lay_ == 'timeline')
        combo = self.ledger_combo
        if sns:
            self.top_lay.removeWidget(combo)
            self.rail_ledger_lay.addWidget(combo)
            combo.setObjectName('RailLedger')
            combo.setMinimumWidth(0)
            if lay_ == 'feed':                      # 손글씨 로고
                f = QFont(TH.logo_family() or self.font().family())
                f.setPixelSize(34)
                self.rail_logo.setFont(f)
                self.rail_logo.setText('우리집 가계부')
            else:                                   # 고양이 로고
                self.rail_logo.setText('')
                self.rail_logo.setPixmap(TH.sticker_pixmap('a01', 46))
            on = c.get('on_bg', '#000000')
            self.rail_create.setIcon(QIcon(IC.pixmap('plus', 26, on)))
            self.rail_create.setIconSize(QSize(26, 26))
            self.rail_compose.setIcon(QIcon(IC.pixmap('pen', 20, '#FFFFFF', width=2.2)))
            self.rail_compose.setIconSize(QSize(20, 20))
            self.rail_avatar.setPixmap(TH.avatar_pixmap(TH.pref('minimi'), 40, theme))
            self.nav.setIconSize(QSize(26, 26))
        else:
            self.rail_ledger_lay.removeWidget(combo)
            self.top_lay.addWidget(combo)
            combo.setObjectName('')
            combo.setMinimumWidth(200)
        combo.style().unpolish(combo)
        combo.style().polish(combo)
        self._nav_icons(theme)

    def _nav_icons(self, theme=None):
        theme = theme or TH.current()[0]
        c = TH.sns_colors(theme)
        cur = self.nav.currentRow()
        for row in range(self.nav.count()):
            it = self.nav.item(row)
            name = type(self.pages[self.nav_order[row]]).__name__
            if c:
                on = row == cur
                ic = QIcon()
                pm = IC.pixmap(NAV_ICON.get(name, 'dots'), 26, c['on_bg'], on=on)
                for mode in (QIcon.Mode.Normal, QIcon.Mode.Selected, QIcon.Mode.Active):
                    ic.addPixmap(pm, mode)                   # 고른 줄도 같은 색 (Qt 가 포인트색으로 물들이지 않게)
                it.setIcon(ic)
                f = QFont(self.nav.font())
                f.setBold(on)
                it.setFont(f)
            else:
                it.setIcon(QIcon())
                it.setFont(self.nav.font())

    def compose(self):
        """왼쪽 줄의 [새 내역]/[입력하기]: 가계부 화면의 입력하기로"""
        lp = self.goto('LedgerPage')
        if lp is not None:
            lp.new()

    def _nav_width(self, base, pad):
        """메뉴 폭: 기본 폭, 글자를 크게 하면 가장 긴 메뉴 이름이 다 보이게 넓힘"""
        self.nav.ensurePolished()
        fm = self.nav.fontMetrics()
        return max(base, max(fm.horizontalAdvance(p.title) for p in self.pages) + pad)

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
        self._nav_icons()

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
        self.rail_name.setText(name)
        self.rail_sub.setText(f'오늘 지출 {fmt_money(texp)}원 · 잔액 {bal}원')
        self.rail_sub.setToolTip(f'이번 달 지출 {fmt_money(exp)}원')
        if TH.current()[0] in TH.SNS_THEMES:
            self.rail_avatar.setPixmap(TH.avatar_pixmap(TH.pref('minimi'), 40))
        return bal

    # ── 장부 ──
    NEW_LEDGER, MANAGE_LEDGERS = '__new', '__manage'

    def reload_ledgers(self):
        self.ledger_combo.blockSignals(True)
        self.ledger_combo.clear()
        for r in L.ledgers(self.con):
            self.ledger_combo.addItem(r['name'], r['id'])
        self.ledger_combo.insertSeparator(self.ledger_combo.count())
        self.ledger_combo.addItem('＋ 새 장부 만들기…', self.NEW_LEDGER)      # 목록에서 바로 새 장부
        self.ledger_combo.addItem('장부 관리…', self.MANAGE_LEDGERS)
        if self.ledger_combo.findData(self.lid) < 0:
            self.lid = L.first_ledger_id(self.con)
        self.ledger_combo.setCurrentIndex(max(0, self.ledger_combo.findData(self.lid)))
        self.ledger_combo.blockSignals(False)

    def new_ledger(self):
        """새 장부: 이름과 만드는 방법(빈 장부 / 지금 장부의 계정과목만 / 통째로 복사) → 만들고 그 장부로"""
        from .ui.widgets import FormDialog, run_dialog
        cur = self.ledger_name().replace('|', '/')       # 고르기 칸 구분자와 겹치지 않게
        how = ['빈 장부 (대분류 수입만)', f'지금 장부({cur})의 계정과목만 복사', '지금 장부를 통째로 복사']
        dlg = FormDialog(self, '새 장부', [('name', '장부 이름', 'text*'), ('how', '만드는 방법', 'choice:' + '|'.join(how))],
                         {'how': 1})
        if run_dialog(dlg) != QDialog.DialogCode.Accepted:
            return None
        v = dlg.values()
        name = str(v.get('name') or '').strip()
        if not name:
            return None
        i = how.index(v['how']) if v.get('how') in how else 1
        lid = L.add_ledger(self.con, name, copy_from=None if i == 0 else self.lid, codes_only=(i == 1))
        self.lid = lid
        self.reload_ledgers()
        self.reset_edit_state()
        self.data_changed()
        self.statusBar().showMessage(f"새 장부 '{name}'을(를) 만들었습니다.", 5000)
        return lid

    def manage_ledgers(self):
        sp = self.goto('SettingsPage')
        from .ui.settings_page import LedgerTab
        for p in sp.parts:
            if isinstance(p, LedgerTab):
                sp.tabs.setCurrentWidget(p)

    def ledger_name(self):
        return self.ledger_combo.currentText()

    def reset_edit_state(self):
        """장부를 바꾸거나 DB를 교체하면 각 화면의 '수정 중' 상태를 지움 (다른 장부 내역을 덮어쓰지 않게)."""
        for p in self.pages:
            if hasattr(p, 'reset_state'):
                p.reset_state()

    def _ledger_selected(self, _i):
        lid = self.ledger_combo.currentData()
        if lid in (self.NEW_LEDGER, self.MANAGE_LEDGERS):
            self.ledger_combo.setCurrentIndex(max(0, self.ledger_combo.findData(self.lid)))   # 고른 칸은 지금 장부로 되돌림
            self.new_ledger() if lid == self.NEW_LEDGER else self.manage_ledgers()
            return
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
        theme = TH.current()[0]
        lay_ = TH.layout_of(theme)
        # 피드의 가계부 화면은 프로필 머리가 제목 대신, 그 밖의 SNS 화면은 위에 화면 이름
        self.sns_title.setVisible(bool(lay_) and not (lay_ == 'feed' and type(self.pages[i]).__name__ == 'LedgerPage'))
        self.sns_title.setText(self.pages[i].title)
        if lay_:
            self._nav_icons(theme)
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
        L.ensure_default_ledgers(self.con)
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
    w.updater.check_later()                         # 켤 때 새 버전 확인 (설정 → 업데이트에서 끌 수 있음)
    rc = app.exec()
    w.deleteLater()            # 창을 먼저 정리한 뒤 종료 (종료 순서 문제로 인한 비정상 종료 방지)
    app.processEvents()
    del w
    return rc


if __name__ == '__main__':
    sys.exit(main())
