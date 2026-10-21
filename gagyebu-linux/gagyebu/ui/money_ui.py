"""1.8.0 화면 조각: 외화로 적기 · 큰돈 나눠 적기 · 같은 곳 모아보기 · 휴지통 · 카테고리 그림 고르기 · 결제수단 설정 ·
통계의 주별/결제수단/저축 탭 · 고정비 한눈에. 계산은 services/money.py·trash.py·catemoji.py 에 있고 여기는 화면만."""
import datetime as dt
import html

from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGridLayout, QInputDialog,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QRadioButton,
                             QSpinBox, QSplitter, QVBoxLayout, QWidget)

from .. import db
from .. import theme as T
from ..services import catemoji as E
from ..services import ledger as L
from ..services import money as M
from ..services import trash as TR
from ..services.reports import settle_day
from ..util import fmt_money, pct, to_date
from .widgets import (CENTER, MonthNav, button, cell, confirm, error, export_csv, fill, h, info, make_table,
                      money_cell, ok_cancel, selected_ids, set_tone)




def cat_label(emap, cmap, code):
    """'🛒 식료품' (그림이 없으면 이름만, 없는 번호는 '(미분류 …)')"""
    return E.deco(emap, code, L.code_label(cmap, code))


def _bar(pct, color=None, height=8):
    from .extras import Bar
    b = Bar(height)
    b.set(pct, color)
    return b


# ── 외화로 적기 ─────────────────────────────────────────
class FxDialog(QDialog):
    """외화 금액 × 환율 → 원. 환율은 통화마다 기억 (자료 파일에 저장, 휴대폰판과 같이 씀)"""
    def __init__(self, parent, con, expense=True):
        super().__init__(parent)
        self.con = con
        self.won, self.note, self.expense = None, '', expense
        self.setWindowTitle('외화로 적기')
        self.cur = QComboBox()
        for c, n, _u in M.CURRENCIES:
            self.cur.addItem(f'{c}  {n}', c)
        self.amount = QLineEdit()
        self.amount.setPlaceholderText('예: 12.50')
        self.rate = QLineEdit()
        self.rate_lbl = QLabel()
        self.result = QLabel()
        self.result.setStyleSheet('font-weight:bold')
        self.r_out, self.r_in = QRadioButton('지출'), QRadioButton('수입')
        (self.r_out if expense else self.r_in).setChecked(True)
        g = QButtonGroup(self)
        g.addButton(self.r_out)
        g.addButton(self.r_in)
        last = db.get_meta(con, 'fx_last') or 'USD'
        i = self.cur.findData(last)
        self.cur.setCurrentIndex(max(i, 0))
        self.cur.currentIndexChanged.connect(self._cur_changed)
        self.amount.textChanged.connect(self._calc)
        self.rate.textChanged.connect(self._calc)
        f = QFormLayout()
        f.addRow('통화', self.cur)
        f.addRow('외화 금액', self.amount)
        f.addRow(self.rate_lbl, self.rate)
        f.addRow('넣을 칸', h(self.r_out, self.r_in, 'stretch'))
        f.addRow('원으로', self.result)
        bb = ok_cancel(self, '넣기', self._ok)
        lay = QVBoxLayout(self)
        lay.addWidget(set_tone(QLabel('여행에서 쓴 외화 금액과 그때 환율을 넣으면 원으로 바꿔 금액 칸에 넣고, '
                                      '메모에 외화 금액을 적어 둡니다. 환율은 통화마다 기억합니다.'), 'note'))
        lay.itemAt(0).widget().setWordWrap(True)
        lay.addLayout(f)
        lay.addWidget(bb)
        self._cur_changed()
        self.resize(420, 0)

    def _cur_changed(self):
        c = self.cur.currentData()
        unit = M._UNIT[c]
        name = {'USD': '달러', 'JPY': '엔', 'EUR': '유로', 'CNY': '위안', 'GBP': '파운드', 'VND': '동'}.get(c, c)
        self.rate_lbl.setText(f'환율 ({unit}{name} = ?원)' if unit != 1 else f'환율 (1{name} = ?원)')
        self.rate.setText(M.fx_rates(self.con).get(c, ''))
        self._calc()

    def _calc(self):
        try:
            won, _n = M.fx_convert(self.amount.text(), self.cur.currentData(), self.rate.text())
            self.result.setText(f'{fmt_money(won)}원')
        except ValueError as e:
            self.result.setText('' if not self.amount.text().strip() else str(e))

    def _ok(self):
        try:
            self.won, self.note = M.fx_convert(self.amount.text(), self.cur.currentData(), self.rate.text())
        except ValueError as e:
            error(self, str(e))
            return
        M.set_fx_rate(self.con, self.cur.currentData(), self.rate.text())
        db.set_meta(self.con, 'fx_last', self.cur.currentData())
        self.con.commit()
        self.expense = self.r_out.isChecked()
        self.accept()


