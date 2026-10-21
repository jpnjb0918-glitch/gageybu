"""1.8.0 에 더한 돈 관리·보기 계산: 결제수단 · 큰돈 나눠 적기 · 외화 · 같은 곳 모아보기 · 주간 예산 · 주별 통계 ·
월별 저축 추이 · 고정비 한눈에 · 한 달 전체 예산 · 달력 돈 일정 · 카드 실적.
안드로이드판 svc-money.js 와 같은 계산 (devtools/compat 로 결과를 비교)."""
import datetime as dt
import json
import re

from .. import db
from ..util import add_months, clamp_day, fmt_money, is_income_code, iso, pct, settle_period, to_date
from . import ledger as L
from . import recurring as R
from . import reports as RP



# ── 결제수단 ────────────────────────────────────────────
PAY_KINDS = (('cash', '현금'), ('card', '카드'), ('bank', '계좌이체'), ('pay', '간편결제'))


def card_label(c):
    """카드 이름: 회사 이름이 카드 이름에 없으면 앞에 붙임 ('신한' + 'Deep Dream' → '신한 Deep Dream')"""
    name, company = (c['name'] or '').strip(), (c['company'] or '').strip()
    return f'{company} {name}'.strip() if company and company not in name else (name or company or '카드')


def custom_pays(con):
    v = db.get_json(con, 'pay_custom', [])
    return [str(x) for x in v if str(x).strip()] if isinstance(v, list) else []


def set_custom_pays(con, names):
    """직접 만든 결제수단 이름들 (순서대로, 같은 것은 한 번)"""
    out = []
    for n in names:
        n = str(n or '').strip()[:20]
        if n and n not in out and n not in dict(PAY_KINDS).values():
            out.append(n)
    db.set_json(con, 'pay_custom', out)
    con.commit()
    return out


def rename_custom_pay(con, old, new):
    """직접 만든 결제수단 이름 바꾸기 — 그 이름으로 넣은 내역·자주 쓰는 내역·고정 수입·지출도 함께 (모든 가계부)"""
    new = str(new or '').strip()[:20]
    names = custom_pays(con)
    if not new or old not in names or new == old:
        return names
    if new in names or new in dict(PAY_KINDS).values():
        raise ValueError('같은 이름의 결제수단이 있습니다')
    names[names.index(old)] = new
    db.set_json(con, 'pay_custom', names)
    for t in ('entry', 'favorite', 'recurring'):
        con.execute(f'UPDATE {t} SET pay=? WHERE pay=?', (f'etc:{new}', f'etc:{old}'))
    con.commit()
    return names


def pay_options(con):
    """[(값, 이름)] — 기본 4가지 → 자산에 넣은 카드 → 직접 만든 것"""
    out = list(PAY_KINDS)
    for c in con.execute('SELECT * FROM card ORDER BY sort, id'):
        out.append((f'card:{c["id"]}', card_label(c)))
    out += [(f'etc:{n}', n) for n in custom_pays(con)]
    return out


def pay_map(con):
    return dict(pay_options(con))


def pay_label(pmap, value):
    """결제수단 이름 ('' 이면 '')"""
    v = value or ''
    if not v:
        return ''
    if v in pmap:
        return pmap[v]
    if v.startswith('etc:'):
        return v[4:]
    if v.startswith('card:'):
        return '카드 (지운 카드)'
    return v


def pay_summary(con, lid, start, end):
    """결제수단별 [{'pay','label','count','income','expense','pct'}] — 지출 많은 순, 미지정은 맨 뒤.
    pct = 그 기간 지출(0 보다 큰 것만 합침) 가운데 비율"""
    pmap = pay_map(con)
    rows = []
    for r in con.execute('SELECT pay, COUNT(*) n, COALESCE(SUM(income),0) inc, COALESCE(SUM(expense),0) exp FROM entry '
                         'WHERE ledger_id=? AND date BETWEEN ? AND ? GROUP BY pay', (lid, iso(start), iso(end))):
        rows.append({'pay': r['pay'] or '', 'label': pay_label(pmap, r['pay']) or '미지정', 'count': r['n'],
                     'income': r['inc'], 'expense': r['exp']})
    total = sum(max(0, x['expense']) for x in rows)
    for x in rows:
        x['pct'] = pct(max(0, x['expense']), total)
    rows.sort(key=lambda x: (x['pay'] == '', -x['expense'], -x['count'], x['label']))
    return rows


