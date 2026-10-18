"""설정(원본 '기본작업'): 계정과목·장부관리·품목관리·암호·백업/복원·가져오기."""
import os
import shutil
import tempfile

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox, QInputDialog,
                             QLabel, QLineEdit, QPlainTextEdit, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from .. import db
from ..services import backup as B
from ..services import importer as I
from ..services import ledger as L
from ..util import CODE_CHARS, check_password, hash_password
from .widgets import (CENTER, button, cell, confirm, error, fill, h, info, make_table, selected_ids)


class CategoryTab(QWidget):
    """대분류(0~9, a~z; 0=수입) · 소분류(대분류+한 자리) 관리."""
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.gt = make_table(['코드', '대분류'], stretch=1)
        self.gt.itemSelectionChanged.connect(self.load_cats)
        self.ct = make_table(['계정코드', '계정과목', '사용 건수'], stretch=1)
        self.info = QLabel('대분류 0번은 수입, 나머지(1~9, a~z)는 지출입니다. 계정코드 = 대분류 + 소분류 한 자리')
        self.info.setStyleSheet('color:#666')
        gbox = QGroupBox('대분류')
        gl = QVBoxLayout(gbox)
        gl.addWidget(self.gt)
        gl.addWidget(h(button('추가', self.add_group), button('이름 변경', self.rename_group),
                       button('삭제', self.del_group)))
        cbox = QGroupBox('소분류 (계정과목)')
        cl = QVBoxLayout(cbox)
        cl.addWidget(self.ct)
        cl.addWidget(h(button('추가', self.add_cat), button('이름 변경', self.rename_cat),
                       button('위로', lambda: self.move(-1)), button('아래로', lambda: self.move(1)),
                       button('다른 계정으로 합치기', self.merge), button('삭제', self.del_cat)))
        lay = QVBoxLayout(self)
        lay.addWidget(self.info)
        lay.addWidget(h(gbox, cbox))

    @property
    def con(self):
        return self.page.con

    @property
    def lid(self):
        return self.page.app.lid

    def group(self):
        ids = selected_ids(self.gt)
        return ids[0] if ids else None

    def code(self):
        ids = selected_ids(self.ct)
        return ids[0] if ids else None

    def refresh(self):
        cur = self.group()
        fill(self.gt, [[cell(g['code'], CENTER, data=g['code']), cell(g['name'])] for g in L.groups(self.con, self.lid)])
        for r in range(self.gt.rowCount()):
            if self.gt.item(r, 0).data(Qt.ItemDataRole.UserRole) == (cur or '0'):
                self.gt.selectRow(r)
        self.load_cats()

    def load_cats(self):
        g = self.group()
        rows = L.categories(self.con, self.lid, g) if g is not None else []
        fill(self.ct, [[cell(c['code'], CENTER, data=c['code']), cell(c['name']),
                        cell(L.category_usage(self.con, self.lid, c['code'])['entry'], CENTER)] for c in rows])

    def add_group(self):
        used = {g['code'] for g in L.groups(self.con, self.lid)}
        free = [c for c in CODE_CHARS[1:] if c not in used]
        if not free:
            error(self, '더 만들 수 있는 대분류가 없습니다 (최대 36개).')
            return
        name, ok = QInputDialog.getText(self, '대분류 추가', f'새 대분류 이름 (코드 {free[0]})')
        if ok and name.strip():
            L.set_group(self.con, self.lid, free[0], name.strip())
            self.page.changed()

    def rename_group(self):
        g = self.group()
        if g is None or g == '0':
            if g == '0':
                error(self, '0번(수입) 대분류 이름은 바꿀 수 없습니다.')
            return
        name, ok = QInputDialog.getText(self, '대분류 이름 변경', '새 이름', text=L.group_map(self.con, self.lid)[g])
        if ok and name.strip():
            L.set_group(self.con, self.lid, g, name.strip())
            self.page.changed()

    def del_group(self):
        g = self.group()
        if g is None:
            return
        try:
            if confirm(self, f'대분류 {g} 를 삭제할까요?'):
                L.delete_group(self.con, self.lid, g)
                self.page.changed()
        except ValueError as e:
            error(self, str(e))

    def add_cat(self):
        g = self.group()
        if g is None:
            error(self, '먼저 왼쪽에서 대분류를 고르세요.')
            return
        used = {c['code'] for c in L.categories(self.con, self.lid, g)}
        free = [g + c for c in CODE_CHARS if g + c not in used]
        if not free:
            error(self, '이 대분류에는 더 만들 수 없습니다 (최대 36개).')
            return
        name, ok = QInputDialog.getText(self, '소분류 추가', f'새 계정과목 이름 (계정코드 {free[0]})')
        if ok and name.strip():
            L.set_category(self.con, self.lid, free[0], name.strip())
            self.page.changed()

    def rename_cat(self):
        c = self.code()
        if not c:
            return
        name, ok = QInputDialog.getText(self, '계정과목 이름 변경', '새 이름', text=L.category_map(self.con, self.lid)[c])
        if ok and name.strip():
            L.set_category(self.con, self.lid, c, name.strip())
            self.page.changed()

    def move(self, d):
        c = self.code()
        if c:
            L.move_category_order(self.con, self.lid, c, d)
            self.load_cats()
            for r in range(self.ct.rowCount()):
                if self.ct.item(r, 0).data(Qt.ItemDataRole.UserRole) == c:
                    self.ct.selectRow(r)

    def merge(self):
        c = self.code()
        if not c:
            return
        cmap = L.category_map(self.con, self.lid)
        choices = [f'{k}  {v}' for k, v in sorted(cmap.items()) if k != c]
        pick, ok = QInputDialog.getItem(self, '다른 계정으로 합치기',
                                        f"'{cmap[c]}'({c})로 입력된 모든 내역·예약·예산을 옮길 계정", choices, 0, False)
        if ok and pick and confirm(self, f"{c} {cmap[c]} → {pick}\n옮긴 뒤 {c} 계정은 없어집니다. 계속할까요?"):
            L.merge_category(self.con, self.lid, c, pick.split()[0])
            self.page.changed()

    def del_cat(self):
        c = self.code()
        if not c:
            return
        u = L.category_usage(self.con, self.lid, c)
        msg = f'계정 {c} 를 삭제할까요?'
        if any(u.values()):
            msg += (f"\n\n주의: 이 계정으로 입력된 내역 {u['entry']}건, 예약 {u['recurring']}건, 예산 {u['budget']}건도 "
                    '함께 삭제됩니다 (원본 프로그램과 같은 동작).\n지우지 않으려면 [다른 계정으로 합치기]를 쓰세요.')
        if confirm(self, msg):
            L.delete_category(self.con, self.lid, c)
            self.page.changed()


