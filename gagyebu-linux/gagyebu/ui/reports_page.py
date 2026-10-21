"""결산 보고서: 월결산·년결산·월별 일일결산·사용자정의 결산·년예산."""
import datetime as dt

from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import (QDialog, QHeaderView, QInputDialog, QLabel, QSpinBox, QTabWidget, QVBoxLayout,
                             QWidget)

from .. import db
from ..services import catemoji as E
from ..services import ledger as L
from ..services import reports as RP
from ..util import fmt_money, parse_money
from .widgets import (CENTER, FOOTER_BG, GROUP_BG, SEP_COLOR, SUBTOTAL_BG, CellDelegate, DateEdit, MonthNav, button,
                      cell, error, export_csv, fill, h, make_table, money_cell, print_table, set_tone)


class ReportDelegate(CellDelegate):
    """결산 보고서 칸: 대분류가 끝나는 줄(소계) 아래와 합계 묶음 위에 굵은 선 — 대분류끼리 한눈에 나뉘게"""
    def __init__(self, table):
        super().__init__(table)
        self.table, self.below, self.above = table, set(), set()

    def paint(self, p, opt, idx):
        super().paint(p, opt, idx)
        last = idx.row() + max(1, self.table.rowSpan(idx.row(), idx.column())) - 1
        top, bottom = idx.row() in self.above, last in self.below
        if not (top or bottom):
            return
        p.save()
        p.setPen(QPen(SEP_COLOR, 2))
        r = opt.rect
        if bottom:
            p.drawLine(r.left(), r.bottom(), r.right() + 1, r.bottom())
        if top:
            p.drawLine(r.left(), r.top() + 1, r.right() + 1, r.top() + 1)
        p.restore()


class ReportView(QWidget):
    """Report → 표. on_cell(row, col_index) 콜백으로 상세보기/예산입력.
    금액 칸은 남는 폭을 나눠 가져 표가 화면 폭을 다 채움 (좁으면 가로 스크롤). 0 은 흐리게."""
    def __init__(self, on_cell=None):
        super().__init__()
        self.report, self.on_cell = None, on_cell
        self.table = make_table(['카테고리', '세부 카테고리'])
        self.delegate = ReportDelegate(self.table)
        self.table.setItemDelegate(self.delegate)
        self.table.cellDoubleClicked.connect(self._dbl)
        self.table.viewport().installEventFilter(self)
        self.note = QLabel()
        set_tone(self.note, 'note')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.note)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Resize:
            self._fit()
        return False

    def _fit(self):
        """칸 폭 = 내용에 맞춘 폭, 남는 폭은 금액 칸들에 고르게 (표가 왼쪽에만 몰려 오른쪽이 비지 않게)"""
        t = self.table
        n = t.columnCount()
        if n < 3:
            return
        hh = t.horizontalHeader()
        nat = [max(t.sizeHintForColumn(c), hh.sectionSizeHint(c)) for c in range(n)]
        room = t.viewport().width() - nat[0] - nat[1]          # 금액 칸들이 쓸 수 있는 폭
        amt = sorted(nat[2:])
        if room > sum(amt):
            # 좁은 칸부터 넓혀 금액 칸 폭을 되도록 같게 (물 채우기): level 보다 좁은 칸은 level 로, 넓은 칸은 그대로
            rest, m = room, len(amt)
            while m > 1 and rest // m < amt[m - 1]:      # 가장 넓은 칸이 level 보다 넓으면 그 칸은 빼고 다시
                rest -= amt[m - 1]
                m -= 1
            level = rest // m
            nat[2:] = [max(wd, level) for wd in nat[2:]]
            nat[-1] += room - sum(nat[2:])                          # 나머지 몇 px 는 마지막 칸에
        for c, wd in enumerate(nat):
            hh.resizeSection(c, wd)

    def show_report(self, rep, emap=None):
        """emap: 카테고리 그림 {번호: 그림} (1.8.0) — 카테고리·세부 카테고리 이름 앞에"""
        self.report = rep
        emap = emap or {}
        deco = (lambda code, name: E.deco(emap, code, name)) if emap else (lambda code, name: name)
        t = self.table
        t.clearSpans()
        t.setColumnCount(2 + len(rep.columns))
        t.setHorizontalHeaderLabels(['카테고리', '세부 카테고리'] + rep.columns)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        rows = []
        for r in rep.rows:
            bg = SUBTOTAL_BG if r.kind == 'subtotal' else FOOTER_BG if r.kind == 'footer' else None
            bold = r.kind != 'cat'
            rows.append([cell(deco(r.code[:1], r.group) if r.kind != 'footer' else r.label, CENTER,
                              bg=bg if r.kind == 'footer' else GROUP_BG, bold=True),
                         cell((deco(r.code, r.label) if r.kind == 'cat' else r.label) if r.kind != 'footer' else '',
                              bg=bg, bold=bold)] +
                        [money_cell(v, blank_zero=False, bg=bg, bold=bold) for v in r.values])
        fill(t, rows)
        kinds = [r.kind for r in rep.rows]
        self.delegate.below = {i for i, k in enumerate(kinds) if k == 'subtotal'}
        self.delegate.above = {i for i, k in enumerate(kinds) if k == 'footer' and (i == 0 or kinds[i - 1] != 'footer')}
        start = 0
        while start < len(rep.rows):                     # 대분류 칸 합치기
            r = rep.rows[start]
            if r.kind == 'footer':
                t.setSpan(start, 0, 1, 2)
                start += 1
                continue
            end = start
            while end + 1 < len(rep.rows) and rep.rows[end + 1].kind != 'footer' and rep.rows[end + 1].group == r.group \
                    and rep.rows[end].kind != 'subtotal':
                end += 1
            if end > start:
                t.setSpan(start, 0, end - start + 1, 1)
            start = end + 1
        self._fit()
        self.note.setText(rep.note + ('   · 금액 칸을 두 번 누르면 상세 내역/예산 입력' if self.on_cell else ''))

    def _dbl(self, row, col):
        if self.report and self.on_cell and col >= 2 and row < len(self.report.rows):
            self.on_cell(self.report.rows[row], col - 2)


