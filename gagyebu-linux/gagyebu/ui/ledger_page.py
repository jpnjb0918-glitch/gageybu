"""가계부 메인 화면: 내역 목록(잔액 포함) + 입력하기 + 이달의 현황."""
import datetime as dt

from PyQt6.QtCore import QStringListModel, Qt
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QCheckBox, QCompleter, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QSplitter, QVBoxLayout, QWidget)

from .. import db
from ..services import ledger as L
from ..util import fmt_money, month_end
from .widgets import (CENTER, CodeCombo, DateEdit, MoneyEdit, MonthNav, button, cell, confirm, error, export_csv,
                      fill, make_table, money_cell, print_table, selected_ids)


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

        self.form = EntryForm(self.con)
        self.save_btn = button('저장 (F5)', self.save)
        self.save_btn.setDefault(True)
        self.new_btn = button('새로 입력', self.new)
        self.del_btn = button('삭제', self.delete)
        self.mode_lbl = QLabel('새 내역 입력')
        self.mode_lbl.setStyleSheet('color:#666')
        box = QGroupBox('입력하기')
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
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(_row(self.nav, self.all_chk, self.desc_chk, 'stretch',
                          button('CSV', lambda: export_csv(self, self.table, '가계부내역')),
                          button('인쇄', lambda: print_table(self, self.table, self._title()))))
        ll.addWidget(self.table)
        bottom = QWidget()
        bot = QHBoxLayout(bottom)
        bot.setContentsMargins(0, 0, 0, 0)
        bot.addWidget(self.month_lbl, 1)
        bot.addWidget(self.bal_lbl, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        ll.addWidget(bottom)
        split = QSplitter()
        split.addWidget(left)
        split.addWidget(box)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        lay = QVBoxLayout(self)
        lay.addWidget(split)
        QShortcut(QKeySequence('F5'), self, activated=self.save)
        QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), self.table, activated=self.delete)
        for w in (self.form.item, self.form.income, self.form.expense, self.form.memo):
            w.returnPressed.connect(self.focusNextChild)

    def _title(self):
        name = self.app.ledger_name()
        return f'{name} — 전체 내역' if self.all_chk.isChecked() else f'{name} — {self.nav.y}년 {self.nav.m}월 내역'

    def refresh(self):
        lid = self.app.lid
        self.form.load(lid, editing=bool(self.editing))
        y, m = self.nav.y, self.nav.m
        self.nav.setEnabled(not self.all_chk.isChecked())
        if self.all_chk.isChecked():
            rows = L.entries_with_balance(self.con, lid)
        else:
            rows = L.entries_with_balance(self.con, lid, dt.date(y, m, 1), dt.date(y, m, month_end(y, m)))
        if self.desc_chk.isChecked():
            rows = rows[::-1]
        cmap = L.category_map(self.con, lid)
        fill(self.table, [[cell(r['date'], CENTER, data=r['id']), cell(r['item']),
                           money_cell(r['income'], 'in'), money_cell(r['expense'], 'out'),
                           money_cell(bal, blank_zero=False), cell(L.code_label(cmap, r['code'])), cell(r['memo'])]
                          for r, bal in rows])
        s, e = dt.date(y, m, 1), dt.date(y, m, month_end(y, m))
        inc, exp = L.totals(self.con, lid, s, e)
        self.month_lbl.setText(f'이달의 현황 ({y}년 {m}월)   수입: {fmt_money(inc)}   지출: {fmt_money(exp)}   '
                               f'차액: {fmt_money(inc - exp)}')
        self.bal_lbl.setText(f'현재 잔액(오늘까지): {fmt_money(L.current_balance(self.con, lid, dt.date.today()))}원')
        if self.editing and not L.get_entry(self.con, self.editing):
            self.new()

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
