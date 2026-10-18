"""기타 프로그램: 주소록·일기장·메모장."""
import datetime as dt

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QComboBox, QFormLayout, QGroupBox, QInputDialog, QLabel, QLineEdit, QPlainTextEdit,
                             QSplitter, QVBoxLayout, QWidget)

from .. import db
from ..services import calendar_svc as C
from ..util import WEATHER
from .widgets import (CENTER, DateEdit, FormDialog, MonthNav, button, cell, confirm, error, export_csv, fill, h,
                      make_table, print_table, selected_ids)

ADDR_FIELDS = [('name', '성명'), ('mobile', '휴대폰'), ('tel1', '전화1'), ('tel2', '전화2'), ('fax', '팩스번호'),
               ('email', '전자우편'), ('homepage', '홈페이지'), ('address', '주소'), ('zipcode', '우편번호'),
               ('memo', '메모'), ('grp', '그룹')]


class AddressPage(QWidget):
    title = '주소록'

    def __init__(self, app):
        super().__init__()
        self.app, self.con = app, app.con
        self.field = QComboBox()
        self.q = QLineEdit()
        self.q.setPlaceholderText('찾을 글자 (비우면 전체)')
        self.q.returnPressed.connect(self.refresh)
        self.table = make_table([], multi=True)
        self.table.doubleClicked.connect(lambda *_: self.edit())
        self.count = QLabel()
        lay = QVBoxLayout(self)
        lay.addWidget(h('찾기 조건', self.field, self.q, button('검색', self.refresh), 'stretch',
                        button('추가', self.add), button('수정', self.edit), button('삭제', self.delete),
                        button('항목 이름 바꾸기', self.rename), button('CSV', lambda: export_csv(self, self.table, '주소록')),
                        button('인쇄', lambda: print_table(self, self.table, '주소록'))))
        lay.addWidget(self.table, 1)
        lay.addWidget(self.count)

    def labels(self):
        custom = db.get_json(self.con, 'address_labels', {})
        return [(k, custom.get(k) or v) for k, v in ADDR_FIELDS]

    def refresh(self):
        labels = self.labels()
        cur = self.field.currentIndex()
        self.field.blockSignals(True)
        self.field.clear()
        self.field.addItem('전체 항목', None)
        for k, v in labels:
            self.field.addItem(v, k)
        self.field.setCurrentIndex(max(0, cur))
        self.field.blockSignals(False)
        self.table.setColumnCount(len(labels))
        self.table.setHorizontalHeaderLabels([v for _, v in labels])
        q = self.q.text().strip()
        where, args = '', ()
        if q:
            k = self.field.currentData()
            like = f'%{q}%'
            if k:
                where, args = f'{k} LIKE ?', (like,)
            else:
                where = ' OR '.join(f'{k} LIKE ?' for k, _ in ADDR_FIELDS)
                args = (like,) * len(ADDR_FIELDS)
        rows = C.simple_list(self.con, 'contact', 'name', where, args)
        fill(self.table, [[cell(r[k], data=r['id'] if i == 0 else None) for i, (k, _) in enumerate(labels)] for r in rows])
        self.count.setText(f'{len(rows)}명')

    def _dialog(self, title, values=None):
        d = FormDialog(self, title, [(k, v, 'text*' if k == 'name' else 'memo' if k == 'memo' else 'text')
                                     for k, v in self.labels()], values)
        return d.values() if d.exec() else None

    def add(self):
        v = self._dialog('주소록 추가')
        if v:
            C.simple_save(self.con, 'contact', v)
            self.refresh()

    def edit(self):
        ids = selected_ids(self.table)
        if not ids:
            return
        r = dict(self.con.execute('SELECT * FROM contact WHERE id=?', (ids[0],)).fetchone())
        v = self._dialog('주소록 수정', r)
        if v:
            C.simple_save(self.con, 'contact', v, ids[0])
            self.refresh()

    def delete(self):
        ids = selected_ids(self.table)
        if ids and confirm(self, f'{len(ids)}명을 삭제할까요?'):
            for i in ids:
                C.simple_delete(self.con, 'contact', i)
            self.refresh()

    def rename(self):
        """원본 '이름 바꾸기': 안 쓰는 항목 이름을 바꿔 다른 용도로 (예: 전자우편 → 생일)."""
        labels = self.labels()
        names = [v for _, v in labels[1:]]
        name, ok = QInputDialog.getItem(self, '항목 이름 바꾸기', '바꿀 항목', names, 0, False)
        if not ok:
            return
        key = labels[1:][names.index(name)][0]
        new, ok = QInputDialog.getText(self, '항목 이름 바꾸기', f"'{name}' 의 새 이름 (비우면 원래대로)")
        if ok:
            custom = db.get_json(self.con, 'address_labels', {})
            if new.strip():
                custom[key] = new.strip()
            else:
                custom.pop(key, None)
            db.set_json(self.con, 'address_labels', custom)
            self.con.commit()
            self.refresh()


