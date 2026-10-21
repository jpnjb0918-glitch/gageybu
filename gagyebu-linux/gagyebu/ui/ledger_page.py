"""가계부 메인 화면: 내역 목록(잔액 포함) + 입력하기 + 이달의 현황."""
import datetime as dt

from PyQt6.QtCore import QEvent, QPoint, QSize, QStringListModel, Qt
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QCompleter, QDialog, QFormLayout, QFrame,
                             QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QScrollArea,
                             QSizePolicy, QSplitter, QToolButton, QVBoxLayout, QWidget)

from .. import db
from .. import theme as T
from ..services import ledger as L
from ..util import fmt_money, month_end
from ..services import order as O
from .widgets import (CENTER, CodeCombo, DateEdit, MoneyEdit, MonthNav, PayCombo, ask_order, button, cell, confirm,
                      error, export_csv, fill, info, make_table, money_cell, ok_cancel, print_table, selected_ids,
                      set_tone)
from . import money_ui as MU
from ..services import catemoji as E
from ..services import money as M
from ..services import trash as TR
from . import icons as I
from . import extras as X
from ..services import attach as AT
from .sns import C_ITEM, C_MEMO, POST_W, Highlights, LedgerDelegate, PinnedPost, ProfileHeader, SnsTabs, Trends


class EntryForm(QWidget):
    """내역 입력 칸 묶음 (메인 화면·수정 창 공용)."""
    def __init__(self, con, parent=None):
        super().__init__(parent)
        self.con, self.lid = con, None
        self.date = DateEdit()
        self.item = QLineEdit()
        self.item.setPlaceholderText('예: 점심, 전기세')
        self.income = MoneyEdit()
        self.expense = MoneyEdit()
        self.code = CodeCombo(con)
        self.pay = PayCombo(con)
        self.memo = QLineEdit()
        self.completer = QCompleter()
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.item.setCompleter(self.completer)
        self.item.editingFinished.connect(self._auto_code)
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow('날짜', self.date)
        form.addRow('내용', self.item)
        form.addRow('수입 금액', self.income)
        form.addRow('지출 금액', self.expense)
        form.addRow('카테고리', self.code)
        form.addRow('결제수단', self.pay)
        form.addRow('메모', self.memo)

    def load(self, lid, editing=False):
        self.lid = lid
        self.code.load(lid, keep_unknown=editing)
        self.pay.load()
        n = int(db.get_meta(self.con, 'item_min_count', 1) or 1)
        self.completer.setModel(QStringListModel([w['name'] for w in L.item_words(self.con, lid, n)]))

    def _auto_code(self):
        """예전에 쓴 품목이면 그때의 계정을 자동 선택 (원본 '품목 자동입력')."""
        if self.lid and self.item.text().strip():
            c = L.last_code_for_item(self.con, self.lid, self.item.text().strip())
            if c and self.code.findData(c) >= 0:
                self.code.set_code(c)

    def value(self):
        return {'date': self.date.date_(), 'item': self.item.text().strip(), 'income': self.income.value(),
                'expense': self.expense.value(), 'code': self.code.code(), 'memo': self.memo.text().strip(),
                'pay': self.pay.pay()}

    def set_value(self, e):
        self.date.set_date(e['date'])
        self.item.setText(e['item'])
        self.income.set_value(e['income'])
        self.expense.set_value(e['expense'])
        self.code.set_code(e['code'], keep_unknown=True)
        self.pay.set_pay(_get(e, 'pay'))
        self.memo.setText(e['memo'] or '')

    def clear(self, keep_date=True):
        d = self.date.date_()
        for w in (self.item, self.income, self.expense, self.memo):
            w.clear()
        if keep_date:
            self.date.set_date(d)

    def validate(self, parent):
        try:
            v = self.value()
        except ValueError:
            error(parent, '금액은 숫자로 입력하세요.')
            return None
        if not v['item']:
            error(parent, '내용을 입력하세요.')
            self.item.setFocus()
            return None
        if not v['income'] and not v['expense']:
            error(parent, '수입 또는 지출 금액을 입력하세요.')
            self.expense.setFocus()
            return None
        if not v['code']:
            error(parent, '카테고리를 선택하세요. (설정 → 카테고리에서 만들 수 있습니다)')
            return None
        return v


class EntryDialog(QDialog):
    def __init__(self, parent, con, lid, entry):
        super().__init__(parent)
        self.setWindowTitle('내역 수정')
        self.form = EntryForm(con)
        self.form.load(lid)
        self.form.set_value(entry)
        bb = ok_cancel(self, '저장', self._ok)
        lay = QVBoxLayout(self)
        lay.addWidget(self.form)
        lay.addWidget(bb)
        self.v = None

    def _ok(self):
        self.v = self.form.validate(self)
        if self.v:
            self.accept()


