/* 1.8.0 에 더한 기능의 계산 (PC판 services/money.py·trash.py·catemoji.py 와 같은 규칙, devtools/compat 로 결과 비교):
   결제수단 · 큰돈 나눠 적기 · 외화 · 같은 곳 모아보기 · 주간 예산 · 주별 통계 · 월별 저축 추이 · 고정비 한눈에 ·
   한 달 전체 예산 · 달력 돈 일정 · 카드 실적 · 휴지통 · 카테고리 그림 */
'use strict';


// ════════════════ 결제수단 ════════════════
const Pay = (() => {
  const KINDS = [['cash', '현금'], ['card', '카드'], ['bank', '계좌이체'], ['pay', '간편결제']];
  /** 카드 이름: 회사 이름이 카드 이름에 없으면 앞에 붙임 */
  function cardLabel(c) {
    const name = (c.name || '').trim(), company = (c.company || '').trim();
    return company && !name.includes(company) ? `${company} ${name}`.trim() : (name || company || '카드');
  }
  function custom() {
    const v = DB.getJson('pay_custom', []);
    return Array.isArray(v) ? v.map(String).filter(x => x.trim()) : [];
  }
  /** 직접 만든 결제수단 이름들 (순서대로, 같은 것은 한 번) */
  function setCustom(names) {
    const base = KINDS.map(k => k[1]);
    const out = [];
    for (const n0 of names) {
      const n = String(n0 || '').trim().slice(0, 20);
      if (n && !out.includes(n) && !base.includes(n)) out.push(n);
    }
    DB.setJson('pay_custom', out);
    return out;
  }
  /** 직접 만든 결제수단 이름 바꾸기 — 그 이름으로 넣은 내역·자주 쓰는 내역·고정 수입·지출도 함께 (모든 가계부) */
  function renameCustom(old, nw) {
    nw = String(nw || '').trim().slice(0, 20);
    const names = custom();
    if (!nw || !names.includes(old) || nw === old) return names;
    if (names.includes(nw) || KINDS.some(k => k[1] === nw)) throw new Error('같은 이름의 결제수단이 있습니다');
    names[names.indexOf(old)] = nw;
    DB.tx(() => {
      DB.setJson('pay_custom', names);
      for (const t of ['entry', 'favorite', 'recurring']) DB.run(`UPDATE ${t} SET pay=? WHERE pay=?`, [`etc:${nw}`, `etc:${old}`]);
    });
    return names;
  }
  /** [[값, 이름]] — 기본 4가지 → 자산에 넣은 카드 → 직접 만든 것 */
  function options() {
    const out = KINDS.slice();
    for (const c of DB.q('SELECT * FROM card ORDER BY sort, id')) out.push([`card:${c.id}`, cardLabel(c)]);
    for (const n of custom()) out.push([`etc:${n}`, n]);
    return out;
  }
  const map = () => Object.fromEntries(options());
  function label(pmap, v) {
    v = v || '';
    if (!v) return '';
    if (v in pmap) return pmap[v];
    if (v.startsWith('etc:')) return v.slice(4);
    if (v.startsWith('card:')) return '카드 (지운 카드)';
    return v;
  }
  /** 결제수단별 [{pay,label,count,income,expense,pct}] — 지출 많은 순, 미지정은 맨 뒤 */
  function summary(lid, start, end) {
    const pmap = map();
    const rows = DB.q('SELECT pay, COUNT(*) AS n, COALESCE(SUM(income),0) AS inc, COALESCE(SUM(expense),0) AS exp FROM entry ' +
      'WHERE ledger_id=? AND date BETWEEN ? AND ? GROUP BY pay', [lid, start, end])
      .map(r => ({ pay: r.pay || '', label: label(pmap, r.pay) || '미지정', count: r.n, income: r.inc, expense: r.exp }));
    const total = U.sum(rows.map(x => Math.max(0, x.expense)));
    for (const x of rows) x.pct = U.pct(Math.max(0, x.expense), total);
    rows.sort((a, b) => (a.pay === '') - (b.pay === '') || b.expense - a.expense || b.count - a.count || U.cmp(a.label, b.label));
    return rows;
  }
  const entries = (lid, pay, start, end) => DB.q('SELECT * FROM entry WHERE ledger_id=? AND pay=? AND date BETWEEN ? AND ? ORDER BY date, id', [lid, pay || '', start, end]);
  /** 문자 붙여넣기: 카드·은행 이름으로 결제수단 짐작 */
  function guess(cardText, kind) {
    const t = (cardText || '').trim();
    if (kind === 'in' || /은행|뱅크/.test(t)) return 'bank';
    if (t.includes('페이')) return 'pay';
    if (!t) return '';
    const core = t.replace(/(카드|체크)$/, '').trim();
    for (const c of DB.q('SELECT * FROM card ORDER BY sort, id')) {
      const comp = (c.company || '').trim(), name = (c.name || '').trim();
      if (core && ((comp && (core.includes(comp) || comp.includes(core))) || name.includes(core))) return `card:${c.id}`;
    }
    return 'card';
  }
  return { KINDS, cardLabel, custom, setCustom, renameCustom, options, map, label, summary, entries, guess };
})();