# ── 큰돈 나눠 적기 ──────────────────────────────────────
class SplitDialog(QDialog):
    """지금 입력 칸의 내역을 여러 달로 나눠 저장 (1년치 보험료를 12달로 등)"""
    def __init__(self, parent, con, lid, v):
        super().__init__(parent)
        self.con, self.lid, self.v = con, lid, v
        self.ids = []
        self.setWindowTitle('나눠 적기')
        self.months = QSpinBox()
        self.months.setRange(2, 60)
        self.months.setValue(12)
        self.months.setSuffix('달')
        self.months.valueChanged.connect(self._preview)
        self.table = make_table(['날짜', '내용', '금액', '메모'], stretch=3)
        self.msg = set_tone(QLabel(), 'note')
        self.msg.setWordWrap(True)
        bb = ok_cancel(self, '나눠서 저장', self._ok)
        self.ok_btn = bb.button(QDialogButtonBox.StandardButton.Ok)
        lay = QVBoxLayout(self)
        lay.addWidget(set_tone(QLabel('1년치 자동차보험·연회비처럼 한 번에 낸 큰돈을 여러 달로 나눠 적습니다. '
                                      '매달 같은 날(그 달에 없으면 말일)에 들어가고, 나머지 원은 첫 달에 더합니다.'), 'note'))
        lay.itemAt(0).widget().setWordWrap(True)
        lay.addWidget(h('몇 달로', self.months, 'stretch'))
        lay.addWidget(self.table, 1)
        lay.addWidget(self.msg)
        lay.addWidget(bb)
        self.resize(620, 480)
        self._preview()

    def _preview(self):
        try:
            plan = M.split_plan(self.v, self.months.value())
        except ValueError as e:
            fill(self.table, [])
            self.msg.setText(str(e))
            self.ok_btn.setEnabled(False)
            return
        fill(self.table, [[cell(p['date'], CENTER), cell(p['item']),
                           money_cell(p['income'] or p['expense'], 'in' if p['income'] else 'out'), cell(p['memo'])]
                          for p in plan])
        total = self.v['income'] or self.v['expense']
        self.msg.setText(f"{fmt_money(total)}원을 {len(plan)}달로 나눠 {len(plan)}건을 넣습니다. "
                         '나중에 하나를 지우면 나머지도 함께 지울지 묻습니다.')
        self.ok_btn.setEnabled(True)

    def _ok(self):
        try:
            self.ids = M.add_split(self.con, self.lid, self.v, self.months.value())
        except ValueError as e:
            error(self, str(e))
            return
        self.accept()


