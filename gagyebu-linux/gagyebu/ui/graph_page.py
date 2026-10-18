"""그래프 분석: 연간(월별) 또는 월간(일별) 계정별 금액 변화. 그래프 종류는 골라 바꿀 수 있음."""
import datetime as dt
import math
from itertools import accumulate

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import QCheckBox, QComboBox, QSpinBox, QVBoxLayout, QWidget

from .. import db
from .. import theme as TH
from ..services import ledger as L
from ..services import reports as RP
from ..util import fmt_money
from .widgets import button, h

PALETTE = ['#2f6fbe', '#d9534f', '#3a9a5b', '#e0912f', '#8a5cc2', '#1aa3a3', '#c2577f', '#7a7a2a', '#5b6b7a',
           '#b5651d', '#4a8f2a', '#a33a3a']
# 그래프 종류 — 열쇠는 안드로이드판 pages-report.js 의 KINDS 와 같음. 고른 것은 이 컴퓨터에 기억 (graph_kind)
KINDS = [('line', '꺾은선 그래프'), ('bar', '막대 그래프'), ('stack', '누적 막대 그래프'), ('area', '영역 그래프'),
         ('cum', '누계 꺾은선 (차례로 더한 금액)'), ('hbar', '가로 막대 (항목별 합계)'), ('pie', '원 그래프 (비율)'),
         ('donut', '도넛 그래프 (비율)')]
KIND_KEYS = [k for k, _ in KINDS]


def _nice(x):
    if x <= 0:
        return 1
    e = 10 ** math.floor(math.log10(x))
    for m in (1, 2, 2.5, 5, 10):
        if x <= m * e:
            return m * e
    return 10 * e


def _scale(vals):
    """축 범위 (lo, hi, step) — 안드로이드판 scale() 과 같은 규칙.
    조금만 음수(환불 등)일 때 눈금 한 칸을 통째로 비우지 않도록 아래쪽은 값보다 조금만 더 내림."""
    vmax, vmin = max(list(vals) + [0]), min(list(vals) + [0])
    if vmax == vmin:
        vmax = vmin + 1
    step = _nice((vmax - vmin) / 5)
    lo = math.floor(vmin / step + 1e-9) * step
    if vmin < 0 and lo < vmin - step * 0.5:
        lo = vmin - (vmax - vmin) * 0.05
    hi = math.ceil(vmax / step - 1e-9) * step
    if vmax > 0 and hi > vmax + step * 0.5:
        hi = vmax + (vmax - vmin) * 0.05
    return lo, hi, step


def _ticks(lo, hi, step):
    k = math.ceil(lo / step - 1e-9)
    out = []
    while k * step <= hi + step * 1e-6:
        out.append(k * step)
        k += 1
    return out


def _unit(lo, hi):
    return (10000, '만원') if max(abs(lo), abs(hi)) >= 1_000_000 else (1, '원')


