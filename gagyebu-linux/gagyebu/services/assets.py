"""자산관리: 통장·카드·증권·보험·부동산/기타."""
import json

from ..util import add_months, clamp_day, iso, to_date
from . import ledger as L

KIND_LABEL = {'bank': '은행통장', 'securities': '증권', 'insurance': '보험', 'property': '부동산/기타'}
PROPERTY_TYPES = ['아파트', '단독/빌라', '토지/임야', '상가/건물', '공장/창고', '기타자산']   # 원본 목록 순서
OTHER_ASSET = len(PROPERTY_TYPES) - 1
INSURANCE_STATUS = ['정상', '실효']
INSURANCE_CLASS = ['저축성', '보장성']
INSURANCE_TYPES = ['암보험', '질병보험', '재해보험', '상해보험', '기타보험']
INSURANCE_PAY = ['월납', '3월납', '6월납', '연납', '일시납']

# 종류별 화면 항목: (키, 이름, 형식). 형식: text/money/date/int/choice:<목록>/memo/password
FIELDS = {
    'bank': [('company', '은행명', 'text*'), ('name', '통장명', 'text*'), ('owner', '예금주', 'text'),
             ('number', '계좌번호', 'text'), ('opening', '초기 잔액', 'money'), ('x.password', '비밀번호', 'password'),
             ('x.issued', '발행일', 'text'), ('x.maturity', '만기일', 'text'),
             ('active', '사용여부', 'active'), ('memo', '비고', 'memo')],
    'securities': [('company', '증권사명', 'text*'), ('name', '계좌이름', 'text*'), ('number', '계좌번호', 'text'),
                   ('owner', '소유주', 'text'), ('deposit', '추정 예수금', 'money'), ('valuation', '평가금액', 'money'),
                   ('x.valued_on', '최종 평가일', 'date'), ('memo', '비고', 'memo')],
    'insurance': [('company', '보험사명', 'text*'), ('name', '보험 상품명', 'text*'), ('number', '보험증권번호', 'text'),
                  ('owner', '계약자', 'text'), ('x.insured', '피보험자', 'text'), ('x.contract_date', '계약일', 'date'),
                  ('x.maturity', '만기일', 'date'), ('x.status', '계약상태', 'choice:' + '|'.join(INSURANCE_STATUS)),
                  ('x.class', '보험구분', 'choice:' + '|'.join(INSURANCE_CLASS)),
                  ('x.pay_method', '납입방법', 'choice:' + '|'.join(INSURANCE_PAY)),
                  ('x.type', '보험종류', 'choice:' + '|'.join(INSURANCE_TYPES)),
                  ('x.total_count', '만기 납입횟수', 'int'), ('x.paid_count', '납입횟수', 'int'),
                  ('x.paid_total', '납입보험료 누계', 'money'), ('x.agent', '담당자 및 연락처', 'text'), ('memo', '비고', 'memo')],
    'property': [('x.ptype', '구분', 'choice:' + '|'.join(PROPERTY_TYPES)), ('name', '자산명', 'text*'),
                 ('owner', '소유주/임차인', 'text'), ('x.acquired', '취득/임차일자', 'date'),
                 ('valuation', '취득/평가금액', 'money'), ('x.valued_on', '최종 평가일', 'date'),
                 ('loan', '대출금액', 'money'), ('memo', '비고', 'memo')],
}
CARD_FIELDS = [('company', '카드사명', 'text*'), ('name', '카드명', 'text*'), ('number', '카드번호', 'text'),
               ('x.password', '카드 비밀번호', 'password'), ('x.valid_ym', '유효기간(YYYY-MM)', 'text'),
               ('pay_day', '결제일', 'int'), ('bill_from_month', '청구기간 시작(월)', 'billmonth'),
               ('bill_from_day', '청구기간 시작(일)', 'int'), ('bill_to_month', '청구기간 끝(월)', 'billmonth'),
               ('bill_to_day', '청구기간 끝(일)', 'int'), ('bank_account_id', '결제 통장', 'bank'),
               ('x.limit', '카드사용한도', 'money'), ('x.cash_limit', '현금서비스 한도', 'money'),
               ('x.loan_limit', '대출한도', 'money'), ('x.issued', '발행일', 'date'), ('memo', '비고', 'memo')]


def _split(values):
    cols, extra = {}, {}
    for k, v in values.items():
        if k.startswith('x.'):
            extra[k[2:]] = v
        else:
            cols[k] = v
    return cols, extra


