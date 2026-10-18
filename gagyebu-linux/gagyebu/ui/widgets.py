"""공통 위젯: 금액·날짜 입력, 표, CSV·인쇄, 범용 입력창, 계정 선택."""
import datetime as dt
import html

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QTextDocument
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
                             QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox,
                             QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout, QWidget)

from ..services import ledger as L
from ..services.backup import write_csv
from ..util import fmt_money, parse_money

RIGHT = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
CENTER = Qt.AlignmentFlag.AlignCenter
LEFT = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
INCOME_COLOR = QColor('#1d5fbf')
EXPENSE_COLOR = QColor('#b8322a')
SUBTOTAL_BG = QColor('#fdf1e3')
FOOTER_BG = QColor('#ece8f6')
ID_ROLE = Qt.ItemDataRole.UserRole


# ── 입력 위젯 ───────────────────────────────────────────
class MoneyEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(RIGHT)
        self.setPlaceholderText('0')
        self.editingFinished.connect(self._fmt)

    def _fmt(self):
        try:
            v = parse_money(self.text())
            self.setText(fmt_money(v) if v else '')
        except ValueError:
            pass

    def value(self):
        return parse_money(self.text())

    def set_value(self, v):
        self.setText(fmt_money(v) if v else '')


class DateEdit(QDateEdit):
    def __init__(self, d=None, parent=None):
        super().__init__(parent)
        self.setCalendarPopup(True)
        self.setDisplayFormat('yyyy-MM-dd')
        self.set_date(d or dt.date.today())

    def date_(self):
        q = self.date()
        return dt.date(q.year(), q.month(), q.day())

    def set_date(self, d):
        d = d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d)[:10])
        self.setDate(QDate(d.year, d.month, d.day))


class CodeCombo(QComboBox):
    """계정 선택 콤보: '30  식료품' 형태. 숫자를 치면 그 코드로 이동."""
    def __init__(self, con, parent=None, allow_empty=False):
        super().__init__(parent)
        self.con = con
        self.allow_empty = allow_empty
        self.setMaxVisibleItems(25)
        self.setMinimumContentsLength(14)

    def load(self, lid, keep_unknown=False):
        cur = self.code()
        self.blockSignals(True)
        self.clear()
        if self.allow_empty:
            self.addItem('(선택 안 함)', '')
        gmap = L.group_map(self.con, lid)
        last_g = None
        for c in L.categories(self.con, lid):
            g = c['code'][:1]
            if g != last_g:
                self.addItem(f'── {g} {gmap.get(g, "")} ──', None)
                idx = self.count() - 1
                self.model().item(idx).setEnabled(False)
                last_g = g
            self.addItem(f"{c['code']}  {c['name']}", c['code'])
        self.blockSignals(False)
        self.set_code(cur, keep_unknown=keep_unknown and bool(cur))

    def code(self):
        return self.currentData() or ''

    def set_code(self, code, keep_unknown=False):
        """keep_unknown=True(기존 내역 수정): 계정 목록에 없는 코드도 바꾸지 않고 '(미분류)'로 그대로 유지."""
        i = self.findData(code) if code else -1
        if i < 0 and keep_unknown:
            self.addItem(f'{code}  (미분류 — 계정 없음)' if code else '(계정 없음 — 골라 주세요)', code or None)
            i = self.count() - 1
        if i < 0:
            first = next((k for k in range(self.count()) if self.itemData(k)), 0)
            i = first if not self.allow_empty else 0
        self.setCurrentIndex(i)


def h(*widgets, stretch_last=False):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    for x in widgets:
        if x == 'stretch':
            lay.addStretch(1)
        elif isinstance(x, str):
            lay.addWidget(QLabel(x))
        else:
            lay.addWidget(x)
    if stretch_last:
        lay.addStretch(1)
    return w


def button(text, slot=None, tip=None):
    b = QPushButton(text)
    if slot:
        b.clicked.connect(slot)
    if tip:
        b.setToolTip(tip)
    return b