// ════════════════ 큰돈 나눠 적기 ════════════════
const Split = (() => {
  /** 큰돈을 months 달로 나눈 내역들 (첫 달에 나머지). 날은 매달 같은 날(없으면 말일) */
  function plan(e, months) {
    const n = parseInt(months || 0, 10);
    if (!(n >= 2 && n <= 60)) throw new Error('2~60달로 나눌 수 있습니다');
    const inc = parseInt(e.income || 0, 10), exp = parseInt(e.expense || 0, 10);
    if ((inc > 0) === (exp > 0) || inc < 0 || exp < 0) throw new Error('수입이나 지출 한쪽에만 0보다 큰 금액을 넣으세요');
    const total = inc || exp;
    if (total < n) throw new Error('나눌 금액이 너무 작습니다');
    const base = Math.floor(total / n), rem = total - base * n;
    const [y0, m0, d0] = U.parts(e.date);
    const item = (e.item || '').trim(), memo = (e.memo || '').trim();
    const note = `${U.fmtMoney(total)}원을 ${n}달로 나눔`;
    const out = [];
    for (let k = 0; k < n; k++) {
      const [y, m] = U.addMonths(y0, m0, k);
      const amt = base + (k === 0 ? rem : 0);
      out.push({ date: U.clampDay(y, m, d0), item: `${item} (${k + 1}/${n})`, income: inc ? amt : 0, expense: exp ? amt : 0,
        code: (e.code || '').trim(), memo: memo ? `${memo} · ${note}` : note, pay: (e.pay || '').trim() });
    }
    return out;
  }
  /** 나눠 적기 저장. 같은 묶음은 origin 'split:<첫 내역 번호>'. 반환: 내역 번호 목록 */
  function add(lid, e, months) {
    const p = plan(e, months);
    return DB.tx(() => {
      const ids = p.map(x => DB.run('INSERT INTO entry(ledger_id,date,item,income,expense,code,memo,origin,pay) VALUES(?,?,?,?,?,?,?,?,?)',
        [lid, x.date, x.item, x.income, x.expense, x.code, x.memo, null, x.pay]).lastId);
      for (const i of ids) DB.run('UPDATE entry SET origin=? WHERE id=?', [`split:${ids[0]}`, i]);
      const item = (e.item || '').trim();
      if (item && !DB.run('UPDATE item_word SET count=count+1 WHERE ledger_id=? AND name=?', [lid, item]).changes) {
        DB.run('INSERT INTO item_word VALUES(?,?,1)', [lid, item]);
      }
      return ids;
    });
  }
  /** 같이 나눠 적은 내역 번호들 (나눠 적은 내역이 아니면 [eid]) */
  function group(eid) {
    const r = DB.one('SELECT origin FROM entry WHERE id=?', [eid]);
    if (!r || !String(r.origin || '').startsWith('split:')) return [eid];
    return DB.q('SELECT id FROM entry WHERE origin=? ORDER BY date, id', [r.origin]).map(x => x.id);
  }
  return { plan, add, group };
})();

