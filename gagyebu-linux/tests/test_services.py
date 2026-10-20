import datetime as dt
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from gagyebu import db, util                                       # noqa: E402
from gagyebu.lunar import lunar_to_solar, solar_to_lunar           # noqa: E402
from gagyebu.services import assets as A                           # noqa: E402
from gagyebu.services import backup as B                           # noqa: E402
from gagyebu.services import calendar_svc as C                     # noqa: E402
from gagyebu.services import importer as I                         # noqa: E402
from gagyebu.services import ledger as L                           # noqa: E402
from gagyebu.services import recurring as R                        # noqa: E402
from gagyebu.services import reports as RP                         # noqa: E402
from gagyebu.services import attach as AT                          # noqa: E402
from gagyebu.services import goals as G                            # noqa: E402
from gagyebu.services import insights as INS                       # noqa: E402
from gagyebu.services import smsparse as SMS                       # noqa: E402

D = dt.date


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.con = db.connect(os.path.join(self.tmp, 't.sqlite3'))
        self.lid = L.first_ledger_id(self.con)

    def add(self, d, item, inc=0, exp=0, code='30'):
        return L.add_entry(self.con, self.lid, {'date': d, 'item': item, 'income': inc, 'expense': exp, 'code': code})


class TestUtil(unittest.TestCase):
    def test_money(self):
        self.assertEqual(util.parse_money('1,234원'), 1234)
        self.assertEqual(util.parse_money(''), 0)
        self.assertEqual(util.parse_money('1000000.0000'), 1000000)
        self.assertEqual(util.fmt_money(1234567), '1,234,567')
        with self.assertRaises(ValueError):
            util.parse_money('abc')

    def test_settle_period(self):
        self.assertEqual(util.settle_period(2026, 2, 1), (D(2026, 2, 1), D(2026, 2, 28)))
        # 결산일 5일: 이달 5일 ~ 다음달 4일 (원본 도움말)
        self.assertEqual(util.settle_period(2026, 1, 5), (D(2026, 1, 5), D(2026, 2, 4)))
        self.assertEqual(util.settle_period(2026, 12, 5), (D(2026, 12, 5), D(2027, 1, 4)))
        # 결산일 31일: 2월은 말일
        self.assertEqual(util.settle_period(2026, 2, 31), (D(2026, 2, 28), D(2026, 3, 30)))

    def test_password(self):
        h = util.hash_password('1111')
        self.assertTrue(util.check_password('1111', h))
        self.assertFalse(util.check_password('1112', h))


class TestLedger(Base):
    def test_balance_and_totals(self):
        self.add('2026-01-10', '급여', inc=3000000, code='00')
        self.add('2026-01-11', '커피', exp=4500)
        self.add('2026-02-01', '전기세', exp=50000, code='11')
        rows = L.entries_with_balance(self.con, self.lid)
        self.assertEqual([b for _, b in rows], [3000000, 2995500, 2945500])
        rows = L.entries_with_balance(self.con, self.lid, D(2026, 2, 1), D(2026, 2, 28))
        self.assertEqual([b for _, b in rows], [2945500])          # 이전 잔액 이월 반영
        self.assertEqual(L.totals(self.con, self.lid, D(2026, 1, 1), D(2026, 1, 31)), (3000000, 4500))
        self.assertEqual(L.current_balance(self.con, self.lid), 2945500)

    def test_search_and(self):
        self.add('2026-01-10', '아메리카노', exp=4500)
        self.add('2026-01-12', '라떼', exp=5000)
        self.add('2026-01-15', '아메리카노', exp=4500, code='31')
        r = L.search(self.con, self.lid, text='아메리카노', codes=['30'])
        self.assertEqual(len(r), 1)
        r = L.search(self.con, self.lid, amount=5000, amount_side='지출', amount_op='크거나 같은 금액')
        self.assertEqual([x['item'] for x in r], ['라떼'])
        r = L.search(self.con, self.lid, start=D(2026, 1, 11), end=D(2026, 1, 31), desc=True)
        self.assertEqual([x['item'] for x in r], ['아메리카노', '라떼'])
        self.assertEqual(L.search(self.con, self.lid, text='100%'), [])   # LIKE 특수문자 이스케이프

    def test_merge_and_delete_category(self):
        self.add('2026-01-10', 'a', exp=100, code='30')
        R.save_rule(self.con, self.lid, {'item': 'x', 'expense': 1, 'code': '30', 'day': 1, 'start': '2026-01-01'})
        RP.set_budget(self.con, self.lid, '2026-01', '30', 1000)
        RP.set_budget(self.con, self.lid, '2026-01', '31', 500)
        L.merge_category(self.con, self.lid, '30', '31')
        self.assertEqual(L.category_usage(self.con, self.lid, '31'), {'entry': 1, 'recurring': 1, 'budget': 1})
        self.assertEqual(RP.budgets(self.con, self.lid, '2026-01')['31'], 1500)
        self.assertNotIn('30', L.category_map(self.con, self.lid))
        L.delete_category(self.con, self.lid, '31')
        self.assertEqual(L.category_usage(self.con, self.lid, '31'), {'entry': 0, 'recurring': 0, 'budget': 0})

    def test_group_rules(self):
        with self.assertRaises(ValueError):
            L.delete_group(self.con, self.lid, '0')
        with self.assertRaises(ValueError):
            L.delete_group(self.con, self.lid, '3')        # 소분류가 있음
        L.set_group(self.con, self.lid, '0', '용돈')
        self.assertEqual(L.group_map(self.con, self.lid)['0'], '수입')   # 0번은 이름 고정

    def test_ledger_copy_reset_delete(self):
        self.add('2026-01-10', 'a', exp=100)
        c = L.add_ledger(self.con, '복사본', copy_from=self.lid)
        self.assertEqual(L.current_balance(self.con, c), -100)
        k = L.add_ledger(self.con, '계정만', copy_from=self.lid, codes_only=True)
        self.assertEqual(L.current_balance(self.con, k), 0)
        self.assertEqual(L.category_map(self.con, k), L.category_map(self.con, self.lid))
        L.reset_ledger(self.con, c)
        self.assertEqual(L.current_balance(self.con, c), 0)
        with self.assertRaises(ValueError):
            L.delete_ledger(self.con, self.lid)
        L.delete_ledger(self.con, c)
        self.assertEqual(len(L.ledgers(self.con)), 2)


