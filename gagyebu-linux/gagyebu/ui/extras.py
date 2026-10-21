"""1.7.0 화면 조각: 문자 붙여넣기 · 자주 쓰는 내역 · 내역 사진 · 예산 막대/예산 정하기 · 자산 간 이체 ·
저축 목표 · 빌려준 돈/빌린 돈 · 이달 리포트 · 태그. 계산은 services/ 에 있고 여기는 화면만."""
import datetime as dt
import html
import os
import re

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QImage, QImageReader, QPainter, QPixmap
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
                             QFileDialog, QFormLayout, QGroupBox, QLabel, QListView, QListWidget,
                             QListWidgetItem, QPlainTextEdit, QScrollArea, QSplitter, QTableWidgetItem, QTextBrowser,
                             QVBoxLayout, QWidget)

from .. import theme as T
from ..services import assets as A
from ..services import attach as AT
from ..services import goals as G
from ..services import insights as INS
from ..services import ledger as L
from ..services import reports as RP
from ..services import smsparse as SMS
from ..services.reports import settle_day
from ..util import add_months, calc_money, fmt_money, is_income_code, month_end, settle_period, to_date
from . import icons as I
from .widgets import (CENTER, CodeCombo, DateEdit, FormDialog, ID_ROLE, MoneyEdit, MonthNav, PayCombo, button, cell,
                      confirm, error, fill, h, info, make_table, money_cell, ok_cancel, selected_id, selected_ids,
                      set_tone)




def alert_after(con, lid, code, date, before):
    """저장 뒤 예산 알림 글 (없으면 None)"""
    try:
        return INS.budget_alert(con, lid, code, date, before, settle_day(con))
    except Exception:        # 알림은 덤 — 실패해도 저장은 된 것
        return None


def spent_before(con, lid, code, date):
    return INS.code_spent(con, lid, code, date, settle_day(con)) if code else 0


def month_before(con, lid, date):
    """그 달 지출 전체 (한 달 전체 예산 알림용, 1.8.0)"""
    from ..services import money as M
    return M.month_spent(con, lid, date, settle_day(con))


def total_alert_after(con, lid, date, before):
    from ..services import money as M
    try:
        return M.total_alert(con, lid, date, before, settle_day(con))
    except Exception:        # 알림은 덤
        return None


# ── 막대 ───────────────────────────────────────────────
WARN_COLOR = '#D98A00'


class Bar(QWidget):
    """진행 막대: 80% 까지 포인트 색, 80~100% 주황, 넘으면 지출색"""
    def __init__(self, height=8, parent=None):
        super().__init__(parent)
        self.pct = 0
        self.color = None
        self.setFixedHeight(height)
        self.setMinimumWidth(40)

    def set(self, pct, color=None):
        self.pct = max(0, pct or 0)
        self.color = color
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        pal = self.palette()
        track = QColor(T.mix(pal.base().color().name(), pal.text().color().name(), 0.13))
        rad = r.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, rad, rad)
        if self.pct > 0:
            if self.color:
                col = QColor(self.color)
            elif self.pct > 100:
                col = QColor(T.tone()['out'])
            elif self.pct >= 80:
                col = QColor(WARN_COLOR)
            else:
                col = pal.highlight().color()
            w = max(r.height(), r.width() * min(self.pct, 100) / 100)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(r.left(), r.top(), w, r.height()), rad, rad)
        p.end()


def _pct_text(pct):
    return '—' if pct is None else f'{pct}%'


