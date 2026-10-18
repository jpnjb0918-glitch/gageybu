"""피드·타임라인 테마의 가계부 목록 그리기.

표(QTableWidget)는 그대로 두고 '품목' 칸 하나에 한 줄 전체를 카드/짧은 글 모양으로 그린다.
선택·여러 줄 선택·Delete·더블클릭·CSV·인쇄는 원래 표 그대로라서 기능이 같다.
"""
import datetime as dt

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QBrush, QColor, QConicalGradient, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QWidget

from .. import theme as T
from ..util import fmt_money

# 가계부 표의 칸 번호
C_DATE, C_ITEM, C_IN, C_OUT, C_BAL, C_CODE, C_MEMO = range(7)
WEEK = '월화수목금토일'


def _date_label(iso):
    try:
        d = dt.date.fromisoformat(iso)
    except ValueError:
        return iso
    return f'{d.year}.{d.month:02d}.{d.day:02d} ({WEEK[d.weekday()]})'


def _short(iso):
    try:
        d = dt.date.fromisoformat(iso)
    except ValueError:
        return iso
    return f'{d.month}/{d.day}'


def _man(v):
    if abs(v) >= 10000:
        s = f'{v / 10000:.{0 if abs(v) >= 100000 else 1}f}'
        return (s[:-2] if s.endswith('.0') else s) + '만'
    return fmt_money(v)


def _ring_brush(rect, cols):
    g = QConicalGradient(rect.center(), 45)
    cols = list(cols) + [cols[0]]
    for i, c in enumerate(cols):
        g.setColorAt(i / (len(cols) - 1), QColor(c))
    return QBrush(g)


def draw_avatar(p, rect, label, c, ring=False):
    """계정과목 첫 글자를 넣은 동그라미"""
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    r = QRectF(rect)
    if ring and c.get('ring'):
        p.setBrush(_ring_brush(r, c['ring']))
        p.drawEllipse(r)
        r = r.adjusted(2.5, 2.5, -2.5, -2.5)
        p.setBrush(QColor(c['card']))
        p.drawEllipse(r)
        r = r.adjusted(2, 2, -2, -2)
    p.setBrush(QColor(T.avatar_color(label)))
    p.drawEllipse(r)
    f = QFont(p.font())
    f.setBold(True)
    f.setPixelSize(max(10, int(r.height() * 0.42)))
    p.setFont(f)
    p.setPen(QColor('#FFFFFF'))
    p.drawText(r, Qt.AlignmentFlag.AlignCenter, T.avatar_initial(label))
    p.restore()


