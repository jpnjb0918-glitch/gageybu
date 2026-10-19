"""PC판(파이썬) 쪽: 표본 자료 만들기 + 같은 계산 결과 뽑기.
   python3 py_side.py build <db>        — PC판 코드로 표본 자료 파일 만들기
   python3 py_side.py dump <db> <json>  — PC판 코드로 계산한 결과를 JSON 으로
"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
DESK = os.path.abspath(os.path.join(HERE, '..', '..', '..', 'gagyebu-linux'))
sys.path.insert(0, DESK)

from gagyebu import db, util                                       # noqa: E402
from gagyebu.lunar import lunar_to_solar, solar_to_lunar           # noqa: E402
from gagyebu.services import assets as A                           # noqa: E402
from gagyebu.services import calendar_svc as C                     # noqa: E402
from gagyebu.services import ledger as L                           # noqa: E402
from gagyebu.services import order as O                            # noqa: E402
from gagyebu.services import recurring as R                        # noqa: E402
from gagyebu.services import reports as RP                         # noqa: E402

TODAY = dt.date(2026, 10, 16)
D = dt.date


def build(path):
    if os.path.exists(path):
        os.remove(path)
    con = db.connect(path)
    lid = L.first_ledger_id(con)
    add = lambda d, item, inc=0, exp=0, code='30', memo='': L.add_entry(
        con, lid, {'date': d, 'item': item, 'income': inc, 'expense': exp, 'code': code, 'memo': memo})
    for y, m in [(2025, 11), (2025, 12), (2026, 1), (2026, 2), (2026, 8), (2026, 9), (2026, 10)]:
        add(D(y, m, 1), '관리비', exp=180000, code='10')
        add(D(y, m, 5), '전기세', exp=40000 + m * 1000, code='11')
        add(D(y, m, 10), '급여', inc=3200000, code='00')
        add(D(y, m, 12), '점심', exp=9000, code='31', memo='회사 앞')
        add(D(y, m, 12), '점심', exp=11000, code='31')
        add(D(y, m, 25), '마트', exp=87300, code='30')
        add(D(y, m, 28), '환불', inc=15000, code='31')        # 지출 계정에 수입 (환불)
    add(D(2026, 10, 3), '용돈', inc=50000, code='01')
    add(D(2026, 10, 16), '커피', exp=4500, code='31')
    add(D(2026, 10, 16), '택시', exp=13200, code='40')
    L.set_category(con, lid, '32', '간식')
    add(D(2026, 9, 9), '붕어빵', exp=3000, code='32')
    L.set_group(con, lid, '9', '여가')
    L.set_category(con, lid, '90', '영화')
    add(D(2026, 9, 20), '영화관', exp=15000, code='90')
    add(D(2026, 9, 21), '알수없음', exp=1000, code='zz')            # 계정표에 없는 코드
    L.move_category_order(con, lid, '31', -1)
    RP.set_budget(con, lid, '2026-10', '30', 400000)
    RP.set_budget(con, lid, '2026-10', '31', 150000)
    RP.set_budget(con, lid, '2026-11', '31', 120000)
    RP.set_budget(con, lid, '2026-10', '00', 3200000)
    L.merge_category(con, lid, '32', '31')                           # UPSERT 합치기 포함
    r1 = R.save_rule(con, lid, {'item': '적금', 'expense': 300000, 'code': '70', 'day': 25, 'start': D(2026, 7, 1)})
    R.save_rule(con, lid, {'item': '월세', 'expense': 500000, 'code': '10', 'day': 31, 'start': D(2026, 8, 1), 'end': D(2026, 12, 31)})
    R.save_rule(con, lid, {'item': '보너스', 'income': 1000000, 'code': '01', 'day': 20, 'start': D(2026, 10, 1)})
    due, _ = R.pending(con, lid, D(2026, 9, 30))
    R.apply(con, lid, [x for x in due if x['rule']['id'] == r1][:2])
    R.apply(con, lid, [x for x in due if x['rule']['id'] != r1][:1], skip=True)
    lid2 = L.add_ledger(con, '비상금 장부', copy_from=lid, codes_only=True)
    L.add_entry(con, lid2, {'date': D(2026, 10, 2), 'item': '비상금', 'income': 100000, 'code': '00'})
    # 자산
    b1 = A.save_account(con, 'bank', {'company': '국민', 'name': '월급통장', 'opening': 1500000, 'x.password': '1234', 'active': 1})
    b2 = A.save_account(con, 'bank', {'company': '신한', 'name': '예전통장', 'opening': 300000, 'active': 0})
    A.add_tx(con, b1, {'date': D(2026, 10, 10), 'summary': '급여', 'deposit': 3200000})
    A.add_tx(con, b1, {'date': D(2026, 10, 11), 'summary': '마트', 'withdraw': 52000}, ledger_id=lid, code='30')
    A.save_account(con, 'securities', {'company': '키움', 'name': '주식', 'valuation': 2500000, 'deposit': 100000})
    A.save_account(con, 'insurance', {'company': '삼성', 'name': '실손', 'x.status': '정상', 'x.pay_method': '월납'})
    A.save_account(con, 'property', {'name': '아파트', 'x.ptype': 0, 'valuation': 400000000, 'loan': 150000000})
    A.save_account(con, 'property', {'name': '자동차', 'x.ptype': 5, 'valuation': 20000000, 'loan': 5000000})
    c1 = A.save_card(con, {'company': '현대', 'name': 'M카드', 'pay_day': 25, 'bill_from_month': -1, 'bill_from_day': 1,
                           'bill_to_month': -1, 'bill_to_day': 31, 'bank_account_id': b1})
    c2 = A.save_card(con, {'company': '삼성', 'name': '탭탭', 'pay_day': 14, 'bill_from_month': -2, 'bill_from_day': 31,
                           'bill_to_month': -1, 'bill_to_day': 30})
    A.add_card_purchase(con, c1, D(2026, 9, 3), '노트북', 1000000, 30000, 3)
    A.add_card_purchase(con, c1, D(2026, 9, 30), '편의점', 5300)
    A.add_card_purchase(con, c2, D(2026, 10, 1), '주유', 70000)
    tx = [r['id'] for r in A.card_txs(con, c1, '2026-10')]
    A.pay_card(con, tx, D(2026, 10, 25), bank_account_id=b1, ledger_id=lid, code='80')
    # 일정·기념일·주소록·일기·메모
    C.add_schedule(con, D(2026, 10, 20), '치과', remind_days=7)
    C.add_schedule(con, D(2026, 10, 5), '운동', repeat={'type': 'weekdays', 'set': '월, 수, 금'}, until=D(2026, 10, 31))
    C.add_schedule(con, D(2026, 1, 31), '정산', repeat={'type': 'every', 'n': 1, 'unit': '월'}, until=D(2026, 12, 31))
    C.add_schedule(con, D(2026, 10, 1), '모임', repeat={'type': 'nth', 'nth': 4, 'weekday': 4, 'n': 1}, until=D(2027, 3, 31))
    C.save_anniversary(con, {'title': '엄마 생신', 'month': 3, 'day': 30, 'lunar': True})
    C.save_anniversary(con, {'title': '결혼기념일', 'month': 2, 'day': 29})
    C.simple_save(con, 'contact', {'name': '홍길동', 'mobile': '010-1234-5678', 'grp': '친구'})
    C.simple_save(con, 'diary', {'date': '2026-10-16', 'weather': 2, 'title': '흐림', 'content': '오늘은'})
    C.simple_save(con, 'memo', {'title': '장보기', 'content': '우유\n계란', 'created': '2026-10-16 09:00', 'sort': 1})
    # 사용자가 정한 순서 (대분류·소분류·같은 날 내역·주소록·일기·메모)
    C.simple_save(con, 'contact', {'name': '가나다', 'mobile': '010-1111-2222'})
    C.simple_save(con, 'contact', {'name': '나중에', 'grp': '친구'})
    C.simple_save(con, 'diary', {'date': '2026-10-15', 'title': '어제', 'content': ''})
    C.simple_save(con, 'diary', {'date': '2026-10-16', 'title': '오늘 두 번째', 'content': ''})
    C.simple_save(con, 'memo', {'title': '할 일', 'content': '', 'created': '2026-10-16 10:00', 'sort': 2})
    C.simple_save(con, 'memo', {'title': '책 목록', 'content': '', 'created': '2026-10-16 11:00', 'sort': 3})
    con.commit()
    O.set_group_order(con, lid, ['3', '0', '9', '1'])
    O.set_category_order(con, lid, ['31', '30'])
    for d in ('2026-10-12', '2026-10-16', '2026-09-12'):
        ids = [r['id'] for r in con.execute('SELECT id FROM entry WHERE ledger_id=? AND date=? ORDER BY id', (lid, d))]
        O.set_day_order(con, lid, d, ids[::-1])
    O.set_day_order(con, lid, '2026-09-12', sorted(ids))            # 원래 순서로 되돌리면 지워짐
    cids = [r['id'] for r in C.simple_list(con, 'contact', 'name')]
    O.set_list_order(con, 'contact', cids[::-1][:2])                 # 일부만 → 나머지는 뒤에
    dids = [r['id'] for r in C.simple_list(con, 'diary', 'date DESC, id DESC')]
    O.set_list_order(con, 'diary', dids[::-1])
    mids = [r['id'] for r in C.simple_list(con, 'memo', 'sort, id')]
    O.set_memo_order(con, [mids[2], mids[0], mids[1]])
    db.set_meta(con, 'settle_day', 25)
    db.set_meta(con, 'password', util.hash_password('1111'))
    con.commit()
    L.ensure_default_ledgers(con)        # PC판 프로그램이 열 때처럼 기본 장부 추가 (휴대폰판이 다시 더하지 않는지도 비교됨)
    con.close()


def _j(x):
    if isinstance(x, (dt.date, dt.datetime)):
        return x.isoformat()[:10]
    if isinstance(x, (list, tuple)):
        return [_j(v) for v in x]
    if isinstance(x, dict):
        return {str(k if not isinstance(k, dt.date) else k.isoformat()): _j(v) for k, v in x.items()}
    if hasattr(x, 'keys') and hasattr(x, '__getitem__'):          # sqlite3.Row
        return {k: _j(x[k]) for k in x.keys()}
    return x


def rep(r):
    return {'title': r.title, 'columns': r.columns, 'note': r.note,
            'rows': [{'kind': x.kind, 'group': x.group, 'label': x.label, 'code': x.code, 'values': x.values} for x in r.rows],
            'periods': [_j(p) for p in r.periods]}


def dump(path, out):
    tmp = tempfile.mkdtemp()
    p2 = os.path.join(tmp, 'x.sqlite3')
    shutil.copy(path, p2)
    con = db.connect(p2, seed=False)
    res = {}
    for led in L.ledgers(con):
        lid = led['id']
        k = f'L{lid}'
        res[k + '.ewb'] = [[r['id'], b] for r, b in L.entries_with_balance(con, lid)]
        res[k + '.ewb_oct'] = [[r['id'], b] for r, b in L.entries_with_balance(con, lid, D(2026, 10, 1), D(2026, 10, 31))]
        res[k + '.cur'] = L.current_balance(con, lid, TODAY)
        res[k + '.groups'] = _j(L.groups(con, lid))
        res[k + '.cats'] = _j(L.categories(con, lid))
        res[k + '.words'] = _j(L.item_words(con, lid, 1))
        for sd in (1, 25):
            for y, m in [(2026, 10), (2026, 1), (2025, 12)]:
                res[f'{k}.monthly.{y}.{m}.{sd}'] = rep(RP.monthly(con, lid, y, m, sd))
            res[f'{k}.yearly.2026.{sd}'] = rep(RP.yearly(con, lid, 2026, sd))
        res[k + '.daily'] = rep(RP.daily(con, lid, 2026, 10))
        res[k + '.custom'] = rep(RP.custom(con, lid, D(2026, 9, 1), D(2026, 10, 16)))
        res[k + '.budget'] = rep(RP.budget_year(con, lid, 2026))
        for g, c, mo in [(None, None, None), ('3', None, None), (None, '31', None), (None, None, 10)]:
            labels, series = RP.graph_series(con, lid, 2026, group=g, code=c, month=mo, settle_day=25)
            res[f'{k}.graph.{g}.{c}.{mo}'] = {'labels': labels, 'series': [[n, v] for n, v in series.items()]}
        res[k + '.search1'] = [r['id'] for r in L.search(con, lid, text='점심')]
        res[k + '.search2'] = [r['id'] for r in L.search(con, lid, start=D(2026, 9, 1), codes=['31', '30'], order='expense', desc=True)]
        res[k + '.search3'] = [r['id'] for r in L.search(con, lid, amount=9000, amount_side='지출', amount_op='크거나 같은 금액')]
        res[k + '.search4'] = [r['id'] for r in L.search(con, lid, start=D(2026, 10, 1))]
        res[k + '.search5'] = [r['id'] for r in L.search(con, lid, start=D(2026, 9, 1), desc=True)]
        res[k + '.dayord'] = O.day_orders(con, lid)
        res[k + '.ewb_desc'] = [[r['id'], b] for r, b in O.apply_day_order(L.entries_with_balance(con, lid), O.day_orders(con, lid), True)]
        due, later = R.pending(con, lid, TODAY)
        res[k + '.pending'] = [[[x['rule']['id'], x['date'].isoformat()] for x in due], [[x['rule']['id'], x['date'].isoformat()] for x in later]]
        res[k + '.rules'] = _j(R.rules(con, lid))
    res['order.contact'] = [r['id'] for r in O.apply_list_order(con, 'contact', C.simple_list(con, 'contact', 'name'))]
    res['order.contact.grp'] = [r['id'] for r in O.apply_list_order(con, 'contact', C.simple_list(con, 'contact', 'name', 'grp=?', ('친구',)))]
    res['order.diary'] = [r['id'] for r in O.apply_list_order(con, 'diary', C.simple_list(con, 'diary', 'date DESC, id DESC'))]
    res['order.memo'] = [r['id'] for r in C.simple_list(con, 'memo', 'sort, id')]
    res['assets.summary'] = A.summary(con)
    for a in A.accounts(con):
        res[f'acct.{a["id"]}'] = [[r['id'], b] for r, b in A.account_txs(con, a['id'])]
        res[f'acct.{a["id"]}.bal'] = A.account_balance(con, a['id'])
    for c in A.cards(con):
        res[f'card.{c["id"]}'] = _j(A.card_txs(con, c['id']))
        res[f'card.{c["id"]}.unpaid'] = A.card_unpaid_total(con, c['id'])
        res[f'card.{c["id"]}.paydates'] = [A.pay_date_for(c, D(2026, 1, 1) + dt.timedelta(days=i * 11)).isoformat() for i in range(40)]
    res['anniv'] = _j({k: v for k, v in sorted(C.anniversaries_between(con, D(2025, 12, 1), D(2027, 2, 28)).items())})
    res['sched'] = _j(C.schedules(con, D(2026, 1, 1), D(2027, 12, 31)))
    res['remind'] = _j(C.reminders(con, TODAY))
    res['grid'] = _j(C.month_grid(2026, 10))
    rules = [{'type': 'every', 'n': 2, 'unit': '주'}, {'type': 'every', 'n': 1, 'unit': '월'}, {'type': 'every', 'n': 1, 'unit': '년'},
             {'type': 'weekdays', 'set': '화, 목'}, {'type': 'nth', 'nth': 2, 'weekday': 1, 'n': 2}, {'type': 'nth', 'nth': 4, 'weekday': 6, 'n': 1}]
    res['repeat'] = [_j(C.expand_repeat(D(2024, 1, 31), D(2026, 3, 1), r)) for r in rules]
    lun = []
    d = D(1950, 1, 1)
    while d <= D(2050, 12, 31):
        lun.append([d.isoformat(), solar_to_lunar(d)])
        d += dt.timedelta(days=97)
    res['lunar'] = _j(lun)
    res['lunar2'] = _j([lunar_to_solar(y, m, dd, False) for y in (2020, 2026, 2033) for m in (1, 4, 8, 12) for dd in (1, 15, 29, 30)])
    res['meta'] = {r['key']: r['value'] for r in con.execute("SELECT * FROM meta WHERE key<>'password'")}
    res['pw'] = [util.check_password('1111', db.get_meta(con, 'password')), util.check_password('1112', db.get_meta(con, 'password'))]
    con.close()
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, sort_keys=True)


if __name__ == '__main__':
    if sys.argv[1] == 'build':
        build(sys.argv[2])
    else:
        dump(sys.argv[2], sys.argv[3])
