"""선 아이콘 (피드·타임라인 테마) — 안드로이드판 ui.js 의 ICONS 와 같은 모양.

QtSvg 없이 그리도록 SVG 조각(path·circle·rect)을 직접 QPainterPath 로 바꾼다.
class="f" 인 부분은 '켜짐'(고른 메뉴 등)일 때 채우고, class="dot" 은 늘 채운다.
"""
import math
import re

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap

ICONS = {
    'home': '<path class="f" d="M3.5 10.2 12 3.3l8.5 6.9V19.6a1.4 1.4 0 0 1-1.4 1.4H15v-6.2H9V21H4.9a1.4 1.4 0 0 1-1.4-1.4z"/>',
    'search': '<circle cx="10.8" cy="10.8" r="7"/><path d="m20.5 20.5-4.7-4.7"/>',
    'plus': '<rect x="3" y="3" width="18" height="18" rx="5.5"/><path d="M12 7.8v8.4M7.8 12h8.4"/>',
    'add': '<path d="M12 4.5v15M4.5 12h15"/>',
    'heart': '<path class="f" d="M12 20.2s-7.6-4.6-9.3-9.3C1.5 7.6 3.7 4.4 7 4.4c2 0 3.4 1.1 5 3 1.6-1.9 3-3 5-3 3.3 0 5.5 3.2 4.3 6.5-1.7 4.7-9.3 9.3-9.3 9.3z"/>',
    'comment': '<path class="f" d="M20.6 11.6a8.6 8.6 0 0 1-12.4 7.7L3.4 20.6l1.4-4.6a8.6 8.6 0 1 1 15.8-4.4z"/>',
    'send': '<path d="M21.3 2.7 10.2 13.8"/><path class="f" d="M21.3 2.7 14.2 21l-4-7.2-7.3-4z"/>',
    'bookmark': '<path class="f" d="M6 3.2h12v17.6l-6-4.9-6 4.9z"/>',
    'calendar': '<rect x="3.2" y="4.6" width="17.6" height="16.4" rx="3"/><path d="M3.2 9.6h17.6M8 2.6v4M16 2.6v4"/>',
    'report': '<rect x="4.8" y="4" width="14.4" height="17" rx="2.6"/><path d="M9 4V2.8h6V4M8.6 10h6.8M8.6 13.8h6.8M8.6 17.6h4"/>',
    'wallet': '<path d="M4.5 7.4H19a2 2 0 0 1 2 2V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6.4A2.4 2.4 0 0 1 5.4 4H16.6v3.4"/><circle cx="16.4" cy="14.2" r="1.3"/>',
    'chart': '<path d="M3.5 20.5h17M7 17V11.5M12 17V6.5M17 17v-3.6"/>',
    'repeat': '<path d="M4.5 8 7.5 5l3 3M7.5 5.6V15a3 3 0 0 0 3 3h3M19.5 16l-3 3-3-3M16.5 18.4V9a3 3 0 0 0-3-3h-3"/>',
    'gift': '<rect x="3.4" y="8" width="17.2" height="4.4" rx="1"/><path d="M5 12.4V20a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-7.6M12 8v13M12 8S10.6 3.6 8.2 4.1 6.4 8 12 8zm0 0s1.4-4.4 3.8-3.9S17.6 8 12 8z"/>',
    'user': '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>',
    'book': '<path d="M4 4.6A1.6 1.6 0 0 1 5.6 3H20v15H5.6A1.6 1.6 0 0 0 4 19.6zM4 19.6A1.6 1.6 0 0 0 5.6 21H20v-3"/>',
    'note': '<path d="M5 3h10l4 4v14H5z"/><path d="M15 3v4h4M8.5 12h7M8.5 16h5"/>',
    'gear': '<path d="M19.25 10.53 L21.52 10.76 L21.52 13.24 L19.25 13.47 L18.17 16.09 L19.61 17.85 L17.85 19.61 L16.09 18.17 L13.47 19.25 L13.24 21.52 L10.76 21.52 L10.53 19.25 L7.91 18.17 L6.15 19.61 L4.39 17.85 L5.83 16.09 L4.75 13.47 L2.48 13.24 L2.48 10.76 L4.75 10.53 L5.83 7.91 L4.39 6.15 L6.15 4.39 L7.91 5.83 L10.53 4.75 L10.76 2.48 L13.24 2.48 L13.47 4.75 L16.09 5.83 L17.85 4.39 L19.61 6.15 L18.17 7.91Z"/><circle cx="12" cy="12" r="3"/>',
    'help': '<circle cx="12" cy="12" r="9"/><path d="M9.4 9.3a2.7 2.7 0 0 1 5.2.9c0 1.8-2.6 2.3-2.6 3.9M12 17.3v.1"/>',
    'dots': '<circle class="dot" cx="5" cy="12" r="1.5"/><circle class="dot" cx="12" cy="12" r="1.5"/><circle class="dot" cx="19" cy="12" r="1.5"/>',
    'more': '<circle cx="12" cy="12" r="9"/><circle class="dot" cx="7.8" cy="12" r="1.2"/><circle class="dot" cx="12" cy="12" r="1.2"/><circle class="dot" cx="16.2" cy="12" r="1.2"/>',
    'back': '<path d="M15 4.5 7.5 12l7.5 7.5"/>',
    'arrowleft': '<path d="M20 12H4.5M10.5 5.5 4 12l6.5 6.5"/>',
    'chevl': '<path d="M14.5 6 8.5 12l6 6"/>',
    'chevr': '<path d="M9.5 6l6 6-6 6"/>',
    'chevd': '<path d="m6 9.5 6 6 6-6"/>',
    'sort': '<path d="M8 4v16M4.5 7.5 8 4l3.5 3.5M16 20V4M12.5 16.5 16 20l3.5-3.5"/>',
    'download': '<path d="M12 3.5v11M7.5 10.5 12 15l4.5-4.5M4 17.5V20h16v-2.5"/>',
    'sliders': '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
    'bell': '<path class="f" d="M6 16.4V11a6 6 0 1 1 12 0v5.4l1.6 2.1H4.4z"/><path d="M10 21h4"/>',
    'pin': '<path d="M14.6 3.4 20.6 9.4l-2.5.9-3.7 3.7.4 4.4-2 2-3.6-3.6L4 21l3.2-5.2-3.6-3.6 2-2 4.4.4 3.7-3.7z"/>',
    'stats': '<path d="M5 20.5V13M10 20.5V7M15 20.5v-9M20 20.5V4"/>',
    'pen': '<path d="M4 20l1.1-4.2L16.3 4.6a2 2 0 0 1 2.8 0l.3.3a2 2 0 0 1 0 2.8L8.2 18.9z"/><path d="M14.5 6.4l3.1 3.1"/>',
    'grid': '<rect x="3.5" y="3.5" width="17" height="17" rx="2.5"/><path d="M9.2 3.5v17M14.8 3.5v17M3.5 9.2h17M3.5 14.8h17"/>',
    'all': '<path d="M7 9c-2.2 0-3.6 1.4-3.6 3S4.8 15 7 15c3.5 0 6.5-6 10-6 2.2 0 3.6 1.4 3.6 3S19.2 15 17 15c-3.5 0-6.5-6-10-6z"/>',
    'print': '<path d="M7 8V3.5h10V8"/><rect x="3.5" y="8" width="17" height="9" rx="2.2"/><path d="M7 13.5h10v7H7z"/>',
    'upload': '<path d="M12 15V4M7.5 8.5 12 4l4.5 4.5M4 17.5V20h16v-2.5"/>',
    'archive': '<rect x="3" y="4" width="18" height="5" rx="1.5"/><path d="M5 9v10a1.5 1.5 0 0 0 1.5 1.5h11A1.5 1.5 0 0 0 19 19V9M10 13h4"/>',
    'lock': '<rect x="4.5" y="10.5" width="15" height="10" rx="2.5"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
    'refresh': '<path d="M20 11a8 8 0 0 0-14.3-4.9L4 8M4 4v4h4M4 13a8 8 0 0 0 14.3 4.9L20 16M20 20v-4h-4"/>',
    'info': '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.6v.1"/>',
    'tag': '<path d="M3.5 12.2V4.5a1 1 0 0 1 1-1h7.7l8.3 8.3a1.5 1.5 0 0 1 0 2.1l-6.2 6.2a1.5 1.5 0 0 1-2.1 0z"/><circle class="dot" cx="8" cy="8" r="1.4"/>',
    'palette': '<path d="M12 3a9 9 0 1 0 0 18c1.2 0 1.8-.8 1.8-1.7 0-1.1-.9-1.6-.9-2.6 0-1 .8-1.7 1.8-1.7h2.1A4.2 4.2 0 0 0 21 10.8C21 6.5 17 3 12 3z"/><circle class="dot" cx="7.5" cy="11.5" r="1.3"/><circle class="dot" cx="10" cy="7.5" r="1.3"/><circle class="dot" cx="14.5" cy="7.5" r="1.3"/>',
    'table': '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M3.5 9.5h17M3.5 14.5h17M9.5 9.5v10"/>',
    'list': '<path d="M8.5 6.5h12M8.5 12h12M8.5 17.5h12"/><circle class="dot" cx="4.5" cy="6.5" r="1.2"/><circle class="dot" cx="4.5" cy="12" r="1.2"/><circle class="dot" cx="4.5" cy="17.5" r="1.2"/>',
}