// ════════════════ 외화 ════════════════
const Fx = (() => {
  const CURRENCIES = [['USD', '미국 달러', 1], ['JPY', '일본 엔', 100], ['EUR', '유로', 1], ['CNY', '중국 위안', 1],
    ['GBP', '영국 파운드', 1], ['HKD', '홍콩 달러', 1], ['TWD', '대만 달러', 1], ['THB', '태국 바트', 1],
    ['VND', '베트남 동', 100], ['PHP', '필리핀 페소', 1], ['SGD', '싱가포르 달러', 1], ['AUD', '호주 달러', 1],
    ['CAD', '캐나다 달러', 1]];
  const UNIT = Object.fromEntries(CURRENCIES.map(c => [c[0], c[2]]));
  function dec(s, what, eul, eun) {
    const t = String(s === undefined || s === null ? '' : s).replace(/[,\s]/g, '');
    if (!/^\d+(\.\d+)?$/.test(t)) throw new Error(`${what}${eul} 숫자로 넣으세요`);
    const [ip, fp0] = t.split('.');
    const fp = (fp0 || '').replace(/0+$/, '');
    const v = BigInt((ip + fp) || '0');
    if (v <= 0n) throw new Error(`${what}${eun} 0보다 커야 합니다`);
    return [v, fp.length, Number(ip).toLocaleString('en-US') + (fp ? `.${fp}` : '')];
  }
  /** 외화 금액 × 환율 → 원 (0.5 원은 올림). 엔·동 환율은 100 단위. 반환 [원, 메모 글] */
  function convert(amount, cur, rate) {
    if (!(cur in UNIT)) throw new Error('통화를 고르세요');
    const [a, sa, at] = dec(amount, '외화 금액', '을(를)', '은(는)');
    const [r, sr, rt] = dec(rate, '환율', '을(를)', '은(는)');
    const den = 10n ** BigInt(sa + sr) * BigInt(UNIT[cur]);
    const won = (2n * a * r + den) / (2n * den);
    if (won >= 10n ** 15n) throw new Error('금액이 너무 큽니다');
    return [Number(won), `${cur} ${at} × ${rt}원` + (UNIT[cur] === 100 ? '/100' : '')];
  }
  function rates() { const v = DB.getJson('fx_rates', {}); return v && typeof v === 'object' && !Array.isArray(v) ? v : {}; }
  function setRate(cur, rate) { const d = rates(); d[cur] = String(rate).replace(/[,\s]/g, ''); DB.setJson('fx_rates', d); }
  return { CURRENCIES, UNIT, convert, rates, setRate };
})();

// ════════════════ 같은 곳 모아보기 · 주간 예산 · 주별 통계 · 월별 저축 추이 ════════════════
const Same = (() => {
  /** 같은 내용(취소 포함)의 최근 months 달 내역 */
  function place(lid, item, upto, months) {
    months = months || 3;
    item = (item || '').trim();
    if (!item) return null;
    const [uy, um, ud] = U.parts(upto);
    const [y, m] = U.addMonths(uy, um, -months);
    const start = U.addDays(U.clampDay(y, m, ud), 1);
    const rows = DB.q('SELECT * FROM entry WHERE ledger_id=? AND item IN (?,?) AND date BETWEEN ? AND ? ORDER BY date DESC, id DESC',
      [lid, item, item + ' (취소)', start, upto]);
    const per = [];
    let [yy, mm] = U.parts(start);
    while (yy < uy || (yy === uy && mm <= um)) {
      const ym = U.ym(yy, mm);
      const sel = rows.filter(r => String(r.date).slice(0, 7) === ym);
      per.push({ ym, count: sel.length, expense: U.sum(sel.map(r => r.expense)) });
      [yy, mm] = U.addMonths(yy, mm, 1);
    }
    const exp = U.sum(rows.map(r => r.expense));
    const cnt = rows.filter(r => r.expense > 0).length || rows.length;
    return { item, start, end: upto, count: rows.length, expense: exp, income: U.sum(rows.map(r => r.income)),
      avg: cnt ? Math.floor(exp / cnt) : 0, months: per, rows };
  }
  return { place };
})();