class TestReports(Base):
    def setUp(self):
        super().setUp()
        self.add('2025-12-20', '이월', inc=100000, code='01')
        self.add('2026-01-05', '급여', inc=2000000, code='00')
        self.add('2026-01-04', '전기', exp=30000, code='11')
        self.add('2026-02-03', '전기', exp=40000, code='11')
        self.add('2026-02-10', '환불', inc=5000, code='11')       # 지출 계정에 들어온 환불
        self.add('2026-02-11', '미분류', exp=7000, code='99')

    def footer(self, rep, label):
        return next(r.values for r in rep.rows if r.kind == 'footer' and r.label == label)

    def cat(self, rep, code):
        return next(r.values for r in rep.rows if r.kind == 'cat' and r.code == code)

    def test_monthly(self):
        rep = RP.monthly(self.con, self.lid, 2026, 2, settle_day=1)
        self.assertEqual(self.cat(rep, '11')[:3], [30000, 35000, 5000])     # 40000-5000 환불 반영
        self.assertEqual(self.footer(rep, '전월 이월금')[:2], [100000, 2070000])
        self.assertEqual(self.footer(rep, '수입계')[:2], [2000000, 0])
        self.assertEqual(self.footer(rep, '지출계')[:2], [30000, 42000])
        self.assertEqual(self.footer(rep, '잔액')[:2], [2070000, 2028000])
        self.assertTrue(any(r.label == '(미분류 99)' for r in rep.rows))
        # 결산일 5일: 2월 = 2/5~3/4 → 환불(+5000)·미분류(7000)만
        rep5 = RP.monthly(self.con, self.lid, 2026, 2, settle_day=5)
        self.assertEqual(self.cat(rep5, '11')[1], -5000)
        self.assertEqual(self.footer(rep5, '전월 이월금')[1], 2030000)

    def test_balance_identity(self):
        for y, m in [(2026, 1), (2026, 2), (2026, 3)]:
            rep = RP.monthly(self.con, self.lid, y, m)
            c, i, e, b = (self.footer(rep, k)[1] for k in ('전월 이월금', '수입계', '지출계', '잔액'))
            self.assertEqual(b, c + i - e)
            end = util.settle_period(y, m)[1]
            self.assertEqual(b, L.current_balance(self.con, self.lid, end))

    def test_yearly_daily_custom(self):
        y = RP.yearly(self.con, self.lid, 2026)
        self.assertEqual(self.footer(y, '전기 이월')[0], 100000)
        self.assertEqual(self.footer(y, '잔액')[11], L.current_balance(self.con, self.lid))
        self.assertEqual(self.cat(y, '11')[12], 65000)
        d = RP.daily(self.con, self.lid, 2026, 2)
        self.assertEqual(len(d.columns), 29)
        self.assertEqual(self.footer(d, '잔액')[-1], L.current_balance(self.con, self.lid))
        c = RP.custom(self.con, self.lid, D(2026, 1, 1), D(2026, 1, 31))
        self.assertEqual(self.footer(c, '수입계 - 지출계')[0], 1970000)

    def test_budget(self):
        RP.set_budget(self.con, self.lid, '2026-03', '11', 50000)
        RP.set_budget(self.con, self.lid, '2026-03', '00', 2000000)
        b = RP.budget_year(self.con, self.lid, 2026)
        self.assertEqual(self.footer(b, '수입계')[2], 2000000)
        self.assertEqual(self.footer(b, '지출계')[2], 50000)
        RP.set_budget(self.con, self.lid, '2026-03', '11', 0)
        self.assertNotIn('11', RP.budgets(self.con, self.lid, '2026-03'))
        m = RP.monthly(self.con, self.lid, 2026, 2)
        self.assertEqual(self.footer(m, '수입계')[4], 2000000)   # 다음달 예산 열

    def test_graph(self):
        labels, s = RP.graph_series(self.con, self.lid, 2026)
        self.assertEqual(len(labels), 12)
        self.assertEqual(s['(1) 공과금'][:2], [30000, 35000])
        labels, s = RP.graph_series(self.con, self.lid, 2026, group='1')
        self.assertIn('(11) 전기세', s)
        labels, s = RP.graph_series(self.con, self.lid, 2026, month=2)
        self.assertEqual(len(labels), 28)


