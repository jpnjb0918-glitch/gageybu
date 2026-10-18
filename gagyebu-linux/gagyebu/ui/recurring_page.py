"""예약 설정 (월 고정 수입·지출 자동입력) + 시작 시 '자동으로 입력될 예약 내용' 확인창."""
import datetime as dt

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
                             QSplitter, QVBoxLayout, QWidget)

from ..services import ledger as L
from ..services import recurring as R
from ..util import fmt_money
from .widgets import (CENTER, CodeCombo, DateEdit, MoneyEdit, button, cell, confirm, error, export_csv, fill, h,
                      make_table, money_cell, selected_ids)


class PendingDialog(QDialog):
    """원본의 '오늘까지 자동으로 입력될 예약설정 내용' / '오늘 이후로 남아있는 이달의 예약 내용'."""
    def __init__(self, parent, con, lid, due, later):
        super().__init__(parent)
        self.con, self.lid, self.due = con, lid, due
        self.setWindowTitle('예약된 수입·지출 자동입력')
        cmap = L.category_map(con, lid)
        self.t1 = make_table(['입력', '날짜', '품목', '수입', '지출', '계정과목', '비고'], stretch=6)
        rows = []
        month_start = dt.date.today().replace(day=1)
        old = 0
        for i, it in enumerate(due):
            r = it['rule']
            chk = cell('', CENTER, data=i)
            chk.setFlags(chk.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            recent = it['date'] >= month_start          # 지난달 이전 것은 이미 손으로 넣었을 수 있어 기본은 체크 해제
            old += not recent
            chk.setCheckState(Qt.CheckState.Checked if recent else Qt.CheckState.Unchecked)
            rows.append([chk, cell(it['date'].isoformat(), CENTER), cell(r['item']), money_cell(r['income'], 'in'),
                         money_cell(r['expense'], 'out'), cell(L.code_label(cmap, r['code'])), cell(r['memo'])])
        fill(self.t1, rows)
        t2 = make_table(['날짜', '품목', '수입', '지출', '계정과목'], stretch=4)
        fill(t2, [[cell(it['date'].isoformat(), CENTER), cell(it['rule']['item']), money_cell(it['rule']['income'], 'in'),
                   money_cell(it['rule']['expense'], 'out'), cell(L.code_label(cmap, it['rule']['code']))]
                  for it in later])
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f'<b>오늘까지 자동으로 입력될 예약 내용 ({len(due)}건)</b> — 입력할 것만 체크하세요' +
                             (f'<br><span style="color:#b8322a">이번 달 이전 날짜 {old}건은 기본으로 체크하지 않았습니다 '
                              '(이미 직접 입력했을 수 있음)</span>' if old else '')))
        lay.addWidget(self.t1, 2)
        lay.addWidget(QLabel(f'오늘 이후로 남아 있는 이달의 예약 내용 ({len(later)}건, 그날이 되면 입력)'))
        lay.addWidget(t2, 1)
        lay.addWidget(h('stretch', button('체크한 것 입력', self.apply_checked),
                        button('체크한 것 건너뛰기(입력 안 함)', lambda: self.apply_checked(skip=True)),
                        button('나중에', self.reject)))
        self.resize(820, 560)

    def _checked(self):
        out = []
        for r in range(self.t1.rowCount()):
            it = self.t1.item(r, 0)
            if it.checkState() == Qt.CheckState.Checked:
                out.append(self.due[it.data(Qt.ItemDataRole.UserRole)])
        return out

    def apply_checked(self, skip=False):
        items = self._checked()
        if not items:
            return
        if skip and not confirm(self, f'{len(items)}건을 장부에 입력하지 않고 "건너뜀"으로 기록할까요?\n'
                                      '(다음부터 다시 묻지 않습니다)'):
            return
        R.apply(self.con, self.lid, items, skip=skip)
        self.accept()            # 체크하지 않은 항목은 다음에 다시 물어봄