class DetailDialog(QDialog):
    def __init__(self, parent, con, lid, code, start, end, title):
        super().__init__(parent)
        self.setWindowTitle(title)
        q = 'SELECT * FROM entry WHERE ledger_id=? AND date BETWEEN ? AND ?'
        a = [lid, start.isoformat(), end.isoformat()]
        if code is not None:
            q += ' AND code=?' if len(code) == 2 else ' AND substr(code,1,1)=?'
            a.append(code)
        rows = con.execute(q + ' ORDER BY date, id', a).fetchall()
        from ..services import order as O
        rows = O.apply_day_order(rows, O.day_orders(con, lid))
        cmap = L.category_map(con, lid)
        t = make_table(['날짜', '내용', '수입', '지출', '카테고리', '메모'], stretch=5)
        fill(t, [[cell(r['date'], CENTER), cell(r['item']), money_cell(r['income'], 'in'),
                  money_cell(r['expense'], 'out'), cell(L.code_label(cmap, r['code'])), cell(r['memo'])] for r in rows])
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f'{start} ~ {end}   {len(rows)}건   수입 {fmt_money(sum(r["income"] for r in rows))}   '
                             f'지출 {fmt_money(sum(r["expense"] for r in rows))}'))
        lay.addWidget(t)
        self.resize(760, 480)


class _Tab(QWidget):
    def __init__(self, page, controls, on_cell=None):
        super().__init__()
        self.page = page
        self.view = ReportView(on_cell)
        lay = QVBoxLayout(self)
        lay.addWidget(h(*controls, 'stretch',
                        button('CSV', lambda: export_csv(self, self.view.table, self.view.report.title)),
                        button('인쇄', lambda: print_table(self, self.view.table,
                                                           f'{page.app.ledger_name()} {self.view.report.title}',
                                                           self.view.report.note))))
        lay.addWidget(self.view, 1)