const Week = (() => {
  /** 그 날이 들어 있는 주 [월요일, 일요일] */
  function bounds(d) { const s = U.addDays(d, -U.weekday(d)); return [s, U.addDays(s, 6)]; }
  function budget(lid) { const v = parseInt(DB.getMeta(`budget_week:${lid}`) || 0, 10); return v > 0 ? v : 0; }
  function setBudget(lid, amount) { const v = parseInt(amount || 0, 10); DB.setMeta(`budget_week:${lid}`, v ? v : null); }
  function spentByDay(lid, start, end) {
    const out = {};
    for (const r of DB.q('SELECT date, code, SUM(income) AS inc, SUM(expense) AS exp FROM entry WHERE ledger_id=? AND date BETWEEN ? AND ? GROUP BY date, code', [lid, start, end])) {
      if (!U.isIncomeCode(r.code)) out[r.date] = (out[r.date] || 0) + r.exp - r.inc;
    }
    return out;
  }
  function progress(lid, d, today) {
    today = today || U.today();
    const [s, e] = bounds(d);
    const by = spentByDay(lid, s, e);
    const days = [];
    for (let i = 0; i < 7; i++) { const x = U.addDays(s, i); days.push({ date: x, spent: by[x] || 0 }); }
    const spent = U.sum(days.map(x => x.spent));
    const b = budget(lid);
    const daysLeft = (s <= today && today <= e) ? U.ord(e) - U.ord(today) + 1 : (today > e ? 0 : 7);
    const left = b - spent;
    return { start: s, end: e, spent, budget: b, left, pct: U.pct(spent, b), days, days_left: daysLeft,
      per_day: b && daysLeft > 0 && left > 0 ? Math.floor(left / daysLeft) : 0 };
  }
  /** 그 달(월 시작일 기준)을 월요일로 나눈 주들 */
  function ofMonth(lid, y, m, sd) {
    const [start, end] = U.settlePeriod(y, m, sd);
    const b = budget(lid);
    const out = [];
    for (let ws = U.addDays(start, -U.weekday(start)); ws <= end; ws = U.addDays(ws, 7)) {
      const s = ws > start ? ws : start;
      const we = U.addDays(ws, 6);
      const e = we < end ? we : end;
      const [inc, exp] = Rep.incomeExpense(lid, s, e);
      out.push({ start: s, end: e, days: U.ord(e) - U.ord(s) + 1, income: inc, expense: exp, budget: b });
    }
    return out;
  }
  return { bounds, budget, setBudget, progress, ofMonth };
})();

const Sav = (() => {
  const WORDS = ['저축', '적금', '예금', '투자', '펀드', '연금', '청약'];
  function codes(lid) {
    const gmap = L.groupMap(lid);
    return L.categories(lid).filter(c => !U.isIncomeCode(c.code) && WORDS.some(w => (c.name + ' ' + (gmap[c.code.slice(0, 1)] || '')).includes(w))).map(c => c.code);
  }
  /** 달마다 수입·지출·남은 돈·저축 카테고리로 낸 돈·모은 돈·저축률·누계 */
  function trend(lid, y, sd) {
    const cs = codes(lid);
    const rows = [];
    let cum = 0;
    for (let m = 1; m <= 12; m++) {
      const [s, e] = U.settlePeriod(y, m, sd);
      const by = Rep.sumByCode(lid, s, e);
      let inc = 0, exp = 0;
      for (const [c, v] of Object.entries(by)) { if (U.isIncomeCode(c)) inc += v; else exp += v; }
      const sv = U.sum(cs.map(c => by[c] || 0));
      const left = inc - exp, saved = left + sv;
      cum += saved;
      rows.push({ month: m, start: s, end: e, income: inc, expense: exp, left, saving: sv, saved, rate: U.pct(saved, inc), cum });
    }
    const ti = U.sum(rows.map(r => r.income)), ts = U.sum(rows.map(r => r.saved));
    const total = { income: ti, expense: U.sum(rows.map(r => r.expense)), left: U.sum(rows.map(r => r.left)),
      saving: U.sum(rows.map(r => r.saving)), saved: ts, rate: U.pct(ts, ti) };
    return { rows, total, codes: cs };
  }
  return { WORDS, codes, trend };
})();

