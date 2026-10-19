"""새 버전 알림 · 내려받기 · 설치 (PC판 화면 쪽). 실제 작업은 services/update.py

흐름 (켤 때 자동 확인과 설정 → 업데이트의 [업데이트 확인] 이 같음)
  확인 → 새 버전이 있으면 '업데이트 내용'을 보여 주고 "업데이트하시겠습니까?" (예/아니요)
       → 아니요: (자동 확인일 때) "설정 → 업데이트에서 직접 확인·내려받기·설치할 수 있다" 안내
       → 예: 내려받기(진행 막대) → "지금 설치할까요?" (예/아니요)
             → 아니요: 받은 파일을 기억해 두고, 설정 → 업데이트의 [내려받은 새 버전 설치] 로 나중에 설치
             → 예: 설치 (윈도우 설치판: 프로그램을 닫고 조용히 설치 후 다시 실행 / deb·rpm: 관리자 암호 창 → 설치 → 다시 실행)
"""
import os
import subprocess
import threading

from PyQt6.QtCore import QObject, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QMessageBox, QProgressDialog

from .. import EDITION, __version__
from .. import theme as TH
from ..services import update as U

TITLE = '우리집 가계부 업데이트'
HINT = '설정 → 업데이트에서 언제든 직접 새 버전을 확인하고, 내려받아 설치할 수 있습니다.'
SYNC = False          # 시험: 다른 스레드 없이 바로 실행


# ── 시험에서 바꿔 끼우는 함수들 ──
def ask(parent, text, yes='예', no='아니요'):
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle(TITLE)
    box.setText(text)
    by = box.addButton(yes, QMessageBox.ButtonRole.YesRole)
    box.addButton(no, QMessageBox.ButtonRole.NoRole)
    box.setDefaultButton(by)
    box.exec()
    return box.clickedButton() is by


