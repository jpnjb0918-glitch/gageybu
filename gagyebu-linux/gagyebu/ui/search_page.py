"""검색: 기간·내용·카테고리·금액·결제수단 조건 (AND)."""
import datetime as dt

from PyQt6.QtWidgets import QCheckBox, QComboBox, QGridLayout, QGroupBox, QLabel, QLineEdit, QVBoxLayout, QWidget

from ..services import catemoji as E
from ..services import ledger as L
from ..services import money as M
from ..util import fmt_money
from .ledger_page import EntryDialog
from .widgets import (CENTER, CodePicker, DateEdit, MoneyEdit, PayCombo, button, cell, confirm, error, export_csv, fill, h,
                      make_table, money_cell, print_table, selected_ids)


class SearchPage(QWidget):
    title = '검색'

    def __init__(self, app):
        super().__init__()
        self.app, self.con = app, app.con
        self.codes = []
        t = dt.date.today()
        self.c_date = QCheckBox('기간')
        self.start, self.end = DateEdit(dt.date(t.year, 1, 1)), DateEdit(t)
        self.c_text = QCheckBox('내용·메모에 포함된 글자')
        self.text = QLineEdit()
        self.text.textEdited.connect(lambda s: self.c_text.setChecked(bool(s)))
        self.c_code = QCheckBox('카테고리')
        self.code_lbl = QLabel('(선택 안 함)')
        self.c_amt = QCheckBox('금액')
        self.side = QComboBox()
        self.side.addItems(['수입+지출', '수입', '지출'])
        self.op = QComboBox()
        self.op.addItems(list(L.AMOUNT_OPS))
        self.amount = MoneyEdit()
        self.amount.textEdited.connect(lambda s: self.c_amt.setChecked(bool(s)))
        self.c_pay = QCheckBox('결제수단')
        self.pay = PayCombo(self.con, none_text='(안 정한 것)')
        self.pay.activated.connect(lambda *_: self.c_pay.setChecked(True))
        self.order = QComboBox()
        self.order.addItems(['날짜', '내용', '수입', '지출', '카테고리 번호', '메모'])
        self.desc = QCheckBox('내림차순')
        g = QGroupBox('검색 조건 (체크한 조건을 모두 만족하는 내역)')
        gl = QGridLayout(g)
        gl.addWidget(self.c_date, 0, 0)
        gl.addWidget(h(self.start, '~', self.end, 'stretch'), 0, 1)
        gl.addWidget(self.c_text, 1, 0)
        gl.addWidget(self.text, 1, 1)
        gl.addWidget(self.c_code, 2, 0)
        gl.addWidget(h(button('카테고리 선택…', self.pick_codes), self.code_lbl, 'stretch'), 2, 1)
        gl.addWidget(self.c_amt, 3, 0)
        gl.addWidget(h(self.side, self.amount, self.op, 'stretch'), 3, 1)
        gl.addWidget(self.c_pay, 4, 0)
        gl.addWidget(h(self.pay, 'stretch'), 4, 1)
        gl.addWidget(QLabel('정렬'), 5, 0)
        gl.addWidget(h(self.order, self.desc, 'stretch', button('검색 실행', self.run)), 5, 1)
        self.text.returnPressed.connect(self.run)
        self.table = make_table(['날짜', '내용', '수입', '지출', '카테고리', '메모', '결제'], stretch=5, multi=True)
        self.table.doubleClicked.connect(lambda *_: self.edit())
        self.sum_lbl = QLabel()
        lay = QVBoxLayout(self)
        lay.addWidget(g)
        lay.addWidget(h(self.sum_lbl, 'stretch', button('수정', self.edit), button('삭제', self.delete),
                        button('CSV', lambda: export_csv(self, self.table, '검색결과')),
                        button('인쇄', lambda: print_table(self, self.table, '검색 결과', self.sum_lbl.text()))))
        lay.addWidget(self.table, 1)

    def reset_state(self):
        fill(self.table, [])
        self.sum_lbl.clear()

    def refresh(self):
        self.codes = [c for c in self.codes if c in L.category_map(self.con, self.app.lid)]
        self._code_text()
        self.pay.load()
        if self.table.rowCount():
            self.run()

    def search_code(self, code, start=None, end=None):
        """계정과목 하나(와 기간)로 바로 검색 (피드·타임라인의 계정 동그라미·트렌드에서)"""
        self.c_date.setChecked(bool(start))
        if start:
            self.start.set_date(start)
            self.end.set_date(end)
        self.c_text.setChecked(False)
        self.c_amt.setChecked(False)
        self.c_pay.setChecked(False)
        self.codes = [code]
        self.c_code.setChecked(True)
        self._code_text()
        self.run()

    def _code_text(self):
        self.code_lbl.setText(', '.join(self.codes) if self.codes else '(선택 안 함)')

    def pick_codes(self):
        d = CodePicker(self, self.con, self.app.lid, self.codes)
        if d.exec():
            self.codes = d.codes()
            self.c_code.setChecked(bool(self.codes))
            self._code_text()

    def run(self):
        try:
            amt = self.amount.value() if self.c_amt.isChecked() else None
        except ValueError:
            error(self, '금액은 숫자로 입력하세요.')
            return
        rows = L.search(self.con, self.app.lid,
                        start=self.start.date_() if self.c_date.isChecked() else None,
                        end=self.end.date_() if self.c_date.isChecked() else None,
                        text=self.text.text().strip() if self.c_text.isChecked() else None,
                        codes=self.codes if self.c_code.isChecked() and self.codes else None,
                        amount=amt, amount_side=self.side.currentText(), amount_op=self.op.currentText(),
                        order=['date', 'item', 'income', 'expense', 'code', 'memo'][self.order.currentIndex()],
                        desc=self.desc.isChecked(),
                        pays=[self.pay.pay()] if self.c_pay.isChecked() else None)
        cmap = L.category_map(self.con, self.app.lid)
        emap, pmap = E.emoji_map(self.con, self.app.lid), M.pay_map(self.con)
        fill(self.table, [[cell(r['date'], CENTER, data=r['id']), cell(r['item']), money_cell(r['income'], 'in'),
                           money_cell(r['expense'], 'out'), cell(E.deco(emap, r['code'], L.code_label(cmap, r['code']))),
                           cell(r['memo']), cell(M.pay_label(pmap, r['pay']))]
                          for r in rows])
        ti, te = sum(r['income'] for r in rows), sum(r['expense'] for r in rows)
        self.sum_lbl.setText(f'검색 결과 {len(rows):,}건   수입 합계 {fmt_money(ti)}   지출 합계 {fmt_money(te)}')

    def edit(self):
        ids = selected_ids(self.table)
        if len(ids) != 1:
            return
        e = L.get_entry(self.con, ids[0])
        d = EntryDialog(self, self.con, self.app.lid, e)
        if d.exec():
            L.update_entry(self.con, e['id'], d.v)
            self.app.data_changed()
            self.run()

    def delete(self):
        ids = selected_ids(self.table)
        if ids and confirm(self, f'선택한 내역 {len(ids)}건을 삭제할까요?\n(가계부 화면 [휴지통]에 30일 동안 보관됩니다)'):
            L.delete_entries(self.con, ids)
            self.app.data_changed()
            self.run()