// ════════════════ 고정비 한눈에 · 한 달 전체 예산 · 달력 돈 일정 · 카드 실적 ════════════════
const Fixed = (() => {
  function items(lid, start, end, today) {
    today = today || U.today();
    const out = [];
    for (const r of R.rules(lid)) {
      for (const d of R.occurrences(r, start, end)) {
        out.push({ rid: r.id, date: d, item: r.item, income: r.income, expense: r.expense, code: r.code, pay: r.pay || '',
          status: R.statusOf(r, d, today) });
      }
    }
    return out.sort((a, b) => U.cmp(a.date, b.date) || a.rid - b.rid);
  }
  function summary(lid, y, m, sd, today) {
    today = today || U.today();
    const [start, end] = U.settlePeriod(y, m, sd);
    const its = items(lid, start, end, today);
    const live = its.filter(x => x.status !== 'skipped');
    const outTotal = U.sum(live.map(x => x.expense)), outDone = U.sum(live.filter(x => x.status === 'done').map(x => x.expense));
    const inTotal = U.sum(live.map(x => x.income)), inDone = U.sum(live.filter(x => x.status === 'done').map(x => x.income));
    const [inc, exp] = Rep.incomeExpense(lid, start, end);
    const fixedExp = DB.val("SELECT COALESCE(SUM(expense),0) FROM entry WHERE ledger_id=? AND date BETWEEN ? AND ? AND origin LIKE 'recurring:%'", [lid, start, end]);
    return { start, end, items: its, out_total: outTotal, out_done: outDone, out_left: outTotal - outDone,
      in_total: inTotal, in_done: inDone, in_left: inTotal - inDone, income: inc, expense: exp, fixed_expense: fixedExp,
      variable: exp - fixedExp, expected_left: inc + (inTotal - inDone) - exp - (outTotal - outDone) };
  }
  return { items, summary };
})();

const TBud = (() => {
  function all(lid) { const d = DB.getJson(`budget_total:${lid}`, {}); return d && typeof d === 'object' && !Array.isArray(d) ? d : {}; }
  function get(lid, ym) { const v = parseInt(all(lid)[ym] || 0, 10); return v > 0 ? v : 0; }
  function set(lid, yms, amount) {
    const d = all(lid);
    const v = parseInt(amount || 0, 10);
    for (const ym of yms) { if (v > 0) d[ym] = v; else delete d[ym]; }
    DB.setJson(`budget_total:${lid}`, d);
  }
  /** 그 날이 들어 있는 달에 쓴 돈 (지출 카테고리 전체) */
  function monthSpent(lid, d, sd) {
    const [y, m] = Ins.periodOf(d, sd);
    const [s, e] = U.settlePeriod(y, m, sd);
    return Rep.incomeExpense(lid, s, e)[1];
  }
  /** 저장한 뒤 한 달 전체 예산의 80%·100% 를 처음 넘었으면 알림 글, 아니면 null */
  function alert(lid, d, before, sd) {
    const [y, m] = Ins.periodOf(d, sd);
    const b = get(lid, U.ym(y, m));
    if (b <= 0) return null;
    const after = monthSpent(lid, d, sd);
    const f = U.fmtMoney;
    if (before < b && b <= after) return `${m}월 전체 예산을 넘었어요: ${f(after)}원 / ${f(b)}원 (${f(after - b)}원 초과)`;
    if (before * 100 < b * 80 && b * 80 <= after * 100) return `${m}월 전체 예산의 ${U.pct(after, b)}%를 썼어요 (남은 돈 ${f(b - after)}원)`;
    return null;
  }
  return { all, get, set, monthSpent, alert };
})();

