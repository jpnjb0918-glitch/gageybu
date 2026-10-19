"""결산 보고서 (원본 도움말의 월결산·년결산·월별 일일결산·사용자정의 결산·년예산)."""
import datetime as dt
from dataclasses import dataclass, field

from ..util import add_months, iso, is_income_code, month_end, settle_period
from . import ledger as L


@dataclass
class Row:
    kind: str            # 'cat' | 'subtotal' | 'footer'
    group: str           # 대분류 이름
    label: str           # 소분류 이름 / '소 계' / 합계 이름
    code: str = ''
    values: list = field(default_factory=list)   # int 또는 None(빈칸)


@dataclass
class Report:
    title: str
    columns: list
    rows: list
    periods: list = field(default_factory=list)   # 각 열의 (시작, 끝) — 상세내역 보기용
    note: str = ''


def _sum_by_code(con, lid, start, end):
    out = {}
    for r in con.execute('SELECT code, SUM(income) inc, SUM(expense) exp FROM entry '
                         'WHERE ledger_id=? AND date BETWEEN ? AND ? GROUP BY code', (lid, iso(start), iso(end))):
        out[r['code']] = L.signed_amount(r['code'], r['inc'], r['exp'])
    return out


def _income_expense(con, lid, start, end):
    """(수입계, 지출계) — 계정 기준: 0으로 시작하는 계정 = 수입."""
    inc = exp = 0
    for code, v in _sum_by_code(con, lid, start, end).items():
        if is_income_code(code):
            inc += v
        else:
            exp += v
    return inc, exp


def _structure(con, lid, extra_codes=()):
    """[(대분류코드, 대분류명, [(code, 이름), ...])] — 내역에만 있는 코드도 포함."""
    gmap = L.group_map(con, lid)
    cats = L.categories(con, lid)
    known = {c['code'] for c in cats}
    by_group = {}
    for c in cats:
        by_group.setdefault(c['code'][:1], []).append((c['code'], c['name']))
    for code in sorted(set(extra_codes) - known):
        by_group.setdefault(code[:1] if code else '?', []).append((code, f'(미분류 {code})' if code else '(미분류)'))
    order = [g['code'] for g in L.groups(con, lid)]
    order += sorted(set(by_group) - set(order))
    return [(g, gmap.get(g, f'(분류 {g})'), by_group.get(g, [])) for g in order if by_group.get(g) or g in gmap]


def _build(con, lid, columns_data, ncols, extra_codes=()):
    """columns_data: code → [값 x ncols]. 대분류별 소계 포함 행 목록."""
    rows = []
    for g, gname, cats in _structure(con, lid, extra_codes):
        sub = [0] * ncols
        for code, name in cats:
            vals = columns_data.get(code, [0] * ncols)
            rows.append(Row('cat', gname, name, code, list(vals)))
            sub = [a + (b or 0) for a, b in zip(sub, vals)]
        if cats:
            rows.append(Row('subtotal', gname, '소 계', g, sub))
    return rows


def monthly(con, lid, y, m, settle_day=1):
    py, pm = add_months(y, m, -1)
    ny, nm = add_months(y, m, 1)
    p_prev, p_cur = settle_period(py, pm, settle_day), settle_period(y, m, settle_day)
    prev, cur = _sum_by_code(con, lid, *p_prev), _sum_by_code(con, lid, *p_cur)
    b_cur, b_next = budgets(con, lid, f'{y:04d}-{m:02d}'), budgets(con, lid, f'{ny:04d}-{nm:02d}')
    codes = set(prev) | set(cur) | set(b_cur) | set(b_next)
    data = {c: [prev.get(c, 0), cur.get(c, 0), cur.get(c, 0) - prev.get(c, 0), b_cur.get(c, 0), b_next.get(c, 0)]
            for c in codes}
    rows = _build(con, lid, data, 5, codes)
    carry_prev = L.balance_before(con, lid, p_prev[0])
    carry_cur = L.balance_before(con, lid, p_cur[0])
    ip, ep = _income_expense(con, lid, *p_prev)
    ic, ec = _income_expense(con, lid, *p_cur)
    bi = sum(v for c, v in b_cur.items() if is_income_code(c))
    be = sum(v for c, v in b_cur.items() if not is_income_code(c))
    ni = sum(v for c, v in b_next.items() if is_income_code(c))
    ne = sum(v for c, v in b_next.items() if not is_income_code(c))
    rows += [Row('footer', '', '전월 이월금', values=[carry_prev, carry_cur, carry_cur - carry_prev, None, None]),
             Row('footer', '', '수입계', values=[ip, ic, ic - ip, bi, ni]),
             Row('footer', '', '지출계', values=[ep, ec, ec - ep, be, ne]),
             Row('footer', '', '잔액', values=[carry_prev + ip - ep, carry_cur + ic - ec,
                                              (carry_cur + ic - ec) - (carry_prev + ip - ep), bi - be, ni - ne])]
    fmt = lambda p: f'{p[0]:%m-%d}~{p[1]:%m-%d}'
    return Report(f'{y}년 {m}월 결산 보고서',
                  [f'지난달 결산\n({fmt(p_prev)})', f'이달의 결산\n({fmt(p_cur)})', '증감\n(이달-지난달)',
                   '이번달 예산', '다음달 예산'], rows, [p_prev, p_cur, None, None, None],
                  note=f'결산일 {settle_day}일 기준')


