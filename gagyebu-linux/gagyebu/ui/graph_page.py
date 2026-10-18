"""그래프 분석: 연간(월별) 또는 월간(일별) 계정별 금액 변화."""
import datetime as dt

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QCheckBox, QComboBox, QSpinBox, QVBoxLayout, QWidget

from .. import db
from ..services import ledger as L
from ..services import reports as RP
from ..util import fmt_money
from .widgets import button, h

PALETTE = ['#2f6fbe', '#d9534f', '#3a9a5b', '#e0912f', '#8a5cc2', '#1aa3a3', '#c2577f', '#7a7a2a', '#5b6b7a',
           '#b5651d', '#4a8f2a', '#a33a3a']


class Chart(QWidget):
    def __init__(self):
        super().__init__()
        self.labels, self.series, self.kind, self.title = [], {}, 'line', ''
        self.setMinimumHeight(360)

    def set_data(self, labels, series, kind, title):
        self.labels, self.series, self.kind, self.title = labels, series, kind, title
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#ffffff'))
        W, H = self.width(), self.height()
        f = QFont(self.font())
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 6, W, 22), Qt.AlignmentFlag.AlignCenter, self.title)
        p.setFont(self.font())
        if not self.series:
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '표시할 자료가 없습니다')
            return
        legend_w = min(220, max(120, W // 5))
        L_, T, R_, B = 80, 40, W - legend_w - 10, H - 40
        vals = [v for s in self.series.values() for v in s]
        vmax, vmin = max(vals + [0]), min(vals + [0])
        if vmax == vmin:
            vmax = vmin + 1
        unit, uname = (10000, '만원') if max(abs(vmax), abs(vmin)) >= 1_000_000 else (1, '원')
        step = _nice((vmax - vmin) / 5)
        top = step * (int(vmax / step) + (1 if vmax % step else 0))
        bot = -step * (int(-vmin / step) + (1 if (-vmin) % step else 0)) if vmin < 0 else 0
        y_of = lambda v: B - (v - bot) / (top - bot) * (B - T)
        p.setPen(QPen(QColor('#e3e3e3')))
        v = bot
        while v <= top + 1e-9:
            y = y_of(v)
            p.drawLine(QPointF(L_, y), QPointF(R_, y))
            p.setPen(QPen(QColor('#555')))
            p.drawText(QRectF(0, y - 9, L_ - 6, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       fmt_money(v / unit))
            p.setPen(QPen(QColor('#e3e3e3')))
            v += step
        p.setPen(QPen(QColor('#777')))
        p.drawText(QRectF(0, T - 26, L_ - 6, 16), Qt.AlignmentFlag.AlignRight, f'단위: {uname}')
        p.drawLine(QPointF(L_, y_of(0)), QPointF(R_, y_of(0)))
        n = len(self.labels)
        slot = (R_ - L_) / max(1, n)
        x_of = lambda i: L_ + slot * (i + 0.5)
        every = max(1, n // 16)
        for i, lab in enumerate(self.labels):
            if i % every == 0:
                p.drawText(QRectF(x_of(i) - slot, B + 4, slot * 2, 18), Qt.AlignmentFlag.AlignHCenter, lab)
        k = len(self.series)
        for si, (name, data) in enumerate(self.series.items()):
            col = QColor(PALETTE[si % len(PALETTE)])
            if self.kind == 'bar':
                bw = slot * 0.8 / k
                for i, v in enumerate(data):
                    x = L_ + slot * i + slot * 0.1 + bw * si
                    y0, y1 = y_of(0), y_of(v)
                    p.fillRect(QRectF(x, min(y0, y1), max(1, bw - 1), abs(y1 - y0)), col)
            else:
                p.setPen(QPen(col, 2))
                pts = [QPointF(x_of(i), y_of(v)) for i, v in enumerate(data)]
                for a, b in zip(pts, pts[1:]):
                    p.drawLine(a, b)
                p.setBrush(col)
                for pt in pts:
                    p.drawEllipse(pt, 2.5, 2.5)
                p.setBrush(Qt.BrushStyle.NoBrush)
        y = T
        for si, (name, data) in enumerate(self.series.items()):
            col = QColor(PALETTE[si % len(PALETTE)])
            p.fillRect(QRectF(R_ + 14, y + 4, 12, 10), col)
            p.setPen(QPen(QColor('#333')))
            p.drawText(QRectF(R_ + 30, y, legend_w - 30, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       f'{name}  {fmt_money(sum(data))}')
            y += 20


def _nice(x):
    import math
    if x <= 0:
        return 1
    e = 10 ** math.floor(math.log10(x))
    for m in (1, 2, 2.5, 5, 10):
        if x <= m * e:
            return m * e
    return 10 * e


class GraphPage(QWidget):
    title = '그래프 분석'

    def __init__(self, app):
        super().__init__()
        self.app, self.con = app, app.con
        t = dt.date.today()
        self.year = QSpinBox()
        self.year.setRange(1990, 2100)
        self.year.setValue(t.year)
        self.year.setSuffix('년')
        self.group = QComboBox()
        self.cat = QComboBox()
        self.monthly = QCheckBox('월단위')
        self.month = QSpinBox()
        self.month.setRange(1, 12)
        self.month.setValue(t.month)
        self.month.setSuffix('월')
        self.kind = QComboBox()
        self.kind.addItems(['꺾은선 그래프', '막대 그래프'])
        self.chart = Chart()
        for w in (self.year, self.month):
            w.valueChanged.connect(lambda *_: self.draw())
        for w in (self.cat, self.kind):
            w.currentIndexChanged.connect(lambda *_: self.draw())
        self.group.currentIndexChanged.connect(self._group_changed)
        self.monthly.toggled.connect(lambda *_: self.draw())
        lay = QVBoxLayout(self)
        lay.addWidget(h('연도', self.year, '  대분류', self.group, '  소분류', self.cat, '  ', self.monthly, self.month,
                        '  ', self.kind, 'stretch', button('이미지로 저장', self.save_png)))
        lay.addWidget(self.chart, 1)

    def refresh(self):
        lid = self.app.lid
        cur = self.group.currentData()
        self.group.blockSignals(True)
        self.group.clear()
        self.group.addItem('전체 계정 (대분류별)', None)
        for g in L.groups(self.con, lid):
            self.group.addItem(f"{g['code']} {g['name']}", g['code'])
        self.group.setCurrentIndex(max(0, self.group.findData(cur)))
        self.group.blockSignals(False)
        self._group_changed()

    def _group_changed(self, *_):
        g = self.group.currentData()
        self.cat.blockSignals(True)
        self.cat.clear()
        self.cat.addItem('모두 보여주기', None)
        if g is not None:
            for c in L.categories(self.con, self.app.lid, g):
                self.cat.addItem(f"{c['code']} {c['name']}", c['code'])
        self.cat.setEnabled(g is not None)
        self.cat.blockSignals(False)
        self.draw()

    def draw(self):
        self.month.setEnabled(self.monthly.isChecked())
        y = self.year.value()
        m = self.month.value() if self.monthly.isChecked() else None
        labels, series = RP.graph_series(self.con, self.app.lid, y, group=self.group.currentData(),
                                         code=self.cat.currentData(), month=m,
                                         settle_day=int(db.get_meta(self.con, 'settle_day', 1) or 1))
        what = self.cat.currentText() if self.cat.currentData() else self.group.currentText()
        title = f"{y}년{f' {m}월' if m else ''} {what} 분석"
        self.chart.set_data(labels, series, 'bar' if self.kind.currentIndex() == 1 else 'line', title)

    def save_png(self):
        from PyQt6.QtWidgets import QFileDialog
        import os
        path, _ = QFileDialog.getSaveFileName(self, '그래프 저장', os.path.join(os.path.expanduser('~'), '그래프.png'),
                                              'PNG (*.png)')
        if path:
            self.chart.grab().save(path, 'PNG')
