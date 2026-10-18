"""자산관리: 은행통장·신용카드·증권·보험·부동산/기타 + 순자산 요약."""
import json

from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QLabel,
                             QLineEdit, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget)
from PyQt6.QtCore import Qt

from ..services import assets as A
from ..services import ledger as L
from ..util import fmt_money
from .widgets import (CENTER, CodeCombo, DateEdit, FormDialog, MoneyEdit, MonthNav, button, cell, confirm, error,
                      export_csv, fill, h, info, make_table, money_cell, selected_ids)

COLS = {
    'bank': ['은행명', '통장명', '예금주', '계좌번호', '잔액', '사용여부', '비고'],
    'securities': ['증권사', '계좌이름', '소유주', '추정 예수금', '평가금액', '최종 평가일', '비고'],
    'insurance': ['보험사명', '상품명', '계약자', '계약일', '납입보험료 누계', '계약상태', '비고'],
    'property': ['구분', '자산명', '소유주', '취득/평가금액', '대출금액', '최종 평가일', '비고'],
}
NOTE = {'bank': '사용중인 통장의 잔액(초기 잔액 + 입금 − 출금)이 자산으로 계산됩니다.',
        'securities': '평가금액만 자산으로 계산되고, 거래 내용은 기록용입니다.',
        'insurance': '보험은 자산으로 계산되지 않으며 거래 내용도 기록용입니다.',
        'property': '취득/평가금액은 자산, 대출금액은 부채로 계산됩니다. 거래 내용은 기록용입니다.'}


class LedgerLink(QWidget):
    """'장부에도 동시저장' 선택 칸."""
    def __init__(self, con, app, label='장부에도 동시저장'):
        super().__init__()
        self.con, self.app = con, app
        self.chk = QCheckBox(label)
        self.ledger = QComboBox()
        self.code = CodeCombo(con)
        self.ledger.currentIndexChanged.connect(lambda *_: self.code.load(self.ledger.currentData())
                                                if self.ledger.currentData() else None)
        f = QFormLayout(self)
        f.setContentsMargins(0, 0, 0, 0)
        f.addRow(self.chk)
        f.addRow('장부', self.ledger)
        f.addRow('계정과목', self.code)
        self.chk.toggled.connect(self._en)
        self._en(False)

    def _en(self, on):
        self.ledger.setEnabled(on)
        self.code.setEnabled(on)

    def load(self):
        cur = self.ledger.currentData() or self.app.lid
        self.ledger.blockSignals(True)
        self.ledger.clear()
        for r in L.ledgers(self.con):
            self.ledger.addItem(r['name'], r['id'])
        self.ledger.setCurrentIndex(max(0, self.ledger.findData(cur)))
        self.ledger.blockSignals(False)
        self.code.load(self.ledger.currentData())

    def target(self):
        if self.chk.isChecked() and self.code.code():
            return self.ledger.currentData(), self.code.code()
        return None, None


