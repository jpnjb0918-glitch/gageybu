"""일정관리: 월간 달력(음력·기념일·일정) + 일정 입력(반복·알림·색상) + 기념일 관리."""
import datetime as dt
import html

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDialog, QFormLayout, QGroupBox,
                             QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QRadioButton,
                             QSpinBox, QSplitter, QTableWidget, QVBoxLayout, QWidget)

from .. import theme as T
from ..lunar import lunar_label
from ..services import calendar_svc as C
from ..services import insights as INS
from ..services import money as M
from ..util import fmt_money, month_end
from .widgets import (CENTER, DateEdit, MonthNav, button, cell, confirm, error, export_csv, fill, h, info, make_table)

SUN = '#d0312d'
SAT = '#2f6fbe'


class AnniversaryDialog(QDialog):
    def __init__(self, parent, con):
        super().__init__(parent)
        self.con, self.editing = con, None
        self.setWindowTitle('기념일 관리')
        self.table = make_table(['기념일', '날짜', '연도', '양력/음력', '평일/휴일'], stretch=0)
        self.table.itemSelectionChanged.connect(self._sel)
        self.title = QLineEdit()
        self.every = QCheckBox('매년 반복')
        self.every.setChecked(True)
        self.year = QSpinBox()
        self.year.setRange(1900, 2100)
        self.year.setValue(dt.date.today().year)
        self.year.setEnabled(False)
        self.every.toggled.connect(lambda c: self.year.setEnabled(not c))
        self.month, self.day = QSpinBox(), QSpinBox()
        self.month.setRange(1, 12)
        self.day.setRange(1, 31)
        self.lunar = QCheckBox('음력')
        self.holiday = QCheckBox('휴일')
        f = QFormLayout()
        f.addRow('기념일 제목', self.title)
        f.addRow('날짜', h(self.every, self.year, '년', self.month, '월', self.day, '일'))
        f.addRow('', h(self.lunar, self.holiday, 'stretch'))
        f.addRow(QLabel('양력·음력의 말일은 31일로 지정하면 됩니다 (예: 설 전날 = 음력 12월 31일)'))
        f.addRow(h(button('추가', self.add), button('수정 저장', self.save), button('삭제', self.delete),
                   button('새로', self.new), 'stretch'))
        lay = QVBoxLayout(self)
        lay.addWidget(self.table, 1)
        lay.addLayout(f)
        self.resize(560, 620)
        self.load()

    def load(self):
        fill(self.table, [[cell(a['title'], data=a['id']), cell(f"{a['month']:02d}-{a['day']:02d}", CENTER),
                           cell(a['year'] or '매년', CENTER), cell('음력' if a['lunar'] else '양력', CENTER),
                           cell('휴일' if a['holiday'] else '평일', CENTER, color=QColor(T.tone()['sun']) if a['holiday'] else None)]
                          for a in C.anniversaries(self.con)])

    def _sel(self):
        rows = {i.row() for i in self.table.selectedIndexes()}
        if len(rows) != 1:
            return
        aid = self.table.item(rows.pop(), 0).data(Qt.ItemDataRole.UserRole)
        a = self.con.execute('SELECT * FROM anniversary WHERE id=?', (aid,)).fetchone()
        self.editing = aid
        self.title.setText(a['title'])
        self.every.setChecked(not a['year'])
        if a['year']:
            self.year.setValue(a['year'])
        self.month.setValue(a['month'])
        self.day.setValue(a['day'])
        self.lunar.setChecked(bool(a['lunar']))
        self.holiday.setChecked(bool(a['holiday']))

    def _v(self):
        if not self.title.text().strip():
            error(self, '기념일 제목을 입력하세요.')
            return None
        return {'title': self.title.text().strip(), 'month': self.month.value(), 'day': self.day.value(),
                'year': None if self.every.isChecked() else self.year.value(), 'lunar': self.lunar.isChecked(),
                'holiday': self.holiday.isChecked()}

    def add(self):
        v = self._v()
        if v:
            C.save_anniversary(self.con, v)
            self.load()

    def save(self):
        v = self._v()
        if v and self.editing:
            C.save_anniversary(self.con, v, self.editing)
            self.load()

    def delete(self):
        if self.editing and confirm(self, '선택한 기념일을 삭제할까요?'):
            C.delete_anniversary(self.con, self.editing)
            self.new()
            self.load()

    def new(self):
        self.editing = None
        self.title.clear()
        self.table.clearSelection()


