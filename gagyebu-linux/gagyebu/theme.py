"""화면 테마 — '미니홈피'(2000년대 서브컬처 느낌) / '기본'.

- 색: 사용자가 준 고양이 스티커에서 뽑은 색 (배경 청록 #347C7C, 귀 하늘 #4BD5D5, 검은 외곽선, 흰 몸통)
- 글꼴: 갈무리11 (도트 글꼴, SIL OFL 1.1) — 12px(본문)·24px(제목)처럼 정수배에서 가장 또렷함
- 설정 값은 데이터 파일이 아니라 사용자 설정(~/.config/gagyebu-linux/)에 저장 → 자료를 가져오거나 복원해도 꾸미기는 유지
"""
import json
import lzma
import os

from PyQt6.QtCore import QByteArray, QSettings, Qt
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
    'pink': '#FF8FB1', 'pink_dark': '#E0507A', 'pink_pale': '#FFE3EC', 'pink_text': '#C93F68',
    'yellow': '#FFE066', 'ink': '#1A1A1A', 'white': '#FFFFFF', 'dash': '#5CC6C6', 'grey': '#8A9A9A',
    'card': '#FFFFFF', 'on_bg': '#FFFFFF', 'caption': '#E3F6F3', 'dot': '#3F8D8D',
}
C_DEFAULT = dict(C)          # 색 바꾸기를 되돌릴 때 쓰는 원래 색 (C 는 그 자리에서 바뀜)

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


def _font_cache_dir():
    from PyQt6.QtCore import QStandardPaths
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericCacheLocation) or \
        os.path.join(os.path.expanduser('~'), '.cache')
    return os.path.join(base, 'gagyebu-linux', 'fonts')


def _add_font(name):
    """assets/fonts 의 글꼴 등록. 'name.xz'(xz 로 줄인 파일)만 있으면 처음 한 번 풀어 사용자 캐시 폴더에 두고 그 파일로 등록
    (글꼴 7개 23.7MB → 설치 2.6MB, 다음부터는 원래처럼 바로 읽힘). 캐시에 못 쓰면 메모리에서 바로 등록.
    성공하면 글꼴 번호, 실패하면 -1"""
    path = os.path.join(ASSETS, 'fonts', name)
    if not os.path.exists(path + '.xz'):
        return QFontDatabase.addApplicationFont(path)
    try:
        st = os.stat(path + '.xz')
        cached = os.path.join(_font_cache_dir(), f'{st.st_size}-{name}')       # 글꼴 파일이 바뀌면 크기로 구분
        if os.path.exists(cached):
            i = QFontDatabase.addApplicationFont(cached)
            if i >= 0:
                return i
        with open(path + '.xz', 'rb') as f:
            data = lzma.decompress(f.read())
    except (OSError, lzma.LZMAError):
        return -1
    try:
        os.makedirs(os.path.dirname(cached), exist_ok=True)
        tmp = cached + '.part'
        with open(tmp, 'wb') as f:
            f.write(data)
        os.replace(tmp, cached)
    except OSError:
        pass
    return QFontDatabase.addApplicationFontFromData(QByteArray(data))


def load_fonts():
    """갈무리11 등록. 성공하면 글꼴 이름, 실패하면 None (그때는 시스템 글꼴로)."""
    global _font_family
    if _font_family is None:
        fam = ''
        for f in ('Galmuri11.ttf', 'Galmuri11-Bold.ttf'):
            i = _add_font(f)
            if i >= 0 and not fam:
                fams = QFontDatabase.applicationFontFamilies(i)
                fam = fams[0] if fams else ''
        _font_family = fam
    return _font_family or None


# 고를 수 있는 한글 글꼴 (모두 SIL OFL 1.1 무료 글꼴, assets/fonts) — 안드로이드판 app.css 와 같은 글꼴
EXTRA_FONTS = {
    'gowun': ('고운돋움 (부드러운 글씨)', 'GowunDodum-Regular.ttf'),
    'jua': ('주아 (동글동글)', 'Jua-Regular.ttf'),
    'gaegu': ('개구 (손글씨)', 'Gaegu-Regular.ttf'),
    'poorstory': ('서툰이야기 (손글씨)', 'PoorStory-Regular.ttf'),
}
_extra_family = {}


def extra_family(key):
    """추가 글꼴 등록 후 글꼴 이름 (없거나 실패하면 None)"""
    if key not in EXTRA_FONTS:
        return None
    if key not in _extra_family:
        i = _add_font(EXTRA_FONTS[key][1])
        fams = QFontDatabase.applicationFontFamilies(i) if i >= 0 else []
        _extra_family[key] = fams[0] if fams else ''
    return _extra_family[key] or None


def _font_for(font0):
    """설정한 추가 글꼴이 있으면 그 글꼴 (크기는 그대로), 아니면 font0"""
    fam = extra_family(pref('font'))
    if not fam:
        return font0
    f = QFont(font0)
    f.setFamily(fam)
    f.setFamilies([fam] + [x for x in font0.families() if x != fam])     # 글꼴에 없는 글자는 원래 글꼴로
    return f


_logo_family = None


def logo_family():
    """피드 테마 손글씨 로고 글꼴 (나눔손글씨 펜 — '우리집 가계부' 글자만 담은 작은 파일, SIL OFL 1.1)"""
    global _logo_family
    if _logo_family is None:
        i = _add_font('NanumPenScript-logo.ttf')
        fams = QFontDatabase.applicationFontFamilies(i) if i >= 0 else []
        _logo_family = fams[0] if fams else ''
    return _logo_family or None


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
QFrame#Hompy { background: %(card)s; border: 2px solid %(ink)s; border-radius: 16px; }
QFrame#ProfileBox { background: %(mint_pale)s; border: 1px dashed %(dash)s; border-radius: 10px; }
QFrame#MainBox { background: %(card)s; border: 1px dashed %(dash)s; border-radius: 10px; }
QFrame#MainBox QScrollArea, QFrame#MainBox QStackedWidget { background: transparent; }
QFrame#Banner { background: transparent; border: none; border-bottom: 2px dotted %(cyan)s; }
QLabel#BannerTitle { color: %(teal_dark)s; %(title_font)s }
QLabel#BannerSub { color: %(pink_text)s; }
QLabel#BannerDeco { color: %(cyan_dark)s; }
QLabel#HompyTitle { color: %(on_bg)s; %(title_font)s }
QLabel#HompyCaption { color: %(caption)s; }
QLabel#TodayLabel { background: %(card)s; border: 2px solid %(ink)s; border-radius: 10px; padding: 2px 10px; }
QLabel#LedgerLabel { color: %(on_bg)s; font-weight: bold; }
QWidget#Marquee { background: %(card)s; border: 2px solid %(ink)s; border-radius: 10px; }
QLabel#Pill { background: %(pink)s; color: %(ink)s; border: 2px solid %(ink)s; border-radius: 8px;
              padding: 1px 8px; font-weight: bold; }