class AccountTab(QWidget):
    def __init__(self, page, kind):
        super().__init__()
        self.page, self.app, self.con, self.kind = page, page.app, page.con, kind
        self.list = make_table(COLS[kind], stretch=len(COLS[kind]) - 1)
        self.list.itemSelectionChanged.connect(self.load_txs)
        self.list.doubleClicked.connect(lambda *_: self.edit())
        self.txs = make_table(['거래일자', '적요', '입금액', '출금액', '잔액' if kind == 'bank' else '누계', '메모', '장부'],
                              stretch=5)
        self.txs.itemSelectionChanged.connect(self._tx_selected)
        self.date = DateEdit()
        self.summary = QLineEdit()
        self.dep, self.wd = MoneyEdit(), MoneyEdit()
        self.memo = QLineEdit()
        self.link = LedgerLink(self.con, self.app)
        self.editing_tx = None
        self.save_btn = button('거래 저장', self.save_tx)
        form = QGroupBox('거래 입력')
        fl = QFormLayout(form)
        fl.addRow('거래일자', self.date)
        fl.addRow('적요', self.summary)
        fl.addRow('입금액', self.dep)
        fl.addRow('출금액', self.wd)
        fl.addRow('메모', self.memo)
        fl.addRow(self.link)
        fl.addRow(h(self.save_btn, button('새로', self.new_tx), button('삭제', self.del_tx)))
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(h(QLabel(f'<b>{A.KIND_LABEL[kind]} 목록</b>'), QLabel(NOTE[kind]), 'stretch',
                       button('추가', self.add), button('수정', self.edit), button('삭제', self.delete),
                       button('위로', lambda: self.move(-1)), button('아래로', lambda: self.move(1))))
        tl.addWidget(self.list)
        bottom = QSplitter()
        txw = QWidget()
        xl = QVBoxLayout(txw)
        xl.setContentsMargins(0, 0, 0, 0)
        self.tx_lbl = QLabel('위 목록에서 하나를 고르면 거래 내역이 나옵니다')
        xl.addWidget(h(self.tx_lbl, 'stretch', button('CSV', lambda: export_csv(self, self.txs, '거래내역'))))
        xl.addWidget(self.txs)
        bottom.addWidget(txw)
        bottom.addWidget(form)
        bottom.setStretchFactor(0, 3)
        sp = QSplitter(Qt.Orientation.Vertical)
        sp.addWidget(top)
        sp.addWidget(bottom)
        QVBoxLayout(self).addWidget(sp)

    def aid(self):
        ids = selected_ids(self.list)
        return ids[0] if ids else None

    def refresh(self):
        cur = self.aid()
        self.link.load()
        rows = []
        for a in A.accounts(self.con, self.kind):
            x = json.loads(a['extra'] or '{}')
            k = self.kind
            if k == 'bank':
                vals = [a['company'], a['name'], a['owner'], a['number'], money_cell(A.account_balance(self.con, a['id']),
                                                                                      blank_zero=False),
                        '사용중' if a['active'] else '사용안함', a['memo']]
            elif k == 'securities':
                vals = [a['company'], a['name'], a['owner'], money_cell(a['deposit']), money_cell(a['valuation']),
                        x.get('valued_on') or '', a['memo']]
            elif k == 'insurance':
                vals = [a['company'], a['name'], a['owner'], x.get('contract_date') or '',
                        money_cell(x.get('paid_total') or 0), x.get('status') or '', a['memo']]
            else:
                pt = int(x.get('ptype') or 0)
                vals = [A.PROPERTY_TYPES[pt] if 0 <= pt < len(A.PROPERTY_TYPES) else '?', a['name'], a['owner'],
                        money_cell(a['valuation']), money_cell(a['loan'], 'out'), x.get('valued_on') or '', a['memo']]
            first = cell(vals[0], data=a['id'])
            rows.append([first] + vals[1:])
        fill(self.list, rows)
        if cur:
            for r in range(self.list.rowCount()):
                if self.list.item(r, 0).data(Qt.ItemDataRole.UserRole) == cur:
                    self.list.selectRow(r)
        if self.list.rowCount() and not self.aid():
            self.list.selectRow(0)
        self.load_txs()

    def add(self):
        d = FormDialog(self, f'새 {A.KIND_LABEL[self.kind]} 만들기', A.FIELDS[self.kind], {}, self.con)
        if d.exec():
            A.save_account(self.con, self.kind, d.values())
            self.page.changed()

    def edit(self):
        aid = self.aid()
        if not aid:
            return
        row = A.merge_extra(self.con.execute('SELECT * FROM account WHERE id=?', (aid,)).fetchone())
        d = FormDialog(self, f'{A.KIND_LABEL[self.kind]} 수정', A.FIELDS[self.kind], row, self.con)
        if d.exec():
            A.save_account(self.con, self.kind, d.values(), aid)
            self.page.changed()

    def delete(self):
        aid = self.aid()
        if aid and confirm(self, '선택한 항목과 그 거래 내역을 모두 삭제할까요?\n(장부에 동시저장된 내역은 남습니다)'):
            A.delete_account(self.con, aid)
            self.page.changed()

    def move(self, d):
        aid = self.aid()
        if aid:
            A.move(self.con, 'account', aid, d, 'kind=?', (self.kind,))
            self.refresh()

    def load_txs(self):
        aid = self.aid()
        if not aid:
            fill(self.txs, [])
            self.tx_lbl.setText('위 목록에서 하나를 고르면 거래 내역이 나옵니다')
            return
        a = self.con.execute('SELECT * FROM account WHERE id=?', (aid,)).fetchone()
        rows = A.account_txs(self.con, aid)
        fill(self.txs, [[cell(r['date'], CENTER, data=r['id']), cell(r['summary']), money_cell(r['deposit'], 'in'),
                         money_cell(r['withdraw'], 'out'), money_cell(bal, blank_zero=False), cell(r['memo']),
                         cell('연결' if r['entry_id'] else '', CENTER)] for r, bal in reversed(rows)])
        extra = f"   현재잔액 {fmt_money(A.account_balance(self.con, aid))}원" if self.kind == 'bank' else ''
        self.tx_lbl.setText(f"<b>{a['company']} {a['name']}</b> 거래 {len(rows)}건{extra}")

    def _tx_selected(self):
        ids = selected_ids(self.txs)
        if len(ids) != 1:
            return
        t = self.con.execute('SELECT * FROM account_tx WHERE id=?', (ids[0],)).fetchone()
        self.editing_tx = t['id']
        self.date.set_date(t['date'])
        self.summary.setText(t['summary'])
        self.dep.set_value(t['deposit'])
        self.wd.set_value(t['withdraw'])
        self.memo.setText(t['memo'])
        self.link.chk.setChecked(False)
        self.link.chk.setEnabled(False)
        self.save_btn.setText('거래 수정 저장')

    def new_tx(self):
        self.editing_tx = None
        self.txs.clearSelection()
        for w in (self.summary, self.dep, self.wd, self.memo):
            w.clear()
        self.link.chk.setEnabled(True)
        self.save_btn.setText('거래 저장')

    def save_tx(self):
        aid = self.aid()
        if not aid:
            error(self, f'먼저 위 목록에서 {A.KIND_LABEL[self.kind]}을(를) 고르세요. 없으면 [추가]로 만드세요.')
            return
        try:
            tx = {'date': self.date.date_(), 'summary': self.summary.text().strip(), 'deposit': self.dep.value(),
                  'withdraw': self.wd.value(), 'memo': self.memo.text().strip()}
        except ValueError:
            error(self, '금액은 숫자로 입력하세요.')
            return
        if not tx['deposit'] and not tx['withdraw']:
            error(self, '입금액 또는 출금액을 입력하세요.')
            return
        if self.editing_tx:
            A.update_tx(self.con, self.editing_tx, tx)
        else:
            lid, code = self.link.target()
            if self.link.chk.isChecked() and not code:
                error(self, '장부 동시저장: 계정과목을 고르세요.')
                return
            A.add_tx(self.con, aid, tx, lid, code)
        self.new_tx()
        self.page.changed()

    def del_tx(self):
        ids = selected_ids(self.txs)
        if not ids:
            return
        t = self.con.execute('SELECT * FROM account_tx WHERE id=?', (ids[0],)).fetchone()
        if not confirm(self, '선택한 거래를 삭제할까요?'):
            return
        with_entry = bool(t['entry_id']) and confirm(self, '장부에 함께 저장된 내역도 삭제할까요?')
        A.delete_tx(self.con, t['id'], with_entry)
        self.new_tx()
        self.page.changed()


