"""피드·타임라인 테마의 가계부 화면 그리기 (안드로이드판과 같은 모양).

표(QTableWidget)는 그대로 두고 '품목' 칸 하나에 한 줄 전체를 그린다.
  피드     : 하루 = 게시물 한 개 (머리 · 사진 칸 · 아이콘 줄 · 합계 · 내역 글 · 잔액) — 한 줄(내역) = 게시물 글 한 줄
  타임라인 : 한 건 = 글 한 개 (얼굴 · 이름 @계정 · 날짜 · 메모 · 금액 · 아이콘 줄), 날짜마다 띠
선택·여러 줄 선택·Delete·CSV·인쇄는 원래 표 그대로라서 기능이 같다. 그림 속 아이콘은 hit_test 로 누른다.
"""
import datetime as dt

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QConicalGradient, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QWidget

from .. import theme as T
from ..util import fmt_money
from . import icons as I

# 가계부 표의 칸 번호
C_DATE, C_ITEM, C_IN, C_OUT, C_BAL, C_CODE, C_MEMO = range(7)
WEEK = '월화수목금토일'
POST_W = 560          # 피드 게시물 폭 (가운데 정렬)
TW_W = 640            # 타임라인 글 칸 폭
TILE_H = 230          # 피드 사진 칸 높이
# 사진 칸 색 (미니홈피 청록·분홍·하늘·노랑·보라) — 안드로이드판 .ptile.t0~t4
TILES = (('#347C7C', '#FFFFFF'), ('#F06C96', '#FFFFFF'), ('#2FB3B3', '#FFFFFF'), ('#FFD84D', '#1A1A1A'), ('#8E7CE8', '#FFFFFF'))
TILE_STK = ('a02', 'a03', 'a05', 'a06', 'a07', 'a08', 'a09', 'a11', 'a12', 'a14', 'a15', 'a16', 'a17', 'a18', 'a20', 'a21',
            'b01', 'b03', 'b04', 'b05', 'b06', 'b07', 'b09', 'b10', 'b12', 'b13', 'b14', 'b15', 'b16', 'b17', 'b18', 'b19', 'b20',
            'b22', 'b24', 'b25', 'b27', 'b28', 'b29', 'b31', 'b32', 'b34', 'b35', 'b36', 'b37', 'b39', 'b40')


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


def _hash(s):
    h = 0
    for ch in str(s or ''):
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h


def _ring_brush(rect, cols):
    g = QConicalGradient(rect.center(), 45)
    cols = list(cols) + [cols[0]]
    for i, c in enumerate(cols):
        g.setColorAt(i / (len(cols) - 1), QColor(c))
    return QBrush(g)


def _font(base, scale=1.0, bold=False, family=None):
    f = QFont(base)
    if family:
        f.setFamily(family)
    if scale != 1.0:
        if f.pixelSize() > 0:
            f.setPixelSize(max(8, round(f.pixelSize() * scale)))
        elif f.pointSizeF() > 0:
            f.setPointSizeF(max(6.0, f.pointSizeF() * scale))
    f.setBold(bold)
    return f


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
        r = r.adjusted(2.5, 2.5, -2.5, -2.5)
    p.setBrush(QColor(T.avatar_color(label)))
    p.drawEllipse(r)
    f = QFont(p.font())
    f.setBold(True)
    f.setPixelSize(max(10, int(r.height() * 0.42)))
    p.setFont(f)
    p.setPen(QColor('#FFFFFF'))
    p.drawText(r, Qt.AlignmentFlag.AlignCenter, T.avatar_initial(label))
    p.restore()


def draw_minimi(p, rect, sid, theme=None):
    """내 미니미 동그라미 (피드는 색 테두리)"""
    pm = T.avatar_pixmap(sid, int(rect.width()), theme)
    p.drawPixmap(QPointF(rect.left(), rect.top()), pm)


def _elide(p, rect, text, flags=Qt.AlignmentFlag.AlignVCenter):
    fm = QFontMetrics(p.font())
    p.drawText(rect, flags, fm.elidedText(text, Qt.TextElideMode.ElideRight, int(max(0, rect.width()))))


def _wrap(fm, text, width, max_lines):
    """글자 단위로 줄 나누기 (한국어는 띄어쓰기가 적어 글자 단위가 자연스러움)"""
    out, cur = [], ''
    for ch in text.replace('\n', ' '):
        if fm.horizontalAdvance(cur + ch) > width and cur:
            out.append(cur)
            cur = ch
            if len(out) == max_lines:
                break
        else:
            cur += ch
    else:
        if cur:
            out.append(cur)
        return out
    out[-1] = fm.elidedText(out[-1] + cur + '…', Qt.TextElideMode.ElideRight, int(width))
    return out


