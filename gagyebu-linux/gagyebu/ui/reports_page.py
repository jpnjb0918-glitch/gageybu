"""결산 보고서: 월결산·년결산·월별 일일결산·사용자정의 결산·년예산."""
import datetime as dt

from PyQt6.QtWidgets import (QDialog, QHeaderView, QInputDialog, QLabel, QSpinBox, QTabWidget, QVBoxLayout,
                             QWidget)

from .. import db
from ..services import ledger as L
from ..services import reports as RP
from ..util import fmt_money, parse_money
from .widgets import (CENTER, FOOTER_BG, SUBTOTAL_BG, DateEdit, MonthNav, button, cell, error, export_csv, fill,
                      h, make_table, money_cell, print_table)


class ReportView(QWidget):
    """Report → 표. on_cell(row, col_index) 콜백으로 상세보기/예산입력."""
    def __init__(self, on_cell=None):
        super().__init__()
        self.report, self.on_cell = None, on_cell
        self.table = make_table(['대분류', '소분류'])
        self.table.cellDoubleClicked.connect(self._dbl)
        self.note = QLabel()
        self.note.setStyleSheet('color:#777')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.table, 1)
        lay.addWidget(self.note)

    def show_report(self, rep):
        self.report = rep
        t = self.table
        t.clearSpans()
        t.setColumnCount(2 + len(rep.columns))
        t.setHorizontalHeaderLabels(['대분류', '소분류'] + rep.columns)
        rows = []
        for r in rep.rows:
            bg = SUBTOTAL_BG if r.kind == 'subtotal' else FOOTER_BG if r.kind == 'footer' else None
            bold = r.kind != 'cat'
            rows.append([cell(r.group if r.kind != 'footer' else r.label, CENTER, bg=bg, bold=r.kind == 'footer'),
                         cell(r.label if r.kind != 'footer' else '', bg=bg, bold=bold)] +
                        [money_cell(v, blank_zero=False, bg=bg, bold=bold) for v in r.values])
        fill(t, rows)
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
        hh = t.horizontalHeader()
        for c in range(2, t.columnCount()):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
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
        t = make_table(['날짜', '품목', '수입', '지출', '계정과목', '메모'], stretch=5)
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
    title = '결산 보고서'

    def __init__(self, app):
        super().__init__()
        self.app, self.con = app, app.con
        t = dt.date.today()
        self.settle = QSpinBox()
        self.settle.setRange(1, 31)
        self.settle.setSuffix('일')
        self.settle.setToolTip('결산일: 5일이면 매달 5일 ~ 다음달 4일을 한 달로 계산')
        self.settle.valueChanged.connect(self._settle_changed)
        self.tabs = QTabWidget()

        self.m_nav = MonthNav()
        self.m_nav.changed.connect(lambda *_: self.refresh())
        self.t_month = _Tab(self, [self.m_nav, QLabel('결산일'), self.settle], self._month_cell)
        self.y_spin = _year_spin(t.year)
        self.y_spin.valueChanged.connect(lambda *_: self.refresh())
        self.settle2 = QLabel()
        self.t_year = _Tab(self, [QLabel('연도'), self.y_spin, self.settle2], self._year_cell)
        self.d_nav = MonthNav()
        self.d_nav.changed.connect(lambda *_: self.refresh())
        self.t_daily = _Tab(self, [self.d_nav], self._daily_cell)
        self.c_start, self.c_end = DateEdit(dt.date(t.year, 1, 1)), DateEdit(t)
        self.t_custom = _Tab(self, [QLabel('기간'), self.c_start, QLabel('~'), self.c_end,
                                    button('결산', self.refresh)], self._custom_cell)
        self.b_spin = _year_spin(t.year)
        self.b_spin.valueChanged.connect(lambda *_: self.refresh())
        self.t_budget = _Tab(self, [QLabel('연도'), self.b_spin], self._budget_cell)
        for tab, name in ((self.t_month, '월결산'), (self.t_year, '년결산'), (self.t_daily, '월별 일일결산'),
                          (self.t_custom, '사용자정의 결산'), (self.t_budget, '년예산')):
            self.tabs.addTab(tab, name)
        self.tabs.currentChanged.connect(lambda *_: self.refresh())
        lay = QVBoxLayout(self)
        lay.addWidget(self.tabs)

    def sd(self):
        return int(db.get_meta(self.con, 'settle_day', 1) or 1)

    def _settle_changed(self, v):
        db.set_meta(self.con, 'settle_day', v)
        self.con.commit()
        self.refresh()

    def refresh(self):
        lid, sd = self.app.lid, self.sd()
        self.settle.blockSignals(True)
        self.settle.setValue(sd)
        self.settle.blockSignals(False)
        self.settle2.setText(f'(결산일 {sd}일 — 월결산 탭에서 변경)')
        i = self.tabs.currentIndex()
        if i == 0:
            self.t_month.view.show_report(RP.monthly(self.con, lid, self.m_nav.y, self.m_nav.m, sd))
        elif i == 1:
            self.t_year.view.show_report(RP.yearly(self.con, lid, self.y_spin.value(), sd))
        elif i == 2:
            self.t_daily.view.show_report(RP.daily(self.con, lid, self.d_nav.y, self.d_nav.m))
        elif i == 3:
            s, e = self.c_start.date_(), self.c_end.date_()
            if s > e:
                error(self, '시작일이 종료일보다 늦습니다.')
                return
            self.t_custom.view.show_report(RP.custom(self.con, lid, s, e))
        else:
            self.t_budget.view.show_report(RP.budget_year(self.con, lid, self.b_spin.value()))

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