class PayDialog(QDialog):
    def __init__(self, parent, con, app, card, total, count):
        super().__init__(parent)
        self.setWindowTitle('카드 대금 결제')
        self.date = DateEdit()
        self.bank_chk = QCheckBox('통장에 출금으로 기록')
        self.bank = QComboBox()
        for a in A.accounts(con, 'bank'):
            self.bank.addItem(f"{a['company']} {a['name']}".strip(), a['id'])
        if card['bank_account_id'] and self.bank.findData(card['bank_account_id']) >= 0:
            self.bank.setCurrentIndex(self.bank.findData(card['bank_account_id']))
            self.bank_chk.setChecked(True)
        self.bank_chk.setEnabled(self.bank.count() > 0)
        self.link = LedgerLink(con, app, '장부에 지출로 기록')
        self.link.load()
        f = QFormLayout(self)
        f.addRow(QLabel(f"<b>{card['name']}</b>  {count}건  결제 금액 <b>{fmt_money(total)}원</b>"))
        f.addRow('결제일', self.date)
        f.addRow(self.bank_chk, self.bank)
        f.addRow(self.link)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText('결제 처리')
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)


class CardTab(QWidget):
    def __init__(self, page):
        super().__init__()
        self.page, self.app, self.con = page, page.app, page.con
        self.list = make_table(['카드사', '카드명', '카드번호', '결제일', '이번 결제월 미결제', '미결제 총액', '비고'], stretch=6)
        self.list.itemSelectionChanged.connect(self.load_txs)
        self.list.doubleClicked.connect(lambda *_: self.edit())
        self.nav = MonthNav()
        self.nav.changed.connect(lambda *_: self.refresh())
        self.paid = QComboBox()
        self.paid.addItems(['미결제', '결제완료', '모두보기'])
        self.paid.currentIndexChanged.connect(lambda *_: self.load_txs())
        self.txs = make_table(['거래일자', '적요', '결제금액', '수수료', '합계', '회차', '결제일', '결제여부', '메모'],
                              stretch=8, multi=True)
        self.tx_lbl = QLabel()
        self.date = DateEdit()
        self.date.dateChanged.connect(self._auto_pay_date)
        self.summary = QLineEdit()
        self.amount, self.fee = MoneyEdit(), MoneyEdit()
        self.months = QSpinBox()
        self.months.setRange(1, 60)
        self.months.setSpecialValueText('일시불')
        self.pay_date = DateEdit()
        self.memo = QLineEdit()
        form = QGroupBox('카드 사용 입력')
        fl = QFormLayout(form)
        fl.addRow('거래일자', self.date)
        fl.addRow('적요', self.summary)
        fl.addRow('사용금액(전체)', self.amount)
        fl.addRow('수수료(전체)', self.fee)
        fl.addRow('할부개월', self.months)
        fl.addRow('첫 결제일', self.pay_date)
        fl.addRow('메모', self.memo)
        fl.addRow(QLabel('할부는 전체 금액을 넣으면 개월 수로 나눠 매달 결제일에 잡힙니다.\n'
                         '첫 결제일은 카드의 청구기간으로 자동 계산되며 바꿀 수 있습니다.'))
        fl.addRow(h(button('저장', self.save), button('삭제(할부 전체)', self.delete_tx)))
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(h(QLabel('<b>신용카드 목록</b>  카드 사용액은 결제 전까지 부채로 계산됩니다.'), 'stretch',
                       button('추가', self.add), button('수정', self.edit), button('삭제', self.delete),
                       button('위로', lambda: self.move(-1)), button('아래로', lambda: self.move(1))))
        tl.addWidget(self.list)
        txw = QWidget()
        xl = QVBoxLayout(txw)
        xl.setContentsMargins(0, 0, 0, 0)
        xl.addWidget(h('결제월', self.nav, self.paid, 'stretch',
                       button('CSV', lambda: export_csv(self, self.txs, '카드거래'))))
        xl.addWidget(self.txs)
        xl.addWidget(h(button('선택 결제', self.pay_selected), button('이달 미결제 모두 결제', self.pay_all),
                       button('결제 취소', self.unpay), 'stretch'))
        xl.addWidget(self.tx_lbl)
        bottom = QSplitter()
        bottom.addWidget(txw)
        bottom.addWidget(form)
        bottom.setStretchFactor(0, 3)
        sp = QSplitter(Qt.Orientation.Vertical)
        sp.addWidget(top)
        sp.addWidget(bottom)
        QVBoxLayout(self).addWidget(sp)

    def cid(self):
        ids = selected_ids(self.list)
        return ids[0] if ids else None

    def card(self):
        c = self.cid()
        return self.con.execute('SELECT * FROM card WHERE id=?', (c,)).fetchone() if c else None

    def ym(self):
        return f'{self.nav.y:04d}-{self.nav.m:02d}'

    def refresh(self):
        cur = self.cid()
        rows = []
        for c in A.cards(self.con):
            this = sum(r['amount'] + r['fee'] for r in A.card_txs(self.con, c['id'], self.ym(), 0))
            rows.append([cell(c['company'], data=c['id']), c['name'], c['number'], cell(f"{c['pay_day']}일", CENTER),
                         money_cell(this, 'out'), money_cell(A.card_unpaid_total(self.con, c['id']), 'out'), c['memo']])
        fill(self.list, rows)
        for r in range(self.list.rowCount()):
            if self.list.item(r, 0).data(Qt.ItemDataRole.UserRole) == cur:
                self.list.selectRow(r)
        if self.list.rowCount() and not self.cid():
            self.list.selectRow(0)
        self.load_txs()

    def load_txs(self):
        cid = self.cid()
        if not cid:
            fill(self.txs, [])
            self.tx_lbl.setText('카드를 먼저 추가하세요.')
            return
        paid = {0: 0, 1: 1, 2: None}[self.paid.currentIndex()]
        rows = A.card_txs(self.con, cid, self.ym(), paid)
        fill(self.txs, [[cell(r['date'], CENTER, data=r['id']), cell(r['summary']), money_cell(r['amount']),
                         money_cell(r['fee']), money_cell(r['amount'] + r['fee'], 'out'),
                         cell('일시불' if r['months'] <= 1 else f"{r['seq']}/{r['months']}", CENTER),
                         cell(r['pay_date'], CENTER), cell('결제완료' if r['paid'] else '미결제', CENTER),
                         cell(r['memo'])] for r in rows])
        tot = sum(r['amount'] + r['fee'] for r in rows)
        unpaid_all = A.card_unpaid_total(self.con, cid)
        this_unpaid = sum(r['amount'] + r['fee'] for r in A.card_txs(self.con, cid, self.ym(), 0))
        self.tx_lbl.setText(f'{self.nav.y}년 {self.nav.m}월 결제분 {len(rows)}건 합계 {fmt_money(tot)}   '
                            f'· 결제할 금액 {fmt_money(this_unpaid)} · 결제 후 남은 금액 {fmt_money(unpaid_all - this_unpaid)}')
        self._auto_pay_date()

    def _auto_pay_date(self, *_):
        c = self.card()
        if c:
            self.pay_date.set_date(A.pay_date_for(c, self.date.date_()))

    def add(self):
        d = FormDialog(self, '새 카드 만들기', A.CARD_FIELDS, {'pay_day': 14, 'bill_from_month': -1, 'bill_from_day': 1,
                                                          'bill_to_month': -1, 'bill_to_day': 31}, self.con)
        if d.exec():
            v = d.values()
            if not 1 <= v['pay_day'] <= 31:
                error(self, '결제일은 1~31 사이로 입력하세요.')
                return
            A.save_card(self.con, v)
            self.page.changed()

    def edit(self):
        c = self.card()
        if not c:
            return
        d = FormDialog(self, '카드 정보 수정', A.CARD_FIELDS, A.merge_extra(c), self.con)
        if d.exec():
            A.save_card(self.con, d.values(), c['id'])
            self.page.changed()

    def delete(self):
        c = self.card()
        if c and confirm(self, f"'{c['name']}' 카드와 그 사용 내역을 모두 삭제할까요?"):
            A.delete_card(self.con, c['id'])
            self.page.changed()

    def move(self, d):
        c = self.cid()
        if c:
            A.move(self.con, 'card', c, d)
            self.refresh()

    def save(self):
        c = self.card()
        if not c:
            error(self, '카드를 먼저 고르세요.')
            return
        try:
            amt, fee = self.amount.value(), self.fee.value()
        except ValueError:
            error(self, '금액은 숫자로 입력하세요.')
            return
        if not amt:
            error(self, '사용금액을 입력하세요.')
            return
        A.add_card_purchase(self.con, c['id'], self.date.date_(), self.summary.text().strip(), amt, fee,
                            self.months.value(), self.pay_date.date_(), self.memo.text().strip())
        for w in (self.summary, self.amount, self.fee, self.memo):
            w.clear()
        self.months.setValue(1)
        self.page.changed()

    def delete_tx(self):
        ids = selected_ids(self.txs)
        if not ids:
            return
        cid = self.cid()
        groups = {self.con.execute('SELECT group_id FROM card_tx WHERE id=?', (i,)).fetchone()['group_id'] for i in ids}
        if confirm(self, '선택한 사용 내역을 삭제할까요? (할부는 모든 회차가 함께 삭제됩니다)'):
            for g in groups:
                if g is None:
                    continue
                A.delete_card_group(self.con, cid, g)
            for i in ids:
                self.con.execute('DELETE FROM card_tx WHERE id=?', (i,))
            self.con.commit()
            self.page.changed()

    def _pay(self, ids):
        c = self.card()
        rows = [self.con.execute('SELECT * FROM card_tx WHERE id=? AND paid=0', (i,)).fetchone() for i in ids]
        rows = [r for r in rows if r]
        if not rows:
            info(self, '결제할 미결제 내역이 없습니다.')
            return
        total = sum(r['amount'] + r['fee'] for r in rows)
        d = PayDialog(self, self.con, self.app, c, total, len(rows))
        if d.exec():
            lid, code = d.link.target()
            A.pay_card(self.con, [r['id'] for r in rows], d.date.date_(),
                       d.bank.currentData() if d.bank_chk.isChecked() else None, lid, code)
            self.page.changed()

    def pay_selected(self):
        self._pay(selected_ids(self.txs))

    def pay_all(self):
        c = self.cid()
        if c:
            self._pay([r['id'] for r in A.card_txs(self.con, c, self.ym(), 0)])

    def unpay(self):
        ids = selected_ids(self.txs)
        if ids and confirm(self, '선택한 내역의 결제를 취소할까요?\n같은 결제로 처리된 회차도 함께 미결제로 돌아가고, '
                                 '그 결제 때 통장 출금·장부 지출로 기록한 내역도 삭제됩니다.'):
            n = A.unpay_card(self.con, ids)
            info(self, f'{n}건을 미결제로 되돌렸습니다.')
            self.page.changed()