class CalendarPage(QWidget):
    title = '달력'

    def __init__(self, app):
        super().__init__()
        self.app, self.con = app, app.con
        self.sel = dt.date.today()
        self.editing, self.bg, self.fg = None, None, None
        self.nav = MonthNav()
        self.nav.changed.connect(lambda *_: self.refresh())
        self.grid = QTableWidget(6, 7)
        self.grid.setHorizontalHeaderLabels(['일', '월', '화', '수', '목', '금', '토'])
        self.grid.verticalHeader().setVisible(False)
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.grid.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.grid.cellClicked.connect(self._clicked)
        for c, col in ((0, SUN), (6, SAT)):
            it = self.grid.horizontalHeaderItem(c)
            it.setForeground(QColor(col))

        self.day_lbl = QLabel()
        self.day_lbl.setObjectName('DayLabel')
        self.ann_lbl = QLabel()
        self.ann_lbl.setWordWrap(True)
        self.money_lbl = QLabel()                  # 그 날의 카드 결제·고정 수입·지출 (1.8.0)
        self.money_lbl.setWordWrap(True)
        self.items = QListWidget()
        self.items.currentRowChanged.connect(self._item_sel)
        self.text = QPlainTextEdit()
        self.text.setPlaceholderText('일정 내용')
        self.text.setMaximumHeight(90)
        self.remind = QSpinBox()
        self.remind.setRange(0, 60)
        self.remind.setSpecialValueText('안 함')
        self.remind.setSuffix('일 전')
        self.bg_btn = button('배경색', lambda: self._pick('bg'))
        self.fg_btn = button('글자색', lambda: self._pick('fg'))
        self.r_none = QRadioButton('반복 안 함')
        self.r_none.setChecked(True)
        self.r_every = QRadioButton('매')
        self.every_n = QSpinBox()
        self.every_n.setRange(1, 99)
        self.every_unit = QComboBox()
        self.every_unit.addItems(['일', '주', '월', '년'])
        self.r_days = QRadioButton('요일')
        self.days_set = QComboBox()
        self.days_set.addItems(list(C.WEEKDAY_SETS))
        self.r_nth = QRadioButton('')
        self.nth = QComboBox()
        self.nth.addItems(C.ORDINALS)
        self.nth_wd = QComboBox()
        self.nth_wd.addItems(C.WEEKDAY_NAMES)
        self.nth_n = QSpinBox()
        self.nth_n.setRange(1, 12)
        self.until = DateEdit()
        rep = QGroupBox('반복 일정 (새 일정 저장할 때만 적용)')
        rf = QFormLayout(rep)
        rf.addRow(self.r_none)
        rf.addRow(h(self.r_every, self.every_n, self.every_unit, '마다', 'stretch'))
        rf.addRow(h(self.r_days, self.days_set, 'stretch'))
        rf.addRow(h(self.r_nth, self.nth, self.nth_wd, ' 매', self.nth_n, '달마다', 'stretch'))
        rf.addRow('반복 종료일', self.until)
        box = QGroupBox('일정')
        bf = QFormLayout(box)
        bf.addRow(self.day_lbl)
        bf.addRow(self.ann_lbl)
        bf.addRow(self.money_lbl)
        bf.addRow(self.items)
        bf.addRow(self.text)
        bf.addRow('시작할 때 알려주기', self.remind)
        bf.addRow('색상', h(self.bg_btn, self.fg_btn, button('기본색', self._reset_colors), 'stretch'))
        bf.addRow(rep)
        self.save_btn = button('새 일정 저장', self.save)
        bf.addRow(h(self.save_btn, button('새로', self.new), button('삭제', self.delete), 'stretch'))
        self.del_from, self.del_to = DateEdit(), DateEdit()
        dl = QGroupBox('기간 일정 일괄 삭제 (복구 불가)')
        QFormLayout(dl).addRow(h(self.del_from, '~', self.del_to, button('일괄 삭제', self.delete_range)))
        bf.addRow(dl)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        self.ns_chk = QCheckBox('무지출 날 표시')
        self.ns_chk.setToolTip('지금 가계부에서 지출이 없었던 날(오늘까지)에 표시 — 무지출 챌린지')
        self.ns_chk.setChecked(str(T.settings().value('cal_no_spend', '1')) not in ('0', 'false'))
        self.ns_chk.toggled.connect(self._ns_toggled)
        self.money_chk = QCheckBox('결제일·고정')
        self.money_chk.setToolTip('카드 대금 결제일(결제할 금액)과 고정 수입·지출 날짜를 달력에 미리 표시')
        self.money_chk.setChecked(str(T.settings().value('cal_money', '1')) not in ('0', 'false'))
        self.money_chk.toggled.connect(self._money_toggled)
        self.ns_lbl = QLabel()
        ll.addWidget(h(self.nav, self.ns_lbl, 'stretch', self.money_chk, self.ns_chk, button('오늘', self.today),
                       button('기념일 관리', self.anniv), button('이달 일정 CSV', self.export)))
        ll.addWidget(self.grid, 1)
        sp = QSplitter()
        sp.addWidget(left)
        sp.addWidget(box)
        sp.setStretchFactor(0, 3)
        sp.setStretchFactor(1, 1)
        QVBoxLayout(self).addWidget(sp)

    def refresh(self):
        y, m = self.nav.y, self.nav.m
        weeks = C.month_grid(y, m)
        start, end = weeks[0][0], weeks[-1][-1]
        anns = C.anniversaries_between(self.con, start, end)
        scheds = C.schedules(self.con, start, end)
        today = dt.date.today()
        tn = T.tone()
        dark = bool((T.sns_colors() or {}).get('dark'))
        no_spend = set()
        self.ns_lbl.setText('')
        if self.ns_chk.isChecked() and dt.date(y, m, 1) <= today:
            lid = self.app.lid
            ms, me = dt.date(y, m, 1), min(dt.date(y, m, month_end(y, m)), today)
            no_spend = set(INS.no_spend_days(self.con, lid, ms, me))
            if no_spend:
                streak = INS.no_spend_streak(self.con, lid, today) if me == today else 0
                self.ns_lbl.setText(f"<span style='color:{tn['ann']}'>무지출 {len(no_spend)}일"
                                    + (f' · 오늘까지 {streak}일째' if streak >= 2 else '') + '</span>')
        self.money = M.money_events(self.con, self.app.lid, start, end, today) if self.money_chk.isChecked() else {}
        for c, key in ((0, 'sun'), (6, 'sat')):
            self.grid.horizontalHeaderItem(c).setForeground(QColor(tn[key]))
        for w, week in enumerate(weeks):
            for c, d in enumerate(week):
                hol = any(x[1] for x in anns.get(d, []))
                color = tn['sun'] if (c == 0 or hol) else tn['sat'] if c == 6 else tn['text']
                if d.month != m:
                    color = tn['faint']
                parts = [f'<span style="color:{color};font-weight:bold">{d.day}</span> '
                         f'<span style="color:{tn["lunar"]};font-size:8pt">({lunar_label(d)})</span>']
                if d.isoformat() in no_spend and d.month == m:
                    parts.append(f'<span style="color:{tn["ann"]};font-size:8pt;font-weight:bold">● 무지출</span>')
                for title, holi in anns.get(d, []):
                    parts.append(f'<span style="color:{tn["sun"] if holi else tn["ann"]};font-size:9pt">{html.escape(title)}</span>')
                for ev in self.money.get(d.isoformat(), []):
                    parts.append(_money_html(ev, tn, short=True))
                for s in scheds.get(d.isoformat(), []):
                    fg = s['fg'] or ('#333' if s['bg'] else tn['text2'])     # 배경색을 고른 일정은 진한 글자
                    bg = s['bg']
                    if bg and dark:          # 어두운 테마: 밝은 일정 바탕을 어둡게, 글자는 그 색 그대로 (화면에서 튀지 않게)
                        fg, bg = s['fg'] or T.mix(bg, '#FFFFFF', 0.25), T.mix('#000000', bg, 0.3)
                    style = f"font-size:9pt;color:{fg};" + (f"background:{bg};" if bg else '')
                    txt = html.escape(s['text'].splitlines()[0][:24] if s['text'] else '')
                    parts.append(f'<span style="{style}">· {txt}</span>')
                lab = QLabel('<br>'.join(parts))
                lab.setTextFormat(Qt.TextFormat.RichText)
                lab.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
                lab.setWordWrap(True)
                lab.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                bg = tn['today_bg'] if d == today else tn['sel_bg'] if d == self.sel else 'transparent'
                lab.setStyleSheet(f'background:{bg};padding:2px')
                self.grid.setCellWidget(w, c, lab)
                self.grid.setItem(w, c, cell(''))
                self.grid.item(w, c).setData(Qt.ItemDataRole.UserRole, d.isoformat())
        self.show_day()

    def _ns_toggled(self, on):
        T.set_pref('cal_no_spend', '1' if on else '0')
        self.refresh()

    def _money_toggled(self, on):
        T.set_pref('cal_money', '1' if on else '0')
        self.refresh()

    def show_date(self, d):
        """그 날을 골라 보여 줌 (가계부 게시물의 [달력에서 보기])"""
        self.sel = d
        if (d.year, d.month) != (self.nav.y, self.nav.m):
            self.nav.set(d.year, d.month)
        else:
            self.refresh()

    def _clicked(self, r, c):
        self.sel = dt.date.fromisoformat(self.grid.item(r, c).data(Qt.ItemDataRole.UserRole))
        if self.sel.month != self.nav.m:
            self.nav.set(self.sel.year, self.sel.month)
        else:
            self.refresh()

    def today(self):
        self.sel = dt.date.today()
        self.nav.this_month()

    def show_day(self):
        d = self.sel
        self.day_lbl.setText(f"{d:%Y-%m-%d} ({'월화수목금토일'[d.weekday()]})  {lunar_label(d)}")
        anns = C.anniversaries_between(self.con, d, d).get(d, [])
        self.ann_lbl.setText(', '.join(t + (' (휴일)' if hh else '') for t, hh in anns))
        evs = getattr(self, 'money', {}).get(d.isoformat(), [])
        self.money_lbl.setText('<br>'.join(_money_html(ev, T.tone()) for ev in evs))
        self.money_lbl.setVisible(bool(evs))
        self.items.clear()
        for s in C.schedules(self.con, d, d).get(d.isoformat(), []):
            it = QListWidgetItem(s['text'] + (f"   [알림 {s['remind_days']}일 전]" if s['remind_days'] else ''))
            it.setData(Qt.ItemDataRole.UserRole, s['id'])
            self.items.addItem(it)
        if not self.until.date_() or self.until.date_() < d:
            self.until.set_date(d)
        self.new()

    def _item_sel(self, row):
        if row < 0:
            return
        sid = self.items.item(row).data(Qt.ItemDataRole.UserRole)
        s = self.con.execute('SELECT * FROM schedule WHERE id=?', (sid,)).fetchone()
        self.editing, self.bg, self.fg = sid, s['bg'], s['fg']
        self.text.setPlainText(s['text'])
        self.remind.setValue(s['remind_days'])
        self.save_btn.setText('수정 저장')

    def reset_state(self):
        self.new()

    def new(self):
        self.editing, self.bg, self.fg = None, None, None
        self.text.clear()
        self.remind.setValue(0)
        self.r_none.setChecked(True)
        self.save_btn.setText('새 일정 저장')

    def _pick(self, which):
        c = QColorDialog.getColor(QColor(getattr(self, which) or '#ffffff'), self)
        if c.isValid():
            setattr(self, which, c.name())

    def _reset_colors(self):
        self.bg = self.fg = None

    def _repeat(self):
        if self.r_every.isChecked():
            return {'type': 'every', 'n': self.every_n.value(), 'unit': self.every_unit.currentText()}
        if self.r_days.isChecked():
            return {'type': 'weekdays', 'set': self.days_set.currentText()}
        if self.r_nth.isChecked():
            return {'type': 'nth', 'nth': self.nth.currentIndex(), 'weekday': self.nth_wd.currentIndex(),
                    'n': self.nth_n.value()}
        return {'type': 'none'}

    def save(self):
        txt = self.text.toPlainText().strip()
        if not txt:
            error(self, '일정 내용을 입력하세요.')
            return
        if self.editing:
            C.update_schedule(self.con, self.editing, txt, self.remind.value(), self.bg, self.fg)
        else:
            rep = self._repeat()
            if rep['type'] != 'none' and self.until.date_() <= self.sel:
                error(self, '반복 종료일을 선택한 날짜보다 뒤로 지정하세요.')
                return
            n = C.add_schedule(self.con, self.sel, txt, self.remind.value(), self.bg, self.fg, rep, self.until.date_())
            if n > 1:
                info(self, f'반복 일정 {n}건을 저장했습니다.')
        self.refresh()

    def delete(self):
        if not self.editing:
            return
        s = self.con.execute('SELECT * FROM schedule WHERE id=?', (self.editing,)).fetchone()
        if s['group_id']:
            n = self.con.execute('SELECT COUNT(*) FROM schedule WHERE group_id=?', (s['group_id'],)).fetchone()[0]
            if confirm(self, f'반복으로 함께 만든 일정 {n}건을 모두 지울까요?\n(아니오 = 이 날짜만)'):
                self.con.execute('DELETE FROM schedule WHERE group_id=?', (s['group_id'],))
                self.con.commit()
                self.refresh()
                return
        if confirm(self, '이 일정을 삭제할까요?'):
            C.delete_schedule(self.con, self.editing)
            self.refresh()

    def delete_range(self):
        a, b = self.del_from.date_(), self.del_to.date_()
        if a > b:
            error(self, '시작일이 종료일보다 늦습니다.')
            return
        if confirm(self, f'{a} ~ {b} 의 일정을 모두 삭제할까요? 복구할 수 없습니다.'):
            n = C.delete_schedule_range(self.con, a, b)
            info(self, f'{n}건 삭제했습니다.')
            self.refresh()

    def anniv(self):
        AnniversaryDialog(self, self.con).exec()
        self.refresh()

    def export(self):
        y, m = self.nav.y, self.nav.m
        start, end = dt.date(y, m, 1), C.month_grid(y, m)[-1][-1]
        t = make_table(['날짜', '음력', '기념일', '일정'])
        anns = C.anniversaries_between(self.con, start, end)
        sch = C.schedules(self.con, start, end)
        rows = []
        d = start
        while d.month == m:
            rows.append([d.isoformat(), lunar_label(d), ', '.join(a for a, _ in anns.get(d, [])),
                         ' / '.join(s['text'] for s in sch.get(d.isoformat(), []))])
            d += dt.timedelta(days=1)
        fill(t, rows)
        export_csv(self, t, f'일정_{y}-{m:02d}')


def _money_html(ev, tn, short=False):
    """달력 칸·그 날 안내의 돈 일정 한 줄: 💳 카드 결제 · 🔁 고정 수입·지출 (이미 결제했거나 넣은 것은 흐리게 ✓)"""
    icon = '💳' if ev['kind'] == 'card' else '🔁'
    col = tn['faint'] if ev['done'] else (tn['in'] if ev['sign'] == 'in' else tn['out'])
    amt = ('+' if ev['sign'] == 'in' else '') + fmt_money(ev['amount'])
    label = ev['label'] if not short or len(ev['label']) <= 10 else ev['label'][:9] + '…'
    return (f'<span style="color:{col};font-size:{8 if short else 10}pt">{icon} {html.escape(label)} {amt}'
            + (' ✓' if ev['done'] else '') + '</span>')