_NUM = re.compile(r'[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?')
_TOK = re.compile(r'[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?')
_ELEM = re.compile(r'<(path|circle|rect)\b([^>]*)/?>')
_ATTR = re.compile(r'([\w-]+)="([^"]*)"')


def _arc(path, x1, y1, rx, ry, phi, fa, fs, x2, y2):
    """SVG 호(끝점 방식)를 QPainterPath.arcTo 로 (회전 없는 호만 씀)"""
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        path.lineTo(x2, y2)
        return
    rx, ry = abs(rx), abs(ry)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    lam = (dx * dx) / (rx * rx) + (dy * dy) / (ry * ry)
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * dy * dy - ry * ry * dx * dx
    den = rx * rx * dy * dy + ry * ry * dx * dx
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if fa == fs:
        co = -co
    cxp, cyp = co * rx * dy / ry, -co * ry * dx / rx
    cx, cy = cxp + (x1 + x2) / 2, cyp + (y1 + y2) / 2
    ang = lambda ux, uy, vx, vy: math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
    t1 = ang(1, 0, (dx - cxp) / rx, (dy - cyp) / ry)
    dt_ = ang((dx - cxp) / rx, (dy - cyp) / ry, (-dx - cxp) / rx, (-dy - cyp) / ry)
    if not fs and dt_ > 0:
        dt_ -= 2 * math.pi
    elif fs and dt_ < 0:
        dt_ += 2 * math.pi
    # 화면 좌표(y 아래)에서 SVG 각도는 시계 방향 → Qt 는 반시계가 양수
    path.arcTo(QRectF(cx - rx, cy - ry, 2 * rx, 2 * ry), -math.degrees(t1), -math.degrees(dt_))