# ── 같은 곳 모아보기 ────────────────────────────────────
class SamePlaceDialog(QDialog):
    """같은 내용(취소 포함)의 최근 3개월 내역·합계·달마다 쓴 돈"""
    def __init__(self, parent, con, lid, item, upto=None):
        super().__init__(parent)
        self.setWindowTitle(f"같은 곳 모아보기 — {item}")
        sp = M.same_place(con, lid, item, upto or dt.date.today())
        lay = QVBoxLayout(self)
        if not sp:
            lay.addWidget(QLabel('내용이 비어 있습니다.'))
            return
        tn = T.tone()
        head = QLabel(f"<b>{html.escape(sp['item'])}</b>  최근 3개월 ({to_date(sp['start']):%m.%d} ~ {to_date(sp['end']):%m.%d})"
                      f"<br><span style='font-size:large'><b style='color:{tn['out']}'>{fmt_money(sp['expense'])}원</b></span>"
                      f" · {sp['count']}건 · 한 번에 평균 {fmt_money(sp['avg'])}원"
                      + (f" · 수입 {fmt_money(sp['income'])}원" if sp['income'] else ''))
        head.setWordWrap(True)
        lay.addWidget(head)
        top = max([m['expense'] for m in sp['months']] + [1])
        grid = QGridLayout()
        for i, m in enumerate(sp['months']):
            grid.addWidget(QLabel(f"{int(m['ym'][5:])}월"), i, 0)
            grid.addWidget(_bar(m['expense'] * 100 // top if m['expense'] > 0 else 0, tn['out']), i, 1)
            grid.addWidget(QLabel(f"{fmt_money(m['expense'])}원 ({m['count']}건)"), i, 2)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        pmap = M.pay_map(con)
        cmap, emap = L.category_map(con, lid), E.emoji_map(con, lid)
        t = make_table(['날짜', '내용', '수입', '지출', '카테고리', '결제수단', '메모'], stretch=6)
        fill(t, [[cell(r['date'], CENTER), cell(r['item']), money_cell(r['income'], 'in'), money_cell(r['expense'], 'out'),
                  cell(cat_label(emap, cmap, r['code'])), cell(M.pay_label(pmap, r['pay'])), cell(r['memo'])]
                 for r in sp['rows']])
        lay.addWidget(t, 1)
        lay.addWidget(h('stretch', button('닫기', self.accept)))
        self.resize(760, 520)


# ── 휴지통 ─────────────────────────────────────────────
class TrashDialog(QDialog):
    """지운 내역 30일 보관 → 되살리기 / 영구 삭제"""
    def __init__(self, parent, con, lid):
        super().__init__(parent)
        self.con, self.lid = con, lid
        self.setWindowTitle('휴지통')
        self.table = make_table(['지운 날', '날짜', '내용', '수입', '지출', '카테고리', '사진', '남은 날'], stretch=2, multi=True)
        self.lbl = set_tone(QLabel(), 'note')
        self.lbl.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addWidget(self.lbl)
        lay.addWidget(self.table, 1)
        lay.addWidget(h(button('되살리기', self.restore), button('영구 삭제', self.remove), button('휴지통 비우기', self.empty),
                        'stretch', button('닫기', self.accept)))
        self.resize(820, 460)
        self.load()

    def load(self):
        items = TR.items(self.con, self.lid)
        cmap, emap = L.category_map(self.con, self.lid), E.emoji_map(self.con, self.lid)
        why = {'category': ' (카테고리 삭제)', 'asset': ' (통장 거래와 함께)'}
        rows = []
        for x in items:
            e = x['entry']
            rows.append([cell(str(x['deleted'])[:16] + why.get(x['why'], ''), data=x['id']), cell(e.get('date', ''), CENTER),
                         cell(e.get('item', '')), money_cell(e.get('income') or 0, 'in'), money_cell(e.get('expense') or 0, 'out'),
                         cell(cat_label(emap, cmap, e.get('code') or '')), cell(f"{x['photos']}장" if x['photos'] else '', CENTER),
                         cell(f"{TR.days_left(x['deleted'])}일", CENTER)])
        fill(self.table, rows)
        self.lbl.setText(f'지운 내역은 {TR.KEEP_DAYS}일 동안 여기에 보관했다가 저절로 지워집니다. '
                         f'지금 {len(items)}건 — 고른 뒤 [되살리기]를 누르면 원래 자리로 돌아갑니다 (여러 줄 고르기 가능).')

    def restore(self):
        ids = selected_ids(self.table)
        if not ids:
            info(self, '되살릴 내역을 고르세요.')
            return
        TR.restore(self.con, ids)
        self.load()

    def remove(self):
        ids = selected_ids(self.table)
        if ids and confirm(self, f'고른 {len(ids)}건을 영구 삭제할까요? 되돌릴 수 없습니다.'):
            TR.remove(self.con, ids)
            self.load()

    def empty(self):
        n = TR.count(self.con, self.lid)
        if n and confirm(self, f'휴지통의 {n}건을 모두 영구 삭제할까요? 되돌릴 수 없습니다.'):
            TR.empty(self.con, self.lid)
            self.load()


# ── 카테고리 그림 고르기 ────────────────────────────────
class EmojiDialog(QDialog):
    def __init__(self, parent, current='', name=''):
        super().__init__(parent)
        self.value = None
        self.setWindowTitle(f"그림 고르기 — {name}" if name else '그림 고르기')
        grid = QGridLayout()
        grid.setSpacing(4)
        ef = QFont()
        ef.setFamilies(['Noto Color Emoji', 'Segoe UI Emoji', 'Apple Color Emoji', 'Twemoji Mozilla'])   # 고르기 창은 색 그림으로
        ef.setPixelSize(20)
        for i, e in enumerate(E.CHOICES):
            b = QPushButton(e)
            b.setFixedSize(40, 36)
            b.setFont(ef)
            b.setCheckable(True)
            b.setChecked(e == current)
            b.clicked.connect(lambda _c=False, e=e: self._pick(e))
            grid.addWidget(b, i // 9, i % 9)
        self.edit = QLineEdit(current)
        self.edit.setMaxLength(4)
        self.edit.setPlaceholderText('다른 그림을 붙여넣어도 됩니다')
        lay = QVBoxLayout(self)
        lay.addLayout(grid)
        lay.addWidget(h('직접', self.edit))
        sug = E.suggest(name)
        bb = ok_cancel(self, '이 그림으로', lambda: self._pick(self.edit.text().strip()))
        lay.addWidget(h(button('그림 없애기', lambda: self._pick('')),
                        *( [button(f'이름에 어울리는 그림 {sug}', lambda: self._pick(sug))] if sug else []), 'stretch'))
        lay.addWidget(bb)

    def _pick(self, e):
        self.value = e
        self.accept()


# ── 설정 › 결제수단 ─────────────────────────────────────
class PayTab(QWidget):
    """결제수단: 기본(현금·카드·계좌이체·간편결제) + 자산의 신용카드 + 직접 만든 것(지역화폐·상품권 등)"""
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.base_lbl = set_tone(QLabel(), 'note')
        self.base_lbl.setWordWrap(True)
        self.list = QListWidget()
        lay = QVBoxLayout(self)
        lay.addWidget(self.base_lbl)
        lay.addWidget(QLabel('<b>직접 만든 결제수단</b>'))
        lay.addWidget(self.list, 1)
        lay.addWidget(h(button('추가', self.add), button('이름 바꾸기', self.rename), button('삭제', self.delete),
                        button('위로', lambda: self.move(-1)), button('아래로', lambda: self.move(1)), 'stretch'))

    @property
    def con(self):
        return self.page.con

    def refresh(self):
        cards = [n for v, n in M.pay_options(self.con) if v.startswith('card:')]
        self.base_lbl.setText('가계부 내역을 넣을 때 고를 결제수단입니다. 통계 › 결제수단에서 결제수단별로 모아 봅니다.<br>'
                              '기본: 현금 · 카드 · 계좌이체 · 간편결제<br>'
                              + ('자산의 신용카드: ' + ', '.join(html.escape(c) for c in cards) if cards else
                                 '자산 › 신용카드에 카드를 넣으면 카드마다 고를 수 있고 카드 실적도 셉니다.'))
        cur = self.list.currentItem().text() if self.list.currentItem() else None
        self.list.clear()
        for n in M.custom_pays(self.con):
            self.list.addItem(QListWidgetItem(n))
            if n == cur:
                self.list.setCurrentRow(self.list.count() - 1)

    def _names(self):
        return [self.list.item(i).text() for i in range(self.list.count())]

    def add(self):
        n, ok = QInputDialog.getText(self, '결제수단 추가', '이름 (예: 지역화폐, 상품권, 회사 카드)')
        if ok and n.strip():
            M.set_custom_pays(self.con, self._names() + [n.strip()])
            self.refresh()
            self.page.app.data_changed()

    def rename(self):
        it = self.list.currentItem()
        if not it:
            return
        n, ok = QInputDialog.getText(self, '결제수단 이름 바꾸기', '새 이름', text=it.text())
        if ok and n.strip() and n.strip() != it.text():
            try:
                M.rename_custom_pay(self.con, it.text(), n.strip())
            except ValueError as e:
                error(self, str(e))
                return
            self.refresh()
            self.page.app.data_changed()

    def delete(self):
        it = self.list.currentItem()
        if it and confirm(self, f"결제수단 '{it.text()}'을(를) 목록에서 지울까요?\n이미 넣은 내역에는 이름이 그대로 남습니다."):
            M.set_custom_pays(self.con, [n for n in self._names() if n != it.text()])
            self.refresh()
            self.page.app.data_changed()

    def move(self, d):
        r = self.list.currentRow()
        names = self._names()
        if 0 <= r < len(names) and 0 <= r + d < len(names):
            names[r], names[r + d] = names[r + d], names[r]
            M.set_custom_pays(self.con, names)
            self.refresh()
            self.list.setCurrentRow(r + d)


# ── 통계 › 주별 · 결제수단 · 저축 ───────────────────────
class WeekStatTab(QWidget):
    """그 달을 월요일로 나눈 주별 수입·지출 (주간 예산 대비)"""
    def __init__(self, page):
        super().__init__()
        self.page, self.con = page, page.con
        self.nav = MonthNav()
        self.nav.changed.connect(lambda *_: self.refresh())
        self.table = make_table(['주', '기간', '수입', '지출', '주간 예산', '예산 대비'], stretch=5)
        self.lbl = set_tone(QLabel(), 'note')
        self.lbl.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addWidget(h(self.nav, 'stretch', button('CSV', lambda: export_csv(self, self.table, '주별'))))
        lay.addWidget(self.table, 1)
        lay.addWidget(self.lbl)

    def refresh(self):
        lid, sd = self.page.app.lid, settle_day(self.con)
        weeks = M.weeks_of_month(self.con, lid, self.nav.y, self.nav.m, sd)
        tn = T.tone()
        rows = []
        for i, w in enumerate(weeks, 1):
            b = w['budget'] * w['days'] // 7 if w['budget'] else 0          # 그 달에 걸친 날만큼
            p = pct(w['expense'], b)
            rows.append([cell(f'{i}주', CENTER), cell(f"{to_date(w['start']):%m.%d} ~ {to_date(w['end']):%m.%d} ({w['days']}일)"),
                         money_cell(w['income'], 'in'), money_cell(w['expense'], 'out'),
                         money_cell(b) if b else cell('—', CENTER),
                         cell('—' if p is None else f'{p}%', CENTER, color=QColor(tn['out']) if (p or 0) > 100 else None)])
        fill(self.table, rows)
        wb = M.week_budget(self.con, lid)
        self.lbl.setText((f'주간 예산 {fmt_money(wb)}원 (달의 처음·끝 주는 그 달에 걸친 날만큼 나눠 셈). ' if wb else
                          '주간 예산을 정하면 주마다 예산 대비를 보여 줍니다 — 가계부 화면 [예산 정하기…]에서. ')
                         + '한 주는 월요일부터 일요일까지입니다.')


class PayStatTab(QWidget):
    """결제수단별 지출 (그 달, 월 시작일 기준). 고르면 그 결제수단의 내역"""
    def __init__(self, page):
        super().__init__()
        self.page, self.con = page, page.con
        self.nav = MonthNav()
        self.nav.changed.connect(lambda *_: self.refresh())
        self.table = make_table(['결제수단', '건수', '수입', '지출', '비율'], stretch=0)
        self.table.itemSelectionChanged.connect(self._sel)
        self.detail = make_table(['날짜', '내용', '수입', '지출', '카테고리', '메모'], stretch=5)
        self.detail_lbl = QLabel()
        self.perf = QLabel()
        self.perf.setWordWrap(True)
        sp = QSplitter()
        lw = QWidget()
        ll = QVBoxLayout(lw)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.table, 1)
        ll.addWidget(self.perf)
        sp.addWidget(lw)
        dw = QWidget()
        dl = QVBoxLayout(dw)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.addWidget(self.detail_lbl)
        dl.addWidget(self.detail, 1)
        sp.addWidget(dw)
        sp.setStretchFactor(1, 2)
        lay = QVBoxLayout(self)
        lay.addWidget(h(self.nav, set_tone(QLabel('내역을 넣을 때 고른 결제수단으로 모아 봅니다.'), 'note'), 'stretch'))
        lay.addWidget(sp, 1)
        self.rows = []

    def _range(self):
        from ..util import settle_period
        return settle_period(self.nav.y, self.nav.m, settle_day(self.con))

    def refresh(self):
        lid = self.page.app.lid
        s, e = self._range()
        cur = selected_ids(self.table)
        self.rows = M.pay_summary(self.con, lid, s, e)
        fill(self.table, [[cell(r['label'], data=r['pay']), cell(r['count'], CENTER), money_cell(r['income'], 'in'),
                           money_cell(r['expense'], 'out'), cell('' if r['pct'] is None else f"{r['pct']}%", CENTER)]
                          for r in self.rows])
        for i, r in enumerate(self.rows):
            if cur and r['pay'] == cur[0]:
                self.table.selectRow(i)
        if self.rows and not cur:
            self.table.selectRow(0)
        if not self.rows:
            fill(self.detail, [])
            self.detail_lbl.setText('이 달에는 내역이 없어요.')
        perf = [p for p in M.card_perf(self.con, self.nav.y, self.nav.m) if p['target']]
        if perf:
            tn = T.tone()
            bits = []
            for p in perf:
                ok = p['spent'] >= p['target']
                bits.append(f"{html.escape(p['label'])}: {fmt_money(p['spent'])} / {fmt_money(p['target'])}원 "
                            + (f"<b style='color:{tn['in']}'>채움 ✓</b>" if ok else f"({p['pct']}% · {fmt_money(p['left'])}원 남음)"))
            self.perf.setText(f'<b>{self.nav.m}월 카드 실적</b> (1일~말일, 모든 가계부)<br>' + '<br>'.join(bits))
        else:
            self.perf.setText('')
        self._sel()

    def _sel(self):
        ids = selected_ids(self.table)
        if not ids and not self.rows:
            return
        pay = ids[0] if ids else self.rows[0]['pay']
        lid = self.page.app.lid
        s, e = self._range()
        rows = M.entries_by_pay(self.con, lid, pay, s, e)
        cmap, emap = L.category_map(self.con, lid), E.emoji_map(self.con, lid)
        fill(self.detail, [[cell(r['date'], CENTER), cell(r['item']), money_cell(r['income'], 'in'),
                            money_cell(r['expense'], 'out'), cell(cat_label(emap, cmap, r['code'])), cell(r['memo'])]
                           for r in rows])
        lab = M.pay_label(M.pay_map(self.con), pay) or '결제수단 안 정함'
        self.detail_lbl.setText(f"<b>{html.escape(lab)}</b>  {len(rows)}건 · 지출 {fmt_money(sum(r['expense'] for r in rows))}원")


class SavingsTab(QWidget):
    """월별 저축 추이: 수입 · 지출 · 남은 돈 · 저축/적금 카테고리로 낸 돈 · 모은 돈 · 저축률 · 누계"""
    def __init__(self, page):
        super().__init__()
        self.page, self.con = page, page.con
        self.year = QSpinBox()
        self.year.setRange(1990, 2100)
        self.year.setValue(dt.date.today().year)
        self.year.setSuffix('년')
        self.year.valueChanged.connect(lambda *_: self.refresh())
        self.table = make_table(['달', '수입', '지출', '남은 돈', '저축·적금', '모은 돈', '저축률', '누계', ''], stretch=8)
        self.lbl = set_tone(QLabel(), 'note')
        self.lbl.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addWidget(h(QLabel('연도'), self.year, 'stretch', button('CSV', lambda: export_csv(self, self.table, '저축 추이'))))
        lay.addWidget(self.table, 1)
        lay.addWidget(self.lbl)

    def refresh(self):
        lid = self.page.app.lid
        tr = M.savings_trend(self.con, lid, self.year.value(), settle_day(self.con))
        tn = T.tone()
        top = max([abs(r['saved']) for r in tr['rows']] + [1])
        rows = []
        for r in tr['rows'] + [dict(tr['total'], month=None, cum=None)]:
            rows.append([cell(f"{r['month']}월" if r['month'] else '합계', CENTER, bold=not r['month']),
                         money_cell(r['income'], 'in'), money_cell(r['expense'], 'out'), money_cell(r['left'], blank_zero=False),
                         money_cell(r['saving']), money_cell(r['saved'], blank_zero=False, bold=True),
                         cell('—' if r['rate'] is None else f"{r['rate']}%", CENTER,
                              color=QColor(tn['out']) if (r['rate'] or 0) < 0 else QColor(tn['in']) if (r['rate'] or 0) >= 20 else None),
                         money_cell(r['cum'], blank_zero=False) if r['cum'] is not None else cell(''), cell('')])
        fill(self.table, rows)
        for i, r in enumerate(tr['rows']):              # 마지막 칸: 모은 돈 막대
            self.table.setCellWidget(i, 8, _bar(abs(r['saved']) * 100 // top if r['saved'] else 0,
                                                tn['in'] if r['saved'] >= 0 else tn['out'], 10))
        cmap = L.category_map(self.con, lid)
        names = ', '.join(cmap.get(c, c) for c in tr['codes'])
        self.lbl.setText('남은 돈 = 수입 − 지출. 모은 돈 = 남은 돈 + 저축·적금으로 낸 돈 (지출로 적었지만 실제로는 모은 돈). '
                         '저축률 = 모은 돈 ÷ 수입.  ' + (f'저축·적금으로 센 세부 카테고리: {names}' if names else
                                                       '이름에 저축·적금·투자·연금이 들어간 세부 카테고리가 없어 남은 돈만 셉니다.'))


# ── 고정비 한눈에 ───────────────────────────────────────
def fixed_html(con, lid, y, m, sd, today=None):
    """이번 달 고정 수입·지출 요약 HTML"""
    fx = M.fixed_summary(con, lid, y, m, sd, today or dt.date.today())
    tn = T.tone()
    f = fmt_money
    if not fx['items']:
        return f"<p style='color:{tn['text2']}'>{m}월에 들어갈 고정 수입·지출이 없어요.</p>"
    exp_left = fx['expected_left']
    return (f"<b>{m}월 고정 지출</b> {f(fx['out_total'])}원 "
            f"<span style='color:{tn['text2']}'>(나감 {f(fx['out_done'])} · 남음 {f(fx['out_left'])})</span>"
            + (f"  ·  <b>고정 수입</b> {f(fx['in_total'])}원 <span style='color:{tn['text2']}'>(남음 {f(fx['in_left'])})</span>"
               if fx['in_total'] else '')
            + f"<br>변동 지출 {f(fx['variable'])}원 (지출 {f(fx['expense'])} − 고정으로 넣은 것 {f(fx['fixed_expense'])})"
            + f"<br>고정비까지 빼면 이달 말 남을 돈 (예상): <b style='color:{tn['out'] if exp_left < 0 else tn['in']}'>"
            f"{f(exp_left)}원</b>")
