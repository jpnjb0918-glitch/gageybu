"""내역 사진 (영수증) — 1.7.0. 사진은 자료 파일(SQLite) 안에 그대로 들어가 PC·휴대폰이 같이 봄.
화면 쪽에서 긴 변 1600px·JPEG 로 줄여서 넣음 (한 장 보통 0.2~0.5MB)."""
import datetime as dt

MAX_SIDE = 1600
QUALITY = 82


def add(con, entry_id, data, name='', mime='image/jpeg', commit=True):
    aid = con.execute('INSERT INTO attachment(entry_id,name,mime,data,created) VALUES(?,?,?,?,?)',
                      (entry_id, name or '', mime or 'image/jpeg', bytes(data),
                       dt.datetime.now().strftime('%Y-%m-%d %H:%M'))).lastrowid
    if commit:
        con.commit()
    return aid


def list_for(con, entry_id):
    """사진 목록 (내용 빼고): id·name·mime·created·size"""
    return con.execute('SELECT id, name, mime, created, length(data) AS size FROM attachment WHERE entry_id=? ORDER BY id',
                       (entry_id,)).fetchall()


def data(con, aid):
    r = con.execute('SELECT data FROM attachment WHERE id=?', (aid,)).fetchone()
    return bytes(r['data']) if r else None


def delete(con, aid):
    con.execute('DELETE FROM attachment WHERE id=?', (aid,))
    con.commit()


def counts(con, entry_ids):
    """{내역 번호: 사진 수} — 목록에 사진 표시용"""
    ids = list(entry_ids)
    out = {}
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        for r in con.execute(f'SELECT entry_id, COUNT(*) n FROM attachment WHERE entry_id IN ({",".join("?" * len(part))}) '
                             'GROUP BY entry_id', part):
            out[r['entry_id']] = r['n']
    return out


def total_size(con):
    return con.execute('SELECT COALESCE(SUM(length(data)),0) FROM attachment').fetchone()[0]