def _path(d):
    p = QPainterPath()
    toks = _TOK.findall(d)
    i, cmd = 0, None
    x = y = sx = sy = 0.0
    lc = None                     # 직전 3차 곡선의 두 번째 조절점 (S 용)
    nums = lambda n: [float(t) for t in toks[i:i + n]]
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in 'Zz':
                p.closeSubpath()
                x, y = sx, sy
                lc = None
                continue
        rel = cmd.islower()
        c = cmd.upper()
        if c == 'M':
            a, b = nums(2)
            i += 2
            x, y = (x + a, y + b) if rel else (a, b)
            p.moveTo(x, y)
            sx, sy = x, y
            cmd = 'l' if rel else 'L'          # 뒤따르는 숫자는 선
            lc = None
        elif c == 'L':
            a, b = nums(2)
            i += 2
            x, y = (x + a, y + b) if rel else (a, b)
            p.lineTo(x, y)
            lc = None
        elif c == 'H':
            a, = nums(1)
            i += 1
            x = x + a if rel else a
            p.lineTo(x, y)
            lc = None
        elif c == 'V':
            a, = nums(1)
            i += 1
            y = y + a if rel else a
            p.lineTo(x, y)
            lc = None
        elif c == 'C':
            v = nums(6)
            i += 6
            if rel:
                v = [v[k] + (x if k % 2 == 0 else y) for k in range(6)]
            p.cubicTo(v[0], v[1], v[2], v[3], v[4], v[5])
            lc = (v[2], v[3])
            x, y = v[4], v[5]
        elif c == 'S':
            v = nums(4)
            i += 4
            if rel:
                v = [v[k] + (x if k % 2 == 0 else y) for k in range(4)]
            c1 = (2 * x - lc[0], 2 * y - lc[1]) if lc else (x, y)
            p.cubicTo(c1[0], c1[1], v[0], v[1], v[2], v[3])
            lc = (v[0], v[1])
            x, y = v[2], v[3]
        elif c == 'Q':
            v = nums(4)
            i += 4
            if rel:
                v = [v[k] + (x if k % 2 == 0 else y) for k in range(4)]
            p.quadTo(v[0], v[1], v[2], v[3])
            x, y = v[2], v[3]
            lc = None
        elif c == 'A':
            v = nums(7)
            i += 7
            ex, ey = (x + v[5], y + v[6]) if rel else (v[5], v[6])
            _arc(p, x, y, v[0], v[1], v[2], int(v[3]), int(v[4]), ex, ey)
            x, y = ex, ey
            lc = None
        else:
            i += 1                              # 모르는 명령은 건너뜀
    return p


