"""휴지통 (1.8.0): 지운 내역을 30일 동안 보관했다가 되살리기.
지운 행은 그대로 JSON 으로(trash.entry), 붙은 사진은 trash_photo 로 옮겨 둔다. 되살릴 때 원래 번호가 비어 있으면
그 번호로 넣어서 같은 날 순서·통장 거래 연결이 그대로 이어진다. 안드로이드판 svc-money.js 의 Trash 와 같은 규칙."""
import datetime as dt
import json

from ..util import to_date

KEEP_DAYS = 30
ENTRY_COLS = ('ledger_id', 'date', 'item', 'income', 'expense', 'code', 'memo', 'origin', 'pay')
DEFAULTS = {'item': '', 'income': 0, 'expense': 0, 'code': '', 'memo': '', 'origin': None, 'pay': ''}


def _now():
    return dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def put(con, ids, why='delete', now=None):
    """내역 ids 를 휴지통에 넣음 (지우기는 부르는 쪽이). 커밋은 부르는 쪽이. 반환: 휴지통 번호 목록"""
    now = now or _now()
    out = []
    for i in ids:
        r = con.execute('SELECT * FROM entry WHERE id=?', (i,)).fetchone()
        if not r:
            continue
        row = {k: r[k] for k in r.keys()}
        tid = con.execute('INSERT INTO trash(ledger_id,deleted,why,entry) VALUES(?,?,?,?)',
                          (r['ledger_id'], now, why, json.dumps(row, ensure_ascii=False, sort_keys=True))).lastrowid
        con.execute('INSERT INTO trash_photo(trash_id,name,mime,data,created) '
                    'SELECT ?,name,mime,data,created FROM attachment WHERE entry_id=? ORDER BY id', (tid, i))
        out.append(tid)
    return out


def items(con, lid=None):
    """[{'id','ledger_id','deleted','why','entry'(dict),'photos'}] — 최근에 지운 것부터"""
    q = ('SELECT t.id, t.ledger_id, t.deleted, t.why, t.entry, '
         '(SELECT COUNT(*) FROM trash_photo p WHERE p.trash_id=t.id) photos FROM trash t')
    a = []
    if lid is not None:
        q += ' WHERE t.ledger_id=?'
        a.append(lid)
    out = []
    for r in con.execute(q + ' ORDER BY t.deleted DESC, t.id DESC', a):
        try:
            e = json.loads(r['entry'])
        except ValueError:
            e = {}
        out.append({'id': r['id'], 'ledger_id': r['ledger_id'], 'deleted': r['deleted'], 'why': r['why'],
                    'entry': e, 'photos': r['photos']})
    return out


def count(con, lid=None):
    if lid is None:
        return con.execute('SELECT COUNT(*) FROM trash').fetchone()[0]
    return con.execute('SELECT COUNT(*) FROM trash WHERE ledger_id=?', (lid,)).fetchone()[0]


def restore(con, tids):
    """되살리기. 반환: 되살린 내역 번호 목록 (가계부가 없어졌으면 건너뜀)"""
    out = []
    for tid in tids:
        r = con.execute('SELECT * FROM trash WHERE id=?', (tid,)).fetchone()
        if not r:
            continue
        try:
            e = json.loads(r['entry'])
        except ValueError:
            e = {}
        if not con.execute('SELECT 1 FROM ledger WHERE id=?', (r['ledger_id'],)).fetchone():
            continue
        e['ledger_id'] = r['ledger_id']
        vals = [e.get(k) if e.get(k) is not None else DEFAULTS.get(k) for k in ENTRY_COLS]
        old = e.get('id')
        if old and not con.execute('SELECT 1 FROM entry WHERE id=?', (old,)).fetchone():
            con.execute(f'INSERT INTO entry(id,{",".join(ENTRY_COLS)}) VALUES(?{",?" * len(ENTRY_COLS)})', [old] + vals)
            eid = old
        else:
            eid = con.execute(f'INSERT INTO entry({",".join(ENTRY_COLS)}) VALUES({",".join("?" * len(ENTRY_COLS))})',
                              vals).lastrowid
        con.execute('INSERT INTO attachment(entry_id,name,mime,data,created) '
                    'SELECT ?,name,mime,data,created FROM trash_photo WHERE trash_id=? ORDER BY id', (eid, tid))
        con.execute('DELETE FROM trash WHERE id=?', (tid,))
        out.append(eid)
    con.commit()
    return out


def remove(con, tids):
    """영구 삭제"""
    con.executemany('DELETE FROM trash WHERE id=?', [(t,) for t in tids])
    con.commit()


def empty(con, lid=None):
    if lid is None:
        con.execute('DELETE FROM trash')
    else:
        con.execute('DELETE FROM trash WHERE ledger_id=?', (lid,))
    con.commit()


def purge(con, today=None, days=KEEP_DAYS):
    """보관 기간이 지난 것 지우기 (프로그램을 켤 때). 반환: 지운 수"""
    limit = (to_date(today or dt.date.today()) - dt.timedelta(days=days)).isoformat()
    n = con.execute('DELETE FROM trash WHERE deleted < ?', (limit,)).rowcount
    con.commit()
    return n


def days_left(deleted, today=None, days=KEEP_DAYS):
    """지운 날부터 보관 기간이 며칠 남았는지 (0 이면 오늘 지나면 지워짐)"""
    d = to_date(str(deleted)[:10])
    return max(0, (d + dt.timedelta(days=days) - to_date(today or dt.date.today())).days)