QLabel#Minimi { background: %(card)s; border: 2px solid %(ink)s; border-radius: 12px; }
QLabel#ProfileInfo { color: %(ink)s; }
QLabel#ProfileFoot { color: %(grey)s; }
QFrame#Dotted { border: none; border-top: 1px dashed %(dash)s; max-height: 1px; }
QPushButton#Link { background: transparent; border: none; color: %(teal_dark)s; padding: 0; min-height: 0;
                   text-decoration: underline; }
QPushButton#Link:hover { color: %(pink_text)s; background: transparent; }
QPushButton#Fold { padding: 0 4px; min-height: 0; border-radius: 6px; }
QLabel#LoginHint { color: %(pink_text)s; }
QLabel[tone="note"] { color: #5F7373; }
QLabel[tone="warn"] { color: %(pink_text)s; font-weight: bold; }

/* 오른쪽 탭 (미니홈피 메뉴) */
QListWidget#TabNav { background: transparent; border: none; outline: none; }
QListWidget#TabNav::item { background: %(cyan)s; color: %(ink)s; border: 2px solid %(ink)s; border-left: none;
                           border-top-right-radius: 9px; border-bottom-right-radius: 9px;
                           padding: 6px 8px; margin: 0px 0px 4px 0px; }
QListWidget#TabNav::item:hover { background: %(pink_pale)s; }
QListWidget#TabNav::item:selected { background: %(card)s; color: %(pink_text)s; font-weight: bold; }

