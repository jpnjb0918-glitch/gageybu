"""윈도우 '우리집 가계부' data 폴더(*.mdb, Access97/Jet3, CP949) → 새 SQLite DB.

mdbtools(mdb-tables, mdb-export)로 읽기만 하며 원본 파일은 바꾸지 않는다.
의미를 확정한 표는 새 구조로 옮기고, 나머지 자료가 있는 표는 legacy_raw 에 그대로 보관한다.
"""
import csv
import io
import json
import os
import shutil
import subprocess

from .. import db
from ..util import hash_password, parse_money

ENV = dict(os.environ, MDB_JET3_CHARSET='cp949', LC_ALL='C.UTF-8')
DT_FMT = '%Y-%m-%d %H:%M:%S'
IS_WIN = os.name == 'nt'

# 의미를 해석해 옮기는 표 (그 외 자료가 있는 표는 원본 그대로 보관)
MAPPED = {
    'main': {'장부명', '가계부환경', '일정관리', 'memday', 'address', '주소록', 'ilgit', 'diary', 'memot',
             'dbversion', '우편번호'},
    'home': {'계정분류', '계정과목', '내역', '예산', 'myautoin', 'myautode', 'dbversion'},
    'asset': {'통장정보', '통장거래', '카드정보', '카드거래', '증권정보', '증권거래', '보험정보', '보험거래',
              '부동산정보', '부동산거래', '인명그룹', '인명정보', '임시거래1', '임시거래2', '임시거래3', '임시거래4',
              '임시거래5'},
}


class MdbError(RuntimeError):
    pass


def _tool(name):
    """mdbtools 실행 파일. 윈도우판은 함께 설치된 tools\\mdbtools\\ (또는 GAGYEBU_MDBTOOLS), 리눅스는 PATH."""
    exe = name + ('.exe' if IS_WIN else '')
    root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
    for d in (os.environ.get('GAGYEBU_MDBTOOLS'), os.path.join(root, 'tools', 'mdbtools')):
        if d and os.path.isfile(os.path.join(d, exe)):
            return os.path.join(d, exe)
    return shutil.which(name)


def have_mdbtools():
    return bool(_tool('mdb-export') and _tool('mdb-tables'))


# 윈도우: 명령줄로는 한글 경로·표 이름이 깨질 수 있으므로
#   ① 원본을 임시 폴더에 영문 이름(f1.mdb …)으로 복사해 그 폴더에서 실행하고
#   ② 표는 이름 대신 순번("#3")으로 지정한다 (함께 넣은 mdb-export.exe 에 추가한 기능)
_staged = {}
_tables = {}
_stage_dir = None


def _stage(path):
    global _stage_dir
    if not IS_WIN:
        return None, path
    key = os.path.abspath(path)
    if key not in _staged:
        if _stage_dir is None:
            import atexit
            import tempfile
            _stage_dir = tempfile.mkdtemp(prefix='gagyebu-mdb-')
            atexit.register(shutil.rmtree, _stage_dir, True)
        name = f'f{len(_staged) + 1}.mdb'
        shutil.copyfile(path, os.path.join(_stage_dir, name))
        _staged[key] = name
    return _stage_dir, _staged[key]


def _run(args, cwd=None):
    kw = {'creationflags': 0x08000000} if IS_WIN else {}          # CREATE_NO_WINDOW: 검은 창이 번쩍이지 않게
    r = subprocess.run(args, env=ENV, capture_output=True, cwd=cwd, **kw)
    if r.returncode != 0:
        raise MdbError(r.stderr.decode('utf-8', 'replace').strip() or ' '.join(args))
    return r.stdout.decode('utf-8', 'replace')


def read_tables(path):
    cwd, arg = _stage(path)
    names = [t.strip('\r') for t in _run([_tool('mdb-tables'), '-1', arg], cwd).splitlines() if t.strip()]
    _tables[os.path.abspath(path)] = names
    return names