def merge_extra(row):
    d = dict(row)
    for k, v in json.loads(d.pop('extra') or '{}').items():
        d['x.' + k] = v
    return d


# ── 통장·증권·보험·부동산 ───────────────────────────────
def accounts(con, kind=None):
    if kind:
        return con.execute('SELECT * FROM account WHERE kind=? ORDER BY sort, id', (kind,)).fetchall()
    return con.execute('SELECT * FROM account ORDER BY kind, sort, id').fetchall()


def save_account(con, kind, values, aid=None):
    cols, extra = _split(values)
    if aid:
        old = json.loads(con.execute('SELECT extra FROM account WHERE id=?', (aid,)).fetchone()['extra'] or '{}')
        old.update(extra)
        cols['extra'] = json.dumps(old, ensure_ascii=False)
        sets = ','.join(f'{k}=?' for k in cols)
        con.execute(f'UPDATE account SET {sets} WHERE id=?', list(cols.values()) + [aid])
    else:
        cols['extra'] = json.dumps(extra, ensure_ascii=False)
        cols['kind'] = kind
        cols.setdefault('sort', con.execute('SELECT COALESCE(MAX(sort),0)+1 FROM account WHERE kind=?',
                                            (kind,)).fetchone()[0])
        aid = con.execute(f'INSERT INTO account({",".join(cols)}) VALUES({",".join("?" * len(cols))})',
                          list(cols.values())).lastrowid
    con.commit()
    return aid


def delete_account(con, aid):
    con.execute('DELETE FROM account WHERE id=?', (aid,))
    con.commit()


def move(con, table, rid, delta, where='1=1', args=()):
    rows = [r['id'] for r in con.execute(f'SELECT id FROM {table} WHERE {where} ORDER BY sort, id', args)]
    i = rows.index(rid)
    j = i + delta
    if 0 <= j < len(rows):
        rows[i], rows[j] = rows[j], rows[i]
        for k, r in enumerate(rows):
            con.execute(f'UPDATE {table} SET sort=? WHERE id=?', (k, r))
        con.commit()


def account_balance(con, aid, upto=None):
    a = con.execute('SELECT opening FROM account WHERE id=?', (aid,)).fetchone()
    q = 'SELECT COALESCE(SUM(deposit-withdraw),0) FROM account_tx WHERE account_id=?'
    args = [aid]
    if upto:
        q += ' AND date<=?'
        args.append(iso(upto))
    return (a['opening'] if a else 0) + con.execute(q, args).fetchone()[0]


def account_txs(con, aid, start=None, end=None):
    """거래 + 누적 잔액."""
    a = con.execute('SELECT * FROM account WHERE id=?', (aid,)).fetchone()
    rows = con.execute('SELECT * FROM account_tx WHERE account_id=? ORDER BY date, id', (aid,)).fetchall()
    bal = a['opening'] if a and a['kind'] == 'bank' else 0
    out = []
    for r in rows:
        bal += r['deposit'] - r['withdraw']
        if (not start or r['date'] >= iso(start)) and (not end or r['date'] <= iso(end)):
            out.append((r, bal))
    return out


def add_tx(con, aid, tx, ledger_id=None, code=None):
    """거래 저장. ledger_id·code 를 주면 '장부에도 동시저장' (입금→수입, 출금→지출)."""
    eid = None
    if ledger_id and code:
        a = con.execute('SELECT name FROM account WHERE id=?', (aid,)).fetchone()
        eid = L.add_entry(con, ledger_id, {'date': tx['date'], 'item': tx.get('summary') or a['name'],
                                           'income': tx.get('deposit', 0), 'expense': tx.get('withdraw', 0),
                                           'code': code, 'memo': tx.get('memo', '')},
                          origin=f'account:{aid}', commit=False)
    tid = con.execute('INSERT INTO account_tx(account_id,date,summary,deposit,withdraw,memo,entry_id) '
                      'VALUES(?,?,?,?,?,?,?)', (aid, iso(tx['date']), tx.get('summary', ''), int(tx.get('deposit') or 0),
                                               int(tx.get('withdraw') or 0), tx.get('memo', ''), eid)).lastrowid
    con.commit()
    return tid


def update_tx(con, tid, tx):
    con.execute('UPDATE account_tx SET date=?,summary=?,deposit=?,withdraw=?,memo=? WHERE id=?',
                (iso(tx['date']), tx.get('summary', ''), int(tx.get('deposit') or 0), int(tx.get('withdraw') or 0),
                 tx.get('memo', ''), tid))
    con.commit()