def entries_by_pay(con, lid, pay, start, end):
    return con.execute('SELECT * FROM entry WHERE ledger_id=? AND pay=? AND date BETWEEN ? AND ? ORDER BY date, id',
                       (lid, pay or '', iso(start), iso(end))).fetchall()


def guess_pay(con, card_text, kind):
    """문자 붙여넣기: 카드·은행 이름으로 결제수단 짐작. 입금·은행 → 계좌이체, 페이 → 간편결제,
    자산에 넣은 카드 중 회사·이름이 맞는 것 → 그 카드, 아니면 '카드'. 이름이 없으면 ''"""
    t = (card_text or '').strip()
    if kind == 'in' or re.search('은행|뱅크', t):
        return 'bank'
    if '페이' in t:
        return 'pay'
    if not t:
        return ''
    core = re.sub(r'(카드|체크)$', '', t).strip()
    for c in con.execute('SELECT * FROM card ORDER BY sort, id'):
        comp, name = (c['company'] or '').strip(), (c['name'] or '').strip()
        if core and ((comp and (comp in core or core in comp)) or core in name):
            return f'card:{c["id"]}'
    return 'card'


# ── 큰돈 나눠 적기 ──────────────────────────────────────
def split_plan(e, months):
    """1년치 보험료처럼 큰돈을 months 달로 나눈 내역들 (첫 달에 나머지). 날은 매달 같은 날(없으면 말일)"""
    n = int(months or 0)
    if not 2 <= n <= 60:
        raise ValueError('2~60달로 나눌 수 있습니다')
    inc, exp = int(e.get('income') or 0), int(e.get('expense') or 0)
    if (inc > 0) == (exp > 0) or inc < 0 or exp < 0:
        raise ValueError('수입이나 지출 한쪽에만 0보다 큰 금액을 넣으세요')
    total = inc or exp
    if total < n:
        raise ValueError('나눌 금액이 너무 작습니다')
    base, rem = divmod(total, n)
    d0 = to_date(e['date'])
    item = (e.get('item') or '').strip()
    memo = (e.get('memo') or '').strip()
    note = f'{fmt_money(total)}원을 {n}달로 나눔'
    out = []
    for k in range(n):
        y, m = add_months(d0.year, d0.month, k)
        amt = base + (rem if k == 0 else 0)
        out.append({'date': clamp_day(y, m, d0.day).isoformat(), 'item': f'{item} ({k + 1}/{n})',
                    'income': amt if inc else 0, 'expense': amt if exp else 0, 'code': (e.get('code') or '').strip(),
                    'memo': f'{memo} · {note}' if memo else note, 'pay': (e.get('pay') or '').strip()})
    return out


def add_split(con, lid, e, months):
    """나눠 적기 저장. 같은 묶음은 origin 'split:<첫 내역 번호>'. 반환: 내역 번호 목록"""
    plan = split_plan(e, months)
    ids = []
    for p in plan:
        ids.append(con.execute('INSERT INTO entry(ledger_id,date,item,income,expense,code,memo,origin,pay) '
                               'VALUES(?,?,?,?,?,?,?,?,?)', (lid, p['date'], p['item'], p['income'], p['expense'],
                                                             p['code'], p['memo'], None, p['pay'])).lastrowid)
    con.executemany('UPDATE entry SET origin=? WHERE id=?', [(f'split:{ids[0]}', i) for i in ids])
    item = (e.get('item') or '').strip()
    if item:                                         # 자동완성에는 원래 내용 하나만
        con.execute('INSERT INTO item_word VALUES(?,?,1) ON CONFLICT(ledger_id,name) DO UPDATE SET count=count+1',
                    (lid, item))
    con.commit()
    return ids