_parsed = {}


def _parts(name):
    """[(QPainterPath, kind)] kind: 'line' | 'fill'(켜지면 채움) | 'dot'(늘 채움)"""
    if name not in _parsed:
        out = []
        for tag, attrs in _ELEM.findall(ICONS.get(name, ICONS['dots'])):
            a = dict(_ATTR.findall(attrs))
            kind = {'f': 'fill', 'dot': 'dot'}.get(a.get('class', ''), 'line')
            if tag == 'path':
                path = _path(a.get('d', ''))
            elif tag == 'circle':
                path = QPainterPath()
                r = float(a.get('r', 0))
                path.addEllipse(QPointF(float(a.get('cx', 0)), float(a.get('cy', 0))), r, r)
            else:
                path = QPainterPath()
                rx = float(a.get('rx', 0))
                path.addRoundedRect(QRectF(float(a.get('x', 0)), float(a.get('y', 0)), float(a.get('width', 0)),
                                           float(a.get('height', 0))), rx, rx)
            out.append((path, kind))
        _parsed[name] = out
    return _parsed[name]


def paint(p, rect, name, color, on=False, width=None):
    """rect 안에 아이콘 그리기 (24×24 기준 선 굵기 1.9, 켜짐이면 2.3 + 채움)"""
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = min(rect.width(), rect.height()) / 24.0
    p.translate(rect.center().x() - 12 * s, rect.center().y() - 12 * s)
    p.scale(s, s)
    col = QColor(color)
    pen = QPen(col, width or (2.3 if on else 1.9))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    for path, kind in _parts(name):
        if kind == 'dot':
            p.fillPath(path, col)
            continue
        if kind == 'fill' and on:
            p.fillPath(path, col)
        p.strokePath(path, pen)
    p.restore()


_pm_cache = {}


def pixmap(name, size, color, on=False, width=None, dpr=None):
    if dpr is None:
        app = QGuiApplication.instance()
        dpr = app.devicePixelRatio() if app else 1.0
    key = (name, size, str(color), on, width, dpr)
    if key not in _pm_cache:
        px = max(1, round(size * dpr))
        pm = QPixmap(px, px)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        paint(p, QRectF(0, 0, px, px), name, color, on, width)
        p.end()
        pm.setDevicePixelRatio(dpr)
        _pm_cache[key] = pm
    return _pm_cache[key]


def icon(name, size, color, on_color=None):
    """메뉴용 QIcon: 보통은 선, 고르면 채운 모양"""
    ic = QIcon()
    ic.addPixmap(pixmap(name, size, color), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(pixmap(name, size, on_color or color, on=True), QIcon.Mode.Selected, QIcon.State.Off)
    ic.addPixmap(pixmap(name, size, on_color or color, on=True), QIcon.Mode.Active, QIcon.State.On)
    return ic
