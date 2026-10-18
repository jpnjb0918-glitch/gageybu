"""일정관리·기념일 (양력/음력)·주소록·일기장·메모장."""
import datetime as dt
import uuid

from ..lunar import lunar_to_solar
from ..util import add_months, iso, to_date

# ── 일정 반복 규칙 (원본: 매 N 일/주/월/년, 월·수·금, 화·목, 월~금, 토·일, N번째 X요일 매 N달) ──
WEEKDAY_SETS = {'월, 수, 금': {0, 2, 4}, '화, 목': {1, 3}, '월 ~ 금': {0, 1, 2, 3, 4}, '토, 일': {5, 6}}
ORDINALS = ['첫 번째', '두 번째', '세 번째', '네 번째', '마지막']
WEEKDAY_NAMES = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']


def _nth_weekday(y, m, nth, wd):
    """nth: 0~3 = 첫~넷째, 4 = 마지막. wd: 0=월."""
    if nth == 4:
        last = add_months(y, m, 1)
        d = dt.date(*last, 1) - dt.timedelta(days=1)
        return d - dt.timedelta(days=(d.weekday() - wd) % 7)
    d = dt.date(y, m, 1)
    d += dt.timedelta(days=(wd - d.weekday()) % 7)
    d += dt.timedelta(weeks=nth)
    return d if d.month == m else None


def expand_repeat(start, until, rule):
    """rule: {'type': 'none'} | {'type':'every','n':N,'unit':'일|주|월|년'} | {'type':'weekdays','set':'월, 수, 금'}
            | {'type':'nth','nth':0~4,'weekday':0~6,'n':N}"""
    start, until = to_date(start), to_date(until or start)
    t = rule.get('type', 'none')
    out = []
    if t == 'none' or until < start:
        return [start]
    if t == 'every':
        n, unit = max(1, int(rule.get('n', 1))), rule.get('unit', '일')
        k = 0
        while True:
            if unit == '일':
                d = start + dt.timedelta(days=n * k)
            elif unit == '주':
                d = start + dt.timedelta(weeks=n * k)
            elif unit == '월':
                y, m = add_months(start.year, start.month, n * k)
                try:
                    d = dt.date(y, m, start.day)
                except ValueError:       # 31일 반복인데 그 달에 31일이 없으면 건너뜀
                    k += 1
                    continue
            else:
                try:
                    d = dt.date(start.year + n * k, start.month, start.day)
                except ValueError:       # 2/29
                    k += 1
                    continue
            if d > until:
                break
            out.append(d)
            k += 1
            if k > 5000:
                break
    elif t == 'weekdays':
        days = WEEKDAY_SETS[rule['set']]
        d = start
        while d <= until:
            if d.weekday() in days:
                out.append(d)
            d += dt.timedelta(days=1)
    elif t == 'nth':
        n = max(1, int(rule.get('n', 1)))
        y, m = start.year, start.month
        while dt.date(y, m, 1) <= until:
            d = _nth_weekday(y, m, int(rule['nth']), int(rule['weekday']))
            if d and start <= d <= until:
                out.append(d)
            y, m = add_months(y, m, n)
    return out


def add_schedule(con, date, text, remind_days=0, bg=None, fg=None, repeat=None, until=None):
    dates = expand_repeat(date, until, repeat or {'type': 'none'})
    gid = uuid.uuid4().hex if len(dates) > 1 else None
    con.executemany('INSERT INTO schedule(date,text,remind_days,bg,fg,group_id) VALUES(?,?,?,?,?,?)',
                    [(iso(d), text, int(remind_days or 0), bg, fg, gid) for d in dates])
    con.commit()
    return len(dates)


def update_schedule(con, sid, text, remind_days=0, bg=None, fg=None):
    con.execute('UPDATE schedule SET text=?, remind_days=?, bg=?, fg=? WHERE id=?', (text, remind_days, bg, fg, sid))
    con.commit()