class LedgerTab(QWidget):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.t = make_table(['장부명', '내역 수', '잔액'], stretch=0)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel('가계부 외에 모임 회비·용돈 등 장부를 여러 개 따로 관리할 수 있습니다. '
                             '첫 번째 장부는 삭제할 수 없습니다.'))
        lay.addWidget(self.t)
        lay.addWidget(h(button('장부 추가', self.add), button('이름 변경', self.rename), button('장부 복사', self.copy),
                        button('계정과목만 복사', lambda: self.copy(True)), button('데이터 초기화', self.reset),
                        button('장부 삭제', self.delete), 'stretch'))

    @property
    def con(self):
        return self.page.con

    def lid(self):
        ids = selected_ids(self.t)
        return ids[0] if ids else None

    def refresh(self):
        from ..util import fmt_money
        fill(self.t, [[cell(r['name'], data=r['id']),
                       cell(self.con.execute('SELECT COUNT(*) FROM entry WHERE ledger_id=?', (r['id'],)).fetchone()[0],
                            CENTER),
                       cell(fmt_money(L.current_balance(self.con, r['id'])), Qt.AlignmentFlag.AlignRight)]
                      for r in L.ledgers(self.con)])

    def _name(self, title, text=''):
        name, ok = QInputDialog.getText(self, title, '장부 이름', text=text)
        return name.strip() if ok and name.strip() else None

    def add(self):
        n = self._name('장부 추가')
        if n:
            L.add_ledger(self.con, n)
            info(self, '새 장부를 만들었습니다. 계정과목 탭에서 계정을 설계하세요 (또는 [계정과목만 복사] 사용).')
            self.page.ledgers_changed()

    def rename(self):
        lid = self.lid()
        if lid:
            n = self._name('장부명 변경', self.t.item(self.t.currentRow(), 0).text())
            if n:
                L.rename_ledger(self.con, lid, n)
                self.page.ledgers_changed()

    def copy(self, codes_only=False):
        lid = self.lid()
        if not lid:
            error(self, '복사할 장부를 고르세요.')
            return
        src = self.t.item(self.t.currentRow(), 0).text()
        n = self._name('계정과목만 복사' if codes_only else '장부 복사', f'{src} 복사본')
        if n:
            L.add_ledger(self.con, n, copy_from=lid, codes_only=codes_only)
            self.page.ledgers_changed()

    def reset(self):
        lid = self.lid()
        if lid and confirm(self, '선택한 장부의 수입/지출·예산·예약을 모두 지울까요? (계정과목은 남습니다)\n되돌릴 수 없습니다.'):
            L.reset_ledger(self.con, lid)
            self.page.ledgers_changed()

    def delete(self):
        lid = self.lid()
        if not lid:
            return
        try:
            if confirm(self, '선택한 장부를 완전히 삭제할까요? 되돌릴 수 없습니다.'):
                L.delete_ledger(self.con, lid)
                self.page.ledgers_changed()
        except ValueError as e:
            error(self, str(e))


