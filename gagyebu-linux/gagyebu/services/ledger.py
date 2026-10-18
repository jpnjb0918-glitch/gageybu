"""장부·계정과목·수입/지출 내역."""
from ..util import CODE_CHARS, iso, is_income_code


# ── 장부 ────────────────────────────────────────────────
def ledgers(con):
    return con.execute('SELECT * FROM ledger ORDER BY sort, id').fetchall()


def add_ledger(con, name, copy_from=None, codes_only=False):
    """새 장부. copy_from 이 있으면 그 장부를 복사(codes_only=True면 계정과목만)."""
    sort = (con.execute('SELECT COALESCE(MAX(sort),0)+1 FROM ledger').fetchone()[0])
    lid = con.execute('INSERT INTO ledger(name, sort) VALUES(?,?)', (name, sort)).lastrowid
    if copy_from:
        con.execute('INSERT INTO cat_group SELECT ?, code, name FROM cat_group WHERE ledger_id=?', (lid, copy_from))
        con.execute('INSERT INTO category SELECT ?, code, name, sort FROM category WHERE ledger_id=?', (lid, copy_from))
        if not codes_only:
            con.execute('INSERT INTO entry(ledger_id,date,item,income,expense,code,memo,origin) '
                        'SELECT ?,date,item,income,expense,code,memo,origin FROM entry WHERE ledger_id=? ORDER BY date,id',
                        (lid, copy_from))
            con.execute('INSERT INTO budget SELECT ?, ym, code, amount FROM budget WHERE ledger_id=?', (lid, copy_from))
            con.execute('INSERT INTO item_word SELECT ?, name, count FROM item_word WHERE ledger_id=?', (lid, copy_from))
            from .recurring import processed_through
            for r in con.execute('SELECT * FROM recurring WHERE ledger_id=?', (copy_from,)).fetchall():
                thr = processed_through(con, r['id'])
                con.execute('INSERT INTO recurring(ledger_id,item,income,expense,code,day,start,end,memo,created,'
                            'applied_through) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                            (lid, r['item'], r['income'], r['expense'], r['code'], r['day'], r['start'], r['end'],
                             r['memo'], r['created'], iso(thr) if thr else None))
    else:
        con.execute("INSERT INTO cat_group VALUES(?, '0', '수입')", (lid,))
    con.commit()
    return lid


def rename_ledger(con, lid, name):
    con.execute('UPDATE ledger SET name=? WHERE id=?', (name, lid))
    con.commit()


def first_ledger_id(con):
    r = con.execute('SELECT id FROM ledger ORDER BY sort, id LIMIT 1').fetchone()
    return r['id'] if r else None


def delete_ledger(con, lid):
    if lid == first_ledger_id(con):
        raise ValueError('첫 번째 장부는 삭제할 수 없습니다 (이름 변경은 가능).')
    con.execute('DELETE FROM ledger WHERE id=?', (lid,))
    con.commit()


def reset_ledger(con, lid):
    """장부 데이터 초기화: 내역·예산·예약 삭제, 계정과목은 유지 (원본 도움말 기준)."""
    for t in ('entry', 'budget', 'recurring_log', 'recurring', 'item_word'):
        con.execute(f'DELETE FROM {t} WHERE ledger_id=?', (lid,))
    con.commit()


# ── 계정과목 ────────────────────────────────────────────
def groups(con, lid):
    """대분류 (사용자가 정한 순서가 있으면 그 순서, 없으면 코드 순)"""
    from . import order as O
    rows = con.execute('SELECT code, name FROM cat_group WHERE ledger_id=?', (lid,)).fetchall()
    rows = sorted(rows, key=lambda r: CODE_CHARS.find(r['code']) if r['code'] in CODE_CHARS else 99)
    return O.by_list(rows, O.group_order(con, lid), key=lambda r: r['code'])


def _group_rank(con, lid):
    return {g['code']: i for i, g in enumerate(groups(con, lid))}


def categories(con, lid, group=None):
    """소분류: 대분류 순서 → sort(사용자가 정한 순서) → 코드"""
    q = 'SELECT code, name, sort FROM category WHERE ledger_id=?'
    args = [lid]
    if group is not None:
        q += ' AND substr(code,1,1)=?'
        args.append(group)
    rows = con.execute(q, args).fetchall()
    rank = _group_rank(con, lid)
    return sorted(rows, key=lambda r: (rank.get(r['code'][:1], 100 + max(CODE_CHARS.find(r['code'][:1]), 0)),
                                       r['sort'], r['code']))


def category_map(con, lid):
    return {r['code']: r['name'] for r in con.execute('SELECT code,name FROM category WHERE ledger_id=?', (lid,))}


def group_map(con, lid):
    return {r['code']: r['name'] for r in con.execute('SELECT code,name FROM cat_group WHERE ledger_id=?', (lid,))}


