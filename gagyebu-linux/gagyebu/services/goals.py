"""저축 목표·빌려준 돈/빌린 돈 (1.7.0). 장부와 따로 (자산처럼 모든 장부에 공통).
안드로이드판 svc-extra.js 의 Goal·Debt 와 같은 계산."""
import datetime as dt

from ..util import iso, to_date


# ── 저축 목표 ───────────────────────────────────────────
def goals(con, include_done=True):
    q = 'SELECT * FROM goal' + ('' if include_done else ' WHERE done=0') + ' ORDER BY done, sort, id'
    return con.execute(q).fetchall()


def save_goal(con, g, gid=None):
    """g: name·target·due(없으면 None)·memo·done"""
    name = (g.get('name') or '').strip()
    if not name:
        raise ValueError('목표 이름을 입력하세요')
    vals = (name, int(g.get('target') or 0), iso(g['due']) if g.get('due') else None, (g.get('memo') or '').strip(),
            1 if g.get('done') else 0)
    if gid:
        con.execute('UPDATE goal SET name=?,target=?,due=?,memo=?,done=? WHERE id=?', vals + (gid,))
    else:
        sort = con.execute('SELECT COALESCE(MAX(sort),0)+1 FROM goal').fetchone()[0]
        gid = con.execute('INSERT INTO goal(name,target,due,memo,done,sort,created) VALUES(?,?,?,?,?,?,?)',
                          vals + (sort, dt.date.today().isoformat())).lastrowid
    con.commit()
    return gid


def delete_goal(con, gid):
    con.execute('DELETE FROM goal WHERE id=?', (gid,))
    con.commit()


def add_goal_tx(con, gid, date, amount, memo=''):
    """모은 돈 기록 (꺼내 쓴 돈은 음수)"""
    tid = con.execute('INSERT INTO goal_tx(goal_id,date,amount,memo) VALUES(?,?,?,?)',
                      (gid, iso(date), int(amount or 0), memo or '')).lastrowid
    con.commit()
    return tid


def delete_goal_tx(con, tid):
    con.execute('DELETE FROM goal_tx WHERE id=?', (tid,))
    con.commit()


def goal_txs(con, gid):
    return con.execute('SELECT * FROM goal_tx WHERE goal_id=? ORDER BY date, id', (gid,)).fetchall()


def goal_status(con, g, today=None):
    """{'saved','left','pct','days_left','per_month'} — per_month: 남은 돈을 남은 달(이번 달 포함) 수로 나눈 값 (올림)"""
    today = to_date(today or dt.date.today())
    saved = con.execute('SELECT COALESCE(SUM(amount),0) FROM goal_tx WHERE goal_id=?', (g['id'],)).fetchone()[0]
    target = g['target']
    left = max(0, target - saved)
    pct = min(100, saved * 100 // target) if target > 0 else 0
    days_left = months_left = None
    if g['due']:
        due = to_date(g['due'])
        days_left = (due - today).days
        months_left = max(1, (due.year - today.year) * 12 + (due.month - today.month) + 1) if days_left >= 0 else 0
    per_month = -(-left // months_left) if months_left else 0
    return {'saved': saved, 'left': left, 'pct': max(0, pct), 'days_left': days_left, 'per_month': per_month}


# ── 빌려준 돈·빌린 돈 ────────────────────────────────────
KINDS = {'lend': '빌려준 돈', 'borrow': '빌린 돈'}


def debts(con, include_done=True):
    q = 'SELECT * FROM debt' + ('' if include_done else ' WHERE done=0') + ' ORDER BY done, date, id'
    return con.execute(q).fetchall()


def save_debt(con, d, did=None):
    """d: kind('lend'|'borrow')·person·amount·date·due·memo·done"""
    if d.get('kind') not in KINDS:
        raise ValueError('빌려준 돈인지 빌린 돈인지 고르세요')
    person = (d.get('person') or '').strip()
    if not person:
        raise ValueError('누구인지 입력하세요')
    amount = int(d.get('amount') or 0)
    if amount <= 0:
        raise ValueError('금액을 입력하세요')
    vals = (d['kind'], person, amount, iso(d.get('date') or dt.date.today()), iso(d['due']) if d.get('due') else None,
            (d.get('memo') or '').strip(), 1 if d.get('done') else 0)
    if did:
        con.execute('UPDATE debt SET kind=?,person=?,amount=?,date=?,due=?,memo=?,done=? WHERE id=?', vals + (did,))
    else:
        did = con.execute('INSERT INTO debt(kind,person,amount,date,due,memo,done) VALUES(?,?,?,?,?,?,?)', vals).lastrowid
    con.commit()
    return did


def delete_debt(con, did):
    con.execute('DELETE FROM debt WHERE id=?', (did,))
    con.commit()


def add_payment(con, did, date, amount, memo=''):
    """갚은(받은) 돈 기록. 다 갚으면 끝남(done)으로"""
    con.execute('INSERT INTO debt_pay(debt_id,date,amount,memo) VALUES(?,?,?,?)', (did, iso(date), int(amount or 0), memo or ''))
    d = con.execute('SELECT amount FROM debt WHERE id=?', (did,)).fetchone()
    if d and debt_paid(con, did) >= d['amount']:
        con.execute('UPDATE debt SET done=1 WHERE id=?', (did,))
    con.commit()


def delete_payment(con, pid):
    r = con.execute('SELECT debt_id FROM debt_pay WHERE id=?', (pid,)).fetchone()
    con.execute('DELETE FROM debt_pay WHERE id=?', (pid,))
    if r:
        d = con.execute('SELECT amount FROM debt WHERE id=?', (r['debt_id'],)).fetchone()
        if d and debt_paid(con, r['debt_id']) < d['amount']:
            con.execute('UPDATE debt SET done=0 WHERE id=?', (r['debt_id'],))
    con.commit()


def payments(con, did):
    return con.execute('SELECT * FROM debt_pay WHERE debt_id=? ORDER BY date, id', (did,)).fetchall()


def debt_paid(con, did):
    return con.execute('SELECT COALESCE(SUM(amount),0) FROM debt_pay WHERE debt_id=?', (did,)).fetchone()[0]


def debt_left(con, d):
    return max(0, d['amount'] - debt_paid(con, d['id']))


def debt_totals(con):
    """(받을 돈 합계, 갚을 돈 합계) — 끝나지 않은 것의 남은 돈"""
    lend = borrow = 0
    for d in debts(con, include_done=False):
        left = debt_left(con, d)
        if d['kind'] == 'lend':
            lend += left
        else:
            borrow += left
    return lend, borrow
