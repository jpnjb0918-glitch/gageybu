/* 자료 처리 (PC판 gagyebu/services/*.py 를 그대로 옮김 — 같은 자료에서 같은 결과가 나와야 함) */
'use strict';

// ════════════════ 사용자가 정한 순서 (services/order.py 와 같은 규칙) ════════════════
// 자료 파일 호환을 위해 표에 칸을 더하지 않는다.
//  대분류 → meta 'order_groups:<장부id>', 같은 날 내역 → meta 'order_day:<장부id>' = {날짜: [id...]},
//  주소록·일기 → meta 'order_list:contact|diary', 소분류·메모 → 원래 있던 sort 칸.
//  저장된 순서에 있는 것이 먼저 그 순서대로, 새로 생긴 것은 그 뒤에 원래 순서대로.
const Ord = (() => {
  const LIST_TABLES = ['contact', 'diary'];
  function get(key, dflt) {
    const v = DB.getJson(key, dflt);
    return (Array.isArray(dflt) ? Array.isArray(v) : (v && typeof v === 'object' && !Array.isArray(v))) ? v : dflt;
  }
  function put(key, value) {
    const empty = Array.isArray(value) ? !value.length : !Object.keys(value).length;
    DB.setMeta(key, empty ? null : JSON.stringify(value));
  }
  function byList(rows, ids, key) {
    key = key || (r => r.id);
    if (!ids || !ids.length) return rows.slice();
    const pos = new Map();
    ids.forEach((v, i) => { if (!pos.has(v)) pos.set(v, i); });
    const listed = rows.filter(r => pos.has(key(r))).sort((a, b) => pos.get(key(a)) - pos.get(key(b)));
    return listed.concat(rows.filter(r => !pos.has(key(r))));
  }
  const groupOrder = lid => get(`order_groups:${lid}`, []).map(String);
  const setGroupOrder = (lid, codes) => put(`order_groups:${lid}`, codes.map(String));
  function dayOrders(lid) {
    const d = get(`order_day:${lid}`, {});
    const out = {};
    for (const [k, v] of Object.entries(d)) if (Array.isArray(v)) out[k] = v.map(Number).filter(Number.isInteger);
    return out;
  }
  function setDayOrder(lid, date, ids) {
    const d = get(`order_day:${lid}`, {});
    ids = ids.map(Number);
    const sorted = ids.slice().sort((a, b) => a - b);
    if (ids.every((v, i) => v === sorted[i])) delete d[date]; else d[date] = ids;
    put(`order_day:${lid}`, d);
  }
  /** 날짜순(같은 날 id 순) 행들의 같은 날 안 순서를 바꿈. desc 면 날짜를 최근 것부터
   *  (순서를 정한 날은 정한 순서 그대로, 안 정한 날은 최근 입력이 위로). 행이 [r, 잔액] 이어도 됨 */
  function applyDayOrder(rows, orders, desc) {
    const R = x => (Array.isArray(x) ? x[0] : x);
    const out = [];
    let i = 0;
    while (i < rows.length) {
      const d = String(R(rows[i]).date);
      let j = i;
      while (j < rows.length && String(R(rows[j]).date) === d) j++;
      let g = rows.slice(i, j).sort((a, b) => R(a).id - R(b).id);
      if (orders[d]) g = byList(g, orders[d], x => R(x).id);
      else if (desc) g.reverse();
      out.push(g);
      i = j;
    }
    if (desc) out.reverse();
    return out.flat();
  }
  function listOrder(table) {
    if (!LIST_TABLES.includes(table)) throw new Error('bad table');
    return get(`order_list:${table}`, []).map(Number).filter(Number.isInteger);
  }
  function setListOrder(table, ids) {
    if (!LIST_TABLES.includes(table)) throw new Error('bad table');
    put(`order_list:${table}`, ids.map(Number));
  }
  /** 보이는 일부(그룹·달)만 순서를 바꿀 때: 다른 것은 그대로 두고 이것들을 정한 순서로 뒤에 붙임. reset 이면 이것들만 순서에서 뺌 */
  function mergeListOrder(table, viewIds, newOrder) {
    const v = new Set(viewIds.map(Number));
    setListOrder(table, listOrder(table).filter(x => !v.has(x)).concat(newOrder ? newOrder.map(Number) : []));
  }
  const applyListOrder = (table, rows) => byList(rows, listOrder(table));
  function setCategoryOrder(lid, codes) {
    DB.tx(() => codes.forEach((c, i) => DB.run('UPDATE category SET sort=? WHERE ledger_id=? AND code=?', [i + 1, lid, c])));
  }
  function setMemoOrder(ids) {
    DB.tx(() => ids.forEach((id, i) => DB.run('UPDATE memo SET sort=? WHERE id=?', [i + 1, id])));
  }
  return { byList, groupOrder, setGroupOrder, dayOrders, setDayOrder, applyDayOrder, listOrder, setListOrder,
    mergeListOrder, applyListOrder, setCategoryOrder, setMemoOrder };
})();