def set_group(con, lid, code, name):
    if code == '0' and con.execute("SELECT 1 FROM cat_group WHERE ledger_id=? AND code='0'", (lid,)).fetchone():
        name = '수입'   # 0번은 수입 고정
    if not name:
        return
    con.execute('INSERT INTO cat_group VALUES(?,?,?) ON CONFLICT(ledger_id,code) DO UPDATE SET name=excluded.name',
                (lid, code, name))
    con.commit()


def delete_group(con, lid, code):
    if code == '0':
        raise ValueError('0번(수입) 대분류는 삭제할 수 없습니다.')
    if categories(con, lid, code):
        raise ValueError('소분류가 남아 있으면 대분류를 삭제할 수 없습니다.')
    con.execute('DELETE FROM cat_group WHERE ledger_id=? AND code=?', (lid, code))
    con.commit()


def set_category(con, lid, code, name):
    if not name:
        return
    sort = con.execute('SELECT sort FROM category WHERE ledger_id=? AND code=?', (lid, code)).fetchone()
    if sort is None:
        nxt = con.execute('SELECT COALESCE(MAX(sort),0)+1 FROM category WHERE ledger_id=? AND substr(code,1,1)=?',
                          (lid, code[:1])).fetchone()[0]
        con.execute('INSERT INTO category VALUES(?,?,?,?)', (lid, code, name, nxt))
    else:
        con.execute('UPDATE category SET name=? WHERE ledger_id=? AND code=?', (name, lid, code))
    con.commit()


def move_category_order(con, lid, code, delta):
    rows = categories(con, lid, code[:1])
    codes = [r['code'] for r in rows]
    i = codes.index(code)
    j = i + delta
    if not 0 <= j < len(codes):
        return
    codes[i], codes[j] = codes[j], codes[i]
    for k, c in enumerate(codes):
        con.execute('UPDATE category SET sort=? WHERE ledger_id=? AND code=?', (k, lid, c))
    con.commit()


def merge_category(con, lid, src, dst):
    """src 계정으로 입력된 모든 내역·예약·예산을 dst 로 옮기고 src 삭제 (원본의 '이동')."""
    if src == dst:
        return
    if not con.execute('SELECT 1 FROM category WHERE ledger_id=? AND code=?', (lid, dst)).fetchone():
        raise ValueError(f'계정코드 {dst} 가 없습니다.')
    con.execute('UPDATE entry SET code=? WHERE ledger_id=? AND code=?', (dst, lid, src))
    con.execute('UPDATE recurring SET code=? WHERE ledger_id=? AND code=?', (dst, lid, src))
    for r in con.execute('SELECT ym, amount FROM budget WHERE ledger_id=? AND code=?', (lid, src)).fetchall():
        con.execute('INSERT INTO budget VALUES(?,?,?,?) ON CONFLICT(ledger_id,ym,code) '
                    'DO UPDATE SET amount=amount+excluded.amount', (lid, r['ym'], dst, r['amount']))
    con.execute('DELETE FROM budget WHERE ledger_id=? AND code=?', (lid, src))
    con.execute('DELETE FROM category WHERE ledger_id=? AND code=?', (lid, src))
    con.commit()


def category_usage(con, lid, code):
    q = lambda t: con.execute(f'SELECT COUNT(*) FROM {t} WHERE ledger_id=? AND code=?', (lid, code)).fetchone()[0]
    return {'entry': q('entry'), 'recurring': q('recurring'), 'budget': q('budget')}


def delete_category(con, lid, code):
    """원본과 같이 그 계정의 내역·예약·예산도 함께 삭제."""
    for t in ('entry', 'recurring', 'budget', 'category'):
        con.execute(f'DELETE FROM {t} WHERE ledger_id=? AND code=?', (lid, code))
    con.commit()


# ── 내역 ────────────────────────────────────────────────
def _norm(e):
    return (iso(e['date']), (e.get('item') or '').strip(), int(e.get('income') or 0), int(e.get('expense') or 0),
            (e.get('code') or '').strip(), (e.get('memo') or '').strip())


def add_entry(con, lid, e, origin=None, commit=True):
    d, item, inc, exp, code, memo = _norm(e)
    eid = con.execute('INSERT INTO entry(ledger_id,date,item,income,expense,code,memo,origin) VALUES(?,?,?,?,?,?,?,?)',
                      (lid, d, item, inc, exp, code, memo, origin)).lastrowid
    if item:
        con.execute('INSERT INTO item_word VALUES(?,?,1) ON CONFLICT(ledger_id,name) DO UPDATE SET count=count+1',
                    (lid, item))
    if commit:
        con.commit()
    return eid


def update_entry(con, eid, e):
    d, item, inc, exp, code, memo = _norm(e)
    con.execute('UPDATE entry SET date=?,item=?,income=?,expense=?,code=?,memo=? WHERE id=?',
                (d, item, inc, exp, code, memo, eid))
    con.commit()


def delete_entries(con, ids):
    con.executemany('DELETE FROM entry WHERE id=?', [(i,) for i in ids])
    con.commit()


def get_entry(con, eid):
    return con.execute('SELECT * FROM entry WHERE id=?', (eid,)).fetchone()


