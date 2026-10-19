"""백업·복원·CSV 내보내기/가져오기."""
import csv
import datetime as dt
import os
import sqlite3

from ..util import parse_money, to_date


def backup(con, folder):
    """현재 DB를 folder/backup(YYYY-MM-DD)/gagyebu.sqlite3 로 안전하게 복사 (원본의 [backup년-월-일] 폴더 방식)."""
    target_dir = os.path.join(folder, f'backup({dt.date.today():%Y-%m-%d})')
    os.makedirs(target_dir, exist_ok=True)
    path = os.path.join(target_dir, 'gagyebu.sqlite3')
    dst = sqlite3.connect(path)
    with dst:
        con.commit()
        con.backup(dst)
    dst.execute('PRAGMA journal_mode=DELETE')     # 백업 파일 하나만 복사해도 온전하도록 (-wal 없이)
    dst.close()
    return path


def backup_to_file(con, path):
    """현재 DB를 고른 파일 하나로 안전하게 저장 (구글 드라이브 폴더·USB 등 아무 곳이나)"""
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    tmp = os.path.join(d, f'.{os.path.basename(path)}.tmp')
    if os.path.exists(tmp):
        os.remove(tmp)
    dst = sqlite3.connect(tmp)
    try:
        with dst:
            con.commit()
            con.backup(dst)
        dst.execute('PRAGMA journal_mode=DELETE')
    finally:
        dst.close()
    os.replace(tmp, path)                      # 다 쓴 뒤 한 번에 바꿈 (반쯤 쓴 파일이 남지 않게)
    return path


def backup_name(today=None):
    """백업 파일 기본 이름 (휴대폰판과 같은 이름: 우리집가계부-백업-YYYY-MM-DD.sqlite3)"""
    return f'우리집가계부-백업-{(today or dt.date.today()):%Y-%m-%d}.sqlite3'


def google_drive_dirs():
    """이 PC에서 찾은 구글 드라이브 폴더들 (Google Drive 데스크톱 앱·리눅스 온라인 계정·rclone 등이 만든 폴더)"""
    home = os.path.expanduser('~')
    cand = []
    if os.name == 'nt':
        import string
        for d in string.ascii_uppercase[3:]:                       # D: ~ Z: (보통 G:)
            for sub in ('내 드라이브', 'My Drive'):
                cand.append(f'{d}:\\{sub}')
        for sub in ('내 드라이브', 'My Drive', 'Google Drive', 'Google 드라이브'):
            cand.append(os.path.join(home, sub))
    else:
        import glob
        cand += sorted(glob.glob(os.path.join(home, 'Library', 'CloudStorage', 'GoogleDrive-*', '*')))   # macOS
        cand += sorted(glob.glob(f'/run/user/{os.getuid()}/gvfs/google-drive:*'))                         # 그놈 온라인 계정
        for sub in ('Google Drive', 'GoogleDrive', 'google-drive', 'gdrive', '구글드라이브', '구글 드라이브', '내 드라이브', 'My Drive'):
            cand.append(os.path.join(home, sub))
    out = []
    for p in cand:
        try:
            if os.path.isdir(p) and p not in out:
                out.append(p)
        except OSError:
            pass
    return out


def validate_db(path):
    try:
        c = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
        ok = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='entry'").fetchone()
        c.close()
        return bool(ok)
    except sqlite3.DatabaseError:
        return False


def prepare_replacement(current_path, new_path):
    """교체할 파일을 SQLite 백업 기능으로 현재 DB 옆 임시 파일에 복사·검증 (-wal 에만 있는 내용까지 포함).
    여기서 실패하면 현재 데이터는 전혀 건드리지 않은 상태."""
    if os.path.exists(current_path) and os.path.exists(new_path) and os.path.samefile(current_path, new_path):
        raise ValueError('지금 쓰고 있는 데이터 파일 자신으로는 복원할 수 없습니다. 백업 폴더의 파일을 고르세요.')
    tmp = current_path + '.incoming'
    for ext in ('', '-wal', '-shm', '-journal'):
        if os.path.exists(tmp + ext):
            os.remove(tmp + ext)
    src = sqlite3.connect(new_path)
    dst = sqlite3.connect(tmp)
    try:
        with dst:
            src.backup(dst)
        dst.execute('PRAGMA journal_mode=DELETE')  # 파일 하나로 완결 (-wal/-shm 남기지 않음)
    finally:
        src.close()
        dst.close()
    if not validate_db(tmp):
        os.remove(tmp)
        raise ValueError('우리집 가계부(새 버전) 데이터 파일이 아닙니다.')
    return tmp