class ReportsPage(QWidget):
    title = '통계'

    def __init__(self, app):
        super().__init__()
        self.app, self.con = app, app.con
        t = dt.date.today()
        self.settle = QSpinBox()
        self.settle.setRange(1, 31)
        self.settle.setSuffix('일')
        self.settle.setToolTip('월 시작일: 5일이면 매달 5일 ~ 다음달 4일을 한 달로 계산')
        self.settle.valueChanged.connect(self._settle_changed)
        self.tabs = QTabWidget()

        self.m_nav = MonthNav()
        self.m_nav.changed.connect(lambda *_: self.refresh())
        self.t_month = _Tab(self, [self.m_nav, QLabel('월 시작일'), self.settle], self._month_cell)
        self.y_spin = _year_spin(t.year)
        self.y_spin.valueChanged.connect(lambda *_: self.refresh())
        self.settle2 = QLabel()
        self.t_year = _Tab(self, [QLabel('연도'), self.y_spin, self.settle2], self._year_cell)
        self.d_nav = MonthNav()
        self.d_nav.changed.connect(lambda *_: self.refresh())
        self.t_daily = _Tab(self, [self.d_nav], self._daily_cell)
        self.c_start, self.c_end = DateEdit(dt.date(t.year, 1, 1)), DateEdit(t)
        self.t_custom = _Tab(self, [QLabel('기간'), self.c_start, QLabel('~'), self.c_end,
                                    button('보기', self.refresh)], self._custom_cell)
        self.b_spin = _year_spin(t.year)
        self.b_spin.valueChanged.connect(lambda *_: self.refresh())
        self.t_budget = _Tab(self, [QLabel('연도'), self.b_spin], self._budget_cell)
        from .extras import InsightTab, TagTab
        from .money_ui import PayStatTab, SavingsTab, WeekStatTab
        self.t_insight = InsightTab(self)
        self.t_tags = TagTab(self)
        self.t_week = WeekStatTab(self)            # 1.8.0
        self.t_pay = PayStatTab(self)
        self.t_save = SavingsTab(self)
        for tab, name in ((self.t_month, '월별'), (self.t_year, '연간'), (self.t_daily, '일별'), (self.t_week, '주별'),
                          (self.t_custom, '기간'), (self.t_budget, '예산'), (self.t_save, '저축'), (self.t_pay, '결제수단'),
                          (self.t_insight, '이달 리포트'), (self.t_tags, '태그')):
            self.tabs.addTab(tab, name)
        self.tabs.currentChanged.connect(lambda *_: self.refresh())
        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs)

    def sd(self):
        return RP.settle_day(self.con)

    def _settle_changed(self, v):
        db.set_meta(self.con, 'settle_day', v)
        self.con.commit()
        self.refresh()

    def refresh(self):
        lid, sd = self.app.lid, self.sd()
        self.settle.blockSignals(True)
        self.settle.setValue(sd)
        self.settle.blockSignals(False)
        self.settle2.setText(f'(월 시작일 {sd}일 — 월별 탭에서 변경)')
        w = self.tabs.currentWidget()
        emap = E.emoji_map(self.con, lid)
        if w is self.t_month:
            self.t_month.view.show_report(RP.monthly(self.con, lid, self.m_nav.y, self.m_nav.m, sd), emap)
        elif w is self.t_year:
            self.t_year.view.show_report(RP.yearly(self.con, lid, self.y_spin.value(), sd), emap)
        elif w is self.t_daily:
            self.t_daily.view.show_report(RP.daily(self.con, lid, self.d_nav.y, self.d_nav.m), emap)
        elif w is self.t_custom:
            s, e = self.c_start.date_(), self.c_end.date_()
            if s > e:
                error(self, '시작일이 종료일보다 늦습니다.')
                return
            self.t_custom.view.show_report(RP.custom(self.con, lid, s, e), emap)
        elif w is self.t_budget:
            self.t_budget.view.show_report(RP.budget_year(self.con, lid, self.b_spin.value()), emap)
        elif hasattr(w, 'refresh'):
            w.refresh()

    # ── 칸 두 번 누르기 ──
    def _detail(self, row, period):
        if not period or row.kind == 'footer':
            return
        code = row.code if row.kind == 'cat' else row.code      # 소계 행 code = 대분류 한 글자
        DetailDialog(self, self.con, self.app.lid, code, period[0], period[1],
                     f'상세 내역 — {row.group} / {row.label}').exec()

    def _month_cell(self, row, col):
        rep = self.t_month.view.report
        if col in (0, 1):
            self._detail(row, rep.periods[col])
        elif col in (3, 4) and row.kind == 'cat':
            y, m = self.m_nav.y, self.m_nav.m
            if col == 4:
                k = y * 12 + m
                y, m = k // 12, k % 12 + 1
            self._edit_budget(row, f'{y:04d}-{m:02d}')

    def _year_cell(self, row, col):
        self._detail(row, self.t_year.view.report.periods[col])

    def _daily_cell(self, row, col):
        self._detail(row, self.t_daily.view.report.periods[col])

    def _custom_cell(self, row, col):
        self._detail(row, self.t_custom.view.report.periods[col])

    def _budget_cell(self, row, col):
        ym = self.t_budget.view.report.periods[col]
        if ym and row.kind == 'cat':
            self._edit_budget(row, ym)

    def _edit_budget(self, row, ym):
        from ..services.reports import budgets
        cur = budgets(self.con, self.app.lid, ym).get(row.code, 0)
        txt, ok = QInputDialog.getText(self, '예산 입력', f'{ym}  {row.group} / {row.label} 예산 (0이면 삭제)',
                                       text=fmt_money(cur) if cur else '')
        if not ok:
            return
        try:
            RP.set_budget(self.con, self.app.lid, ym, row.code, parse_money(txt))
        except ValueError:
            error(self, '금액은 숫자로 입력하세요.')
            return
        self.refresh()


def _year_spin(y):
    s = QSpinBox()
    s.setRange(1990, 2100)
    s.setValue(y)
    s.setSuffix('년')
    return s
