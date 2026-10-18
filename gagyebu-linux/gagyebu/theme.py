"""화면 테마 — '미니홈피'(2000년대 서브컬처 느낌) / '기본'.

- 색: 사용자가 준 고양이 스티커에서 뽑은 색 (배경 청록 #347C7C, 귀 하늘 #4BD5D5, 검은 외곽선, 흰 몸통)
- 글꼴: 갈무리11 (도트 글꼴, SIL OFL 1.1) — 12px(본문)·24px(제목)처럼 정수배에서 가장 또렷함
- 설정 값은 데이터 파일이 아니라 사용자 설정(~/.config/gagyebu-linux/)에 저장 → 자료를 가져오거나 복원해도 꾸미기는 유지
"""
import json
import os

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette, QPixmap
from PyQt6.QtWidgets import QApplication, QStyleFactory

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, 'assets')
STICKERS = os.path.join(ASSETS, 'stickers')
ICON = os.path.join(ASSETS, 'icon.png')
PIXEL_FAMILY = 'Galmuri11'

C = {
    'teal': '#347C7C', 'teal_dark': '#24595A', 'cyan': '#4BD5D5', 'cyan_dark': '#2BB5B5',
    'mint': '#B8EBE4', 'mint_pale': '#EAF9F7', 'mint_row': '#F0FBFA',
    'pink': '#FF8FB1', 'pink_dark': '#E0507A', 'pink_pale': '#FFE3EC',
    'yellow': '#FFE066', 'ink': '#1A1A1A', 'white': '#FFFFFF', 'dash': '#5CC6C6', 'grey': '#8A9A9A',
}

# 화면(클래스 이름) → (스티커, 한 줄 소개)
PAGE_DECOR = {
    'LedgerPage': ('a22', '들어오고 나간 돈 차곡차곡 ♪'),
    'SearchPage': ('b23', '그때 그 지출, 어디 갔지?'),
    'ReportsPage': ('b30', '한 달 성적표 두근두근'),
    'GraphPage': ('b26', '쑥쑥 크는 그래프 (^-^)'),
    'RecurringPage': ('b38', '매달 알아서 척척'),
    'AssetsPage': ('a04', '통장·카드·내 재산 한눈에'),
    'CalendarPage': ('b11', '기념일 잊지 말기 ☆'),
    'AddressPage': ('a13', '우리 일촌 연락처'),
    'DiaryPage': ('b33', '오늘 하루 끄적끄적'),
    'MemoPage': ('a19', '잊기 전에 메모!'),
    'SettingsPage': ('b08', '내 맘대로 꾸미기'),
}
LOGIN_STICKER = 'a01'
DEFAULT_MINIMI = 'b16'
MOODS = ['행복 (^-^)', '신남 (^0^)/', '알뜰 (-_-)b', '월급날 ♡(^_^)♡', '두근두근 (*^^*)',
         '텅장 (ㅠ_ㅠ)', '지름신 강림 (>_<)', '피곤 (-_-)zZ']

DEFAULTS = {'theme': 'retro', 'font': 'pixel', 'marquee': True, 'minimi': DEFAULT_MINIMI,
            'mood': MOODS[0], 'motto': '', 'profile_hidden': False}


# ── 사용자 설정 ──
def settings():
    return QSettings('gagyebu-linux', 'gagyebu')


def pref(key):
    v = settings().value(key, DEFAULTS[key])
    d = DEFAULTS[key]
    if isinstance(d, bool):
        return v if isinstance(v, bool) else str(v).lower() in ('1', 'true', 'yes')
    return str(v) if v is not None else d


def set_pref(key, value):
    s = settings()
    s.setValue(key, value)
    s.sync()


# ── 스티커 ──
_sticker_list = None
_pix_cache = {}


def sticker_list():
    """[{'id': 'a01', 'label': ''}, ...] — label 은 원본 시트에 적힌 이름"""
    global _sticker_list
    if _sticker_list is None:
        try:
            with open(os.path.join(STICKERS, 'stickers.json'), encoding='utf-8') as f:
                _sticker_list = [s for s in json.load(f)['stickers']
                                 if os.path.exists(os.path.join(STICKERS, s['id'] + '.png'))]
        except (OSError, ValueError, KeyError):
            _sticker_list = []
    return _sticker_list


def sticker_path(sid):
    p = os.path.join(STICKERS, f'{sid}.png')
    return p if os.path.exists(p) else os.path.join(STICKERS, f'{DEFAULT_MINIMI}.png')