def delete_tx(con, tid, with_entry=False):
    r = con.execute('SELECT entry_id FROM account_tx WHERE id=?', (tid,)).fetchone()
    if with_entry and r and r['entry_id']:
        con.execute('DELETE FROM entry WHERE id=?', (r['entry_id'],))
    con.execute('DELETE FROM account_tx WHERE id=?', (tid,))
    con.commit()


# ── 신용카드 ────────────────────────────────────────────
def cards(con):
    return con.execute('SELECT * FROM card ORDER BY sort, id').fetchall()


def save_card(con, values, cid=None):
    cols, extra = _split(values)
    if cid:
        old = json.loads(con.execute('SELECT extra FROM card WHERE id=?', (cid,)).fetchone()['extra'] or '{}')
        old.update(extra)
        cols['extra'] = json.dumps(old, ensure_ascii=False)
        con.execute(f'UPDATE card SET {",".join(f"{k}=?" for k in cols)} WHERE id=?', list(cols.values()) + [cid])
    else:
        cols['extra'] = json.dumps(extra, ensure_ascii=False)
        cols.setdefault('sort', con.execute('SELECT COALESCE(MAX(sort),0)+1 FROM card').fetchone()[0])
        cid = con.execute(f'INSERT INTO card({",".join(cols)}) VALUES({",".join("?" * len(cols))})',
                          list(cols.values())).lastrowid
    con.commit()
    return cid


def delete_card(con, cid):
    con.execute('DELETE FROM card WHERE id=?', (cid,))
    con.commit()


def billing_window(card, pay_y, pay_m):
    fy, fm = add_months(pay_y, pay_m, card['bill_from_month'])
    ty, tm = add_months(pay_y, pay_m, card['bill_to_month'])
    return clamp_day(fy, fm, card['bill_from_day']), clamp_day(ty, tm, card['bill_to_day'])


def pay_date_for(card, purchase_date):
    """거래일이 속한 청구기간으로 결제일 계산 (원본: 거래일자 선택 시 결제일 자동 선택)."""
    d = to_date(purchase_date)
    for k in range(-1, 5):
        y, m = add_months(d.year, d.month, k)
        lo, hi = billing_window(card, y, m)
        if lo <= d <= hi:
            return clamp_day(y, m, card['pay_day'])
    y, m = add_months(d.year, d.month, 1)
    return clamp_day(y, m, card['pay_day'])


def add_card_purchase(con, cid, date, summary, total, fee_total=0, months=1, pay_date=None, memo=''):
    """사용금액·수수료는 전체 금액을 입력, 할부개월로 나눠 회차별로 저장 (원본 도움말)."""
    card = con.execute('SELECT * FROM card WHERE id=?', (cid,)).fetchone()
    months = max(1, int(months or 1))
    first = to_date(pay_date) if pay_date else pay_date_for(card, date)
    base, rem = divmod(int(total), months)
    fbase, frem = divmod(int(fee_total or 0), months)
    gid = (con.execute('SELECT COALESCE(MAX(group_id),0)+1 FROM card_tx').fetchone()[0])
    for k in range(months):
        y, m = add_months(first.year, first.month, k)
        pd = clamp_day(y, m, first.day if k == 0 else card['pay_day'])
        con.execute('INSERT INTO card_tx(card_id,group_id,date,summary,total,fee_total,months,seq,amount,fee,pay_date,memo) '
                    'VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                    (cid, gid, iso(date), summary, int(total), int(fee_total or 0), months, k + 1,
                     base + (rem if k == 0 else 0), fbase + (frem if k == 0 else 0), iso(pd), memo))
    con.commit()
    return gid


def delete_card_group(con, card_id, group_id):
    con.execute('DELETE FROM card_tx WHERE card_id=? AND group_id=?', (card_id, group_id))
    con.commit()


def card_txs(con, cid, ym=None, paid=None):
    """ym='YYYY-MM' 결제월 기준. paid: None=모두, 0=미결제, 1=결제완료."""
    q = 'SELECT * FROM card_tx WHERE card_id=?'
    a = [cid]
    if ym:
        q += ' AND substr(pay_date,1,7)=?'
        a.append(ym)
    if paid is not None:
        q += ' AND paid=?'
        a.append(paid)
    return con.execute(q + ' ORDER BY pay_date, date, id', a).fetchall()