// ════════════════ 장부·계정과목·내역 (services/ledger.py) ════════════════
const L = (() => {
  const ledgers = () => DB.q('SELECT * FROM ledger ORDER BY sort, id');

  function addLedger(name, copyFrom, codesOnly) {
    return DB.tx(() => {
      const sort = DB.val('SELECT COALESCE(MAX(sort),0)+1 AS v FROM ledger');
      const lid = DB.run('INSERT INTO ledger(name, sort) VALUES(?,?)', [name, sort]).lastId;
      if (copyFrom) {
        DB.run('INSERT INTO cat_group SELECT ?, code, name FROM cat_group WHERE ledger_id=?', [lid, copyFrom]);
        DB.run('INSERT INTO category SELECT ?, code, name, sort FROM category WHERE ledger_id=?', [lid, copyFrom]);
        if (!codesOnly) {
          DB.run('INSERT INTO entry(ledger_id,date,item,income,expense,code,memo,origin) ' +
            'SELECT ?,date,item,income,expense,code,memo,origin FROM entry WHERE ledger_id=? ORDER BY date,id', [lid, copyFrom]);
          DB.run('INSERT INTO budget SELECT ?, ym, code, amount FROM budget WHERE ledger_id=?', [lid, copyFrom]);
          DB.run('INSERT INTO item_word SELECT ?, name, count FROM item_word WHERE ledger_id=?', [lid, copyFrom]);
          for (const r of DB.q('SELECT * FROM recurring WHERE ledger_id=?', [copyFrom])) {
            const thr = R.processedThrough(r.id);
            DB.run('INSERT INTO recurring(ledger_id,item,income,expense,code,day,start,end,memo,created,applied_through) ' +
              'VALUES(?,?,?,?,?,?,?,?,?,?,?)',
              [lid, r.item, r.income, r.expense, r.code, r.day, r.start, r.end, r.memo, r.created, thr || null]);
          }
        }
      } else {
        DB.run("INSERT INTO cat_group VALUES(?, '0', '수입')", [lid]);
      }
      return lid;
    });
  }

  /** 기본 장부(생활비·용돈·비상금·여행)를 자료 파일마다 한 번만 — PC판 ledger.ensure_default_ledgers 와 같은 규칙
      (계정과목은 첫 장부에서 복사, 같은 이름 있으면 건너뜀, meta default_ledgers 로 표시 → 지운 장부는 다시 안 생김) */
  const DEFAULT_EXTRA_LEDGERS = ['생활비 장부', '용돈 장부', '비상금 장부', '여행 장부'];
  function ensureDefaultLedgers() {
    if (DB.getMeta('default_ledgers')) return [];
    const first = firstLedgerId();
    if (first === null) return [];
    const have = new Set(ledgers().map(l => l.name));
    const added = DEFAULT_EXTRA_LEDGERS.filter(n => !have.has(n)).map(n => addLedger(n, first, true));
    DB.setMeta('default_ledgers', '1');
    return added;
  }
  const renameLedger = (lid, name) => DB.run('UPDATE ledger SET name=? WHERE id=?', [name, lid]);
  function firstLedgerId() { const r = DB.one('SELECT id FROM ledger ORDER BY sort, id LIMIT 1'); return r ? r.id : null; }
  function deleteLedger(lid) {
    if (lid === firstLedgerId()) throw new Error('첫 번째 장부는 삭제할 수 없습니다 (이름 변경은 가능).');
    DB.run('DELETE FROM ledger WHERE id=?', [lid]);
  }
  /** 장부 데이터 초기화: 내역·예산·예약 삭제, 계정과목은 유지 */
  function resetLedger(lid) {
    DB.tx(() => {
      for (const t of ['entry', 'budget', 'recurring_log', 'recurring', 'item_word']) DB.run(`DELETE FROM ${t} WHERE ledger_id=?`, [lid]);
    });
  }

  // ── 계정과목 ──
  const ci = c => U.CODE_CHARS.indexOf(c);
  /** 대분류 (사용자가 정한 순서가 있으면 그 순서, 없으면 코드 순) */
  function groups(lid) {
    const rows = DB.q('SELECT code, name FROM cat_group WHERE ledger_id=?', [lid]);
    const k = r => (r.code.length === 1 && ci(r.code) >= 0 ? ci(r.code) : 99);
    return Ord.byList(rows.sort((a, b) => k(a) - k(b)), Ord.groupOrder(lid), r => r.code);
  }
  /** 소분류: 대분류 순서 → sort(사용자가 정한 순서) → 코드 */
  function categories(lid, group) {
    let sql = 'SELECT code, name, sort FROM category WHERE ledger_id=?';
    const args = [lid];
    if (group !== undefined && group !== null) { sql += ' AND substr(code,1,1)=?'; args.push(group); }
    const rank = {};
    groups(lid).forEach((g, i) => { rank[g.code] = i; });
    const gr = c => (c in rank ? rank[c] : 100 + Math.max(ci(c), 0));
    return DB.q(sql, args).sort((a, b) => (gr(a.code.slice(0, 1)) - gr(b.code.slice(0, 1))) || (a.sort - b.sort) ||
      (a.code < b.code ? -1 : a.code > b.code ? 1 : 0));
  }
  function categoryMap(lid) { const m = {}; for (const r of DB.q('SELECT code,name FROM category WHERE ledger_id=?', [lid])) m[r.code] = r.name; return m; }
  function groupMap(lid) { const m = {}; for (const r of DB.q('SELECT code,name FROM cat_group WHERE ledger_id=?', [lid])) m[r.code] = r.name; return m; }

  function setGroup(lid, code, name) {
    if (code === '0' && DB.one("SELECT 1 AS x FROM cat_group WHERE ledger_id=? AND code='0'", [lid])) name = '수입';
    if (!name) return;
    DB.run('INSERT OR REPLACE INTO cat_group VALUES(?,?,?)', [lid, code, name]);
  }
  function deleteGroup(lid, code) {
    if (code === '0') throw new Error('0번(수입) 대분류는 삭제할 수 없습니다.');
    if (categories(lid, code).length) throw new Error('소분류가 남아 있으면 대분류를 삭제할 수 없습니다.');
    DB.run('DELETE FROM cat_group WHERE ledger_id=? AND code=?', [lid, code]);
  }
  function setCategory(lid, code, name) {
    if (!name) return;
    const r = DB.one('SELECT sort FROM category WHERE ledger_id=? AND code=?', [lid, code]);
    if (!r) {
      const nxt = DB.val('SELECT COALESCE(MAX(sort),0)+1 AS v FROM category WHERE ledger_id=? AND substr(code,1,1)=?', [lid, code.slice(0, 1)]);
      DB.run('INSERT INTO category VALUES(?,?,?,?)', [lid, code, name, nxt]);
    } else {
      DB.run('UPDATE category SET name=? WHERE ledger_id=? AND code=?', [name, lid, code]);
    }
  }
  function moveCategoryOrder(lid, code, delta) {
    const codes = categories(lid, code.slice(0, 1)).map(r => r.code);
    const i = codes.indexOf(code), j = i + delta;
    if (i < 0 || j < 0 || j >= codes.length) return;
    [codes[i], codes[j]] = [codes[j], codes[i]];
    DB.tx(() => codes.forEach((c, k) => DB.run('UPDATE category SET sort=? WHERE ledger_id=? AND code=?', [k, lid, c])));
  }
  /** src 계정으로 입력된 모든 내역·예약·예산을 dst 로 옮기고 src 삭제 */
  function mergeCategory(lid, src, dst) {
    if (src === dst) return;
    if (!DB.one('SELECT 1 AS x FROM category WHERE ledger_id=? AND code=?', [lid, dst])) throw new Error(`계정코드 ${dst} 가 없습니다.`);
    DB.tx(() => {
      DB.run('UPDATE entry SET code=? WHERE ledger_id=? AND code=?', [dst, lid, src]);
      DB.run('UPDATE recurring SET code=? WHERE ledger_id=? AND code=?', [dst, lid, src]);
      for (const r of DB.q('SELECT ym, amount FROM budget WHERE ledger_id=? AND code=?', [lid, src])) {
        if (!DB.run('UPDATE budget SET amount=amount+? WHERE ledger_id=? AND ym=? AND code=?', [r.amount, lid, r.ym, dst]).changes) {
          DB.run('INSERT INTO budget VALUES(?,?,?,?)', [lid, r.ym, dst, r.amount]);
        }
      }
      DB.run('DELETE FROM budget WHERE ledger_id=? AND code=?', [lid, src]);
      DB.run('DELETE FROM category WHERE ledger_id=? AND code=?', [lid, src]);
    });
  }
  function categoryUsage(lid, code) {
    const n = t => DB.val(`SELECT COUNT(*) AS v FROM ${t} WHERE ledger_id=? AND code=?`, [lid, code]);
    return { entry: n('entry'), recurring: n('recurring'), budget: n('budget') };
  }
  /** 원본과 같이 그 계정의 내역·예약·예산도 함께 삭제 */
  function deleteCategory(lid, code) {
    DB.tx(() => { for (const t of ['entry', 'recurring', 'budget', 'category']) DB.run(`DELETE FROM ${t} WHERE ledger_id=? AND code=?`, [lid, code]); });
  }

  // ── 내역 ──
  const norm = e => [e.date, (e.item || '').trim(), parseInt(e.income || 0, 10), parseInt(e.expense || 0, 10),
    (e.code || '').trim(), (e.memo || '').trim()];

  function addEntry(lid, e, origin) {
    const [d, item, inc, exp, code, memo] = norm(e);
    return DB.tx(() => {
      const eid = DB.run('INSERT INTO entry(ledger_id,date,item,income,expense,code,memo,origin) VALUES(?,?,?,?,?,?,?,?)',
        [lid, d, item, inc, exp, code, memo, origin || null]).lastId;
      if (item && !DB.run('UPDATE item_word SET count=count+1 WHERE ledger_id=? AND name=?', [lid, item]).changes) {
        DB.run('INSERT INTO item_word VALUES(?,?,1)', [lid, item]);
      }
      return eid;
    });
  }
  function updateEntry(eid, e) {
    const [d, item, inc, exp, code, memo] = norm(e);
    DB.run('UPDATE entry SET date=?,item=?,income=?,expense=?,code=?,memo=? WHERE id=?', [d, item, inc, exp, code, memo, eid]);
  }
  const deleteEntries = ids => DB.tx(() => ids.forEach(i => DB.run('DELETE FROM entry WHERE id=?', [i])));
  const getEntry = eid => DB.one('SELECT * FROM entry WHERE id=?', [eid]);
  const balanceBefore = (lid, date) => DB.val('SELECT COALESCE(SUM(income-expense),0) AS v FROM entry WHERE ledger_id=? AND date<?', [lid, date]);

  /** 날짜순 내역 + 각 행까지의 누적 잔액(이전 기간 이월 포함) */
  function entriesWithBalance(lid, start, end) {
    let sql = 'SELECT * FROM entry WHERE ledger_id=?';
    const a = [lid];
    if (start) { sql += ' AND date>=?'; a.push(start); }
    if (end) { sql += ' AND date<=?'; a.push(end); }
    const rows = Ord.applyDayOrder(DB.q(sql + ' ORDER BY date, id', a), Ord.dayOrders(lid));   // 같은 날 안은 사용자가 정한 순서
    let bal = start ? balanceBefore(lid, start) : 0;
    return rows.map(r => { bal += r.income - r.expense; return [r, bal]; });
  }
  function totals(lid, start, end) {
    const r = DB.one('SELECT COALESCE(SUM(income),0) AS i, COALESCE(SUM(expense),0) AS e FROM entry WHERE ledger_id=? AND date BETWEEN ? AND ?', [lid, start, end]);
    return [r.i, r.e];
  }
  function currentBalance(lid, upto) {
    let sql = 'SELECT COALESCE(SUM(income-expense),0) AS v FROM entry WHERE ledger_id=?';
    const a = [lid];
    if (upto) { sql += ' AND date<=?'; a.push(upto); }
    return DB.val(sql, a);
  }

  const AMOUNT_OPS = { '같은 금액': '=', '크거나 같은 금액': '>=', '작거나 같은 금액': '<=', '큰 금액': '>', '작은 금액': '<' };
  /** 검색 조건 4가지 (AND): 기간·품목 글자·계정코드(복수)·금액 */
  function search(lid, o) {
    o = o || {};
    let sql = 'SELECT * FROM entry WHERE ledger_id=?';
    const a = [lid];
    if (o.start) { sql += ' AND date>=?'; a.push(o.start); }
    if (o.end) { sql += ' AND date<=?'; a.push(o.end); }
    if (o.text) {
      sql += " AND (item LIKE ? ESCAPE '\\' OR memo LIKE ? ESCAPE '\\')";
      const t = '%' + o.text.replace(/\\/g, '\\\\').replace(/%/g, '\\%').replace(/_/g, '\\_') + '%';
      a.push(t, t);
    }
    if (o.codes && o.codes.length) { sql += ` AND code IN (${o.codes.map(() => '?').join(',')})`; a.push(...o.codes); }
    if (o.amount !== undefined && o.amount !== null) {
      const op = AMOUNT_OPS[o.amountOp || '같은 금액'];
      const side = o.amountSide || '수입+지출';
      if (side === '수입') { sql += ` AND income ${op} ? AND income<>0`; a.push(o.amount); }
      else if (side === '지출') { sql += ` AND expense ${op} ? AND expense<>0`; a.push(o.amount); }
      else { sql += ` AND ((income<>0 AND income ${op} ?) OR (expense<>0 AND expense ${op} ?))`; a.push(o.amount, o.amount); }
    }
    const col = { date: 'date', item: 'item', income: 'income', expense: 'expense', code: 'code', memo: 'memo' }[o.order] || 'date';
    const dir = o.desc ? 'DESC' : 'ASC';
    const rows = DB.q(sql + ` ORDER BY ${col} ${dir}, id ${dir}`, a);
    if (col !== 'date') return rows;
    const asc = rows.slice().sort((x, y) => (x.date < y.date ? -1 : x.date > y.date ? 1 : x.id - y.id));
    return Ord.applyDayOrder(asc, Ord.dayOrders(lid), !!o.desc);
  }

  // ── 품목 자동완성 ──
  const itemWords = (lid, minCount) => DB.q('SELECT name, count FROM item_word WHERE ledger_id=? AND count>=? ORDER BY count DESC, name', [lid, minCount || 1]);
  function setItemWord(lid, name, count, oldName) {
    DB.tx(() => {
      if (oldName && oldName !== name) DB.run('DELETE FROM item_word WHERE ledger_id=? AND name=?', [lid, oldName]);
      DB.run('INSERT OR REPLACE INTO item_word VALUES(?,?,?)', [lid, name, count]);
    });
  }
  const deleteItemWord = (lid, name) => DB.run('DELETE FROM item_word WHERE ledger_id=? AND name=?', [lid, name]);
  function lastCodeForItem(lid, item) {
    const r = DB.one('SELECT code FROM entry WHERE ledger_id=? AND item=? ORDER BY date DESC, id DESC LIMIT 1', [lid, item]);
    return r ? r.code : null;
  }
  const codeLabel = (cmap, code) => cmap[code] || (code ? `(미분류 ${code})` : '(미분류)');
  /** 보고서용: 수입 계정은 수입-지출, 지출 계정은 지출-수입 */
  const signedAmount = (code, income, expense) => (U.isIncomeCode(code) ? income - expense : expense - income);

  return { ledgers, addLedger, ensureDefaultLedgers, DEFAULT_EXTRA_LEDGERS, renameLedger, firstLedgerId, deleteLedger, resetLedger, groups, categories,
    categoryMap, groupMap, setGroup, deleteGroup, setCategory, moveCategoryOrder, mergeCategory, categoryUsage,
    deleteCategory, addEntry, updateEntry, deleteEntries, getEntry, balanceBefore, entriesWithBalance, totals,
    currentBalance, AMOUNT_OPS, search, itemWords, setItemWord, deleteItemWord, lastCodeForItem, codeLabel, signedAmount };
})();

