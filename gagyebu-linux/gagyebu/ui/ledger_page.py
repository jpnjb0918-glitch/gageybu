"""가계부 메인 화면: 내역 목록(잔액 포함) + 입력하기 + 이달의 현황."""
import datetime as dt

from PyQt6.QtCore import QEvent, QPoint, QSize, QStringListModel, Qt
from PyQt6.QtGui import QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QCompleter, QDialog, QDialogButtonBox, QFormLayout, QFrame,
                             QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QScrollArea, QSplitter,
                             QToolButton, QVBoxLayout, QWidget)

from .. import db
from .. import theme as T
from ..services import ledger as L
from ..util import fmt_money, month_end
from ..services import order as O
from .widgets import (CENTER, CodeCombo, DateEdit, MoneyEdit, MonthNav, ask_order, button, cell, confirm, error,
                      export_csv, fill, info, make_table, money_cell, print_table, selected_ids)
from . import icons as I
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
        self.memo = QLineEdit()
        self.completer = QCompleter()
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.item.setCompleter(self.completer)
        self.item.editingFinished.connect(self._auto_code)
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow('날짜', self.date)
        form.addRow('품목', self.item)
        form.addRow('수입 금액', self.income)
        form.addRow('지출 금액', self.expense)
        form.addRow('계정과목', self.code)
        form.addRow('메모', self.memo)

    def load(self, lid, editing=False):
        self.lid = lid
        self.code.load(lid, keep_unknown=editing)
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
                'expense': self.expense.value(), 'code': self.code.code(), 'memo': self.memo.text().strip()}

    def set_value(self, e):
        self.date.set_date(e['date'])
        self.item.setText(e['item'])
        self.income.set_value(e['income'])
        self.expense.set_value(e['expense'])
        self.code.set_code(e['code'], keep_unknown=True)
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
            error(parent, '품목을 입력하세요.')
            self.item.setFocus()
            return None
        if not v['income'] and not v['expense']:
            error(parent, '수입 또는 지출 금액을 입력하세요.')
            self.expense.setFocus()
            return None
        if not v['code']:
            error(parent, '계정과목을 선택하세요. (설정 → 계정과목에서 만들 수 있습니다)')
            return None
        return v