def keep_current(current_path, keep_dir):
    """현재 DB를 keep_dir 에 사본으로 보관 (열려 있어도 안전한 백업 기능 사용). 보관 경로 반환."""
    if not os.path.exists(current_path):
        return None
    os.makedirs(keep_dir, exist_ok=True)
    stamp = f'{dt.datetime.now():%Y%m%d-%H%M%S}'
    kept = os.path.join(keep_dir, f'before-restore-{stamp}.sqlite3')
    k = 1
    while os.path.exists(kept):                     # 같은 초에 두 번 바꿔도 앞 보관본을 덮어쓰지 않게
        k += 1
        kept = os.path.join(keep_dir, f'before-restore-{stamp}-{k}.sqlite3')
    src = sqlite3.connect(current_path)
    dst = sqlite3.connect(kept)
    try:
        with dst:
            src.backup(dst)
        dst.execute('PRAGMA journal_mode=DELETE')  # 파일 하나로 완결 (-wal/-shm 남기지 않음)
    finally:
        src.close()
        dst.close()
    return kept


def swap_in(current_path, tmp):
    """현재 DB 연결을 모두 닫은 뒤에 호출. 임시 파일을 한 번에 바꿔 끼움."""
    for ext in ('-wal', '-shm'):
        for path in (current_path + ext, tmp + ext):
            if os.path.exists(path):
                os.remove(path)
    os.replace(tmp, current_path)


def replace_db(current_path, new_path, keep_dir):
    """(열린 연결이 없을 때) 현재 DB를 보관한 뒤 new_path 내용으로 교체. 보관 경로 반환."""
    tmp = prepare_replacement(current_path, new_path)
    kept = keep_current(current_path, keep_dir)
    swap_in(current_path, tmp)
    return kept


def write_csv(path, header, rows):
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def read_entries_csv(path, valid_codes):
    """원본 '엑셀데이타 불러오기' 대체: 날짜, 품목, 수입, 지출, 계정코드[, 계정과목, 메모] 순서의 CSV.
    반환: (정상 행 목록, 오류 목록[(행번호, 내용)])"""
    rows, errors = [], []
    for enc in ('utf-8-sig', 'cp949'):
        try:
            with open(path, encoding=enc, newline='') as f:
                data = list(csv.reader(f))
            break
        except UnicodeDecodeError:
            continue
    else:
        return [], [(0, '파일 인코딩을 읽을 수 없습니다 (UTF-8 또는 CP949 CSV로 저장하세요)')]
    if data and data[0] and data[0][0].strip() in ('날짜', 'date'):
        data = data[1:]
    for n, r in enumerate(data, start=2):
        if not any(c.strip() for c in r):
            continue
        r = (r + [''] * 7)[:7]
        try:
            d = to_date(r[0].strip().replace('.', '-').replace('/', '-'))
        except ValueError:
            errors.append((n, f'날짜 형식 오류: {r[0]!r}'))
            continue
        try:
            inc, exp = parse_money(r[2]), parse_money(r[3])
        except ValueError:
            errors.append((n, f'금액 오류: {r[2]!r}, {r[3]!r}'))
            continue
        code = r[4].strip()
        if not r[1].strip():
            errors.append((n, '품목이 비어 있음'))
            continue
        if code not in valid_codes:
            errors.append((n, f'없는 계정코드: {code!r}'))
            continue
        if not inc and not exp:
            errors.append((n, '수입·지출이 모두 0'))
            continue
        rows.append({'date': d, 'item': r[1].strip(), 'income': inc, 'expense': exp, 'code': code, 'memo': r[6].strip()})
    return rows, errors