// ════════════════ 예약 (services/recurring.py) ════════════════
const R = (() => {
  const rules = lid => DB.q('SELECT * FROM recurring WHERE ledger_id=? ORDER BY day, id', [lid]);

  function saveRule(lid, r, rid) {
    const vals = [r.item || '', parseInt(r.income || 0, 10), parseInt(r.expense || 0, 10), r.code || '',
      parseInt(r.day, 10), r.start, r.end || null, r.memo || ''];
    if (rid) {
      // 규칙을 고쳐도 이미 처리한 기간은 다시 묻지 않음
      const thr = processedThrough(rid);
      DB.run('UPDATE recurring SET item=?,income=?,expense=?,code=?,day=?,start=?,end=?,memo=?,applied_through=? WHERE id=?',
        vals.concat([thr || null, rid]));
      return rid;
    }
    return DB.run('INSERT INTO recurring(item,income,expense,code,day,start,end,memo,ledger_id,created) VALUES(?,?,?,?,?,?,?,?,?,?)',
      vals.concat([lid, U.today()])).lastId;
  }
  const deleteRule = rid => DB.run('DELETE FROM recurring WHERE id=?', [rid]);

  /** rule 이 start~end 사이에 입력될 날짜들 */
  function occurrences(rule, start, end) {
    const lo = start > rule.start ? start : rule.start;
    const hi = rule.end ? (end < rule.end ? end : rule.end) : end;
    const out = [];
    if (lo > hi) return out;
    let [y, m] = U.parts(lo);
    const [hy, hm] = U.parts(hi);
    while (y < hy || (y === hy && m <= hm)) {
      const d = U.clampDay(y, m, rule.day);
      if (lo <= d && d <= hi) out.push(d);
      [y, m] = U.addMonths(y, m, 1);
    }
    return out;
  }
  const lastLogged = rid => DB.val('SELECT MAX(date) AS v FROM recurring_log WHERE recurring_id=?', [rid]);
  /** applied_through 와 마지막 기록 날짜 중 늦은 날 */
  function processedThrough(rid) {
    const r = DB.one('SELECT applied_through FROM recurring WHERE id=?', [rid]);
    const c = [r && r.applied_through ? String(r.applied_through).slice(0, 10) : null, lastLogged(rid)].filter(Boolean);
    return c.length ? c.sort()[c.length - 1] : null;
  }
  /** [오늘까지 입력될 목록, 오늘 이후 이달에 남은 목록] — 각 항목 {rule, date} */
  function pending(lid, today) {
    today = today || U.today();
    const [ty, tm] = U.parts(today);
    const monthLast = U.clampDay(ty, tm, 31);
    const due = [], later = [];
    for (const r of rules(lid)) {
      const done = new Set(DB.q('SELECT date FROM recurring_log WHERE recurring_id=?', [r.id]).map(x => String(x.date).slice(0, 10)));
      const thr = r.applied_through ? String(r.applied_through).slice(0, 10) : null;
      for (const d of occurrences(r, r.start, monthLast)) {
        if (!done.has(d) && !(thr && d <= thr)) (d <= today ? due : later).push({ rule: r, date: d });
      }
    }
    const key = (a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : a.rule.id - b.rule.id);
    return [due.sort(key), later.sort(key)];
  }
  /** items 를 장부에 입력 (skip=true 면 입력 없이 '건너뜀'으로 기록만) */
  function apply(lid, items, skip) {
    DB.tx(() => {
      for (const { rule: r, date: d } of items) {
        let eid = null;
        if (!skip) {
          eid = L.addEntry(lid, { date: d, item: r.item, income: r.income, expense: r.expense, code: r.code, memo: r.memo },
            `recurring:${r.id}`);
        }
        DB.run('INSERT INTO recurring_log(recurring_id,ledger_id,date,item,income,expense,code,entry_id,skipped) VALUES(?,?,?,?,?,?,?,?,?)',
          [r.id, lid, d, r.item, r.income, r.expense, r.code, eid, skip ? 1 : 0]);
      }
    });
  }
  function log(o) {
    o = o || {};
    let sql = 'SELECT * FROM recurring_log WHERE 1=1';
    const a = [];
    if (o.rid) { sql += ' AND recurring_id=?'; a.push(o.rid); }
    if (o.lid) { sql += ' AND ledger_id=?'; a.push(o.lid); }
    if (o.start) { sql += ' AND date>=?'; a.push(o.start); }
    if (o.end) { sql += ' AND date<=?'; a.push(o.end); }
    return DB.q(sql + ' ORDER BY date, id', a);
  }
  return { rules, saveRule, deleteRule, occurrences, processedThrough, pending, apply, log };
})();