class AssetsPage(QWidget):
    title = '자산관리'

    def __init__(self, app):
        super().__init__()
        self.app, self.con = app, app.con
        self.sum_lbl = QLabel()
        self.sum_lbl.setObjectName('SumLabel')
        self.sum_lbl.setWordWrap(True)            # 좁은 화면에서는 두 줄로
        self.tabs = QTabWidget()
        self.bank = AccountTab(self, 'bank')
        self.card_tab = CardTab(self)
        self.sec = AccountTab(self, 'securities')
        self.ins = AccountTab(self, 'insurance')
        self.prop = AccountTab(self, 'property')
        for t, n in ((self.bank, '은행통장'), (self.card_tab, '신용카드'), (self.sec, '증권'), (self.ins, '보험'),
                     (self.prop, '부동산/기타')):
            self.tabs.addTab(t, n)
        self.tabs.currentChanged.connect(lambda *_: self.tabs.currentWidget().refresh())
        lay = QVBoxLayout(self)
        lay.addWidget(self.sum_lbl)
        lay.addWidget(self.tabs, 1)

    def reset_state(self):
        for t in (self.bank, self.sec, self.ins, self.prop):
            t.new_tx()

    def changed(self):
        self.refresh()
        self.app.data_changed()

    def refresh(self):
        s = A.summary(self.con)
        m = fmt_money
        self.sum_lbl.setText(f"<b>자산 합계 {m(s['자산합계'])}</b>  (예금 {m(s['예금'])} · 증권 {m(s['증권'])} · "
                             f"부동산 {m(s['부동산'])} · 기타 {m(s['기타'])})&nbsp;&nbsp;&nbsp;&nbsp;"
                             f"<b>부채 합계 {m(s['부채합계'])}</b>  (대출 {m(s['대출'])} · 카드 {m(s['카드'])} · "
                             f"기타부채 {m(s['기타부채'])})&nbsp;&nbsp;&nbsp;&nbsp;<b style='color:#1d5fbf'>순자산 {m(s['순자산'])}원</b>")
        self.tabs.currentWidget().refresh()