def read_table(path, table):
    cwd, arg = _stage(path)
    which = table
    if IS_WIN:
        names = _tables.get(os.path.abspath(path)) or read_tables(path)
        which = f'#{names.index(table)}'
    text = _run([_tool('mdb-export'), '-T', DT_FMT, '-b', 'strip', arg, which], cwd)
    rows = list(csv.DictReader(io.StringIO(text)))
    return [{k: (v if v != '' else None) for k, v in r.items()} for r in rows]


def find_file(folder, name):
    """윈도우 파일은 대소문자 구분이 없으므로 대소문자 무시하고 찾기."""
    for f in os.listdir(folder):
        if f.lower() == name.lower():
            return os.path.join(folder, f)
    return None


def _d(v):
    return v[:10] if v else None


def _i(v, default=0):
    try:
        return int(float(v)) if v not in (None, '') else default
    except ValueError:
        return default


def _m(v):
    try:
        return parse_money(v)
    except ValueError:
        return 0


def _s(v):
    return (v or '').strip()


class Report:
    def __init__(self):
        self.lines, self.warnings, self.counts = [], [], {}

    def add(self, key, n):
        self.counts[key] = self.counts.get(key, 0) + n

    def text(self):
        out = ['[가져온 자료]'] + [f'  {k}: {v:,}건' for k, v in self.counts.items() if v]
        if self.lines:
            out += ['', '[참고]'] + ['  ' + s for s in self.lines]
        if self.warnings:
            out += ['', '[확인 필요]'] + ['  ' + s for s in self.warnings]
        return '\n'.join(out)


def _keep_raw(con, rep, source, table, rows, note=True):
    con.executemany('INSERT INTO legacy_raw(source,tbl,data) VALUES(?,?,?)',
                    [(source, table, json.dumps(r, ensure_ascii=False)) for r in rows])
    if note:
        rep.lines.append(f'{source}의 [{table}] {len(rows)}행은 원본 그대로 보관함 (화면에는 안 나옴)')


def _keep_all(con, rep, source, data, mapped):
    """원본의 모든 표를 원본 그대로 보관 (새 구조로 옮기며 버린 칸이 있어도 나중에 되살릴 수 있게)."""
    n = rows = 0
    for t, rs in data.items():
        if rs:
            _keep_raw(con, rep, source, t, rs, note=t not in mapped)
            n += 1
            rows += len(rs)
    if n:
        rep.lines.append(f'{source}: 자료가 있는 원본 표 {n}개({rows:,}행)는 옮긴 것과 별도로 원본 그대로도 보관했습니다')


def _load(path):
    out = {}
    for t in read_tables(path):
        out[t] = read_table(path, t)
    return out


