"""고정 수입·지출 (원본 '예약 설정': 매달·매주·매년 자동 입력) + 시작 시 '오늘까지 들어갈 것' 확인창 + 고정비 한눈에."""
import datetime as dt

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QSpinBox, QSplitter, QVBoxLayout, QWidget)

from ..services import ledger as L
from ..services import recurring as R
from ..util import fmt_money
from .widgets import (CENTER, CodeCombo, DateEdit, MoneyEdit, PayCombo, button, cell, confirm, error, export_csv, fill, h,
                      make_table, money_cell, selected_ids)
from ..services import money as M
from ..services import catemoji as E
from ..services.insights import period_of
from ..services.reports import settle_day
from .money_ui import fixed_html


class PendingDialog(QDialog):
    """원본의 '오늘까지 자동으로 입력될 예약설정 내용' / '오늘 이후로 남아있는 이달의 예약 내용'."""
    def __init__(self, parent, con, lid, due, later):
        super().__init__(parent)
        self.con, self.lid, self.due = con, lid, due
        self.setWindowTitle('고정 수입·지출 자동 입력')
        cmap = L.category_map(con, lid)
        self.t1 = make_table(['입력', '날짜', '내용', '수입', '지출', '카테고리', '메모'], stretch=6)
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
        t2 = make_table(['날짜', '내용', '수입', '지출', '카테고리'], stretch=4)
        fill(t2, [[cell(it['date'].isoformat(), CENTER), cell(it['rule']['item']), money_cell(it['rule']['income'], 'in'),
                   money_cell(it['rule']['expense'], 'out'), cell(L.code_label(cmap, it['rule']['code']))]
                  for it in later])
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f'<b>오늘까지 들어갈 고정 수입·지출 ({len(due)}건)</b> — 넣을 것만 체크하세요' +
                             (f'<br><span style="color:#b8322a">이번 달 이전 날짜 {old}건은 기본으로 체크하지 않았습니다 '
                              '(이미 직접 입력했을 수 있음)</span>' if old else '')))
        lay.addWidget(self.t1, 2)
        lay.addWidget(QLabel(f'이번 달에 아직 남은 고정 수입·지출 ({len(later)}건, 그날이 되면 들어감)'))
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
        if skip and not confirm(self, f'{len(items)}건을 가계부에 입력하지 않고 "건너뜀"으로 기록할까요?\n'
                                      '(다음부터 다시 묻지 않습니다)'):
            return
        R.apply(self.con, self.lid, items, skip=skip)
        self.accept()            # 체크하지 않은 항목은 다음에 다시 물어봄