class TestRecurring(Base):
    def test_occurrences_month_end(self):
        r = {'day': 31, 'start': '2026-01-01', 'end': '2026-04-30'}
        self.assertEqual(R.occurrences(r, D(2026, 1, 1), D(2026, 12, 31)),
                         [D(2026, 1, 31), D(2026, 2, 28), D(2026, 3, 31), D(2026, 4, 30)])

    def test_pending_apply_no_dupes(self):
        rid = R.save_rule(self.con, self.lid, {'item': '월세', 'expense': 500000, 'code': '50', 'day': 25,
                                               'start': '2026-01-01'})
        due, later = R.pending(self.con, self.lid, today=D(2026, 3, 10))
        self.assertEqual([x['date'] for x in due], [D(2026, 1, 25), D(2026, 2, 25)])
        self.assertEqual([x['date'] for x in later], [D(2026, 3, 25)])
        R.apply(self.con, self.lid, due[1:])                 # 2월만 입력, 1월은 남겨 둠
        due2, _ = R.pending(self.con, self.lid, today=D(2026, 3, 10))
        self.assertEqual([x['date'] for x in due2], [D(2026, 1, 25)])
        R.apply(self.con, self.lid, due2)
        self.assertEqual(L.current_balance(self.con, self.lid), -1000000)
        due, _ = R.pending(self.con, self.lid, today=D(2026, 3, 10))
        self.assertEqual(due, [])
        due, _ = R.pending(self.con, self.lid, today=D(2026, 3, 25))
        R.apply(self.con, self.lid, due, skip=True)              # 건너뛰기: 기록만
        self.assertEqual(L.current_balance(self.con, self.lid), -1000000)
        self.assertEqual(len(R.log(self.con, rid=rid)), 3)


