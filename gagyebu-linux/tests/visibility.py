"""화면 전체 가시성 점검 (1.6.1): 테마 8개에서 잘림·흐린 글자·안 보이는 테두리를 고친 것이 그대로인지.
사용: QT_QPA_PLATFORM=offscreen python3 tests/visibility.py <출력폴더>"""
import datetime as dt
import os
import sys
import tempfile
import traceback

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)

from PyQt6.QtGui import QColor, QFontMetrics  # noqa: E402
from PyQt6.QtWidgets import QApplication, QScrollArea  # noqa: E402

from gagyebu import db  # noqa: E402
from gagyebu.services import ledger as L  # noqa: E402

out = sys.argv[1]
os.makedirs(out, exist_ok=True)
tmp = tempfile.mkdtemp()
os.environ['XDG_CONFIG_HOME'] = os.path.join(tmp, 'config')
path = os.path.join(tmp, 'g.sqlite3')
con = db.connect(path)
db.set_meta(con, 'password', None)
lid = L.first_ledger_id(con)
T0 = dt.date.today()
L.add_entry(con, lid, {'date': T0, 'item': '아주 긴 품목 이름을 가진 마트 장보기 (채소·과일·우유·계란)', 'expense': 35000,
                       'code': '30', 'memo': '회사 앞'})
L.add_entry(con, lid, {'date': T0, 'item': '급여', 'income': 3200000, 'code': '00'})
con.close()

from gagyebu import theme as TH  # noqa: E402
from gagyebu.app import MainWindow  # noqa: E402
from gagyebu.ui import widgets as W  # noqa: E402

app = QApplication(sys.argv[:1])
TH.apply(app)
w = MainWindow(path)
w.resize(1360, 860)
w.show()
w.data_changed()
fails = []


def check(name, cond, extra=''):
    print(('  ✓ ' if cond else '  ✗ ') + name + (f'  ({extra})' if extra and not cond else ''))
    if not cond:
        fails.append(name)


def hscroll(page):
    """그 화면이 들어 있는 스크롤 영역에 가로 스크롤이 생겼는지"""
    p = page.parentWidget()
    while p is not None and not isinstance(p, QScrollArea):
        p = p.parentWidget()
    return p.horizontalScrollBar().maximum() if p is not None else 0


def contrast(a, b):
    def lum(c):
        c = QColor(c)
        v = [x / 255 for x in (c.red(), c.green(), c.blue())]
        v = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in v]
        return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


for th in TH.THEMES:
    print(th)
    try:
        TH.set_pref('theme', th)
        w.apply_theme()
        app.processEvents()
        qss = app.styleSheet()
        # 분홍 바탕 위 흰 글자 없음 (미니홈피)
        if th == 'retro':
            check('분홍 이름표·눌린 단추·선택 글자가 검정 (흰 글자 대비 2.1:1 → 8:1)', 'background: #FF8FB1; color: white' not in qss
                  and 'selection-color: white' not in qss.split('/* ── 탭')[0], '')
            check('분홍 글자는 흰 바탕 대비 4.5:1 이상', contrast(TH.C['pink_text'], '#FFFFFF') >= 4.5, TH.C['pink_text'])
        sc = TH.sns_colors(th)
        if sc:
            # 입력칸 테두리가 카드와 또렷이 구분
            import re
            m = re.search(r'QLineEdit, QSpinBox.*?border: 1px solid (#[0-9A-Fa-f]{6})', qss, re.S)
            check('입력칸 테두리 대비 1.9:1 이상', m and contrast(m.group(1), sc['card']) >= 1.9, m and m.group(1))
            if TH.variant_of(th) == 'mh':
                check('청록 위 보조 글자 대비 4:1 이상', contrast(sc['on_bg2'], sc['bg']) >= 4.0, sc['on_bg2'])
            check('고른 메뉴에 바탕색', f"QListWidget#TabNav::item:selected {{ background: {sc['nav_sel_bg']}" in qss)
            tc = TH.table_colors(th)
            check('표 고른 줄이 줄무늬와 구분', tc['tbl_sel'] != tc['tbl_alt'] and contrast(tc['tbl_sel'], tc['tbl_alt']) >= 1.15,
                  f"{tc['tbl_sel']} {tc['tbl_alt']}")
        # 가계부: 긴 품목을 고르면 입력 칸이 넓어져 가로 스크롤이 생기던 것
        lp = w.goto('LedgerPage')
        app.processEvents()
        if th not in TH.SNS_THEMES:
            lp.table.clearSelection()
            lp.table.selectRow(next(r for r in range(lp.table.rowCount()) if '아주 긴' in (lp.table.item(r, 1).text())))
            app.processEvents()
            check('긴 품목을 골라 고치는 중에도 가로 스크롤 없음', hscroll(lp) == 0, str(hscroll(lp)))
            check("고치는 중 안내는 '주의' 색(테마에 따름)", lp.mode_lbl.property('tone') == 'warn')
            vis = lp.box.mapTo(w, lp.del_btn.geometry().topRight()).x() <= w.width()
            check('[삭제] 단추가 화면 안', vis)
            w.grab().save(os.path.join(out, f'{th}_가계부_수정.png'))
            lp.new()
        # 일정관리: 일괄 삭제 날짜가 다 보이는 폭
        cp = w.goto('CalendarPage')
        app.processEvents()
        need = QFontMetrics(cp.del_from.font()).horizontalAdvance('2026-10-30')
        check('날짜 칸 폭이 날짜 글자보다 넉넉', cp.del_from.width() >= need + 50, f'{cp.del_from.width()} {need}')
        check('음력 날짜 글자 대비 4.5:1 이상', contrast(TH.tone(th)['lunar'], '#FFFFFF' if not (sc and sc['dark']) else '#000000') >= 4.5)
        w.grab().save(os.path.join(out, f'{th}_일정.png'))
        # 그래프: [이미지로 저장] 이 화면 안
        gp = w.goto('GraphPage')
        app.processEvents()
        btn = next(b for b in gp.findChildren(W.QPushButton) if b.text() == '이미지로 저장')
        right = btn.mapTo(w, btn.rect().topRight()).x()
        check('그래프 [이미지로 저장] 단추가 화면 안, 가로 스크롤 없음', right <= w.width() and hscroll(gp) == 0, f'{right} {hscroll(gp)}')
        # 수입·지출 색이 흰/검은 바탕에서 읽힘
        tn = TH.tone(th)
        bg = sc['card'] if sc else '#FFFFFF'
        check('수입·지출 글자 대비 3.5:1 이상', contrast(tn['in'], bg) >= 3.5 and contrast(tn['out'], bg) >= 3.5, f"{tn['in']} {tn['out']}")
        # 안내 글 색: 박아 둔 회색이 아니라 테마 규칙
        rp = w.goto('ReportsPage')
        check('결산 보고서 안내 글이 테마 색 규칙(tone=note)', rp.t_month.view.note.property('tone') == 'note')
    except Exception:
        fails.append(th)
        traceback.print_exc()

TH.set_pref('theme', 'retro')
w.apply_theme()
print()
print('실패:', fails if fails else '없음')
sys.exit(1 if fails else 0)