class LedgerDelegate(QStyledItemDelegate):
    """theme: 'feed' | 'timeline' | 'timeline_dark'"""
    HEAD = 34          # 날짜 머리 높이

    def __init__(self, table):
        super().__init__(table)
        self.table = table
        self.theme = 'feed'
        self.day_sums = {}        # 'YYYY-MM-DD' → (수입, 지출)
        self.day_counts = {}

    def _text(self, row, col):
        it = self.table.item(row, col)
        return it.text() if it else ''

    def first_of_day(self, row):
        return row == 0 or self._text(row - 1, C_DATE) != self._text(row, C_DATE)

    def row_height(self, row):
        fm = QFontMetrics(self.table.font())
        lh = fm.height()
        head = self.HEAD if self.first_of_day(row) else 0
        if self.theme == 'feed':
            return head + max(64, 2 * lh + 30)
        memo = 1 if self._text(row, C_MEMO) else 0
        return head + max(60, (2 + memo) * lh + 26)

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.row_height(index.row()))

    # ── 그리기 ──
    def paint(self, p, option, index):
        c = T.sns_colors(self.theme) or T.SNS['feed']
        row = index.row()
        rect = QRectF(option.rect)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.fillRect(rect, QColor(c['bg'] if self.theme == 'feed' else c['card']))
        date = self._text(row, C_DATE)
        if self.first_of_day(row):
            self._paint_head(p, QRectF(rect.left(), rect.top(), rect.width(), self.HEAD), date, c)
            rect = rect.adjusted(0, self.HEAD, 0, 0)
        if self.theme == 'feed':
            self._paint_card(p, rect, row, c, selected)
        else:
            self._paint_post(p, rect, row, c, selected)
        p.restore()

    def _paint_head(self, p, r, date, c):
        inc, exp = self.day_sums.get(date, (0, 0))
        f = QFont(p.font())
        f.setBold(True)
        if self.theme == 'feed':
            p.setFont(f)
            p.setPen(QColor(c['ink']))
            p.drawText(r.adjusted(16, 6, -16, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       f'{_date_label(date)}')
        else:
            p.fillRect(r, QColor(c['surface2']))
            p.setPen(QColor(c['grid']))
            p.drawLine(QPointF(r.left(), r.bottom() - 0.5), QPointF(r.right(), r.bottom() - 0.5))
            p.setFont(f)
            p.setPen(QColor(c['ink']))
            p.drawText(r.adjusted(14, 0, -14, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, _date_label(date))
        f.setBold(False)
        p.setFont(f)
        x = r.right() - 16
        for txt, col in ((f'-{fmt_money(exp)}' if exp else '', c['out']), (f'+{fmt_money(inc)}' if inc else '', c['in'])):
            if not txt:
                continue
            w = QFontMetrics(f).horizontalAdvance(txt)
            p.setPen(QColor(col))
            p.drawText(QRectF(x - w, r.top() + (6 if self.theme == 'feed' else 0), w, r.height() - (6 if self.theme == 'feed' else 0)),
                       Qt.AlignmentFlag.AlignVCenter, txt)
            x -= w + 10

    def _amounts(self, row):
        out = []
        inc, exp = self._text(row, C_IN), self._text(row, C_OUT)
        if inc:
            out.append(('+' + inc, 'in'))
        if exp:
            out.append(('-' + exp, 'out'))
        return out

    def _paint_card(self, p, rect, row, c, selected):
        card = rect.adjusted(12, 4, -12, -4)
        p.setPen(QPen(QColor(c['accent'] if selected else c['line']), 1.5 if selected else 1))
        p.setBrush(QColor(c['sel'] if selected else c['card']))
        p.drawRoundedRect(card, 12, 12)
        av = QRectF(card.left() + 12, card.center().y() - 19, 38, 38)
        code = self._text(row, C_CODE)
        draw_avatar(p, av, code, c)
        self._paint_texts(p, QRectF(av.right() + 12, card.top() + 8, card.width() - (av.width() + 36), card.height() - 16),
                          row, c, sub=' · '.join(x for x in (code, self._text(row, C_MEMO)) if x), memo_line=False)

    def _paint_post(self, p, rect, row, c, selected):
        if selected:
            p.fillRect(rect, QColor(c['sel']))
        p.setPen(QColor(c['grid']))
        p.drawLine(QPointF(rect.left(), rect.bottom() - 0.5), QPointF(rect.right(), rect.bottom() - 0.5))
        av = QRectF(rect.left() + 14, rect.top() + 11, 42, 42)
        code = self._text(row, C_CODE)
        draw_avatar(p, av, code, c)
        self._paint_texts(p, QRectF(av.right() + 12, rect.top() + 10, rect.width() - (av.width() + 40), rect.height() - 18),
                          row, c, sub=f'{code} · {_short(self._text(row, C_DATE))}', memo_line=True)

    def _paint_texts(self, p, r, row, c, sub, memo_line):
        base = QFont(p.font())
        fb = QFont(base)
        fb.setBold(True)
        fs = QFont(base)
        fs.setPointSizeF(max(7.0, base.pointSizeF() * 0.88) if base.pointSizeF() > 0 else 8.0)
        fmb, fms = QFontMetrics(fb), QFontMetrics(fs)
        # 오른쪽: 금액 (굵게) + 잔액
        amts = self._amounts(row)
        amt_w = max([fmb.horizontalAdvance(t) for t, _ in amts] + [0])
        bal = f'잔액 {self._text(row, C_BAL)}'
        right_w = max(amt_w, fms.horizontalAdvance(bal) if not memo_line else 0)
        y = r.top()
        p.setFont(fb)
        for i, (t, k) in enumerate(amts):
            p.setPen(QColor(c[k]))
            p.drawText(QRectF(r.right() - right_w, y + i * fmb.height(), right_w, fmb.height()),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, t)
        text_w = r.width() - right_w - 12
        # 1줄: 품목 (+ 타임라인은 옆에 계정과목 · 날짜)
        item = self._text(row, C_ITEM)
        p.setPen(QColor(c['ink']))
        if memo_line:
            iw = min(fmb.horizontalAdvance(item), int(text_w * 0.7))
            p.drawText(QRectF(r.left(), y, iw, fmb.height()), Qt.AlignmentFlag.AlignVCenter,
                       fmb.elidedText(item, Qt.TextElideMode.ElideRight, iw))
            p.setFont(fs)
            p.setPen(QColor(c['muted']))
            mw = text_w - iw - 6
            if mw > 20:
                p.drawText(QRectF(r.left() + iw + 6, y, mw, fmb.height()), Qt.AlignmentFlag.AlignVCenter,
                           fms.elidedText(sub, Qt.TextElideMode.ElideRight, int(mw)))
            y += fmb.height() + 2
            memo = self._text(row, C_MEMO)
            if memo:
                p.setFont(base)
                p.setPen(QColor(c['ink']))
                fm = QFontMetrics(base)
                p.drawText(QRectF(r.left(), y, text_w, fm.height()), Qt.AlignmentFlag.AlignVCenter,
                           fm.elidedText(memo.replace('\n', ' '), Qt.TextElideMode.ElideRight, int(text_w)))
                y += fm.height() + 2
            p.setFont(fs)
            p.setPen(QColor(c['muted']))
            p.drawText(QRectF(r.left(), y, text_w, fms.height()), Qt.AlignmentFlag.AlignVCenter, bal)
        else:
            p.drawText(QRectF(r.left(), y, text_w, fmb.height()), Qt.AlignmentFlag.AlignVCenter,
                       fmb.elidedText(item, Qt.TextElideMode.ElideRight, int(text_w)))
            y += fmb.height() + 3
            p.setFont(fs)
            p.setPen(QColor(c['muted']))
            p.drawText(QRectF(r.left(), y, text_w, fms.height()), Qt.AlignmentFlag.AlignVCenter,
                       fms.elidedText(sub, Qt.TextElideMode.ElideRight, int(text_w)))
            p.drawText(QRectF(r.right() - right_w, y + max(0, len(amts) - 1) * fmb.height(), right_w, fms.height()),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, bal)


class Stories(QWidget):
    """피드 테마 맨 위: 지출이 많은 계정과목 동그라미 (보기만 하는 요약)"""
    SIZE = 58

    def __init__(self):
        super().__init__()
        self.items, self.caption = [], ''
        self.setFixedHeight(self.SIZE + 50)

    def set_items(self, items, caption):
        self.items, self.caption = items, caption
        self.setToolTip('\n'.join(f'{k}  {fmt_money(v)}원' for k, v in items))
        self.update()

    def paintEvent(self, _ev):
        c = T.sns_colors('feed')
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        f = QFont(self.font())
        fs = QFont(f)
        fs.setPointSizeF(max(7.0, f.pointSizeF() * 0.85) if f.pointSizeF() > 0 else 8.0)
        p.setFont(fs)
        p.setPen(QColor(c['muted']))
        p.drawText(QRectF(14, 0, self.width() - 28, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.caption)
        x, slot = 14, self.SIZE + 18
        fm = QFontMetrics(fs)
        for k, v in self.items:
            if x + slot > self.width():
                break
            draw_avatar(p, QRectF(x + 9, 18, self.SIZE, self.SIZE), k, c, ring=True)
            p.setPen(QColor(c['ink']))
            p.drawText(QRectF(x, 18 + self.SIZE + 2, slot, fm.height()), Qt.AlignmentFlag.AlignHCenter,
                       fm.elidedText(k, Qt.TextElideMode.ElideRight, slot))
            fb = QFont(fs)
            fb.setBold(True)
            p.setFont(fb)
            p.setPen(QColor(c['out']))
            p.drawText(QRectF(x, 18 + self.SIZE + 2 + fm.height(), slot, fm.height()), Qt.AlignmentFlag.AlignHCenter, _man(v))
            p.setFont(fs)
            x += slot
        p.end()