def info(parent, text):
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(TITLE)
    box.setText(text)
    box.addButton('확인', QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def open_url(url):
    QDesktopServices.openUrl(QUrl(url))


def run_install(cmd):
    """deb·rpm 설치 명령 실행 → 끝 코드 (pkexec 가 관리자 암호를 물음)"""
    return subprocess.run(cmd, stdin=subprocess.DEVNULL).returncode


def auto_enabled():
    v = TH.settings().value('update_auto', True)
    return v if isinstance(v, bool) else str(v).lower() in ('1', 'true', 'yes')


def set_auto(on):
    TH.set_pref('update_auto', bool(on))


class _Relay(QObject):
    """다른 스레드에서 화면 스레드로 함수 넘기기"""
    call = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(lambda f: f(), Qt.ConnectionType.QueuedConnection)


class Updater(QObject):
    changed = pyqtSignal()           # 설정 → 업데이트 탭 다시 그리기

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.kind = U.install_kind()
        self.latest = None
        self.busy = False
        self.status = ''
        self._relay = _Relay()

    # ── 공통 ──
    def _bg(self, fn, done):
        """fn() 을 다른 스레드에서 → 끝나면 done(결과, 오류) 를 화면 스레드에서"""
        def work():
            try:
                res, err = fn(), None
            except Exception as e:      # noqa: BLE001 — 인터넷·파일 오류를 그대로 안내
                res, err = None, e
            if SYNC:
                done(res, err)
            else:
                self._relay.call.emit(lambda: done(res, err))
        if SYNC:
            work()
        else:
            threading.Thread(target=work, daemon=True).start()

    def _set(self, status):
        self.status = status
        self.changed.emit()

    def downloaded(self):
        """받아 두고 아직 설치하지 않은 새 버전 (경로, 버전) 또는 None"""
        s = TH.settings()
        path, ver = str(s.value('update_file', '') or ''), str(s.value('update_file_ver', '') or '')
        if path and os.path.isfile(path) and U.newer(ver, __version__):
            return path, ver
        return None

    def _remember(self, path, ver):
        TH.set_pref('update_file', path or '')
        TH.set_pref('update_file_ver', ver or '')

    def summary(self, rel):
        lines = rel.get('changes') or rel.get('notes') or []
        body = '\n'.join(f'· {x}' for x in lines) if lines else '· (적힌 내용 없음 — 내려받기 페이지에서 볼 수 있습니다)'
        return f'새 버전 {rel["version"]}이(가) 있습니다. (지금 {EDITION} {__version__})\n\n업데이트 내용\n{body}'

    # ── 확인 ──
    def check_later(self, delay=1500):
        """켤 때 자동 확인 (설정에서 끈 경우 안 함). 다른 창이 떠 있으면 닫힐 때까지 기다림"""
        if auto_enabled():
            QTimer.singleShot(delay, lambda: self.check(manual=False))

    def check(self, manual=False, parent=None):
        if self.busy:
            return
        if not manual and QApplication.activeModalWidget() is not None:
            QTimer.singleShot(2000, lambda: self.check(manual=False))       # 예약 입력 창 등이 닫힌 뒤에
            return
        self.busy = True
        self._set('새 버전을 확인하는 중…')
        self._bg(lambda: U.fetch_latest(__version__), lambda rel, err: self._checked(rel, err, manual, parent))

    def _checked(self, rel, err, manual, parent):
        self.busy = False
        parent = parent or self.win
        if err is not None:
            self._set(f'확인하지 못했습니다: {err}')
            if manual:
                info(parent, f'새 버전을 확인하지 못했습니다.\n인터넷 연결을 확인해 주세요.\n\n({err})')
            return
        if not rel or not U.newer(rel['version'], __version__):
            self.latest = None
            self._set(f'지금 판({__version__})이 최신입니다.')
            if manual:
                info(parent, f'지금 판({EDITION} {__version__})이 최신입니다.')
            return
        self.latest = rel
        self._set(f'새 버전 {rel["version"]}이(가) 있습니다.')
        auto = self.kind in U.AUTO_KINDS
        if auto:
            q = self.summary(rel) + '\n\n업데이트하시겠습니까?'
        else:
            q = (self.summary(rel) + f'\n\n지금 설치 방식({U.KIND_LABEL.get(self.kind, self.kind)})은 자동 설치가 되지 않아 '
                 '내려받기 페이지를 엽니다.\n업데이트하시겠습니까?')
        if ask(parent, q):
            if auto:
                self.download(rel, parent)
            else:
                open_url(rel['page'])
        elif not manual:
            info(parent, HINT)

    # ── 내려받기 ──
    def download(self, rel, parent=None):
        parent = parent or self.win
        name, asset = U.asset_for(rel, self.kind)
        if not asset:
            info(parent, '이 릴리스에 지금 설치 방식용 파일이 없습니다. 내려받기 페이지를 엽니다.')
            open_url(rel['page'])
            return
        dlg = QProgressDialog(f'새 버전 {rel["version"]}을(를) 내려받는 중…', '취소', 0, 100, parent)
        dlg.setWindowTitle(TITLE)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setValue(0)
        stop = {'v': False}
        dlg.canceled.connect(lambda: stop.__setitem__('v', True))
        self.busy = True
        self._set('내려받는 중…')

        def prog(got, total):
            pct = int(got * 100 / total) if total else 0
            if SYNC:
                dlg.setValue(pct)
            else:
                self._relay.call.emit(lambda: dlg.setValue(pct))
        self._bg(lambda: U.download(name, asset, prog, lambda: stop['v']),
                 lambda path, err: self._downloaded(rel, path, err, parent, dlg))

    def _downloaded(self, rel, path, err, parent, dlg):
        self.busy = False
        dlg.close()
        if err is not None:
            if isinstance(err, U.Cancelled):
                self._set('내려받기를 취소했습니다.')
            else:
                self._set(f'내려받지 못했습니다: {err}')
                info(parent, f'새 버전을 내려받지 못했습니다.\n\n({err})')
            return
        self._remember(path, rel['version'])
        self._set(f'새 버전 {rel["version"]}을(를) 내려받았습니다. 설치를 기다리는 중입니다.')
        self.ask_install(path, rel['version'], parent)

    # ── 설치 ──
    def ask_install(self, path, ver, parent=None):
        parent = parent or self.win
        if self.kind == 'windows-setup':
            how = '설치하면 프로그램이 닫히고, 설치가 끝나면 새 버전으로 다시 열립니다.'
        else:
            how = '관리자 암호를 묻는 창이 뜹니다. 설치가 끝나면 프로그램이 새 버전으로 다시 열립니다.'
        if ask(parent, f'새 버전 {ver}을(를) 내려받았습니다.\n지금 설치할까요?\n\n{how}'):
            self.install(path, ver, parent)
        else:
            info(parent, '설정 → 업데이트의 [내려받은 새 버전 설치]로 나중에 설치할 수 있습니다.')

    def install(self, path, ver, parent=None):
        parent = parent or self.win
        if self.kind == 'windows-setup':
            U.spawn_detached(U.windows_script(path, os.getpid(), U.windows_launcher()))
            self.quit_app()
            return
        cmd = U.install_command(self.kind, path)
        if not cmd or not U.can_elevate():
            info(parent, f'이 컴퓨터에서는 자동으로 설치할 수 없습니다.\n받은 파일을 직접 설치해 주세요:\n{path}')
            open_url(QUrl.fromLocalFile(os.path.dirname(path)).toString())
            return
        busy = QProgressDialog('설치하는 중… (관리자 암호 창이 뜨면 암호를 넣어 주세요)', None, 0, 0, parent)
        busy.setWindowTitle(TITLE)
        busy.setWindowModality(Qt.WindowModality.WindowModal)
        busy.setMinimumDuration(0)
        busy.show()
        self.busy = True
        self._set('설치하는 중…')
        self._bg(lambda: run_install(cmd), lambda rc, err: self._installed(rc, err, ver, parent, busy))

    def _installed(self, rc, err, ver, parent, busy):
        self.busy = False
        busy.close()
        if err is not None or rc != 0:
            why = str(err) if err is not None else ('관리자 암호 입력을 취소했습니다.' if rc in (126, 127) else f'끝 코드 {rc}')
            self._set(f'설치하지 못했습니다: {why}')
            info(parent, f'설치하지 못했습니다.\n({why})\n\n설정 → 업데이트에서 다시 설치할 수 있습니다.')
            return
        self._remember('', '')
        self._set(f'새 버전 {ver}을(를) 설치했습니다.')
        info(parent, f'새 버전 {ver}을(를) 설치했습니다.\n프로그램을 새 버전으로 다시 엽니다.')
        U.spawn_detached(U.relaunch_command())
        self.quit_app()

    def quit_app(self):
        self.win.close()
        QTimer.singleShot(0, QApplication.quit)