def balance_before(con, lid, date):
    r = con.execute('SELECT COALESCE(SUM(income-expense),0) FROM entry WHERE ledger_id=? AND date<?',
                    (lid, iso(date))).fetchone()
    return r[0]


def entries_with_balance(con, lid, start=None, end=None):
    """날짜순 내역 + 각 행까지의 누적 잔액(이전 기간 이월 포함)."""
    q = 'SELECT * FROM entry WHERE ledger_id=?'
    args = [lid]
    if start:
        q += ' AND date>=?'
        args.append(iso(start))
    if end:
        q += ' AND date<=?'
        args.append(iso(end))
    rows = con.execute(q + ' ORDER BY date, id', args).fetchall()
    from . import order as O
    rows = O.apply_day_order(rows, O.day_orders(con, lid))        # 같은 날 안은 사용자가 정한 순서
    bal = balance_before(con, lid, start) if start else 0
    out = []
    for r in rows:
        bal += r['income'] - r['expense']
        out.append((r, bal))
    return out


def totals(con, lid, start, end):
    r = con.execute('SELECT COALESCE(SUM(income),0), COALESCE(SUM(expense),0) FROM entry '
                    'WHERE ledger_id=? AND date BETWEEN ? AND ?', (lid, iso(start), iso(end))).fetchone()
    return r[0], r[1]


def current_balance(con, lid, upto=None):
    q = 'SELECT COALESCE(SUM(income-expense),0) FROM entry WHERE ledger_id=?'
    args = [lid]
    if upto:
        q += ' AND date<=?'
        args.append(iso(upto))
    return con.execute(q, args).fetchone()[0]


AMOUNT_OPS = {'같은 금액': '=', '크거나 같은 금액': '>=', '작거나 같은 금액': '<=', '큰 금액': '>', '작은 금액': '<'}


def search(con, lid, start=None, end=None, text=None, codes=None, amount=None, amount_side='수입+지출',
           amount_op='같은 금액', order='date', desc=False):
    """원본 검색 조건 4가지 (AND 조건): 기간·품목 글자·계정코드(복수)·금액."""
    q = 'SELECT * FROM entry WHERE ledger_id=?'
    a = [lid]
    if start:
        q += ' AND date>=?'
        a.append(iso(start))
    if end:
        q += ' AND date<=?'
        a.append(iso(end))
    if text:
        q += " AND (item LIKE ? ESCAPE '\\' OR memo LIKE ? ESCAPE '\\')"
        t = '%' + text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        a += [t, t]
    if codes:
        q += f" AND code IN ({','.join('?' * len(codes))})"
        a += list(codes)
    if amount is not None:
        op = AMOUNT_OPS[amount_op]
        if amount_side == '수입':
            q += f' AND income {op} ? AND income<>0'
            a.append(amount)
        elif amount_side == '지출':
            q += f' AND expense {op} ? AND expense<>0'
            a.append(amount)
        else:
            q += f' AND ((income<>0 AND income {op} ?) OR (expense<>0 AND expense {op} ?))'
            a += [amount, amount]
    col = {'date': 'date', 'item': 'item', 'income': 'income', 'expense': 'expense', 'code': 'code',
           'memo': 'memo'}.get(order, 'date')
    q += f" ORDER BY {col} {'DESC' if desc else 'ASC'}, id {'DESC' if desc else 'ASC'}"
    rows = con.execute(q, a).fetchall()
    if col == 'date':
        from . import order as O
        rows = O.apply_day_order(sorted(rows, key=lambda r: (r['date'], r['id'])), O.day_orders(con, lid), desc)
    return rows


# ── 품목 자동완성 ───────────────────────────────────────
def item_words(con, lid, min_count=1):
    return con.execute('SELECT name, count FROM item_word WHERE ledger_id=? AND count>=? ORDER BY count DESC, name',
                       (lid, min_count)).fetchall()


def set_item_word(con, lid, name, count, old_name=None):
    if old_name and old_name != name:
        con.execute('DELETE FROM item_word WHERE ledger_id=? AND name=?', (lid, old_name))
    con.execute('INSERT INTO item_word VALUES(?,?,?) ON CONFLICT(ledger_id,name) DO UPDATE SET count=excluded.count',
                (lid, name, count))
    con.commit()


def delete_item_word(con, lid, name):
    con.execute('DELETE FROM item_word WHERE ledger_id=? AND name=?', (lid, name))
    con.commit()


def last_code_for_item(con, lid, item):
    r = con.execute('SELECT code FROM entry WHERE ledger_id=? AND item=? ORDER BY date DESC, id DESC LIMIT 1',
                    (lid, item)).fetchone()
    return r['code'] if r else None


def code_label(cmap, code):
    return cmap.get(code) or (f'(미분류 {code})' if code else '(미분류)')


def signed_amount(code, income, expense):
    """보고서용: 수입 계정은 수입-지출, 지출 계정은 지출-수입 (환불 등 반대 방향 입력도 반영)."""
    return (income - expense) if is_income_code(code) else (expense - income)