class Chart(QWidget):
    def __init__(self):
        super().__init__()
        self.labels, self.series, self.kind, self.title = [], {}, 'line', ''
        self.setMinimumHeight(360)

    def set_data(self, labels, series, kind, title):
        self.labels, self.series, self.kind, self.title = labels, series, kind, title
        self.update()

    # ── 공통 ──
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        tn = TH.tone()
        p.fillRect(self.rect(), QColor(tn['chart_bg']))
        p.setPen(QPen(QColor(tn['title'])))
        W, H = self.width(), self.height()
        f = QFont(self.font())
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 6, W, 22), Qt.AlignmentFlag.AlignCenter, self.title)
        p.setFont(self.font())
        if not self.series:
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '표시할 자료가 없습니다')
            return
        legend_w = min(240, max(130, W // 5))
        box = (80, 40, W - legend_w - 10, H - 40)          # 왼, 위, 오른, 아래
        cols = {name: QColor(PALETTE[i % len(PALETTE)]) for i, name in enumerate(self.series)}
        if self.kind in ('pie', 'donut'):
            legend = self._pie(p, tn, box, cols)
        elif self.kind == 'hbar':
            legend = self._hbar(p, tn, box, cols)
        else:
            legend = self._xy(p, tn, box, cols)
        y = box[1]
        for name, text in legend:
            p.fillRect(QRectF(box[2] + 14, y + 4, 12, 10), cols[name])
            p.setPen(QPen(QColor(tn['legend'])))
            p.drawText(QRectF(box[2] + 30, y, legend_w - 30, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       p.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle, legend_w - 32))
            y += 20

    def _empty(self, p, tn, msg):
        p.setPen(QPen(QColor(tn['axis'])))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, msg)

    # ── 꺾은선·누계·영역·막대·누적 막대 ──
    def _xy(self, p, tn, box, cols):
        L_, T, R_, B = box
        kind, n = self.kind, len(self.labels)
        data = {k: list(accumulate(v)) for k, v in self.series.items()} if kind == 'cum' else self.series
        if kind == 'stack':
            vals = [sum(max(0, v[i]) for v in data.values()) for i in range(n)] + \
                   [sum(min(0, v[i]) for v in data.values()) for i in range(n)]
        else:
            vals = [v for s in data.values() for v in s]
        lo, hi, step = _scale(vals)
        unit, uname = _unit(lo, hi)
        y_of = lambda v: B - (v - lo) / (hi - lo) * (B - T)
        for v in _ticks(lo, hi, step):
            y = y_of(v)
            p.setPen(QPen(QColor(tn['grid'])))
            p.drawLine(QPointF(L_, y), QPointF(R_, y))
            p.setPen(QPen(QColor(tn['axis'])))
            p.drawText(QRectF(0, y - 9, L_ - 6, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       fmt_money(v / unit))
        p.setPen(QPen(QColor(tn['axis2'])))
        p.drawText(QRectF(0, T - 26, L_ - 6, 16), Qt.AlignmentFlag.AlignRight, f'단위: {uname}')
        slot = (R_ - L_) / max(1, n)
        x_of = lambda i: L_ + slot * (i + 0.5)
        every = max(1, n // 16)
        p.setPen(QPen(QColor(tn['axis'])))
        for i, lab in enumerate(self.labels):
            if i % every == 0:
                p.drawText(QRectF(x_of(i) - slot, B + 4, slot * 2, 18), Qt.AlignmentFlag.AlignHCenter, lab)
        k = len(data)
        if kind == 'bar':
            bw = slot * 0.8 / max(1, k)
            for si, (name, vs) in enumerate(data.items()):
                for i, v in enumerate(vs):
                    if v:
                        x = L_ + slot * i + slot * 0.1 + bw * si
                        y0, y1 = y_of(0), y_of(v)
                        p.fillRect(QRectF(x, min(y0, y1), max(1, bw - 1), max(1, abs(y1 - y0))), cols[name])
        elif kind == 'stack':
            up, dn = [0] * n, [0] * n
            sep = QPen(QColor(tn['chart_bg']), 1)
            for name, vs in data.items():
                for i, v in enumerate(vs):
                    if not v:
                        continue
                    base = up[i] if v > 0 else dn[i]
                    top = base + v
                    if v > 0:
                        up[i] = top
                    else:
                        dn[i] = top
                    y0, y1 = y_of(base), y_of(top)
                    r = QRectF(L_ + slot * i + slot * 0.15, min(y0, y1), max(1, slot * 0.7), max(1, abs(y1 - y0)))
                    p.fillRect(r, cols[name])
                    p.setPen(sep)
                    p.drawLine(r.topLeft(), r.topRight())
        else:
            if kind == 'area':
                p.setPen(Qt.PenStyle.NoPen)
                for name, vs in data.items():
                    c = QColor(cols[name])
                    c.setAlpha(46)
                    p.setBrush(c)
                    poly = [QPointF(x_of(0), y_of(0))] + [QPointF(x_of(i), y_of(v)) for i, v in enumerate(vs)] + \
                           [QPointF(x_of(n - 1), y_of(0))]
                    p.drawPolygon(QPolygonF(poly))
                p.setBrush(Qt.BrushStyle.NoBrush)
            for name, vs in data.items():
                p.setPen(QPen(cols[name], 2))
                pts = [QPointF(x_of(i), y_of(v)) for i, v in enumerate(vs)]
                for a, b in zip(pts, pts[1:]):
                    p.drawLine(a, b)
                if n <= 31:
                    p.setBrush(cols[name])
                    for pt in pts:
                        p.drawEllipse(pt, 2.5, 2.5)
                    p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(tn['axis2'])))
        p.drawLine(QPointF(L_, y_of(0)), QPointF(R_, y_of(0)))
        if kind == 'cum':
            return [(name, f'{name}  {fmt_money(vs[-1] if vs else 0)}') for name, vs in data.items()]
        return [(name, f'{name}  {fmt_money(sum(vs))}') for name, vs in data.items()]

    # ── 가로 막대: 항목별 합계, 큰 것부터 ──
    def _hbar(self, p, tn, box, cols):
        _, T, R_, B = box
        items = sorted(((name, sum(vs)) for name, vs in self.series.items() if any(vs)), key=lambda x: -x[1])
        if not items:
            self._empty(p, tn, '표시할 자료가 없습니다')
            return []
        name_w = 150
        L_, R2 = 10 + name_w, R_ - 80
        lo, hi, step = _scale([t for _, t in items])
        unit, uname = _unit(lo, hi)
        x_of = lambda v: L_ + (v - lo) / (hi - lo) * (R2 - L_)
        row = min(56, (B - T - 40) / len(items))
        for v in _ticks(lo, hi, step):
            x = x_of(v)
            p.setPen(QPen(QColor(tn['grid'] if v else tn['axis2'])))
            p.drawLine(QPointF(x, T), QPointF(x, T + row * len(items)))
            p.setPen(QPen(QColor(tn['axis'])))
            p.drawText(QRectF(x - 50, T + row * len(items) + 4, 100, 18), Qt.AlignmentFlag.AlignHCenter, fmt_money(v / unit))
        p.setPen(QPen(QColor(tn['axis2'])))
        p.drawText(QRectF(R2 - 100, T + row * len(items) + 22, 100, 16), Qt.AlignmentFlag.AlignRight, f'단위: {uname}')
        fm = p.fontMetrics()
        for i, (name, t) in enumerate(items):
            yy = T + row * i
            p.setPen(QPen(QColor(tn['legend'])))
            p.drawText(QRectF(10, yy, name_w - 8, row), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(name, Qt.TextElideMode.ElideRight, name_w - 8))
            a, b = x_of(min(0, t)), x_of(max(0, t))
            p.fillRect(QRectF(a, yy + row * 0.2, max(1, b - a), row * 0.6), cols[name])
            p.setPen(QPen(QColor(tn['axis'])))
            p.drawText(QRectF(b + 5, yy, 120, row), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, fmt_money(t))
        return [(name, f'{name}  {fmt_money(t)}') for name, t in items]

    # ── 원·도넛: 합계가 0보다 큰 항목의 비율 ──
    def _pie(self, p, tn, box, cols):
        _, T, R_, B = box
        totals = [(name, sum(vs)) for name, vs in self.series.items() if any(vs)]
        items = [(name, t) for name, t in totals if t > 0]
        skipped = len(totals) - len(items)
        if not items:
            self._empty(p, tn, '합계가 0보다 큰 항목이 없어 비율로 그릴 수 없습니다')
            return []
        tot = sum(t for _, t in items)
        cx, cy = (10 + R_) / 2, (T + B) / 2 - (8 if skipped else 0)
        r = max(30, min(R_ - 10, B - T - (20 if skipped else 0)) / 2 - 6)
        rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
        donut = self.kind == 'donut'
        r0 = r * 0.56 if donut else 0
        a = 90.0                                            # 12시 방향부터 시계 방향
        sep = QPen(QColor(tn['chart_bg']), 1.5)
        marks = []
        for name, t in items:
            span = t / tot * 360
            p.setPen(sep if len(items) > 1 else Qt.PenStyle.NoPen)
            p.setBrush(cols[name])
            p.drawPie(rect, int(round(a * 16)), -int(round(span * 16)))
            mid = math.radians(a - span / 2)
            if t / tot >= 0.05:
                rr = (r + r0) / 2 if donut else r * 0.62
                marks.append((cx + rr * math.cos(mid), cy - rr * math.sin(mid), f'{t / tot * 100:.0f}%'))
            a -= span
        p.setBrush(Qt.BrushStyle.NoBrush)
        if donut:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(tn['chart_bg']))
            p.drawEllipse(QPointF(cx, cy), r0, r0)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(tn['axis'])))
            p.drawText(QRectF(cx - r0, cy - 26, 2 * r0, 18), Qt.AlignmentFlag.AlignCenter, '합계')
            f = QFont(self.font())
            f.setBold(True)
            if f.pointSizeF() > 0:                           # 글꼴 크기가 pt 또는 px 로 정해져 있음 (테마)
                f.setPointSizeF(f.pointSizeF() * 1.25)
            elif f.pixelSize() > 0:
                f.setPixelSize(round(f.pixelSize() * 1.25))
            p.setFont(f)
            p.setPen(QPen(QColor(tn['title'])))
            p.drawText(QRectF(cx - r0, cy - 6, 2 * r0, 26), Qt.AlignmentFlag.AlignCenter, f'{fmt_money(tot)}원')
            p.setFont(self.font())
        f = QFont(self.font())
        f.setBold(True)
        p.setFont(f)
        for x, y, txt in marks:
            rr_ = QRectF(x - 30, y - 10, 60, 20)
            p.setPen(QPen(QColor(0, 0, 0, 110)))
            p.drawText(rr_.translated(1, 1), Qt.AlignmentFlag.AlignCenter, txt)
            p.setPen(QPen(QColor('#ffffff')))
            p.drawText(rr_, Qt.AlignmentFlag.AlignCenter, txt)
        p.setFont(self.font())
        if skipped:
            p.setPen(QPen(QColor(tn['axis2'])))
            p.drawText(QRectF(10, B - 4, R_ - 10, 20), Qt.AlignmentFlag.AlignCenter,
                       f'합계가 0 이하인 {skipped}개 항목은 비율에서 뺐습니다')
        return [(name, f'{name}  {t / tot * 100:.1f}%') for name, t in items]


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
        self.year.setToolTip('연도를 칸에 바로 쳐서 바꿀 수 있습니다')
        self.group = QComboBox()
        self.cat = QComboBox()
        self.monthly = QCheckBox('월단위')
        self.month = QComboBox()
        self.month.addItems([f'{i}월' for i in range(1, 13)])
        self.month.setCurrentIndex(t.month - 1)
        self.kind = QComboBox()
        for key, label in KINDS:
            self.kind.addItem(label, key)
        saved = TH.settings().value('graph_kind', 'line')
        self.kind.setCurrentIndex(KIND_KEYS.index(saved) if saved in KIND_KEYS else 0)
        self.chart = Chart()
        self.year.valueChanged.connect(lambda *_: self.draw())
        for w in (self.cat, self.month):
            w.currentIndexChanged.connect(lambda *_: self.draw())
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.group.currentIndexChanged.connect(self._group_changed)
        self.monthly.toggled.connect(lambda *_: self.draw())
        lay = QVBoxLayout(self)
        lay.addWidget(h('연도', self.year, '  대분류', self.group, '  소분류', self.cat, '  ', self.monthly, self.month,
                        '  종류', self.kind, 'stretch', button('이미지로 저장', self.save_png)))
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

    def _kind_changed(self, *_):
        key = self.kind.currentData()
        s = TH.settings()
        if key == 'line':
            s.remove('graph_kind')
        else:
            s.setValue('graph_kind', key)
        self.draw()

    def draw(self):
        self.month.setEnabled(self.monthly.isChecked())
        y = self.year.value()
        m = self.month.currentIndex() + 1 if self.monthly.isChecked() else None
        labels, series = RP.graph_series(self.con, self.app.lid, y, group=self.group.currentData(),
                                         code=self.cat.currentData(), month=m,
                                         settle_day=int(db.get_meta(self.con, 'settle_day', 1) or 1))
        what = self.cat.currentText() if self.cat.currentData() else self.group.currentText()
        title = f"{y}년{f' {m}월' if m else ''} {what} 분석"
        self.chart.set_data(labels, series, self.kind.currentData() or 'line', title)

    def save_png(self):
        from PyQt6.QtWidgets import QFileDialog
        import os
        path, _ = QFileDialog.getSaveFileName(self, '그래프 저장', os.path.join(os.path.expanduser('~'), '그래프.png'),
                                              'PNG (*.png)')
        if path:
            self.chart.grab().save(path, 'PNG')