class ItemTab(QWidget):
    """품목 관리(자동입력): 사용횟수가 기준 이상인 품목만 입력할 때 자동완성."""
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.t = make_table(['품목', '사용 횟수'], stretch=0)
        self.min = QSpinBox()
        self.min.setRange(1, 999)
        self.min.valueChanged.connect(self._min)
        lay = QVBoxLayout(self)
        lay.addWidget(h('자동완성에 보일 최소 사용 횟수', self.min, 'stretch', button('추가', self.add),
                        button('수정', self.edit), button('삭제', self.delete)))
        lay.addWidget(self.t)

    @property
    def con(self):
        return self.page.con

    def refresh(self):
        self.min.blockSignals(True)
        self.min.setValue(int(db.get_meta(self.con, 'item_min_count', 1) or 1))
        self.min.blockSignals(False)
        fill(self.t, [[cell(w['name'], data=w['name']), cell(w['count'], CENTER)]
                      for w in L.item_words(self.con, self.page.app.lid)])

    def _min(self, v):
        db.set_meta(self.con, 'item_min_count', v)
        self.con.commit()
        self.page.app.data_changed()

    def add(self):
        n, ok = QInputDialog.getText(self, '품목 추가', '품목 이름')
        if ok and n.strip():
            L.set_item_word(self.con, self.page.app.lid, n.strip(), self.min.value())
            self.refresh()

    def edit(self):
        ids = selected_ids(self.t)
        if not ids:
            return
        n, ok = QInputDialog.getText(self, '품목 수정', '품목 이름', text=ids[0])
        if not ok or not n.strip():
            return
        cnt, ok = QInputDialog.getInt(self, '품목 수정', '사용 횟수', int(self.t.item(self.t.currentRow(), 1).text()), 0)
        if ok:
            L.set_item_word(self.con, self.page.app.lid, n.strip(), cnt, ids[0])
            self.refresh()

    def delete(self):
        ids = selected_ids(self.t)
        if ids:
            L.delete_item_word(self.con, self.page.app.lid, ids[0])
            self.refresh()


