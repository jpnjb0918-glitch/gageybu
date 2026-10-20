"""이달 살펴보기 (1.7.0): 예산 진행·예산 알림·이달 소비 리포트·무지출 날.
결산일(예: 25일)을 따르는 '그 달' 기간 기준. 안드로이드판 svc-extra.js 의 Ins 와 같은 계산 (devtools/compat 로 비교)."""
import datetime as dt
import math

from ..util import add_months, fmt_money, is_income_code, iso, settle_period, to_date
from . import ledger as L
from . import reports as RP


def period_of(d, settle_day=1):
    """그 날이 들어 있는 결산 '달' (연, 월)"""
    d = to_date(d)
    start, _end = settle_period(d.year, d.month, settle_day)
    return (d.year, d.month) if d >= start else add_months(d.year, d.month, -1)


def _pct(a, b):
    """a/b 를 % 로 (0.5 는 올림). b<=0 이면 None"""
    return math.floor(a * 100 / b + 0.5) if b > 0 else None


def _spent_by_code(con, lid, start, end):
    """지출 계정별 쓴 돈 (지출 - 그 계정 환불)"""
    return {c: v for c, v in RP._sum_by_code(con, lid, start, end).items() if not is_income_code(c)}


# ── 예산 진행 ───────────────────────────────────────────
def budget_progress(con, lid, y, m, settle_day=1, today=None):
    """{'rows': [{'code','name','budget','spent','left','pct'}] (많이 쓴 비율 순), 'budget','spent','left','pct',
        'days_left','per_day'} — 지출 계정 예산만. 예산이 없으면 rows 가 빈 목록"""
    today = to_date(today or dt.date.today())
    start, end = settle_period(y, m, settle_day)
    bud = {c: v for c, v in RP.budgets(con, lid, f'{y:04d}-{m:02d}').items() if not is_income_code(c) and v > 0}
    spent = _spent_by_code(con, lid, start, end)
    cmap = L.category_map(con, lid)
    rows = []
    for code, b in bud.items():
        s = spent.get(code, 0)
        rows.append({'code': code, 'name': L.code_label(cmap, code), 'budget': b, 'spent': s, 'left': b - s,
                     'pct': _pct(s, b)})
    rows.sort(key=lambda r: (-r['pct'], -r['spent'], r['code']))
    tb, ts = sum(bud.values()), sum(r['spent'] for r in rows)
    days_left = (end - today).days + 1 if start <= today <= end else (0 if today > end else (end - start).days + 1)
    left = tb - ts
    return {'rows': rows, 'budget': tb, 'spent': ts, 'left': left, 'pct': _pct(ts, tb), 'days_left': days_left,
            'per_day': left // days_left if days_left > 0 and left > 0 else 0, 'start': iso(start), 'end': iso(end)}


def code_spent(con, lid, code, d, settle_day=1):
    """그 날이 들어 있는 달에 그 계정으로 쓴 돈 — 저장 전·후를 비교해 예산 알림에 씀"""
    y, m = period_of(d, settle_day)
    start, end = settle_period(y, m, settle_day)
    return _spent_by_code(con, lid, start, end).get(code, 0)


def budget_alert(con, lid, code, d, before, settle_day=1):
    """저장한 뒤 그 계정이 예산의 80%·100% 를 처음 넘었으면 알림 글, 아니면 None. before = 저장 전 code_spent"""
    if not code or is_income_code(code):
        return None
    y, m = period_of(d, settle_day)
    b = RP.budgets(con, lid, f'{y:04d}-{m:02d}').get(code, 0)
    if b <= 0:
        return None
    after = code_spent(con, lid, code, d, settle_day)
    name = L.code_label(L.category_map(con, lid), code)
    if before < b <= after:
        return f'{m}월 {name} 예산을 넘었어요: {fmt_money(after)}원 / {fmt_money(b)}원 ({fmt_money(after - b)}원 초과)'
    if before * 100 < b * 80 <= after * 100:
        return f'{m}월 {name} 예산의 {_pct(after, b)}%를 썼어요 (남은 돈 {fmt_money(b - after)}원)'
    return None


# ── 무지출 날 ───────────────────────────────────────────
def no_spend_days(con, lid, start, end):
    """[start, end] 중 지출이 없는 날 (그 날 지출 합계가 0 이하 — 환불만 있는 날 포함) — 'YYYY-MM-DD' 목록.
    장부에 처음 적은 날보다 앞은 빼고 셈 (빈 장부는 없음)"""
    first = con.execute('SELECT MIN(date) FROM entry WHERE ledger_id=?', (lid,)).fetchone()[0]
    if not first:
        return []
    start, end = max(to_date(start), to_date(first)), to_date(end)
    spent = {r[0] for r in con.execute('SELECT date FROM entry WHERE ledger_id=? AND date BETWEEN ? AND ? '
                                       'GROUP BY date HAVING SUM(expense) > 0', (lid, iso(start), iso(end)))}
    out, d = [], start
    while d <= end:
        if d.isoformat() not in spent:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def no_spend_streak(con, lid, upto, limit=366):
    """upto 부터 거꾸로 이어진 무지출 날 수 (upto 가 지출 있는 날이면 0)"""
    upto = to_date(upto)
    days = set(no_spend_days(con, lid, upto - dt.timedelta(days=limit - 1), upto))
    n, d = 0, upto
    while d.isoformat() in days:
        n += 1
        d -= dt.timedelta(days=1)
    return n


# ── 이달 소비 리포트 ────────────────────────────────────
def month_insight(con, lid, y, m, settle_day=1, today=None):
    """그 달(결산일 기준) 요약. 이번 달이면 오늘까지, 지난 달이면 그 달 전체."""
    today = to_date(today or dt.date.today())
    start, end = settle_period(y, m, settle_day)
    current = start <= today <= end
    upto = today if current else end
    total_days = (end - start).days + 1
    days = (upto - start).days + 1 if upto >= start else 0
    inc, exp = RP._income_expense(con, lid, start, upto) if days else (0, 0)
    py, pm = add_months(y, m, -1)
    ps, pe = settle_period(py, pm, settle_day)
    p_upto = min(ps + dt.timedelta(days=max(days, 1) - 1), pe)
    prev_same = RP._income_expense(con, lid, ps, p_upto)[1] if days else 0
    prev_full = RP._income_expense(con, lid, ps, pe)[1]
    cmap = L.category_map(con, lid)
    cur = _spent_by_code(con, lid, start, upto) if days else {}
    prev = _spent_by_code(con, lid, ps, p_upto) if days else {}
    top = sorted(((c, v) for c, v in cur.items() if v > 0), key=lambda cv: (-cv[1], cv[0]))[:3]
    big = con.execute('SELECT item, expense, date FROM entry WHERE ledger_id=? AND date BETWEEN ? AND ? AND expense>0 '
                      'ORDER BY expense DESC, date, id LIMIT 1', (lid, iso(start), iso(upto))).fetchone() if days else None
    # 무지출 날은 오늘까지만 셈 (앞으로 올 날은 빼기 — 미리 넣은 카드대금 같은 미래 달)
    ns_end = min(upto, today)
    ns = no_spend_days(con, lid, start, ns_end) if days and ns_end >= start else []
    avg = exp // days if days else 0
    return {
        'start': iso(start), 'end': iso(end), 'upto': iso(upto) if days else '', 'current': current,
        'days': days, 'total_days': total_days, 'income': inc, 'expense': exp,
        'prev_same': prev_same, 'prev_full': prev_full, 'change_pct': _pct(exp - prev_same, prev_same),
        'daily_avg': avg, 'projected': avg * total_days if current else exp,
        'top': [{'code': c, 'name': L.code_label(cmap, c), 'amount': v, 'prev': prev.get(c, 0),
                 'change_pct': _pct(v - prev.get(c, 0), prev.get(c, 0))} for c, v in top],
        'biggest': {'item': big['item'], 'amount': big['expense'], 'date': big['date']} if big else None,
        'no_spend': len(ns), 'streak': no_spend_streak(con, lid, ns_end) if days and ns_end >= start else 0,
        'budget': budget_progress(con, lid, y, m, settle_day, today),
    }