class RecurringPage(QWidget):
    title = '예약 설정'

    def __init__(self, app):
        super().__init__()
        self.app, self.con = app, app.con
        self.editing = None
        self.table = make_table(['자동입력일', '품목', '수입', '지출', '계정과목', '시작 적용일', '종료 적용일', '비고'],
                                stretch=7)
        self.table.itemSelectionChanged.connect(self._selected)
        self.item = QLineEdit()
        self.income, self.expense = MoneyEdit(), MoneyEdit()
        self.code = CodeCombo(self.con)
        self.day = QSpinBox()
        self.day.setRange(1, 31)
        self.day.setSuffix('일')
        self.day.setToolTip('31일로 하면 매달 말일 (짧은 달은 자동으로 말일)')
        self.start = DateEdit()
        self.end = DateEdit()
        self.cont = QCheckBox('계속 적용')
        self.cont.setChecked(True)
        self.end.setEnabled(False)
        self.cont.toggled.connect(lambda c: self.end.setEnabled(not c))
        self.memo = QLineEdit()
        box = QGroupBox('예약 추가·수정')
        f = QFormLayout(box)
        f.addRow('품목', self.item)
        f.addRow('수입 금액', self.income)
        f.addRow('지출 금액', self.expense)
        f.addRow('계정과목', self.code)
        f.addRow('자동입력일', self.day)
        f.addRow('시작 적용일', self.start)
        f.addRow('종료 적용일', h(self.end, self.cont))
        f.addRow('비고', self.memo)
        self.save_btn = button('예약 추가', self.save)
        f.addRow(h(self.save_btn, button('새로', self.new), button('삭제', self.delete)))
        self.log = make_table(['날짜', '품목', '수입', '지출', '상태'], stretch=1)
        log_box = QGroupBox('선택한 예약의 자동입력 기록 (참고용)')
        QVBoxLayout(log_box).addWidget(self.log)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(box)
        rl.addWidget(log_box, 1)
        self.sum_lbl = QLabel()
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(h(QLabel('<b>예약으로 설정된 내용</b> — 매달 지정한 날에 장부에 자동 입력됩니다'), 'stretch',
                       button('지금 입력할 예약 확인', self.check_now), button('CSV', lambda: export_csv(self, self.table, '예약설정'))))
        ll.addWidget(self.table, 1)
        ll.addWidget(self.sum_lbl)
        sp = QSplitter()
        sp.addWidget(left)
        sp.addWidget(right)
        sp.setStretchFactor(0, 3)
        sp.setStretchFactor(1, 2)
        QHBoxLayout(self).addWidget(sp)

    def refresh(self):
        self.code.load(self.app.lid, keep_unknown=bool(self.editing))
        cmap = L.category_map(self.con, self.app.lid)
        rules = R.rules(self.con, self.app.lid)
        fill(self.table, [[cell(f"{r['day']}일", CENTER, data=r['id']), cell(r['item']), money_cell(r['income'], 'in'),
                           money_cell(r['expense'], 'out'), cell(L.code_label(cmap, r['code'])), cell(r['start'], CENTER),
                           cell(r['end'] or '계속 적용', CENTER), cell(r['memo'])] for r in rules])
        self.sum_lbl.setText(f"매달 합계  수입 {fmt_money(sum(r['income'] for r in rules))}   "
                             f"지출 {fmt_money(sum(r['expense'] for r in rules))}")
        self._selected()

    def _selected(self):
        ids = selected_ids(self.table)
        if not ids:
            fill(self.log, [])
            return
        r = self.con.execute('SELECT * FROM recurring WHERE id=?', (ids[0],)).fetchone()
        if not r:
            return
        self.editing = r['id']
        self.item.setText(r['item'])
        self.income.set_value(r['income'])
        self.expense.set_value(r['expense'])
        self.code.set_code(r['code'], keep_unknown=True)
        self.day.setValue(r['day'])
        self.start.set_date(r['start'])
        self.cont.setChecked(not r['end'])
        if r['end']:
            self.end.set_date(r['end'])
        self.memo.setText(r['memo'])
        self.save_btn.setText('수정 저장')
        fill(self.log, [[cell(x['date'], CENTER), cell(x['item']), money_cell(x['income'], 'in'),
                         money_cell(x['expense'], 'out'), cell('건너뜀' if x['skipped'] else '입력됨', CENTER)]
                        for x in R.log(self.con, rid=r['id'])])

    def reset_state(self):
        self.new()

    def _own(self):
        """수정 중인 예약이 지금 장부의 것인지 확인."""
        if not self.editing:
            return False
        r = self.con.execute('SELECT ledger_id FROM recurring WHERE id=?', (self.editing,)).fetchone()
        if not r or r['ledger_id'] != self.app.lid:
            self.editing = None
            return False
        return True

    def new(self):
        self.editing = None
        self.table.clearSelection()
        for w in (self.item, self.income, self.expense, self.memo):
            w.clear()
        self.start.set_date(dt.date.today())
        self.cont.setChecked(True)
        self.save_btn.setText('예약 추가')
        fill(self.log, [])

    def save(self):
        try:
            inc, exp = self.income.value(), self.expense.value()
        except ValueError:
            error(self, '금액은 숫자로 입력하세요.')
            return
        if not self.item.text().strip() or not (inc or exp) or not self.code.code():
            error(self, '품목, 금액, 계정과목을 입력하세요.')
            return
        self._own()
        end = None if self.cont.isChecked() else self.end.date_()
        if end and end < self.start.date_():
            error(self, '종료 적용일이 시작 적용일보다 빠릅니다.')
            return
        R.save_rule(self.con, self.app.lid, {'item': self.item.text().strip(), 'income': inc, 'expense': exp,
                                             'code': self.code.code(), 'day': self.day.value(),
                                             'start': self.start.date_(), 'end': end, 'memo': self.memo.text().strip()},
                    self.editing)
        self.new()
        self.refresh()
        self.check_now(quiet=True)

    def delete(self):
        if self._own() and confirm(self, '이 예약을 삭제할까요? (이미 장부에 입력된 내역은 그대로 남습니다)'):
            R.delete_rule(self.con, self.editing)
            self.new()
            self.refresh()

    def check_now(self, quiet=False):
        due, later = R.pending(self.con, self.app.lid)
        if due:
            PendingDialog(self, self.con, self.app.lid, due, later).exec()
            self.app.data_changed()
        elif not quiet:
            from .widgets import info
            info(self, '오늘까지 입력할 예약 내용이 없습니다.' +
                 (f'\n이달에 남은 예약: {len(later)}건' if later else ''))