class LedgerPage(QWidget):
    title = '가계부'

    def __init__(self, app):
        super().__init__()
        self.app, self.con = app, app.con
        self.editing = None
        self.nav = MonthNav()
        self.nav.changed.connect(lambda *_: self.refresh())
        self.all_chk = QCheckBox('전체 기간')
        self.all_chk.toggled.connect(lambda *_: self.refresh())
        self.desc_chk = QCheckBox('최신순')
        self.desc_chk.setChecked(True)
        self.desc_chk.toggled.connect(lambda *_: self.refresh())
        self.table = make_table(['날짜', '내용', '수입', '지출', '잔액', '카테고리', '메모', '결제'], stretch=6, multi=True)
        self.table.itemSelectionChanged.connect(self._selected)
        self.table.doubleClicked.connect(lambda *_: self.form.item.setFocus())
        self.sns_delegate = LedgerDelegate(self.table)      # 피드·타임라인 테마일 때만 씀
        self.table.viewport().installEventFilter(self)      # 그림 속 아이콘 누르기
        self.table.viewport().setMouseTracking(True)
        self.table.installEventFilter(self)                 # 폭이 바뀌면 줄 높이 다시 (타임라인 메모 줄바꿈)

        self.form = EntryForm(self.con)
        self.save_btn = button('저장 (F5)', self.save)
        self.save_btn.setDefault(True)
        self.new_btn = button('새 내역', self.new)
        self.del_btn = button('삭제', self.delete)
        self.pending_photos = []                  # 새 내역에 붙일 사진 (저장할 때 함께)
        self.sms_btn = button('문자 붙여넣기', self.paste_sms, '카드·은행 알림 문자를 붙여넣으면 날짜·금액·가게를 읽어 내역으로 넣습니다')
        self.fav_btn = button('★ 자주 쓰는 내역', None, '자주 넣는 내역을 골라 입력 칸을 한 번에 채웁니다')
        self.fav_menu = QMenu(self)
        self.fav_menu.aboutToShow.connect(self._fill_fav_menu)
        self.fav_btn.setMenu(self.fav_menu)
        self.photo_btn = button('사진', self.photos, '영수증 사진을 이 내역에 붙입니다 (자료 파일에 함께 저장)')
        self.fx_btn = button('외화', self.foreign, '여행에서 쓴 외화 금액과 환율로 원 금액을 넣습니다')
        self.split_btn = button('나눠 적기', self.split_entry, '1년치 보험료처럼 큰돈을 여러 달로 나눠 적습니다')
        self.mode_lbl = set_tone(QLabel('새 내역 입력'), 'note')
        self.mode_lbl.setWordWrap(True)           # 긴 품목 이름이 입력 칸을 넓혀 화면 밖으로 밀지 않게
        self.same_btn = button('', self.same_place, '같은 내용의 최근 3개월 내역과 합계')
        self.same_btn.setFlat(True)
        self.same_btn.setStyleSheet('text-align:left; padding:1px 2px; text-decoration: underline')
        self.same_btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)   # 긴 내용이라도 옆 칸을 넓히지 않게
        self.same_btn.hide()
        box = QGroupBox('입력하기')
        self.box = box
        bl = QVBoxLayout(box)
        bl.addWidget(self.mode_lbl)
        bl.addWidget(self.same_btn)
        bl.addWidget(self.form)
        tools = QGridLayout()                    # 여러 줄: 좁은 입력 상자(미니홈피 도트 글꼴)에서도 화면 밖으로 밀리지 않게
        tools.setContentsMargins(0, 0, 0, 0)
        tools.addWidget(self.sms_btn, 0, 0)
        tools.addWidget(self.photo_btn, 0, 1)
        tools.addWidget(self.fx_btn, 1, 0)
        tools.addWidget(self.split_btn, 1, 1)
        tools.addWidget(self.fav_btn, 2, 0, 1, 2)
        bl.addLayout(tools)
        row = QHBoxLayout()
        row.addWidget(self.save_btn)
        row.addWidget(self.new_btn)
        row.addWidget(self.del_btn)
        bl.addLayout(row)
        bl.addStretch(1)
        tips = QLabel('· 내용을 예전과 같게 쓰면 카테고리가 자동 선택됩니다\n· 금액 칸에 12000+3500 처럼 계산식도 됩니다\n'
                      '· 메모에 #여행 처럼 쓰면 통계 › 태그에서 모아 봅니다\n'
                      '· Enter=다음 칸, F5=저장, Delete=고른 내역 삭제 (여러 줄 가능)')
        set_tone(tips, 'note')
        tips.setWordWrap(True)
        bl.addWidget(tips)

        self.month_lbl = QLabel()
        self.month_lbl.setWordWrap(True)          # 금액이 길어도 화면 폭을 넓히지 않고 줄바꿈
        self.bal_lbl = QLabel()
        self.bal_lbl.setStyleSheet('font-weight:bold')
        self.trash_btn = button('휴지통', self.open_trash, f'지운 내역을 {TR.KEEP_DAYS}일 동안 보관했다가 되살립니다')
        left = QWidget()
        self.left_lay = ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.day_btn = button('같은 날 순서…', self.day_order, '고른 내역이 있는 날의 내역 순서 바꾸기 (PC·휴대폰 같은 자료 파일에 저장)')
        self.csv_btn = button('CSV', lambda: export_csv(self, self.table, '가계부내역'))
        self.print_btn = button('인쇄', lambda: print_table(self, self.table, self._title()))
        top_row = _row(self.nav, self.all_chk, self.desc_chk, 'stretch', self.day_btn, self.csv_btn, self.print_btn)
        self.top_row = top_row
        bottom = QWidget()
        bot = QHBoxLayout(bottom)
        bot.setContentsMargins(0, 0, 0, 0)
        bot.addWidget(self.month_lbl, 1)
        bot.addWidget(self.bal_lbl, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        bot.addWidget(self.trash_btn, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self.parts = {'nav': top_row, 'table': self.table, 'summary': bottom}

        # ── 피드·타임라인: 가운데 칸 (위 덩어리 + 표가 같이 스크롤) + 오른쪽 칸 ──
        self.sns_prof = ProfileHeader()
        self.sns_prof.avatar_clicked.connect(self._open_deco)
        self.sns_pin = PinnedPost()
        self.sns_hl = Highlights()
        self.sns_hl.new_clicked.connect(self.new)
        self.sns_hl.code_clicked.connect(self._search_code)
        self.sns_tabs = SnsTabs()
        self.sns_tabs.clicked.connect(self._tab)
        self.sns_trends = Trends()
        self.sns_trends.code_clicked.connect(self._search_code)
        self.sns_trends.hide()
        self.sns_tools = []
        for ic, tip, fn in (('sort', '같은 날 순서 바꾸기 (고른 내역이 있는 날)', self.day_order), ('download', 'CSV로 저장', self.csv_btn.click),
                            ('print', '인쇄', self.print_btn.click), ('trash', '휴지통 (지운 내역 되살리기)', self.open_trash)):
            tb = QToolButton()
            tb.setObjectName('SnsTool')
            tb.setToolTip(tip)
            tb.setAutoRaise(True)
            tb.clicked.connect(fn)
            tb.setProperty('ic', ic)
            self.sns_tools.append(tb)
        self.sns_month = QWidget()
        mr = QHBoxLayout(self.sns_month)
        mr.setContentsMargins(16, 6, 16, 6)
        mr.addStretch(1)
        self.sns_month_box = QWidget()
        self.sns_month_box.setMaximumWidth(POST_W)
        mb = QHBoxLayout(self.sns_month_box)
        mb.setContentsMargins(0, 0, 0, 0)
        self.sns_month_box_lay = mb
        self.sns_spacer = QWidget()                    # 달 이동과 도구 단추 사이 빈칸
        mb.addWidget(self.sns_spacer, 1)
        for tb in self.sns_tools:
            mb.addWidget(tb)
        mr.addWidget(self.sns_month_box, 10)
        mr.addStretch(1)
        self.sns_inner = QWidget()
        self.sns_inner.setObjectName('SnsCol')
        self.sns_inner_lay = QVBoxLayout(self.sns_inner)
        self.sns_inner_lay.setContentsMargins(0, 0, 0, 0)
        self.sns_inner_lay.setSpacing(0)
        self.sns_scroll = QScrollArea()
        self.sns_scroll.setWidgetResizable(True)
        self.sns_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.sns_scroll.setWidget(self.sns_inner)
        self.sns_center = QWidget()
        self.sns_center.setObjectName('SnsCol')
        sc = QVBoxLayout(self.sns_center)
        sc.setContentsMargins(0, 0, 0, 0)
        sc.setSpacing(0)
        self.sns_center_lay = sc
        sc.addWidget(self.sns_scroll, 1)
        self.sns_center.hide()

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.sns_trends)
        rl.addWidget(box, 1)
        self.budget = X.BudgetCard(self)
        rl.addWidget(self.budget)
        self.right_lay = rl
        for k in T.ledger_layout():
            if k in self.parts:
                ll.addWidget(self.parts[k], 1 if k == 'table' else 0)
        # 오른쪽 칸(입력 상자 + 예산 막대)은 세로로 넘치면 스크롤 — 창이 낮아도 입력 칸이 눌려 찌그러지지 않게
        side = _SideScroll()
        side.setWidget(right)
        self.split = split = QSplitter()
        split.addWidget(left)
        split.addWidget(side)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        self.left_w, self.box_w = left, side
        self.layout_key = None
        self.page_lay = lay = QVBoxLayout(self)
        lay.addWidget(split)
        QShortcut(QKeySequence('F5'), self, activated=self.save)
        QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), self.table, activated=self.delete)
        for w in (self.form.item, self.form.income, self.form.expense, self.form.memo):
            w.returnPressed.connect(self.focusNextChild)

    def _title(self):
        name = self.app.ledger_name()
        return f'{name} — 전체 내역' if self.all_chk.isChecked() else f'{name} — {self.nav.y}년 {self.nav.m}월 내역'

    def _sns(self):
        return T.layout_of(T.current()[0])

    def apply_page_layout(self):
        """설정의 화면 구성 순서·입력 상자 위치·테마 모양(표 / 피드 / 타임라인)을 적용 (바뀌었을 때만)"""
        sns = self._sns()
        key = (tuple(T.ledger_layout()), T.input_side(), sns)
        if key == self.layout_key:
            return
        self.layout_key = key
        ll = self.left_lay
        for w in list(self.parts.values()) + [self.sns_center]:
            ll.removeWidget(w)
        for w in (self.sns_prof, self.sns_pin, self.sns_hl, self.sns_month, self.sns_tabs, self.table):
            self.sns_inner_lay.removeWidget(w)
            self.sns_center_lay.removeWidget(w)
        t = self.table
        if sns:
            for w in self.parts.values():
                w.hide()
            self.sns_month_box_lay.insertWidget(0, self.nav)
            if self.sns_month_box_lay.indexOf(self.sns_spacer) < 0:
                self.sns_month_box_lay.insertWidget(1, self.sns_spacer, 1)
            for w in (self.all_chk, self.desc_chk):
                w.hide()
            parts = {'summary': self.sns_prof if sns == 'feed' else self.sns_pin, 'nav': self.sns_month,
                     'stories': self.sns_hl if sns == 'feed' else None, 'table': self.table}
            for k in key[0]:
                if k == 'table' and sns == 'feed':
                    self.sns_inner_lay.addWidget(self.sns_tabs)     # 탭은 목록 바로 위
                if parts.get(k) is not None:
                    self.sns_inner_lay.addWidget(parts[k])
            if sns == 'timeline':
                self.sns_center_lay.insertWidget(0, self.sns_tabs)  # 타임라인 탭은 맨 위에 붙어 있음
            self.sns_inner_lay.addStretch(0)
            for w in (self.sns_prof, self.sns_pin, self.sns_hl):
                w.setVisible(w in parts.values())
            self.sns_tabs.show()
            self.sns_month.show()
            self.table.show()
            ll.addWidget(self.sns_center, 1)
            self.sns_center.show()
            self.sns_trends.setVisible(sns == 'timeline' and 'stories' in key[0])
            t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            t.setFrameShape(QFrame.Shape.NoFrame)
            t.setStyleSheet('QTableView { border: none; background: transparent; }')
            self.page_lay.setContentsMargins(0, 0, 0, 0)
            self.right_lay.setContentsMargins(12, 12, 12, 12)
        else:
            self.sns_center.hide()
            self.sns_trends.hide()
            self.top_row.layout().insertWidget(0, self.nav)
            for w in (self.all_chk, self.desc_chk):
                w.show()
            for k in key[0]:
                if k in self.parts:
                    ll.addWidget(self.parts[k], 1 if k == 'table' else 0)
                    self.parts[k].show()
            t.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            t.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            t.setFrameShape(QFrame.Shape.StyledPanel)
            t.setStyleSheet('')
            t.setMinimumHeight(0)
            t.setMaximumHeight(16777215)
            m = self.style().pixelMetric(self.style().PixelMetric.PM_LayoutLeftMargin)
            self.page_lay.setContentsMargins(m, m, m, m)
            self.right_lay.setContentsMargins(0, 0, 0, 0)
        want = [self.box_w, self.left_w] if key[1] == 'left' else [self.left_w, self.box_w]
        if [self.split.widget(0), self.split.widget(1)] != want:
            self.split.insertWidget(0, want[0])
        self.split.setStretchFactor(self.split.indexOf(self.left_w), 3)
        self.split.setStretchFactor(self.split.indexOf(self.box_w), 1)

    def refresh(self):
        self.apply_page_layout()
        lid = self.app.lid
        self.form.load(lid, editing=bool(self.editing))
        y, m = self.nav.y, self.nav.m
        self.nav.setEnabled(not self.all_chk.isChecked())
        if self.all_chk.isChecked():
            rows = L.entries_with_balance(self.con, lid)
        else:
            rows = L.entries_with_balance(self.con, lid, dt.date(y, m, 1), dt.date(y, m, month_end(y, m)))
        end_bal = {str(r['date']): b for r, b in rows}          # 그날 마지막 잔액 (날짜 순서대로 계산된 값)
        if self.desc_chk.isChecked():           # 최근 날짜 위로 (같은 날 순서를 정한 날은 그 순서 그대로)
            rows = O.apply_day_order(rows, O.day_orders(self.con, lid), desc=True)
        cmap = L.category_map(self.con, lid)
        emap = E.emoji_map(self.con, lid)
        pmap = M.pay_map(self.con)
        self.table.setRowCount(0)               # 줄 높이를 처음 상태로 (테마를 바꿨을 때)
        fill(self.table, [[cell(r['date'], CENTER, data=r['id']), cell(r['item']),
                           money_cell(r['income'], 'in'), money_cell(r['expense'], 'out'),
                           money_cell(bal, blank_zero=False), cell(MU.cat_label(emap, cmap, r['code'])), cell(r['memo']),
                           cell(M.pay_label(pmap, r['pay']))]
                          for r, bal in rows])
        n_trash = TR.count(self.con, lid)
        self.trash_btn.setText(f'휴지통 {n_trash}' if n_trash else '휴지통')
        self.photo_counts = AT.counts(self.con, [r['id'] for r, _b in rows])
        if self.photo_counts:                   # 사진 붙은 내역: 품목 칸에 사진기 표시
            ic = X.camera_icon()
            for i, (r, _b) in enumerate(rows):
                if r['id'] in self.photo_counts:
                    self.table.item(i, 1).setIcon(ic)
                    self.table.item(i, 1).setToolTip(f"사진 {self.photo_counts[r['id']]}장 — 입력 상자의 [사진]에서 보기")
        self.sns_delegate.photos = self.photo_counts
        self._photo_label()                     # 테마가 바뀌었을 수 있어 사진기 색도 다시
        self.budget.setVisible(T.pref('budget_card'))
        if self.budget.isVisible():
            self.budget.load(lid, y, m)
        s, e = dt.date(y, m, 1), dt.date(y, m, month_end(y, m))
        inc, exp = L.totals(self.con, lid, s, e)
        bal = L.current_balance(self.con, lid, dt.date.today())
        self._apply_layout(T.current()[0], rows, cmap, end_bal, (inc, exp, bal))
        self.month_lbl.setText(f'이번 달 요약 ({y}년 {m}월)   수입: {fmt_money(inc)}   지출: {fmt_money(exp)}   '
                               f'차액: {fmt_money(inc - exp)}')
        self.bal_lbl.setText(f'현재 잔액(오늘까지): {fmt_money(bal)}원')
        if self.editing and not L.get_entry(self.con, self.editing):
            self.new()

    def _apply_layout(self, theme, rows, cmap, end_bal, sums):
        """피드·타임라인 테마면 표를 게시물/짧은 글 모양으로 (칸 하나에 그리기) + 위 덩어리 채우기, 아니면 원래 표로."""
        t = self.table
        sns = theme in T.SNS_THEMES
        hh = t.horizontalHeader()
        for col in range(t.columnCount()):
            t.setColumnHidden(col, sns and col != C_ITEM)
        hh.setVisible(not sns)
        t.setShowGrid(not sns)
        t.setAlternatingRowColors(not sns)
        if not sns:
            t.setItemDelegateForColumn(C_ITEM, t.itemDelegate())
            t.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
            hh.setSectionResizeMode(C_ITEM, QHeaderView.ResizeMode.ResizeToContents)
            hh.setSectionResizeMode(C_MEMO, QHeaderView.ResizeMode.Stretch)
            return
        days = {}
        for r, _b in rows:
            d = str(r['date'])
            x = days.setdefault(d, {'inc': 0, 'exp': 0, 'n': 0, 'first': r['item'], 'bal': end_bal.get(d, 0)})
            x['inc'] += r['income'] or 0
            x['exp'] += r['expense'] or 0
            x['n'] += 1
        dg = self.sns_delegate
        dg.theme, dg.days = theme, days
        dg.ledger_name, dg.minimi = self.app.ledger_name(), T.pref('minimi')
        t.setItemDelegateForColumn(C_ITEM, dg)
        t.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        hh.setSectionResizeMode(C_MEMO, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(C_ITEM, QHeaderView.ResizeMode.Stretch)
        self._sns_heights()
        # 위 덩어리
        inc, exp, bal = sums
        today = dt.date.today()
        _ti, texp = L.totals(self.con, self.app.lid, today, today)
        y, m = self.nav.y, self.nav.m
        common = dict(minimi=T.pref('minimi'), name=self.app.ledger_name(), inc=inc, exp=exp, bal=bal, texp=texp,
                      month=m, mood=T.pref('mood'))
        self.sns_prof.set_data(motto=T.pref('motto').strip(), **common)
        self.sns_pin.set_data(ym=f'{y}.{m}', n=len(rows), n_in=sum(1 for r, _b in rows if r['income']),
                              n_out=sum(1 for r, _b in rows if r['expense']), **common)
        by = {}
        for r, _b in rows:
            if r['expense']:
                v = by.setdefault(r['code'], [0, 0])
                v[0] += r['expense']
                v[1] += 1
        top = sorted(by.items(), key=lambda kv: -kv[1][0])
        emap = E.emoji_map(self.con, self.app.lid)
        self.sns_hl.set_items([(k, MU.cat_label(emap, cmap, k), v[0]) for k, v in top[:14]])
        period = '전체 기간' if self.all_chk.isChecked() else f'{m}월'
        self.sns_trends.set_items([(k, MU.cat_label(emap, cmap, k), v[0], v[1]) for k, v in top[:4]], f'{period}에 많이 쓴 곳')
        self.sns_trends.setVisible(T.layout_of(theme) == 'timeline' and bool(top) and 'stories' in T.ledger_layout())
        desc = self.desc_chk.isChecked()
        al = self.all_chk.isChecked()
        if T.layout_of(theme) == 'feed':
            self.sns_tabs.set_tabs([('month', 'grid', f'{m}월', not al, True), ('all', 'all', '전체 기간', al, True),
                                    ('desc', 'sort', '최신순' if desc else '오래된순', False, True)], 'feed')
        else:
            self.sns_tabs.set_tabs([('month', None, f'{m}월', not al, True), ('all', None, '전체 기간', al, True),
                                    ('desc', 'sort', '', desc, False)], 'timeline')
        c = T.sns_colors(theme)
        for tb in self.sns_tools:
            tb.setIcon(QIcon(I.pixmap(tb.property('ic'), 22, c['ink'])))
            tb.setIconSize(QSize(22, 22))

    def _sns_heights(self):
        """줄 높이를 그림에 맞추고, 표 높이를 내용 전체로 (가운데 칸 전체가 같이 스크롤)"""
        t = self.table
        t.setUpdatesEnabled(False)
        total = 0
        for i in range(t.rowCount()):
            h = self.sns_delegate.row_height(i)
            t.setRowHeight(i, h)
            total += h
        t.setUpdatesEnabled(True)
        t.setFixedHeight(max(total + 2 * t.frameWidth() + 4, 120))

    def eventFilter(self, obj, ev):
        if self._sns() and obj is self.table and ev.type() == QEvent.Type.Resize and T.layout_of(T.current()[0]) == 'timeline':
            if ev.oldSize().width() != ev.size().width():
                self._sns_heights()
        if self._sns() and obj is self.table.viewport():
            if ev.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove, QEvent.Type.MouseButtonDblClick):
                pos = ev.position()
                row = self.table.rowAt(int(pos.y()))
                hit = self.sns_delegate.hit_test(row, pos) if row >= 0 else None
                if ev.type() == QEvent.Type.MouseMove:
                    obj.setCursor(Qt.CursorShape.PointingHandCursor if hit else Qt.CursorShape.ArrowCursor)
                    return False
                if hit and ev.button() == Qt.MouseButton.LeftButton:
                    if ev.type() == QEvent.Type.MouseButtonPress:
                        self.sns_action(hit[0], hit[1], row, obj.mapToGlobal(pos.toPoint()))
                    return True
        return super().eventFilter(obj, ev)

    def sns_action(self, what, val, row=None, gpos=None):
        """게시물·글 속 아이콘: menu(⋯) add(이 날 새 내역) order(순서) cal(달력) edit(수정) copy(다시 입력)"""
        if what == 'menu':
            menu = QMenu(self)
            acts = [('이 날 새 내역', 'add'), ('이 날 내역 순서 바꾸기', 'order'), ('달력에서 이 날 보기', 'cal')]
            if self.sns_delegate.days.get(val, {}).get('n', 1) < 2:
                acts.pop(1)
            chosen = {menu.addAction(lab): k for lab, k in acts}
            a = menu.exec(gpos) if gpos else None
            if a in chosen:
                self.sns_action(chosen[a], val)
        elif what == 'add':
            self.new()
            self.form.date.set_date(dt.date.fromisoformat(val))
            self.form.item.setFocus()
        elif what == 'order':
            self.day_order(dt.date.fromisoformat(val))
        elif what == 'cal':
            cp = self.app.goto('CalendarPage')
            if cp is not None and hasattr(cp, 'show_date'):
                cp.show_date(dt.date.fromisoformat(val))
        elif what == 'edit':
            self.table.selectRow(val)
            self.form.item.setFocus()
        elif what == 'copy':
            it = self.table.item(val, 0)
            e = L.get_entry(self.con, it.data(Qt.ItemDataRole.UserRole)) if it else None
            if e:
                self.new()
                e = dict(e)
                e['date'] = dt.date.today()
                self.form.set_value(e)
                self.mode_lbl.setText(f"다시 입력: '{e['item']}' 을(를) 오늘 날짜로 새로 넣습니다 — 고친 뒤 저장")
                self.form.item.setFocus()

    def _tab(self, key):
        if key == 'month':
            self.all_chk.setChecked(False)
        elif key == 'all':
            self.all_chk.setChecked(True)
        elif key == 'desc':
            self.desc_chk.setChecked(not self.desc_chk.isChecked())

    def _search_code(self, code):
        sp = self.app.goto('SearchPage')
        if sp is None:
            return
        if self.all_chk.isChecked():
            sp.search_code(code)
        else:
            y, m = self.nav.y, self.nav.m
            sp.search_code(code, dt.date(y, m, 1), dt.date(y, m, month_end(y, m)))

    def _open_deco(self):
        sp = self.app.goto('SettingsPage')
        from .settings_page import ThemeTab
        for p in getattr(sp, 'parts', []):
            if isinstance(p, ThemeTab):
                sp.tabs.setCurrentWidget(p)

    def day_order(self, d=None):
        """고른 내역이 있는 날(또는 d)의 내역 순서 바꾸기"""
        if not isinstance(d, dt.date):
            ids = selected_ids(self.table)
            if not ids:
                info(self, '순서를 바꿀 날의 내역을 하나 고른 뒤 누르세요.')
                return
            e = L.get_entry(self.con, ids[0])
            d = dt.date.fromisoformat(str(e['date']))
        lid = self.app.lid
        rows = [r for r, _b in L.entries_with_balance(self.con, lid, d, d)]
        if len(rows) < 2:
            info(self, f'{d} 에는 내역이 하나뿐입니다.')
            return
        cmap = L.category_map(self.con, lid)
        items = [(r['id'], r['item'] or '(내용 없음)',
                  ' · '.join(x for x in (L.code_label(cmap, r['code']), f"+{fmt_money(r['income'])}" if r['income'] else '',
                                         f"-{fmt_money(r['expense'])}" if r['expense'] else '') if x)) for r in rows]
        what, keys = ask_order(self, f'{d} 내역 순서', items, '같은 날 안에서의 순서입니다. 잔액도 이 순서로 계산되고, '
                               '자료 파일에 저장되어 휴대폰판에서도 같은 순서로 보입니다.', '기본 순서로')
        if what == 'save':
            O.set_day_order(self.con, lid, d.isoformat(), [int(k) for k in keys])
        elif what == 'reset':
            O.set_day_order(self.con, lid, d.isoformat(), sorted(r['id'] for r in rows))
        else:
            return
        self.app.data_changed()

    def _selected(self):
        ids = selected_ids(self.table)
        if len(ids) == 1:
            e = L.get_entry(self.con, ids[0])
            if e:
                self.editing = e['id']
                self.form.set_value(e)
                self.mode_lbl.setText(f"선택한 내역 수정 중 ({e['date']} {e['item']}) — 저장하면 덮어씁니다")
                set_tone(self.mode_lbl, 'warn')
                self.save_btn.setText('수정 (F5)')      # 글자 폭을 '저장 (F5)' 와 같게 (입력 칸이 넓어져 화면 밖으로 밀리지 않게)
                self._photo_label()
                self._same_label(e['item'])
                # 가운데 칸이 통째로 스크롤되므로 고른 줄이 보이게. 화면 모양을 바꾸는 중(표를 옮기는 중)에는 건너뜀 —
                # 표가 가운데 칸 안에 없을 때 위치를 바꿔 계산하면 Qt 가 죽음
                if self._sns() and self.sns_inner.isAncestorOf(self.table):
                    r = self.table.currentRow()
                    if r >= 0:
                        y0 = self.table.mapTo(self.sns_inner, QPoint(0, self.table.rowViewportPosition(r))).y()
                        self.sns_scroll.ensureVisible(0, y0 + self.table.rowHeight(r) // 2, 0, self.table.rowHeight(r) // 2 + 20)

    def new(self):
        self.editing = None
        self.pending_photos = []
        self.table.clearSelection()
        self.form.clear()
        self.mode_lbl.setText('새 내역 입력')
        set_tone(self.mode_lbl, 'note')
        self.save_btn.setText('저장 (F5)')
        self._photo_label()
        self.same_btn.hide()
        self.form.item.setFocus()

    def _photo_label(self):
        n = len(AT.list_for(self.con, self.editing)) if self.editing else len(self.pending_photos)
        self.photo_btn.setText(f'사진 {n}' if n else '사진')
        c = T.sns_colors()                      # SNS 테마는 단추 글자색을 스타일시트로 정함 (팔레트는 그대로)
        self.photo_btn.setIcon(X.camera_icon(c['ink'] if c else self.palette().buttonText().color().name()))

    def photos(self):
        title = ''
        if self.editing:
            e = L.get_entry(self.con, self.editing)
            title = f"{e['date']} {e['item']}" if e else ''
        d = X.PhotoDialog(self, self.con, self.editing, None if self.editing else self.pending_photos, title)
        d.exec()
        if d.changed and self.editing:
            self.app.data_changed()
        self._photo_label()

    def paste_sms(self):
        d = X.SmsDialog(self, self.con, self.app.lid)
        if d.exec() and d.saved:
            self.app.data_changed()
            self._show_alerts(d.alerts, f'{d.saved}건을 넣었어요.')

    def _show_alerts(self, alerts, head=''):
        """저장 뒤 알림: 입력 상자 위 안내 줄에 (예산 80%·100% 넘음)"""
        if alerts:
            self.mode_lbl.setText(' '.join(([head] if head else []) + ['⚠ ' + a for a in alerts]))
            set_tone(self.mode_lbl, 'warn')
            self.app.statusBar().showMessage(alerts[-1], 10000)
        elif head:
            self.mode_lbl.setText(head)
            set_tone(self.mode_lbl, 'note')

    def _fill_fav_menu(self):
        m = self.fav_menu
        m.clear()
        lid = self.app.lid
        cmap = L.category_map(self.con, lid)
        favs = L.favorites(self.con, lid)
        for f in favs:
            a = m.addAction(X.favorite_label(cmap, f))
            a.triggered.connect(lambda _c=False, f=f: self.use_favorite(f))
        if not favs:
            a = m.addAction('(아직 없어요 — 입력 칸을 채운 뒤 아래에서 넣으세요)')
            a.setEnabled(False)
        m.addSeparator()
        m.addAction('지금 입력을 자주 쓰는 내역에 넣기', self.add_favorite)
        m.addAction('자주 쓰는 내역 정리…', lambda: X.FavoritesDialog(self, self.con, self.app.lid).exec())

    def use_favorite(self, f):
        d = self.form.date.date_()
        self.new()
        self.form.date.set_date(d)
        self.form.item.setText(f['item'])
        self.form.income.set_value(f['income'])
        self.form.expense.set_value(f['expense'])
        if f['code']:
            self.form.code.set_code(f['code'])
        self.form.pay.set_pay(_get(f, 'pay'))
        self.form.memo.setText(f['memo'] or '')
        self.mode_lbl.setText(f"자주 쓰는 내역 '{f['item']}' — 날짜·금액을 확인하고 저장하세요")
        (self.form.expense if f['expense'] or not f['income'] else self.form.income).setFocus()

    def add_favorite(self):
        try:
            v = self.form.value()
        except ValueError:
            error(self, '금액은 숫자로 입력하세요.')
            return
        if not v['item']:
            error(self, '먼저 내용과 금액·카테고리를 입력한 뒤 넣으세요.')
            self.form.item.setFocus()
            return
        L.save_favorite(self.con, self.app.lid, v)
        info(self, f"'{v['item']}' 을(를) 자주 쓰는 내역에 넣었습니다.\n[★ 자주 쓰는 내역]에서 고르면 칸이 한 번에 채워집니다.")

    def reset_state(self):
        self.new()

    def save(self):
        v = self.form.validate(self)
        if not v:
            return
        if self.editing:                       # 다른 장부의 내역을 덮어쓰지 않도록 다시 확인
            e = L.get_entry(self.con, self.editing)
            if not e or e['ledger_id'] != self.app.lid:
                self.editing = None
        before = X.spent_before(self.con, self.app.lid, v['code'], v['date'])
        before_m = X.month_before(self.con, self.app.lid, v['date'])
        if self.editing:
            L.update_entry(self.con, self.editing, v)
        else:
            eid = L.add_entry(self.con, self.app.lid, v)
            for data, name in self.pending_photos:
                AT.add(self.con, eid, data, name, commit=False)
            if self.pending_photos:
                self.con.commit()
            if not self.all_chk.isChecked() and (v['date'].year, v['date'].month) != (self.nav.y, self.nav.m):
                self.nav.set(v['date'].year, v['date'].month)
        alerts = [a for a in (X.alert_after(self.con, self.app.lid, v['code'], v['date'], before),
                              X.total_alert_after(self.con, self.app.lid, v['date'], before_m)) if a]
        self.app.data_changed()
        self.new()
        self._show_alerts(alerts)

    def delete(self):
        ids = selected_ids(self.table)
        if not ids:
            return
        extra = []                                 # 나눠 적은 내역: 함께 나눠 적은 나머지도 지울지
        for i in ids:
            extra += [x for x in M.split_group(self.con, i) if x not in ids and x not in extra]
        if extra:
            from PyQt6.QtWidgets import QMessageBox
            box = QMessageBox(QMessageBox.Icon.Question, '나눠 적은 내역', f'나눠 적은 내역입니다. 함께 나눠 적은 {len(extra)}건도 지울까요?',
                              parent=self)
            b_all = box.addButton(f'모두 지우기 ({len(ids) + len(extra)}건)', QMessageBox.ButtonRole.YesRole)
            b_one = box.addButton(f'고른 것만 ({len(ids)}건)', QMessageBox.ButtonRole.NoRole)
            box.addButton('취소', QMessageBox.ButtonRole.RejectRole)
            box.exec()
            if box.clickedButton() is b_all:
                ids = ids + extra
            elif box.clickedButton() is not b_one:
                return
        elif not confirm(self, f'선택한 내역 {len(ids)}건을 삭제할까요?\n(휴지통에 {TR.KEEP_DAYS}일 동안 보관됩니다)'):
            return
        L.delete_entries(self.con, ids)
        self.app.data_changed()
        self.new()
        self.app.statusBar().showMessage(f'{len(ids)}건을 휴지통으로 옮겼어요 — [휴지통]에서 {TR.KEEP_DAYS}일 안에 되살릴 수 있어요', 10000)

    def open_trash(self):
        d = MU.TrashDialog(self, self.con, self.app.lid)
        d.exec()
        self.app.data_changed()

    def _same_label(self, item):
        sp = M.same_place(self.con, self.app.lid, item, dt.date.today()) if item else None
        if sp and sp['count']:
            amt = f"{fmt_money(sp['expense'])}원" if sp['expense'] or not sp['income'] else f"수입 {fmt_money(sp['income'])}원"
            short = item if len(item) <= 12 else item[:11] + '…'
            self.same_btn.setText(f"'{short}' 최근 3개월 {sp['count']}건 · {amt} ›")
            self.same_btn.setToolTip(f"'{item}' 의 최근 3개월 내역과 합계")
            self.same_btn.show()
        else:
            self.same_btn.hide()

    def same_place(self):
        item = self.form.item.text().strip()
        if item:
            MU.SamePlaceDialog(self, self.con, self.app.lid, item).exec()

    def foreign(self):
        try:
            v = self.form.value()
        except ValueError:
            v = {'income': 0, 'expense': 0}
        d = MU.FxDialog(self, self.con, expense=not (v['income'] and not v['expense']))
        if not d.exec():
            return
        (self.form.expense if d.expense else self.form.income).set_value(d.won)
        (self.form.income if d.expense else self.form.expense).set_value(0)
        memo = self.form.memo.text().strip()
        self.form.memo.setText(f'{memo} · {d.note}' if memo else d.note)

    def split_entry(self):
        if self.editing:
            info(self, '나눠 적기는 새 내역에서 씁니다. [새 내역]을 누른 뒤 전체 금액을 넣고 다시 누르세요.')
            return
        v = self.form.validate(self)
        if not v:
            return
        d = MU.SplitDialog(self, self.con, self.app.lid, v)
        if d.exec() and d.ids:
            self.app.data_changed()
            self.new()
            self._show_alerts([], f'{len(d.ids)}달로 나눠 넣었어요.')


def _get(row, key, default=''):
    """sqlite Row·dict 어느 쪽이든 (예전 자료에 없는 칸이면 default)"""
    try:
        v = row[key]
    except (KeyError, IndexError):
        return default
    return default if v is None else v


class _SideScroll(QScrollArea):
    """오른쪽 칸 스크롤: 폭은 내용의 최소 폭(가로 스크롤 없음), 배경은 투명 (테마 배경이 그대로 보이게)"""
    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setObjectName('SideScroll')
        self.setStyleSheet('QScrollArea#SideScroll { background: transparent; } '
                           'QScrollArea#SideScroll > QWidget > QWidget { background: transparent; }')
        self.viewport().setAutoFillBackground(False)

    def _extra(self):
        return self.verticalScrollBar().sizeHint().width() + 2 * self.frameWidth()

    def minimumSizeHint(self):
        w = self.widget()
        return QSize(w.minimumSizeHint().width() + self._extra(), 120) if w else super().minimumSizeHint()

    def sizeHint(self):
        w = self.widget()
        return QSize(w.sizeHint().width() + self._extra(), w.sizeHint().height()) if w else super().sizeHint()


def _row(*widgets):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    for x in widgets:
        if x == 'stretch':
            lay.addStretch(1)
        else:
            lay.addWidget(x)
    return w