# ── 표 ─────────────────────────────────────────────────
def make_table(headers, stretch=None, multi=False):
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection if multi
                       else QAbstractItemView.SelectionMode.SingleSelection)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(24)
    hh = t.horizontalHeader()
    hh.setHighlightSections(False)
    hh.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    if stretch is not None:
        hh.setSectionResizeMode(stretch, QHeaderView.ResizeMode.Stretch)
    return t


def cell(text='', align=LEFT, color=None, bg=None, bold=False, data=None):
    it = QTableWidgetItem('' if text is None else str(text))
    it.setTextAlignment(align)
    if color is not None:
        it.setForeground(color)
    if bg is not None:
        it.setBackground(bg)
    if bold:
        f = it.font()
        f.setBold(True)
        it.setFont(f)
    if data is not None:
        it.setData(ID_ROLE, data)
    return it


def money_cell(v, kind=None, blank_zero=True, **kw):
    color = INCOME_COLOR if kind == 'in' else EXPENSE_COLOR if kind == 'out' else None
    if v is not None and v < 0 and kind is None:
        color = EXPENSE_COLOR
    return cell('' if v is None else fmt_money(v, blank_zero), RIGHT, color=kw.pop('color', color), **kw)


def fill(table, rows):
    """rows: [[QTableWidgetItem 또는 str, ...], ...]"""
    table.setSortingEnabled(False)
    hh = table.horizontalHeader()
    auto = [c for c in range(table.columnCount())
            if hh.sectionResizeMode(c) == QHeaderView.ResizeMode.ResizeToContents]
    for c in auto:        # 칸마다 폭을 다시 재지 않도록 잠시 끔 (수천 행에서 수 초 → 순간)
        hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
    table.setUpdatesEnabled(False)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            table.setItem(r, c, v if isinstance(v, QTableWidgetItem) else cell(v))
    table.setUpdatesEnabled(True)
    for c in auto:
        hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)


def selected_ids(table, col=0):
    rows = sorted({i.row() for i in table.selectedIndexes()})
    out = []
    for r in rows:
        it = table.item(r, col)
        if it is not None and it.data(ID_ROLE) is not None:
            out.append(it.data(ID_ROLE))
    return out


def table_rows(table):
    head = [table.horizontalHeaderItem(c).text().replace('\n', ' ') if table.horizontalHeaderItem(c) else ''
            for c in range(table.columnCount())]
    rows = []
    for r in range(table.rowCount()):
        rows.append([(table.item(r, c).text() if table.item(r, c) else '') for c in range(table.columnCount())])
    return head, rows


def export_csv(parent, table, name):
    import os
    path, _ = QFileDialog.getSaveFileName(parent, 'CSV로 저장', os.path.join(os.path.expanduser('~'), f'{name}.csv'),
                                          'CSV (*.csv)')
    if not path:
        return
    head, rows = table_rows(table)
    write_csv(path, head, rows)
    info(parent, f'저장했습니다:\n{path}\n\n리브레오피스 Calc·엑셀에서 바로 열 수 있습니다.')


def table_html(table, title, note=''):
    head, rows = table_rows(table)
    th = ''.join(f'<th>{html.escape(x)}</th>' for x in head)
    body = []
    for r in range(table.rowCount()):
        tds = []
        for c in range(table.columnCount()):
            it = table.item(r, c)
            txt = html.escape(it.text()) if it else ''
            right = it is not None and bool(it.textAlignment() & int(Qt.AlignmentFlag.AlignRight.value))
            bg = it.background().color().name() if it and it.background().style() != Qt.BrushStyle.NoBrush else None
            style = ('text-align:right;' if right else '') + (f'background:{bg};' if bg else '')
            tds.append(f'<td style="{style}">{txt}</td>')
        body.append('<tr>' + ''.join(tds) + '</tr>')
    return (f'<h3>{html.escape(title)}</h3><p style="color:#555">{html.escape(note)}</p>'
            '<table border="1" cellspacing="0" cellpadding="3" style="border-collapse:collapse;font-size:9pt">'
            f'<tr style="background:#dde4f0">{th}</tr>{"".join(body)}</table>')