const MCal = (() => {
  /** {날짜: [{kind:'card'|'fixed', label, amount, sign:'in'|'out', done}]} */
  function events(lid, start, end, today) {
    const out = {};
    for (const r of DB.q('SELECT c.id, c.name, c.company, c.sort, t.pay_date, SUM(t.amount+t.fee) AS amt, MIN(t.paid) AS allpaid ' +
      'FROM card_tx t JOIN card c ON c.id=t.card_id WHERE t.pay_date BETWEEN ? AND ? GROUP BY c.id, t.pay_date ORDER BY t.pay_date, c.sort, c.id', [start, end])) {
      (out[r.pay_date] || (out[r.pay_date] = [])).push({ kind: 'card', label: `${Pay.cardLabel(r)} 결제`, amount: r.amt, sign: 'out', done: !!r.allpaid });
    }
    for (const x of Fixed.items(lid, start, end, today)) {
      (out[x.date] || (out[x.date] = [])).push({ kind: 'fixed', label: x.item || '고정', amount: x.income || x.expense,
        sign: x.income && !x.expense ? 'in' : 'out', done: x.status === 'done' || x.status === 'skipped' });
    }
    return out;
  }
  return { events };
})();

const Perf = (() => {
  /** 카드마다 그 달(1일~말일) 결제수단이 그 카드인 지출 합계와 월 실적 목표 (모든 가계부를 합침) */
  function cards(y, m) {
    const s = U.iso(y, m, 1), e = U.clampDay(y, m, 31);
    return DB.q('SELECT * FROM card ORDER BY sort, id').map(c => {
      let target = 0;
      try { target = Math.max(0, parseInt(JSON.parse(c.extra || '{}').perf || 0, 10) || 0); } catch (_) { target = 0; }
      const r = DB.one('SELECT COUNT(*) AS n, COALESCE(SUM(expense),0) AS exp FROM entry WHERE pay=? AND date BETWEEN ? AND ?', [`card:${c.id}`, s, e]);
      return { id: c.id, label: Pay.cardLabel(c), target, spent: r.exp, count: r.n, left: Math.max(0, target - r.exp), pct: U.pct(r.exp, target) };
    });
  }
  return { cards };
})();