class EntryDialog(QDialog):
    def __init__(self, parent, con, lid, entry):
        super().__init__(parent)
        self.setWindowTitle('내역 수정')
        self.form = EntryForm(con)
        self.form.load(lid)
        self.form.set_value(entry)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
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
        self.copy_note = ''
        self.nav = MonthNav()
        self.nav.changed.connect(lambda *_: self.refresh())
        self.all_chk = QCheckBox('전체 기간')
        self.all_chk.toggled.connect(lambda *_: self.refresh())
        self.desc_chk = QCheckBox('최근 것을 위로')
        self.desc_chk.setChecked(True)
        self.desc_chk.toggled.connect(lambda *_: self.refresh())
        self.table = make_table(['날짜', '품목', '수입', '지출', '잔액', '계정과목', '메모'], stretch=6, multi=True)
        self.table.itemSelectionChanged.connect(self._selected)
        self.table.doubleClicked.connect(lambda *_: self.form.item.setFocus())
        self.sns_delegate = LedgerDelegate(self.table)      # 피드·타임라인 테마일 때만 씀
        self.table.viewport().installEventFilter(self)      # 그림 속 아이콘 누르기
        self.table.viewport().setMouseTracking(True)
        self.table.installEventFilter(self)                 # 폭이 바뀌면 줄 높이 다시 (타임라인 메모 줄바꿈)

        self.form = EntryForm(self.con)
        self.save_btn = button('저장 (F5)', self.save)
        self.save_btn.setDefault(True)
        self.new_btn = button('새로 입력', self.new)
        self.del_btn = button('삭제', self.delete)
        self.mode_lbl = QLabel('새 내역 입력')
        self.mode_lbl.setStyleSheet('color:#666')
        box = QGroupBox('입력하기')
        self.box = box
        bl = QVBoxLayout(box)
        bl.addWidget(self.mode_lbl)
        bl.addWidget(self.form)
        row = QHBoxLayout()
        row.addWidget(self.save_btn)
        row.addWidget(self.new_btn)
        row.addWidget(self.del_btn)
        bl.addLayout(row)
        bl.addStretch(1)
        tips = QLabel('· 품목을 예전과 같게 쓰면 계정이 자동 선택됩니다\n· Enter=다음 칸, F5=저장, Delete=선택 내역 삭제\n'
                      '· 여러 줄을 골라 한꺼번에 삭제할 수 있습니다')
        tips.setStyleSheet('color:#777')
        tips.setWordWrap(True)
        bl.addWidget(tips)

        self.month_lbl = QLabel()
        self.month_lbl.setWordWrap(True)          # 금액이 길어도 화면 폭을 넓히지 않고 줄바꿈
        self.bal_lbl = QLabel()
        self.bal_lbl.setStyleSheet('font-weight:bold')
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
                            ('print', '인쇄', self.print_btn.click)):
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
        self.sns_month_lay = mr
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
        self.right_lay = rl
        for k in T.ledger_layout():
            if k in self.parts:
                ll.addWidget(self.parts[k], 1 if k == 'table' else 0)
        self.split = split = QSplitter()
        split.addWidget(left)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        self.left_w, self.box_w = left, right
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
        self.table.setRowCount(0)               # 줄 높이를 처음 상태로 (테마를 바꿨을 때)
        fill(self.table, [[cell(r['date'], CENTER, data=r['id']), cell(r['item']),
                           money_cell(r['income'], 'in'), money_cell(r['expense'], 'out'),
                           money_cell(bal, blank_zero=False), cell(L.code_label(cmap, r['code'])), cell(r['memo'])]
                          for r, bal in rows])
        s, e = dt.date(y, m, 1), dt.date(y, m, month_end(y, m))
        inc, exp = L.totals(self.con, lid, s, e)
        bal = L.current_balance(self.con, lid, dt.date.today())
        self._apply_layout(T.current()[0], rows, cmap, end_bal, (inc, exp, bal))
        self.month_lbl.setText(f'이달의 현황 ({y}년 {m}월)   수입: {fmt_money(inc)}   지출: {fmt_money(exp)}   '
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
        self.sns_hl.set_items([(k, L.code_label(cmap, k), v[0]) for k, v in top[:14]])
        period = '전체 기간' if self.all_chk.isChecked() else f'{m}월'
        self.sns_trends.set_items([(k, L.code_label(cmap, k), v[0], v[1]) for k, v in top[:4]], f'{period}에 많이 쓴 곳')
        self.sns_trends.setVisible(T.layout_of(theme) == 'timeline' and bool(top) and 'stories' in T.ledger_layout())
        desc = self.desc_chk.isChecked()
        al = self.all_chk.isChecked()
        if T.layout_of(theme) == 'feed':
            self.sns_tabs.set_tabs([('month', 'grid', f'{m}월', not al, True), ('all', 'all', '전체 기간', al, True),
                                    ('desc', 'sort', '최근 것 위로' if desc else '오래된 것 위로', False, True)], 'feed')
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
        items = [(r['id'], r['item'] or '(품목 없음)',
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
                self.mode_lbl.setStyleSheet('color:#b8322a')
                self.save_btn.setText('수정 저장 (F5)')
                if self._sns():                       # 가운데 칸이 통째로 스크롤되므로 고른 줄이 보이게
                    r = self.table.currentRow()
                    if r >= 0:
                        y0 = self.table.mapTo(self.sns_inner, QPoint(0, self.table.rowViewportPosition(r))).y()
                        self.sns_scroll.ensureVisible(0, y0 + self.table.rowHeight(r) // 2, 0, self.table.rowHeight(r) // 2 + 20)

    def new(self):
        self.editing = None
        self.table.clearSelection()
        self.form.clear()
        self.mode_lbl.setText('새 내역 입력')
        self.mode_lbl.setStyleSheet('color:#666')
        self.save_btn.setText('저장 (F5)')
        self.form.item.setFocus()

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
        if self.editing:
            L.update_entry(self.con, self.editing, v)
        else:
            L.add_entry(self.con, self.app.lid, v)
            if not self.all_chk.isChecked() and (v['date'].year, v['date'].month) != (self.nav.y, self.nav.m):
                self.nav.set(v['date'].year, v['date'].month)
        self.app.data_changed()
        self.new()

    def delete(self):
        ids = selected_ids(self.table)
        if not ids:
            return
        if confirm(self, f'선택한 내역 {len(ids)}건을 삭제할까요?'):
            L.delete_entries(self.con, ids)
            self.app.data_changed()
            self.new()


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
