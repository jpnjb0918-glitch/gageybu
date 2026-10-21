"""SQLite 저장소. 모든 금액은 원 단위 정수(INTEGER)."""
import json
import os
import sqlite3

SCHEMA_VERSION = 1

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);

-- 장부 / 계정
CREATE TABLE IF NOT EXISTS ledger(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, sort INTEGER NOT NULL DEFAULT 0,
    memo TEXT NOT NULL DEFAULT '', legacy_file TEXT);
CREATE TABLE IF NOT EXISTS cat_group(              -- 대분류 (0=수입, 1~9,a~z=지출)
    ledger_id INTEGER NOT NULL REFERENCES ledger(id) ON DELETE CASCADE,
    code TEXT NOT NULL, name TEXT NOT NULL, PRIMARY KEY(ledger_id, code));
CREATE TABLE IF NOT EXISTS category(               -- 소분류 = 계정코드 2자리
    ledger_id INTEGER NOT NULL REFERENCES ledger(id) ON DELETE CASCADE,
    code TEXT NOT NULL, name TEXT NOT NULL, sort INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(ledger_id, code));
CREATE TABLE IF NOT EXISTS entry(                  -- 수입/지출 내역
    id INTEGER PRIMARY KEY,
    ledger_id INTEGER NOT NULL REFERENCES ledger(id) ON DELETE CASCADE,
    date TEXT NOT NULL, item TEXT NOT NULL DEFAULT '',
    income INTEGER NOT NULL DEFAULT 0, expense INTEGER NOT NULL DEFAULT 0,
    code TEXT NOT NULL DEFAULT '', memo TEXT NOT NULL DEFAULT '', origin TEXT);
CREATE INDEX IF NOT EXISTS entry_ld ON entry(ledger_id, date, id);
CREATE TABLE IF NOT EXISTS budget(
    ledger_id INTEGER NOT NULL REFERENCES ledger(id) ON DELETE CASCADE,
    ym TEXT NOT NULL, code TEXT NOT NULL, amount INTEGER NOT NULL,
    PRIMARY KEY(ledger_id, ym, code));
CREATE TABLE IF NOT EXISTS item_word(              -- 품목 자동완성 (사용횟수)
    ledger_id INTEGER NOT NULL REFERENCES ledger(id) ON DELETE CASCADE,
    name TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(ledger_id, name));

-- 예약(고정 수입/지출 자동입력)
CREATE TABLE IF NOT EXISTS recurring(
    id INTEGER PRIMARY KEY,
    ledger_id INTEGER NOT NULL REFERENCES ledger(id) ON DELETE CASCADE,
    item TEXT NOT NULL DEFAULT '', income INTEGER NOT NULL DEFAULT 0, expense INTEGER NOT NULL DEFAULT 0,
    code TEXT NOT NULL DEFAULT '', day INTEGER NOT NULL, start TEXT NOT NULL, end TEXT,
    memo TEXT NOT NULL DEFAULT '', created TEXT,
    applied_through TEXT);   -- 이 날짜까지는 처리 끝 (수정·복사·가져오기 때 지난 날짜가 다시 나오지 않게)