class TestAssets(Base):
    def test_bank_and_summary(self):
        b = A.save_account(self.con, 'bank', {'name': '월급통장', 'company': '은행', 'opening': 1000, 'active': 1,
                                              'x.password': '0000'})
        A.add_tx(self.con, b, {'date': '2026-01-02', 'summary': '입금', 'deposit': 5000})
        t = A.add_tx(self.con, b, {'date': '2026-01-03', 'summary': '마트', 'withdraw': 2000},
                     ledger_id=self.lid, code='30')
        self.assertEqual(A.account_balance(self.con, b), 4000)
        self.assertEqual(L.current_balance(self.con, self.lid), -2000)       # 장부 동시저장
        A.delete_tx(self.con, t, with_entry=True)
        self.assertEqual(L.current_balance(self.con, self.lid), 0)
        self.assertEqual(A.merge_extra(self.con.execute('SELECT * FROM account WHERE id=?', (b,)).fetchone())
                         ['x.password'], '0000')
        A.save_account(self.con, 'property', {'name': '집', 'valuation': 300000000, 'loan': 100000000, 'x.ptype': 0})
        A.save_account(self.con, 'property', {'name': '차', 'valuation': 10000000, 'x.ptype': A.OTHER_ASSET})
        A.save_account(self.con, 'securities', {'name': '주식', 'valuation': 2000000})
        A.save_account(self.con, 'insurance', {'name': '실손'})
        A.save_account(self.con, 'bank', {'name': '안쓰는통장', 'opening': 999, 'active': 0})
        s = A.summary(self.con)
        self.assertEqual((s['예금'], s['증권'], s['부동산'], s['기타'], s['대출']),
                         (6000, 2000000, 300000000, 10000000, 100000000))
        self.assertEqual(s['순자산'], 6000 + 2000000 + 300000000 + 10000000 - 100000000)

    def test_card_billing_installments_pay(self):
        bank = A.save_account(self.con, 'bank', {'name': '결제통장', 'opening': 1000000})
        cid = A.save_card(self.con, {'name': '카드', 'pay_day': 14, 'bill_from_month': -1, 'bill_from_day': 1,
                                     'bill_to_month': -1, 'bill_to_day': 31, 'bank_account_id': bank})
        card = self.con.execute('SELECT * FROM card WHERE id=?', (cid,)).fetchone()
        self.assertEqual(A.pay_date_for(card, '2026-01-20'), D(2026, 2, 14))   # 전월 1~말일 사용분 → 다음달 14일
        self.assertEqual(A.pay_date_for(card, '2026-02-28'), D(2026, 3, 14))
        A.add_card_purchase(self.con, cid, '2026-01-20', '노트북', 100000, months=3)
        rows = A.card_txs(self.con, cid)
        self.assertEqual([(r['pay_date'], r['amount']) for r in rows],
                         [('2026-02-14', 33334), ('2026-03-14', 33333), ('2026-04-14', 33333)])
        self.assertEqual(A.card_unpaid_total(self.con), 100000)
        feb = A.card_txs(self.con, cid, ym='2026-02', paid=0)
        paid = A.pay_card(self.con, [r['id'] for r in feb], '2026-02-14', bank_account_id=bank,
                          ledger_id=self.lid, code='50')
        self.assertEqual(paid, 33334)
        self.assertEqual(A.account_balance(self.con, bank), 1000000 - 33334)
        self.assertEqual(L.current_balance(self.con, self.lid), -33334)
        self.assertEqual(A.card_unpaid_total(self.con), 66666)
        self.assertEqual(A.pay_card(self.con, [r['id'] for r in feb], '2026-02-14'), 0)   # 중복 결제 안 됨

    def test_card_window_this_month(self):
        cid = A.save_card(self.con, {'name': '당월카드', 'pay_day': 25, 'bill_from_month': -1, 'bill_from_day': 15,
                                     'bill_to_month': 0, 'bill_to_day': 14})
        card = self.con.execute('SELECT * FROM card WHERE id=?', (cid,)).fetchone()
        self.assertEqual(A.pay_date_for(card, '2026-03-10'), D(2026, 3, 25))
        self.assertEqual(A.pay_date_for(card, '2026-03-20'), D(2026, 4, 25))