def import_ledger(con, rep, path, name, sort):
    data = _load(path)
    fn = os.path.basename(path)
    lid = con.execute('INSERT INTO ledger(name,sort,legacy_file) VALUES(?,?,?)', (name, sort, fn)).lastrowid
    groups = [(r['계정분류'], r['설명']) for r in data.get('계정분류', []) if r.get('계정분류') and r.get('설명')]
    if not any(g == '0' for g, _ in groups):
        groups.append(('0', '수입'))
    con.executemany('INSERT OR REPLACE INTO cat_group VALUES(?,?,?)', [(lid, g, n) for g, n in groups])
    cats = [(lid, r['계정코드'], r['계정과목'], _i(r.get('번호')))
            for r in data.get('계정과목', []) if r.get('계정코드') and r.get('계정과목')]
    con.executemany('INSERT OR REPLACE INTO category VALUES(?,?,?,?)', cats)
    n_entry = bad = 0
    for r in sorted(data.get('내역', []), key=lambda r: (r.get('날짜') or '', _i(r.get('번호')))):
        if not r.get('날짜'):
            bad += 1
            continue
        con.execute('INSERT INTO entry(ledger_id,date,item,income,expense,code,memo,origin) VALUES(?,?,?,?,?,?,?,?)',
                    (lid, _d(r['날짜']), _s(r.get('품목')), _m(r.get('수입')), _m(r.get('지출')),
                     _s(r.get('계정코드')), _s(r.get('메모')), 'import'))
        n_entry += 1
        if _s(r.get('품목')):
            con.execute('INSERT INTO item_word VALUES(?,?,1) ON CONFLICT(ledger_id,name) DO UPDATE SET count=count+1',
                        (lid, _s(r['품목'])))
    if bad:
        rep.warnings.append(f'[{name}] 날짜가 비어 있는 내역 {bad}건은 옮기지 않았습니다 (원본 보관 표에는 있음)')
    rep.add('가계부 내역', n_entry)
    n_b = 0
    for r in data.get('예산', []):
        if r.get('날짜') and r.get('계정코드'):
            amt = _m(r.get('수입')) + _m(r.get('지출'))
            con.execute('INSERT INTO budget VALUES(?,?,?,?) ON CONFLICT(ledger_id,ym,code) '
                        'DO UPDATE SET amount=amount+excluded.amount', (lid, r['날짜'][:7], r['계정코드'], amt))
            n_b += 1
    rep.add('예산', n_b)
    idmap = {}
    logs = {}
    for r in data.get('myautode', []):
        if r.get('입력일'):
            k = _i(r.get('자번'))
            logs[k] = max(logs.get(k, ''), _d(r['입력일']))
    import datetime as _dt
    prev_month_end = (_dt.date.today().replace(day=1) - _dt.timedelta(days=1)).isoformat()
    for r in data.get('myautoin', []):
        cont = _i(r.get('입력형태')) != 0 or not r.get('종료일')   # 추정: 입력형태 1(또는 VB 참=-1) = '계속 적용함'
        start = _d(r.get('시작일')) or _d(r.get('등록일')) or '2000-01-01'
        end = None if cont else _d(r.get('종료일'))
        memo = ' '.join(x for x in (_s(r.get('비고')), _s(r.get('메모'))) if x)
        # 원본에서 이미 처리한 기간은 다시 묻지 않음: 마지막 자동입력 기록 날짜까지, 기록이 없으면 지난달 말까지
        thr = logs.get(_i(r.get('번호'))) or prev_month_end
        rid = con.execute('INSERT INTO recurring(ledger_id,item,income,expense,code,day,start,end,memo,created,'
                          'applied_through) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                          (lid, _s(r.get('품목')), _m(r.get('수입')), _m(r.get('지출')), _s(r.get('계정코드')),
                           max(1, min(31, _i(r.get('자동입력일'), 1))), start, end, memo, _d(r.get('등록일')),
                           thr)).lastrowid
        idmap[_i(r.get('번호'))] = rid
        rep.lines.append(f"[{name}] 예약 '{_s(r.get('품목'))}' 매월 {_i(r.get('자동입력일'))}일, {start}부터 "
                         f"{'계속' if end is None else end + '까지'} (원본 입력형태={r.get('입력형태')}, 종료일={_d(r.get('종료일'))})")
    if data.get('myautoin'):
        rep.warnings.append('예약설정의 "계속 적용" 여부는 원본의 입력형태 값으로 추정했습니다 — 예약 화면에서 확인하세요')
        rep.lines.append('예약은 원본에서 마지막으로 자동입력한 날(기록이 없으면 지난달 말)까지 처리된 것으로 보고, '
                         '그 뒤 날짜만 입력할지 묻습니다')
    rep.add('예약설정', len(idmap))
    n_log = 0
    for r in data.get('myautode', []):
        if not r.get('입력일'):
            continue
        con.execute('INSERT INTO recurring_log(recurring_id,ledger_id,date,item,income,expense,code) VALUES(?,?,?,?,?,?,?)',
                    (idmap.get(_i(r.get('자번'))), lid, _d(r['입력일']), _s(r.get('품목')), _m(r.get('수입')),
                     _m(r.get('지출')), _s(r.get('계정코드'))))
        n_log += 1
    rep.add('예약 자동입력 기록', n_log)
    _keep_all(con, rep, fn, data, MAPPED['home'])
    return lid