def print_table(parent, table, title, note=''):
    from PyQt6.QtPrintSupport import QPrinter, QPrintPreviewDialog
    doc = QTextDocument()
    doc.setHtml(table_html(table, title, note))
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    if table.columnCount() > 7:
        from PyQt6.QtGui import QPageLayout
        printer.setPageOrientation(QPageLayout.Orientation.Landscape)
    dlg = QPrintPreviewDialog(printer, parent)
    dlg.setWindowTitle(f'인쇄 미리보기 — {title}  (PDF로 저장하려면 프린터에서 "PDF로 인쇄" 선택)')
    dlg.paintRequested.connect(doc.print)
    dlg.resize(1000, 800)
    dlg.exec()


# ── 메시지 ─────────────────────────────────────────────
def info(parent, text, title='알림'):
    QMessageBox.information(parent, title, text)


def error(parent, text, title='오류'):
    QMessageBox.warning(parent, title, text)


def confirm(parent, text, title='확인'):
    return QMessageBox.question(parent, title, text) == QMessageBox.StandardButton.Yes


# ── 범용 입력창 ────────────────────────────────────────
class FormDialog(QDialog):
    """fields: [(키, 이름, 형식)] 형식: text, text*(필수), money, date, int, choice:a|b, memo, password,
    active(사용중/사용안함), billmonth(전전월/전월/당월), bank(통장 목록)"""
    def __init__(self, parent, title, fields, values=None, con=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.fields, self.w = fields, {}
        values = values or {}
        form = QFormLayout()
        for key, label, kind in fields:
            v = values.get(key)
            if kind.startswith('choice:'):
                w = QComboBox()
                w.addItems(kind[7:].split('|'))
                if isinstance(v, int) and 0 <= v < w.count():
                    w.setCurrentIndex(v)
                elif isinstance(v, str) and w.findText(v) >= 0:
                    w.setCurrentIndex(w.findText(v))
            elif kind == 'active':
                w = QComboBox()
                w.addItems(['사용중 (자산으로 계산)', '사용안함 (자산 계산 안 함)'])
                w.setCurrentIndex(0 if v in (None, 1) else 1)
            elif kind == 'billmonth':
                w = QComboBox()
                w.addItems(['전전월', '전월', '당월'])
                w.setCurrentIndex((v if v is not None else -1) + 2)
            elif kind == 'bank':
                w = QComboBox()
                w.addItem('(없음)', None)
                if con:
                    for a in con.execute("SELECT id, company, name FROM account WHERE kind='bank' ORDER BY sort, id"):
                        w.addItem(f"{a['company']} {a['name']}".strip(), a['id'])
                i = w.findData(v)
                w.setCurrentIndex(max(0, i))
            elif kind == 'money':
                w = MoneyEdit()
                w.set_value(v or 0)
            elif kind == 'date':
                w = QWidget()
                lay = QHBoxLayout(w)
                lay.setContentsMargins(0, 0, 0, 0)
                w.chk = QCheckBox()
                w.de = DateEdit(v if v else None)
                w.chk.setChecked(bool(v))
                w.de.setEnabled(bool(v))
                w.chk.toggled.connect(w.de.setEnabled)
                lay.addWidget(w.chk)
                lay.addWidget(w.de, 1)
            elif kind == 'int':
                w = QSpinBox()
                w.setRange(0, 100000)
                w.setValue(int(v or 0))
            elif kind == 'memo':
                w = QPlainTextEdit(v or '')
                w.setMinimumHeight(70)
            else:
                w = QLineEdit('' if v is None else str(v))
                if kind == 'password':
                    w.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
            self.w[key] = w
            form.addRow(label + (' *' if kind == 'text*' else ''), w)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText('저장')
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText('취소')
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(bb)
        self.resize(460, self.sizeHint().height())

    def values(self):
        out = {}
        for key, label, kind in self.fields:
            w = self.w[key]
            if kind.startswith('choice:'):
                out[key] = w.currentIndex() if key in ('x.ptype',) else w.currentText()
            elif kind == 'active':
                out[key] = 1 if w.currentIndex() == 0 else 0
            elif kind == 'billmonth':
                out[key] = w.currentIndex() - 2
            elif kind == 'bank':
                out[key] = w.currentData()
            elif kind == 'money':
                out[key] = w.value()
            elif kind == 'date':
                out[key] = w.de.date_().isoformat() if w.chk.isChecked() else None
            elif kind == 'int':
                out[key] = w.value()
            elif kind == 'memo':
                out[key] = w.toPlainText().strip()
            else:
                out[key] = w.text().strip()
        return out

    def _ok(self):
        for key, label, kind in self.fields:
            if kind == 'money':
                try:
                    self.w[key].value()
                except ValueError:
                    error(self, f'{label}: 금액을 숫자로 입력하세요.')
                    return
            if kind == 'text*' and not self.w[key].text().strip():
                error(self, f'{label} 은(는) 꼭 입력해야 합니다.')
                return
        self.accept()


# ── 계정 다중 선택 ─────────────────────────────────────
class CodePicker(QDialog):
    """대분류를 체크하면 소분류 전체 선택 (원본 '계정코드 선택하기')."""
    def __init__(self, parent, con, lid, selected=()):
        super().__init__(parent)
        self.setWindowTitle('계정코드 선택')
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['계정'])
        gmap = L.group_map(con, lid)
        nodes = {}
        for g in L.groups(con, lid):
            n = QTreeWidgetItem([f"{g['code']}  {g['name']}"])
            n.setFlags(n.flags() | Qt.ItemFlag.ItemIsAutoTristate | Qt.ItemFlag.ItemIsUserCheckable)
            n.setCheckState(0, Qt.CheckState.Unchecked)
            self.tree.addTopLevelItem(n)
            nodes[g['code']] = n
        for c in L.categories(con, lid):
            parent_node = nodes.get(c['code'][:1])
            if parent_node is None:
                parent_node = QTreeWidgetItem([f"{c['code'][:1]}  {gmap.get(c['code'][:1], '?')}"])
                self.tree.addTopLevelItem(parent_node)
                nodes[c['code'][:1]] = parent_node
            it = QTreeWidgetItem([f"{c['code']}  {c['name']}"])
            it.setData(0, ID_ROLE, c['code'])
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(0, Qt.CheckState.Checked if c['code'] in selected else Qt.CheckState.Unchecked)
            parent_node.addChild(it)
        self.tree.expandAll()
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        clear = button('다시 설정', lambda: [self._set_all(Qt.CheckState.Unchecked)])
        lay = QVBoxLayout(self)
        lay.addWidget(self.tree)
        lay.addWidget(h(clear, 'stretch', bb))
        self.resize(360, 520)

    def _set_all(self, st):
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, st)

    def codes(self):
        out = []
        for i in range(self.tree.topLevelItemCount()):
            g = self.tree.topLevelItem(i)
            for k in range(g.childCount()):
                c = g.child(k)
                if c.checkState(0) == Qt.CheckState.Checked:
                    out.append(c.data(0, ID_ROLE))
        return out