// ════════════════ 휴지통 (services/trash.py) ════════════════
const Trash = (() => {
  const KEEP_DAYS = 30;
  const COLS = ['ledger_id', 'date', 'item', 'income', 'expense', 'code', 'memo', 'origin', 'pay'];
  const DEFAULTS = { item: '', income: 0, expense: 0, code: '', memo: '', origin: null, pay: '' };
  const p2 = n => String(n).padStart(2, '0');
  function now() { const t = new Date(); return `${U.iso(t.getFullYear(), t.getMonth() + 1, t.getDate())} ${p2(t.getHours())}:${p2(t.getMinutes())}:${p2(t.getSeconds())}`; }
  const sortedJson = o => JSON.stringify(Object.fromEntries(Object.keys(o).sort().map(k => [k, o[k]])));
  /** 내역 ids 를 휴지통에 넣음 (지우기는 부르는 쪽이). 반환: 휴지통 번호 목록 */
  function put(ids, why, at) {
    const t = at || now();
    return DB.tx(() => {
      const out = [];
      for (const i of ids) {
        const r = DB.one('SELECT * FROM entry WHERE id=?', [i]);
        if (!r) continue;
        const tid = DB.run('INSERT INTO trash(ledger_id,deleted,why,entry) VALUES(?,?,?,?)', [r.ledger_id, t, why || 'delete', sortedJson(r)]).lastId;
        DB.run('INSERT INTO trash_photo(trash_id,name,mime,data,created) SELECT ?,name,mime,data,created FROM attachment WHERE entry_id=? ORDER BY id', [tid, i]);
        out.push(tid);
      }
      return out;
    });
  }
  function items(lid) {
    let sql = 'SELECT t.id, t.ledger_id, t.deleted, t.why, t.entry, (SELECT COUNT(*) FROM trash_photo p WHERE p.trash_id=t.id) AS photos FROM trash t';
    const a = [];
    if (lid !== undefined && lid !== null) { sql += ' WHERE t.ledger_id=?'; a.push(lid); }
    return DB.q(sql + ' ORDER BY t.deleted DESC, t.id DESC', a).map(r => {
      let e = {};
      try { e = JSON.parse(r.entry); } catch (_) { e = {}; }
      return { id: r.id, ledger_id: r.ledger_id, deleted: r.deleted, why: r.why, entry: e, photos: r.photos };
    });
  }
  const count = lid => (lid === undefined || lid === null ? DB.val('SELECT COUNT(*) FROM trash') : DB.val('SELECT COUNT(*) FROM trash WHERE ledger_id=?', [lid]));
  /** 되살리기. 반환: 되살린 내역 번호 목록 (원래 번호가 비어 있으면 그 번호로) */
  function restore(tids) {
    return DB.tx(() => {
      const out = [];
      for (const tid of tids) {
        const r = DB.one('SELECT * FROM trash WHERE id=?', [tid]);
        if (!r) continue;
        let e = {};
        try { e = JSON.parse(r.entry); } catch (_) { e = {}; }
        if (!DB.one('SELECT 1 AS x FROM ledger WHERE id=?', [r.ledger_id])) continue;
        e.ledger_id = r.ledger_id;
        const vals = COLS.map(k => (e[k] !== undefined && e[k] !== null ? e[k] : (k in DEFAULTS ? DEFAULTS[k] : null)));
        let eid;
        if (e.id && !DB.one('SELECT 1 AS x FROM entry WHERE id=?', [e.id])) {
          DB.run(`INSERT INTO entry(id,${COLS.join(',')}) VALUES(?${',?'.repeat(COLS.length)})`, [e.id].concat(vals));
          eid = e.id;
        } else {
          eid = DB.run(`INSERT INTO entry(${COLS.join(',')}) VALUES(${COLS.map(() => '?').join(',')})`, vals).lastId;
        }
        DB.run('INSERT INTO attachment(entry_id,name,mime,data,created) SELECT ?,name,mime,data,created FROM trash_photo WHERE trash_id=? ORDER BY id', [eid, tid]);
        DB.run('DELETE FROM trash WHERE id=?', [tid]);
        out.push(eid);
      }
      return out;
    });
  }
  const remove = tids => DB.tx(() => tids.forEach(t => DB.run('DELETE FROM trash WHERE id=?', [t])));
  const empty = lid => (lid === undefined || lid === null ? DB.run('DELETE FROM trash') : DB.run('DELETE FROM trash WHERE ledger_id=?', [lid]));
  /** 보관 기간이 지난 것 지우기 (앱을 켤 때). 반환: 지운 수 */
  function purge(today, days) {
    const limit = U.addDays(today || U.today(), -(days || KEEP_DAYS));
    return DB.run('DELETE FROM trash WHERE deleted < ?', [limit]).changes;
  }
  const daysLeft = (deleted, today, days) => Math.max(0, U.ord(U.addDays(String(deleted).slice(0, 10), days || KEEP_DAYS)) - U.ord(today || U.today()));
  return { KEEP_DAYS, put, items, count, restore, remove, empty, purge, daysLeft };
})();