def import_main(con, rep, path):
    data = _load(path)
    fn = os.path.basename(path)
    env = (data.get('가계부환경') or [{}])[0]
    if env.get('pwd'):
        db.set_meta(con, 'password', hash_password(env['pwd']))
        rep.lines.append('원본 프로그램의 시작 암호를 그대로 가져왔습니다 (같은 암호로 로그인'
                         + (', 원본에서 바꾼 적이 없다면 기본값 1111' if env['pwd'] == '1111' else '') + ')')
    n = 0
    for r in data.get('일정관리', []):
        text = _s(r.get('내용'))
        if not r.get('입력일자') or not text or text == 'mainorder':   # 'mainorder' 는 원본 내부 설정값
            continue
        con.execute('INSERT INTO schedule(date,text) VALUES(?,?)', (_d(r['입력일자']), text))
        n += 1
    rep.add('일정', n)
    an = data.get('memday', [])
    if an:
        con.execute('DELETE FROM anniversary')
        for i, r in enumerate(an):
            md = (r.get('날짜') or '').strip()
            if len(md) != 4 or not md.isdigit() or not r.get('제목'):
                continue
            yr = r.get('년도')
            con.execute('INSERT INTO anniversary(title,month,day,year,lunar,holiday,sort) VALUES(?,?,?,?,?,?,?)',
                        (_s(r['제목']), int(md[:2]), int(md[2:]), int(yr) if yr and yr.isdigit() else None,
                         1 if (r.get('양음') or '').startswith('음') else 0,
                         1 if (r.get('평휴') or '').startswith('휴') else 0, i))
        rep.add('기념일', len(an))
    n = 0
    for r in data.get('address', []):
        if not _s(r.get('성명')):
            continue
        con.execute('INSERT INTO contact(name,mobile,tel1,tel2,fax,email,homepage,address,zipcode,memo) '
                    'VALUES(?,?,?,?,?,?,?,?,?,?)', tuple(_s(r.get(k)) for k in
                                                         ('성명', '휴대폰', '전화1', '전화2', '팩스번호', '전자우편',
                                                          '홈페이지', '주소', '우편번호', '메모')))
        n += 1
    for r in data.get('주소록', []):   # 구버전 주소록 표
        if not _s(r.get('성명')):
            continue
        con.execute('INSERT INTO contact(name,mobile,tel1,tel2,email,address,zipcode,memo,grp) VALUES(?,?,?,?,?,?,?,?,?)',
                    tuple(_s(r.get(k)) for k in ('성명', '휴대폰', '전화1', '전화2', '전자우편', '주소', '우편번호',
                                                  '비고', '구분')))
        n += 1
    rep.add('주소록', n)
    n = 0
    for r in data.get('ilgit', []):
        if not r.get('날짜') or not (_s(r.get('제목')) or _s(r.get('내용'))):
            continue
        content = _s(r.get('내용'))
        if _s(r.get('비고')):
            content += f"\n\n(비고: {_s(r['비고'])})"
        con.execute('INSERT INTO diary(date,weather,title,content) VALUES(?,?,?,?)',
                    (_d(r['날짜']), _i(r.get('날씨')), _s(r.get('제목')), content))
        n += 1
    for r in data.get('diary', []):    # 구버전 일기 표
        if r.get('입력일자') and _s(r.get('내용')):
            con.execute('INSERT INTO diary(date,title,content) VALUES(?,?,?)', (_d(r['입력일자']), '', _s(r['내용'])))
            n += 1
    if n:
        rep.warnings.append('일기 날씨는 원본 번호(0=맑음, 1=구름 조금 …)로 추정해 옮겼습니다')
    rep.add('일기', n)
    n = 0
    for r in sorted(data.get('memot', []), key=lambda r: _i(r.get('번호'))):
        if not (_s(r.get('제목')) or _s(r.get('내용'))):
            continue
        created = _d(r.get('입력날짜'))
        if created and _s(r.get('입력시간')):
            created += ' ' + _s(r['입력시간'])
        con.execute('INSERT INTO memo(title,content,created,sort) VALUES(?,?,?,?)',
                    (_s(r.get('제목')), _s(r.get('내용')), created, _i(r.get('번호'))))
        n += 1
    rep.add('메모', n)
    _keep_all(con, rep, fn, data, MAPPED['main'])
    return data.get('장부명', [])