class LedgerDelegate(QStyledItemDelegate):
    """theme: SNS 테마 이름 (피드·타임라인 × 미니홈피 색·밝게·어둡게). 모양은 T.layout_of 로"""
    HEAD = 36           # 타임라인 날짜 띠 높이

    def __init__(self, table):
        super().__init__(table)
        self.table = table
        self.theme = 'feed'
        self.days = {}            # 'YYYY-MM-DD' → {'inc','exp','n','first','bal'}
        self.ledger_name = ''
        self.minimi = T.DEFAULT_MINIMI
        self.hits = {}            # 줄 번호 → [(QRectF, 할 일, 날짜/값)] (그릴 때 채움)

    @property
    def feed(self):
        return T.layout_of(self.theme) == 'feed'

    def _text(self, row, col):
        it = self.table.item(row, col)
        return it.text() if it else ''

    def first_of_day(self, row):
        return row == 0 or self._text(row - 1, C_DATE) != self._text(row, C_DATE)

    def last_of_day(self, row):
        return row == self.table.rowCount() - 1 or self._text(row + 1, C_DATE) != self._text(row, C_DATE)

    def _col(self, rect):
        """가운데 칸 (x, 폭)"""
        w = min(POST_W if self.feed else TW_W, rect.width() - (24 if self.feed else 0))
        return rect.left() + max(0.0, (rect.width() - w) / 2), w

    def _fonts(self):
        base = QFont(self.table.font())
        return base, _font(base, bold=True), _font(base, 0.88)

    # ── 높이 ──
    def row_height(self, row):
        base, fb, fs = self._fonts()
        lh, lhb, lhs = QFontMetrics(base).height(), QFontMetrics(fb).height(), QFontMetrics(fs).height()
        if self.feed:
            h = lh + 10                                   # 내역 글 한 줄
            if self.first_of_day(row):
                h += 58 + TILE_H + 46 + lhb + 8           # 머리 · 사진 · 아이콘 줄 · 합계
            if self.last_of_day(row):
                h += lhs + 26                             # 잔액 · 게시물 사이
            return h
        x, w = self._col(QRectF(0, 0, self.table.viewport().width(), 10))
        memo = self._text(row, C_MEMO)
        lines = len(_wrap(QFontMetrics(base), memo, w - 82, 3)) if memo else 0
        h = 12 + lhb + 2 + lines * (lh + 1) + QFontMetrics(_font(base, 1.12, True)).height() + 4 + 32 + 6
        return h + (self.HEAD if self.first_of_day(row) else 0)

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.row_height(index.row()))

    # ── 누르기 ──
    def hit_test(self, row, pos):
        for r, what, val in self.hits.get(row, ()):
            if r.contains(pos):
                return what, val
        return None

    # ── 그리기 ──
    def paint(self, p, option, index):
        c = T.sns_colors(self.theme) or T.SNS['feed']
        row = index.row()
        rect = QRectF(option.rect)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(rect, QColor(c['page']))
        self.hits[row] = []
        if self.feed:
            self._paint_feed(p, rect, row, c, selected)
        else:
            self._paint_tweet(p, rect, row, c, selected)
        p.restore()

    def _icon(self, p, r, name, color, row, what=None, val=None, on=False):
        I.paint(p, r, name, color, on)
        if what:
            self.hits[row].append((r.adjusted(-6, -6, 6, 6), what, val))

    def _paint_feed(self, p, rect, row, c, selected):
        base, fb, fs = self._fonts()
        x0, w = self._col(rect)
        date = self._text(row, C_DATE)
        day = self.days.get(date, {})
        y = rect.top()
        if self.first_of_day(row):
            # 머리: 내 미니미 · 날짜 · 장부·건수 · ⋯
            draw_minimi(p, QRectF(x0 + 4, y + 12, 36, 36), self.minimi, self.theme)
            p.setFont(fb)
            p.setPen(QColor(c['ink']))
            p.drawText(QRectF(x0 + 50, y + 11, w - 100, QFontMetrics(fb).height()), Qt.AlignmentFlag.AlignVCenter, _date_label(date))
            p.setFont(fs)
            p.setPen(QColor(c['muted']))
            _elide(p, QRectF(x0 + 50, y + 13 + QFontMetrics(fb).height(), w - 100, QFontMetrics(fs).height()),
                   f"{self.ledger_name} · {day.get('n', 1)}건")
            self._icon(p, QRectF(x0 + w - 32, y + 18, 24, 24), 'dots', c['ink'], row, 'menu', date)
            y += 58
            self._paint_tile(p, QRectF(x0, y, w, TILE_H), date, day)
            y += TILE_H
            # 아이콘 줄: ♥(수입 있는 날) 💬(이 날 새 내역) ⇅(순서) 📅(달력)
            ix = x0 + 6
            inc, exp, n = day.get('inc', 0), day.get('exp', 0), day.get('n', 1)
            self._icon(p, QRectF(ix, y + 10, 26, 26), 'heart', c['accent'] if inc else c['ink'], row, on=bool(inc))
            ix += 42
            self._icon(p, QRectF(ix, y + 10, 26, 26), 'comment', c['ink'], row, 'add', date)
            ix += 42
            if n > 1:
                self._icon(p, QRectF(ix, y + 10, 26, 26), 'sort', c['ink'], row, 'order', date)
                ix += 42
            self._icon(p, QRectF(ix, y + 10, 26, 26), 'calendar', c['ink'], row, 'cal', date)
            if n > 1:                                      # 여러 장 사진처럼 점
                k = min(n, 5)
                cx = x0 + w / 2 - (k - 1) * 5
                p.setPen(Qt.PenStyle.NoPen)
                for i in range(k):
                    p.setBrush(QColor(c['accent'] if i == 0 else c['line']))
                    p.drawEllipse(QPointF(cx + i * 10, y + 23), 3, 3)
            y += 46
            # 합계 줄 (좋아요 줄 자리)
            p.setFont(fb)
            xx = x0 + 10
            parts = []
            if exp:
                parts += [('지출 ', c['ink']), (f'-{fmt_money(exp)}', c['out'])]
            if inc:
                parts += [(' · ' if exp else '', c['ink']), ('수입 ', c['ink']), (f'+{fmt_money(inc)}', c['in'])]
            fm = QFontMetrics(fb)
            for t, col in parts:
                if not t:
                    continue
                p.setPen(QColor(col))
                p.drawText(QRectF(xx, y, fm.horizontalAdvance(t) + 2, fm.height()), Qt.AlignmentFlag.AlignVCenter, t)
                xx += fm.horizontalAdvance(t)
            y += fm.height() + 8
        # 내역 글 한 줄: 품목(굵게) 계정 · 메모 ......... 금액
        lh = QFontMetrics(base).height()
        line = QRectF(x0 + 4, y, w - 8, lh + 8)
        if selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(c['sel']))
            p.drawRoundedRect(line, 8, 8)
        amts = self._amounts(row)
        p.setFont(fb)
        fmb = QFontMetrics(fb)
        aw = sum(fmb.horizontalAdvance(t) for t, _ in amts) + 8 * max(0, len(amts) - 1)
        ax = line.right() - 6 - aw
        for t, k in amts:
            p.setPen(QColor(c[k]))
            p.drawText(QRectF(ax, line.top(), fmb.horizontalAdvance(t) + 2, line.height()), Qt.AlignmentFlag.AlignVCenter, t)
            ax += fmb.horizontalAdvance(t) + 8
        item = self._text(row, C_ITEM) or '(품목 없음)'
        avail = line.width() - 18 - aw
        iw = min(fmb.horizontalAdvance(item), avail * 0.72)
        p.setPen(QColor(c['ink']))
        _elide(p, QRectF(line.left() + 6, line.top(), iw, line.height()), item)
        sub = ' · '.join(x for x in (self._text(row, C_CODE), self._text(row, C_MEMO).replace('\n', ' ')) if x)
        p.setFont(base)
        p.setPen(QColor(c['muted']))
        _elide(p, QRectF(line.left() + 12 + iw, line.top(), avail - iw - 6, line.height()), sub)
        y += lh + 10
        if self.last_of_day(row):
            p.setFont(fs)
            p.setPen(QColor(c['muted']))
            p.drawText(QRectF(x0 + 10, y, w - 20, QFontMetrics(fs).height()), Qt.AlignmentFlag.AlignVCenter,
                       f"잔액 {fmt_money(day.get('bal', 0))}원")
            p.setPen(QPen(QColor(c['grid']), 1))
            p.drawLine(QPointF(x0, rect.bottom() - 1), QPointF(x0 + w, rect.bottom() - 1))

    def _paint_tile(self, p, r, date, day):
        """사진 칸: 물방울 무늬 + 그날 금액(도트 글꼴) + 품목 + 옛날 디카 날짜 도장 + 고양이"""
        try:
            d = dt.date.fromisoformat(date)
        except ValueError:
            d = dt.date.today()
        bg, fg = TILES[d.day % 5]
        p.save()
        p.setClipRect(r)
        p.fillRect(r, QColor(bg))
        dot = QColor('#FFFFFF')
        dot.setAlphaF(0.45 if fg != '#FFFFFF' else 0.2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(dot)
        yy = r.top() + 7
        while yy < r.bottom():
            xx = r.left() + 7
            while xx < r.right():
                p.drawEllipse(QPointF(xx, yy), 1.5, 1.5)
                xx += 14
            yy += 14
        fam = T.load_fonts()
        base = QFont(self.table.font())
        big = QFont(fam) if fam else QFont(base)
        big.setPixelSize(30)
        big.setBold(True)
        inc, exp, n = day.get('inc', 0), day.get('exp', 0), day.get('n', 1)
        txt = f'-{fmt_money(exp)}' if exp else f'+{fmt_money(inc)}'
        tx = QRectF(r.left() + 18, r.top(), r.width() - 110, r.height())
        fmb = QFontMetrics(big)
        cy = r.center().y() - 14
        p.setFont(big)
        sh = QColor('#000000' if fg == '#FFFFFF' else '#FFFFFF')
        sh.setAlphaF(0.22 if fg == '#FFFFFF' else 0.6)
        p.setPen(sh)
        p.drawText(QRectF(tx.left() + 2, cy - fmb.height() / 2 + 2, tx.width(), fmb.height()), Qt.AlignmentFlag.AlignCenter, txt)
        p.setPen(QColor(fg))
        p.drawText(QRectF(tx.left(), cy - fmb.height() / 2, tx.width(), fmb.height()), Qt.AlignmentFlag.AlignCenter, txt)
        cap_f = QFont(fam) if fam else QFont(base)
        cap_f.setPixelSize(12)
        p.setFont(cap_f)
        fmc = QFontMetrics(cap_f)
        first = day.get('first') or '(품목 없음)'
        cap = f'{first} 외 {n - 1}건' if n > 1 else first
        cw = min(fmc.horizontalAdvance(cap) + 24, tx.width())
        pill = QRectF(tx.center().x() - cw / 2, cy + fmb.height() / 2 + 6, cw, fmc.height() + 8)
        pc = QColor('#000000' if fg == '#FFFFFF' else '#FFFFFF')
        pc.setAlphaF(0.2 if fg == '#FFFFFF' else 0.55)
        p.setBrush(pc)
        p.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
        p.setPen(QColor(fg))
        p.drawText(pill.adjusted(12, 0, -12, 0), Qt.AlignmentFlag.AlignCenter,
                   fmc.elidedText(cap, Qt.TextElideMode.ElideRight, int(pill.width() - 24)))
        stamp = f"'{d.year % 100:02d} {d.month:02d} {d.day:02d}"
        p.setPen(QColor(0, 0, 0, 120))
        p.drawText(QRectF(r.right() - 121, r.top() + 10, 110, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, stamp)
        p.setPen(QColor('#FFB347'))
        p.drawText(QRectF(r.right() - 122, r.top() + 9, 110, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, stamp)
        pm = T.sticker_pixmap(TILE_STK[_hash(date) % len(TILE_STK)], 84)
        if not pm.isNull():
            dpr = pm.devicePixelRatio() or 1.0
            p.drawPixmap(QPointF(r.right() - pm.width() / dpr - 10, r.bottom() - pm.height() / dpr - 8), pm)
        p.restore()

    def _amounts(self, row):
        out = []
        inc, exp = self._text(row, C_IN), self._text(row, C_OUT)
        if inc:
            out.append(('+' + inc, 'in'))
        if exp:
            out.append(('-' + exp, 'out'))
        return out

    def _paint_tweet(self, p, rect, row, c, selected):
        base, fb, fs = self._fonts()
        x0, w = self._col(rect)
        date = self._text(row, C_DATE)
        day = self.days.get(date, {})
        pen_line = QPen(QColor(c['line']), 1)
        y = rect.top()
        if self.first_of_day(row):
            hr = QRectF(x0, y, w, self.HEAD)
            p.fillRect(hr, QColor(c['surface2']))
            p.setFont(fb)
            p.setPen(QColor(c['ink']))
            p.drawText(hr.adjusted(16, 0, -16, 0), Qt.AlignmentFlag.AlignVCenter, _date_label(date))
            xr = hr.right() - 14
            if day.get('n', 1) > 1:
                self._icon(p, QRectF(xr - 20, hr.center().y() - 10, 20, 20), 'sort', c['ink'], row, 'order', date)
                xr -= 30
            p.setFont(base)
            fm = QFontMetrics(base)
            for t, col in ((f"-{fmt_money(day.get('exp', 0))}" if day.get('exp') else '', c['out']),
                           (f"+{fmt_money(day.get('inc', 0))}" if day.get('inc') else '', c['in'])):
                if t:
                    tw = fm.horizontalAdvance(t)
                    p.setPen(QColor(col))
                    p.drawText(QRectF(xr - tw, hr.top(), tw + 2, hr.height()), Qt.AlignmentFlag.AlignVCenter, t)
                    xr -= tw + 10
            p.setPen(pen_line)
            p.drawLine(QPointF(x0, hr.bottom() - 0.5), QPointF(x0 + w, hr.bottom() - 0.5))
            y += self.HEAD
        body = QRectF(x0, y, w, rect.bottom() - y)
        if selected:
            p.fillRect(body, QColor(c['sel']))
        code = self._text(row, C_CODE)
        draw_avatar(p, QRectF(x0 + 14, y + 12, 42, 42), code, c)
        cx, cw = x0 + 68, w - 82
        yy = y + 11
        # 1줄: 품목 @계정 · 날짜
        fmb = QFontMetrics(fb)
        item = self._text(row, C_ITEM) or '(품목 없음)'
        iw = min(fmb.horizontalAdvance(item), cw * 0.62)
        p.setFont(fb)
        p.setPen(QColor(c['ink']))
        _elide(p, QRectF(cx, yy, iw, fmb.height()), item)
        p.setFont(base)
        p.setPen(QColor(c['muted']))
        _elide(p, QRectF(cx + iw + 6, yy, cw - iw - 6, fmb.height()), f"@{code.replace(' ', '')} · {_short(date)}")
        yy += fmb.height() + 2
        memo = self._text(row, C_MEMO)
        if memo:
            fm = QFontMetrics(base)
            p.setPen(QColor(c['ink']))
            for ln in _wrap(fm, memo, cw, 3):
                p.drawText(QRectF(cx, yy, cw, fm.height()), Qt.AlignmentFlag.AlignVCenter, ln)
                yy += fm.height() + 1
        fm_ = _font(base, 1.12, True)
        p.setFont(fm_)
        fmm = QFontMetrics(fm_)
        ax = cx
        for t, k in self._amounts(row):
            p.setPen(QColor(c[k]))
            p.drawText(QRectF(ax, yy, fmm.horizontalAdvance(t) + 2, fmm.height()), Qt.AlignmentFlag.AlignVCenter, t)
            ax += fmm.horizontalAdvance(t) + 10
        yy += fmm.height() + 4
        # 아이콘 줄: 💬 수정 · 🔁 다시 입력 · ♥(수입) · 📊 잔액
        step = min(cw, 330) / 3.6
        inc = bool(self._text(row, C_IN))
        self._icon(p, QRectF(cx, yy + 6, 19, 19), 'comment', c['muted'], row, 'edit', row)
        self._icon(p, QRectF(cx + step, yy + 6, 19, 19), 'repeat', c['muted'], row, 'copy', row)
        I.paint(p, QRectF(cx + step * 2, yy + 6, 19, 19), 'heart', c['accent'] if inc else c['muted'], inc)
        I.paint(p, QRectF(cx + step * 3, yy + 6, 19, 19), 'stats', c['muted'])
        p.setFont(fs)
        p.setPen(QColor(c['muted']))
        p.drawText(QRectF(cx + step * 3 + 23, yy + 4, 140, 23), Qt.AlignmentFlag.AlignVCenter, self._text(row, C_BAL))
        p.setPen(pen_line)
        p.drawLine(QPointF(x0, rect.bottom() - 0.5), QPointF(x0 + w, rect.bottom() - 0.5))
        # 글 칸 양옆 선 (짧은 글 SNS 의 가운데 칸)
        if w < rect.width() - 2:
            p.drawLine(QPointF(x0, rect.top()), QPointF(x0, rect.bottom()))
            p.drawLine(QPointF(x0 + w, rect.top()), QPointF(x0 + w, rect.bottom()))


# ════════ 가계부 화면 위쪽 덩어리 (피드: 프로필 머리·하이라이트·탭 / 타임라인: 탭·고정된 글·트렌드) ════════
class _Painted(QWidget):
    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.hits = []

    def colors(self):
        return T.sns_colors() or T.SNS['feed']

    def mouseMoveEvent(self, ev):
        on = any(r.contains(ev.position()) for r, _w, _v in self.hits)
        self.setCursor(Qt.CursorShape.PointingHandCursor if on else Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, ev):
        for r, what, val in self.hits:
            if r.contains(ev.position()):
                self.on_hit(what, val)
                return
        super().mousePressEvent(ev)

    def on_hit(self, what, val):
        pass


class ProfileHeader(_Painted):
    """피드: 큰 미니미 · 장부 이름 · 이달 수입/지출/차액(게시물·팔로워 자리) · 기분·다짐·오늘 지출·잔액"""
    avatar_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.d = {}

    def set_data(self, **d):
        self.d = d
        fm = QFontMetrics(self.font())
        lines = 3 + (1 if d.get('motto') else 0)
        self.setFixedHeight(max(150, 26 + 36 + 34 + lines * (fm.height() + 3) + 16))
        self.update()

    def on_hit(self, what, val):
        self.avatar_clicked.emit()

    def paintEvent(self, _ev):
        c, d = self.colors(), self.d
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(c['page']))
        x0 = max(16.0, (self.width() - POST_W - 60) / 2)
        av = QRectF(x0 + 8, 22, 118, 118)
        draw_minimi(p, av, d.get('minimi', T.DEFAULT_MINIMI))
        self.hits = [(av, 'avatar', None)]
        base = QFont(self.font())
        x = av.right() + 34
        wv = self.width() - x - 16
        f_name = _font(base, 1.3, True)
        p.setFont(f_name)
        p.setPen(QColor(c['ink']))
        fmn = QFontMetrics(f_name)
        y = 26
        _elide(p, QRectF(x, y, wv, fmn.height()), d.get('name', ''))
        y += fmn.height() + 12
        # 이달 수입 3,300,000   이달 지출 863,500   차액 2,436,500
        fb = _font(base, 1.0, True)
        fmb, fm = QFontMetrics(fb), QFontMetrics(base)
        xx = x
        m = d.get('month', '')
        for lab, val, col in ((f'{m}월 수입 ', fmt_money(d.get('inc', 0)), c['in']), (f'{m}월 지출 ', fmt_money(d.get('exp', 0)), c['out']),
                              ('차액 ', fmt_money(d.get('inc', 0) - d.get('exp', 0)), c['ink'])):
            p.setFont(base)
            p.setPen(QColor(c['ink']))
            p.drawText(QRectF(xx, y, fm.horizontalAdvance(lab) + 2, fmb.height()), Qt.AlignmentFlag.AlignVCenter, lab)
            xx += fm.horizontalAdvance(lab)
            p.setFont(fb)
            p.setPen(QColor(col))
            p.drawText(QRectF(xx, y, fmb.horizontalAdvance(val) + 2, fmb.height()), Qt.AlignmentFlag.AlignVCenter, val)
            xx += fmb.horizontalAdvance(val) + 26
        y += fmb.height() + 14
        p.setFont(base)
        lines = [(f"오늘의 기분: {d.get('mood', '')}", c['ink'])]
        if d.get('motto'):
            lines.append((d['motto'], c['ink']))
        for t, col in lines:
            p.setPen(QColor(col))
            _elide(p, QRectF(x, y, wv, fm.height()), t)
            y += fm.height() + 3
        p.setPen(QColor(c['muted']))
        t1 = '오늘 지출 '
        p.drawText(QRectF(x, y, fm.horizontalAdvance(t1) + 2, fm.height()), Qt.AlignmentFlag.AlignVCenter, t1)
        xx = x + fm.horizontalAdvance(t1)
        p.setPen(QColor(c['ink']))
        t2 = f"{fmt_money(d.get('texp', 0))}원 · "
        p.drawText(QRectF(xx, y, fm.horizontalAdvance(t2) + 2, fm.height()), Qt.AlignmentFlag.AlignVCenter, t2)
        xx += fm.horizontalAdvance(t2)
        p.setPen(QColor(c['muted']))
        t3 = '현재 잔액 '
        p.drawText(QRectF(xx, y, fm.horizontalAdvance(t3) + 2, fm.height()), Qt.AlignmentFlag.AlignVCenter, t3)
        xx += fm.horizontalAdvance(t3)
        p.setFont(fb)
        p.setPen(QColor(c['out'] if d.get('bal', 0) < 0 else c['ink']))
        p.drawText(QRectF(xx, y, 220, fm.height()), Qt.AlignmentFlag.AlignVCenter, f"{fmt_money(d.get('bal', 0))}원")
        p.end()


class PinnedPost(_Painted):
    """타임라인: 맨 위 고정된 글 (이달 요약)"""

    def __init__(self):
        super().__init__()
        self.d = {}

    def set_data(self, **d):
        self.d = d
        fm = QFontMetrics(self.font())
        self.setFixedHeight(14 + 20 + fm.height() + 3 * (fm.height() + 2) + 36 + 8)
        self.update()

    def paintEvent(self, _ev):
        c, d = self.colors(), self.d
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(c['page']))
        w = min(TW_W, self.width())
        x0 = (self.width() - w) / 2
        p.setPen(QPen(QColor(c['line']), 1))
        if w < self.width() - 2:
            p.drawLine(QPointF(x0, 0), QPointF(x0, self.height()))
            p.drawLine(QPointF(x0 + w, 0), QPointF(x0 + w, self.height()))
        p.drawLine(QPointF(x0, self.height() - 0.5), QPointF(x0 + w, self.height() - 0.5))
        base = QFont(self.font())
        fb, fs = _font(base, 1.0, True), _font(base, 0.86, True)
        fm, fmb = QFontMetrics(base), QFontMetrics(fb)
        cx, cw = x0 + 68, w - 82
        y = 12
        I.paint(p, QRectF(cx - 22, y + 2, 15, 15), 'pin', c['muted'])
        p.setFont(fs)
        p.setPen(QColor(c['muted']))
        p.drawText(QRectF(cx, y, cw, 20), Qt.AlignmentFlag.AlignVCenter, '고정된 글')
        y += 20
        draw_minimi(p, QRectF(x0 + 14, y, 42, 42), d.get('minimi', T.DEFAULT_MINIMI))
        p.setFont(fb)
        p.setPen(QColor(c['ink']))
        name = d.get('name', '')
        nw = min(fmb.horizontalAdvance(name), cw * 0.6)
        _elide(p, QRectF(cx, y, nw, fmb.height()), name)
        p.setFont(base)
        p.setPen(QColor(c['muted']))
        _elide(p, QRectF(cx + nw + 6, y, cw - nw - 6, fmb.height()), f"@{d.get('month', '')}월_요약 · {d.get('ym', '')}")
        y += fmb.height() + 2
        inc, exp, bal = d.get('inc', 0), d.get('exp', 0), d.get('bal', 0)
        rows = [[(f"{d.get('month', '')}월 수입 ", c['ink'], base), (f'{fmt_money(inc)}원', c['in'], fb), (', 지출 ', c['ink'], base),
                 (f'{fmt_money(exp)}원', c['out'], fb)],
                [('차액 ', c['ink'], base), (f'{fmt_money(inc - exp)}원', c['out'] if inc - exp < 0 else c['ink'], fb),
                 (' · 현재 잔액 ', c['ink'], base), (f'{fmt_money(bal)}원', c['out'] if bal < 0 else c['ink'], fb)],
                [(f"오늘의 기분: {d.get('mood', '')}", c['ink'], base)]]
        for parts in rows:
            xx = cx
            for t, col, f in parts:
                p.setFont(f)
                p.setPen(QColor(col))
                tw = QFontMetrics(f).horizontalAdvance(t)
                p.drawText(QRectF(xx, y, tw + 2, fm.height()), Qt.AlignmentFlag.AlignVCenter, t)
                xx += tw
            y += fm.height() + 2
        step = min(cw, 330) / 3.6
        p.setFont(_font(base, 0.88))
        for k, (ic, val, tip) in enumerate((('comment', d.get('n', 0), '내역'), ('heart', d.get('n_in', 0), '수입'),
                                            ('repeat', d.get('n_out', 0), '지출'), ('stats', fmt_money(d.get('texp', 0)), '오늘 지출'))):
            I.paint(p, QRectF(cx + step * k, y + 8, 19, 19), ic, c['muted'])
            p.setPen(QColor(c['muted']))
            p.drawText(QRectF(cx + step * k + 23, y + 6, step - 24, 23), Qt.AlignmentFlag.AlignVCenter, str(val))
        p.end()


class Highlights(_Painted):
    """피드: ＋새 내역 + 지출 많은 계정과목 동그라미 (누르면 그 계정으로 검색)"""
    SIZE = 66
    new_clicked = pyqtSignal()
    code_clicked = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.items = []                 # [(코드, 이름, 금액)]
        self.setFixedHeight(self.SIZE + 58)

    def set_items(self, items):
        self.items = items
        self.update()

    def on_hit(self, what, val):
        if what == 'new':
            self.new_clicked.emit()
        else:
            self.code_clicked.emit(val)

    def paintEvent(self, _ev):
        c = self.colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(c['page']))
        base = QFont(self.font())
        fs = _font(base, 0.86)
        fsb = _font(base, 0.82, True)
        fm, fmb = QFontMetrics(fs), QFontMetrics(fsb)
        slot = self.SIZE + 24
        x0 = max(16.0, (self.width() - POST_W - 60) / 2)
        x, y = x0, 10
        self.hits = []
        # ＋ 새 내역
        r = QRectF(x + 12, y, self.SIZE, self.SIZE)
        pen = QPen(QColor(c['line']), 1.5, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(r.adjusted(1, 1, -1, -1))
        I.paint(p, QRectF(r.center().x() - 14, r.center().y() - 14, 28, 28), 'add', c['ink'])
        p.setFont(fs)
        p.setPen(QColor(c['ink']))
        p.drawText(QRectF(x, y + self.SIZE + 4, slot, fm.height()), Qt.AlignmentFlag.AlignHCenter, '새 내역')
        self.hits.append((QRectF(x, y, slot, self.SIZE + 40), 'new', None))
        x += slot
        for code, label, v in self.items:
            if x + slot > self.width() - 8:
                break
            r = QRectF(x + 12, y, self.SIZE, self.SIZE)
            draw_avatar(p, r, label, c, ring=True)
            p.setFont(fs)
            p.setPen(QColor(c['ink']))
            p.drawText(QRectF(x, y + self.SIZE + 4, slot, fm.height()), Qt.AlignmentFlag.AlignHCenter,
                       fm.elidedText(label, Qt.TextElideMode.ElideRight, slot - 4))
            p.setFont(fsb)
            p.setPen(QColor(c['out']))
            p.drawText(QRectF(x, y + self.SIZE + 4 + fm.height(), slot, fmb.height()), Qt.AlignmentFlag.AlignHCenter, _man(v))
            self.hits.append((QRectF(x, y, slot, self.SIZE + 40), 'code', code))
            x += slot
        p.end()


class Trends(_Painted):
    """타임라인 오른쪽: 이 기간에 많이 쓴 곳 (누르면 그 계정으로 검색)"""
    code_clicked = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.items, self.title = [], ''

    def set_items(self, items, title):
        self.items, self.title = items[:4], title
        fm = QFontMetrics(self.font())
        self.setFixedHeight(16 + QFontMetrics(_font(self.font(), 1.3, True)).height() + 8
                            + len(self.items) * (fm.height() * 3 + 12) + 10 if self.items else 0)
        self.setVisible(bool(self.items))
        self.update()

    def on_hit(self, what, val):
        self.code_clicked.emit(val)

    def paintEvent(self, _ev):
        c = self.colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(QColor(c['line']), 1))
        p.setBrush(QColor(c['card']))
        p.drawRoundedRect(r, 16, 16)
        base = QFont(self.font())
        ft = _font(base, 1.3, True)
        fs, fb = _font(base, 0.82), _font(base, 1.0, True)
        p.setFont(ft)
        p.setPen(QColor(c['ink']))
        y = 12
        p.drawText(QRectF(16, y, r.width() - 32, QFontMetrics(ft).height()), Qt.AlignmentFlag.AlignVCenter, self.title)
        y += QFontMetrics(ft).height() + 8
        fm = QFontMetrics(base)
        self.hits = []
        for i, (code, label, v, cnt) in enumerate(self.items):
            h = fm.height() * 3 + 12
            self.hits.append((QRectF(1, y, r.width() - 2, h), 'code', code))
            p.setFont(fs)
            p.setPen(QColor(c['muted']))
            p.drawText(QRectF(16, y + 4, r.width() - 32, fm.height()), Qt.AlignmentFlag.AlignVCenter, f'{i + 1} · 지출 순위')
            p.setFont(fb)
            p.setPen(QColor(c['ink']))
            _elide(p, QRectF(16, y + 4 + fm.height(), r.width() - 32, fm.height()), '#' + label.replace(' ', ''))
            p.setFont(fs)
            p.setPen(QColor(c['muted']))
            p.drawText(QRectF(16, y + 4 + fm.height() * 2, r.width() - 32, fm.height()), Qt.AlignmentFlag.AlignVCenter,
                       f'{fmt_money(v)}원 · {cnt}건')
            y += h
        p.end()