class GeneralTab(QWidget):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.pw_state = QLabel()
        pw = QGroupBox('시작 암호')
        pl = QVBoxLayout(pw)
        pl.addWidget(self.pw_state)
        pl.addWidget(h(button('암호 설정/변경', self.set_pw), button('암호 해제', self.clear_pw), 'stretch'))
        pl.addWidget(QLabel('암호는 복구할 방법이 없으니 잘 기억해 두세요. (저장은 원문이 아닌 해시로 합니다)'))
        self.bk_dir = QLineEdit()
        self.bk_exit = QCheckBox('프로그램을 끌 때 자동 백업 (원본의 [백업 후 종료])')
        self.bk_exit.toggled.connect(self._save_exit)
        bk = QGroupBox('백업 · 복원')
        bl = QFormLayout(bk)
        bl.addRow('백업 폴더', h(self.bk_dir, button('찾기…', self._pick_dir)))
        bl.addRow(self.bk_exit)
        bl.addRow(h(button('지금 백업하기', self.backup), button('백업 파일로 복원하기…', self.restore), 'stretch'))
        self.db_lbl = QLabel()
        self.db_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay = QVBoxLayout(self)
        lay.addWidget(pw)
        lay.addWidget(bk)
        lay.addWidget(self.db_lbl)
        lay.addStretch(1)

    @property
    def con(self):
        return self.page.con

    def refresh(self):
        self.pw_state.setText('현재: 암호 사용 중' if db.get_meta(self.con, 'password') else '현재: 암호 없음')
        default = os.path.join(os.path.expanduser('~'), '우리집가계부_백업')
        self.bk_dir.setText(db.get_meta(self.con, 'backup_dir') or default)
        self.bk_exit.blockSignals(True)
        self.bk_exit.setChecked(bool(db.get_meta(self.con, 'backup_on_exit')))
        self.bk_exit.blockSignals(False)
        self.db_lbl.setText(f'데이터 파일: {self.page.app.db_path}')

    def set_pw(self):
        cur = db.get_meta(self.con, 'password')
        if cur:
            old, ok = QInputDialog.getText(self, '암호 변경', '현재 암호', QLineEdit.EchoMode.Password)
            if not ok:
                return
            if not check_password(old, cur):
                error(self, '현재 암호가 틀렸습니다.')
                return
        a, ok = QInputDialog.getText(self, '암호 설정', '새 암호', QLineEdit.EchoMode.Password)
        if not ok or not a:
            return
        b, ok = QInputDialog.getText(self, '암호 설정', '새 암호 확인', QLineEdit.EchoMode.Password)
        if not ok:
            return
        if a != b:
            error(self, '두 암호가 다릅니다.')
            return
        db.set_meta(self.con, 'password', hash_password(a))
        self.con.commit()
        info(self, '암호를 설정했습니다. 다음 실행부터 암호를 물어봅니다.')
        self.refresh()

    def clear_pw(self):
        cur = db.get_meta(self.con, 'password')
        if not cur:
            return
        old, ok = QInputDialog.getText(self, '암호 해제', '현재 암호', QLineEdit.EchoMode.Password)
        if ok and check_password(old, cur):
            db.set_meta(self.con, 'password', None)
            self.con.commit()
            self.refresh()
        elif ok:
            error(self, '암호가 틀렸습니다.')

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, '백업 폴더', self.bk_dir.text())
        if d:
            self.bk_dir.setText(d)
            db.set_meta(self.con, 'backup_dir', d)
            self._save_exit(self.bk_exit.isChecked())

    def _save_exit(self, on):
        db.set_meta(self.con, 'backup_dir', self.bk_dir.text())
        db.set_meta(self.con, 'backup_on_exit', self.bk_dir.text() if on else None)
        self.con.commit()

    def backup(self):
        try:
            os.makedirs(self.bk_dir.text(), exist_ok=True)
            p = B.backup(self.con, self.bk_dir.text())
            db.set_meta(self.con, 'backup_dir', self.bk_dir.text())
            self.con.commit()
            info(self, f'백업했습니다:\n{p}')
        except OSError as e:
            error(self, f'백업 실패: {e}')

    def restore(self):
        p, _ = QFileDialog.getOpenFileName(self, '복원할 백업 파일', self.bk_dir.text(), '가계부 데이터 (*.sqlite3)')
        if not p:
            return
        if not B.validate_db(p):
            error(self, '우리집 가계부(새 버전) 백업 파일이 아닙니다.')
            return
        if confirm(self, '지금 데이터를 이 백업으로 바꿀까요?\n(현재 데이터는 자동으로 따로 보관합니다)'):
            try:
                kept = self.page.app.replace_db(p)
            except (ValueError, OSError) as e:
                error(self, f'복원하지 못했습니다 (현재 데이터는 그대로입니다):\n{e}')
                return
            info(self, f'복원했습니다. 복원 전 데이터 보관 위치:\n{kept}\n\n복원된 시점의 암호를 쓰세요.')