def _put_account(con, kind, sort, name, company='', owner='', number='', opening=0, valuation=0, loan=0, deposit=0,
                 active=1, extra=None, memo=''):
    return con.execute('INSERT INTO account(kind,sort,name,company,owner,number,opening,valuation,loan,deposit,active,'
                       'extra,memo) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (kind, sort, name or '(이름 없음)', company, owner, number, opening, valuation, loan, deposit,
                        active, json.dumps({k: v for k, v in (extra or {}).items() if v not in (None, '')},
                                           ensure_ascii=False), memo)).lastrowid


def _put_txs(con, rep, rows, fk, idmap, label):
    n = 0
    for r in rows:
        aid = idmap.get(_i(r.get(fk)))
        if not aid or not r.get('거래일자'):
            continue
        memo = _s(r.get('메모'))
        con.execute('INSERT INTO account_tx(account_id,date,summary,deposit,withdraw,memo) VALUES(?,?,?,?,?,?)',
                    (aid, _d(r['거래일자']), _s(r.get('적요')), _m(r.get('입금액')), _m(r.get('출금액')), memo))
        n += 1
    rep.add(label, n)


def import_asset(con, rep, path):
    data = _load(path)
    fn = os.path.basename(path)
    ids = {}
    for kind, info_t, tx_t, fk, label in [('bank', '통장정보', '통장거래', '통장번호', '통장 거래'),
                                          ('securities', '증권정보', '증권거래', '증권번호', '증권 거래'),
                                          ('insurance', '보험정보', '보험거래', '보험번호', '보험 거래'),
                                          ('property', '부동산정보', '부동산거래', '부동산번호', '부동산/기타 거래')]:
        idmap = {}
        for r in data.get(info_t, []):
            s = _i(r.get('번호'))
            if kind == 'bank':
                aid = _put_account(con, kind, s, _s(r.get('통장명')), _s(r.get('은행명')), _s(r.get('예금주')),
                                   _s(r.get('계좌번호')), opening=_m(r.get('초기잔액')),
                                   active=0 if _i(r.get('사용여부')) != 0 else 1,   # 0 = 사용중
                                   extra={'password': _s(r.get('비밀번호')), 'issued': _s(r.get('발행일')),
                                          'maturity': _s(r.get('만기일'))}, memo=_s(r.get('메모')))
            elif kind == 'securities':
                aid = _put_account(con, kind, s, _s(r.get('계좌이름')), _s(r.get('증권사')), _s(r.get('소유주')),
                                   _s(r.get('계좌번호')), valuation=_m(r.get('평가금액')), deposit=_m(r.get('추정예수금')),
                                   extra={'valued_on': _d(r.get('평가일'))}, memo=_s(r.get('비고')))
            elif kind == 'insurance':
                aid = _put_account(con, kind, s, _s(r.get('상품명')), _s(r.get('보험사명')), _s(r.get('계약자')),
                                   _s(r.get('증권번호')), memo=_s(r.get('비고')),
                                   extra={'insured': _s(r.get('피보험자')), 'contract_date': _d(r.get('계약일')),
                                          'maturity': _d(r.get('만기일')), 'status': _s(r.get('계약상태')),
                                          'class': _s(r.get('보험구분')), 'pay_method': _s(r.get('납입방법')),
                                          'type': _s(r.get('보험종류')), 'total_count': _i(r.get('만기납입횟수')),
                                          'paid_count': _i(r.get('납입횟수')), 'paid_total': _m(r.get('납입보험료누계')),
                                          'agent': _s(r.get('담당자'))})
            else:
                aid = _put_account(con, kind, s, _s(r.get('자산명')), owner=_s(r.get('소유주')),
                                   valuation=_m(r.get('평가금액')), loan=_m(r.get('대출금액')), memo=_s(r.get('비고')),
                                   extra={'ptype': _i(r.get('구분')), 'acquired': _d(r.get('취득일자')),
                                          'valued_on': _d(r.get('평가일자'))})
            idmap[_i(r.get('일련번호'))] = aid
        rep.add(f'{info_t[:-2]}', len(idmap))
        _put_txs(con, rep, data.get(tx_t, []), fk, idmap, label)
        ids[kind] = idmap
    cmap = {}
    acct_by_number = {r['number']: r['id'] for r in con.execute("SELECT id, number FROM account WHERE kind='bank'")}
    for r in data.get('카드정보', []):
        pay_day = max(1, min(31, _i(r.get('결제일'), 1)))
        # 결제기간1~4: 청구기간 (월 오프셋 목록 '전전월|전월|당월' 의 위치, 일) — 원본 화면 구성으로 추정
        fm, fd, tm, td = (_i(r.get(f'결제기간{k}'), None) for k in range(1, 5))
        bill = (fm - 2 if fm is not None and 0 <= fm <= 2 else -1, fd if fd and 1 <= fd <= 31 else 1,
                tm - 2 if tm is not None and 0 <= tm <= 2 else -1, td if td and 1 <= td <= 31 else 31)
        bank_id = acct_by_number.get(_s(r.get('계좌번호')))
        cid = con.execute('INSERT INTO card(sort,company,name,number,pay_day,bill_from_month,bill_from_day,bill_to_month,'
                          'bill_to_day,bank_account_id,extra,memo) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                          (_i(r.get('번호')), _s(r.get('카드사명')), _s(r.get('카드명')) or '(카드)', _s(r.get('카드번호')),
                           pay_day, *bill, bank_id,
                           json.dumps({'password': _s(r.get('카드비밀번호')),
                                       'valid_ym': f"{_i(r.get('유효년'))}-{_i(r.get('유효월')):02d}" if r.get('유효년') else '',
                                       'cyc': _s(r.get('cyc번호')), 'account_text': _s(r.get('계좌번호')),
                                       'limit': _m(r.get('카드사용한도')), 'cash_limit': _m(r.get('현금서비스')),
                                       'loan_limit': _m(r.get('대출한도')), 'issued': _d(r.get('발행일'))},
                                      ensure_ascii=False), _s(r.get('비고')))).lastrowid
        cmap[_i(r.get('일련번호'))] = cid
    rep.add('신용카드', len(cmap))
    if cmap:
        rep.warnings.append('카드 청구기간(결제기간1~4)은 원본 화면 구성을 보고 추정해 옮겼습니다 — 카드 정보에서 확인하세요')
    n = 0
    gid_map = {}
    next_gid = 1
    for r in data.get('카드거래', []):
        cid = cmap.get(_i(r.get('카드번호')))
        if not cid or not r.get('거래일자'):
            continue
        months = max(1, _i(r.get('할부개월'), 1))
        con.execute('INSERT INTO card_tx(card_id,group_id,date,summary,total,fee_total,months,seq,amount,fee,pay_date,paid,memo) '
                    'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (cid, None, _d(r['거래일자']), _s(r.get('적요')),
                     _m(r.get('총사용금액')) or _m(r.get('사용금액')), 0, months, max(1, _i(r.get('몇회차'), 1)),
                     _m(r.get('사용금액')), _m(r.get('수수료')), _d(r.get('결제일')) or _d(r['거래일자']),
                     1 if _i(r.get('결제여부')) != 0 else 0, _s(r.get('메모'))))   # 0 = 미결제
        # 할부 묶음 번호는 카드마다 새로 매김 (원본 번호가 카드끼리 겹쳐도 다른 카드 내역이 함께 지워지지 않게)
        key = (cid, _i(r.get('할부번호')) or f'단건{n}')
        if key not in gid_map:
            gid_map[key] = next_gid
            next_gid += 1
        con.execute('UPDATE card_tx SET group_id=? WHERE id=last_insert_rowid()', (gid_map[key],))
        n += 1
    rep.add('카드 거래', n)
    n = 0
    groups = {r.get('일련번호'): _s(r.get('그룹명')) for r in data.get('인명그룹', [])}
    for r in data.get('인명정보', []):
        if not _s(r.get('이름')):
            continue
        memo = '\n'.join(f'{k}: {_s(r.get(k))}' for k in ('회사학교명', '회사주소', '기타전화', '생일') if _s(r.get(k)))
        if _s(r.get('메모')):
            memo = (memo + '\n' + _s(r['메모'])).strip()
        con.execute('INSERT INTO contact(name,mobile,tel1,tel2,fax,email,homepage,address,memo,grp) VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (_s(r['이름']), _s(r.get('휴대전화')), _s(r.get('자택전화')), _s(r.get('회사전화')), _s(r.get('팩스번호')),
                     _s(r.get('전자우편')), _s(r.get('홈페이지')), _s(r.get('자택주소')), memo,
                     groups.get(r.get('그룹'), '')))
        n += 1
    rep.add('주소록(자산 쪽 인명정보)', n)
    if all(not v or v == 'null' for r in data.get('환경변수', []) for v in r.values()):
        data.pop('환경변수', None)          # 기본값('null')만 있는 설정 표는 의미 없음
    _keep_all(con, rep, fn, data, MAPPED['asset'])