// ════════════════ 카테고리 그림 (services/catemoji.py) ════════════════
const Emo = (() => {
  const CHOICES = ['💰', '💵', '💴', '💳', '🏦', '📈', '🐷', '🎁',
    '🍚', '🍜', '🍔', '🍕', '🍰', '☕', '🍺', '🛒', '🍎', '🏪',
    '🚌', '🚇', '🚕', '🚗', '⛽', '✈️', '🚲', '🎫',
    '🏠', '💡', '💧', '🔥', '📱', '🌐', '📺', '🔧',
    '🎓', '📚', '✏️', '🏥', '💊', '☔', '👕', '💄',
    '🎬', '🎮', '🎵', '⚽', '🐶', '👶', '💒', '🙏',
    '📦', '📝', '❤️', '⭐'];
  const HINTS = [
    [/급여|월급|상여|보너스|수입/i, '💰'], [/용돈/i, '💵'], [/이자|배당|투자|주식|펀드/i, '📈'],
    [/저축|적금|예금|청약|연금/i, '🐷'], [/대출|카드대금|할부/i, '🏦'],
    [/관리비|월세|주거|공과금/i, '🏠'], [/수도/i, '💧'], [/전기/i, '💡'], [/가스|난방/i, '🔥'],
    [/학원|교육|학비|등록금/i, '🎓'], [/교재|책|도서/i, '📚'],
    [/카페|커피|간식|디저트/i, '☕'], [/배달|치킨|피자/i, '🍔'], [/외식|식당/i, '🍜'], [/^술$|술값|주류|회식/i, '🍺'],
    [/식료품|장보기|마트|식비|식재료/i, '🛒'], [/편의점/i, '🏪'],
    [/택시/i, '🚕'], [/주유|자동차|차량|주차|정비/i, '🚗'], [/교통|버스|지하철|기차/i, '🚌'],
    [/휴대폰|통신|전화/i, '📱'], [/인터넷|와이파이/i, '🌐'], [/구독|넷플릭스|OTT|음악/i, '🎵'], [/TV|방송/i, '📺'],
    [/병원|의료|치과/i, '🏥'], [/약국|약값|의약|약품/i, '💊'], [/보험/i, '☔'],
    [/옷|의류|쇼핑|패션/i, '👕'], [/미용|화장|뷰티|헤어/i, '💄'], [/생필품|생활용품|생활/i, '📦'],
    [/영화|문화|공연|여가|취미/i, '🎬'], [/게임/i, '🎮'], [/운동|헬스|스포츠/i, '⚽'], [/여행|휴가/i, '✈️'],
    [/경조사|선물|축의|부의/i, '🎁'], [/결혼|웨딩/i, '💒'], [/반려|애완|강아지|고양이/i, '🐶'], [/육아|아기|유아|어린이/i, '👶'],
    [/기부|헌금|후원/i, '🙏'], [/수리|공구|집수리/i, '🔧'], [/잡비|기타/i, '📝'],
  ];
  function suggest(name) { for (const [re, e] of HINTS) if (re.test(name || '')) return e; return ''; }
  function map(lid) {
    const v = DB.getJson(`cat_emoji:${lid}`, {});
    const out = {};
    if (v && typeof v === 'object' && !Array.isArray(v)) for (const [k, e] of Object.entries(v)) if (e) out[String(k)] = String(e);
    return out;
  }
  function set(lid, code, emoji) {
    const d = map(lid);
    const e = Array.from(String(emoji || '').trim()).slice(0, 4).join('');
    if (e) d[code] = e; else delete d[code];
    DB.setJson(`cat_emoji:${lid}`, d);
  }
  /** 그림이 없는 카테고리·세부 카테고리에 이름으로 어울리는 그림 넣기. 반환: 넣은 수 */
  function fillDefaults(lid, overwrite) {
    const d = map(lid);
    let n = 0;
    const rows = DB.q('SELECT code, name FROM cat_group WHERE ledger_id=? ORDER BY code', [lid])
      .concat(DB.q('SELECT code, name FROM category WHERE ledger_id=? ORDER BY code', [lid]));
    for (const { code, name } of rows) {
      if (d[code] && !overwrite) continue;
      const e = suggest(name);
      if (e && d[code] !== e) { d[code] = e; n++; }
    }
    DB.setJson(`cat_emoji:${lid}`, d);
    return n;
  }
  /** '🛒 식료품' (그림이 없으면 이름만). 세부 카테고리에 그림이 없으면 카테고리 그림 */
  function deco(emap, code, name) {
    const e = emap[code] || (code && code.length > 1 ? emap[code.slice(0, 1)] : '') || '';
    return e ? `${e} ${name}` : name;
  }
  return { CHOICES, HINTS, suggest, map, set, fillDefaults, deco };
})();