class ImportTab(QWidget):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        win = QGroupBox('윈도우 "우리집 가계부"에서 쓰던 자료 가져오기')
        wl = QVBoxLayout(win)
        wl.addWidget(QLabel('윈도우의 <b>우리집 가계부\\data</b> 폴더(main.mdb, homemaster.mdb, asset.mdb …)를 고르세요.<br>'
                            '윈도우 7 이후라면 <b>C:\\Users\\(사용자)\\AppData\\Local\\VirtualStore\\Program Files (x86)\\'
                            '우리집 가계부\\data</b> 쪽이 최신일 수 있습니다.<br>'
                            '가져오면 <b>지금 데이터를 대신</b>합니다 (현재 데이터는 자동 보관). 원본 .mdb 는 바뀌지 않습니다.'))
        wl.addWidget(h(button('data 폴더 선택해서 가져오기…', self.import_mdb), 'stretch'))
        csvb = QGroupBox('CSV 내역 불러오기 (원본의 엑셀데이타 불러오기)')
        cl = QVBoxLayout(csvb)
        cl.addWidget(QLabel('열 순서: 날짜, 품목, 수입, 지출, 계정코드 (계정과목·메모는 있어도 되고 없어도 됨). '
                            '리브레오피스/엑셀에서 CSV로 저장하세요.\n오류가 하나라도 있으면 저장하지 않고 오류 위치를 보여줍니다.'))
        cl.addWidget(h(button('CSV 파일 선택…', self.import_csv), 'stretch'))
        lay = QVBoxLayout(self)
        lay.addWidget(win)
        lay.addWidget(csvb)
        lay.addWidget(QLabel('결과'))
        lay.addWidget(self.out, 1)

    def refresh(self):
        pass

    def import_mdb(self):
        if not I.have_mdbtools():
            error(self, '자료 읽기 도구(tools/mdbtools)가 없습니다. 프로그램을 다시 설치해 주세요.' if os.name == 'nt'
                  else 'mdbtools 가 필요합니다. 터미널에서:\n  sudo apt install mdbtools')
            return
        d = QFileDialog.getExistingDirectory(self, '윈도우 우리집 가계부의 data 폴더')
        if not d:
            return
        if not I.find_file(d, 'main.mdb') and not any(f.lower().endswith('.mdb') for f in os.listdir(d)):
            error(self, '이 폴더에는 .mdb 파일이 없습니다. data 폴더를 고르세요.')
            return
        if not confirm(self, '가져온 자료로 현재 데이터를 바꿉니다. (현재 데이터는 자동 보관)\n계속할까요?'):
            return
        tmpdir = tempfile.mkdtemp(prefix='gagyebu-import-', dir=os.path.dirname(self.page.app.db_path))
        tmp = os.path.join(tmpdir, 'import.sqlite3')
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            rep = I.import_folder(d, tmp)
        except Exception as e:      # mdbtools 오류 등은 그대로 보여 줌
            QApplication.restoreOverrideCursor()
            shutil.rmtree(tmpdir, ignore_errors=True)
            error(self, f'가져오기 실패:\n{e}')
            return
        QApplication.restoreOverrideCursor()
        kept = self.page.app.replace_db(tmp)
        shutil.rmtree(tmpdir, ignore_errors=True)
        self.out.setPlainText(rep.text() + (f'\n\n이전 데이터 보관: {kept}' if kept else ''))
        info(self, '가져오기를 마쳤습니다. 결과 창의 [확인 필요] 항목을 살펴보세요.')
        self.page.app.check_recurring()

    def import_csv(self):
        p, _ = QFileDialog.getOpenFileName(self, 'CSV 파일', os.path.expanduser('~'), 'CSV (*.csv *.txt)')
        if not p:
            return
        app = self.page.app
        rows, errs = B.read_entries_csv(p, set(L.category_map(app.con, app.lid)))
        if errs:
            self.out.setPlainText(f'오류 {len(errs)}개 — 하나도 저장하지 않았습니다.\n' +
                                  '\n'.join(f'  {n}번째 줄: {m}' for n, m in errs[:200]))
            error(self, f'오류가 {len(errs)}개 있어 저장하지 않았습니다. 결과 창을 보고 고쳐 주세요.')
            return
        if confirm(self, f'{len(rows)}건을 [{app.ledger_name()}] 장부에 입력할까요?'):
            for r in rows:
                L.add_entry(app.con, app.lid, r, origin='csv', commit=False)
            app.con.commit()
            self.out.setPlainText(f'{len(rows)}건을 입력했습니다.')
            app.data_changed()