class TestCalendar(Base):
    def test_lunar(self):
        self.assertEqual(lunar_to_solar(2026, 8, 15), D(2026, 9, 25))     # 2026 추석
        self.assertEqual(lunar_to_solar(2026, 1, 1), D(2026, 2, 17))      # 2026 설날
        self.assertEqual(lunar_to_solar(2025, 12, 31), D(2026, 2, 16))    # 말일 지정 → 설 전날
        self.assertEqual(solar_to_lunar(D(2026, 9, 25))[:3], (2026, 8, 15))

    def test_anniversaries(self):
        a = C.anniversaries_between(self.con, D(2026, 2, 1), D(2026, 2, 28))
        self.assertIn(('설날', True), a[D(2026, 2, 17)])
        self.assertIn(('설날 연휴', True), a[D(2026, 2, 16)])
        a = C.anniversaries_between(self.con, D(2026, 9, 1), D(2026, 10, 31))
        self.assertIn(('추석', True), a[D(2026, 9, 25)])
        self.assertIn(('한글날', True), a[D(2026, 10, 9)])
        C.save_anniversary(self.con, {'title': '결혼기념일', 'month': 2, 'day': 30, 'year': None})
        a = C.anniversaries_between(self.con, D(2026, 2, 1), D(2026, 2, 28))
        self.assertIn(('결혼기념일', False), a[D(2026, 2, 28)])

    def test_repeat(self):
        e = C.expand_repeat
        self.assertEqual(len(e('2026-01-01', '2026-01-31', {'type': 'every', 'n': 1, 'unit': '주'})), 5)
        self.assertEqual(e('2026-01-31', '2026-05-31', {'type': 'every', 'n': 1, 'unit': '월'}),
                         [D(2026, 1, 31), D(2026, 3, 31), D(2026, 5, 31)])
        self.assertEqual(len(e('2026-01-05', '2026-01-11', {'type': 'weekdays', 'set': '월 ~ 금'})), 5)
        self.assertEqual(e('2026-01-01', '2026-03-31', {'type': 'nth', 'nth': 1, 'weekday': 1, 'n': 1}),
                         [D(2026, 1, 13), D(2026, 2, 10), D(2026, 3, 10)])     # 둘째 화요일
        self.assertEqual(e('2026-01-01', '2026-02-28', {'type': 'nth', 'nth': 4, 'weekday': 4, 'n': 1}),
                         [D(2026, 1, 30), D(2026, 2, 27)])                     # 마지막 금요일
        self.assertEqual(e('2026-01-01', None, {'type': 'none'}), [D(2026, 1, 1)])

    def test_schedule_and_reminder(self):
        n = C.add_schedule(self.con, '2026-03-02', '회의', remind_days=1,
                           repeat={'type': 'every', 'n': 1, 'unit': '주'}, until='2026-03-31')
        self.assertEqual(n, 5)
        self.assertEqual([r['date'] for r in C.reminders(self.con, D(2026, 3, 1))], ['2026-03-02'])
        self.assertEqual(C.delete_schedule_range(self.con, '2026-03-10', '2026-03-31'), 3)
        self.assertEqual(len(C.month_grid(2026, 3)), 6)
        self.assertEqual(C.month_grid(2026, 3)[0][0], D(2026, 3, 1))             # 2026-03-01 은 일요일


