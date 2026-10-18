"""예약 설정 (매월 고정 수입/지출 자동입력). 원본 규칙:
- 자동입력일 1~31, 그 달에 없는 날이면 말일로
- 시작 적용일부터, 종료 적용일까지(없으면 계속)
- 프로그램 시작·장부 선택 시 오늘까지 입력될 내용을 보여주고 확인하면 입력
"""
import datetime as dt

from ..util import add_months, clamp_day, iso, to_date
from . import ledger as L


def rules(con, lid):
    return con.execute('SELECT * FROM recurring WHERE ledger_id=? ORDER BY day, id', (lid,)).fetchall()


def save_rule(con, lid, r, rid=None):
    vals = (r.get('item', ''), int(r.get('income') or 0), int(r.get('expense') or 0), r.get('code', ''),
            int(r['day']), iso(r['start']), iso(r['end']) if r.get('end') else None, r.get('memo', ''))
    if rid:
        # 규칙을 고쳐도 이미 처리한 기간은 다시 묻지 않음 (예: 25일→10일로 바꿔도 지난 달들이 또 나오지 않게)
        thr = processed_through(con, rid)
        con.execute('UPDATE recurring SET item=?,income=?,expense=?,code=?,day=?,start=?,end=?,memo=?,applied_through=? '
                    'WHERE id=?', vals + (iso(thr) if thr else None, rid))
    else:
        rid = con.execute('INSERT INTO recurring(item,income,expense,code,day,start,end,memo,ledger_id,created) '
                          'VALUES(?,?,?,?,?,?,?,?,?,?)', vals + (lid, iso(dt.date.today()))).lastrowid
    con.commit()
    return rid


def delete_rule(con, rid):
    con.execute('DELETE FROM recurring WHERE id=?', (rid,))
    con.commit()


def occurrences(rule, start, end):
    """rule 이 start~end 사이에 입력될 날짜들."""
    start, end = to_date(start), to_date(end)
    rs = to_date(rule['start'])
    re_ = to_date(rule['end']) if rule['end'] else None
    lo = max(start, rs)
    hi = min(end, re_) if re_ else end
    out = []
    if lo > hi:
        return out
    y, m = lo.year, lo.month
    while (y, m) <= (hi.year, hi.month):
        d = clamp_day(y, m, rule['day'])
        if lo <= d <= hi:
            out.append(d)
        y, m = add_months(y, m, 1)
    return out


def last_logged(con, rid):
    r = con.execute('SELECT MAX(date) FROM recurring_log WHERE recurring_id=?', (rid,)).fetchone()[0]
    return to_date(r) if r else None


def processed_through(con, rid):
    """applied_through 와 마지막 기록 날짜 중 늦은 날."""
    r = con.execute('SELECT applied_through FROM recurring WHERE id=?', (rid,)).fetchone()
    cands = [d for d in (to_date(r['applied_through']) if r and r['applied_through'] else None, last_logged(con, rid)) if d]
    return max(cands) if cands else None


def pending(con, lid, today=None):
    """(오늘까지 입력될 목록, 오늘 이후 이달에 남은 목록) — 각 항목 dict(rule, date)."""
    today = to_date(today or dt.date.today())
    month_last = clamp_day(today.year, today.month, 31)
    due, later = [], []
    for r in rules(con, lid):
        done = {to_date(x['date']) for x in con.execute('SELECT date FROM recurring_log WHERE recurring_id=?',
                                                        (r['id'],))}
        thr = to_date(r['applied_through']) if r['applied_through'] else None
        for d in occurrences(r, r['start'], month_last):
            if d not in done and not (thr and d <= thr):   # 일부만 입력하고 남겨 둔 날짜는 다시 보여 줌
                (due if d <= today else later).append({'rule': r, 'date': d})
    key = lambda x: (x['date'], x['rule']['id'])
    return sorted(due, key=key), sorted(later, key=key)


def apply(con, lid, items, skip=False):
    """items 를 장부에 입력(skip=True면 입력 없이 '건너뜀'으로 기록만)."""
    for it in items:
        r, d = it['rule'], it['date']
        eid = None
        if not skip:
            eid = L.add_entry(con, lid, {'date': d, 'item': r['item'], 'income': r['income'],
                                         'expense': r['expense'], 'code': r['code'], 'memo': r['memo']},
                              origin=f'recurring:{r["id"]}', commit=False)
        con.execute('INSERT INTO recurring_log(recurring_id,ledger_id,date,item,income,expense,code,entry_id,skipped) '
                    'VALUES(?,?,?,?,?,?,?,?,?)', (r['id'], lid, iso(d), r['item'], r['income'], r['expense'],
                                                  r['code'], eid, 1 if skip else 0))
    con.commit()


def log(con, rid=None, lid=None, start=None, end=None):
    q = 'SELECT * FROM recurring_log WHERE 1=1'
    a = []
    if rid:
        q += ' AND recurring_id=?'
        a.append(rid)
    if lid:
        q += ' AND ledger_id=?'
        a.append(lid)
    if start:
        q += ' AND date>=?'
        a.append(iso(start))
    if end:
        q += ' AND date<=?'
        a.append(iso(end))
    return con.execute(q + ' ORDER BY date, id', a).fetchall()
