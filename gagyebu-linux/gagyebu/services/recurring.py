"""고정 수입·지출 (원본 '예약 설정'): 정한 날마다 자동으로 넣기. 원본 규칙:
- 자동입력일 1~31, 그 달에 없는 날이면 말일로
- 시작 적용일부터, 종료 적용일까지(없으면 계속)
- 프로그램 시작·장부 선택 시 오늘까지 입력될 내용을 보여주고 확인하면 입력
1.8.0: 매주(몇 주마다·요일)·매년(몇 월 며칠)도. 매주·매년 규칙은 end 칸에 BLOCK_END(1900-01-01)를 넣어
예전 판(매달만 아는 판)이 그 규칙을 매달로 잘못 넣지 않게 막고, 진짜 종료일은 end2 칸에 둔다.
"""
import datetime as dt

from ..util import add_months, clamp_day, iso, to_date
from . import ledger as L


def rules(con, lid):
    return con.execute('SELECT * FROM recurring WHERE ledger_id=? ORDER BY day, id', (lid,)).fetchall()


BLOCK_END = '1900-01-01'          # 매주·매년 규칙의 end — 예전 판은 '이미 끝난 규칙'으로 보고 건너뜀
CYCLES = (('M', '매달'), ('W', '매주'), ('Y', '매년'))
WEEKDAY_NAMES = '월화수목금토일'


def _get(rule, key, default=None):
    try:
        v = rule[key]
    except (KeyError, IndexError):
        return default
    return default if v is None else v


def cycle_of(rule):
    c = _get(rule, 'cycle', 'M')
    return c if c in ('M', 'W', 'Y') else 'M'


def end_of(rule):
    """진짜 종료일 문자열 (없으면 None) — 매주·매년은 end2"""
    return _get(rule, 'end2') if cycle_of(rule) != 'M' else _get(rule, 'end')


def rule_text(rule):
    """'매달 25일' · '매주 월요일' · '2주마다 금요일' · '매년 3월 15일' (31일은 '말일')"""
    c = cycle_of(rule)
    if c == 'W':
        n = max(1, int(_get(rule, 'every', 1)))
        return f"{'매주' if n == 1 else f'{n}주마다'} {WEEKDAY_NAMES[int(_get(rule, 'wday', 0)) % 7]}요일"
    day = int(_get(rule, 'day', 1))
    dtxt = '말일' if day >= 31 else f'{day}일'
    if c == 'Y':
        return f"매년 {int(_get(rule, 'ymonth', 1))}월 {dtxt}"
    return f'매달 {dtxt}'


def save_rule(con, lid, r, rid=None):
    """r: item·income·expense·code·day·start·end·memo·pay + cycle('M'|'W'|'Y')·every·wday·ymonth"""
    cyc = r.get('cycle') or 'M'
    if cyc not in ('M', 'W', 'Y'):
        raise ValueError('반복 주기가 올바르지 않습니다')
    end = iso(r['end']) if r.get('end') else None
    day = int(r.get('day') or 1)
    if cyc == 'W':
        day = 1
    vals = (r.get('item', ''), int(r.get('income') or 0), int(r.get('expense') or 0), r.get('code', ''),
            day, iso(r['start']), end if cyc == 'M' else BLOCK_END, r.get('memo', ''),
            (r.get('pay') or '').strip(), cyc, max(1, int(r.get('every') or 1)), int(r.get('wday') or 0) % 7,
            min(12, max(1, int(r.get('ymonth') or 1))), end if cyc != 'M' else None)
    cols = 'item=?,income=?,expense=?,code=?,day=?,start=?,end=?,memo=?,pay=?,cycle=?,every=?,wday=?,ymonth=?,end2=?'
    if rid:
        # 규칙을 고쳐도 이미 처리한 기간은 다시 묻지 않음 (예: 25일→10일로 바꿔도 지난 달들이 또 나오지 않게)
        thr = processed_through(con, rid)
        con.execute(f'UPDATE recurring SET {cols},applied_through=? WHERE id=?', vals + (iso(thr) if thr else None, rid))
    else:
        rid = con.execute('INSERT INTO recurring(item,income,expense,code,day,start,end,memo,pay,cycle,every,wday,ymonth,end2,'
                          'ledger_id,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                          vals + (lid, iso(dt.date.today()))).lastrowid
    con.commit()
    return rid


def delete_rule(con, rid):
    con.execute('DELETE FROM recurring WHERE id=?', (rid,))
    con.commit()


def occurrences(rule, start, end):
    """rule 이 start~end 사이에 입력될 날짜들."""
    start, end = to_date(start), to_date(end)
    rs = to_date(rule['start'])
    e = end_of(rule)
    re_ = to_date(e) if e else None
    lo = max(start, rs)
    hi = min(end, re_) if re_ else end
    out = []
    if lo > hi:
        return out
    cyc = cycle_of(rule)
    if cyc == 'W':                                   # 시작일 이후 첫 그 요일부터 every 주마다
        step = 7 * max(1, int(_get(rule, 'every', 1)))
        d = rs + dt.timedelta(days=(int(_get(rule, 'wday', 0)) % 7 - rs.weekday()) % 7)
        if d < lo:
            d += dt.timedelta(days=-(-(lo - d).days // step) * step)
        while d <= hi:
            out.append(d)
            d += dt.timedelta(days=step)
        return out
    if cyc == 'Y':
        mo = min(12, max(1, int(_get(rule, 'ymonth', 1))))
        for y in range(lo.year, hi.year + 1):
            d = clamp_day(y, mo, rule['day'])
            if lo <= d <= hi:
                out.append(d)
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
                                         'expense': r['expense'], 'code': r['code'], 'memo': r['memo'],
                                         'pay': _get(r, 'pay', '')},
                              origin=f'recurring:{r["id"]}', commit=False)
        con.execute('INSERT INTO recurring_log(recurring_id,ledger_id,date,item,income,expense,code,entry_id,skipped) '
                    'VALUES(?,?,?,?,?,?,?,?,?)', (r['id'], lid, iso(d), r['item'], r['income'], r['expense'],
                                                  r['code'], eid, 1 if skip else 0))
    con.commit()


def status_of(con, rule, d, today=None):
    """그 날의 상태: 'done'(넣음) · 'skipped'(건너뜀) · 'due'(오늘까지인데 아직) · 'later'(앞으로)"""
    r = con.execute('SELECT skipped FROM recurring_log WHERE recurring_id=? AND date=? ORDER BY id LIMIT 1',
                    (rule['id'], iso(d))).fetchone()
    if r:
        return 'skipped' if r['skipped'] else 'done'
    thr = _get(rule, 'applied_through')
    if thr and to_date(d) <= to_date(thr):
        return 'done'
    return 'due' if to_date(d) <= to_date(today or dt.date.today()) else 'later'


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