class DiaryPage(QWidget):
    title = '일기장'

    def __init__(self, app):
        super().__init__()
        self.app, self.con = app, app.con
        self.editing = None
        self.nav = MonthNav()
        self.nav.changed.connect(lambda *_: self.refresh())
        self.q = QLineEdit()
        self.q.setPlaceholderText('제목·내용 검색 (비우면 이달 목록)')
        self.q.returnPressed.connect(self.refresh)
        self.list = make_table(['날짜', '날씨', '제목'], stretch=2)
        self.list.itemSelectionChanged.connect(self._sel)
        self.date = DateEdit()
        self.weather = QComboBox()
        self.weather.addItems(WEATHER)
        self.title_e = QLineEdit()
        self.content = QPlainTextEdit()
        self.save_btn = button('일기 저장', self.save)
        right = QGroupBox('일기 쓰기')
        f = QFormLayout(right)
        f.addRow(h(button('어제', lambda: self.jump(-1)), button('오늘', lambda: self.jump(0)),
                   button('내일', lambda: self.jump(1)), 'stretch'))
        f.addRow('날짜', h(self.date, '날씨', self.weather, 'stretch'))
        f.addRow('제목', self.title_e)
        f.addRow(self.content)
        f.addRow(h(self.save_btn, button('새로 쓰기', self.new), button('삭제', self.delete), 'stretch'))
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(self.nav)
        ll.addWidget(h(self.q, button('검색', self.refresh)))
        ll.addWidget(self.list, 1)
        ll.addWidget(button('CSV', lambda: export_csv(self, self.list, '일기장')))
        sp = QSplitter()
        sp.addWidget(left)
        sp.addWidget(right)
        sp.setStretchFactor(1, 2)
        QVBoxLayout(self).addWidget(sp)

    def refresh(self):
        q = self.q.text().strip()
        if q:
            rows = C.simple_list(self.con, 'diary', 'date DESC', 'title LIKE ? OR content LIKE ?', (f'%{q}%',) * 2)
        else:
            ym = f'{self.nav.y:04d}-{self.nav.m:02d}'
            rows = C.simple_list(self.con, 'diary', 'date DESC', 'substr(date,1,7)=?', (ym,))
        fill(self.list, [[cell(r['date'], CENTER, data=r['id']),
                          cell(WEATHER[r['weather']] if 0 <= r['weather'] < len(WEATHER) else '', CENTER),
                          cell(r['title'] or (r['content'] or '').split('\n')[0][:30])] for r in rows])

    def _sel(self):
        ids = selected_ids(self.list)
        if not ids:
            return
        r = self.con.execute('SELECT * FROM diary WHERE id=?', (ids[0],)).fetchone()
        self.editing = r['id']
        self.date.set_date(r['date'])
        self.weather.setCurrentIndex(r['weather'] if 0 <= r['weather'] < len(WEATHER) else 0)
        self.title_e.setText(r['title'])
        self.content.setPlainText(r['content'])
        self.save_btn.setText('수정 저장')

    def jump(self, delta):
        d = dt.date.today() + dt.timedelta(days=delta)
        r = self.con.execute('SELECT id FROM diary WHERE date=? ORDER BY id LIMIT 1', (d.isoformat(),)).fetchone()
        self.nav.set(d.year, d.month)
        if r:
            for i in range(self.list.rowCount()):
                if self.list.item(i, 0).data(Qt.ItemDataRole.UserRole) == r['id']:
                    self.list.selectRow(i)
                    return
        self.new()
        self.date.set_date(d)

    def reset_state(self):
        self.new()

    def new(self):
        self.editing = None
        self.list.clearSelection()
        self.title_e.clear()
        self.content.clear()
        self.save_btn.setText('일기 저장')

    def save(self):
        v = {'date': self.date.date_().isoformat(), 'weather': self.weather.currentIndex(),
             'title': self.title_e.text().strip(), 'content': self.content.toPlainText().strip()}
        if not v['title'] and not v['content']:
            error(self, '제목이나 내용을 입력하세요.')
            return
        C.simple_save(self.con, 'diary', v, self.editing)
        d = self.date.date_()
        self.nav.set(d.year, d.month)
        self.new()

    def delete(self):
        if self.editing and confirm(self, '이 일기를 삭제할까요?'):
            C.simple_delete(self.con, 'diary', self.editing)
            self.new()
            self.refresh()