// ════════════════ 결산 보고서·예산·그래프 (services/reports.py) ════════════════
const Rep = (() => {
  const Row = (kind, group, label, code, values) => ({ kind, group, label, code: code || '', values: values || [] });

  function sumByCode(lid, start, end) {
    const out = {};
    for (const r of DB.q('SELECT code, SUM(income) AS inc, SUM(expense) AS exp FROM entry WHERE ledger_id=? AND date BETWEEN ? AND ? GROUP BY code', [lid, start, end])) {
      out[r.code] = L.signedAmount(r.code, r.inc, r.exp);
    }
    return out;
  }
  /** [수입계, 지출계] — 0으로 시작하는 계정 = 수입 */
  function incomeExpense(lid, start, end) {
    let inc = 0, exp = 0;
    for (const [code, v] of Object.entries(sumByCode(lid, start, end))) { if (U.isIncomeCode(code)) inc += v; else exp += v; }
    return [inc, exp];
  }
  const sortStr = arr => arr.slice().sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));

  /** [[대분류코드, 대분류명, [[code, 이름], ...]]] — 내역에만 있는 코드도 포함 */
  function structure(lid, extraCodes) {
    const gmap = L.groupMap(lid);
    const cats = L.categories(lid);
    const known = new Set(cats.map(c => c.code));
    const byGroup = {};
    for (const c of cats) (byGroup[c.code.slice(0, 1)] = byGroup[c.code.slice(0, 1)] || []).push([c.code, c.name]);
    for (const code of sortStr([...new Set(extraCodes || [])].filter(c => !known.has(c)))) {
      const g = code ? code.slice(0, 1) : '?';
      (byGroup[g] = byGroup[g] || []).push([code, code ? `(미분류 ${code})` : '(미분류)']);
    }
    let order = L.groups(lid).map(g => g.code);
    order = order.concat(sortStr(Object.keys(byGroup).filter(g => !order.includes(g))));
    return order.filter(g => (byGroup[g] && byGroup[g].length) || g in gmap)
      .map(g => [g, g in gmap ? gmap[g] : `(분류 ${g})`, byGroup[g] || []]);
  }
  /** columnsData: code → [값 x ncols]. 대분류별 소계 포함 행 목록 */
  function build(lid, columnsData, ncols, extraCodes) {
    const rows = [];
    for (const [g, gname, cats] of structure(lid, extraCodes)) {
      let sub = new Array(ncols).fill(0);
      for (const [code, name] of cats) {
        const vals = columnsData[code] || new Array(ncols).fill(0);
        rows.push(Row('cat', gname, name, code, vals.slice()));
        sub = sub.map((a, i) => a + (vals[i] || 0));
      }
      if (cats.length) rows.push(Row('subtotal', gname, '소 계', g, sub));
    }
    return rows;
  }
  const settleDay = () => parseInt(DB.getMeta('settle_day', 1) || 1, 10) || 1;
  const mmdd = s => s.slice(5, 10);

  function monthly(lid, y, m, sd) {
    sd = sd || 1;
    const [py, pm] = U.addMonths(y, m, -1), [ny, nm] = U.addMonths(y, m, 1);
    const pPrev = U.settlePeriod(py, pm, sd), pCur = U.settlePeriod(y, m, sd);
    const prev = sumByCode(lid, ...pPrev), cur = sumByCode(lid, ...pCur);
    const bCur = budgets(lid, U.ym(y, m)), bNext = budgets(lid, U.ym(ny, nm));
    const codes = new Set([...Object.keys(prev), ...Object.keys(cur), ...Object.keys(bCur), ...Object.keys(bNext)]);
    const data = {};
    for (const c of codes) data[c] = [prev[c] || 0, cur[c] || 0, (cur[c] || 0) - (prev[c] || 0), bCur[c] || 0, bNext[c] || 0];
    const rows = build(lid, data, 5, codes);
    const carryPrev = L.balanceBefore(lid, pPrev[0]), carryCur = L.balanceBefore(lid, pCur[0]);
    const [ip, ep] = incomeExpense(lid, ...pPrev), [ic, ec] = incomeExpense(lid, ...pCur);
    const bsum = (b, inc) => U.sum(Object.entries(b).filter(([c]) => U.isIncomeCode(c) === inc).map(([, v]) => v));
    const bi = bsum(bCur, true), be = bsum(bCur, false), ni = bsum(bNext, true), ne = bsum(bNext, false);
    rows.push(Row('footer', '', '전월 이월금', '', [carryPrev, carryCur, carryCur - carryPrev, null, null]),
      Row('footer', '', '수입계', '', [ip, ic, ic - ip, bi, ni]),
      Row('footer', '', '지출계', '', [ep, ec, ec - ep, be, ne]),
      Row('footer', '', '잔액', '', [carryPrev + ip - ep, carryCur + ic - ec, (carryCur + ic - ec) - (carryPrev + ip - ep), bi - be, ni - ne]));
    const fmt = p => `${mmdd(p[0])}~${mmdd(p[1])}`;
    return { title: `${y}년 ${m}월 결산 보고서`,
      columns: [`지난달 결산\n(${fmt(pPrev)})`, `이달의 결산\n(${fmt(pCur)})`, '증감\n(이달-지난달)', '이번달 예산', '다음달 예산'],
      rows, periods: [pPrev, pCur, null, null, null], note: `결산일 ${sd}일 기준` };
  }

  function yearly(lid, y, sd) {
    sd = sd || 1;
    const periods = [];
    for (let m = 1; m <= 12; m++) periods.push(U.settlePeriod(y, m, sd));
    const sums = periods.map(p => sumByCode(lid, ...p));
    const codes = new Set(sums.flatMap(s => Object.keys(s)));
    const data = {};
    for (const c of codes) { const v = sums.map(s => s[c] || 0); data[c] = v.concat([U.sum(v)]); }
    const rows = build(lid, data, 13, codes);
    const carry = L.balanceBefore(lid, periods[0][0]);
    const ie = periods.map(p => incomeExpense(lid, ...p));
    let bal = carry;
    const bals = ie.map(([i, e]) => (bal += i - e));
    const carries = [carry].concat(bals.slice(0, -1));
    rows.push(Row('footer', '', '전기 이월', '', carries.concat([carry])),
      Row('footer', '', '수입계', '', ie.map(x => x[0]).concat([U.sum(ie.map(x => x[0]))])),
      Row('footer', '', '지출계', '', ie.map(x => x[1]).concat([U.sum(ie.map(x => x[1]))])),
      Row('footer', '', '잔액', '', bals.concat([bals[bals.length - 1]])));
    const cols = [];
    for (let m = 1; m <= 12; m++) cols.push(`${m}월`);
    return { title: `${y}년 결산 보고서`, columns: cols.concat(['합계']), rows, periods: periods.concat([null]),
      note: `결산일 ${sd}일 기준 · 전기 이월 = 그 기간 시작 전까지의 잔액` };
  }

  function daily(lid, y, m) {
    const n = U.monthEnd(y, m);
    const days = [];
    for (let d = 1; d <= n; d++) days.push(U.iso(y, m, d));
    const sums = days.map(d => sumByCode(lid, d, d));
    const codes = new Set(sums.flatMap(s => Object.keys(s)));
    const data = {};
    for (const c of codes) { const v = sums.map(s => s[c] || 0); data[c] = v.concat([U.sum(v)]); }
    const rows = build(lid, data, n + 1, codes);
    const carry = L.balanceBefore(lid, days[0]);
    const ie = days.map(d => incomeExpense(lid, d, d));
    let ci2 = 0, ce = 0;
    const cumI = [], cumE = [], bals = [];
    for (const [i, e] of ie) { ci2 += i; ce += e; cumI.push(ci2); cumE.push(ce); bals.push(carry + ci2 - ce); }
    rows.push(Row('footer', '', '수입계', '', ie.map(x => x[0]).concat([ci2])),
      Row('footer', '', '수입누계', '', cumI.concat([ci2])),
      Row('footer', '', '지출계', '', ie.map(x => x[1]).concat([ce])),
      Row('footer', '', '지출누계', '', cumE.concat([ce])),
      Row('footer', '', '전월 이월금', '', [carry].concat(new Array(n - 1).fill(null), [carry])),
      Row('footer', '', '잔액', '', bals.concat([bals[bals.length - 1]])));
    return { title: `${y}년 ${m}월 일일결산 보고서`, columns: days.map(d => `${Number(d.slice(8))}일`).concat(['합계']),
      rows, periods: days.map(d => [d, d]).concat([[days[0], days[days.length - 1]]]), note: '' };
  }

  function custom(lid, start, end) {
    const first = DB.val('SELECT MIN(date) AS v FROM entry WHERE ledger_id=?', [lid]) || start;
    const last = DB.val('SELECT MAX(date) AS v FROM entry WHERE ledger_id=?', [lid]) || end;
    const y = Number(start.slice(0, 4));
    const periods = [[start, end], [U.iso(y, 1, 1), U.iso(y, 12, 31)], [String(first).slice(0, 10), String(last).slice(0, 10)]];
    const sums = periods.map(p => sumByCode(lid, ...p));
    const codes = new Set(sums.flatMap(s => Object.keys(s)));
    const data = {};
    for (const c of codes) data[c] = sums.map(s => s[c] || 0);
    const rows = build(lid, data, 3, codes);
    const ie = periods.map(p => incomeExpense(lid, ...p));
    rows.push(Row('footer', '', '수입계', '', ie.map(x => x[0])), Row('footer', '', '지출계', '', ie.map(x => x[1])),
      Row('footer', '', '수입계 - 지출계', '', ie.map(x => x[0] - x[1])));
    const yy = s => s.slice(2);
    return { title: `${start} ~ ${end} 결산 보고서`, columns: [`${yy(start)} ~ ${yy(end)}`, `${y}년 결산`, '전체 합계'],
      rows, periods, note: '' };
  }

  // ── 예산 ──
  function budgets(lid, ymv) {
    const out = {};
    for (const r of DB.q('SELECT code, amount FROM budget WHERE ledger_id=? AND ym=?', [lid, ymv])) out[r.code] = r.amount;
    return out;
  }
  function setBudget(lid, ymv, code, amount) {
    if (amount) DB.run('INSERT OR REPLACE INTO budget VALUES(?,?,?,?)', [lid, ymv, code, parseInt(amount, 10)]);
    else DB.run('DELETE FROM budget WHERE ledger_id=? AND ym=? AND code=?', [lid, ymv, code]);
  }
  function budgetYear(lid, y) {
    const yms = [];
    for (let m = 1; m <= 12; m++) yms.push(U.ym(y, m));
    const bs = yms.map(v => budgets(lid, v));
    const codes = new Set(bs.flatMap(b => Object.keys(b)));
    const data = {};
    for (const c of codes) { const v = bs.map(b => b[c] || 0); data[c] = v.concat([U.sum(v)]); }
    const rows = build(lid, data, 13, codes);
    const carry = L.balanceBefore(lid, U.iso(y, 1, 1));
    const inc = bs.map(b => U.sum(Object.entries(b).filter(([c]) => U.isIncomeCode(c)).map(([, v]) => v)));
    const exp = bs.map(b => U.sum(Object.entries(b).filter(([c]) => !U.isIncomeCode(c)).map(([, v]) => v)));
    let bal = carry;
    const bals = inc.map((i, k) => (bal += i - exp[k]));
    rows.push(Row('footer', '', '전년도 이월금액', '', [carry].concat(new Array(11).fill(null), [carry])),
      Row('footer', '', '수입계', '', inc.concat([U.sum(inc)])),
      Row('footer', '', '지출계', '', exp.concat([U.sum(exp)])),
      Row('footer', '', '잔액', '', bals.concat([bals[bals.length - 1]])));
    const cols = [];
    for (let m = 1; m <= 12; m++) cols.push(`${m}월 예산`);
    return { title: `${y}년 예산 보고서`, columns: cols.concat(['합계']), rows, periods: yms.concat([null]),
      note: '소분류 칸을 눌러 예산 금액을 입력하세요' };
  }

  // ── 그래프 ──
  /** {labels, series: [[이름, [값...]]]} — group 없음=대분류별, group=그 대분류의 소분류별, code=그 소분류. month 지정=일별 */
  function graphSeries(lid, y, o) {
    o = o || {};
    let periods, labels;
    if (o.month) {
      const n = U.monthEnd(y, o.month);
      periods = []; labels = [];
      for (let d = 1; d <= n; d++) { const s = U.iso(y, o.month, d); periods.push([s, s]); labels.push(String(d)); }
    } else {
      periods = []; labels = [];
      for (let m = 1; m <= 12; m++) { periods.push(U.settlePeriod(y, m, o.settleDay || 1)); labels.push(`${m}월`); }
    }
    const sums = periods.map(p => sumByCode(lid, ...p));
    const gmap = L.groupMap(lid), cmap = L.categoryMap(lid);
    const series = [];
    if (o.code) {
      series.push([`(${o.code}) ${L.codeLabel(cmap, o.code)}`, sums.map(s => s[o.code] || 0)]);
    } else if (o.group !== undefined && o.group !== null) {
      const codes = sortStr([...new Set([...sums.flatMap(s => Object.keys(s)), ...Object.keys(cmap)].filter(c => c.slice(0, 1) === o.group))]);
      for (const c of codes) series.push([`(${c}) ${L.codeLabel(cmap, c)}`, sums.map(s => s[c] || 0)]);
    } else {
      const gs = [...new Set([...sums.flatMap(s => Object.keys(s).map(c => c.slice(0, 1))), ...Object.keys(gmap)])]
        .sort((a, b) => ((a in gmap ? 0 : 1) - (b in gmap ? 0 : 1)) || (a < b ? -1 : a > b ? 1 : 0));
      for (const g of gs) {
        series.push([`(${g}) ${g in gmap ? gmap[g] : '?'}`,
          sums.map(s => U.sum(Object.entries(s).filter(([c]) => c.slice(0, 1) === g).map(([, v]) => v)))]);
      }
    }
    return { labels, series };
  }

  return { sumByCode, incomeExpense, monthly, yearly, daily, custom, budgets, setBudget, budgetYear, graphSeries, settleDay };
})();