class TestBackupCsv(Base):
    def test_backup_restore(self):
        self.add('2026-01-01', 'x', exp=1)
        path = B.backup(self.con, self.tmp)
        self.assertTrue(B.validate_db(path))
        bad = os.path.join(self.tmp, 'bad.sqlite3')
        open(bad, 'w').write('not a db')
        self.assertFalse(B.validate_db(bad))

    def test_csv(self):
        p = os.path.join(self.tmp, 'a.csv')
        open(p, 'w', encoding='cp949').write('날짜,품목,수입,지출,계정코드\n2026.01.02,커피,,"4,500",30\n'
                                              '2026-01-03,,0,100,30\nxx,a,1,0,00\n2026-01-04,b,1,0,ZZ\n')
        rows, errs = B.read_entries_csv(p, set(L.category_map(self.con, self.lid)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['expense'], 4500)
        self.assertEqual([n for n, _ in errs], [3, 4, 5])



class TestReviewRegressions(Base):
    """독립 검토에서 찾은 문제들이 다시 생기지 않는지."""
    def test_recurring_edit_does_not_repropose(self):
        rid = R.save_rule(self.con, self.lid, {'item': '월세', 'expense': 500000, 'code': '50', 'day': 25,
                                               'start': '2026-01-01'})
        due, _ = R.pending(self.con, self.lid, today=D(2026, 9, 30))
        R.apply(self.con, self.lid, due)                                   # 1~9월 9건
        r = self.con.execute('SELECT * FROM recurring WHERE id=?', (rid,)).fetchone()
        R.save_rule(self.con, self.lid, {**dict(r), 'day': 10}, rid)       # 25일 → 10일
        due, _ = R.pending(self.con, self.lid, today=D(2026, 9, 30))
        self.assertEqual(due, [])
        due, later = R.pending(self.con, self.lid, today=D(2026, 10, 5))
        self.assertEqual([x['date'] for x in later], [D(2026, 10, 10)])
        self.assertEqual(L.current_balance(self.con, self.lid), -4500000)

    def test_ledger_copy_does_not_repropose(self):
        R.save_rule(self.con, self.lid, {'item': '월세', 'expense': 1, 'code': '50', 'day': 1, 'start': '2026-01-01'})
        R.apply(self.con, self.lid, R.pending(self.con, self.lid, today=D(2026, 10, 15))[0])
        c = L.add_ledger(self.con, '복사본', copy_from=self.lid)
        self.assertEqual(L.current_balance(self.con, c), -10)
        self.assertEqual(R.pending(self.con, c, today=D(2026, 10, 15))[0], [])
        self.assertEqual([x['date'] for x in R.pending(self.con, c, today=D(2026, 11, 2))[0]], [D(2026, 11, 1)])

    def test_replace_db_same_path_and_wal(self):
        cur = os.path.join(self.tmp, 't.sqlite3')
        with self.assertRaises(ValueError):
            B.prepare_replacement(cur, cur)
        self.assertTrue(os.path.exists(cur))
        # 내용이 아직 -wal 에만 있는 백업 파일로 복원해도 내역이 살아 있어야 함
        src_path = os.path.join(self.tmp, 'walonly.sqlite3')
        other = db.connect(src_path)
        other.execute('PRAGMA wal_autocheckpoint=0')
        L.add_entry(other, L.first_ledger_id(other), {'date': '2026-01-01', 'item': 'WAL에만', 'expense': 7, 'code': '30'})
        self.assertTrue(os.path.getsize(src_path + '-wal') > 0)
        snap = os.path.join(self.tmp, 'snap')
        os.makedirs(snap)
        import shutil
        for ext in ('', '-wal', '-shm'):
            shutil.copyfile(src_path + ext, os.path.join(snap, 'b.sqlite3' + ext))
        other.close()
        self.con.close()
        kept = B.replace_db(cur, os.path.join(snap, 'b.sqlite3'), os.path.join(self.tmp, 'keep'))
        self.assertTrue(kept and os.path.exists(kept))
        c2 = db.connect(cur)
        self.assertEqual(c2.execute("SELECT COUNT(*) FROM entry WHERE item='WAL에만'").fetchone()[0], 1)
        c2.close()
        bad = os.path.join(self.tmp, 'bad.sqlite3')
        with open(bad, 'w') as f:
            f.write('x' * 100)
        with self.assertRaises(Exception):
            B.replace_db(cur, bad, os.path.join(self.tmp, 'keep'))
        c3 = db.connect(cur)                                               # 실패해도 현재 DB 는 그대로
        self.assertEqual(c3.execute("SELECT COUNT(*) FROM entry WHERE item='WAL에만'").fetchone()[0], 1)
        c3.close()
        self.con = db.connect(cur)

    def test_card_group_delete_scoped_and_unpay_cleans_up(self):
        bank = A.save_account(self.con, 'bank', {'name': '통장', 'opening': 1000000})
        a = A.save_card(self.con, {'name': 'A', 'pay_day': 14})
        b = A.save_card(self.con, {'name': 'B', 'pay_day': 14})
        for cid in (a, b):          # 원본처럼 할부번호가 카드끼리 겹치는 경우
            self.con.execute("INSERT INTO card_tx(card_id,group_id,date,summary,amount,pay_date) "
                             "VALUES(?,1,'2026-01-05','x',100,'2026-02-14')", (cid,))
        self.con.commit()
        A.delete_card_group(self.con, a, 1)
        self.assertEqual(len(A.card_txs(self.con, b)), 1)
        A.add_card_purchase(self.con, b, '2026-01-20', '노트북', 200000, months=2)
        ids = [r['id'] for r in A.card_txs(self.con, b, '2026-02', 0)]
        A.pay_card(self.con, ids, '2026-02-14', bank, self.lid, '50')
        self.assertEqual(A.unpay_card(self.con, ids[:1]), len(ids))      # 같은 결제는 함께 취소
        A.pay_card(self.con, ids, '2026-02-14', bank, self.lid, '50')
        paid_total = sum(r['amount'] for r in A.card_txs(self.con, b, '2026-02'))
        self.assertEqual(A.account_balance(self.con, bank), 1000000 - paid_total)   # 두 번 빠지지 않음
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM entry WHERE origin='card_pay'").fetchone()[0], 1)

    def test_money_rejects_garbage(self):
        for bad in ('inf', 'nan', '1e30', '1' * 20, '1,2,3x'):
            with self.assertRaises(ValueError):
                util.parse_money(bad)
        self.assertEqual(util.parse_money('2.5'), 3)
        self.assertEqual(util.parse_money('-1,500원'), -1500)


class TestBenchmark170(Base):
    """1.7.0 기능: 계산기·문자·자주 쓰는 내역·태그·예산 알림·리포트·무지출·이체·목표·빌린 돈·사진"""

    def test_calc_money(self):
        for t, v in [('12000+3500', 15500), ('45,000/3', 15000), ('(1200+800)*2', 4000), ('3×4', 12), ('12÷5', 2),
                     ('7/2', 4), ('-5/2', -3), ('1,000', 1000), ('', 0), ('10000-2500*2', 5000)]:
            self.assertEqual(util.calc_money(t), v, t)
        for t in ('10/0', '2*(3', '1+', 'abc'):
            with self.assertRaises(ValueError):
                util.calc_money(t)

    def test_sms(self):
        txt = ('[Web발신]\n신한카드(1234)승인\n홍*동님\n12,500원 일시불\n10/19 08:41\n스타벅스\n누적 345,600원\n\n'
               '[Web발신]\n롯데카드 승인취소 홍*동 12,500원 10/19 09:10 스타벅스\n\n'
               '[Web발신]\n삼성카드 홍*동 120,000원 03개월 10/17 18:20 이마트 누적1,000,000원')
        r = SMS.parse(txt, D(2026, 10, 20))
        self.assertEqual([(x['date'], x['amount'], x['kind'], x['item']) for x in r],
                         [('2026-10-19', 12500, 'out', '스타벅스'), ('2026-10-19', 12500, 'cancel', '스타벅스'),
                          ('2026-10-17', 120000, 'out', '이마트')])
        self.assertEqual(r[2]['months'], 3)
        e = SMS.to_entry(r[1])
        self.assertEqual((e['expense'], e['item']), (-12500, '스타벅스 (취소)'))
        # 연초에 작년 12월 문자
        self.assertEqual(SMS.parse('KB국민카드 9,900원 12/30 23:59 넷플릭스', D(2027, 1, 2))[0]['date'], '2026-12-30')
        self.assertFalse(SMS.parse('안녕하세요', D(2026, 10, 20))[0]['ok'])

    def test_favorites_and_tags(self):
        a = L.save_favorite(self.con, self.lid, {'item': '지하철', 'expense': 1500, 'code': '40'})
        b = L.save_favorite(self.con, self.lid, {'item': '점심', 'expense': 9000, 'code': '31'})
        L.move_favorite(self.con, self.lid, b, -1)
        self.assertEqual([f['id'] for f in L.favorites(self.con, self.lid)], [b, a])
        L.delete_favorite(self.con, a)
        self.assertEqual(len(L.favorites(self.con, self.lid)), 1)
        self.assertEqual(L.tags_of('#여행 부산 #맛집, #여행'), ['여행', '맛집'])
        L.add_entry(self.con, self.lid, {'date': '2026-10-01', 'item': '기차 #여행', 'expense': 50000, 'code': '40'})
        L.add_entry(self.con, self.lid, {'date': '2026-10-02', 'item': '숙소', 'expense': 80000, 'code': '80', 'memo': '#여행 #부산'})
        t = {r['tag']: (r['count'], r['expense']) for r in L.tag_summary(self.con, self.lid)}
        self.assertEqual(t, {'여행': (2, 130000), '부산': (1, 80000)})
        self.assertEqual(len(L.entries_with_tag(self.con, self.lid, '부산')), 1)

    def test_budget_alert_and_insight(self):
        RP.set_budget(self.con, self.lid, '2026-10', '30', 100000)
        self.add('2026-10-02', '장보기', exp=70000)
        before = INS.code_spent(self.con, self.lid, '30', D(2026, 10, 5))
        self.add('2026-10-05', '장보기', exp=15000)
        self.assertIn('85%', INS.budget_alert(self.con, self.lid, '30', D(2026, 10, 5), before))
        before = INS.code_spent(self.con, self.lid, '30', D(2026, 10, 6))
        self.add('2026-10-06', '장보기', exp=20000)
        self.assertIn('넘었어요', INS.budget_alert(self.con, self.lid, '30', D(2026, 10, 6), before))
        before = INS.code_spent(self.con, self.lid, '30', D(2026, 10, 7))
        self.add('2026-10-07', '장보기', exp=1000)
        self.assertIsNone(INS.budget_alert(self.con, self.lid, '30', D(2026, 10, 7), before))   # 이미 넘은 뒤엔 다시 안 알림
        p = INS.budget_progress(self.con, self.lid, 2026, 10, 1, D(2026, 10, 7))
        self.assertEqual((p['spent'], p['pct'], p['days_left']), (106000, 106, 25))
        self.add('2026-09-03', '장보기', exp=50000)
        i = INS.month_insight(self.con, self.lid, 2026, 10, 1, D(2026, 10, 10))
        self.assertEqual((i['days'], i['expense'], i['prev_same'], i['no_spend'], i['streak']), (10, 106000, 50000, 6, 3))
        self.assertEqual(i['change_pct'], 112)
        self.assertEqual(INS.no_spend_streak(self.con, self.lid, D(2026, 10, 7)), 0)

    def test_transfer(self):
        a = A.save_account(self.con, 'bank', {'name': '월급', 'opening': 100000})
        b = A.save_account(self.con, 'bank', {'name': '비상금', 'opening': 0})
        x, y = A.transfer(self.con, a, b, D(2026, 10, 1), 30000)
        self.assertEqual((A.account_balance(self.con, a), A.account_balance(self.con, b)), (70000, 30000))
        A.update_tx(self.con, x, {'date': D(2026, 10, 2), 'summary': '이체', 'deposit': 0, 'withdraw': 40000, 'memo': ''})
        self.assertEqual((A.account_balance(self.con, a), A.account_balance(self.con, b)), (60000, 40000))
        A.delete_tx(self.con, y)
        self.assertEqual((A.account_balance(self.con, a), A.account_balance(self.con, b)), (100000, 0))
        with self.assertRaises(ValueError):
            A.transfer(self.con, a, a, D(2026, 10, 1), 1)

    def test_goals_and_debts(self):
        g = G.save_goal(self.con, {'name': '여행', 'target': 1000000, 'due': D(2026, 12, 31)})
        G.add_goal_tx(self.con, g, D(2026, 10, 1), 400000)
        st = G.goal_status(self.con, G.goals(self.con)[0], D(2026, 10, 20))
        self.assertEqual((st['saved'], st['left'], st['pct'], st['per_month']), (400000, 600000, 40, 200000))
        d = G.save_debt(self.con, {'kind': 'lend', 'person': '철수', 'amount': 50000})
        G.save_debt(self.con, {'kind': 'borrow', 'person': '영희', 'amount': 20000})
        G.add_payment(self.con, d, D(2026, 10, 5), 50000)
        self.assertEqual(G.debt_totals(self.con), (0, 20000))
        self.assertEqual(G.debts(self.con, include_done=False)[0]['person'], '영희')
        pid = G.payments(self.con, d)[0]['id']
        G.delete_payment(self.con, pid)
        self.assertEqual(G.debt_totals(self.con), (50000, 20000))
        s = A.summary(self.con)
        self.assertEqual((s['받을돈'], s['갚을돈']), (50000, 20000))

    def test_attachment_cascade(self):
        e = self.add('2026-10-01', '영수증', exp=1000)
        AT.add(self.con, e, b'\xff\xd8\xff', 'a.jpg')
        self.assertEqual(AT.counts(self.con, [e]), {e: 1})
        L.delete_entries(self.con, [e])
        self.assertEqual(AT.total_size(self.con), 0)


@unittest.skipUnless(os.environ.get('GAGYEBU_TEST_MDB_DIR') and I.have_mdbtools(), '원본 mdb 폴더 필요')
class TestImporter(unittest.TestCase):
    def test_import_installer_defaults(self):
        tmp = tempfile.mkdtemp()
        dest = os.path.join(tmp, 'imp.sqlite3')
        rep = I.import_folder(os.environ['GAGYEBU_TEST_MDB_DIR'], dest)
        con = sqlite3.connect(dest)
        con.row_factory = sqlite3.Row
        led = con.execute('SELECT * FROM ledger').fetchall()
        self.assertEqual([r['name'] for r in led], ['가계부 장부'])
        lid = led[0]['id']
        self.assertEqual(con.execute('SELECT COUNT(*) FROM entry WHERE ledger_id=?', (lid,)).fetchone()[0], 10)
        self.assertEqual(con.execute('SELECT SUM(income), SUM(expense) FROM entry').fetchone()[:], (1000000, 193300))
        self.assertEqual(con.execute('SELECT COUNT(*) FROM category').fetchone()[0], 11)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM cat_group').fetchone()[0], 8)
        self.assertEqual(con.execute('SELECT COUNT(*) FROM anniversary').fetchone()[0], 42)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM anniversary WHERE lunar=1").fetchone()[0] > 0, True)
        self.assertTrue(util.check_password('1111', db.get_meta(con, 'password')))
        self.assertEqual(con.execute('SELECT COUNT(*) FROM schedule').fetchone()[0], 0)     # 'mainorder' 제외
        raw = dict(con.execute('SELECT tbl, COUNT(*) FROM legacy_raw GROUP BY tbl').fetchall())
        self.assertEqual(raw.get('내역'), 10)          # 새 구조로 옮긴 표도 빠진 칸 없이 원본 그대로 보관
        self.assertEqual(raw.get('memday'), 42)
        print('\n' + rep.text())


if __name__ == '__main__':
    unittest.main()