class RecurringPage(QWidget):
    title = '고정 수입·지출'

    def __init__(self, app):
        super().__init__()
        self.app, self.con = app, app.con
        self.editing = None
        self.table = make_table(['언제', '내용', '수입', '지출', '카테고리', '결제수단', '시작일', '끝나는 날', '메모'],
                                stretch=8)
        self.table.itemSelectionChanged.connect(self._selected)
        self.item = QLineEdit()
        self.income, self.expense = MoneyEdit(), MoneyEdit()
        self.code = CodeCombo(self.con)
        self.pay = PayCombo(self.con)
        self.cycle = QComboBox()                   # 매달 · 매주 · 2주마다 · 매년 (1.8.0)
        for t, v in (('매달', 'M:1'), ('매주', 'W:1'), ('2주마다', 'W:2'), ('4주마다', 'W:4'), ('매년', 'Y:1')):
            self.cycle.addItem(t, v)            # 글자로 저장 (튜플은 findData 로 못 찾음)
        self.cycle.currentIndexChanged.connect(self._cycle_changed)
        self.wday = QComboBox()
        self.wday.addItems([f'{w}요일' for w in '월화수목금토일'])
        self.ymonth = QSpinBox()
        self.ymonth.setRange(1, 12)
        self.ymonth.setSuffix('월')
        self.day = QSpinBox()
        self.day.setRange(1, 31)
        self.day.setSuffix('일')
        self.day.setToolTip('31일로 하면 말일 (짧은 달은 자동으로 말일)')
        self.start = DateEdit()
        self.end = DateEdit()
        self.cont = QCheckBox('계속 적용')
        self.cont.setChecked(True)
        self.end.setEnabled(False)
        self.cont.toggled.connect(lambda c: self.end.setEnabled(not c))
        self.memo = QLineEdit()
        box = QGroupBox('고정 수입·지출 추가·수정')
        f = QFormLayout(box)
        f.addRow('내용', self.item)
        f.addRow('수입 금액', self.income)
        f.addRow('지출 금액', self.expense)
        f.addRow('카테고리', self.code)
        f.addRow('결제수단', self.pay)
        f.addRow('반복', h(self.cycle, self.ymonth, self.wday, self.day, 'stretch'))
        f.addRow('시작일', self.start)
        f.addRow('끝나는 날', h(self.end, self.cont))
        f.addRow('메모', self.memo)
        self.save_btn = button('추가', self.save)
        f.addRow(h(self.save_btn, button('새로', self.new), button('삭제', self.delete)))
        self.log = make_table(['날짜', '내용', '수입', '지출', '상태'], stretch=1)
        log_box = QGroupBox('고른 항목이 들어간 기록 (참고용)')
        QVBoxLayout(log_box).addWidget(self.log)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(box)
        rl.addWidget(log_box, 1)
        self.sum_lbl = QLabel()
        self.fixed_lbl = QLabel()                  # 고정비 한눈에 (1.8.0)
        self.fixed_lbl.setWordWrap(True)
        fixed_box = QGroupBox('이번 달 고정비 한눈에')
        QVBoxLayout(fixed_box).addWidget(self.fixed_lbl)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(h(QLabel('<b>고정 수입·지출</b> — 정한 날마다 가계부에 저절로 들어갑니다'), 'stretch',
                       button('지금 넣을 것 확인', self.check_now), button('CSV', lambda: export_csv(self, self.table, '고정수입지출'))))
        ll.addWidget(fixed_box)
        ll.addWidget(self.table, 1)
        ll.addWidget(self.sum_lbl)
        sp = QSplitter()
        sp.addWidget(left)
        sp.addWidget(right)
        sp.setStretchFactor(0, 3)
        sp.setStretchFactor(1, 2)
        QHBoxLayout(self).addWidget(sp)
        self._cycle_changed()

    def refresh(self):
        self.code.load(self.app.lid, keep_unknown=bool(self.editing))
        self.pay.load()
        cmap = L.category_map(self.con, self.app.lid)
        pmap = M.pay_map(self.con)
        emap = E.emoji_map(self.con, self.app.lid)
        rules = R.rules(self.con, self.app.lid)
        fill(self.table, [[cell(R.rule_text(r), CENTER, data=r['id']), cell(r['item']), money_cell(r['income'], 'in'),
                           money_cell(r['expense'], 'out'), cell(E.deco(emap, r['code'], L.code_label(cmap, r['code']))),
                           cell(M.pay_label(pmap, r['pay'])),
                           cell(r['start'], CENTER), cell(R.end_of(r) or '계속', CENTER), cell(r['memo'])] for r in rules])
        monthly = [r for r in rules if R.cycle_of(r) == 'M']
        self.sum_lbl.setText(f"매달 것 합계  수입 {fmt_money(sum(r['income'] for r in monthly))}   "
                             f"지출 {fmt_money(sum(r['expense'] for r in monthly))}"
                             + ('   (매주·매년 것은 위 \'이번 달 고정비\'에 들어갈 날만큼 셈)' if len(monthly) < len(rules) else ''))
        sd = settle_day(self.con)
        y, m = period_of(dt.date.today(), sd)
        self.fixed_lbl.setText(fixed_html(self.con, self.app.lid, y, m, sd))
        self._selected()

    def cycle_value(self):
        """('M'|'W'|'Y', 몇 주마다)"""
        c, _, n = str(self.cycle.currentData() or 'M:1').partition(':')
        return c, int(n or 1)

    def _cycle_changed(self, *_):
        c, _n = self.cycle_value()
        self.wday.setVisible(c == 'W')
        self.day.setVisible(c != 'W')
        self.ymonth.setVisible(c == 'Y')

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
        self.pay.set_pay(r['pay'])
        c = R.cycle_of(r)
        want = f"{c}:{max(1, int(r['every'] or 1)) if c == 'W' else 1}"
        i = self.cycle.findData(want)
        if i < 0:                                   # 목록에 없는 주기(3주마다 등)는 그대로 보이게 더함
            self.cycle.addItem(R.rule_text(r).split(' ')[0], want)
            i = self.cycle.count() - 1
        self.cycle.setCurrentIndex(i)
        self.wday.setCurrentIndex(int(r['wday'] or 0) % 7)
        self.ymonth.setValue(int(r['ymonth'] or 1))
        self.day.setValue(r['day'])
        self.start.set_date(r['start'])
        end = R.end_of(r)
        self.cont.setChecked(not end)
        if end:
            self.end.set_date(end)
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
        self.cycle.setCurrentIndex(0)
        self.pay.set_pay('')
        self._cycle_changed()
        self.save_btn.setText('추가')
        fill(self.log, [])

    def save(self):
        try:
            inc, exp = self.income.value(), self.expense.value()
        except ValueError:
            error(self, '금액은 숫자로 입력하세요.')
            return
        if not self.item.text().strip() or not (inc or exp) or not self.code.code():
            error(self, '내용, 금액, 카테고리를 입력하세요.')
            return
        self._own()
        end = None if self.cont.isChecked() else self.end.date_()
        if end and end < self.start.date_():
            error(self, '끝나는 날이 시작일보다 빠릅니다.')
            return
        c, every = self.cycle_value()
        R.save_rule(self.con, self.app.lid, {'item': self.item.text().strip(), 'income': inc, 'expense': exp,
                                             'code': self.code.code(), 'day': self.day.value(),
                                             'start': self.start.date_(), 'end': end, 'memo': self.memo.text().strip(),
                                             'pay': self.pay.pay(), 'cycle': c, 'every': every,
                                             'wday': self.wday.currentIndex(), 'ymonth': self.ymonth.value()},
                    self.editing)
        self.new()
        self.refresh()
        self.check_now(quiet=True)

    def delete(self):
        if self._own() and confirm(self, '이 고정 수입·지출을 삭제할까요? (이미 가계부에 들어간 내역은 그대로 남습니다)'):
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
            info(self, '오늘까지 넣을 고정 수입·지출이 없습니다.' +
                 (f'\n이번 달에 남은 것: {len(later)}건' if later else ''))