class MemoPage(QWidget):
    title = '메모장'

    def __init__(self, app):
        super().__init__()
        self.app, self.con = app, app.con
        self.editing = None
        self.q = QLineEdit()
        self.q.setPlaceholderText('제목·내용 검색')
        self.q.returnPressed.connect(self.refresh)
        self.order = QComboBox()
        self.order.addItems(['입력순', '제목순', '최근 작성순'])
        self.order.currentIndexChanged.connect(lambda *_: self.refresh())
        self.list = make_table(['제목', '작성일시'], stretch=0)
        self.list.itemSelectionChanged.connect(self._sel)
        self.title_e = QLineEdit()
        self.content = QPlainTextEdit()
        self.save_btn = button('메모 추가', self.save)
        right = QGroupBox('메모')
        f = QFormLayout(right)
        f.addRow('제목', self.title_e)
        f.addRow(self.content)
        f.addRow(h(self.save_btn, button('새로 작성', self.new), button('삭제', self.delete), 'stretch'))
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.addWidget(h(self.q, self.order))
        ll.addWidget(self.list, 1)
        ll.addWidget(h(button('위로', lambda: self.move(-1)), button('아래로', lambda: self.move(1)), 'stretch',
                       button('CSV', self.export)))
        sp = QSplitter()
        sp.addWidget(left)
        sp.addWidget(right)
        sp.setStretchFactor(1, 2)
        QVBoxLayout(self).addWidget(sp)

    def refresh(self):
        order = ['sort, id', 'title, id', 'created DESC, id DESC'][self.order.currentIndex()]
        q = self.q.text().strip()
        rows = C.simple_list(self.con, 'memo', order, 'title LIKE ? OR content LIKE ?' if q else '',
                             (f'%{q}%',) * 2 if q else ())
        fill(self.list, [[cell(r['title'] or (r['content'] or '').split('\n')[0][:30], data=r['id']),
                          cell(r['created'] or '', CENTER)] for r in rows])

    def _sel(self):
        ids = selected_ids(self.list)
        if not ids:
            return
        r = self.con.execute('SELECT * FROM memo WHERE id=?', (ids[0],)).fetchone()
        self.editing = r['id']
        self.title_e.setText(r['title'])
        self.content.setPlainText(r['content'])
        self.save_btn.setText('메모 수정')

    def reset_state(self):
        self.new()

    def new(self):
        self.editing = None
        self.list.clearSelection()
        self.title_e.clear()
        self.content.clear()
        self.save_btn.setText('메모 추가')
        self.title_e.setFocus()

    def save(self):
        v = {'title': self.title_e.text().strip(), 'content': self.content.toPlainText().strip()}
        if not v['title'] and not v['content']:
            error(self, '제목이나 내용을 입력하세요.')
            return
        if not self.editing:
            v['created'] = f'{dt.datetime.now():%Y-%m-%d %H:%M}'
            v['sort'] = self.con.execute('SELECT COALESCE(MAX(sort),0)+1 FROM memo').fetchone()[0]
        C.simple_save(self.con, 'memo', v, self.editing)
        self.new()
        self.refresh()

    def delete(self):
        if self.editing and confirm(self, '이 메모를 삭제할까요?'):
            C.simple_delete(self.con, 'memo', self.editing)
            self.new()
            self.refresh()

    def move(self, d):
        ids = selected_ids(self.list)
        if ids:
            from ..services.assets import move
            move(self.con, 'memo', ids[0], d)
            self.order.setCurrentIndex(0)
            self.refresh()
            for i in range(self.list.rowCount()):
                if self.list.item(i, 0).data(Qt.ItemDataRole.UserRole) == ids[0]:
                    self.list.selectRow(i)

    def export(self):
        t = make_table(['제목', '작성일시', '내용'])
        fill(t, [[r['title'], r['created'] or '', r['content']] for r in C.simple_list(self.con, 'memo', 'sort, id')])
        export_csv(self, t, '메모장')