/* ── 버튼: 2000년대 반짝이 버튼 ── */
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:0.49 #E4FAF8, stop:0.5 #C6F0EC, stop:1 %(mint)s);
    border: 2px solid %(ink)s; border-radius: 9px; padding: 3px 10px; min-height: 18px; }
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FFFFFF, stop:0.49 #FFEEF3, stop:0.5 #FFD3E1, stop:1 #FFBCD0); }
QPushButton:pressed { background: %(pink)s; color: %(ink)s; }
QPushButton:default { border-color: %(pink_dark)s; }
QPushButton:disabled { color: #9AA; border-color: #9AA; background: #EEF3F3; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 2px; }
QToolButton:hover { background: %(pink_pale)s; border-color: %(ink)s; }

/* ── 입력칸 ── */
QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox, QTextEdit, QPlainTextEdit {
    background: %(card)s; border: 2px solid %(ink)s; border-radius: 6px; padding: 2px 4px;
    selection-background-color: %(pink)s; selection-color: %(ink)s; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QComboBox:focus,
QTextEdit:focus, QPlainTextEdit:focus { border-color: %(cyan_dark)s; background: #FFFFF4; }
QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled, QSpinBox:disabled { color: #8A9A9A; background: #F2F5F5; border-color: #9AA; }
QComboBox { padding-right: 20px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 18px;
    border-left: 2px solid %(ink)s; background: %(cyan)s; border-top-right-radius: 4px; border-bottom-right-radius: 4px; }
QComboBox::down-arrow { image: url("%(arrow_down)s"); width: 9px; height: 5px; }
QComboBox QAbstractItemView { background: %(card)s; border: 2px solid %(ink)s; selection-background-color: %(pink_pale)s;
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
    background: %(card)s; alternate-background-color: %(mint_row)s; border: 2px solid %(ink)s; border-radius: 6px;
    gridline-color: #CBEDEA; selection-background-color: #FFD1DF; selection-color: %(ink)s; }
QHeaderView { background: transparent; }
QHeaderView::section { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8FE6E6, stop:1 %(cyan)s);
    border: none; border-right: 1px solid %(cyan_dark)s; border-bottom: 2px solid %(ink)s;
    padding: 5px 6px; font-weight: bold; }
QHeaderView::section:vertical { border-right: 2px solid %(ink)s; border-bottom: 1px solid %(cyan_dark)s; }
QTableCornerButton::section { background: %(cyan)s; border: none; border-right: 2px solid %(ink)s; border-bottom: 2px solid %(ink)s; }

/* ── 묶음 상자: 점선 + 분홍 이름표 ── */
QGroupBox { background: #F8FFFE; border: 2px dashed %(dash)s; border-radius: 10px; margin-top: 16px; padding: 12px 8px 8px 8px; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 12px; top: 2px; padding: 1px 8px;
    background: %(pink)s; color: %(ink)s; border: 2px solid %(ink)s; border-radius: 7px; font-weight: bold; }

/* ── 탭 ── */
QTabWidget::pane { background: %(card)s; border: 2px solid %(ink)s; border-radius: 8px; top: -2px; }
QTabBar::tab { background: %(mint)s; border: 2px solid %(ink)s; border-bottom: none; border-top-left-radius: 9px;
    border-top-right-radius: 9px; padding: 4px 12px; margin-right: 3px; margin-top: 3px; }
QTabBar::tab:selected { background: %(card)s; color: %(pink_text)s; font-weight: bold; margin-top: 0px; padding-bottom: 6px; }
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
QMenu { background: %(card)s; border: 2px solid %(ink)s; padding: 3px; }
QMenu::item { padding: 4px 18px; border-radius: 4px; }
QMenu::item:selected { background: %(pink_pale)s; color: %(ink)s; }
QCalendarWidget QWidget#qt_calendar_navigationbar { background: %(cyan)s; }
QCalendarWidget QToolButton { color: %(ink)s; font-weight: bold; }
QCalendarWidget QAbstractItemView { selection-background-color: %(pink)s; selection-color: %(ink)s; border: none; }

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
QLabel[tone="note"] { color: #5f6368; }
QLabel[tone="warn"] { color: #b8322a; font-weight: bold; }
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
         QPalette.ColorRole.Base: C['card'], QPalette.ColorRole.AlternateBase: C['mint_row'],
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


# ── SNS 테마: 피드(사진 SNS 느낌) · 타임라인(짧은 글 SNS 느낌) — 각각 미니홈피 색 / 밝게 / 어둡게 ──
# 기능·화면은 같고 색·모양과 가계부 목록 모양만 다르다. 실제 서비스의 로고·이름은 쓰지 않는다. (안드로이드판 app.css 와 같은 색)
#   feed, timeline           : 미니홈피 색 (청록 바탕 + 흰 카드, 하늘·분홍 포인트) — 바탕 위 글자는 흰색
#   feed_light, timeline_light: 흰 바탕
#   feed_dark, timeline_dark : 검은 바탕
THEMES = ('retro', 'basic', 'feed', 'feed_light', 'feed_dark', 'timeline', 'timeline_light', 'timeline_dark')
SNS_THEMES = THEMES[2:]


def layout_of(theme):
    """가계부 목록 모양: 'feed' | 'timeline' | None (SNS 테마가 아님)"""
    theme = str(theme or '')
    return 'feed' if theme.startswith('feed') else 'timeline' if theme.startswith('timeline') else None


def variant_of(theme):
    """SNS 테마의 색: 'mh'(미니홈피 색) | 'light' | 'dark' | None"""
    if layout_of(theme) is None:
        return None
    return 'light' if theme.endswith('_light') else 'dark' if theme.endswith('_dark') else 'mh'


def _sns_entry(**c):
    """빠진 열쇠 채우기: 바탕 위 글자(on_bg)·메뉴 색은 카드와 같은 바탕이면 카드 글자색 그대로"""
    c.setdefault('page', c['card'])               # 가계부 목록 뒤
    c.setdefault('on_bg', c['ink'])               # 바탕 위 제목·메뉴 글자
    c.setdefault('on_bg2', c['muted'])
    c.setdefault('nav_hover', c['hover'])
    c.setdefault('nav_sel_bg', c['hover'])
    c.setdefault('btn2', c['surface2'])           # 회색 단추 (사진 SNS 의 '프로필 편집' 단추 같은)
    c.setdefault('fab', c['accent'])              # 쓰기 단추
    return c


_TEAL, _TEAL_DARK = '#347C7C', '#24595A'
# 미니홈피 색 (기본): 청록 물방울 바탕 위 흰 화면, 분홍·하늘·노랑 포인트 (안드로이드판 app.css 와 같은 색)
_MH = dict(bg=_TEAL, card='#FFFFFF', surface='#FFFFFF', surface2='#EAF6F5', grid='#E3F0EF', ink='#1A1A1A',
           muted='#5F7373', line='#CFE6E3', hover='#EAF9F7', scroll='#B8D8D5', dark=False, btn2='#E3F4F2',
           on_bg='#FFFFFF', on_bg2='#E3F6F3', nav_hover='#4A8B8B', nav_sel_bg='#4A8B8B', navsel='#FFFFFF',
           **{'in': '#1F6FB2', 'out': '#D23F6E'})
SNS = {
    'feed': _sns_entry(**dict(_MH, sel='#FFE3EC', accent='#E0507A', accent2='#C93F68',
                              ring=('#FFE066', '#FF8FB1', '#4BD5D5'))),
    'feed_light': _sns_entry(bg='#FFFFFF', card='#FFFFFF', surface='#FFFFFF', surface2='#EFEFEF', grid='#EFEFEF',
                             ink='#111111', muted='#737373', line='#DBDBDB', hover='#F2F2F2', sel='#FDEBF1',
                             accent='#E5487E', accent2='#D13A6E', navsel='#111111', scroll='#D0D0D0',
                             ring=('#FFD15C', '#FF5E8A', '#A35CFF'), dark=False, **{'in': '#2F6FDB', 'out': '#E0336A'}),
    'feed_dark': _sns_entry(bg='#000000', card='#000000', surface='#000000', surface2='#262626', grid='#262626',
                            ink='#F5F5F5', muted='#A8A8A8', line='#363636', hover='#1A1A1A', sel='#3A1424',
                            accent='#F0568C', accent2='#F46F9C', navsel='#F5F5F5', scroll='#444444', btn2='#363636',
                            ring=('#FFD15C', '#FF5E8A', '#A35CFF'), dark=True, **{'in': '#5B9BF5', 'out': '#F45C84'}),
    'timeline': _sns_entry(**dict(_MH, sel='#DFF5F2', accent='#2A8F8F', accent2=_TEAL_DARK, ring=None, fab='#E0507A')),
    'timeline_light': _sns_entry(bg='#FFFFFF', card='#FFFFFF', surface='#FFFFFF', surface2='#F7F9F9', grid='#EFF3F4',
                                 ink='#0F1419', muted='#536471', line='#EFF3F4', hover='#F2F4F5', sel='#E8F5FD',
                                 accent='#1D9BF0', accent2='#1A8CD8', navsel='#0F1419', scroll='#CCD6DD', btn2='#EFF3F4',
                                 ring=None, dark=False, **{'in': '#1A8CD8', 'out': '#F4212E'}),
    'timeline_dark': _sns_entry(bg='#000000', card='#000000', surface='#000000', surface2='#16181C', grid='#2F3336',
                                ink='#E7E9EA', muted='#71767B', line='#2F3336', hover='#181919', sel='#0A2A40',
                                accent='#1D9BF0', accent2='#3AA7F0', navsel='#E7E9EA', scroll='#3A4148', btn2='#202327',
                                ring=None, dark=True, **{'in': '#4CB0F5', 'out': '#F4556A'}),
}
AV_COLORS = ('#E8833A', '#E0525B', '#9457D6', '#3B7DDD', '#2E9E5B', '#139A9A', '#D24E8E', '#66788F')

SNS_QSS = """
QMainWindow { background: %(bg)s; }
QDialog, QMessageBox { background: %(card)s; }
QWidget { color: %(ink)s; }
QToolTip { background: %(ink)s; color: %(card)s; border: none; border-radius: 6px; padding: 4px 8px; }
QStatusBar { background: %(card)s; color: %(muted)s; border-top: 1px solid %(line)s; }
QStatusBar QLabel { color: %(muted)s; }
QFrame#Hompy { background: transparent; border: none; }
QFrame#MainBox { background: %(card)s; border: none; %(mainbox_extra)s }
QFrame#MainBox QScrollArea, QFrame#MainBox QStackedWidget { background: transparent; }
QLabel#HompyTitle { color: %(on_bg)s; font-size: 15pt; font-weight: 800; }
QLabel#TodayLabel { background: %(surface2)s; border-radius: 12px; padding: 3px 12px; }
QLabel#LedgerLabel { color: %(on_bg2)s; }

/* 왼쪽 메뉴 (SNS 앱의 왼쪽 줄: 로고 · 아이콘 메뉴 · 쓰기 · 내 프로필) */
QWidget#SnsRail { background: %(rail_bg)s; %(rail_extra)s }
QLabel#RailLogo { color: %(on_bg)s; padding: 4px 10px 10px 12px; }
QLabel#RailName { color: %(on_bg)s; font-weight: 700; }
QLabel#RailSub { color: %(on_bg2)s; }
QLabel[tone="note"] { color: %(muted)s; }
QLabel[tone="warn"] { color: %(out)s; font-weight: bold; }
QListWidget#TabNav { background: transparent; border: none; outline: none; font-size: 12pt; }
QListWidget#TabNav::item { padding: 9px 10px; margin: 2px 0px; border-radius: 10px; color: %(on_bg)s; }
QListWidget#TabNav::item:hover { background: %(nav_hover)s; }
QListWidget#TabNav::item:selected { background: %(nav_sel_bg)s; color: %(on_bg)s; font-weight: 800; }
QPushButton#RailCompose { background: %(fab)s; color: white; border: none; border-radius: 23px; min-height: 34px;
    font-size: 12pt; font-weight: 800; }
QPushButton#RailCompose:hover { background: %(accent2)s; }
QPushButton#RailCreate { background: transparent; color: %(on_bg)s; border: none; border-radius: 10px; text-align: left;
    padding: 9px 10px; font-size: 12pt; font-weight: 400; }
QPushButton#RailCreate:hover { background: %(nav_hover)s; }
QComboBox#RailLedger { background: %(rail_combo)s; color: %(ink)s; border: none; border-radius: 14px; padding: 5px 12px;
    font-weight: 700; }
QComboBox#RailLedger QAbstractItemView { background: %(surface)s; color: %(ink)s; border: 1px solid %(line)s; font-weight: 400;
    selection-background-color: %(hover)s; selection-color: %(ink)s; }
QLabel#SnsTitle { font-size: 15pt; font-weight: 800; padding: 10px 16px 8px 16px; background: %(card)s;
    border-bottom: 1px solid %(line)s; }
QWidget#SnsCol { background: %(card)s; }
QFrame#SnsSide { background: transparent; }
QPushButton#SnsGray { background: %(btn2)s; border: none; border-radius: 8px; padding: 6px 12px; font-weight: 600; }
QPushButton#SnsGray:hover { background: %(line)s; }
QToolButton#SnsTool { border-radius: 8px; padding: 5px; }
QToolButton#SnsTool:hover { background: %(hover)s; }

/* 버튼: 둥근 알약 모양 */
QPushButton { background: %(surface)s; color: %(ink)s; border: 1px solid %(line)s; border-radius: 15px;
              padding: 5px 14px; min-height: 18px; font-weight: 600; }
QPushButton:hover { background: %(hover)s; }
QPushButton:pressed { background: %(line)s; }
QPushButton:default { background: %(accent)s; color: white; border-color: %(accent)s; }
QPushButton:default:hover { background: %(accent2)s; }
QPushButton:disabled { color: %(muted)s; background: %(surface2)s; border-color: %(line)s; }
QPushButton#Link { background: transparent; border: none; color: %(accent)s; padding: 0; min-height: 0; }
QToolButton { background: transparent; border: none; border-radius: 6px; padding: 3px; }
QToolButton:hover { background: %(hover)s; }

/* 입력칸 */
QLineEdit, QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox, QTextEdit, QPlainTextEdit {
    background: %(surface)s; color: %(ink)s; border: 1px solid %(input_line)s; border-radius: 8px; padding: 4px 8px;
    selection-background-color: %(accent)s; selection-color: white; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QComboBox:focus,
QTextEdit:focus, QPlainTextEdit:focus { border: 1px solid %(accent)s; }
QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled, QSpinBox:disabled { color: %(muted)s; background: %(surface2)s;
    border-color: %(line)s; }
QComboBox QAbstractItemView { background: %(surface)s; color: %(ink)s; border: 1px solid %(line)s;
    selection-background-color: %(hover)s; selection-color: %(ink)s; outline: none; }
QComboBox QAbstractItemView::item { min-height: 28px; padding: 0 8px; }
QComboBox, QDateEdit { padding-right: 22px; }
QComboBox::drop-down, QDateEdit::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 22px;
    border: none; background: transparent; }
QComboBox::down-arrow, QDateEdit::down-arrow { image: url("%(chev_down)s"); width: 9px; height: 5px; }
QSpinBox, QDoubleSpinBox { padding-right: 20px; }
QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 18px;
    border: none; background: transparent; margin-top: 3px; }
QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 18px;
    border: none; background: transparent; margin-bottom: 3px; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::up-button:hover,
QDoubleSpinBox::down-button:hover { background: %(hover)s; border-radius: 4px; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url("%(chev_up)s"); width: 9px; height: 5px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url("%(chev_down)s"); width: 9px; height: 5px; }

/* 표 */
QTableView, QTableWidget, QTreeView, QTreeWidget, QListView, QListWidget {
    background: %(card)s; alternate-background-color: %(surface2)s; color: %(ink)s; border: 1px solid %(line)s;
    border-radius: 10px; gridline-color: %(grid)s; selection-background-color: %(sel)s; selection-color: %(ink)s; }
/* 표만: 줄무늬·선택·칸 선 색 (미니홈피 색이면 미니홈피 테마 표와 같은 민트 줄무늬·분홍 선택) */
QTableView, QTableWidget { alternate-background-color: %(tbl_alt)s; gridline-color: %(tbl_grid)s;
    selection-background-color: %(tbl_sel)s; }
QHeaderView { background: transparent; }
QHeaderView::section { background: %(hdr_bg)s; color: %(ink)s; border: none; border-bottom: %(hdr_line)s;
    border-right: 1px solid %(hdr_sep)s; padding: 6px 8px; font-weight: bold; }
QTableCornerButton::section { background: %(hdr_bg)s; border: none; }

/* 묶음 상자 */
QGroupBox { background: %(card)s; border: 1px solid %(line)s; border-radius: 12px; margin-top: 18px;
    padding: 14px 10px 10px 10px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; left: 12px; top: 2px; padding: 0 4px; color: %(ink)s; }

/* 탭: 밑줄로 고른 탭 표시 */
QTabWidget::pane { background: %(card)s; border: 1px solid %(line)s; border-radius: 10px; top: -1px; }
QTabBar::tab { background: transparent; color: %(muted)s; border: none; border-bottom: 3px solid transparent; padding: 6px 14px; }
QTabBar::tab:selected { color: %(ink)s; border-bottom: 3px solid %(accent)s; }
QTabBar::tab:hover:!selected { color: %(ink)s; }

/* 스크롤바: 얇게 */
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; border: none; }
QScrollBar::handle:vertical { background: %(scroll)s; border-radius: 5px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; border: none; }
QScrollBar::handle:horizontal { background: %(scroll)s; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; background: none; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }

QSplitter::handle { background: transparent; }
QMenu { background: %(surface)s; color: %(ink)s; border: 1px solid %(line)s; border-radius: 8px; padding: 4px; }
QMenu::item { padding: 5px 18px; border-radius: 6px; }
QMenu::item:selected { background: %(hover)s; color: %(ink)s; }
QCalendarWidget QWidget#qt_calendar_navigationbar { background: %(card)s; }
QCalendarWidget QToolButton { color: %(ink)s; font-weight: bold; }
QCalendarWidget QAbstractItemView { background: %(surface)s; color: %(ink)s; selection-background-color: %(accent)s;
    selection-color: white; border: none; }
QLabel#MonthLabel { font-size: 13pt; font-weight: bold; }
QWidget#MonthNav QPushButton { background: %(btn2)s; border: none; border-radius: 8px; min-height: 22px; }
QWidget#MonthNav QPushButton:hover { background: %(line)s; }
QLabel#DayLabel { font-weight: bold; font-size: 12pt; }
QLabel#SumLabel { background: %(surface2)s; border-radius: 10px; padding: 8px; }

/* 체크·라디오 단추 (어두운 테마에서도 보이게) */
QCheckBox, QRadioButton { spacing: 7px; }
QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; }
QCheckBox::indicator { border: 2px solid %(scroll)s; border-radius: 4px; background: %(surface)s; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: %(accent)s; }
QCheckBox::indicator:checked { background: %(accent)s; border-color: %(accent)s; image: url("%(check)s"); }
QCheckBox::indicator:disabled { background: %(surface2)s; border-color: %(line)s; }
QRadioButton::indicator { border: 2px solid %(scroll)s; border-radius: 10px; background: %(surface)s; }
QRadioButton::indicator:checked { border: 2px solid %(accent)s;
    background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 %(accent)s, stop:0.55 %(accent)s,
                                stop:0.62 %(surface)s, stop:1 %(surface)s); }
QTableWidget::indicator, QListWidget::indicator, QTreeWidget::indicator { width: 15px; height: 15px; }
QTableWidget::indicator:unchecked, QListWidget::indicator:unchecked, QTreeWidget::indicator:unchecked {
    border: 2px solid %(scroll)s; border-radius: 4px; background: %(surface)s; }
QTableWidget::indicator:checked, QListWidget::indicator:checked, QTreeWidget::indicator:checked {
    border: 2px solid %(accent)s; border-radius: 4px; background: %(accent)s; image: url("%(check)s"); }
"""


# ── 색 바꾸기: 테마마다 6가지 색 (안드로이드판과 같은 방식, 나머지 색은 이 색들로 계산) ──
COLOR_KEYS = (('accent', '포인트 (단추·강조)'), ('bg', '바탕'), ('card', '카드·창'), ('ink', '글자'),
              ('in', '수입 글자'), ('out', '지출 글자'))


def _rgb(h):
    h = h.lstrip('#')
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _hex(a):
    return '#' + ''.join(f'{max(0, min(255, round(x))):02X}' for x in a)


def mix(a, b, t):
    x, y = _rgb(a), _rgb(b)
    return _hex([v + (y[i] - v) * t for i, v in enumerate(x)])


def lum(h):
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def norm_hex(v):
    v = str(v or '').strip().upper()
    if not v.startswith('#'):
        v = '#' + v
    if len(v) == 4 and all(c in '0123456789ABCDEF' for c in v[1:]):
        v = '#' + ''.join(c * 2 for c in v[1:])
    return v if len(v) == 7 and all(c in '0123456789ABCDEF' for c in v[1:]) else None


def base_colors(theme=None):
    """그 테마의 처음 색 6가지"""
    theme = theme or current()[0]
    if theme in SNS:
        c = SNS[theme]
        return {'accent': c['accent'], 'bg': c['bg'], 'card': c['card'], 'ink': c['ink'], 'in': c['in'], 'out': c['out']}
    if theme == 'basic':
        app = QApplication.instance()
        pal = app._gb_orig[1] if app is not None and hasattr(app, '_gb_orig') else QPalette()
        g = lambda r: pal.color(r).name().upper()
        return {'accent': g(QPalette.ColorRole.Highlight), 'bg': g(QPalette.ColorRole.Window), 'card': g(QPalette.ColorRole.Base),
                'ink': g(QPalette.ColorRole.Text), 'in': '#1D5FBF', 'out': '#B8322A'}
    d = C_DEFAULT
    # 수입·지출 글자색: 미니홈피 색 SNS 테마·안드로이드판 미니홈피와 같은 파랑·분홍빨강
    return {'accent': d['pink'], 'bg': d['teal'], 'card': d['card'], 'ink': d['ink'], 'in': '#1F6FB2', 'out': '#D23F6E'}


def _json_pref(key, dflt):
    v = settings().value(key, '')
    if not v:
        return dflt
    try:
        out = json.loads(str(v))
    except ValueError:
        return dflt
    return out if isinstance(out, type(dflt)) else dflt


def custom_colors(theme=None):
    theme = theme or current()[0]
    raw = _json_pref(f'colors_{theme}', {})
    return {k: norm_hex(raw.get(k)) for k, _l in COLOR_KEYS if norm_hex(raw.get(k))}


def set_custom_color(key, value, theme=None):
    """value=None 이면 그 색만 처음으로. key=None 이면 그 테마 색 모두 처음으로."""
    theme = theme or current()[0]
    cu = {} if key is None else custom_colors(theme)
    if key is not None:
        v = norm_hex(value)
        if v and v != base_colors(theme)[key].upper():
            cu[key] = v
        else:
            cu.pop(key, None)
    set_pref(f'colors_{theme}', json.dumps(cu) if cu else '')
    _sns_cache.clear()


def effective_colors(theme=None):
    theme = theme or current()[0]
    c = base_colors(theme)
    c.update(custom_colors(theme))
    return c


_sns_cache = {}


def sns_colors(theme=None):
    """SNS 테마의 실제 색 (사용자가 바꾼 색 반영). SNS 테마가 아니면 None. 목록 그리기에서 자주 불려 기억해 둠"""
    theme = theme or current()[0]
    if theme not in SNS:
        return None
    if theme not in _sns_cache:
        _sns_cache[theme] = _sns_colors(theme)
    return _sns_cache[theme]


def _sns_colors(theme):
    base = dict(SNS[theme])
    cu = custom_colors(theme)
    if not cu:
        return base
    c = effective_colors(theme)
    bg, card, ink, acc = c['bg'], c['card'], c['ink'], c['accent']
    dark = lum(card) < 0.18
    hover = mix(card, ink, 0.07)
    # 바탕이 카드와 확 다르면 (미니홈피 색처럼) 바탕 위 제목·메뉴 글자를 바탕에 맞춰 따로 정함
    sep = abs(lum(bg) - lum(card)) > 0.25
    on_bg = ('#FFFFFF' if lum(bg) < 0.4 else '#1A1A1A') if sep else ink
    feed = layout_of(theme) == 'feed'
    base.update({'bg': bg, 'card': card, 'ink': ink, 'accent': acc, 'in': c['in'], 'out': c['out'],
                 'surface': mix(card, ink, 0.06) if dark else card, 'surface2': mix(card, ink, 0.045),
                 'grid': mix(card, ink, 0.09), 'muted': mix(ink, card, 0.45), 'line': mix(card, ink, 0.14),
                 'hover': hover, 'sel': mix(card, acc, 0.15), 'accent2': mix(acc, '#000000', 0.1),
                 'navsel': ink if sep else (acc if theme == 'timeline_light' else ink),
                 'scroll': mix(card, ink, 0.25), 'dark': dark,
                 'page': card, 'btn2': mix(card, bg if sep else ink, 0.1 if sep else 0.08),
                 'fab': base.get('fab', acc) if 'accent' not in cu else acc,
                 'on_bg': on_bg, 'on_bg2': mix(on_bg, bg, 0.15), 'nav_hover': mix(bg, on_bg, 0.12) if sep else hover,
                 'nav_sel_bg': mix(bg, on_bg, 0.12) if sep else hover})
    if feed and 'accent' in cu:
        base['ring'] = (mix(acc, '#FFC861', 0.55), acc, mix(acc, '#8B5CF6', 0.55))
    return base


def _apply_retro_colors():
    """미니홈피 테마 색 C 를 그 자리에서 바꿈 (다른 모듈이 T.C 를 읽음)"""
    C.clear()
    C.update(C_DEFAULT)
    cu = custom_colors('retro')
    if not cu:
        return
    c = effective_colors('retro')
    bg, card, acc = c['bg'], c['card'], c['accent']
    C.update({'teal': bg, 'teal_dark': mix(bg, '#000000', 0.3), 'pink': acc, 'pink_dark': mix(acc, '#000000', 0.18),
              'pink_text': mix(acc, '#000000', 0.3),
              'pink_pale': mix(card, acc, 0.18), 'mint_pale': mix(card, bg, 0.1), 'mint': mix(card, bg, 0.3),
              'mint_row': mix(card, bg, 0.06), 'dash': mix(card, bg, 0.6), 'ink': c['ink'], 'card': card,
              'on_bg': '#FFFFFF' if lum(bg) < 0.4 else '#1A1A1A',
              'caption': mix(bg, '#FFFFFF', 0.85) if lum(bg) < 0.4 else mix(bg, '#000000', 0.6),
              'dot': mix(bg, '#FFFFFF', 0.1)})


def _basic_palette(pal0):
    cu = custom_colors('basic')
    if not cu:
        return QPalette(pal0)
    c = effective_colors('basic')
    p = QPalette(pal0)
    for role, col in ((QPalette.ColorRole.Highlight, c['accent']), (QPalette.ColorRole.Window, c['bg']),
                      (QPalette.ColorRole.Base, c['card']), (QPalette.ColorRole.AlternateBase, mix(c['card'], c['ink'], 0.045)),
                      (QPalette.ColorRole.Text, c['ink']), (QPalette.ColorRole.WindowText, c['ink']),
                      (QPalette.ColorRole.ButtonText, c['ink']), (QPalette.ColorRole.Button, mix(c['bg'], c['card'], 0.5)),
                      (QPalette.ColorRole.Link, c['accent'])):
        p.setColor(QPalette.ColorGroup.Active, role, QColor(col))
        p.setColor(QPalette.ColorGroup.Inactive, role, QColor(col))
    return p


# ── 순서 (이 PC에만 저장) ──
NAV_PAGES = ('LedgerPage', 'SearchPage', 'ReportsPage', 'GraphPage', 'RecurringPage', 'AssetsPage', 'CalendarPage',
             'AddressPage', 'DiaryPage', 'MemoPage', 'SettingsPage')
LEDGER_PARTS = (('nav', '달 이동·단추 줄'), ('stories', '지출 많은 계정 동그라미 (피드) · 많이 쓴 곳 (타임라인)'), ('table', '내역 목록'),
                ('summary', '이달의 현황 (피드: 프로필 머리, 타임라인: 고정된 글)'))


def _key_order(saved, all_keys):
    out = [k for i, k in enumerate(saved) if k in all_keys and k not in saved[:i]]
    return out + [k for k in all_keys if k not in out]


def nav_order():
    return _key_order(_json_pref('nav_order', []), list(NAV_PAGES))


def set_nav_order(keys):
    set_pref('nav_order', json.dumps(list(keys)) if keys else '')


# 순서를 따로 정하지 않았으면 테마에 맞는 기본 순서 (피드: 프로필 머리가 맨 위 / 타임라인: 달 이동 → 고정된 글)
LEDGER_DEFAULT = {'feed': ['summary', 'nav', 'stories', 'table'], 'timeline': ['nav', 'summary', 'stories', 'table']}


def ledger_layout():
    keys = [k for k, _l in LEDGER_PARTS]
    return _key_order(_json_pref('ledger_layout', []) or LEDGER_DEFAULT.get(layout_of(current()[0]), []), keys)


def set_ledger_layout(keys):
    set_pref('ledger_layout', json.dumps(list(keys)) if keys else '')


def input_side():
    return 'left' if str(settings().value('input_side', 'right')) == 'left' else 'right'


def set_input_side(side):
    set_pref('input_side', 'left' if side == 'left' else 'right')


def sns_palette(c):
    p = QPalette()
    # Window = 화면(카드) 바탕. 창 바깥 바탕(bg)은 스타일시트의 QMainWindow 가 칠함 — 스크롤 영역 안 화면이 Window 로 칠해지므로
    g = {QPalette.ColorRole.Window: c['card'], QPalette.ColorRole.WindowText: c['ink'],
         QPalette.ColorRole.Base: c['surface'], QPalette.ColorRole.AlternateBase: c['surface2'],
         QPalette.ColorRole.Text: c['ink'], QPalette.ColorRole.Button: c['surface'],
         QPalette.ColorRole.ButtonText: c['ink'], QPalette.ColorRole.Highlight: c['accent'],
         QPalette.ColorRole.HighlightedText: '#FFFFFF', QPalette.ColorRole.ToolTipBase: c['ink'],
         QPalette.ColorRole.ToolTipText: c['card'], QPalette.ColorRole.PlaceholderText: c['muted'],
         QPalette.ColorRole.Link: c['accent'], QPalette.ColorRole.BrightText: c['out'],
         QPalette.ColorRole.Light: c['surface'], QPalette.ColorRole.Midlight: c['surface2'],
         QPalette.ColorRole.Mid: c['line'], QPalette.ColorRole.Dark: c['scroll'], QPalette.ColorRole.Shadow: c['line']}
    for role, col in g.items():
        p.setColor(role, QColor(col))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, QColor(c['muted']))
    return p


# 미니홈피 표 색 — 미니홈피 테마와 미니홈피 색(피드·타임라인) 테마, 안드로이드판 main.js applyTableColors 와 같음
MH_TABLE = dict(hdr_bg='qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8FE6E6, stop:1 #4BD5D5)',
                hdr_line='2px solid #2BB5B5', hdr_sep='#2BB5B5', tbl_alt='#F0FBFA', tbl_grid='#CBEDEA', tbl_sel='#FFD1DF')


def table_colors(theme=None):
    """SNS 테마의 표 머리줄·줄무늬·선택 색. 미니홈피 색이면 미니홈피 표와 같게, 밝게·어둡게는 그 바탕에 맞춤"""
    theme = theme or current()[0]
    c = sns_colors(theme)
    if variant_of(theme) == 'mh':
        return dict(MH_TABLE)
    # 고른 줄: 줄무늬·소계와 헷갈리지 않게 포인트 색을 더 진하게
    return dict(hdr_bg=c['surface2'], hdr_line=f"1px solid {mix(c['card'], c['ink'], 0.32)}", hdr_sep=c['grid'],
                tbl_alt=c['surface2'], tbl_grid=c['grid'], tbl_sel=mix(c['card'], c['accent'], 0.35 if c['dark'] else 0.24))


def tone(theme=None):
    """직접 그리는 화면(달력·그래프)과 표 색. 어두운 테마면 밝은 글자색."""
    theme = theme or current()[0]
    c = sns_colors(theme)
    eff = effective_colors(theme)
    if c and c['dark']:
        return {'text': c['ink'], 'text2': '#D0D4D8', 'faint': '#5A6168', 'lunar': '#8F969D', 'ann': '#5FC28F',
                'today_bg': '#3A3412', 'sel_bg': c['sel'], 'chart_bg': c['surface'], 'grid': c['grid'],
                'axis': '#A0A6AC', 'axis2': c['muted'], 'legend': '#D0D4D8', 'title': c['ink'],
                'sun': '#F45C84', 'sat': '#52AEF2', 'in': c['in'], 'out': c['out'],
                # 표: 소계·합계 줄은 포인트 색을 옅게(합계가 더 진하게), 대분류 칸은 회색, 0 은 흐리게
                'subtotal_bg': mix(c['card'], c['accent'], 0.20), 'footer_bg': mix(c['card'], c['accent'], 0.34),
                'zero': mix(c['card'], c['ink'], 0.36), 'group_bg': mix(c['card'], c['ink'], 0.10),
                'sep': mix(c['card'], c['ink'], 0.42)}
    t = {'text': '#222', 'text2': '#333', 'faint': '#aaa', 'lunar': '#767676', 'ann': '#2f7d5b',
         'today_bg': '#fff5d6', 'sel_bg': '#eaf2ff', 'chart_bg': '#ffffff', 'grid': '#e3e3e3',
         'axis': '#555', 'axis2': '#777', 'legend': '#333', 'title': '#222', 'sun': '#d0312d', 'sat': '#2f6fbe',
         'in': '#1d5fbf', 'out': '#b8322a', 'subtotal_bg': '#fdf1e3', 'footer_bg': '#ece8f6',
         # 0 원(흐리게)·결산 보고서 대분류 칸·대분류끼리 나누는 선
         'zero': '#b8b8b8', 'group_bg': '#eef2f7', 'sep': '#9aa4ae'}
    if c and variant_of(theme) == 'mh':          # 미니홈피 색: 미니홈피 테마처럼 살구색 소계·민트 대분류·청록 선
        t.update({'in': c['in'], 'out': c['out'], 'sel_bg': c['sel'], 'group_bg': mix(c['card'], '#4BD5D5', 0.16),
                  'sep': '#5CC6C6'})
    elif c:
        t.update({'in': c['in'], 'out': c['out'], 'sel_bg': c['sel'], 'subtotal_bg': mix(c['card'], c['accent'], 0.09),
                  'footer_bg': mix(c['card'], c['accent'], 0.18), 'group_bg': mix(c['card'], c['ink'], 0.045),
                  'sep': mix(c['card'], c['ink'], 0.32)})
    elif theme == 'retro':
        t.update({'in': eff['in'], 'out': eff['out'], 'group_bg': mix(eff['card'], C['cyan'], 0.16), 'sep': C['dash']})
    else:
        t.update({'in': eff['in'], 'out': eff['out']})
    return t


def avatar_color(label):
    h = 0
    for ch in str(label or ''):
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return AV_COLORS[h % len(AV_COLORS)]


def avatar_initial(label):
    s = str(label or '')
    if s.startswith('(미분류'):
        return '?'
    for ch in s:
        if not ch.isspace() and ch not in '()[]·.,_-':
            return ch
    return '?'


def avatar_pixmap(sid, size, theme=None, dpr=None):
    """미니미를 동그란 프로필 사진처럼 (피드 테마는 색 테두리)."""
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QBrush, QConicalGradient, QPainter, QPainterPath, QPen
    c = sns_colors(theme) or SNS['timeline']
    if dpr is None:
        app = QGuiApplication.instance()
        dpr = app.devicePixelRatio() if app else 1.0
    px = max(1, round(size * dpr))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    r = QRectF(0, 0, px, px)
    ring = max(2.0, px * 0.06)
    if c['ring']:
        g = QConicalGradient(px / 2, px / 2, 45)
        cols = list(c['ring']) + [c['ring'][0]]
        for i, col in enumerate(cols):
            g.setColorAt(i / (len(cols) - 1), QColor(col))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawEllipse(r)
        inner = r.adjusted(ring, ring, -ring, -ring)
    else:
        p.setPen(QPen(QColor(c['line']), max(1.0, dpr)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        inner = r.adjusted(0.5, 0.5, -0.5, -0.5)
        p.drawEllipse(inner)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(c['card']))
    p.drawEllipse(inner)
    pic = inner.adjusted(ring * 0.7, ring * 0.7, -ring * 0.7, -ring * 0.7)
    path = QPainterPath()
    path.addEllipse(pic)
    p.setClipPath(path)
    p.fillPath(path, QColor(c['surface']))
    img = QPixmap(sticker_path(sid))
    if not img.isNull():
        side = int(pic.width() * 0.86)
        img = img.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        p.drawPixmap(int(pic.center().x() - img.width() / 2), int(pic.center().y() - img.height() / 2), img)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


FONT_PX_MIN, FONT_PX_MAX = 8, 28


def font_px():
    """글자 크기를 1px 단위로 정했으면 그 값, 아니면 0 (테마의 기본 크기)"""
    try:
        v = int(settings().value('font_px', 0) or 0)
    except (TypeError, ValueError):
        return 0
    return v if FONT_PX_MIN <= v <= FONT_PX_MAX else 0


def _with_px(f):
    """글자 크기를 1px 단위로 정했으면 그 크기로 (스타일시트보다 먼저 정해야 화면에 적용됨)"""
    px = font_px()
    if not px:
        return f
    f = QFont(f)
    f.setPixelSize(px)
    return f


def set_font_px(px):
    set_pref('font_px', int(px) if px and FONT_PX_MIN <= int(px) <= FONT_PX_MAX else 0)


def current():
    """지금 적용할 (테마, 도트글꼴 사용 여부)"""
    theme = pref('theme')
    theme = theme if theme in THEMES else 'retro'
    pixel = theme == 'retro' and pref('font') == 'pixel' and load_fonts() is not None
    return theme, pixel


def _set_style(app, name):
    """같은 스타일이면 다시 만들지 않음 — 스타일·팔레트·글꼴·스타일시트를 바꿀 때마다 Qt 가 모든 위젯을 다시 꾸며
    (켤 때 같은 테마를 두 번 입히느라 1초 넘게 걸리던 것)"""
    if getattr(app, '_gb_style', None) == name.lower():
        return
    st = QStyleFactory.create(name)
    if st is not None:
        app.setStyle(st)
        app._gb_style = name.lower()


def _set_look(app, pal, font, qss):
    """색·글꼴·스타일시트 중 하나라도 바뀌었으면 셋 다 다시 입힘 (스타일시트를 다시 입혀야 바뀐 글꼴이 모든 위젯에 퍼짐),
    하나도 안 바뀌었으면 건너뜀"""
    if app.palette() == pal and app.font() == font and app.styleSheet() == qss:
        return
    app.setPalette(pal)
    app.setFont(font)
    app.setStyleSheet(qss)


def apply(app=None):
    """앱 전체에 테마 적용. 처음 부를 때 원래 스타일·팔레트·글꼴을 기억해 '기본'으로 되돌릴 수 있게 함.
    바뀐 것만 다시 입힘 (같은 테마를 다시 입히면 거의 0초)"""
    app = app or QApplication.instance()
    if not hasattr(app, '_gb_orig'):
        app._gb_orig = (app.style().name(), QPalette(app.palette()), QFont(app.font()))
    style0, pal0, font0 = app._gb_orig
    theme, pixel = current()
    _sns_cache.clear()
    _apply_retro_colors()
    if theme == 'retro':
        _set_style(app, 'Fusion')
        if pixel:
            f = QFont(PIXEL_FAMILY)
            f.setPixelSize(12)
            f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
            f = _with_px(f)
        else:
            f = _with_px(_font_for(font0))
        _set_look(app, retro_palette(), f, retro_qss(pixel))
    elif theme in SNS_THEMES:
        c = sns_colors(theme)
        _set_style(app, 'Fusion')
        tag = 'light' if c['dark'] else 'grey'
        mh = variant_of(theme) == 'mh'
        extra = dict(rail_bg='transparent' if mh else c['card'],
                     rail_extra='' if mh else f"border-right: 1px solid {c['line']};",
                     mainbox_extra='border-top-left-radius: 18px; border-bottom-left-radius: 18px;' if mh else '',
                     rail_combo=c['card'] if mh else c['btn2'])     # 장부 고르기: 흰 알약 (펼친 목록 글자도 진하게)
        extra.update(table_colors(theme))
        # 입력칸 테두리: 바탕과 확실히 구분되게 (미니홈피 색은 청록빛, 밝게·어둡게는 회색)
        extra['input_line'] = mix(c['card'], c['bg'], 0.5) if mh else mix(c['card'], c['ink'], 0.38)
        _set_look(app, sns_palette(c), _with_px(_font_for(font0)),
                  SNS_QSS % dict(c, check=_url('check-white.png'), chev_down=_url(f'chev-down-{tag}.png'),
                                 chev_up=_url(f'chev-up-{tag}.png'), **extra))
    else:
        _set_style(app, style0)
        _set_look(app, _basic_palette(pal0), _with_px(_font_for(font0)), BASIC_QSS)
    _pix_cache.clear()
    from .ui import widgets as _w          # 표의 수입·지출 글자색, 소계 배경색
    _w.retheme(tone(theme))
    return theme, pixel