def yearly(con, lid, y, settle_day=1):
    periods = [settle_period(y, m, settle_day) for m in range(1, 13)]
    sums = [_sum_by_code(con, lid, *p) for p in periods]
    codes = set().union(*sums)
    data = {c: [s.get(c, 0) for s in sums] + [sum(s.get(c, 0) for s in sums)] for c in codes}
    rows = _build(con, lid, data, 13, codes)
    carry = L.balance_before(con, lid, periods[0][0])
    ie = [_income_expense(con, lid, *p) for p in periods]
    bal, bals = carry, []
    for i, e in ie:
        bal += i - e
        bals.append(bal)
    carries = [carry] + bals[:-1]
    rows += [Row('footer', '', '전기 이월', values=carries + [carry]),
             Row('footer', '', '수입계', values=[i for i, _ in ie] + [sum(i for i, _ in ie)]),
             Row('footer', '', '지출계', values=[e for _, e in ie] + [sum(e for _, e in ie)]),
             Row('footer', '', '잔액', values=bals + [bals[-1]])]
    return Report(f'{y}년 결산 보고서', [f'{m}월' for m in range(1, 13)] + ['합계'], rows, periods + [None],
                  note=f'결산일 {settle_day}일 기준 · 전기 이월 = 그 기간 시작 전까지의 잔액')


def daily(con, lid, y, m):
    n = month_end(y, m)
    days = [dt.date(y, m, d) for d in range(1, n + 1)]
    sums = [_sum_by_code(con, lid, d, d) for d in days]
    codes = set().union(*sums)
    data = {c: [s.get(c, 0) for s in sums] + [sum(s.get(c, 0) for s in sums)] for c in codes}
    rows = _build(con, lid, data, n + 1, codes)
    carry = L.balance_before(con, lid, days[0])
    ie = [_income_expense(con, lid, d, d) for d in days]
    ci = ce = 0
    cum_i, cum_e, bals = [], [], []
    for i, e in ie:
        ci += i
        ce += e
        cum_i.append(ci)
        cum_e.append(ce)
        bals.append(carry + ci - ce)
    rows += [Row('footer', '', '수입계', values=[i for i, _ in ie] + [ci]),
             Row('footer', '', '수입누계', values=cum_i + [ci]),
             Row('footer', '', '지출계', values=[e for _, e in ie] + [ce]),
             Row('footer', '', '지출누계', values=cum_e + [ce]),
             Row('footer', '', '전월 이월금', values=[carry] + [None] * (n - 1) + [carry]),
             Row('footer', '', '잔액', values=bals + [bals[-1]])]
    return Report(f'{y}년 {m}월 일일결산 보고서', [f'{d.day}일' for d in days] + ['합계'], rows,
                  [(d, d) for d in days] + [(days[0], days[-1])])