class MonthNav(QWidget):
    """◀ 2026년 10월 ▶ [이번 달]"""
    changed = pyqtSignal(int, int)

    def __init__(self, parent=None, y=None, m=None):
        super().__init__(parent)
        t = dt.date.today()
        self.y, self.m = y or t.year, m or t.month
        self.lbl = QLabel()
        self.lbl.setObjectName('MonthLabel')      # 글꼴·크기는 테마 스타일시트에서 (theme.py)
        self.lbl.setAlignment(CENTER)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        for txt, d in (('◀', -1), (None, 0), ('▶', 1)):
            if txt is None:
                lay.addWidget(self.lbl)
            else:
                b = QPushButton(txt)
                b.setFixedWidth(34)
                b.clicked.connect(lambda _=False, d=d: self.shift(d))
                lay.addWidget(b)
        lay.addWidget(button('이번 달', self.this_month))
        self._upd()

    def shift(self, d):
        k = self.y * 12 + self.m - 1 + d
        self.y, self.m = k // 12, k % 12 + 1
        self._upd(True)

    def this_month(self):
        t = dt.date.today()
        self.y, self.m = t.year, t.month
        self._upd(True)

    def set(self, y, m):
        self.y, self.m = y, m
        self._upd(True)

    def _upd(self, emit=False):
        self.lbl.setText(f'{self.y}년 {self.m}월')
        if emit:
            self.changed.emit(self.y, self.m)