def card_unpaid_total(con, cid=None, until=None):
    q = 'SELECT COALESCE(SUM(amount+fee),0) FROM card_tx WHERE paid=0'
    a = []
    if cid:
        q += ' AND card_id=?'
        a.append(cid)
    if until:
        q += ' AND pay_date<=?'
        a.append(iso(until))
    return con.execute(q, a).fetchone()[0]


def pay_card(con, tx_ids, pay_date, bank_account_id=None, ledger_id=None, code=None):
    """선택 회차 결제 처리. 통장·장부에 동시 기록 옵션 (원본 '통장 및 장부에 동시입력')."""
    if not tx_ids:
        return 0
    rows = con.execute(f'SELECT t.*, c.name cname FROM card_tx t JOIN card c ON c.id=t.card_id '
                       f'WHERE t.id IN ({",".join("?" * len(tx_ids))}) AND t.paid=0', list(tx_ids)).fetchall()
    total = sum(r['amount'] + r['fee'] for r in rows)
    if not rows:
        return 0
    cname = rows[0]['cname']
    atx = eid = None
    if bank_account_id:
        atx = con.execute('INSERT INTO account_tx(account_id,date,summary,deposit,withdraw,memo) VALUES(?,?,?,?,?,?)',
                          (bank_account_id, iso(pay_date), f'{cname} 카드대금', 0, total, '')).lastrowid
    if ledger_id and code:
        eid = L.add_entry(con, ledger_id, {'date': pay_date, 'item': f'{cname} 카드대금', 'expense': total,
                                           'code': code}, origin='card_pay', commit=False)
    for r in rows:
        con.execute('UPDATE card_tx SET paid=1, paid_entry_id=?, paid_account_tx_id=? WHERE id=?', (eid, atx, r['id']))
    con.commit()
    return total


def unpay_card(con, tx_ids):
    """결제 취소. 같은 결제로 처리된 회차는 함께 미결제로 되돌리고, 그 결제 때 통장·장부에 남긴 기록도 지움
    (그대로 두면 다시 결제할 때 출금·지출이 두 번 잡힘). 반환: 미결제로 되돌린 건수."""
    if not tx_ids:
        return 0
    rows = con.execute(f'SELECT id, paid_entry_id, paid_account_tx_id FROM card_tx '
                       f'WHERE id IN ({",".join("?" * len(tx_ids))}) AND paid=1', list(tx_ids)).fetchall()
    ids = {r['id'] for r in rows}
    for r in rows:
        if r['paid_entry_id'] or r['paid_account_tx_id']:
            for x in con.execute('SELECT id FROM card_tx WHERE paid=1 AND ((paid_entry_id IS NOT NULL AND paid_entry_id=?) '
                                 'OR (paid_account_tx_id IS NOT NULL AND paid_account_tx_id=?))',
                                 (r['paid_entry_id'], r['paid_account_tx_id'])):
                ids.add(x['id'])
            if r['paid_entry_id']:
                con.execute('DELETE FROM entry WHERE id=?', (r['paid_entry_id'],))
            if r['paid_account_tx_id']:
                con.execute('DELETE FROM account_tx WHERE id=?', (r['paid_account_tx_id'],))
    con.executemany('UPDATE card_tx SET paid=0, paid_entry_id=NULL, paid_account_tx_id=NULL WHERE id=?',
                    [(i,) for i in ids])
    con.commit()
    return len(ids)


# ── 자산 요약 (원본 자산관리 메인 하단) ──────────────────
def summary(con, today=None):
    s = {'예금': 0, '증권': 0, '부동산': 0, '기타': 0, '대출': 0, '카드': 0, '기타부채': 0}
    for a in accounts(con):
        x = json.loads(a['extra'] or '{}')
        if a['kind'] == 'bank' and a['active']:
            s['예금'] += account_balance(con, a['id'])
        elif a['kind'] == 'securities':
            s['증권'] += a['valuation']
        elif a['kind'] == 'property':
            if int(x.get('ptype') or 0) == OTHER_ASSET:
                s['기타'] += a['valuation']
                s['기타부채'] += a['loan']
            else:
                s['부동산'] += a['valuation']
                s['대출'] += a['loan']
    s['카드'] = card_unpaid_total(con)
    s['자산합계'] = s['예금'] + s['증권'] + s['부동산'] + s['기타']
    s['부채합계'] = s['대출'] + s['카드'] + s['기타부채']
    s['순자산'] = s['자산합계'] - s['부채합계']
    return s