// ════════════════ 자산 (services/assets.py) ════════════════
const A = (() => {
  const KIND_LABEL = { bank: '은행통장', securities: '증권', insurance: '보험', property: '부동산/기타' };
  const PROPERTY_TYPES = ['아파트', '단독/빌라', '토지/임야', '상가/건물', '공장/창고', '기타자산'];
  const OTHER_ASSET = PROPERTY_TYPES.length - 1;
  const INSURANCE_STATUS = ['정상', '실효'];
  const INSURANCE_CLASS = ['저축성', '보장성'];
  const INSURANCE_TYPES = ['암보험', '질병보험', '재해보험', '상해보험', '기타보험'];
  const INSURANCE_PAY = ['월납', '3월납', '6월납', '연납', '일시납'];
  const BILL_MONTHS = { '-2': '전전월', '-1': '전월', '0': '당월' };
  const ch = list => 'choice:' + list.join('|');
  // (키, 이름, 형식). 형식: text/money/date/int/choice:<목록>/memo/password/active  (* = 꼭 입력)
  const FIELDS = {
    bank: [['company', '은행명', 'text*'], ['name', '통장명', 'text*'], ['owner', '예금주', 'text'],
      ['number', '계좌번호', 'text'], ['opening', '초기 잔액', 'money'], ['x.password', '비밀번호', 'password'],
      ['x.issued', '발행일', 'text'], ['x.maturity', '만기일', 'text'], ['active', '사용여부', 'active'], ['memo', '비고', 'memo']],
    securities: [['company', '증권사명', 'text*'], ['name', '계좌이름', 'text*'], ['number', '계좌번호', 'text'],
      ['owner', '소유주', 'text'], ['deposit', '추정 예수금', 'money'], ['valuation', '평가금액', 'money'],
      ['x.valued_on', '최종 평가일', 'date'], ['memo', '비고', 'memo']],
    insurance: [['company', '보험사명', 'text*'], ['name', '보험 상품명', 'text*'], ['number', '보험증권번호', 'text'],
      ['owner', '계약자', 'text'], ['x.insured', '피보험자', 'text'], ['x.contract_date', '계약일', 'date'],
      ['x.maturity', '만기일', 'date'], ['x.status', '계약상태', ch(INSURANCE_STATUS)],
      ['x.class', '보험구분', ch(INSURANCE_CLASS)], ['x.pay_method', '납입방법', ch(INSURANCE_PAY)],
      ['x.type', '보험종류', ch(INSURANCE_TYPES)], ['x.total_count', '만기 납입횟수', 'int'], ['x.paid_count', '납입횟수', 'int'],
      ['x.paid_total', '납입보험료 누계', 'money'], ['x.agent', '담당자 및 연락처', 'text'], ['memo', '비고', 'memo']],
    property: [['x.ptype', '구분', ch(PROPERTY_TYPES)], ['name', '자산명', 'text*'], ['owner', '소유주/임차인', 'text'],
      ['x.acquired', '취득/임차일자', 'date'], ['valuation', '취득/평가금액', 'money'], ['x.valued_on', '최종 평가일', 'date'],
      ['loan', '대출금액', 'money'], ['memo', '비고', 'memo']],
  };
  const CARD_FIELDS = [['company', '카드사명', 'text*'], ['name', '카드명', 'text*'], ['number', '카드번호', 'text'],
    ['x.password', '카드 비밀번호', 'password'], ['x.valid_ym', '유효기간(YYYY-MM)', 'text'],
    ['pay_day', '결제일', 'int'], ['bill_from_month', '청구기간 시작(월)', 'billmonth'],
    ['bill_from_day', '청구기간 시작(일)', 'int'], ['bill_to_month', '청구기간 끝(월)', 'billmonth'],
    ['bill_to_day', '청구기간 끝(일)', 'int'], ['bank_account_id', '결제 통장', 'bank'],
    ['x.limit', '카드사용한도', 'money'], ['x.cash_limit', '현금서비스 한도', 'money'],
    ['x.loan_limit', '대출한도', 'money'], ['x.issued', '발행일', 'date'], ['memo', '비고', 'memo']];
  const ACCOUNT_COLS = new Set(['sort', 'name', 'company', 'owner', 'number', 'opening', 'valuation', 'loan', 'deposit', 'active', 'memo']);
  const CARD_COLS = new Set(['sort', 'company', 'name', 'number', 'pay_day', 'bill_from_month', 'bill_from_day', 'bill_to_month',
    'bill_to_day', 'bank_account_id', 'memo']);

  function split(values, allowed) {
    const cols = {}, extra = {};
    for (const [k, v] of Object.entries(values)) {
      if (k.startsWith('x.')) extra[k.slice(2)] = v;
      else if (allowed.has(k)) cols[k] = v;
    }
    return [cols, extra];
  }
  const parseExtra = s => { try { return JSON.parse(s || '{}') || {}; } catch (_) { return {}; } };
  function mergeExtra(row) {
    const d = Object.assign({}, row);
    const x = parseExtra(d.extra);
    delete d.extra;
    for (const [k, v] of Object.entries(x)) d['x.' + k] = v;
    return d;
  }

  // ── 통장·증권·보험·부동산 ──
  const accounts = kind => (kind ? DB.q('SELECT * FROM account WHERE kind=? ORDER BY sort, id', [kind])
    : DB.q('SELECT * FROM account ORDER BY kind, sort, id'));

  function saveAccount(kind, values, aid) {
    const [cols, extra] = split(values, ACCOUNT_COLS);
    if (aid) {
      const old = parseExtra((DB.one('SELECT extra FROM account WHERE id=?', [aid]) || {}).extra);
      Object.assign(old, extra);
      cols.extra = JSON.stringify(old);
      const keys = Object.keys(cols);
      DB.run(`UPDATE account SET ${keys.map(k => k + '=?').join(',')} WHERE id=?`, keys.map(k => cols[k]).concat([aid]));
      return aid;
    }
    cols.extra = JSON.stringify(extra);
    cols.kind = kind;
    if (cols.sort === undefined) cols.sort = DB.val('SELECT COALESCE(MAX(sort),0)+1 AS v FROM account WHERE kind=?', [kind]);
    const keys = Object.keys(cols);
    return DB.run(`INSERT INTO account(${keys.join(',')}) VALUES(${keys.map(() => '?').join(',')})`, keys.map(k => cols[k])).lastId;
  }
  const deleteAccount = aid => DB.run('DELETE FROM account WHERE id=?', [aid]);

  function move(table, rid, delta, where, args) {
    if (!['account', 'card', 'anniversary', 'memo'].includes(table)) return;
    const ids = DB.q(`SELECT id FROM ${table} WHERE ${where || '1=1'} ORDER BY sort, id`, args || []).map(r => r.id);
    const i = ids.indexOf(rid), j = i + delta;
    if (i < 0 || j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    DB.tx(() => ids.forEach((r, k) => DB.run(`UPDATE ${table} SET sort=? WHERE id=?`, [k, r])));
  }

  function accountBalance(aid, upto) {
    const a = DB.one('SELECT opening FROM account WHERE id=?', [aid]);
    let sql = 'SELECT COALESCE(SUM(deposit-withdraw),0) AS v FROM account_tx WHERE account_id=?';
    const args = [aid];
    if (upto) { sql += ' AND date<=?'; args.push(upto); }
    return (a ? a.opening : 0) + DB.val(sql, args);
  }
  /** 거래 + 누적 잔액 */
  function accountTxs(aid, start, end) {
    const a = DB.one('SELECT * FROM account WHERE id=?', [aid]);
    const rows = DB.q('SELECT * FROM account_tx WHERE account_id=? ORDER BY date, id', [aid]);
    let bal = a && a.kind === 'bank' ? a.opening : 0;
    const out = [];
    for (const r of rows) {
      bal += r.deposit - r.withdraw;
      if ((!start || r.date >= start) && (!end || r.date <= end)) out.push([r, bal]);
    }
    return out;
  }
  /** 거래 저장. ledgerId·code 를 주면 '장부에도 동시저장' (입금→수입, 출금→지출) */
  function addTx(aid, t, ledgerId, code) {
    return DB.tx(() => {
      let eid = null;
      if (ledgerId && code) {
        const a = DB.one('SELECT name FROM account WHERE id=?', [aid]);
        eid = L.addEntry(ledgerId, { date: t.date, item: t.summary || a.name, income: t.deposit || 0, expense: t.withdraw || 0,
          code, memo: t.memo || '' }, `account:${aid}`);
      }
      return DB.run('INSERT INTO account_tx(account_id,date,summary,deposit,withdraw,memo,entry_id) VALUES(?,?,?,?,?,?,?)',
        [aid, t.date, t.summary || '', parseInt(t.deposit || 0, 10), parseInt(t.withdraw || 0, 10), t.memo || '', eid]).lastId;
    });
  }
  const updateTx = (tid, t) => DB.run('UPDATE account_tx SET date=?,summary=?,deposit=?,withdraw=?,memo=? WHERE id=?',
    [t.date, t.summary || '', parseInt(t.deposit || 0, 10), parseInt(t.withdraw || 0, 10), t.memo || '', tid]);
  function deleteTx(tid, withEntry) {
    DB.tx(() => {
      const r = DB.one('SELECT entry_id FROM account_tx WHERE id=?', [tid]);
      if (withEntry && r && r.entry_id) DB.run('DELETE FROM entry WHERE id=?', [r.entry_id]);
      DB.run('DELETE FROM account_tx WHERE id=?', [tid]);
    });
  }

  // ── 신용카드 ──
  const cards = () => DB.q('SELECT * FROM card ORDER BY sort, id');
  function saveCard(values, cid) {
    const [cols, extra] = split(values, CARD_COLS);
    if (cid) {
      const old = parseExtra((DB.one('SELECT extra FROM card WHERE id=?', [cid]) || {}).extra);
      Object.assign(old, extra);
      cols.extra = JSON.stringify(old);
      const keys = Object.keys(cols);
      DB.run(`UPDATE card SET ${keys.map(k => k + '=?').join(',')} WHERE id=?`, keys.map(k => cols[k]).concat([cid]));
      return cid;
    }
    cols.extra = JSON.stringify(extra);
    if (cols.sort === undefined) cols.sort = DB.val('SELECT COALESCE(MAX(sort),0)+1 AS v FROM card');
    const keys = Object.keys(cols);
    return DB.run(`INSERT INTO card(${keys.join(',')}) VALUES(${keys.map(() => '?').join(',')})`, keys.map(k => cols[k])).lastId;
  }
  const deleteCard = cid => DB.run('DELETE FROM card WHERE id=?', [cid]);

  function billingWindow(card, payY, payM) {
    const [fy, fm] = U.addMonths(payY, payM, card.bill_from_month);
    const [ty, tm] = U.addMonths(payY, payM, card.bill_to_month);
    return [U.clampDay(fy, fm, card.bill_from_day), U.clampDay(ty, tm, card.bill_to_day)];
  }
  /** 거래일이 속한 청구기간으로 결제일 계산 */
  function payDateFor(card, purchase) {
    const [py, pm] = U.parts(purchase);
    for (let k = -1; k < 5; k++) {
      const [y, m] = U.addMonths(py, pm, k);
      const [lo, hi] = billingWindow(card, y, m);
      if (lo <= purchase && purchase <= hi) return U.clampDay(y, m, card.pay_day);
    }
    const [y, m] = U.addMonths(py, pm, 1);
    return U.clampDay(y, m, card.pay_day);
  }
  const divmod = (a, b) => { const q = Math.floor(a / b); return [q, a - q * b]; };
  /** 사용금액·수수료는 전체 금액, 할부개월로 나눠 회차별로 저장 */
  function addCardPurchase(cid, date, summary, total, feeTotal, months, payDate, memo) {
    return DB.tx(() => {
      const card = DB.one('SELECT * FROM card WHERE id=?', [cid]);
      months = Math.max(1, parseInt(months || 1, 10));
      const first = payDate || payDateFor(card, date);
      const [base, rem] = divmod(parseInt(total, 10), months);
      const [fbase, frem] = divmod(parseInt(feeTotal || 0, 10), months);
      const gid = DB.val('SELECT COALESCE(MAX(group_id),0)+1 AS v FROM card_tx');
      const [fy, fm, fd] = U.parts(first);
      for (let k = 0; k < months; k++) {
        const [y, m] = U.addMonths(fy, fm, k);
        const pd = U.clampDay(y, m, k === 0 ? fd : card.pay_day);
        DB.run('INSERT INTO card_tx(card_id,group_id,date,summary,total,fee_total,months,seq,amount,fee,pay_date,memo) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
          [cid, gid, date, summary, parseInt(total, 10), parseInt(feeTotal || 0, 10), months, k + 1,
            base + (k === 0 ? rem : 0), fbase + (k === 0 ? frem : 0), pd, memo || '']);
      }
      return gid;
    });
  }
  const deleteCardGroup = (cardId, groupId) => DB.run('DELETE FROM card_tx WHERE card_id=? AND group_id=?', [cardId, groupId]);
  /** ym='YYYY-MM' 결제월 기준. paid: null=모두, 0=미결제, 1=결제완료 */
  function cardTxs(cid, ymv, paid) {
    let sql = 'SELECT * FROM card_tx WHERE card_id=?';
    const a = [cid];
    if (ymv) { sql += ' AND substr(pay_date,1,7)=?'; a.push(ymv); }
    if (paid !== undefined && paid !== null) { sql += ' AND paid=?'; a.push(paid); }
    return DB.q(sql + ' ORDER BY pay_date, date, id', a);
  }
  function cardUnpaidTotal(cid, until) {
    let sql = 'SELECT COALESCE(SUM(amount+fee),0) AS v FROM card_tx WHERE paid=0';
    const a = [];
    if (cid) { sql += ' AND card_id=?'; a.push(cid); }
    if (until) { sql += ' AND pay_date<=?'; a.push(until); }
    return DB.val(sql, a);
  }
  /** 선택 회차 결제 처리. 통장·장부에 동시 기록 옵션 */
  function payCard(txIds, payDate, bankAccountId, ledgerId, code) {
    if (!txIds.length) return 0;
    return DB.tx(() => {
      const rows = DB.q(`SELECT t.*, c.name AS cname FROM card_tx t JOIN card c ON c.id=t.card_id WHERE t.id IN (${txIds.map(() => '?').join(',')}) AND t.paid=0`, txIds);
      if (!rows.length) return 0;
      const total = U.sum(rows.map(r => r.amount + r.fee));
      const cname = rows[0].cname;
      let atx = null, eid = null;
      if (bankAccountId) {
        atx = DB.run('INSERT INTO account_tx(account_id,date,summary,deposit,withdraw,memo) VALUES(?,?,?,?,?,?)',
          [bankAccountId, payDate, `${cname} 카드대금`, 0, total, '']).lastId;
      }
      if (ledgerId && code) {
        eid = L.addEntry(ledgerId, { date: payDate, item: `${cname} 카드대금`, expense: total, code }, 'card_pay');
      }
      for (const r of rows) DB.run('UPDATE card_tx SET paid=1, paid_entry_id=?, paid_account_tx_id=? WHERE id=?', [eid, atx, r.id]);
      return total;
    });
  }
  /** 결제 취소. 같은 결제로 처리된 회차도 함께 되돌리고, 그 결제로 남긴 통장·장부 기록도 지움 */
  function unpayCard(txIds) {
    if (!txIds.length) return 0;
    return DB.tx(() => {
      const rows = DB.q(`SELECT id, paid_entry_id, paid_account_tx_id FROM card_tx WHERE id IN (${txIds.map(() => '?').join(',')}) AND paid=1`, txIds);
      const ids = new Set(rows.map(r => r.id));
      for (const r of rows) {
        if (r.paid_entry_id || r.paid_account_tx_id) {
          for (const x of DB.q('SELECT id FROM card_tx WHERE paid=1 AND ((paid_entry_id IS NOT NULL AND paid_entry_id=?) OR (paid_account_tx_id IS NOT NULL AND paid_account_tx_id=?))',
            [r.paid_entry_id, r.paid_account_tx_id])) ids.add(x.id);
          if (r.paid_entry_id) DB.run('DELETE FROM entry WHERE id=?', [r.paid_entry_id]);
          if (r.paid_account_tx_id) DB.run('DELETE FROM account_tx WHERE id=?', [r.paid_account_tx_id]);
        }
      }
      for (const i of ids) DB.run('UPDATE card_tx SET paid=0, paid_entry_id=NULL, paid_account_tx_id=NULL WHERE id=?', [i]);
      return ids.size;
    });
  }

  // ── 자산 요약 ──
  function summary() {
    const s = { 예금: 0, 증권: 0, 부동산: 0, 기타: 0, 대출: 0, 카드: 0, 기타부채: 0 };
    for (const a of accounts()) {
      const x = parseExtra(a.extra);
      if (a.kind === 'bank' && a.active) s.예금 += accountBalance(a.id);
      else if (a.kind === 'securities') s.증권 += a.valuation;
      else if (a.kind === 'property') {
        if (parseInt(x.ptype || 0, 10) === OTHER_ASSET) { s.기타 += a.valuation; s.기타부채 += a.loan; }
        else { s.부동산 += a.valuation; s.대출 += a.loan; }
      }
    }
    s.카드 = cardUnpaidTotal();
    s.자산합계 = s.예금 + s.증권 + s.부동산 + s.기타;
    s.부채합계 = s.대출 + s.카드 + s.기타부채;
    s.순자산 = s.자산합계 - s.부채합계;
    return s;
  }

  return { KIND_LABEL, PROPERTY_TYPES, OTHER_ASSET, BILL_MONTHS, FIELDS, CARD_FIELDS, parseExtra, mergeExtra,
    accounts, saveAccount, deleteAccount, move, accountBalance, accountTxs, addTx, updateTx, deleteTx,
    cards, saveCard, deleteCard, billingWindow, payDateFor, addCardPurchase, deleteCardGroup, cardTxs,
    cardUnpaidTotal, payCard, unpayCard, summary };
})();

// ════════════════ 일정·기념일·주소록·일기·메모 (services/calendar_svc.py) ════════════════
const Cal = (() => {
  const WEEKDAY_SETS = { '월, 수, 금': [0, 2, 4], '화, 목': [1, 3], '월 ~ 금': [0, 1, 2, 3, 4], '토, 일': [5, 6] };
  const ORDINALS = ['첫 번째', '두 번째', '세 번째', '네 번째', '마지막'];
  const WEEKDAY_NAMES = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일'];

  /** nth: 0~3 = 첫~넷째, 4 = 마지막. wd: 0=월 */
  function nthWeekday(y, m, nth, wd) {
    if (nth === 4) {
      const d = U.iso(y, m, U.monthEnd(y, m));
      return U.addDays(d, -(((U.weekday(d) - wd) % 7 + 7) % 7));
    }
    let d = U.iso(y, m, 1);
    d = U.addDays(d, ((wd - U.weekday(d)) % 7 + 7) % 7);
    d = U.addDays(d, nth * 7);
    return Number(d.slice(5, 7)) === m ? d : null;
  }
  const validDate = (y, m, d) => (m >= 1 && m <= 12 && d >= 1 && d <= U.monthEnd(y, m) ? U.iso(y, m, d) : null);

  /** rule: {type:'none'} | {type:'every',n,unit:'일|주|월|년'} | {type:'weekdays',set} | {type:'nth',nth,weekday,n} */
  function expandRepeat(start, until, rule) {
    until = until || start;
    const t = (rule && rule.type) || 'none';
    const out = [];
    if (t === 'none' || until < start) return [start];
    const [sy, sm, sd] = U.parts(start);
    if (t === 'every') {
      const n = Math.max(1, parseInt(rule.n || 1, 10)), unit = rule.unit || '일';
      for (let k = 0; k <= 5000; k++) {
        let d;
        if (unit === '일') d = U.addDays(start, n * k);
        else if (unit === '주') d = U.addDays(start, 7 * n * k);
        else if (unit === '월') { const [y, m] = U.addMonths(sy, sm, n * k); d = validDate(y, m, sd); if (!d) continue; }
        else { d = validDate(sy + n * k, sm, sd); if (!d) continue; }
        if (d > until) break;
        out.push(d);
      }
    } else if (t === 'weekdays') {
      const days = WEEKDAY_SETS[rule.set] || [];
      for (let d = start; d <= until; d = U.addDays(d, 1)) if (days.includes(U.weekday(d))) out.push(d);
    } else if (t === 'nth') {
      const n = Math.max(1, parseInt(rule.n || 1, 10));
      let y = sy, m = sm;
      while (U.iso(y, m, 1) <= until) {
        const d = nthWeekday(y, m, parseInt(rule.nth, 10), parseInt(rule.weekday, 10));
        if (d && start <= d && d <= until) out.push(d);
        [y, m] = U.addMonths(y, m, n);
      }
    }
    return out;
  }
  function uuidHex() {
    if (window.GagyebuNative && GagyebuNative.randomHex) return GagyebuNative.randomHex(16);
    let s = '';
    for (let i = 0; i < 32; i++) s += Math.floor(Math.random() * 16).toString(16);
    return s;
  }
  function addSchedule(date, text, remindDays, bg, fg, repeat, until) {
    const dates = expandRepeat(date, until, repeat || { type: 'none' });
    const gid = dates.length > 1 ? uuidHex() : null;
    DB.tx(() => dates.forEach(d => DB.run('INSERT INTO schedule(date,text,remind_days,bg,fg,group_id) VALUES(?,?,?,?,?,?)',
      [d, text, parseInt(remindDays || 0, 10), bg || null, fg || null, gid])));
    return dates.length;
  }
  const updateSchedule = (sid, text, remindDays, bg, fg) => DB.run('UPDATE schedule SET text=?, remind_days=?, bg=?, fg=? WHERE id=?',
    [text, parseInt(remindDays || 0, 10), bg || null, fg || null, sid]);
  const deleteSchedule = sid => DB.run('DELETE FROM schedule WHERE id=?', [sid]);
  const deleteScheduleGroup = gid => DB.run('DELETE FROM schedule WHERE group_id=?', [gid]).changes;
  const deleteScheduleRange = (start, end) => DB.run('DELETE FROM schedule WHERE date BETWEEN ? AND ?', [start, end]).changes;
  function schedules(start, end) {
    const out = {};
    for (const r of DB.q('SELECT * FROM schedule WHERE date BETWEEN ? AND ? ORDER BY date, id', [start, end])) (out[r.date] = out[r.date] || []).push(r);
    return out;
  }
  /** '미리 알려주기 N일 전' 이 걸린 일정 중 오늘 알려줄 것 */
  function reminders(today) {
    today = today || U.today();
    return DB.q('SELECT * FROM schedule WHERE remind_days>0 AND date>=? ORDER BY date', [today])
      .filter(r => U.addDays(r.date, -r.remind_days) <= today);
  }

  // ── 기념일 ──
  const anniversaries = () => DB.q('SELECT * FROM anniversary ORDER BY sort, id');
  function saveAnniversary(v, aid) {
    const vals = [v.title, parseInt(v.month, 10), parseInt(v.day, 10), v.year ? parseInt(v.year, 10) : null, v.lunar ? 1 : 0, v.holiday ? 1 : 0];
    if (aid) { DB.run('UPDATE anniversary SET title=?,month=?,day=?,year=?,lunar=?,holiday=? WHERE id=?', vals.concat([aid])); return aid; }
    const sort = DB.val('SELECT COALESCE(MAX(sort),0)+1 AS v FROM anniversary');
    return DB.run('INSERT INTO anniversary(title,month,day,year,lunar,holiday,sort) VALUES(?,?,?,?,?,?,?)', vals.concat([sort])).lastId;
  }
  const deleteAnniversary = aid => DB.run('DELETE FROM anniversary WHERE id=?', [aid]);
  /** {date: [[제목, 휴일여부]]} — 음력 기념일은 해당 양력 날짜로 변환 */
  function anniversariesBetween(start, end) {
    const out = {};
    const sy = Number(start.slice(0, 4)), ey = Number(end.slice(0, 4));
    for (const a of anniversaries()) {
      const years = [];
      if (a.year) years.push(a.year); else for (let y = sy - 1; y <= ey; y++) years.push(y);
      for (const y of years) {
        let d = null;
        if (a.lunar) d = Lunar.lunarToSolar(y, a.month, a.day, false);
        else if (a.month >= 1 && a.month <= 12) {
          const last = U.monthEnd(y, a.month);
          const day = Math.min(a.day, 31);
          d = day <= last ? U.iso(y, a.month, day) : (a.day >= 28 ? U.iso(y, a.month, last) : null);
        }
        if (d && start <= d && d <= end) (out[d] = out[d] || []).push([a.title, !!a.holiday]);
      }
    }
    return out;
  }
  /** 일요일 시작 6주 x 7일 */
  function monthGrid(y, m) {
    const first = U.iso(y, m, 1);
    const start = U.addDays(first, -((U.weekday(first) + 1) % 7));
    const weeks = [];
    for (let w = 0; w < 6; w++) { const row = []; for (let d = 0; d < 7; d++) row.push(U.addDays(start, w * 7 + d)); weeks.push(row); }
    return weeks;
  }

  // ── 단순 목록 (주소록·일기장·메모장) ──
  const TABLES = { contact: true, diary: true, memo: true };
  function simpleList(table, order, where, args) {
    if (!TABLES[table]) throw new Error('bad table');
    return DB.q(`SELECT * FROM ${table}${where ? ' WHERE ' + where : ''} ORDER BY ${order || 'id'}`, args || []);
  }
  function simpleSave(table, values, rid) {
    if (!TABLES[table]) throw new Error('bad table');
    const keys = Object.keys(values).filter(k => /^[a-z_]+$/.test(k));
    if (rid) { DB.run(`UPDATE ${table} SET ${keys.map(k => k + '=?').join(',')} WHERE id=?`, keys.map(k => values[k]).concat([rid])); return rid; }
    return DB.run(`INSERT INTO ${table}(${keys.join(',')}) VALUES(${keys.map(() => '?').join(',')})`, keys.map(k => values[k])).lastId;
  }
  function simpleDelete(table, rid) { if (TABLES[table]) DB.run(`DELETE FROM ${table} WHERE id=?`, [rid]); }

  return { WEEKDAY_SETS, ORDINALS, WEEKDAY_NAMES, nthWeekday, expandRepeat, addSchedule, updateSchedule, deleteSchedule,
    deleteScheduleGroup, deleteScheduleRange, schedules, reminders, anniversaries, saveAnniversary, deleteAnniversary,
    anniversariesBetween, monthGrid, simpleList, simpleSave, simpleDelete };
})();

// ════════════════ CSV·암호 (services/backup.py, util.py) ════════════════
const Bk = (() => {
  const CSV_HEADER = ['날짜', '품목', '수입', '지출', '계정코드', '계정과목', '메모'];
  function csvCell(v) {
    const s = v === null || v === undefined ? '' : String(v);
    return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  /** 엑셀에서 한글이 깨지지 않게 BOM + CRLF (PC판 utf-8-sig 와 같음) */
  const toCsv = (header, rows) => '\ufeff' + [header].concat(rows).map(r => r.map(csvCell).join(',')).join('\r\n') + '\r\n';

  function parseCsv(text) {
    text = text.replace(/^\ufeff/, '');
    const rows = [];
    let row = [], cell = '', q = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (q) {
        if (c === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += c;
      } else if (c === '"') q = true;
      else if (c === ',') { row.push(cell); cell = ''; }
      else if (c === '\n' || c === '\r') {
        if (c === '\r' && text[i + 1] === '\n') i++;
        row.push(cell); rows.push(row); row = []; cell = '';
      } else cell += c;
    }
    if (cell !== '' || row.length) { row.push(cell); rows.push(row); }
    return rows;
  }
  function toDate(s) {
    s = s.trim().replace(/[./]/g, '-');
    if (/^\d{8}$/.test(s)) s = `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6)}`;
    s = s.slice(0, 10);
    if (!U.isValidIso(s)) throw new Error('bad date');
    return s;
  }
  /** 날짜, 품목, 수입, 지출, 계정코드[, 계정과목, 메모] 순서의 CSV → [정상 행, 오류[(행번호, 내용)]] */
  function readEntriesCsv(text, validCodes) {
    let data = parseCsv(text);
    const rows = [], errors = [];
    if (data.length && data[0].length && ['날짜', 'date'].includes(data[0][0].trim())) data = data.slice(1);
    data.forEach((r0, k) => {
      const n = k + 2;
      if (!r0.some(c => c.trim())) return;
      const r = r0.concat(new Array(7).fill('')).slice(0, 7);
      let d, inc, exp;
      try { d = toDate(r[0]); } catch (_) { errors.push([n, `날짜 형식 오류: ${r[0]}`]); return; }
      try { inc = U.parseMoney(r[2]); exp = U.parseMoney(r[3]); } catch (_) { errors.push([n, `금액 오류: ${r[2]}, ${r[3]}`]); return; }
      const code = r[4].trim();
      if (!r[1].trim()) { errors.push([n, '품목이 비어 있음']); return; }
      if (!validCodes.has(code)) { errors.push([n, `없는 계정코드: ${code}`]); return; }
      if (!inc && !exp) { errors.push([n, '수입·지출이 모두 0']); return; }
      rows.push({ date: d, item: r[1].trim(), income: inc, expense: exp, code, memo: r[6].trim() });
    });
    return [rows, errors];
  }

  // ── 암호 (PC판과 같은 형식: pbkdf2$소금$해시) ──
  function pbkdf2(pw, salt) {
    const o = JSON.parse(GagyebuNative.pbkdf2(pw, salt, 120000));
    if (!o.ok) throw new Error(o.error);
    return o.hex;
  }
  function hashPassword(pw, salt) {
    salt = salt || GagyebuNative.randomHex(16);
    return `pbkdf2$${salt}$${pbkdf2(pw, salt)}`;
  }
  function checkPassword(pw, stored) {
    if (!stored) return true;
    const p = String(stored).split('$');
    if (p.length !== 3) return false;
    return hashPassword(pw, p[1]) === stored;
  }

  return { CSV_HEADER, toCsv, parseCsv, readEntriesCsv, hashPassword, checkPassword };
})();