class SnsTabs(_Painted):
    """탭 줄. style='feed': 아이콘+글자, 고른 탭 위에 선 / 'timeline': 글자, 고른 탭 아래 포인트색 막대"""
    clicked = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.items, self.kind = [], 'feed'       # [(열쇠, 아이콘, 글자, 켜짐, 탭인지)]

    def set_tabs(self, items, style):
        self.items, self.kind = items, style
        fm = QFontMetrics(self.font())
        self.setFixedHeight(fm.height() + (34 if style == 'feed' else 28))
        self.update()

    def on_hit(self, what, val):
        self.clicked.emit(val)

    def paintEvent(self, _ev):
        c = self.colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(c['page']))
        feed = self.kind == 'feed'
        w = min(POST_W if feed else TW_W, self.width() - (24 if feed else 0))
        x0 = (self.width() - w) / 2
        base = QFont(self.font())
        p.setPen(QPen(QColor(c['line']), 1))
        if feed:
            p.drawLine(QPointF(x0, 0.5), QPointF(x0 + w, 0.5))
        else:
            p.drawLine(QPointF(x0, self.height() - 0.5), QPointF(x0 + w, self.height() - 0.5))
            if w < self.width() - 2:
                p.drawLine(QPointF(x0, 0), QPointF(x0, self.height()))
                p.drawLine(QPointF(x0 + w, 0), QPointF(x0 + w, self.height()))
        tabs = [t for t in self.items if t[4]]
        extra = [t for t in self.items if not t[4]]
        tw = (w - 52 * len(extra)) / max(1, len(tabs))
        self.hits = []
        x = x0
        for key, ic, label, on, _is_tab in tabs:
            r = QRectF(x, 0, tw, self.height())
            self.hits.append((r, 'tab', key))
            col = QColor(c['ink'] if on else c['muted'])
            if feed:
                if on:
                    p.fillRect(QRectF(r.left(), 0, r.width(), 1.5), QColor(c['ink']))
                f = _font(base, 0.92, on)
                p.setFont(f)
                lw = QFontMetrics(f).horizontalAdvance(label)
                sx = r.center().x() - (lw + 24) / 2
                I.paint(p, QRectF(sx, r.center().y() - 9, 18, 18), ic, col, on)
                p.setPen(col)
                p.drawText(QRectF(sx + 24, 0, lw + 2, self.height()), Qt.AlignmentFlag.AlignVCenter, label)
            else:
                f = _font(base, 1.0, on)
                p.setFont(f)
                p.setPen(col)
                p.drawText(r.adjusted(0, 0, 0, -6), Qt.AlignmentFlag.AlignCenter, label)
                if on:
                    lw = QFontMetrics(f).horizontalAdvance(label)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(c['accent']))
                    p.drawRoundedRect(QRectF(r.center().x() - lw / 2 - 4, self.height() - 4, lw + 8, 4), 2, 2)
            x += tw
        for key, ic, label, on, _is_tab in extra:            # 정렬 같은 단추 (오른쪽 끝)
            r = QRectF(x, 0, 52, self.height())
            self.hits.append((r, 'tab', key))
            I.paint(p, QRectF(r.center().x() - 10, r.center().y() - 10, 20, 20), ic, c['accent'] if on else c['muted'], False, 2.2)
            x += 52
        p.end()