def sticker_pixmap(sid, size, dpr=None):
    """size×size 상자 안에 비율 유지해 맞춘 그림 (고해상도 화면이면 그만큼 크게 만들어 선명하게)."""
    if dpr is None:
        app = QGuiApplication.instance()
        dpr = app.devicePixelRatio() if app else 1.0
    key = (sid, size, dpr)
    if key not in _pix_cache:
        pm = QPixmap(sticker_path(sid))
        if not pm.isNull():
            px = max(1, round(size * dpr))
            pm = pm.scaled(px, px, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
        _pix_cache[key] = pm
    return _pix_cache[key]


# ── 글꼴 ──
_font_family = None


def load_fonts():
    """갈무리11 등록. 성공하면 글꼴 이름, 실패하면 None (그때는 시스템 글꼴로)."""
    global _font_family
    if _font_family is None:
        fam = ''
        for f in ('Galmuri11.ttf', 'Galmuri11-Bold.ttf'):
            i = QFontDatabase.addApplicationFont(os.path.join(ASSETS, 'fonts', f))
            if i >= 0 and not fam:
                fams = QFontDatabase.applicationFontFamilies(i)
                fam = fams[0] if fams else ''
        _font_family = fam
    return _font_family or None


# ── 스타일시트 ──
def _url(name):
    return os.path.join(ASSETS, 'ui', name).replace('\\', '/')


RETRO_QSS = """
QMainWindow, QDialog, QMessageBox { background: %(mint_pale)s; }
QWidget { color: %(ink)s; }
QToolTip { background: #FFFDE7; color: %(ink)s; border: 2px solid %(ink)s; border-radius: 6px; padding: 3px 6px; }
QStatusBar { background: %(teal_dark)s; color: white; }
QStatusBar QLabel { color: white; }

/* ── 미니홈피 틀 ── */
QFrame#Hompy { background: white; border: 2px solid %(ink)s; border-radius: 16px; }
QFrame#ProfileBox { background: %(mint_pale)s; border: 1px dashed %(dash)s; border-radius: 10px; }
QFrame#MainBox { background: white; border: 1px dashed %(dash)s; border-radius: 10px; }
QFrame#MainBox QScrollArea, QFrame#MainBox QStackedWidget { background: transparent; }
QFrame#Banner { background: transparent; border: none; border-bottom: 2px dotted %(cyan)s; }
QLabel#BannerTitle { color: %(teal_dark)s; %(title_font)s }
QLabel#BannerSub { color: %(pink_dark)s; }
QLabel#BannerDeco { color: %(cyan_dark)s; }
QLabel#HompyTitle { color: white; %(title_font)s }
QLabel#HompyCaption { color: %(mint)s; }
QLabel#TodayLabel { background: white; border: 2px solid %(ink)s; border-radius: 10px; padding: 2px 10px; }
QLabel#LedgerLabel { color: white; font-weight: bold; }
QWidget#Marquee { background: white; border: 2px solid %(ink)s; border-radius: 10px; }
QLabel#Pill { background: %(pink)s; color: white; border: 2px solid %(ink)s; border-radius: 8px;
              padding: 1px 8px; font-weight: bold; }
QLabel#Minimi { background: white; border: 2px solid %(ink)s; border-radius: 12px; }
QLabel#ProfileInfo { color: %(ink)s; }
QLabel#ProfileFoot { color: %(grey)s; }
QFrame#Dotted { border: none; border-top: 1px dashed %(dash)s; max-height: 1px; }
QPushButton#Link { background: transparent; border: none; color: %(teal_dark)s; padding: 0; min-height: 0;
                   text-decoration: underline; }
QPushButton#Link:hover { color: %(pink_dark)s; background: transparent; }
QPushButton#Fold { padding: 0 4px; min-height: 0; border-radius: 6px; }
QLabel#LoginHint { color: %(pink_dark)s; }

/* 오른쪽 탭 (미니홈피 메뉴) */
QListWidget#TabNav { background: transparent; border: none; outline: none; }
QListWidget#TabNav::item { background: %(cyan)s; color: %(ink)s; border: 2px solid %(ink)s; border-left: none;
                           border-top-right-radius: 9px; border-bottom-right-radius: 9px;
                           padding: 6px 8px; margin: 0px 0px 4px 0px; }
QListWidget#TabNav::item:hover { background: %(pink_pale)s; }
QListWidget#TabNav::item:selected { background: white; color: %(pink_dark)s; }

/* ── 버튼: 2000년대 반짝이 버튼 ── */
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:0.49 #E4FAF8, stop:0.5 #C6F0EC, stop:1 %(mint)s);
    border: 2px solid %(ink)s; border-radius: 9px; padding: 3px 10px; min-height: 18px; }
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:0.49 #FFEEF3, stop:0.5 #FFD3E1, stop:1 #FFBCD0); }
QPushButton:pressed { background: %(pink)s; color: white; }
QPushButton:default { border-color: %(pink_dark)s; }
QPushButton:disabled { color: #9AA; border-color: #9AA; background: #EEF3F3; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 2px; }
QToolButton:hover { background: %(pink_pale)s; border-color: %(ink)s; }

/* ── 입력칸 ── */
QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox, QTextEdit, QPlainTextEdit {
    background: white; border: 2px solid %(ink)s; border-radius: 6px; padding: 2px 4px;
    selection-background-color: %(pink)s; selection-color: white; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QComboBox:focus,
QTextEdit:focus, QPlainTextEdit:focus { border-color: %(cyan_dark)s; background: #FFFFF4; }
QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled, QSpinBox:disabled { color: #8A9A9A; background: #F2F5F5; border-color: #9AA; }
QComboBox { padding-right: 20px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 18px;
    border-left: 2px solid %(ink)s; background: %(cyan)s; border-top-right-radius: 4px; border-bottom-right-radius: 4px; }
QComboBox::down-arrow { image: url("%(arrow_down)s"); width: 9px; height: 5px; }
QComboBox QAbstractItemView { background: white; border: 2px solid %(ink)s; selection-background-color: %(pink_pale)s;
    selection-color: %(ink)s; outline: none; }
QDateEdit { padding-right: 20px; }
QDateEdit::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 18px;
    border-left: 2px solid %(ink)s; background: %(cyan)s; border-top-right-radius: 4px; border-bottom-right-radius: 4px; }
QDateEdit::down-arrow { image: url("%(arrow_down)s"); width: 9px; height: 5px; }
QSpinBox, QDoubleSpinBox { padding-right: 18px; }
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 16px;
    border-left: 2px solid %(ink)s; border-bottom: 1px solid %(ink)s; background: %(cyan)s; border-top-right-radius: 4px; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 16px;
    border-left: 2px solid %(ink)s; background: %(cyan)s; border-bottom-right-radius: 4px; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover { background: %(pink_pale)s; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url("%(arrow_up)s"); width: 9px; height: 5px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url("%(arrow_down)s"); width: 9px; height: 5px; }

/* ── 표 ── */
QTableView, QTableWidget, QTreeView, QTreeWidget, QListView, QListWidget {
    background: white; alternate-background-color: %(mint_row)s; border: 2px solid %(ink)s; border-radius: 6px;
    gridline-color: #CBEDEA; selection-background-color: #FFD1DF; selection-color: %(ink)s; }
QHeaderView { background: transparent; }
QHeaderView::section { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8FE6E6, stop:1 %(cyan)s);
    border: none; border-right: 1px solid %(cyan_dark)s; border-bottom: 2px solid %(ink)s;
    padding: 3px 5px; font-weight: bold; }
QHeaderView::section:vertical { border-right: 2px solid %(ink)s; border-bottom: 1px solid %(cyan_dark)s; }
QTableCornerButton::section { background: %(cyan)s; border: none; border-right: 2px solid %(ink)s; border-bottom: 2px solid %(ink)s; }

/* ── 묶음 상자: 점선 + 분홍 이름표 ── */
QGroupBox { background: #F8FFFE; border: 2px dashed %(dash)s; border-radius: 10px; margin-top: 16px; padding: 12px 8px 8px 8px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 12px; top: 2px; padding: 1px 8px;
    background: %(pink)s; color: white; border: 2px solid %(ink)s; border-radius: 7px; }

/* ── 탭 ── */
QTabWidget::pane { background: white; border: 2px solid %(ink)s; border-radius: 8px; top: -2px; }
QTabBar::tab { background: %(mint)s; border: 2px solid %(ink)s; border-bottom: none; border-top-left-radius: 9px;
    border-top-right-radius: 9px; padding: 4px 12px; margin-right: 3px; margin-top: 3px; }
QTabBar::tab:selected { background: white; color: %(pink_dark)s; margin-top: 0px; padding-bottom: 6px; }
QTabBar::tab:hover:!selected { background: %(pink_pale)s; }

/* ── 스크롤바 ── */
QScrollBar:vertical { background: %(mint_pale)s; width: 14px; margin: 0; border: none; }
QScrollBar::handle:vertical { background: %(cyan)s; border: 2px solid %(ink)s; border-radius: 6px; min-height: 26px; }
QScrollBar:horizontal { background: %(mint_pale)s; height: 14px; margin: 0; border: none; }
QScrollBar::handle:horizontal { background: %(cyan)s; border: 2px solid %(ink)s; border-radius: 6px; min-width: 26px; }
QScrollBar::handle:hover { background: %(pink)s; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; background: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

QSplitter::handle { background: transparent; }
QSplitter::handle:hover { background: %(mint)s; }
QMenu { background: white; border: 2px solid %(ink)s; padding: 3px; }
QMenu::item { padding: 4px 18px; border-radius: 4px; }
QMenu::item:selected { background: %(pink_pale)s; color: %(ink)s; }
QCalendarWidget QWidget#qt_calendar_navigationbar { background: %(cyan)s; }
QCalendarWidget QToolButton { color: %(ink)s; font-weight: bold; }
QCalendarWidget QAbstractItemView { selection-background-color: %(pink)s; selection-color: white; border: none; }

QLabel#MonthLabel { %(month_font)s }
QLabel#DayLabel { font-weight: bold; }
QLabel#SumLabel { background: %(mint_pale)s; border: 2px dashed %(dash)s; border-radius: 10px; padding: 8px; }
"""

BASIC_QSS = """
QListWidget#TabNav { font-size: 11pt; }
QListWidget#TabNav::item { padding: 7px 6px; }
QLabel#MonthLabel { font-weight: bold; font-size: 12pt; }
QLabel#DayLabel { font-weight: bold; font-size: 12pt; }
QLabel#SumLabel { background: #eef4fb; padding: 8px; border-radius: 4px; }
"""


def retro_qss(pixel):
    v = dict(C)
    v['arrow_down'] = _url('arrow-down.png')
    v['arrow_up'] = _url('arrow-up.png')
    if pixel:
        v['title_font'] = f'font-family: "{PIXEL_FAMILY}"; font-size: 24px; font-weight: bold;'
        v['month_font'] = f'font-family: "{PIXEL_FAMILY}"; font-size: 24px; font-weight: bold; color: {C["teal_dark"]};'
    else:
        v['title_font'] = 'font-size: 16pt; font-weight: bold;'
        v['month_font'] = f'font-size: 13pt; font-weight: bold; color: {C["teal_dark"]};'
    return RETRO_QSS % v


def retro_palette():
    p = QPalette()
    g = {QPalette.ColorRole.Window: C['mint_pale'], QPalette.ColorRole.WindowText: C['ink'],
         QPalette.ColorRole.Base: '#FFFFFF', QPalette.ColorRole.AlternateBase: C['mint_row'],
         QPalette.ColorRole.Text: C['ink'], QPalette.ColorRole.Button: C['mint'],
         QPalette.ColorRole.ButtonText: C['ink'], QPalette.ColorRole.Highlight: C['pink'],
         QPalette.ColorRole.HighlightedText: '#FFFFFF', QPalette.ColorRole.ToolTipBase: '#FFFDE7',
         QPalette.ColorRole.ToolTipText: C['ink'], QPalette.ColorRole.PlaceholderText: C['grey'],
         QPalette.ColorRole.Link: C['teal_dark'], QPalette.ColorRole.BrightText: C['pink_dark'],
         QPalette.ColorRole.Light: '#FFFFFF', QPalette.ColorRole.Midlight: C['mint_pale'],
         QPalette.ColorRole.Mid: C['dash'], QPalette.ColorRole.Dark: C['teal'], QPalette.ColorRole.Shadow: C['ink']}
    for role, col in g.items():
        p.setColor(role, QColor(col))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor('#8A9A9A'))
    return p