CREATE TABLE IF NOT EXISTS recurring_log(
    id INTEGER PRIMARY KEY,
    recurring_id INTEGER REFERENCES recurring(id) ON DELETE SET NULL,
    ledger_id INTEGER NOT NULL REFERENCES ledger(id) ON DELETE CASCADE,
    date TEXT NOT NULL, item TEXT, income INTEGER, expense INTEGER, code TEXT,
    entry_id INTEGER, skipped INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS rlog_r ON recurring_log(recurring_id, date);

-- 자산: 통장(bank)·증권(securities)·보험(insurance)·부동산/기타(property)
CREATE TABLE IF NOT EXISTS account(
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('bank','securities','insurance','property')),
    sort INTEGER NOT NULL DEFAULT 0, name TEXT NOT NULL, company TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT '', number TEXT NOT NULL DEFAULT '',
    opening INTEGER NOT NULL DEFAULT 0,     -- 통장 초기잔액
    valuation INTEGER NOT NULL DEFAULT 0,   -- 증권·부동산 평가금액 (자산)
    loan INTEGER NOT NULL DEFAULT 0,        -- 부동산 대출금액 (부채)
    deposit INTEGER NOT NULL DEFAULT 0,     -- 증권 추정예수금
    active INTEGER NOT NULL DEFAULT 1,      -- 통장 사용여부 (1=사용중 → 자산 계산)
    extra TEXT NOT NULL DEFAULT '{}', memo TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS account_tx(
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES account(id) ON DELETE CASCADE,
    date TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
    deposit INTEGER NOT NULL DEFAULT 0, withdraw INTEGER NOT NULL DEFAULT 0,
    memo TEXT NOT NULL DEFAULT '', entry_id INTEGER,
    link_id INTEGER);                              -- 자산 간 이체의 짝 거래 (없으면 NULL)
CREATE TABLE IF NOT EXISTS card(
    id INTEGER PRIMARY KEY, sort INTEGER NOT NULL DEFAULT 0,
    company TEXT NOT NULL DEFAULT '', name TEXT NOT NULL, number TEXT NOT NULL DEFAULT '',
    pay_day INTEGER NOT NULL DEFAULT 1,
    bill_from_month INTEGER NOT NULL DEFAULT -1, bill_from_day INTEGER NOT NULL DEFAULT 1,   -- -2 전전월, -1 전월, 0 당월
    bill_to_month INTEGER NOT NULL DEFAULT -1, bill_to_day INTEGER NOT NULL DEFAULT 31,
    bank_account_id INTEGER REFERENCES account(id) ON DELETE SET NULL,
    extra TEXT NOT NULL DEFAULT '{}', memo TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS card_tx(                -- 할부는 회차별 행으로 펼쳐 저장
    id INTEGER PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES card(id) ON DELETE CASCADE,
    group_id INTEGER, date TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
    total INTEGER NOT NULL DEFAULT 0, fee_total INTEGER NOT NULL DEFAULT 0,
    months INTEGER NOT NULL DEFAULT 1, seq INTEGER NOT NULL DEFAULT 1,
    amount INTEGER NOT NULL DEFAULT 0, fee INTEGER NOT NULL DEFAULT 0,
    pay_date TEXT NOT NULL, paid INTEGER NOT NULL DEFAULT 0,
    memo TEXT NOT NULL DEFAULT '', paid_entry_id INTEGER, paid_account_tx_id INTEGER);
CREATE INDEX IF NOT EXISTS card_tx_g ON card_tx(card_id, pay_date);

-- 일정·기념일·주소록·일기·메모
CREATE TABLE IF NOT EXISTS schedule(
    id INTEGER PRIMARY KEY, date TEXT NOT NULL, text TEXT NOT NULL DEFAULT '',
    remind_days INTEGER NOT NULL DEFAULT 0, bg TEXT, fg TEXT, group_id TEXT);
CREATE INDEX IF NOT EXISTS schedule_d ON schedule(date);
CREATE TABLE IF NOT EXISTS anniversary(
    id INTEGER PRIMARY KEY, title TEXT NOT NULL, month INTEGER NOT NULL, day INTEGER NOT NULL,
    year INTEGER,                                   -- NULL = 매년 반복
    lunar INTEGER NOT NULL DEFAULT 0, holiday INTEGER NOT NULL DEFAULT 0, sort INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS contact(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, mobile TEXT NOT NULL DEFAULT '',
    tel1 TEXT NOT NULL DEFAULT '', tel2 TEXT NOT NULL DEFAULT '', fax TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '', homepage TEXT NOT NULL DEFAULT '', address TEXT NOT NULL DEFAULT '',
    zipcode TEXT NOT NULL DEFAULT '', memo TEXT NOT NULL DEFAULT '', grp TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS diary(
    id INTEGER PRIMARY KEY, date TEXT NOT NULL, weather INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '', content TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS memo(
    id INTEGER PRIMARY KEY, title TEXT NOT NULL DEFAULT '', content TEXT NOT NULL DEFAULT '',
    created TEXT, sort INTEGER NOT NULL DEFAULT 0);

-- 자주 쓰는 내역 (한 번에 입력) — 1.7.0
CREATE TABLE IF NOT EXISTS favorite(
    id INTEGER PRIMARY KEY,
    ledger_id INTEGER NOT NULL REFERENCES ledger(id) ON DELETE CASCADE,
    item TEXT NOT NULL DEFAULT '', income INTEGER NOT NULL DEFAULT 0, expense INTEGER NOT NULL DEFAULT 0,
    code TEXT NOT NULL DEFAULT '', memo TEXT NOT NULL DEFAULT '', sort INTEGER NOT NULL DEFAULT 0);
-- 내역 사진 (영수증) — 자료 파일 하나에 같이 들어감 (PC와 휴대폰이 그대로 주고받음)
CREATE TABLE IF NOT EXISTS attachment(
    id INTEGER PRIMARY KEY,
    entry_id INTEGER NOT NULL REFERENCES entry(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT '', mime TEXT NOT NULL DEFAULT 'image/jpeg', data BLOB NOT NULL, created TEXT);
CREATE INDEX IF NOT EXISTS attachment_e ON attachment(entry_id);
-- 저축 목표
CREATE TABLE IF NOT EXISTS goal(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, target INTEGER NOT NULL DEFAULT 0, due TEXT,
    memo TEXT NOT NULL DEFAULT '', done INTEGER NOT NULL DEFAULT 0, sort INTEGER NOT NULL DEFAULT 0, created TEXT);
CREATE TABLE IF NOT EXISTS goal_tx(
    id INTEGER PRIMARY KEY, goal_id INTEGER NOT NULL REFERENCES goal(id) ON DELETE CASCADE,
    date TEXT NOT NULL, amount INTEGER NOT NULL, memo TEXT NOT NULL DEFAULT '');
-- 빌려준 돈(lend)·빌린 돈(borrow)과 갚은 돈
CREATE TABLE IF NOT EXISTS debt(
    id INTEGER PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('lend','borrow')), person TEXT NOT NULL,
    amount INTEGER NOT NULL, date TEXT NOT NULL, due TEXT, memo TEXT NOT NULL DEFAULT '', done INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS debt_pay(
    id INTEGER PRIMARY KEY, debt_id INTEGER NOT NULL REFERENCES debt(id) ON DELETE CASCADE,
    date TEXT NOT NULL, amount INTEGER NOT NULL, memo TEXT NOT NULL DEFAULT '');

-- 휴지통 (1.8.0): 지운 내역을 30일 동안 보관 — entry 는 지운 행 그대로(JSON), 사진은 trash_photo 에
CREATE TABLE IF NOT EXISTS trash(
    id INTEGER PRIMARY KEY, ledger_id INTEGER NOT NULL REFERENCES ledger(id) ON DELETE CASCADE,
    deleted TEXT NOT NULL, why TEXT NOT NULL DEFAULT '', entry TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trash_photo(
    id INTEGER PRIMARY KEY, trash_id INTEGER NOT NULL REFERENCES trash(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT '', mime TEXT NOT NULL DEFAULT 'image/jpeg', data BLOB NOT NULL, created TEXT);
CREATE INDEX IF NOT EXISTS trash_photo_t ON trash_photo(trash_id);

-- 원본에서 의미를 확정하지 못한 표는 내용 그대로 보관 (자료 손실 방지)
CREATE TABLE IF NOT EXISTS legacy_raw(id INTEGER PRIMARY KEY, source TEXT, tbl TEXT, data TEXT);
"""

# 1.8.0 에 더한 열 (안드로이드판 db.js 의 NEW_COLUMNS 와 같은 순서)
NEW_COLUMNS = [
    ('entry', [('pay', "TEXT NOT NULL DEFAULT ''")]),                 # 결제수단: cash·card·bank·pay·card:<카드번호>·etc:<이름>
    ('favorite', [('pay', "TEXT NOT NULL DEFAULT ''")]),
    ('recurring', [('pay', "TEXT NOT NULL DEFAULT ''"),
                   ('cycle', "TEXT NOT NULL DEFAULT 'M'"),             # M=매달 W=매주 Y=매년
                   ('every', 'INTEGER NOT NULL DEFAULT 1'),             # 매주: 몇 주마다
                   ('wday', 'INTEGER NOT NULL DEFAULT 0'),              # 매주: 요일 0=월 … 6=일
                   ('ymonth', 'INTEGER NOT NULL DEFAULT 1'),            # 매년: 몇 월 (날은 day)
                   ('end2', 'TEXT')]),                                  # 매주·매년의 진짜 종료일 (end 는 예전 판이 건너뛰게 막아 둠)
]

DEFAULT_GROUPS = [('0', '수입'), ('1', '공과금'), ('2', '교육비'), ('3', '식비'), ('4', '교통·통신비'),
                  ('5', '생활용품'), ('6', '보험'), ('7', '저축'), ('8', '기타지출')]
DEFAULT_CATEGORIES = [('00', '급여'), ('01', '기타 수입'), ('10', '수도세'), ('11', '전기세'), ('12', '가스비'),
                      ('20', '학원비'), ('21', '교재비'), ('30', '식료품'), ('31', '외식'), ('40', '대중교통'),
                      ('41', '휴대폰 요금'), ('42', '인터넷'), ('50', '생필품'), ('60', '보험료'), ('70', '적금'),
                      ('80', '잡비')]
# (제목, 월, 일, 음력?, 휴일?) — 대한민국 공휴일·주요 기념일
DEFAULT_ANNIVERSARIES = [
    ('신정', 1, 1, 0, 1), ('설날 연휴', 12, 31, 1, 1), ('설날', 1, 1, 1, 1), ('설날 연휴', 1, 2, 1, 1),
    ('삼일절', 3, 1, 0, 1), ('식목일', 4, 5, 0, 0), ('근로자의 날', 5, 1, 0, 0), ('어린이날', 5, 5, 0, 1),
    ('어버이날', 5, 8, 0, 0), ('부처님 오신 날', 4, 8, 1, 1), ('스승의 날', 5, 15, 0, 0), ('현충일', 6, 6, 0, 1),
    ('제헌절', 7, 17, 0, 0), ('광복절', 8, 15, 0, 1), ('추석 연휴', 8, 14, 1, 1), ('추석', 8, 15, 1, 1),
    ('추석 연휴', 8, 16, 1, 1), ('국군의 날', 10, 1, 0, 0), ('개천절', 10, 3, 0, 1), ('한글날', 10, 9, 0, 1),
    ('성탄절', 12, 25, 0, 1)]


def default_db_path():
    """리눅스: ~/.local/share/gagyebu/  ·  윈도우: %APPDATA%/gagyebu/"""
    if os.name == 'nt':
        base = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.join(os.path.expanduser('~'), '.local', 'share')
    return os.path.join(base, 'gagyebu', 'gagyebu.sqlite3')


def connect(path, seed=True):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute('PRAGMA foreign_keys = ON')
    con.execute('PRAGMA journal_mode = WAL')
    con.executescript(SCHEMA)
    cols = {r[1] for r in con.execute('PRAGMA table_info(recurring)')}
    if 'applied_through' not in cols:
        con.execute('ALTER TABLE recurring ADD COLUMN applied_through TEXT')
    cols = {r[1] for r in con.execute('PRAGMA table_info(account_tx)')}
    if 'link_id' not in cols:                      # 자산 간 이체: 짝이 되는 거래 번호 (1.7.0)
        con.execute('ALTER TABLE account_tx ADD COLUMN link_id INTEGER')
    for table, cols_ in NEW_COLUMNS:               # 1.8.0: 예전 판은 모르는 열이라 그냥 둠 (자료를 주고받아도 됨)
        have = {r[1] for r in con.execute(f'PRAGMA table_info({table})')}
        for name, decl in cols_:
            if name not in have:
                con.execute(f'ALTER TABLE {table} ADD COLUMN {name} {decl}')
    if get_meta(con, 'schema_version') is None:
        set_meta(con, 'schema_version', SCHEMA_VERSION)
    if seed and not con.execute('SELECT 1 FROM ledger LIMIT 1').fetchone():
        seed_defaults(con)
    con.commit()
    return con


def seed_defaults(con, with_ledger=True, with_anniversaries=True):
    if with_ledger:
        lid = con.execute("INSERT INTO ledger(name, sort) VALUES('가계부 장부', 1)").lastrowid
        con.executemany('INSERT INTO cat_group VALUES(?,?,?)', [(lid, c, n) for c, n in DEFAULT_GROUPS])
        con.executemany('INSERT INTO category VALUES(?,?,?,?)',
                        [(lid, c, n, i) for i, (c, n) in enumerate(DEFAULT_CATEGORIES)])
    if with_anniversaries and not con.execute('SELECT 1 FROM anniversary LIMIT 1').fetchone():
        con.executemany('INSERT INTO anniversary(title,month,day,lunar,holiday,sort) VALUES(?,?,?,?,?,?)',
                        [(t, m, d, lu, h, i) for i, (t, m, d, lu, h) in enumerate(DEFAULT_ANNIVERSARIES)])


class ConProxy:
    """화면들이 공유하는 연결. 가져오기·복원 때 실제 연결만 바꿔 끼운다."""
    def __init__(self, con):
        self._con = con

    def __getattr__(self, name):
        return getattr(self._con, name)

    def swap(self, con):
        self._con = con


def get_meta(con, key, default=None):
    r = con.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
    return r['value'] if r else default


def set_meta(con, key, value):
    con.execute('INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                (key, None if value is None else str(value)))


def get_json(con, key, default):
    v = get_meta(con, key)
    try:
        return json.loads(v) if v else default
    except ValueError:
        return default


def set_json(con, key, value):
    set_meta(con, key, json.dumps(value, ensure_ascii=False))