def split_group(con, eid):
    """같이 나눠 적은 내역 번호들 (나눠 적은 내역이 아니면 [eid])"""
    r = con.execute('SELECT origin FROM entry WHERE id=?', (eid,)).fetchone()
    if not r or not (r['origin'] or '').startswith('split:'):
        return [eid]
    return [x['id'] for x in con.execute('SELECT id FROM entry WHERE origin=? ORDER BY date, id', (r['origin'],))]


# ── 외화 ────────────────────────────────────────────────
# (통화, 이름, 환율 단위) — 엔·동은 은행처럼 100 단위 환율
CURRENCIES = (('USD', '미국 달러', 1), ('JPY', '일본 엔', 100), ('EUR', '유로', 1), ('CNY', '중국 위안', 1),
              ('GBP', '영국 파운드', 1), ('HKD', '홍콩 달러', 1), ('TWD', '대만 달러', 1), ('THB', '태국 바트', 1),
              ('VND', '베트남 동', 100), ('PHP', '필리핀 페소', 1), ('SGD', '싱가포르 달러', 1), ('AUD', '호주 달러', 1),
              ('CAD', '캐나다 달러', 1))
_UNIT = {c: u for c, _n, u in CURRENCIES}
_DEC = re.compile(r'\d+(\.\d+)?')


def _dec(s, what):
    t = re.sub(r'[,\s]', '', str(s or ''))
    if not _DEC.fullmatch(t):
        raise ValueError(f'{what}을(를) 숫자로 넣으세요')
    ip, _, fp = t.partition('.')
    fp = fp.rstrip('0')
    v = int(ip + fp) if (ip + fp) else 0
    if v <= 0:
        raise ValueError(f'{what}은(는) 0보다 커야 합니다')
    return v, len(fp), (f'{int(ip):,}' + (f'.{fp}' if fp else ''))


def fx_convert(amount, cur, rate):
    """외화 금액 × 환율 → 원 (0.5 원은 올림). 엔·동 환율은 100 단위. 반환 (원, 메모 글)"""
    if cur not in _UNIT:
        raise ValueError('통화를 고르세요')
    a, sa, at = _dec(amount, '외화 금액')
    r, sr, rt = _dec(rate, '환율')
    den = 10 ** (sa + sr) * _UNIT[cur]
    won = (2 * a * r + den) // (2 * den)
    if won >= 10 ** 15:
        raise ValueError('금액이 너무 큽니다')
    note = f'{cur} {at} × {rt}원' + ('/100' if _UNIT[cur] == 100 else '')
    return won, note


def fx_rates(con):
    v = db.get_json(con, 'fx_rates', {})
    return v if isinstance(v, dict) else {}


def set_fx_rate(con, cur, rate):
    d = fx_rates(con)
    d[cur] = re.sub(r'[,\s]', '', str(rate))
    db.set_json(con, 'fx_rates', d)
    con.commit()