def delete_schedule(con, sid):
    con.execute('DELETE FROM schedule WHERE id=?', (sid,))
    con.commit()


def delete_schedule_range(con, start, end):
    n = con.execute('DELETE FROM schedule WHERE date BETWEEN ? AND ?', (iso(start), iso(end))).rowcount
    con.commit()
    return n


def schedules(con, start, end):
    out = {}
    for r in con.execute('SELECT * FROM schedule WHERE date BETWEEN ? AND ? ORDER BY date, id', (iso(start), iso(end))):
        out.setdefault(r['date'], []).append(r)
    return out


def reminders(con, today=None):
    """'시작시 알려주기 N일 전' 이 걸린 일정 중 오늘 알려줄 것."""
    today = to_date(today or dt.date.today())
    rows = con.execute('SELECT * FROM schedule WHERE remind_days>0 AND date>=? ORDER BY date',
                       (iso(today),)).fetchall()
    return [r for r in rows if to_date(r['date']) - dt.timedelta(days=r['remind_days']) <= today]


# ── 기념일 ──────────────────────────────────────────────
def anniversaries(con):
    return con.execute('SELECT * FROM anniversary ORDER BY sort, id').fetchall()


def save_anniversary(con, v, aid=None):
    vals = (v['title'], int(v['month']), int(v['day']), v.get('year'), int(bool(v.get('lunar'))),
            int(bool(v.get('holiday'))))
    if aid:
        con.execute('UPDATE anniversary SET title=?,month=?,day=?,year=?,lunar=?,holiday=? WHERE id=?', vals + (aid,))
    else:
        sort = con.execute('SELECT COALESCE(MAX(sort),0)+1 FROM anniversary').fetchone()[0]
        aid = con.execute('INSERT INTO anniversary(title,month,day,year,lunar,holiday,sort) VALUES(?,?,?,?,?,?,?)',
                          vals + (sort,)).lastrowid
    con.commit()
    return aid


def delete_anniversary(con, aid):
    con.execute('DELETE FROM anniversary WHERE id=?', (aid,))
    con.commit()


def anniversaries_between(con, start, end):
    """{date: [(제목, 휴일여부)]} — 음력 기념일은 해당 양력 날짜로 변환."""
    start, end = to_date(start), to_date(end)
    out = {}
    for a in anniversaries(con):
        years = [a['year']] if a['year'] else range(start.year - 1, end.year + 1)
        for y in years:
            if a['lunar']:
                d = lunar_to_solar(y, a['month'], a['day'], False)
            else:
                try:
                    d = dt.date(y, a['month'], min(a['day'], 31))
                except ValueError:
                    import calendar as _c
                    d = dt.date(y, a['month'], _c.monthrange(y, a['month'])[1]) if a['day'] >= 28 else None
            if d and start <= d <= end:
                out.setdefault(d, []).append((a['title'], bool(a['holiday'])))
    return out


def month_grid(y, m):
    """일요일 시작 6주 x 7일."""
    first = dt.date(y, m, 1)
    start = first - dt.timedelta(days=(first.weekday() + 1) % 7)
    return [[start + dt.timedelta(days=w * 7 + d) for d in range(7)] for w in range(6)]


# ── 단순 목록 (주소록·일기장·메모장) ───────────────────
def simple_list(con, table, order='id', where='', args=()):
    q = f'SELECT * FROM {table}'
    if where:
        q += ' WHERE ' + where
    return con.execute(q + f' ORDER BY {order}', args).fetchall()


def simple_save(con, table, values, rid=None):
    if rid:
        con.execute(f'UPDATE {table} SET {",".join(f"{k}=?" for k in values)} WHERE id=?', list(values.values()) + [rid])
    else:
        rid = con.execute(f'INSERT INTO {table}({",".join(values)}) VALUES({",".join("?" * len(values))})',
                          list(values.values())).lastrowid
    con.commit()
    return rid


def simple_delete(con, table, rid):
    con.execute(f'DELETE FROM {table} WHERE id=?', (rid,))
    con.commit()
