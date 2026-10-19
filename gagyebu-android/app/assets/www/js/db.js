/* SQLite 저장소 (PC판 gagyebu/db.py 와 같은 표 구조 → 백업 파일을 PC와 그대로 주고받음).
   안드로이드 SQLite(7.0 = 3.9)에 없는 문법(ON CONFLICT DO UPDATE 등)은 쓰지 않는다. */
'use strict';
const DB = (() => {
  const SCHEMA_VERSION = 1;
  const SCHEMA = `
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS ledger(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, sort INTEGER NOT NULL DEFAULT 0,
    memo TEXT NOT NULL DEFAULT '', legacy_file TEXT);
CREATE TABLE IF NOT EXISTS cat_group(
    ledger_id INTEGER NOT NULL REFERENCES ledger(id) ON DELETE CASCADE,
    code TEXT NOT NULL, name TEXT NOT NULL, PRIMARY KEY(ledger_id, code));
CREATE TABLE IF NOT EXISTS category(
    ledger_id INTEGER NOT NULL REFERENCES ledger(id) ON DELETE CASCADE,
    code TEXT NOT NULL, name TEXT NOT NULL, sort INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(ledger_id, code));
CREATE TABLE IF NOT EXISTS entry(
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
CREATE TABLE IF NOT EXISTS item_word(
    ledger_id INTEGER NOT NULL REFERENCES ledger(id) ON DELETE CASCADE,
    name TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(ledger_id, name));
CREATE TABLE IF NOT EXISTS recurring(
    id INTEGER PRIMARY KEY,
    ledger_id INTEGER NOT NULL REFERENCES ledger(id) ON DELETE CASCADE,
    item TEXT NOT NULL DEFAULT '', income INTEGER NOT NULL DEFAULT 0, expense INTEGER NOT NULL DEFAULT 0,
    code TEXT NOT NULL DEFAULT '', day INTEGER NOT NULL, start TEXT NOT NULL, end TEXT,
    memo TEXT NOT NULL DEFAULT '', created TEXT,
    applied_through TEXT);
CREATE TABLE IF NOT EXISTS recurring_log(
    id INTEGER PRIMARY KEY,
    recurring_id INTEGER REFERENCES recurring(id) ON DELETE SET NULL,
    ledger_id INTEGER NOT NULL REFERENCES ledger(id) ON DELETE CASCADE,
    date TEXT NOT NULL, item TEXT, income INTEGER, expense INTEGER, code TEXT,
    entry_id INTEGER, skipped INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS rlog_r ON recurring_log(recurring_id, date);
CREATE TABLE IF NOT EXISTS account(
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL CHECK(kind IN ('bank','securities','insurance','property')),
    sort INTEGER NOT NULL DEFAULT 0, name TEXT NOT NULL, company TEXT NOT NULL DEFAULT '',
    owner TEXT NOT NULL DEFAULT '', number TEXT NOT NULL DEFAULT '',
    opening INTEGER NOT NULL DEFAULT 0,
    valuation INTEGER NOT NULL DEFAULT 0,
    loan INTEGER NOT NULL DEFAULT 0,
    deposit INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    extra TEXT NOT NULL DEFAULT '{}', memo TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS account_tx(
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES account(id) ON DELETE CASCADE,
    date TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
    deposit INTEGER NOT NULL DEFAULT 0, withdraw INTEGER NOT NULL DEFAULT 0,
    memo TEXT NOT NULL DEFAULT '', entry_id INTEGER);
CREATE TABLE IF NOT EXISTS card(
    id INTEGER PRIMARY KEY, sort INTEGER NOT NULL DEFAULT 0,
    company TEXT NOT NULL DEFAULT '', name TEXT NOT NULL, number TEXT NOT NULL DEFAULT '',
    pay_day INTEGER NOT NULL DEFAULT 1,
    bill_from_month INTEGER NOT NULL DEFAULT -1, bill_from_day INTEGER NOT NULL DEFAULT 1,
    bill_to_month INTEGER NOT NULL DEFAULT -1, bill_to_day INTEGER NOT NULL DEFAULT 31,
    bank_account_id INTEGER REFERENCES account(id) ON DELETE SET NULL,
    extra TEXT NOT NULL DEFAULT '{}', memo TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS card_tx(
    id INTEGER PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES card(id) ON DELETE CASCADE,
    group_id INTEGER, date TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
    total INTEGER NOT NULL DEFAULT 0, fee_total INTEGER NOT NULL DEFAULT 0,
    months INTEGER NOT NULL DEFAULT 1, seq INTEGER NOT NULL DEFAULT 1,
    amount INTEGER NOT NULL DEFAULT 0, fee INTEGER NOT NULL DEFAULT 0,
    pay_date TEXT NOT NULL, paid INTEGER NOT NULL DEFAULT 0,
    memo TEXT NOT NULL DEFAULT '', paid_entry_id INTEGER, paid_account_tx_id INTEGER);
CREATE INDEX IF NOT EXISTS card_tx_g ON card_tx(card_id, pay_date);
CREATE TABLE IF NOT EXISTS schedule(
    id INTEGER PRIMARY KEY, date TEXT NOT NULL, text TEXT NOT NULL DEFAULT '',
    remind_days INTEGER NOT NULL DEFAULT 0, bg TEXT, fg TEXT, group_id TEXT);
CREATE INDEX IF NOT EXISTS schedule_d ON schedule(date);
CREATE TABLE IF NOT EXISTS anniversary(
    id INTEGER PRIMARY KEY, title TEXT NOT NULL, month INTEGER NOT NULL, day INTEGER NOT NULL,
    year INTEGER,
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
CREATE TABLE IF NOT EXISTS legacy_raw(id INTEGER PRIMARY KEY, source TEXT, tbl TEXT, data TEXT)`;

  const DEFAULT_GROUPS = [['0', '수입'], ['1', '공과금'], ['2', '교육비'], ['3', '식비'], ['4', '교통·통신비'],
    ['5', '생활용품'], ['6', '보험'], ['7', '저축'], ['8', '기타지출']];
  const DEFAULT_CATEGORIES = [['00', '급여'], ['01', '기타 수입'], ['10', '수도세'], ['11', '전기세'], ['12', '가스비'],
    ['20', '학원비'], ['21', '교재비'], ['30', '식료품'], ['31', '외식'], ['40', '대중교통'],
    ['41', '휴대폰 요금'], ['42', '인터넷'], ['50', '생필품'], ['60', '보험료'], ['70', '적금'], ['80', '잡비']];
  const DEFAULT_ANNIVERSARIES = [
    ['신정', 1, 1, 0, 1], ['설날 연휴', 12, 31, 1, 1], ['설날', 1, 1, 1, 1], ['설날 연휴', 1, 2, 1, 1],
    ['삼일절', 3, 1, 0, 1], ['식목일', 4, 5, 0, 0], ['근로자의 날', 5, 1, 0, 0], ['어린이날', 5, 5, 0, 1],
    ['어버이날', 5, 8, 0, 0], ['부처님 오신 날', 4, 8, 1, 1], ['스승의 날', 5, 15, 0, 0], ['현충일', 6, 6, 0, 1],
    ['제헌절', 7, 17, 0, 0], ['광복절', 8, 15, 0, 1], ['추석 연휴', 8, 14, 1, 1], ['추석', 8, 15, 1, 1],
    ['추석 연휴', 8, 16, 1, 1], ['국군의 날', 10, 1, 0, 0], ['개천절', 10, 3, 0, 1], ['한글날', 10, 9, 0, 1],
    ['성탄절', 12, 25, 0, 1]];

  let N = null;          // window.GagyebuNative
  let depth = 0;         // 묶음 저장(트랜잭션) 깊이

  function call(res) {
    const o = JSON.parse(res);
    if (!o.ok) throw new Error(o.error || '저장소 오류');
    return o;
  }
  const argJson = args => JSON.stringify((args || []).map(v => (v === undefined ? null : v)));

  /** 여러 행: [{열:값}] */
  function q(sql, args) {
    const o = call(N.query(sql, argJson(args)));
    const cols = o.cols;
    return o.rows.map(r => { const x = {}; for (let i = 0; i < cols.length; i++) x[cols[i]] = r[i]; return x; });
  }
  /** 첫 행 (없으면 null) */
  const one = (sql, args) => q(sql, args)[0] || null;
  /** 첫 행 첫 칸 */
  function val(sql, args) {
    const o = call(N.query(sql, argJson(args)));
    return o.rows.length ? o.rows[0][0] : null;
  }
  /** {changes, lastId} */
  function run(sql, args) {
    const o = call(N.exec(sql, argJson(args)));
    return { changes: o.changes || 0, lastId: o.lastId };
  }
  /** fn 을 한 묶음으로 저장 (중간에 오류가 나면 모두 취소). 안쪽에서 또 부르면 바깥 묶음에 합쳐짐 */
  function tx(fn) {
    if (depth > 0) return fn();
    call(N.begin());
    depth++;
    try {
      const r = fn();
      depth--;
      call(N.commit());
      return r;
    } catch (e) {
      depth--;
      try { call(N.rollback()); } catch (_) { /* 무시 */ }
      throw e;
    }
  }

  function statements(script) {
    return script.split(';').map(s => s.trim()).filter(Boolean);
  }

  function open(native) {
    N = native;
    for (const s of statements(SCHEMA)) run(s);
    const cols = q('PRAGMA table_info(recurring)').map(r => r.name);
    if (!cols.includes('applied_through')) run('ALTER TABLE recurring ADD COLUMN applied_through TEXT');
    if (getMeta('schema_version') === null) setMeta('schema_version', SCHEMA_VERSION);
    if (!one('SELECT 1 AS x FROM ledger LIMIT 1')) tx(() => seedDefaults(true, true));
  }

  function seedDefaults(withLedger, withAnniv) {
    if (withLedger) {
      const lid = run("INSERT INTO ledger(name, sort) VALUES('가계부 장부', 1)").lastId;
      for (const [c, n] of DEFAULT_GROUPS) run('INSERT INTO cat_group VALUES(?,?,?)', [lid, c, n]);
      DEFAULT_CATEGORIES.forEach(([c, n], i) => run('INSERT INTO category VALUES(?,?,?,?)', [lid, c, n, i]));
    }
    if (withAnniv && !one('SELECT 1 AS x FROM anniversary LIMIT 1')) {
      DEFAULT_ANNIVERSARIES.forEach(([t, m, d, lu, h], i) =>
        run('INSERT INTO anniversary(title,month,day,lunar,holiday,sort) VALUES(?,?,?,?,?,?)', [t, m, d, lu, h, i]));
    }
  }

  function getMeta(key, dflt) {
    const r = one('SELECT value FROM meta WHERE key=?', [key]);
    return r ? r.value : (dflt === undefined ? null : dflt);
  }
  function setMeta(key, value) {
    run('INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)', [key, value === null || value === undefined ? null : String(value)]);
  }
  function getJson(key, dflt) {
    const v = getMeta(key);
    try { return v ? JSON.parse(v) : dflt; } catch (_) { return dflt; }
  }
  const setJson = (key, value) => setMeta(key, JSON.stringify(value));

  return { SCHEMA, open, q, one, val, run, tx, getMeta, setMeta, getJson, setJson, seedDefaults,
    DEFAULT_ANNIVERSARIES };
})();