# ── 같은 곳 모아보기 ────────────────────────────────────
def same_place(con, lid, item, upto, months=3):
    """같은 내용(취소 포함)의 최근 months 달 내역. {'item','start','end','count','expense','income','avg','months','rows'}
    months: 달마다 [{'ym','count','expense'}] (오래된 달부터)"""
    item = (item or '').strip()
    if not item:
        return None
    upto = to_date(upto)
    y, m = add_months(upto.year, upto.month, -months)
    start = clamp_day(y, m, upto.day) + dt.timedelta(days=1)
    rows = con.execute('SELECT * FROM entry WHERE ledger_id=? AND item IN (?,?) AND date BETWEEN ? AND ? '
                       'ORDER BY date DESC, id DESC', (lid, item, item + ' (취소)', iso(start), iso(upto))).fetchall()
    per = []
    yy, mm = start.year, start.month
    while (yy, mm) <= (upto.year, upto.month):
        ym = f'{yy:04d}-{mm:02d}'
        sel = [r for r in rows if r['date'][:7] == ym]
        per.append({'ym': ym, 'count': len(sel), 'expense': sum(r['expense'] for r in sel)})
        yy, mm = add_months(yy, mm, 1)
    exp = sum(r['expense'] for r in rows)
    cnt = len([r for r in rows if r['expense'] > 0]) or len(rows)
    return {'item': item, 'start': iso(start), 'end': iso(upto), 'count': len(rows), 'expense': exp,
            'income': sum(r['income'] for r in rows), 'avg': exp // cnt if cnt else 0, 'months': per, 'rows': rows}


# ── 주간 예산 · 주별 통계 ───────────────────────────────
def week_bounds(d):
    """그 날이 들어 있는 주 (월요일 ~ 일요일)"""
    d = to_date(d)
    s = d - dt.timedelta(days=d.weekday())
    return s, s + dt.timedelta(days=6)


def week_budget(con, lid):
    try:
        return max(0, int(db.get_meta(con, f'budget_week:{lid}') or 0))
    except ValueError:
        return 0


def set_week_budget(con, lid, amount):
    db.set_meta(con, f'budget_week:{lid}', int(amount or 0) or None)
    con.commit()


def _spent_by_day(con, lid, start, end):
    """날마다 쓴 돈 (지출 카테고리: 지출 - 환불)"""
    out = {}
    for r in con.execute('SELECT date, code, SUM(income) inc, SUM(expense) exp FROM entry WHERE ledger_id=? '
                         'AND date BETWEEN ? AND ? GROUP BY date, code', (lid, iso(start), iso(end))):
        if not is_income_code(r['code']):
            out[r['date']] = out.get(r['date'], 0) + r['exp'] - r['inc']
    return out


def week_progress(con, lid, d, today=None):
    """{'start','end','spent','budget','left','pct','days':[{'date','spent'}×7],'days_left','per_day'}"""
    today = to_date(today or dt.date.today())
    s, e = week_bounds(d)
    by = _spent_by_day(con, lid, s, e)
    days = [{'date': (s + dt.timedelta(days=i)).isoformat(), 'spent': by.get((s + dt.timedelta(days=i)).isoformat(), 0)}
            for i in range(7)]
    spent = sum(x['spent'] for x in days)
    b = week_budget(con, lid)
    days_left = (e - today).days + 1 if s <= today <= e else (0 if today > e else 7)
    left = b - spent
    return {'start': iso(s), 'end': iso(e), 'spent': spent, 'budget': b, 'left': left, 'pct': pct(spent, b),
            'days': days, 'days_left': days_left, 'per_day': left // days_left if b and days_left > 0 and left > 0 else 0}


def weeks_of_month(con, lid, y, m, settle_day=1):
    """그 달(월 시작일 기준)을 월요일로 나눈 주들 [{'start','end','days','income','expense','budget'}]"""
    start, end = settle_period(y, m, settle_day)
    b = week_budget(con, lid)
    out = []
    ws = start - dt.timedelta(days=start.weekday())
    while ws <= end:
        s, e = max(ws, start), min(ws + dt.timedelta(days=6), end)
        inc, exp = RP._income_expense(con, lid, s, e)
        out.append({'start': iso(s), 'end': iso(e), 'days': (e - s).days + 1, 'income': inc, 'expense': exp,
                    'budget': b})
        ws += dt.timedelta(days=7)
    return out


# ── 월별 저축 추이 ──────────────────────────────────────
SAVING_WORDS = ('저축', '적금', '예금', '투자', '펀드', '연금', '청약')


def saving_codes(con, lid):
    """이름(카테고리 또는 세부 카테고리)에 저축·적금·투자… 가 들어간 지출 세부 카테고리 번호들"""
    gmap = L.group_map(con, lid)
    out = []
    for c in L.categories(con, lid):
        if is_income_code(c['code']):
            continue
        text = c['name'] + ' ' + gmap.get(c['code'][:1], '')
        if any(w in text for w in SAVING_WORDS):
            out.append(c['code'])
    return out


def savings_trend(con, lid, y, settle_day=1):
    """{'rows':[{'month','start','end','income','expense','left','saving','saved','rate','cum'}×12], 'total':{…}, 'codes'}
    left = 수입 − 지출, saving = 저축·적금 카테고리로 낸 돈(지출에 들어 있음), saved = left + saving (모은 돈),
    rate = saved / 수입 (%), cum = 1월부터 모은 돈 누계"""
    codes = saving_codes(con, lid)
    rows, cum = [], 0
    for m in range(1, 13):
        s, e = settle_period(y, m, settle_day)
        by = RP._sum_by_code(con, lid, s, e)
        inc = sum(v for c, v in by.items() if is_income_code(c))
        exp = sum(v for c, v in by.items() if not is_income_code(c))
        sv = sum(by.get(c, 0) for c in codes)
        left = inc - exp
        saved = left + sv
        cum += saved
        rows.append({'month': m, 'start': iso(s), 'end': iso(e), 'income': inc, 'expense': exp, 'left': left,
                     'saving': sv, 'saved': saved, 'rate': pct(saved, inc), 'cum': cum})
    ti = sum(r['income'] for r in rows)
    ts = sum(r['saved'] for r in rows)
    total = {'income': ti, 'expense': sum(r['expense'] for r in rows), 'left': sum(r['left'] for r in rows),
             'saving': sum(r['saving'] for r in rows), 'saved': ts, 'rate': pct(ts, ti)}
    return {'rows': rows, 'total': total, 'codes': codes}


# ── 고정비 한눈에 ───────────────────────────────────────
def fixed_items(con, lid, start, end, today=None):
    """그 기간의 고정 수입·지출 [{'rid','date','item','income','expense','code','pay','status'}] (날짜순)"""
    today = to_date(today or dt.date.today())
    out = []
    for r in R.rules(con, lid):
        for d in R.occurrences(r, start, end):
            out.append({'rid': r['id'], 'date': d.isoformat(), 'item': r['item'], 'income': r['income'],
                        'expense': r['expense'], 'code': r['code'], 'pay': r['pay'] or '',
                        'status': R.status_of(con, r, d, today)})
    out.sort(key=lambda x: (x['date'], x['rid']))
    return out


def fixed_summary(con, lid, y, m, settle_day=1, today=None):
    """그 달(월 시작일 기준) 고정비: 고정 지출·수입 합계와 이미 나간/아직 남은 것, 변동 지출,
    '이달 말 남을 돈'(예상) = 수입 + 아직 안 들어온 고정 수입 − 지출 − 아직 안 나간 고정 지출"""
    today = to_date(today or dt.date.today())
    start, end = settle_period(y, m, settle_day)
    items = fixed_items(con, lid, start, end, today)
    live = [x for x in items if x['status'] != 'skipped']
    out_total = sum(x['expense'] for x in live)
    out_done = sum(x['expense'] for x in live if x['status'] == 'done')
    in_total = sum(x['income'] for x in live)
    in_done = sum(x['income'] for x in live if x['status'] == 'done')
    inc, exp = RP._income_expense(con, lid, start, end)
    fixed_exp = con.execute("SELECT COALESCE(SUM(expense),0) FROM entry WHERE ledger_id=? AND date BETWEEN ? AND ? "
                            "AND origin LIKE 'recurring:%'", (lid, iso(start), iso(end))).fetchone()[0]
    return {'start': iso(start), 'end': iso(end), 'items': items,
            'out_total': out_total, 'out_done': out_done, 'out_left': out_total - out_done,
            'in_total': in_total, 'in_done': in_done, 'in_left': in_total - in_done,
            'income': inc, 'expense': exp, 'fixed_expense': fixed_exp, 'variable': exp - fixed_exp,
            'expected_left': inc + (in_total - in_done) - exp - (out_total - out_done)}


# ── 한 달 전체 예산 ─────────────────────────────────────
def total_budget(con, lid, ym):
    d = db.get_json(con, f'budget_total:{lid}', {})
    try:
        return max(0, int((d if isinstance(d, dict) else {}).get(ym, 0) or 0))
    except (TypeError, ValueError):
        return 0


def set_total_budget(con, lid, yms, amount):
    d = db.get_json(con, f'budget_total:{lid}', {})
    d = d if isinstance(d, dict) else {}
    for ym in yms:
        if int(amount or 0) > 0:
            d[ym] = int(amount)
        else:
            d.pop(ym, None)
    db.set_json(con, f'budget_total:{lid}', d)
    con.commit()


def month_spent(con, lid, d, settle_day=1):
    """그 날이 들어 있는 달에 쓴 돈 (지출 카테고리 전체) — 저장 전·후를 비교해 전체 예산 알림에 씀"""
    from .insights import period_of
    y, m = period_of(d, settle_day)
    s, e = settle_period(y, m, settle_day)
    return RP._income_expense(con, lid, s, e)[1]


def total_alert(con, lid, d, before, settle_day=1):
    """저장한 뒤 한 달 전체 예산의 80%·100% 를 처음 넘었으면 알림 글, 아니면 None"""
    from .insights import period_of
    y, m = period_of(d, settle_day)
    b = total_budget(con, lid, f'{y:04d}-{m:02d}')
    if b <= 0:
        return None
    after = month_spent(con, lid, d, settle_day)
    if before < b <= after:
        return f'{m}월 전체 예산을 넘었어요: {fmt_money(after)}원 / {fmt_money(b)}원 ({fmt_money(after - b)}원 초과)'
    if before * 100 < b * 80 <= after * 100:
        return f'{m}월 전체 예산의 {pct(after, b)}%를 썼어요 (남은 돈 {fmt_money(b - after)}원)'
    return None


# ── 달력 돈 일정 ────────────────────────────────────────
def money_events(con, lid, start, end, today=None):
    """{날짜: [{'kind':'card'|'fixed','label','amount','sign':'in'|'out','done'}]} — 카드 결제일(결제할 금액)과
    고정 수입·지출. done = 이미 결제했거나 넣은(건너뛴) 것"""
    today = to_date(today or dt.date.today())
    out = {}
    for r in con.execute('SELECT c.id, c.name, c.company, c.sort, t.pay_date, SUM(t.amount+t.fee) amt, MIN(t.paid) allpaid '
                         'FROM card_tx t JOIN card c ON c.id=t.card_id WHERE t.pay_date BETWEEN ? AND ? '
                         'GROUP BY c.id, t.pay_date ORDER BY t.pay_date, c.sort, c.id', (iso(start), iso(end))):
        out.setdefault(r['pay_date'], []).append({'kind': 'card', 'label': f'{card_label(r)} 결제', 'amount': r['amt'],
                                                  'sign': 'out', 'done': bool(r['allpaid'])})
    for x in fixed_items(con, lid, start, end, today):
        out.setdefault(x['date'], []).append({'kind': 'fixed', 'label': x['item'] or '고정',
                                              'amount': x['income'] or x['expense'],
                                              'sign': 'in' if x['income'] and not x['expense'] else 'out',
                                              'done': x['status'] in ('done', 'skipped')})
    return out


# ── 카드 실적 ───────────────────────────────────────────
def card_perf(con, y, m):
    """카드마다 그 달(1일~말일) 가계부 내역 중 결제수단이 그 카드인 지출 합계와 실적 목표(카드 정보의 '월 실적 목표').
    [{'id','label','target','spent','count','left','pct'}] — 자산에 넣은 카드 순서대로 (모든 가계부를 합침)"""
    s, e = dt.date(y, m, 1), clamp_day(y, m, 31)
    out = []
    for c in con.execute('SELECT * FROM card ORDER BY sort, id').fetchall():
        try:
            target = max(0, int(json.loads(c['extra'] or '{}').get('perf') or 0))
        except (TypeError, ValueError):
            target = 0
        r = con.execute('SELECT COUNT(*) n, COALESCE(SUM(expense),0) exp FROM entry WHERE pay=? AND date BETWEEN ? AND ?',
                        (f'card:{c["id"]}', iso(s), iso(e))).fetchone()
        out.append({'id': c['id'], 'label': card_label(c), 'target': target, 'spent': r['exp'], 'count': r['n'],
                    'left': max(0, target - r['exp']), 'pct': pct(r['exp'], target)})
    return out