def custom(con, lid, start, end):
    first = con.execute('SELECT MIN(date) FROM entry WHERE ledger_id=?', (lid,)).fetchone()[0] or iso(start)
    last = con.execute('SELECT MAX(date) FROM entry WHERE ledger_id=?', (lid,)).fetchone()[0] or iso(end)
    year = dt.date(start.year, 1, 1), dt.date(start.year, 12, 31)
    periods = [(start, end), year, (dt.date.fromisoformat(first), dt.date.fromisoformat(last))]
    sums = [_sum_by_code(con, lid, *p) for p in periods]
    codes = set().union(*sums)
    data = {c: [s.get(c, 0) for s in sums] for c in codes}
    rows = _build(con, lid, data, 3, codes)
    ie = [_income_expense(con, lid, *p) for p in periods]
    rows += [Row('footer', '', '수입계', values=[i for i, _ in ie]),
             Row('footer', '', '지출계', values=[e for _, e in ie]),
             Row('footer', '', '수입계 - 지출계', values=[i - e for i, e in ie])]
    return Report(f'{start} ~ {end} 결산 보고서',
                  [f'{start:%y-%m-%d} ~ {end:%y-%m-%d}', f'{start.year}년 결산', '전체 합계'], rows, periods)


# ── 예산 ────────────────────────────────────────────────
def budgets(con, lid, ym):
    return {r['code']: r['amount'] for r in
            con.execute('SELECT code, amount FROM budget WHERE ledger_id=? AND ym=?', (lid, ym))}


def set_budget(con, lid, ym, code, amount):
    if amount:
        con.execute('INSERT INTO budget VALUES(?,?,?,?) ON CONFLICT(ledger_id,ym,code) DO UPDATE SET amount=excluded.amount',
                    (lid, ym, code, int(amount)))
    else:
        con.execute('DELETE FROM budget WHERE ledger_id=? AND ym=? AND code=?', (lid, ym, code))
    con.commit()


def budget_year(con, lid, y):
    yms = [f'{y:04d}-{m:02d}' for m in range(1, 13)]
    bs = [budgets(con, lid, ym) for ym in yms]
    codes = set().union(*bs)
    data = {c: [b.get(c, 0) for b in bs] + [sum(b.get(c, 0) for b in bs)] for c in codes}
    rows = _build(con, lid, data, 13, codes)
    carry = L.balance_before(con, lid, dt.date(y, 1, 1))
    inc = [sum(v for c, v in b.items() if is_income_code(c)) for b in bs]
    exp = [sum(v for c, v in b.items() if not is_income_code(c)) for b in bs]
    bal, bals = carry, []
    for i, e in zip(inc, exp):
        bal += i - e
        bals.append(bal)
    rows += [Row('footer', '', '전년도 이월금액', values=[carry] + [None] * 11 + [carry]),
             Row('footer', '', '수입계', values=inc + [sum(inc)]),
             Row('footer', '', '지출계', values=exp + [sum(exp)]),
             Row('footer', '', '잔액', values=bals + [bals[-1]])]
    return Report(f'{y}년 예산 보고서', [f'{m}월 예산' for m in range(1, 13)] + ['합계'], rows, yms + [None],
                  note='소분류 칸을 두 번 눌러 예산 금액을 입력하세요')


# ── 그래프 ──────────────────────────────────────────────
def graph_series(con, lid, y, group=None, code=None, month=None, settle_day=1):
    """그래프용 {이름: [값...]} 와 x축 라벨.
    group=None → 대분류별 전체, group 지정 → 그 대분류의 소분류별, code 지정 → 그 소분류 하나.
    month 지정 → 그 달의 일별."""
    if month:
        n = month_end(y, month)
        periods = [(dt.date(y, month, d),) * 2 for d in range(1, n + 1)]
        labels = [str(d) for d in range(1, n + 1)]
    else:
        periods = [settle_period(y, m, settle_day) for m in range(1, 13)]
        labels = [f'{m}월' for m in range(1, 13)]
    sums = [_sum_by_code(con, lid, *p) for p in periods]
    gmap, cmap = L.group_map(con, lid), L.category_map(con, lid)
    series = {}
    if code:
        series[f'({code}) {L.code_label(cmap, code)}'] = [s.get(code, 0) for s in sums]
    elif group is not None:
        codes = sorted({c for s in sums for c in s if c[:1] == group} |
                       {c for c in cmap if c[:1] == group})
        for c in codes:
            series[f'({c}) {L.code_label(cmap, c)}'] = [s.get(c, 0) for s in sums]
    else:
        gs = sorted({c[:1] for s in sums for c in s} | set(gmap), key=lambda g: (g not in gmap, g))
        for g in gs:
            series[f'({g}) {gmap.get(g, "?")}'] = [sum(v for c, v in s.items() if c[:1] == g) for s in sums]
    return labels, series