class ThemeTab(QWidget):
    """화면 꾸미기: 테마(미니홈피/기본), 글꼴, 전광판, 미니미."""

    def __init__(self, page):
        super().__init__()
        self.page = page
        from .. import theme as T
        self.T = T
        self.theme = QComboBox()
        self.theme.addItem('미니홈피 (2000년대 감성)', 'retro')
        self.theme.addItem('기본 (처음 화면)', 'basic')
        self.font = QComboBox()
        self.font.addItem('도트 글꼴 (갈무리11)', 'pixel')
        self.font.addItem('시스템 글꼴', 'system')
        self.marquee = QCheckBox('맨 위 전광판 글씨 흐르게 하기')
        self.minimi = QLabel()
        self.minimi.setFixedSize(110, 100)
        self.minimi.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box = QGroupBox('화면 꾸미기')
        fl = QFormLayout(box)
        fl.addRow('테마', self.theme)
        fl.addRow('글꼴', self.font)
        fl.addRow('', self.marquee)
        fl.addRow('미니미', h(self.minimi, button('바꾸기…', self.pick), 'stretch'))
        self.note = QLabel()
        self.note.setWordWrap(True)
        credit = QLabel('스티커 그림: 사용자가 넣어 준 고양이 스티커 시트에서 오려 낸 것 (assets/stickers)\n'
                        '도트 글꼴: 갈무리(Galmuri) — SIL Open Font License 1.1 (assets/fonts/OFL-Galmuri.txt)')
        credit.setStyleSheet('color:#777')
        lay = QVBoxLayout(self)
        lay.addWidget(box)
        lay.addWidget(self.note)
        lay.addStretch(1)
        lay.addWidget(credit)
        self.theme.currentIndexChanged.connect(self._changed)
        self.font.currentIndexChanged.connect(self._changed)
        self.marquee.toggled.connect(self._changed)

    def refresh(self):
        T = self.T
        for w in (self.theme, self.font, self.marquee):
            w.blockSignals(True)
        self.theme.setCurrentIndex(max(0, self.theme.findData(T.pref('theme'))))
        self.font.setCurrentIndex(max(0, self.font.findData(T.pref('font'))))
        self.marquee.setChecked(T.pref('marquee'))
        for w in (self.theme, self.font, self.marquee):
            w.blockSignals(False)
        retro = T.pref('theme') == 'retro'
        self.font.setEnabled(retro)
        self.marquee.setEnabled(retro)
        self.minimi.setPixmap(T.sticker_pixmap(T.pref('minimi'), 96))
        fam = T.load_fonts()
        self.note.setText('· 바꾸면 바로 적용됩니다. 글꼴·전광판은 미니홈피 테마에서만 쓰입니다.\n'
                          '· 프로필의 ◀ 단추로 프로필을 접을 수 있습니다 (좁은 화면에서 유용).'
                          + ('' if fam else '\n· 도트 글꼴 파일을 불러오지 못해 시스템 글꼴을 씁니다.'))

    def _changed(self, *_):
        T = self.T
        T.set_pref('theme', self.theme.currentData())
        T.set_pref('font', self.font.currentData())
        T.set_pref('marquee', self.marquee.isChecked())
        self.page.app.apply_theme()
        self.refresh()

    def pick(self):
        from .hompy import StickerPicker
        dlg = StickerPicker(self, self.T.pref('minimi'))
        if dlg.exec() and dlg.selected():
            self.T.set_pref('minimi', dlg.selected())
            self.page.app.profile.load_prefs()
            self.refresh()


class SettingsPage(QWidget):
    title = '설정'

    def __init__(self, app):
        super().__init__()
        self.app, self.con = app, app.con
        self.tabs = QTabWidget()
        self.parts = [CategoryTab(self), LedgerTab(self), ItemTab(self), GeneralTab(self), ImportTab(self),
                      ThemeTab(self)]
        for p, n in zip(self.parts, ['계정과목', '장부 관리', '품목 관리', '암호 · 백업', '자료 가져오기', '화면 꾸미기']):
            self.tabs.addTab(p, n)
        self.tabs.currentChanged.connect(lambda i: self.parts[i].refresh())
        QVBoxLayout(self).addWidget(self.tabs)

    def refresh(self):
        self.parts[self.tabs.currentIndex()].refresh()

    def changed(self):
        self.refresh()
        self.app.data_changed()

    def ledgers_changed(self):
        self.app.reload_ledgers()
        self.refresh()
        self.app.data_changed()
