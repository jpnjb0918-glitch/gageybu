"""'미니홈피' 테마 장식: 배경, 프로필(미니미·오늘의 기분·다짐), 화면 제목 띠, 전광판, 스티커 고르기."""
import datetime as dt
import random

from PyQt6.QtCore import QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter
from PyQt6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel, QListView,
                             QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton, QSizePolicy, QVBoxLayout,
                             QWidget)

from .. import theme as T

WEEK = '월화수목금토일'


class Backdrop(QWidget):
    """창 바탕: 미니홈피 테마면 청록 + 물방울 점 + 도트 반짝이, 기본 테마면 아무것도 그리지 않음."""

    def __init__(self):
        super().__init__()
        self.retro = False
        rnd = random.Random(2009)
        self.sparkles = [(rnd.random(), rnd.random(), rnd.choice((2, 3)), rnd.random() < 0.7) for _ in range(28)]

    def paintEvent(self, _ev):
        if not self.retro:
            return
        p = QPainter(self)
        W, H = self.width(), self.height()
        p.fillRect(self.rect(), QColor(T.C['teal']))
        dot = QColor(T.C['dot'])
        for y in range(8, H, 16):
            for x in range(8 + (8 if (y // 16) % 2 else 0), W, 16):
                p.fillRect(x, y, 2, 2, dot)
        for fx, fy, s, yellow in self.sparkles:          # 도트 반짝이 (+ 모양)
            x, y = int(fx * W), int(fy * H)
            col = QColor(T.C['yellow'] if yellow else '#FFFFFF')
            p.fillRect(x - s, y - 3 * s, 2 * s, 6 * s + 1, col)
            p.fillRect(x - 3 * s, y - s, 6 * s + 1, 2 * s, col)
        p.end()


class Marquee(QWidget):
    """2000년대 홈페이지의 흐르는 글씨(전광판). 마우스를 올리면 멈춤."""

    def __init__(self):
        super().__init__()
        self.setObjectName('Marquee')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.text = ''
        self.offset = 0
        self.running = True
        self.hover = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.setMinimumWidth(220)
        self.setFixedHeight(26)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_text(self, text):
        if text != self.text:
            self.text = text
            self.offset = 0
            self.update()

    def set_running(self, on):
        self.running = on
        if on and self.isVisible():
            self.timer.start(40)
        else:
            self.timer.stop()
            self.offset = 0
        self.update()

    def showEvent(self, ev):
        if self.running:
            self.timer.start(40)
        super().showEvent(ev)

    def hideEvent(self, ev):
        self.timer.stop()
        super().hideEvent(ev)

    def enterEvent(self, ev):
        self.hover = True
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self.hover = False
        super().leaveEvent(ev)

    def _tick(self):
        if not self.hover:
            self.offset += 1
            self.update()

    def paintEvent(self, ev):
        super().paintEvent(ev)                           # 스타일시트 배경·테두리
        p = QPainter(self)
        p.setClipRect(self.rect().adjusted(6, 2, -6, -2))
        p.setPen(QColor(T.C['ink']))
        fm = p.fontMetrics()
        unit = self.text + '        '
        w = max(1, fm.horizontalAdvance(unit))
        y = (self.height() + fm.ascent() - fm.descent()) // 2
        if not self.running:
            p.drawText(8, y, self.text)
            return
        x = 8 - (self.offset % w)
        while x < self.width():
            p.drawText(x, y, unit)
            x += w
        p.end()


class PageBanner(QFrame):
    """화면 위 제목 띠: [스티커] 화면 이름  ‥ 한 줄 소개 ‥"""

    def __init__(self):
        super().__init__()
        self.setObjectName('Banner')
        self.pic = QLabel()
        self.pic.setFixedSize(48, 48)
        self.pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title = QLabel()
        self.title.setObjectName('BannerTitle')
        self.sub = QLabel()
        self.sub.setObjectName('BannerSub')
        self.deco = QLabel('☆ ‥‥‥‥‥‥ ★')
        self.deco.setObjectName('BannerDeco')
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 6, 4)
        lay.addWidget(self.pic)
        lay.addWidget(self.title)
        lay.addSpacing(10)
        lay.addWidget(self.sub, 0, Qt.AlignmentFlag.AlignBottom)
        lay.addStretch(1)
        lay.addWidget(self.deco, 0, Qt.AlignmentFlag.AlignBottom)

    def set_page(self, page):
        sid, sub = T.PAGE_DECOR.get(type(page).__name__, (T.DEFAULT_MINIMI, ''))
        self.pic.setPixmap(T.sticker_pixmap(sid, 46))
        self.title.setText(page.title)
        self.sub.setText(sub)


class ClickLabel(QLabel):
    clicked = pyqtSignal()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(ev)


class StickerPicker(QDialog):
    """미니미(프로필 그림) 고르기."""

    def __init__(self, parent, current=None):
        super().__init__(parent)
        self.setWindowTitle('미니미 고르기')
        self.resize(720, 560)
        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setIconSize(QSize(88, 88))
        self.list.setGridSize(QSize(108, 108))
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setUniformItemSizes(True)
        for s in T.sticker_list():
            pm = T.sticker_pixmap(s['id'], 88)
            ic = QIcon(pm)
            ic.addPixmap(pm, QIcon.Mode.Selected)
            it = QListWidgetItem(ic, '')
            it.setData(Qt.ItemDataRole.UserRole, s['id'])
            it.setToolTip(f"{s['id']}" + (f"  (원본 표기: {s['label']})" if s['label'] else ''))
            self.list.addItem(it)
            if s['id'] == current:
                self.list.setCurrentItem(it)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        rnd = bb.addButton('아무거나 ♪', QDialogButtonBox.ButtonRole.ActionRole)
        rnd.clicked.connect(self._random)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel('♡ 프로필에 둘 미니미를 골라 주세요 (두 번 누르면 바로 선택)'))
        lay.addWidget(self.list, 1)
        lay.addWidget(bb)

    def _random(self):
        if self.list.count():
            self.list.setCurrentRow(random.randrange(self.list.count()))

    def selected(self):
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None


class ProfilePanel(QFrame):
    """왼쪽 프로필: 미니미, 오늘의 기분, 잔액·이달 수입/지출, 이번 달 다짐. 접기(◀)/펴기(▶)."""
    motto_changed = pyqtSignal()

    def __init__(self, mw):
        super().__init__()
        self.mw = mw
        self.setObjectName('ProfileBox')
        self.full = QWidget()
        self.mini = QWidget()
        # ── 펼친 모양 ──
        head = QLabel('♡ PROFILE')
        head.setObjectName('Pill')
        fold = QPushButton('◀')
        fold.setObjectName('Fold')
        fold.setToolTip('프로필 접기')
        fold.setFixedWidth(26)
        fold.clicked.connect(lambda: self.set_hidden(True))
        self.minimi = ClickLabel()
        self.minimi.setObjectName('Minimi')
        self.minimi.setFixedSize(150, 136)
        self.minimi.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.minimi.setCursor(Qt.CursorShape.PointingHandCursor)
        self.minimi.setToolTip('눌러서 미니미 바꾸기')
        self.minimi.clicked.connect(self.pick_minimi)
        change = QPushButton('♡ 미니미 바꾸기')
        change.setObjectName('Link')
        change.setCursor(Qt.CursorShape.PointingHandCursor)
        change.clicked.connect(self.pick_minimi)
        self.mood = QComboBox()
        self.mood.addItems(T.MOODS)
        self.mood.currentTextChanged.connect(lambda t: T.set_pref('mood', t))
        self.info = QLabel()
        self.info.setObjectName('ProfileInfo')
        self.info.setTextFormat(Qt.TextFormat.RichText)
        self.motto = QPlainTextEdit()
        self.motto.setPlaceholderText('이번 달 다짐을 적어 보세요 ^^\n(예: 커피는 하루 한 잔!)')
        self.motto.setMaximumHeight(78)
        self._motto_timer = QTimer(self)
        self._motto_timer.setSingleShot(True)
        self._motto_timer.timeout.connect(self._save_motto)
        self.motto.textChanged.connect(lambda: self._motto_timer.start(600))
        foot = QLabel('since 2009 ♡')
        foot.setObjectName('ProfileFoot')
        fl = QVBoxLayout(self.full)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(6)
        fl.addLayout(_row(head, 'stretch', fold))
        fl.addWidget(self.minimi, 0, Qt.AlignmentFlag.AlignHCenter)
        fl.addWidget(change, 0, Qt.AlignmentFlag.AlignHCenter)
        fl.addWidget(_caption('TODAY IS..'))
        fl.addWidget(self.mood)
        fl.addWidget(_dotted())
        fl.addWidget(self.info)
        fl.addWidget(_dotted())
        fl.addWidget(_caption('♣ 이번 달 다짐'))
        fl.addWidget(self.motto)
        fl.addStretch(1)
        fl.addWidget(foot, 0, Qt.AlignmentFlag.AlignHCenter)
        # ── 접은 모양 ──
        unfold = QPushButton('▶')
        unfold.setObjectName('Fold')
        unfold.setToolTip('프로필 펴기')
        unfold.setFixedWidth(26)
        unfold.clicked.connect(lambda: self.set_hidden(False))
        ml = QVBoxLayout(self.mini)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(unfold)
        ml.addStretch(1)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.addWidget(self.full)
        lay.addWidget(self.mini)
        self.load_prefs()

    def load_prefs(self):
        self.minimi.setPixmap(T.sticker_pixmap(T.pref('minimi'), 124))
        self.mood.blockSignals(True)
        m = T.pref('mood')
        if self.mood.findText(m) < 0:
            m = T.MOODS[0]
        self.mood.setCurrentText(m)
        self.mood.blockSignals(False)
        if self.motto.toPlainText() != T.pref('motto'):
            self.motto.blockSignals(True)
            self.motto.setPlainText(T.pref('motto'))
            self.motto.blockSignals(False)
        self.set_hidden(T.pref('profile_hidden'), save=False)

    def set_hidden(self, hidden, save=True):
        self.full.setVisible(not hidden)
        self.mini.setVisible(hidden)
        self.setFixedWidth(46 if hidden else 176)
        if save:
            T.set_pref('profile_hidden', bool(hidden))

    def pick_minimi(self):
        dlg = StickerPicker(self, T.pref('minimi'))
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected():
            T.set_pref('minimi', dlg.selected())
            self.minimi.setPixmap(T.sticker_pixmap(dlg.selected(), 124))

    def _save_motto(self):
        T.set_pref('motto', self.motto.toPlainText().strip())
        self.motto_changed.emit()

    def set_numbers(self, ledger, bal, inc, exp):
        t = dt.date.today()
        pink, teal = T.C['pink_dark'], T.C['teal_dark']
        self.info.setText(
            f"<div style='line-height:150%'>"
            f"◈ {t:%Y.%m.%d} ({WEEK[t.weekday()]})<br>"
            f"<b>♡ {_esc(ledger)}</b><br>"
            f"♥ 잔액 <b style='color:{teal}'>{bal}</b>원<br>"
            f"♥ 이달 수입 <span style='color:#1d5fbf'>{inc}</span>원<br>"
            f"♥ 이달 지출 <span style='color:{pink}'>{exp}</span>원</div>")


def _esc(s):
    import html
    return html.escape(s or '')


def _row(*ws):
    lay = QHBoxLayout()
    lay.setContentsMargins(0, 0, 0, 0)
    for w in ws:
        if w == 'stretch':
            lay.addStretch(1)
        else:
            lay.addWidget(w)
    return lay


def _caption(text):
    lab = QLabel(text)
    lab.setStyleSheet(f"color:{T.C['teal_dark']};font-weight:bold")
    return lab


def _dotted():
    f = QFrame()
    f.setObjectName('Dotted')
    f.setFixedHeight(1)
    return f


def today_html(today_exp, month_exp):
    """싸이월드 'TODAY 12 | TOTAL 3456' 처럼 — 오늘 지출 | 이달 지출"""
    c = T.sns_colors()
    a, sep, b = (c['accent'], c['muted'], c['accent']) if c else (T.C['pink_dark'], T.C['grey'], T.C['teal_dark'])
    return (f"<span style='color:{a};font-weight:bold'>TODAY</span> {today_exp}"
            f" <span style='color:{sep}'>|</span> "
            f"<span style='color:{b};font-weight:bold'>이달</span> {month_exp}")