def import_folder(folder, dest_path):
    """folder 의 원본 데이터를 dest_path(새 파일)로 가져와 Report 반환."""
    if not have_mdbtools():
        raise MdbError('mdbtools 가 없습니다: sudo apt install mdbtools')
    if os.path.exists(dest_path):
        os.remove(dest_path)
    rep = Report()
    con = db.connect(dest_path, seed=False)
    main = find_file(folder, 'main.mdb')
    books = []
    if main:
        books = import_main(con, rep, main)
    else:
        rep.warnings.append('main.mdb 가 없어 장부 목록·암호·일정·주소록·일기·메모는 가져오지 못했습니다')
    used = set()
    sort = 0
    for b in sorted(books, key=lambda r: _i(r.get('번호'))):
        fname = _s(b.get('파일명'))
        path = find_file(folder, f'home{fname}.mdb') if fname else None
        if not path:
            rep.warnings.append(f"장부 '{_s(b.get('장부명'))}' 의 파일 home{fname}.mdb 가 없습니다")
            continue
        sort += 1
        import_ledger(con, rep, path, _s(b.get('장부명')) or fname, sort)
        used.add(os.path.basename(path).lower())
    for f in sorted(os.listdir(folder)):         # 장부 목록에 없지만 내역이 있는 home*.mdb 도 가져오기
        lf = f.lower()
        if lf.startswith('home') and lf.endswith('.mdb') and lf not in used:
            p = os.path.join(folder, f)
            try:
                has = any(t == '내역' for t in read_tables(p)) and read_table(p, '내역')
            except MdbError:
                has = False
            if has:
                sort += 1
                import_ledger(con, rep, p, f'{f[:-4]} (목록에 없던 장부)', sort)
                rep.warnings.append(f'{f} 는 장부 목록에 없지만 내역이 있어 별도 장부로 가져왔습니다')
    asset = find_file(folder, 'asset.mdb')
    if asset:
        import_asset(con, rep, asset)
    if not con.execute('SELECT 1 FROM ledger').fetchone():
        db.seed_defaults(con, with_anniversaries=False)
        rep.warnings.append('가져올 장부가 없어 기본 장부를 만들었습니다')
    if not con.execute('SELECT 1 FROM anniversary').fetchone():
        db.seed_defaults(con, with_ledger=False)
    db.set_meta(con, 'imported_from', os.path.abspath(folder))
    con.commit()
    con.close()
    return rep