def current():
    """지금 적용할 (테마, 도트글꼴 사용 여부)"""
    theme = pref('theme')
    theme = theme if theme in ('retro', 'basic') else 'retro'
    pixel = theme == 'retro' and pref('font') == 'pixel' and load_fonts() is not None
    return theme, pixel


def apply(app=None):
    """앱 전체에 테마 적용. 처음 부를 때 원래 스타일·팔레트·글꼴을 기억해 '기본'으로 되돌릴 수 있게 함."""
    app = app or QApplication.instance()
    if not hasattr(app, '_gb_orig'):
        app._gb_orig = (app.style().name(), QPalette(app.palette()), QFont(app.font()))
    style0, pal0, font0 = app._gb_orig
    theme, pixel = current()
    if theme == 'retro':
        fusion = QStyleFactory.create('Fusion')
        if fusion is not None:
            app.setStyle(fusion)
        app.setPalette(retro_palette())
        if pixel:
            f = QFont(PIXEL_FAMILY)
            f.setPixelSize(12)
            f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
            app.setFont(f)
        else:
            app.setFont(font0)
        app.setStyleSheet(retro_qss(pixel))
    else:
        st = QStyleFactory.create(style0)
        if st is not None:
            app.setStyle(st)
        app.setPalette(pal0)
        app.setFont(font0)
        app.setStyleSheet(BASIC_QSS)
    _pix_cache.clear()
    return theme, pixel