class WeekBars(QWidget):
    """이번 주 월~일 날마다 쓴 돈 작은 막대 (1.8.0)"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.days, self.today = [], ''
        self.setFixedHeight(46)
        self.setMinimumWidth(140)

    def set(self, days, today):
        self.days, self.today = days, today
        self.setToolTip('\n'.join(f"{'월화수목금토일'[i]} {d['date'][5:]}  {fmt_money(d['spent'])}원" for i, d in enumerate(days)))
        self.update()

    def paintEvent(self, _ev):
        if not self.days:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        txt = pal.text().color()
        track = QColor(T.mix(pal.base().color().name(), txt.name(), 0.10))
        top = max([d['spent'] for d in self.days] + [1])
        n = len(self.days)
        w = self.width() / n
        bh = self.height() - 16
        f = p.font()
        f.setPixelSize(10)
        p.setFont(f)
        for i, d in enumerate(self.days):
            x = i * w + w * 0.22
            bw = w * 0.56
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(track)
            p.drawRoundedRect(QRectF(x, 0, bw, bh), 3, 3)
            if d['spent'] > 0:
                hh = max(3.0, bh * d['spent'] / top)
                col = pal.highlight().color() if d['date'] != self.today else QColor(T.tone()['out'])
                p.setBrush(col)
                p.drawRoundedRect(QRectF(x, bh - hh, bw, hh), 3, 3)
            p.setPen(txt if d['date'] != self.today else QColor(T.tone()['out']))
            p.drawText(QRectF(i * w, bh + 1, w, 14), Qt.AlignmentFlag.AlignCenter, '월화수목금토일'[i])
        p.end()


# ── 예산 막대 (가계부 화면 오른쪽) ────────────────────────
class BudgetCard(QGroupBox):
    """그 달 예산 진행 막대 + 하루에 쓸 수 있는 돈 + 무지출 날. [예산 정하기…] 로 바로 정함"""
    MAX_ROWS = 6

    def __init__(self, page):
        super().__init__('이달 예산')
        self.page, self.con = page, page.con
        self.ym = None
        lay = QVBoxLayout(self)
        lay.setSpacing(4)
        self.total_lbl = QLabel()
        self.total_lbl.setWordWrap(True)
        self.total_bar = Bar(10)
        self.sub_lbl = set_tone(QLabel(), 'note')
        self.sub_lbl.setWordWrap(True)
        self.rows = QWidget()
        self.rows_lay = QVBoxLayout(self.rows)
        self.rows_lay.setContentsMargins(0, 2, 0, 2)
        self.rows_lay.setSpacing(3)
        self.empty_lbl = set_tone(QLabel('아직 이달 예산이 없어요. 한 달 전체나 카테고리별로 정해 두면 얼마나 썼는지 막대로 보여 주고, '
                                         '80%·100%를 넘을 때 알려 드려요.'), 'note')
        self.empty_lbl.setWordWrap(True)
        self.ns_lbl = QLabel()
        self.ns_lbl.setWordWrap(True)
        self.week = QWidget()                      # 이번 주 (주간 예산, 1.8.0)
        wl = QVBoxLayout(self.week)
        wl.setContentsMargins(0, 4, 0, 0)
        wl.setSpacing(2)
        self.week_lbl = QLabel()
        self.week_lbl.setWordWrap(True)
        self.week_bar = Bar(8)
        self.week_days = WeekBars()
        wl.addWidget(self.week_lbl)
        wl.addWidget(self.week_bar)
        wl.addWidget(self.week_days)
        self.set_btn = button('예산 정하기…', self.edit)
        lay.addWidget(self.total_lbl)
        lay.addWidget(self.total_bar)
        lay.addWidget(self.sub_lbl)
        lay.addWidget(self.rows)
        lay.addWidget(self.empty_lbl)
        lay.addWidget(self.week)
        lay.addWidget(self.ns_lbl)
        lay.addWidget(h(self.set_btn, 'stretch'))

    def load(self, lid, y, m):
        self.lid, self.ym = lid, (y, m)
        sd = settle_day(self.con)
        today = dt.date.today()
        bp = INS.budget_progress(self.con, lid, y, m, sd, today)
        start, end = to_date(bp['start']), to_date(bp['end'])
        self.setTitle(f'{m}월 예산' + (f'  ({start:%m.%d}~{end:%m.%d})' if sd != 1 else ''))
        has = bool(bp['rows']) or bp.get('total', False)
        for w in (self.total_lbl, self.total_bar, self.sub_lbl, self.rows):
            w.setVisible(has)
        from ..services import money as M
        wb = M.week_budget(self.con, lid)
        self.empty_lbl.setVisible(not has and not wb)
        while self.rows_lay.count():
            it = self.rows_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if has:
            tn = T.tone()
            over = bp['left'] < 0
            self.total_lbl.setText(('전체 예산 ' if bp.get('total') else '') + f"<b>{fmt_money(bp['spent'])}</b> / {fmt_money(bp['budget'])}원 "
                                   f"<span style='color:{tn['out'] if over else tn['text2']}'>({_pct_text(bp['pct'])})</span>")
            self.total_bar.set(bp['pct'])
            if over:
                sub = f"예산보다 {fmt_money(-bp['left'])}원 더 썼어요"
            elif start <= today <= end:
                sub = f"남은 돈 {fmt_money(bp['left'])}원 · 하루 {fmt_money(bp['per_day'])}원씩 ({bp['days_left']}일 남음)"
            else:
                sub = f"남은 돈 {fmt_money(bp['left'])}원"
            self.sub_lbl.setText(sub)
            for r in bp['rows'][:self.MAX_ROWS]:
                w = QWidget()
                wl = QVBoxLayout(w)
                wl.setContentsMargins(0, 0, 0, 0)
                wl.setSpacing(1)
                col = tn['out'] if r['left'] < 0 else tn['text2']
                lab = QLabel(f"{html.escape(r['name'])} <span style='color:{col}'>{fmt_money(r['spent'])} / "
                             f"{fmt_money(r['budget'])} ({_pct_text(r['pct'])})</span>")
                bar = Bar(6)
                bar.set(r['pct'])
                wl.addWidget(lab)
                wl.addWidget(bar)
                self.rows_lay.addWidget(w)
            more = len(bp['rows']) - self.MAX_ROWS
            if more > 0:
                self.rows_lay.addWidget(set_tone(QLabel(f'외 {more}개 — 통계 › 이달 리포트에서 모두 보기'), 'note'))
        # 이번 주 (주간 예산을 정했으면, 보고 있는 달에 오늘이 들어 있을 때)
        if wb and start <= today <= end:
            wk = M.week_progress(self.con, lid, today, today)
            tn = T.tone()
            over = wk['left'] < 0
            self.week_lbl.setText(f"이번 주 ({to_date(wk['start']):%m.%d}~{to_date(wk['end']):%m.%d}) <b>{fmt_money(wk['spent'])}</b>"
                                  f" / {fmt_money(wk['budget'])}원 <span style='color:{tn['out'] if over else tn['text2']}'>"
                                  + (f"({fmt_money(-wk['left'])}원 넘음)" if over else
                                     f"(남은 돈 {fmt_money(wk['left'])} · 하루 {fmt_money(wk['per_day'])})") + '</span>')
            self.week_bar.set(wk['pct'])
            self.week_days.set(wk['days'], today.isoformat())
            self.week.setVisible(True)
        else:
            self.week.setVisible(False)
        # 무지출 날
        if start <= today:
            upto = min(end, today)
            ns = len(INS.no_spend_days(self.con, lid, start, upto))
            streak = INS.no_spend_streak(self.con, lid, today) if start <= today <= end else 0
            txt = f'무지출 {ns}일' + (f' · 오늘까지 {streak}일째 이어지는 중' if streak >= 2 else
                                     ' · 오늘은 아직 안 썼어요' if streak == 1 else '')
            self.ns_lbl.setText(txt)
            self.ns_lbl.setVisible(True)
        else:
            self.ns_lbl.setVisible(False)

    def edit(self):
        y, m = self.ym or (dt.date.today().year, dt.date.today().month)
        if BudgetDialog(self, self.con, self.page.app.lid, y, m).exec():
            self.page.app.data_changed()


class BudgetDialog(QDialog):
    """계정별 그 달 예산 정하기 (같은 금액을 다음 달들에도)"""
    def __init__(self, parent, con, lid, y, m):
        super().__init__(parent)
        self.con, self.lid, self.y, self.m = con, lid, y, m
        self.setWindowTitle(f'{y}년 {m}월 예산 정하기')
        sd = settle_day(con)
        py, pm = add_months(y, m, -1)
        ps, pe = settle_period(py, pm, sd)
        prev_spent = {c: v for c, v in RP._sum_by_code(con, lid, ps, pe).items()}
        cur = RP.budgets(con, lid, f'{y:04d}-{m:02d}')
        self.prev_bud = RP.budgets(con, lid, f'{py:04d}-{pm:02d}')
        self.table = make_table(['카테고리', f'지난달({pm}월) 쓴 돈', f'{m}월 예산'], stretch=0)
        self.edits = {}
        cats = [c for c in L.categories(con, lid) if not is_income_code(c['code'])]
        self.table.setRowCount(len(cats))
        for i, c in enumerate(cats):
            self.table.setItem(i, 0, cell(f"{c['code']}  {c['name']}"))
            self.table.setItem(i, 1, money_cell(prev_spent.get(c['code'], 0), blank_zero=False))
            e = MoneyEdit()
            e.set_value(cur.get(c['code'], 0))
            self.table.setCellWidget(i, 2, e)
            self.edits[c['code']] = e
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.horizontalHeader().setMinimumSectionSize(110)
        self.span = QComboBox()
        self.span.addItem(f'{m}월만', 1)
        if m < 12:
            self.span.addItem(f'{m}월부터 12월까지 같게', 13 - m)
        self.span.addItem(f'{m}월부터 12달 동안 같게', 12)
        from ..services import money as M          # 한 달 전체 예산 · 주간 예산 (1.8.0)
        self.month_total = MoneyEdit()
        self.month_total.set_value(M.total_budget(con, lid, f'{y:04d}-{m:02d}'))
        self.week_total = MoneyEdit()
        self.week_total.set_value(M.week_budget(con, lid))
        self.total = QLabel()
        for e in self.edits.values():
            e.editingFinished.connect(self._sum)
        bb = ok_cancel(self, '저장', self._ok)
        lay = QVBoxLayout(self)
        top = QFormLayout()
        top.addRow('한 달 전체 예산', h(self.month_total, set_tone(QLabel('카테고리를 나누지 않고 한 달에 쓸 돈 (비우면 안 씀)'), 'note'), 'stretch'))
        top.addRow('주간 예산 (매주)', h(self.week_total, set_tone(QLabel('월~일 한 주에 쓸 돈 (비우면 안 씀)'), 'note'), 'stretch'))
        lay.addLayout(top)
        lay.addWidget(set_tone(QLabel('카테고리별 예산 — 쓰지 않을 카테고리는 비워 두세요. 금액 칸에 계산식(예: 300000/4)도 됩니다.'
                                      + (f'  월 시작일 {sd}일 기준 기간으로 셉니다.' if sd != 1 else '')), 'note'))
        lay.addWidget(self.table, 1)
        lay.addWidget(h(button('지난달 예산 가져오기', self._copy_prev), button('모두 비우기', self._clear), 'stretch',
                        self.total))
        lay.addWidget(h(QLabel('적용할 달'), self.span, 'stretch'))
        lay.addWidget(bb)
        self.resize(560, 620)
        self._sum()

    def _vals(self):
        return {c: e.value() for c, e in self.edits.items()}

    def _sum(self):
        try:
            self.total.setText(f'합계 {fmt_money(sum(self._vals().values()))}원')
        except ValueError:
            self.total.setText('')

    def _copy_prev(self):
        if not self.prev_bud:
            info(self, '지난달에 정한 예산이 없습니다.')
            return
        for c, e in self.edits.items():
            e.set_value(self.prev_bud.get(c, 0))
        self._sum()

    def _clear(self):
        for e in self.edits.values():
            e.clear()
        self._sum()

    def _ok(self):
        try:
            vals = self._vals()
            mt, wt = self.month_total.value(), self.week_total.value()
        except ValueError:
            error(self, '금액은 숫자(또는 계산식)로 입력하세요.')
            return
        if any(v < 0 for v in vals.values()) or mt < 0 or wt < 0:
            error(self, '예산은 0 이상으로 입력하세요.')
            return
        n = self.span.currentData()
        yms = []
        y, m = self.y, self.m
        for _ in range(n):
            yms.append(f'{y:04d}-{m:02d}')
            y, m = add_months(y, m, 1)
        RP.set_budgets(self.con, self.lid, yms, vals)
        from ..services import money as M
        M.set_total_budget(self.con, self.lid, yms, mt)
        M.set_week_budget(self.con, self.lid, wt)
        self.accept()


# ── 문자 붙여넣기 ───────────────────────────────────────
SMS_HINT = ('[Web발신]\n신한카드(1234)승인 홍*동 12,500원 일시불 10/19 08:41 스타벅스 누적345,600원\n\n'
            '[Web발신]\nKB국민카드 3*0*승인 홍*동 45,000원 일시불 10/18 19:02 교촌치킨')
_EDITABLE = (QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed
             | QAbstractItemView.EditTrigger.AnyKeyPressed | QAbstractItemView.EditTrigger.SelectedClicked)
C_CHK, C_DATE, C_ITEM, C_IN, C_OUT, C_CODE, C_MEMO, C_PAY = range(8)


def looks_like_sms(text):
    return bool(re.search(r'\d[\d,]*\s*원', text or '')) and bool(re.search(r'\d{1,2}[./-]\d{1,2}', text or ''))


class SmsDialog(QDialog):
    """카드·은행 알림 문자 → 내역 후보 표 (고쳐서 저장)"""
    def __init__(self, parent, con, lid):
        super().__init__(parent)
        self.con, self.lid = con, lid
        self.saved, self.alerts = 0, []
        self.setWindowTitle('문자 붙여넣기 — 카드·은행 알림 문자로 내역 넣기')
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText('카드·은행 알림 문자를 복사해서 여기에 붙여넣으세요. 여러 개를 한꺼번에 넣어도 됩니다.\n\n'
                                     '예)\n' + SMS_HINT)
        self.text.setMinimumHeight(110)
        self.table = make_table(['넣기', '날짜', '내용', '수입', '지출', '카테고리', '메모', '결제수단'], stretch=C_MEMO)
        self.table.setEditTriggers(_EDITABLE)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.status = set_tone(QLabel('붙여넣은 뒤 [읽기]를 누르세요.'), 'note')
        self.status.setWordWrap(True)
        self.save_btn = button('고른 내역 저장', self._save)
        self.save_btn.setEnabled(False)
        sp = QSplitter(Qt.Orientation.Vertical)
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(self.text, 1)
        tl.addWidget(h(button('클립보드에서 붙여넣기', self._paste), button('읽기', self.parse), button('지우기', self._clear),
                       'stretch'))
        sp.addWidget(top)
        bot = QWidget()
        bl = QVBoxLayout(bot)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(self.table, 1)
        bl.addWidget(self.status)
        sp.addWidget(bot)
        sp.setStretchFactor(1, 2)
        lay = QVBoxLayout(self)
        lay.addWidget(sp, 1)
        lay.addWidget(h(set_tone(QLabel('칸을 두 번 누르면 고칠 수 있어요. 취소 문자는 지출을 빼는 내역(−)으로 들어갑니다.'), 'note'),
                        'stretch', self.save_btn, button('닫기', self.reject)))
        self.resize(900, 640)
        cb = QApplication.clipboard().text() if QApplication.clipboard() else ''
        if looks_like_sms(cb):
            self.text.setPlainText(cb)
            self.parse()

    def _paste(self):
        cb = QApplication.clipboard().text()
        if cb:
            self.text.setPlainText(cb)
            self.parse()

    def _clear(self):
        self.text.clear()
        fill(self.table, [])
        self.save_btn.setEnabled(False)

    def _dup(self, e):
        return self.con.execute('SELECT 1 FROM entry WHERE ledger_id=? AND date=? AND item=? AND income=? AND expense=? LIMIT 1',
                                (self.lid, e['date'], e['item'], e['income'], e['expense'])).fetchone() is not None

    def parse(self):
        found = SMS.parse(self.text.toPlainText(), dt.date.today())
        self.table.setRowCount(0)
        self.table.setRowCount(len(found))
        n_ok = n_dup = 0
        for i, p in enumerate(found):
            e = SMS.to_entry(p, self.con)            # 결제수단도 짐작 (은행 → 계좌이체, 넣어 둔 카드 → 그 카드)
            dup = bool(p['ok']) and self._dup(e)
            ok = bool(p['ok']) and not dup
            n_ok += ok
            n_dup += dup
            chk = QTableWidgetItem('이미 있음' if dup else '' if p['ok'] else '확인 필요')
            chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            chk.setCheckState(Qt.CheckState.Checked if ok else Qt.CheckState.Unchecked)
            chk.setToolTip(p['raw'])
            self.table.setItem(i, C_CHK, chk)
            self.table.setItem(i, C_DATE, cell(e['date'] or '', CENTER))
            self.table.setItem(i, C_ITEM, cell(e['item']))
            self.table.setItem(i, C_IN, money_cell(e['income'], 'in'))
            self.table.setItem(i, C_OUT, money_cell(e['expense'], 'out'))
            combo = CodeCombo(self.con)
            combo.load(self.lid)
            combo.set_code(SMS.guess_code(self.con, self.lid, p['item'], p['kind'] == 'in'))
            self.table.setCellWidget(i, C_CODE, combo)
            self.table.setItem(i, C_MEMO, cell(e['memo']))
            pc = PayCombo(self.con)
            pc.load()
            pc.set_pay(e['pay'])
            self.table.setCellWidget(i, C_PAY, pc)
            for c in (C_CHK, C_CODE):
                it = self.table.item(i, c)
                if it is not None:
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
        self.table.resizeColumnsToContents()
        if not found:
            self.status.setText('문자에서 내역을 찾지 못했습니다. 카드·은행 알림 문자를 그대로 붙여넣었는지 확인하세요.')
        else:
            bits = [f'{len(found)}건을 찾았어요']
            if n_dup:
                bits.append(f'이미 넣은 것 {n_dup}건은 빼 두었어요')
            if len(found) - n_ok - n_dup:
                bits.append(f'날짜나 금액을 못 찾은 {len(found) - n_ok - n_dup}건은 고친 뒤 체크하세요')
            self.status.setText(' · '.join(bits) + '.')
        self.save_btn.setEnabled(bool(found))

    def _row_value(self, i):
        t = lambda c: (self.table.item(i, c).text().strip() if self.table.item(i, c) else '')   # noqa: E731
        try:
            d = dt.date.fromisoformat(t(C_DATE))
        except ValueError:
            raise ValueError(f'{i + 1}번째 줄: 날짜를 2026-10-19 처럼 입력하세요.')
        try:
            inc, exp = calc_money(t(C_IN)), calc_money(t(C_OUT))
        except ValueError:
            raise ValueError(f'{i + 1}번째 줄: 금액은 숫자로 입력하세요.')
        if not t(C_ITEM):
            raise ValueError(f'{i + 1}번째 줄: 내용을 입력하세요.')
        if not inc and not exp:
            raise ValueError(f'{i + 1}번째 줄: 수입 또는 지출 금액을 입력하세요.')
        code = self.table.cellWidget(i, C_CODE).code()
        if not code:
            raise ValueError(f'{i + 1}번째 줄: 카테고리를 고르세요.')
        return {'date': d, 'item': t(C_ITEM), 'income': inc, 'expense': exp, 'code': code, 'memo': t(C_MEMO),
                'pay': self.table.cellWidget(i, C_PAY).pay()}

    def _save(self):
        rows = [i for i in range(self.table.rowCount())
                if self.table.item(i, C_CHK).checkState() == Qt.CheckState.Checked]
        if not rows:
            error(self, '저장할 내역을 체크하세요.')
            return
        try:
            vals = [self._row_value(i) for i in rows]
        except ValueError as ex:
            error(self, str(ex))
            return
        alerts = []
        for v in vals:
            before = spent_before(self.con, self.lid, v['code'], v['date'])
            before_m = month_before(self.con, self.lid, v['date'])
            L.add_entry(self.con, self.lid, v)
            for a in (alert_after(self.con, self.lid, v['code'], v['date'], before),
                      total_alert_after(self.con, self.lid, v['date'], before_m)):
                if a and a not in alerts:
                    alerts.append(a)
        self.saved, self.alerts = len(vals), alerts
        self.accept()


# ── 자주 쓰는 내역 ──────────────────────────────────────
def favorite_label(cmap, f):
    amt = f"+{fmt_money(f['income'])}" if f['income'] else f"{fmt_money(f['expense'])}원" if f['expense'] else ''
    return '  '.join(x for x in (f['item'], amt, L.code_label(cmap, f['code']) if f['code'] else '') if x)


class FavoritesDialog(QDialog):
    """자주 쓰는 내역 정리 (순서·지우기)"""
    def __init__(self, parent, con, lid):
        super().__init__(parent)
        self.con, self.lid = con, lid
        self.setWindowTitle('자주 쓰는 내역 정리')
        self.table = make_table(['내용', '수입', '지출', '카테고리', '메모', '결제수단'], stretch=4)
        lay = QVBoxLayout(self)
        lay.addWidget(set_tone(QLabel('가계부 입력 상자의 [★ 자주 쓰는 내역]에서 고르면 칸이 한 번에 채워집니다. '
                                      '새로 넣으려면 입력 칸을 채운 뒤 [지금 입력을 자주 쓰는 내역에 넣기].'), 'note'))
        lay.addWidget(self.table, 1)
        lay.addWidget(h(button('위로', lambda: self._move(-1)), button('아래로', lambda: self._move(1)),
                        button('지우기', self._del), 'stretch', button('닫기', self.accept)))
        self.resize(620, 420)
        self.load()

    def load(self, sel=None):
        cmap = L.category_map(self.con, self.lid)
        from ..services import money as M
        pmap = M.pay_map(self.con)
        rows = L.favorites(self.con, self.lid)
        fill(self.table, [[cell(f['item'], data=f['id']), money_cell(f['income'], 'in'), money_cell(f['expense'], 'out'),
                           cell(L.code_label(cmap, f['code']) if f['code'] else ''), cell(f['memo']),
                           cell(M.pay_label(pmap, f['pay']))] for f in rows])
        for r, f in enumerate(rows):
            if f['id'] == sel:
                self.table.selectRow(r)

    def _move(self, d):
        ids = selected_ids(self.table)
        if ids:
            L.move_favorite(self.con, self.lid, ids[0], d)
            self.load(ids[0])

    def _del(self):
        ids = selected_ids(self.table)
        if ids and confirm(self, '고른 자주 쓰는 내역을 지울까요? (이미 넣은 내역은 그대로입니다)'):
            L.delete_favorite(self.con, ids[0])
            self.load()


# ── 내역 사진 ──────────────────────────────────────────
IMAGE_FILTER = '사진 (*.jpg *.jpeg *.png *.webp *.bmp *.gif *.heic)'


def prepare_image(path):
    """사진 파일 → (JPEG bytes, 이름). 긴 변 1600px 로 줄이고 회전 정보대로 바로 세움"""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    img = reader.read()
    if img.isNull():
        raise ValueError(f'사진을 열 수 없습니다: {os.path.basename(path)} ({reader.errorString()})')
    return image_bytes(img), os.path.splitext(os.path.basename(path))[0] + '.jpg'


def image_bytes(img):
    if max(img.width(), img.height()) > AT.MAX_SIDE:
        img = img.scaled(AT.MAX_SIDE, AT.MAX_SIDE, Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    if img.hasAlphaChannel():                  # 투명한 곳은 흰색으로 (JPEG 은 투명이 없음)
        bg = QImage(img.size(), QImage.Format.Format_RGB32)
        bg.fill(QColor('#FFFFFF'))
        p = QPainter(bg)
        p.drawImage(0, 0, img)
        p.end()
        img = bg
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, 'JPEG', AT.QUALITY)
    buf.close()
    return bytes(ba)


def pixmap_of(data):
    pm = QPixmap()
    pm.loadFromData(bytes(data))
    return pm


class PhotoViewer(QDialog):
    def __init__(self, parent, data, title):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.pm = pixmap_of(data)
        self.lab = QLabel()
        self.lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setWidget(self.lab)
        lay = QVBoxLayout(self)
        lay.addWidget(sc)
        scr = QApplication.primaryScreen().availableGeometry() if QApplication.primaryScreen() else None
        w, hh = (min(self.pm.width() + 40, int(scr.width() * 0.85)), min(self.pm.height() + 60, int(scr.height() * 0.85))) \
            if scr else (900, 700)
        self.resize(max(320, w), max(240, hh))

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if not self.pm.isNull():
            s = self.size() - QSize(40, 50)
            self.lab.setPixmap(self.pm if self.pm.width() <= s.width() and self.pm.height() <= s.height() else
                               self.pm.scaled(s, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


class PhotoDialog(QDialog):
    """내역 사진 (영수증). entry_id 가 있으면 바로 자료 파일에, 없으면(새 내역) pending 목록에 넣었다가 저장할 때 함께"""
    THUMB = 150

    def __init__(self, parent, con, entry_id=None, pending=None, title=''):
        super().__init__(parent)
        self.con, self.eid = con, entry_id
        self.pending = pending if pending is not None else []
        self.changed = False
        self.setWindowTitle('내역 사진' + (f' — {title}' if title else ''))
        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setIconSize(QSize(self.THUMB, self.THUMB))
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setSpacing(8)
        self.list.itemDoubleClicked.connect(lambda *_: self._view())
        self.note = set_tone(QLabel(), 'note')
        self.note.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addWidget(self.list, 1)
        lay.addWidget(self.note)
        lay.addWidget(h(button('사진 넣기…', self._add), button('크게 보기', self._view), button('파일로 저장…', self._export),
                        button('지우기', self._del), 'stretch', button('닫기', self.accept)))
        self.resize(720, 480)
        self.load()

    def _items(self):
        """[(키, 이름, bytes 또는 None(자료 파일에서 읽음))]"""
        if self.eid:
            return [(a['id'], a['name'] or f"사진 {a['id']}", None) for a in AT.list_for(self.con, self.eid)]
        return [(i, n, d) for i, (d, n) in enumerate(self.pending)]

    def _data(self, key, d):
        return d if d is not None else AT.data(self.con, key)

    def load(self):
        self.list.clear()
        total = 0
        for key, name, d in self._items():
            data = self._data(key, d) or b''
            total += len(data)
            pm = pixmap_of(data)
            it = QListWidgetItem(QIcon(pm.scaled(self.THUMB, self.THUMB, Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation)) if not pm.isNull() else QIcon(),
                                 name)
            it.setData(ID_ROLE, key)
            self.list.addItem(it)
        n = self.list.count()
        base = (f'사진 {n}장 · {total / 1048576:.1f}MB' if n else '아직 사진이 없어요. [사진 넣기…]로 영수증 사진을 붙여 두세요.')
        self.note.setText(base + ('' if self.eid else '  (새 내역 — 내역을 저장할 때 함께 저장됩니다)') +
                          '\n사진은 자료 파일 안에 들어가 휴대폰판에서도 보입니다. 긴 변 1600px 로 줄여서 넣습니다.')

    def _cur(self):
        it = self.list.currentItem()
        return it.data(ID_ROLE) if it else None

    def _add(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '사진 고르기', os.path.expanduser('~'), IMAGE_FILTER)
        bad = []
        for p in paths:
            try:
                data, name = prepare_image(p)
            except ValueError as ex:
                bad.append(str(ex))
                continue
            if self.eid:
                AT.add(self.con, self.eid, data, name)
            else:
                self.pending.append((data, name))
            self.changed = True
        self.load()
        if bad:
            error(self, '\n'.join(bad) + '\n\nHEIC 사진은 JPG 로 바꿔서 넣어 주세요.')

    def _view(self):
        key = self._cur()
        if key is None:
            return
        for k, name, d in self._items():
            if k == key:
                PhotoViewer(self, self._data(k, d), name).exec()

    def _export(self):
        key = self._cur()
        if key is None:
            return
        for k, name, d in self._items():
            if k == key:
                path, _ = QFileDialog.getSaveFileName(self, '사진 저장', os.path.join(os.path.expanduser('~'), name),
                                                      'JPEG (*.jpg)')
                if path:
                    with open(path, 'wb') as f:
                        f.write(self._data(k, d))

    def _del(self):
        key = self._cur()
        if key is None or not confirm(self, '고른 사진을 지울까요?'):
            return
        if self.eid:
            AT.delete(self.con, key)
        else:
            del self.pending[key]
        self.changed = True
        self.load()


def camera_icon(color=None, size=16):
    return QIcon(I.pixmap('camera', size, color or T.tone()['text2']))


# ── 자산 간 이체 ────────────────────────────────────────
class TransferDialog(QDialog):
    def __init__(self, parent, con, from_id=None):
        super().__init__(parent)
        self.con = con
        self.setWindowTitle('통장끼리 이체')
        self.src, self.dst = QComboBox(), QComboBox()
        for a in A.accounts(con, 'bank'):
            if not a['active']:
                continue
            label = f"{a['company']} {a['name']}".strip() + f"  (잔액 {fmt_money(A.account_balance(con, a['id']))})"
            self.src.addItem(label, a['id'])
            self.dst.addItem(label, a['id'])
        if from_id is not None and self.src.findData(from_id) >= 0:
            self.src.setCurrentIndex(self.src.findData(from_id))
        if self.dst.count() > 1 and self.dst.currentData() == self.src.currentData():
            self.dst.setCurrentIndex(1)
        self.date = DateEdit()
        self.amount = MoneyEdit()
        self.memo = QPlainTextEdit()
        self.memo.setMaximumHeight(54)
        f = QFormLayout()
        f.addRow('보내는 통장', self.src)
        f.addRow('받는 통장', self.dst)
        f.addRow('날짜', self.date)
        f.addRow('금액', self.amount)
        f.addRow('메모', self.memo)
        bb = ok_cancel(self, '이체 기록', self._ok)
        lay = QVBoxLayout(self)
        lay.addWidget(set_tone(QLabel('보내는 통장에 출금, 받는 통장에 입금이 짝으로 기록됩니다. 가계부(수입·지출)에는 넣지 않아\n'
                                      '이달 지출이 부풀지 않아요. 한쪽을 고치거나 지우면 짝도 같이 바뀝니다.'), 'note'))
        lay.addLayout(f)
        lay.addWidget(bb)
        self.resize(520, self.sizeHint().height())

    def _ok(self):
        if self.src.count() < 2:
            error(self, '사용중인 은행통장이 두 개 이상 있어야 합니다. 은행통장 탭에서 먼저 만드세요.')
            return
        try:
            amt = self.amount.value()
        except ValueError:
            error(self, '금액은 숫자로 입력하세요.')
            return
        try:
            A.transfer(self.con, self.src.currentData(), self.dst.currentData(), self.date.date_(), amt,
                       self.memo.toPlainText().strip())
        except ValueError as ex:
            error(self, str(ex))
            return
        self.accept()


# ── 저축 목표 ──────────────────────────────────────────
GOAL_FIELDS = [('name', '목표 이름', 'text*'), ('target', '목표 금액', 'money'), ('due', '목표 날짜', 'date'),
               ('memo', '메모', 'memo'), ('done', '상태', 'choice:모으는 중|이뤘어요')]


class GoalsTab(QWidget):
    """저축 목표: 목표별로 모은 돈 기록 → 진행 막대·남은 돈·한 달에 얼마씩"""
    def __init__(self, page):
        super().__init__()
        self.page, self.con = page, page.con
        self.list = make_table(['목표', '목표 금액', '모은 돈', '남은 돈', '진행', '목표 날짜', '한 달에', '메모'], stretch=7)
        self.list.itemSelectionChanged.connect(self.load_txs)
        self.list.doubleClicked.connect(lambda *_: self.edit())
        self.txs = make_table(['날짜', '금액', '메모'], stretch=2)
        self.date, self.amount, self.memo = DateEdit(), MoneyEdit(), QPlainTextEdit()
        self.memo.setMaximumHeight(54)
        self.tx_lbl = QLabel('위 목록에서 목표를 고르면 모은 기록이 나옵니다')
        self.bar = Bar(12)
        form = QGroupBox('모은 돈 기록')
        fl = QFormLayout(form)
        fl.addRow('날짜', self.date)
        fl.addRow('금액', self.amount)
        fl.addRow('메모', self.memo)
        fl.addRow(h(button('모았어요 (+)', lambda: self.add_tx(1)), button('꺼내 썼어요 (−)', lambda: self.add_tx(-1)),
                    button('기록 지우기', self.del_tx)))
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(h(QLabel('<b>저축 목표</b>'), set_tone(QLabel('여행 자금·비상금처럼 목표를 정하고 모을 때마다 기록하세요. '
                                                                   '통장 잔액과는 따로 셉니다.'), 'note'), 'stretch',
                       button('추가', self.add), button('수정', self.edit), button('삭제', self.delete)))
        tl.addWidget(self.list)
        txw = QWidget()
        xl = QVBoxLayout(txw)
        xl.setContentsMargins(0, 0, 0, 0)
        xl.addWidget(self.tx_lbl)
        xl.addWidget(self.bar)
        xl.addWidget(self.txs)
        bottom = QSplitter()
        bottom.addWidget(txw)
        bottom.addWidget(form)
        bottom.setStretchFactor(0, 3)
        sp = QSplitter(Qt.Orientation.Vertical)
        sp.addWidget(top)
        sp.addWidget(bottom)
        QVBoxLayout(self).addWidget(sp)

    def gid(self):
        return selected_id(self.list)

    def refresh(self):
        cur = self.gid()
        today = dt.date.today()
        rows = []
        tn = T.tone()
        for g in G.goals(self.con):
            st = G.goal_status(self.con, g, today)
            due = g['due'] or ''
            if g['due'] and not g['done'] and st['days_left'] is not None:
                due += f"  (D-{st['days_left']})" if st['days_left'] >= 0 else '  (지남)'
            name = g['name'] + ('  ✓' if g['done'] else '')
            rows.append([cell(name, data=g['id'], color=QColor(tn['faint']) if g['done'] else None),
                         money_cell(g['target']), money_cell(st['saved'], 'in'), money_cell(st['left']),
                         cell(f"{st['pct']}%" if g['target'] else '', CENTER), cell(due, CENTER),
                         money_cell(st['per_month'] if not g['done'] else 0), cell(g['memo'])])
        fill(self.list, rows)
        for r in range(self.list.rowCount()):
            if self.list.item(r, 0).data(ID_ROLE) == cur:
                self.list.selectRow(r)
        if self.list.rowCount() and not self.gid():
            self.list.selectRow(0)
        self.load_txs()

    def _goal(self):
        gid = self.gid()
        return self.con.execute('SELECT * FROM goal WHERE id=?', (gid,)).fetchone() if gid else None

    def load_txs(self):
        g = self._goal()
        if not g:
            fill(self.txs, [])
            self.tx_lbl.setText('위 목록에서 목표를 고르면 모은 기록이 나옵니다 — 없으면 [추가]로 만드세요')
            self.bar.set(0)
            return
        st = G.goal_status(self.con, g, dt.date.today())
        fill(self.txs, [[cell(t['date'], CENTER, data=t['id']), money_cell(t['amount'], 'in' if t['amount'] > 0 else 'out'),
                         cell(t['memo'])] for t in reversed(G.goal_txs(self.con, g['id']))])
        txt = f"<b>{html.escape(g['name'])}</b>  모은 돈 {fmt_money(st['saved'])}원"
        if g['target']:
            txt += f" / {fmt_money(g['target'])}원 ({st['pct']}%)"
            if st['left'] and st['per_month'] and not g['done']:
                txt += f" · 목표 날짜까지 한 달에 {fmt_money(st['per_month'])}원씩"
            elif not st['left']:
                txt += ' · 목표를 다 모았어요!'
        self.tx_lbl.setText(txt)
        self.bar.set(st['pct'], tn_ok() if st['pct'] >= 100 else None)

    def add(self):
        d = FormDialog(self, '새 저축 목표', GOAL_FIELDS, {})
        if d.exec():
            v = d.values()
            v['done'] = v['done'] == '이뤘어요'
            try:
                G.save_goal(self.con, v)
            except ValueError as ex:
                error(self, str(ex))
            self.page.changed()

    def edit(self):
        g = self._goal()
        if not g:
            return
        vals = dict(g)
        vals['done'] = 1 if g['done'] else 0
        d = FormDialog(self, '저축 목표 수정', GOAL_FIELDS, vals)
        if d.exec():
            v = d.values()
            v['done'] = v['done'] == '이뤘어요'
            G.save_goal(self.con, v, g['id'])
            self.page.changed()

    def delete(self):
        g = self._goal()
        if g and confirm(self, f"'{g['name']}' 목표와 모은 기록을 모두 지울까요?"):
            G.delete_goal(self.con, g['id'])
            self.page.changed()

    def add_tx(self, sign):
        g = self._goal()
        if not g:
            error(self, '먼저 위 목록에서 목표를 고르세요. 없으면 [추가]로 만드세요.')
            return
        try:
            amt = self.amount.value()
        except ValueError:
            error(self, '금액은 숫자로 입력하세요.')
            return
        if amt <= 0:
            error(self, '금액을 입력하세요.')
            return
        G.add_goal_tx(self.con, g['id'], self.date.date_(), sign * amt, self.memo.toPlainText().strip())
        self.amount.clear()
        self.memo.clear()
        self.page.changed()

    def del_tx(self):
        ids = selected_ids(self.txs)
        if ids and confirm(self, '고른 기록을 지울까요?'):
            G.delete_goal_tx(self.con, ids[0])
            self.page.changed()


def tn_ok():
    return T.tone()['ann']


# ── 빌려준 돈·빌린 돈 ──────────────────────────────────
DEBT_FIELDS = [('kind', '구분', 'choice:빌려준 돈 (받을 돈)|빌린 돈 (갚을 돈)'), ('person', '누구', 'text*'),
               ('amount', '금액', 'money'), ('date', '빌려준/빌린 날', 'date'), ('due', '갚기로 한 날', 'date'),
               ('memo', '메모', 'memo')]


class DebtsTab(QWidget):
    def __init__(self, page):
        super().__init__()
        self.page, self.con = page, page.con
        self.show_done = QCheckBox('끝난 것도 보기')
        self.show_done.toggled.connect(lambda *_: self.refresh())
        self.sum_lbl = QLabel()
        self.list = make_table(['구분', '누구', '금액', '받은/갚은 돈', '남은 돈', '날짜', '갚기로 한 날', '상태', '메모'], stretch=8)
        self.list.itemSelectionChanged.connect(self.load_pays)
        self.list.doubleClicked.connect(lambda *_: self.edit())
        self.pays = make_table(['날짜', '금액', '메모'], stretch=2)
        self.date, self.amount, self.memo = DateEdit(), MoneyEdit(), QPlainTextEdit()
        self.memo.setMaximumHeight(54)
        self.pay_lbl = QLabel()
        self.pay_btn = button('받았어요/갚았어요', self.add_pay)
        form = QGroupBox('받은 돈·갚은 돈 기록')
        fl = QFormLayout(form)
        fl.addRow('날짜', self.date)
        fl.addRow('금액', self.amount)
        fl.addRow('메모', self.memo)
        fl.addRow(h(self.pay_btn, button('남은 돈 모두', self._fill_left), button('기록 지우기', self.del_pay)))
        top = QWidget()
        tl = QVBoxLayout(top)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(h(QLabel('<b>빌려준 돈·빌린 돈</b>'), self.sum_lbl, 'stretch', self.show_done,
                       button('추가', self.add), button('수정', self.edit), button('삭제', self.delete)))
        tl.addWidget(self.list)
        pw = QWidget()
        pl = QVBoxLayout(pw)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(self.pay_lbl)
        pl.addWidget(self.pays)
        bottom = QSplitter()
        bottom.addWidget(pw)
        bottom.addWidget(form)
        bottom.setStretchFactor(0, 3)
        sp = QSplitter(Qt.Orientation.Vertical)
        sp.addWidget(top)
        sp.addWidget(bottom)
        QVBoxLayout(self).addWidget(sp)

    def did(self):
        return selected_id(self.list)

    def refresh(self):
        cur = self.did()
        today = dt.date.today().isoformat()
        tn = T.tone()
        lend, borrow = G.debt_totals(self.con)
        self.sum_lbl.setText(f"<span style='color:{tn['in']}'>받을 돈 {fmt_money(lend)}원</span> · "
                             f"<span style='color:{tn['out']}'>갚을 돈 {fmt_money(borrow)}원</span>"
                             "  <span style='font-size:small'>(자산 합계·부채 합계에 들어갑니다)</span>")
        rows = []
        for d in G.debts(self.con, include_done=self.show_done.isChecked()):
            paid, left = G.debt_paid(self.con, d['id']), G.debt_left(self.con, d)
            late = not d['done'] and d['due'] and d['due'] < today
            state = '끝남' if d['done'] else ('기한 지남' if late else '진행 중')
            kind = 'in' if d['kind'] == 'lend' else 'out'
            faint = QColor(tn['faint']) if d['done'] else None
            rows.append([cell(G.KINDS[d['kind']], CENTER, data=d['id'], color=faint or QColor(tn[kind])),
                         cell(d['person'], color=faint), money_cell(d['amount']), money_cell(paid),
                         money_cell(left, kind), cell(d['date'] or '', CENTER), cell(d['due'] or '', CENTER),
                         cell(state, CENTER, color=QColor(tn['out']) if late else faint, bold=bool(late)), cell(d['memo'])])
        fill(self.list, rows)
        for r in range(self.list.rowCount()):
            if self.list.item(r, 0).data(ID_ROLE) == cur:
                self.list.selectRow(r)
        if self.list.rowCount() and not self.did():
            self.list.selectRow(0)
        self.load_pays()

    def _debt(self):
        did = self.did()
        return self.con.execute('SELECT * FROM debt WHERE id=?', (did,)).fetchone() if did else None

    def load_pays(self):
        d = self._debt()
        if not d:
            fill(self.pays, [])
            self.pay_lbl.setText('위 목록에서 고르면 받은/갚은 기록이 나옵니다 — 없으면 [추가]로 만드세요')
            return
        fill(self.pays, [[cell(p['date'], CENTER, data=p['id']), money_cell(p['amount']), cell(p['memo'])]
                         for p in reversed(G.payments(self.con, d['id']))])
        verb = '받은' if d['kind'] == 'lend' else '갚은'
        self.pay_btn.setText('받았어요' if d['kind'] == 'lend' else '갚았어요')
        self.pay_lbl.setText(f"<b>{html.escape(d['person'])}</b> {G.KINDS[d['kind']]} {fmt_money(d['amount'])}원 · "
                             f"{verb} 돈 {fmt_money(G.debt_paid(self.con, d['id']))}원 · 남은 돈 "
                             f"<b>{fmt_money(G.debt_left(self.con, d))}원</b>")

    def _vals(self, d):
        v = d.values()
        v['kind'] = 'lend' if v['kind'].startswith('빌려준') else 'borrow'
        return v

    def add(self):
        d = FormDialog(self, '빌려준 돈·빌린 돈 추가', DEBT_FIELDS, {'date': dt.date.today().isoformat()})
        if d.exec():
            try:
                G.save_debt(self.con, self._vals(d))
            except ValueError as ex:
                error(self, str(ex))
            self.page.changed()

    def edit(self):
        x = self._debt()
        if not x:
            return
        vals = dict(x)
        vals['kind'] = 0 if x['kind'] == 'lend' else 1
        d = FormDialog(self, '빌려준 돈·빌린 돈 수정', DEBT_FIELDS, vals)
        if d.exec():
            v = self._vals(d)
            v['done'] = 1 if G.debt_paid(self.con, x['id']) >= (v.get('amount') or 0) > 0 else 0
            try:
                G.save_debt(self.con, v, x['id'])
            except ValueError as ex:
                error(self, str(ex))
            self.page.changed()

    def delete(self):
        x = self._debt()
        if x and confirm(self, f"{x['person']} — {G.KINDS[x['kind']]} 기록을 모두 지울까요?"):
            G.delete_debt(self.con, x['id'])
            self.page.changed()

    def _fill_left(self):
        x = self._debt()
        if x:
            self.amount.set_value(G.debt_left(self.con, x))

    def add_pay(self):
        x = self._debt()
        if not x:
            error(self, '먼저 위 목록에서 고르세요.')
            return
        try:
            amt = self.amount.value()
        except ValueError:
            error(self, '금액은 숫자로 입력하세요.')
            return
        if amt <= 0:
            error(self, '금액을 입력하세요.')
            return
        G.add_payment(self.con, x['id'], self.date.date_(), amt, self.memo.toPlainText().strip())
        self.amount.clear()
        self.memo.clear()
        self.page.changed()

    def del_pay(self):
        ids = selected_ids(self.pays)
        if ids and confirm(self, '고른 기록을 지울까요?'):
            G.delete_payment(self.con, ids[0])
            self.page.changed()


# ── 결산 보고서: 이달 리포트 ─────────────────────────────
def insight_html(con, lid, y, m, sd, today=None):
    """이달 소비 리포트 HTML (QTextBrowser 용)"""
    today = today or dt.date.today()
    i = INS.month_insight(con, lid, y, m, sd, today)
    tn = T.tone()
    out, inc, mute = tn['out'], tn['in'], tn['text2']
    f = fmt_money
    e = html.escape

    def pct_word(p, more='많이', less='적게'):
        if p is None:
            return ''
        if p == 0:
            return '똑같이'
        return f"<b style='color:{out if p > 0 else inc}'>{abs(p)}% {more if p > 0 else less}</b>"

    start, end = to_date(i['start']), to_date(i['end'])
    per = f'{start:%Y.%m.%d} ~ {end:%m.%d}'
    parts = [f"<h2 style='margin:0'>{y}년 {m}월 리포트</h2><p style='color:{mute};margin-top:2px'>{per}"
             + (f' · 월 시작일 {sd}일 기준' if sd != 1 else '') + '</p>']
    if not i['days']:
        parts.append('<p>아직 시작하지 않은 달입니다.</p>')
        return ''.join(parts)
    head = f"오늘까지 <b>{i['days']}일</b> 동안" if i['current'] else '한 달 동안'
    parts.append(f"<p style='font-size:large'>{head} <b style='color:{out}'>{f(i['expense'])}원</b> 썼어요"
                 f" <span style='color:{mute}'>(수입 {f(i['income'])}원)</span></p>")
    bl = []
    if i['prev_same']:
        same = '지난달 같은 기간' if i['current'] else '지난달'
        bl.append(f"{same}({f(i['prev_same'])}원)보다 {pct_word(i['change_pct'])} 썼어요")
    elif i['expense']:
        bl.append('지난달 같은 기간에는 쓴 돈이 없어요')
    bl.append(f"하루 평균 {f(i['daily_avg'])}원")
    if i['current'] and i['days'] < i['total_days']:
        bl.append(f"이대로 쓰면 이달 지출은 약 <b>{f(i['projected'])}원</b>"
                  + (f" (지난달 전체 {f(i['prev_full'])}원)" if i['prev_full'] else ''))
    if i['biggest']:
        b = i['biggest']
        bl.append(f"가장 큰 지출: {e(b['item'])} {f(b['amount'])}원 ({to_date(b['date']):%m.%d})")
    ns = f"무지출 {i['no_spend']}일"
    if i['current'] and i['streak'] >= 1:
        ns += f" · 오늘까지 {i['streak']}일 이어지는 중"
    bl.append(ns)
    parts.append('<ul>' + ''.join(f'<li>{x}</li>' for x in bl) + '</ul>')
    if i['top']:
        parts.append('<h3>많이 쓴 곳</h3><table cellpadding="4">')
        for n, t in enumerate(i['top'], 1):
            ch = (f"<span style='color:{mute}'>지난달({f(t['prev'])}원)보다</span> {pct_word(t['change_pct'])}" if t['prev']
                  else f"<span style='color:{mute}'>지난달엔 없음</span>")
            parts.append(f"<tr><td>{n}.</td><td><b>{e(t['name'])}</b></td><td align='right'>{f(t['amount'])}원</td>"
                         f"<td>{ch}</td></tr>")
        parts.append('</table>')
    from .money_ui import fixed_html             # 고정비 한눈에 (1.8.0)
    from ..services import money as M
    parts.append('<h3>고정 수입·지출</h3><p>' + fixed_html(con, lid, y, m, sd, today) + '</p>')
    perf = [p for p in M.card_perf(con, y, m) if p['target']]
    if perf:
        parts.append(f"<h3>카드 실적 <span style='font-size:small;color:{mute}'>(1일~말일, 모든 가계부)</span></h3><table cellpadding='3'>")
        for p in perf:
            done = p['spent'] >= p['target']
            parts.append(f"<tr><td>{e(p['label'])}</td><td align='right'>{f(p['spent'])}</td><td>/ {f(p['target'])}</td>"
                         + (f"<td style='color:{inc}'><b>채움 ✓</b></td>" if done else
                            f"<td>{_pct_text(p['pct'])} · {f(p['left'])}원 남음</td>") + '</tr>')
        parts.append('</table>')
    bp = i['budget']
    if bp['rows'] or bp.get('total'):
        parts.append(f"<h3>예산</h3><p>{'전체 예산 ' if bp.get('total') else ''}{f(bp['spent'])} / {f(bp['budget'])}원 ({_pct_text(bp['pct'])})"
                     + (f" · 남은 돈 {f(bp['left'])}원" if bp['left'] >= 0 else
                        f" · <b style='color:{out}'>{f(-bp['left'])}원 넘음</b>") + '</p><table cellpadding="3">')
        for r in bp['rows']:
            col = out if r['left'] < 0 else WARN_COLOR if (r['pct'] or 0) >= 80 else mute
            parts.append(f"<tr><td>{e(r['name'])}</td><td align='right'>{f(r['spent'])}</td><td>/ {f(r['budget'])}</td>"
                         f"<td style='color:{col}'><b>{_pct_text(r['pct'])}</b></td></tr>")
        parts.append('</table>')
    return ''.join(parts)


class InsightTab(QWidget):
    def __init__(self, page):
        super().__init__()
        self.page, self.con = page, page.con
        self.nav = MonthNav()
        self.nav.changed.connect(lambda *_: self.refresh())
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(False)
        lay = QVBoxLayout(self)
        lay.addWidget(h(self.nav, set_tone(QLabel('지난달 같은 기간과 비교한 이달 쓰임새'), 'note'), 'stretch'))
        lay.addWidget(self.view, 1)
        self._first = True

    def refresh(self):
        sd = settle_day(self.con)
        if self._first:                 # 처음엔 '오늘이 들어 있는 달' (결산일 기준)
            self._first = False
            y, m = INS.period_of(dt.date.today(), sd)
            if (y, m) != (self.nav.y, self.nav.m):
                self.nav.set(y, m)
                return
        self.view.setHtml(insight_html(self.con, self.page.app.lid, self.nav.y, self.nav.m, sd))


# ── 결산 보고서: 태그 ───────────────────────────────────
class TagTab(QWidget):
    """#태그별 합계 (품목·메모에 #여행 처럼 쓴 것). 두 번 누르면 그 태그 내역"""
    def __init__(self, page):
        super().__init__()
        self.page, self.con = page, page.con
        self.nav = MonthNav()
        self.nav.changed.connect(lambda *_: self.refresh())
        self.all_chk = QCheckBox('전체 기간')
        self.all_chk.setChecked(True)
        self.all_chk.toggled.connect(lambda *_: self.refresh())
        self.table = make_table(['태그', '건수', '수입', '지출'], stretch=0)
        self.table.cellDoubleClicked.connect(self._open)
        self.detail = make_table(['날짜', '내용', '수입', '지출', '카테고리', '메모'], stretch=5)
        self.detail_lbl = QLabel()
        sp = QSplitter()
        sp.addWidget(self.table)
        dw = QWidget()
        dl = QVBoxLayout(dw)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.addWidget(self.detail_lbl)
        dl.addWidget(self.detail, 1)
        sp.addWidget(dw)
        sp.setStretchFactor(1, 2)
        self.table.itemSelectionChanged.connect(self._sel)
        lay = QVBoxLayout(self)
        lay.addWidget(h(self.nav, self.all_chk, set_tone(QLabel('내용이나 메모에 #여행 #회사 처럼 쓰면 카테고리와 따로 모아 봅니다.'), 'note'),
                        'stretch'))
        lay.addWidget(sp, 1)

    def _range(self):
        if self.all_chk.isChecked():
            return None, None
        y, m = self.nav.y, self.nav.m
        return dt.date(y, m, 1), dt.date(y, m, month_end(y, m))

    def refresh(self):
        self.nav.setEnabled(not self.all_chk.isChecked())
        s, e = self._range()
        cur = self._tag()
        rows = L.tag_summary(self.con, self.page.app.lid, s, e)
        fill(self.table, [[cell('#' + r['tag'], data=r['tag']), cell(r['count'], CENTER), money_cell(r['income'], 'in'),
                           money_cell(r['expense'], 'out')] for r in rows])
        for i, r in enumerate(rows):
            if r['tag'] == cur:
                self.table.selectRow(i)
        if not rows:
            self.detail_lbl.setText('아직 태그를 쓴 내역이 없어요. 내용이나 메모에 #여행 처럼 써 보세요.')
            fill(self.detail, [])
        elif not self._tag():
            self.table.selectRow(0)
        self._sel()

    def _tag(self):
        return selected_id(self.table)

    def _sel(self):
        tag = self._tag()
        if not tag:
            return
        s, e = self._range()
        lid = self.page.app.lid
        rows = L.entries_with_tag(self.con, lid, tag, s, e)
        cmap = L.category_map(self.con, lid)
        fill(self.detail, [[cell(r['date'], CENTER), cell(r['item']), money_cell(r['income'], 'in'),
                            money_cell(r['expense'], 'out'), cell(L.code_label(cmap, r['code'])), cell(r['memo'])]
                           for r in rows])
        self.detail_lbl.setText(f"<b>#{html.escape(tag)}</b>  {len(rows)}건 · 지출 {fmt_money(sum(r['expense'] for r in rows))}원")

    def _open(self, *_):
        self._sel()
