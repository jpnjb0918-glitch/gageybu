/* 1.7.0 에 더한 기능의 계산 (PC판 services/smsparse.py·insights.py·goals.py·attach.py·ledger.py 와 같은 규칙,
   devtools/compat 로 결과를 비교): 문자 붙여넣기·자주 쓰는 내역·#태그·예산 진행·예산 알림·이달 리포트·무지출·
   저축 목표·빌려준 돈/빌린 돈·내역 사진 */
'use strict';

// ════════════════ 자주 쓰는 내역·#태그 (services/ledger.py) ════════════════
Object.assign(L, (() => {
  const favorites = lid => DB.q('SELECT * FROM favorite WHERE ledger_id=? ORDER BY sort, id', [lid]);
  function saveFavorite(lid, f, fid) {
    const vals = [(f.item || '').trim(), parseInt(f.income || 0, 10), parseInt(f.expense || 0, 10), (f.code || '').trim(), (f.memo || '').trim()];
    if (fid) { DB.run('UPDATE favorite SET item=?,income=?,expense=?,code=?,memo=? WHERE id=?', [...vals, fid]); return fid; }
    const sort = DB.val('SELECT COALESCE(MAX(sort),0)+1 FROM favorite WHERE ledger_id=?', [lid]);
    return DB.run('INSERT INTO favorite(ledger_id,item,income,expense,code,memo,sort) VALUES(?,?,?,?,?,?,?)', [lid, ...vals, sort]).lastId;
  }
  const deleteFavorite = fid => DB.run('DELETE FROM favorite WHERE id=?', [fid]);
  function moveFavorite(lid, fid, delta) {
    const ids = favorites(lid).map(r => r.id);
    const i = ids.indexOf(fid), j = i + delta;
    if (i < 0 || j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    DB.tx(() => ids.forEach((x, k) => DB.run('UPDATE favorite SET sort=? WHERE id=?', [k, x])));
  }

  const TAG_RE = /#([^\s#.,;:!?()[\]{}"'<>/]+)/g;
  /** 글에서 태그 목록 (순서대로, 같은 것은 한 번) */
  function tagsOf(...texts) {
    const out = [];
    for (const t of texts) for (const m of String(t || '').matchAll(TAG_RE)) if (!out.includes(m[1])) out.push(m[1]);
    return out;
  }
  /** [{tag,count,income,expense}] — 지출 많은 순 (같으면 건수·이름 순) */
  function tagSummary(lid, start, end) {
    let sql = "SELECT item, memo, income, expense FROM entry WHERE ledger_id=? AND (item LIKE '%#%' OR memo LIKE '%#%')";
    const a = [lid];
    if (start) { sql += ' AND date>=?'; a.push(start); }
    if (end) { sql += ' AND date<=?'; a.push(end); }
    const acc = {};
    for (const r of DB.q(sql, a)) {
      for (const t of tagsOf(r.item, r.memo)) {
        const x = acc[t] || (acc[t] = { tag: t, count: 0, income: 0, expense: 0 });
        x.count++; x.income += r.income; x.expense += r.expense;
      }
    }
    return Object.values(acc).sort((x, y) => y.expense - x.expense || y.count - x.count || (x.tag < y.tag ? -1 : x.tag > y.tag ? 1 : 0));
  }
  /** 그 태그가 정확히 들어 있는 내역 (#여행 을 찾을 때 #여행지 는 빼고) */
  const entriesWithTag = (lid, tag, start, end) => L.search(lid, { start, end, text: '#' + tag }).filter(r => tagsOf(r.item, r.memo).includes(tag));
  return { favorites, saveFavorite, deleteFavorite, moveFavorite, tagsOf, tagSummary, entriesWithTag };
})());

// ════════════════ 문자 붙여넣기 (services/smsparse.py) ════════════════
const Sms = (() => {
  const ISSUERS = ['KB국민', 'NH농협', 'IBK기업', 'SC제일', '카카오뱅크', '토스뱅크', '케이뱅크', '새마을금고', '우체국',
    '신한', '국민', '삼성', '현대', '롯데', '우리', '하나', '농협', '비씨', 'BC', '씨티', '기업', '수협', '신협',
    '광주', '전북', '경남', '부산', '대구', '제주', '카카오페이', '네이버페이', '토스', 'KB', 'NH'];
  const reEsc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const ISSUER = new RegExp('(' + ISSUERS.map(reEsc).join('|') + ')');
  const AMOUNT = () => /(?<![\d.])(\d{1,3}(?:,\d{3})+|\d+)\s*원/g;
  const BARE = () => /(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d{3,})(?![\d,]*\s*원)/g;
  const DATE = () => /(?:(\d{4})[./-])?(\d{1,2})[./-](\d{1,2})(?!\d)/g;
  const TIME = /(?<!\d)(\d{1,2}):(\d{2})(?!\d)/;
  const MONTHS = /(\d{1,2})\s*개월/;
  const NOISE = ['누적', '잔액', '한도', '총누적', '결제예정', '포인트'];
  const SKIP_LINE = /Web발신|승인|님(?=\s|$)|\*|누적|잔액|한도|일시불|할부|개월|^\[.*\]$|^\(.*\)$|입금|출금|결제|사용|취소/;

  function split(text) {
    const t = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    const out = [];
    for (const part of t.split(/\[Web발신\]|\n\s*\n/)) {
      let cur = [];
      for (const ln of part.split('\n')) {
        if (cur.length && /^\s*\[[^\]]{1,12}\]/.test(ln)) { out.push(cur.join('\n')); cur = []; }
        cur.push(ln);
      }
      out.push(cur.join('\n'));
    }
    return out.map(p => p.trim()).filter(Boolean);
  }
  function cutNoise(s) {
    const idx = NOISE.map(n => s.indexOf(n)).filter(i => i >= 0);
    return idx.length ? s.slice(0, Math.min(...idx)) : s;
  }
  const noiseBefore = (block, i) => NOISE.some(n => block.slice(Math.max(0, i - 5), i).includes(n));
  function yearFor(m, d, today) {
    const y = Number(today.slice(0, 4));
    if (d > U.monthEnd(y, m)) return null;
    let cand = U.iso(y, m, d);
    if (cand > U.addDays(today, 2)) {
      if (d > U.monthEnd(y - 1, m)) return null;
      cand = U.iso(y - 1, m, d);
    }
    return cand;
  }
  function amountOf(block) {
    for (const m of block.matchAll(AMOUNT())) {
      if (noiseBefore(block, m.index)) continue;
      return parseInt(m[1].replace(/,/g, ''), 10);
    }
    for (const kw of ['입금', '출금']) {
      const i = block.indexOf(kw);
      if (i >= 0) {
        const re = BARE();
        re.lastIndex = i;
        let m;
        while ((m = re.exec(block)) && m.index < i) { /* 앞쪽은 건너뜀 */ }
        if (m && !noiseBefore(block, m.index)) return parseInt(m[1].replace(/,/g, ''), 10);
      }
    }
    return null;
  }
  function merchant(block, issuer) {
    const lines = block.split('\n').map(l => l.trim()).filter(Boolean);
    for (const ln of lines) {
      const m = TIME.exec(ln);
      if (m) {
        let rest = cutNoise(ln.slice(m.index + m[0].length)).replace(AMOUNT(), ' ').split(/\s+/).filter(Boolean).join(' ');
        rest = rest.replace(/^(출금|입금|승인|결제|사용|일시불)\s*/, '').replace(/^[\s,·-]+|[\s,·-]+$/g, '');
        if (rest && !/^[\d,\s]+$/.test(rest) && !['입금', '출금', '승인', '취소'].includes(rest)) return rest;
      }
    }
    for (const ln of lines) {
      if (SKIP_LINE.test(ln) || AMOUNT().test(ln) || DATE().test(ln) || TIME.test(ln)) continue;
      if (issuer && ln.includes(issuer)) continue;
      if (/^[\d,\-\s]+$/.test(ln)) continue;
      return ln;
    }
    return '';
  }
  /** 붙여넣은 글 → [{date,time,amount,kind,item,card,months,ok,raw}] (kind: out·cancel·in) */
  function parse(text, today) {
    today = today || U.today();
    const out = [];
    for (const block of split(text)) {
      const flat = block.split(/\s+/).filter(Boolean).join(' ');
      const im = ISSUER.exec(block);
      const issuer = im ? im[1] : '';
      let card = '';
      if (issuer) {
        const cm = new RegExp(reEsc(issuer) + '\\s*(카드|은행|뱅크|체크|페이)?').exec(block);
        card = cm ? issuer + (cm[1] || '') : issuer;
      }
      const kind = flat.includes('취소') ? 'cancel' : (flat.includes('입금') && !flat.includes('출금') ? 'in' : 'out');
      const amount = amountOf(block);
      let dm = null;
      for (const m of block.matchAll(DATE())) {
        const mo = Number(m[2]), dd = Number(m[3]);
        if (mo >= 1 && mo <= 12 && dd >= 1 && dd <= 31) { dm = m; break; }
      }
      let date = null;
      if (dm) {
        const mo = Number(dm[2]), dd = Number(dm[3]);
        if (dm[1]) date = dd <= U.monthEnd(Number(dm[1]), mo) ? U.iso(Number(dm[1]), mo, dd) : null;
        else date = yearFor(mo, dd, today);
      }
      const tm = TIME.exec(block);
      const mm = MONTHS.exec(block);
      const months = mm ? Math.max(1, parseInt(mm[1], 10)) : 1;
      const item = merchant(block, issuer) || `${card || '카드'} ${kind === 'in' ? '입금' : '승인'}`.trim();
      out.push({ date: date || '', time: tm ? `${U.pad(Number(tm[1]))}:${tm[2]}` : '', amount: amount || 0, kind, item, card, months,
        ok: !!(amount && date), raw: flat });
    }
    return out;
  }
  /** 후보 하나 → 내역 값. 취소는 지출을 음수로 */
  function toEntry(p) {
    const memo = [p.card, p.months > 1 ? `${p.months}개월` : '', p.time].filter(Boolean).join(' ');
    if (p.kind === 'in') return { date: p.date, item: p.item, income: p.amount, expense: 0, memo };
    const sign = p.kind === 'cancel' ? -1 : 1;
    return { date: p.date, item: p.item + (p.kind === 'cancel' ? ' (취소)' : ''), income: 0, expense: sign * p.amount, memo };
  }
  // 가게 이름 → 흔한 계정 이름 (PC판 smsparse.HINTS 와 같음)
  const HINTS = [
    [/영화|CGV|메가박스|롯데시네마|공연|티켓|전시/i, ["문화", "여가", "잡비"]],
    [/스타벅스|커피|카페|이디야|투썸|메가MGC|빽다방|폴바셋|할리스|공차|배스킨|던킨|파리바게|뚜레쥬르|베이커리/i, ["카페", "간식", "외식", "식비"]],
    [/배달|요기요|쿠팡이츠|치킨|피자|버거|맥도날드|롯데리아|맘스터치|분식|김밥|식당|국밥|고기|횟집|족발|보쌈|초밥|돈까스|반점|짬뽕/i, ["배달", "외식", "식비"]],
    [/이마트24|GS25|CU|씨유|세븐일레븐|미니스톱|편의점/i, ["편의점", "간식", "식료품", "식비"]],
    [/마트|홈플러스|코스트코|트레이더스|하나로|식자재|정육|청과|노브랜드|더프레시|컬리/i, ["식료품", "장보기", "식비"]],
    [/택시|카카오T|버스|지하철|코레일|KTX|SRT|티머니|교통|주유|에너지|칼텍스|오일|충전소|하이패스|주차/i, ["대중교통", "교통", "주유", "차량"]],
    [/SKT|KT|LG유플러스|U\+|통신|알뜰폰/i, ["휴대폰", "통신"]],
    [/약국|병원|의원|치과|한의원|안과|피부과|정형외과|내과/i, ["병원", "의료", "약"]],
    [/다이소|올리브영|쿠팡|11번가|G마켓|지마켓|옥션|무신사|오늘의집|생활/i, ["생필품", "생활용품", "쇼핑"]],
    [/학원|교습|서점|교보문고|영풍문고|YES24|알라딘/i, ["학원비", "교재비", "교육"]],
    [/넷플릭스|유튜브|멜론|디즈니|티빙|웨이브|왓챠|스포티파이|구독/i, ["구독", "문화", "잡비"]],
    [/보험/i, ["보험료", "보험"]],
    [/한전|전기요금/i, ["전기세", "전기"]],
    [/도시가스|가스요금/i, ["가스비", "가스"]],
    [/수도요금|상수도/i, ["수도세", "수도"]],
  ];
  /** 새 내역의 계정 고르기: ① 예전 같은 품목 ② 가게 이름으로 짐작 ③ 가장 많이 쓴 지출 계정 ④ 첫 계정 */
  function guessCode(lid, item, income) {
    item = String(item || '').trim();
    const c = item ? L.lastCodeForItem(lid, item) : null;
    if (c && U.isIncomeCode(c) === !!income) return c;
    const cats = L.categories(lid).map(r => [r.code, r.name]);
    if (income) {
      const inc = cats.filter(x => U.isIncomeCode(x[0]));
      const k = inc.find(x => x[1].includes('기타'));
      return k ? k[0] : (inc.length ? inc[0][0] : '');
    }
    const exp = cats.filter(x => !U.isIncomeCode(x[0]));
    for (const [pat, names] of HINTS) {
      if (pat.test(item)) {
        for (const want of names) {
          const hit = exp.find(x => x[1].includes(want));
          if (hit) return hit[0];
        }
      }
    }
    const r = DB.one("SELECT code, COUNT(*) n FROM entry WHERE ledger_id=? AND expense>0 AND substr(code,1,1)<>'0' GROUP BY code ORDER BY n DESC, code LIMIT 1", [lid]);
    if (r && exp.some(x => x[0] === r.code)) return r.code;
    return exp.length ? exp[0][0] : '';
  }
  return { parse, toEntry, guessCode, HINTS };
})();

// ════════════════ 예산 진행·알림·이달 리포트·무지출 (services/insights.py) ════════════════
const Ins = (() => {
  /** 그 날이 들어 있는 결산 '달' [연, 월] */
  function periodOf(d, sd) {
    const [y, m] = U.parts(d);
    const [start] = U.settlePeriod(y, m, sd);
    return d >= start ? [y, m] : U.addMonths(y, m, -1);
  }
  const pct = (a, b) => (b > 0 ? Math.floor(a * 100 / b + 0.5) : null);
  function spentByCode(lid, start, end) {
    const out = {};
    for (const [c, v] of Object.entries(Rep.sumByCode(lid, start, end))) if (!U.isIncomeCode(c)) out[c] = v;
    return out;
  }
  const cmpStr = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  const dayDiff = (a, b) => U.ord(a) - U.ord(b);

  function budgetProgress(lid, y, m, sd, today) {
    today = today || U.today();
    const [start, end] = U.settlePeriod(y, m, sd);
    const bud = {};
    for (const [c, v] of Object.entries(Rep.budgets(lid, U.ym(y, m)))) if (!U.isIncomeCode(c) && v > 0) bud[c] = v;
    const spent = spentByCode(lid, start, end);
    const cmap = L.categoryMap(lid);
    const rows = Object.entries(bud).map(([code, b]) => {
      const s = spent[code] || 0;
      return { code, name: L.codeLabel(cmap, code), budget: b, spent: s, left: b - s, pct: pct(s, b) };
    });
    rows.sort((x, z) => z.pct - x.pct || z.spent - x.spent || cmpStr(x.code, z.code));
    const tb = U.sum(Object.values(bud)), ts = U.sum(rows.map(r => r.spent));
    const daysLeft = (start <= today && today <= end) ? dayDiff(end, today) + 1 : (today > end ? 0 : dayDiff(end, start) + 1);
    const left = tb - ts;
    return { rows, budget: tb, spent: ts, left, pct: pct(ts, tb), days_left: daysLeft,
      per_day: daysLeft > 0 && left > 0 ? Math.floor(left / daysLeft) : 0, start, end };
  }
  function codeSpent(lid, code, d, sd) {
    const [y, m] = periodOf(d, sd);
    const [start, end] = U.settlePeriod(y, m, sd);
    return spentByCode(lid, start, end)[code] || 0;
  }
  /** 저장한 뒤 그 계정이 예산의 80%·100% 를 처음 넘었으면 알림 글, 아니면 null */
  function budgetAlert(lid, code, d, before, sd) {
    if (!code || U.isIncomeCode(code)) return null;
    const [y, m] = periodOf(d, sd);
    const b = Rep.budgets(lid, U.ym(y, m))[code] || 0;
    if (b <= 0) return null;
    const after = codeSpent(lid, code, d, sd);
    const name = L.codeLabel(L.categoryMap(lid), code);
    const f = U.fmtMoney;
    if (before < b && b <= after) return `${m}월 ${name} 예산을 넘었어요: ${f(after)}원 / ${f(b)}원 (${f(after - b)}원 초과)`;
    if (before * 100 < b * 80 && b * 80 <= after * 100) return `${m}월 ${name} 예산의 ${pct(after, b)}%를 썼어요 (남은 돈 ${f(b - after)}원)`;
    return null;
  }
  /** 지출이 없는 날 (그 날 지출 합계가 0 이하). 장부에 처음 적은 날보다 앞은 빼고 셈 (빈 장부는 없음) */
  function noSpendDays(lid, start, end) {
    const first = DB.val('SELECT MIN(date) FROM entry WHERE ledger_id=?', [lid]);
    if (!first) return [];
    if (start < first) start = first;
    const spent = new Set(DB.q('SELECT date FROM entry WHERE ledger_id=? AND date BETWEEN ? AND ? GROUP BY date HAVING SUM(expense) > 0', [lid, start, end]).map(r => r.date));
    const out = [];
    for (let d = start; d <= end; d = U.addDays(d, 1)) if (!spent.has(d)) out.push(d);
    return out;
  }
  function noSpendStreak(lid, upto, limit) {
    const days = new Set(noSpendDays(lid, U.addDays(upto, -((limit || 366) - 1)), upto));
    let n = 0;
    for (let d = upto; days.has(d); d = U.addDays(d, -1)) n++;
    return n;
  }
  function monthInsight(lid, y, m, sd, today) {
    today = today || U.today();
    const [start, end] = U.settlePeriod(y, m, sd);
    const current = start <= today && today <= end;
    const upto = current ? today : end;
    const totalDays = dayDiff(end, start) + 1;
    const days = upto >= start ? dayDiff(upto, start) + 1 : 0;
    const [inc, exp] = days ? Rep.incomeExpense(lid, start, upto) : [0, 0];
    const [py, pm] = U.addMonths(y, m, -1);
    const [ps, pe] = U.settlePeriod(py, pm, sd);
    const pUptoRaw = U.addDays(ps, Math.max(days, 1) - 1);
    const pUpto = pUptoRaw < pe ? pUptoRaw : pe;
    const prevSame = days ? Rep.incomeExpense(lid, ps, pUpto)[1] : 0;
    const prevFull = Rep.incomeExpense(lid, ps, pe)[1];
    const cmap = L.categoryMap(lid);
    const cur = days ? spentByCode(lid, start, upto) : {};
    const prev = days ? spentByCode(lid, ps, pUpto) : {};
    const top = Object.entries(cur).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1] || cmpStr(a[0], b[0])).slice(0, 3);
    const big = days ? DB.one('SELECT item, expense, date FROM entry WHERE ledger_id=? AND date BETWEEN ? AND ? AND expense>0 ORDER BY expense DESC, date, id LIMIT 1', [lid, start, upto]) : null;
    // 무지출 날은 오늘까지만 셈 (앞으로 올 날은 빼기 — 미리 넣은 카드대금 같은 미래 달)
    const nsEnd = upto < today ? upto : today;
    const ns = days && nsEnd >= start ? noSpendDays(lid, start, nsEnd) : [];
    const avg = days ? Math.floor(exp / days) : 0;
    return {
      start, end, upto: days ? upto : '', current, days, total_days: totalDays, income: inc, expense: exp,
      prev_same: prevSame, prev_full: prevFull, change_pct: pct(exp - prevSame, prevSame),
      daily_avg: avg, projected: current ? avg * totalDays : exp,
      top: top.map(([c, v]) => ({ code: c, name: L.codeLabel(cmap, c), amount: v, prev: prev[c] || 0, change_pct: pct(v - (prev[c] || 0), prev[c] || 0) })),
      biggest: big ? { item: big.item, amount: big.expense, date: big.date } : null,
      no_spend: ns.length, streak: days && nsEnd >= start ? noSpendStreak(lid, nsEnd) : 0,
      budget: budgetProgress(lid, y, m, sd, today),
    };
  }
  return { periodOf, budgetProgress, codeSpent, budgetAlert, noSpendDays, noSpendStreak, monthInsight };
})();

// ════════════════ 저축 목표·빌려준 돈/빌린 돈 (services/goals.py) ════════════════
const Goal = (() => {
  const goals = includeDone => DB.q('SELECT * FROM goal' + (includeDone === false ? ' WHERE done=0' : '') + ' ORDER BY done, sort, id');
  function saveGoal(g, gid) {
    const name = (g.name || '').trim();
    if (!name) throw new Error('목표 이름을 입력하세요');
    const vals = [name, parseInt(g.target || 0, 10), g.due || null, (g.memo || '').trim(), g.done ? 1 : 0];
    if (gid) { DB.run('UPDATE goal SET name=?,target=?,due=?,memo=?,done=? WHERE id=?', [...vals, gid]); return gid; }
    const sort = DB.val('SELECT COALESCE(MAX(sort),0)+1 FROM goal');
    return DB.run('INSERT INTO goal(name,target,due,memo,done,sort,created) VALUES(?,?,?,?,?,?,?)', [...vals, sort, U.today()]).lastId;
  }
  const deleteGoal = gid => DB.run('DELETE FROM goal WHERE id=?', [gid]);
  const addGoalTx = (gid, date, amount, memo) => DB.run('INSERT INTO goal_tx(goal_id,date,amount,memo) VALUES(?,?,?,?)', [gid, date, parseInt(amount || 0, 10), memo || '']).lastId;
  const deleteGoalTx = tid => DB.run('DELETE FROM goal_tx WHERE id=?', [tid]);
  const goalTxs = gid => DB.q('SELECT * FROM goal_tx WHERE goal_id=? ORDER BY date, id', [gid]);
  function goalStatus(g, today) {
    today = today || U.today();
    const saved = DB.val('SELECT COALESCE(SUM(amount),0) FROM goal_tx WHERE goal_id=?', [g.id]);
    const target = g.target;
    const left = Math.max(0, target - saved);
    const p = target > 0 ? Math.min(100, Math.floor(saved * 100 / target)) : 0;
    let daysLeft = null, monthsLeft = null;
    if (g.due) {
      daysLeft = U.ord(g.due) - U.ord(today);
      const [dy, dm] = U.parts(g.due), [ty, tm] = U.parts(today);
      monthsLeft = daysLeft >= 0 ? Math.max(1, (dy - ty) * 12 + (dm - tm) + 1) : 0;
    }
    return { saved, left, pct: Math.max(0, p), days_left: daysLeft, per_month: monthsLeft ? Math.ceil(left / monthsLeft) : 0 };
  }

  const KINDS = { lend: '빌려준 돈', borrow: '빌린 돈' };
  const debts = includeDone => DB.q('SELECT * FROM debt' + (includeDone === false ? ' WHERE done=0' : '') + ' ORDER BY done, date, id');
  function saveDebt(d, did) {
    if (!KINDS[d.kind]) throw new Error('빌려준 돈인지 빌린 돈인지 고르세요');
    const person = (d.person || '').trim();
    if (!person) throw new Error('누구인지 입력하세요');
    const amount = parseInt(d.amount || 0, 10);
    if (!(amount > 0)) throw new Error('금액을 입력하세요');
    const vals = [d.kind, person, amount, d.date || U.today(), d.due || null, (d.memo || '').trim(), d.done ? 1 : 0];
    if (did) { DB.run('UPDATE debt SET kind=?,person=?,amount=?,date=?,due=?,memo=?,done=? WHERE id=?', [...vals, did]); return did; }
    return DB.run('INSERT INTO debt(kind,person,amount,date,due,memo,done) VALUES(?,?,?,?,?,?,?)', vals).lastId;
  }
  const deleteDebt = did => DB.run('DELETE FROM debt WHERE id=?', [did]);
  const debtPaid = did => DB.val('SELECT COALESCE(SUM(amount),0) FROM debt_pay WHERE debt_id=?', [did]);
  function addPayment(did, date, amount, memo) {
    DB.tx(() => {
      DB.run('INSERT INTO debt_pay(debt_id,date,amount,memo) VALUES(?,?,?,?)', [did, date, parseInt(amount || 0, 10), memo || '']);
      const d = DB.one('SELECT amount FROM debt WHERE id=?', [did]);
      if (d && debtPaid(did) >= d.amount) DB.run('UPDATE debt SET done=1 WHERE id=?', [did]);
    });
  }
  function deletePayment(pid) {
    DB.tx(() => {
      const r = DB.one('SELECT debt_id FROM debt_pay WHERE id=?', [pid]);
      DB.run('DELETE FROM debt_pay WHERE id=?', [pid]);
      if (r) {
        const d = DB.one('SELECT amount FROM debt WHERE id=?', [r.debt_id]);
        if (d && debtPaid(r.debt_id) < d.amount) DB.run('UPDATE debt SET done=0 WHERE id=?', [r.debt_id]);
      }
    });
  }
  const payments = did => DB.q('SELECT * FROM debt_pay WHERE debt_id=? ORDER BY date, id', [did]);
  const debtLeft = d => Math.max(0, d.amount - debtPaid(d.id));
  function debtTotals() {
    let lend = 0, borrow = 0;
    for (const d of debts(false)) { if (d.kind === 'lend') lend += debtLeft(d); else borrow += debtLeft(d); }
    return [lend, borrow];
  }
  return { goals, saveGoal, deleteGoal, addGoalTx, deleteGoalTx, goalTxs, goalStatus,
    KINDS, debts, saveDebt, deleteDebt, addPayment, deletePayment, payments, debtPaid, debtLeft, debtTotals };
})();

// ════════════════ 내역 사진 (services/attach.py) — 사진 바이트는 자바(NativeBridge)가 직접 다룸 ════════════════
const Att = (() => {
  const listFor = eid => DB.q('SELECT id, name, mime, created, length(data) AS size FROM attachment WHERE entry_id=? ORDER BY id', [eid]);
  const del = aid => DB.run('DELETE FROM attachment WHERE id=?', [aid]);
  function counts(ids) {
    const out = {};
    for (let i = 0; i < ids.length; i += 500) {
      const part = ids.slice(i, i + 500);
      for (const r of DB.q(`SELECT entry_id, COUNT(*) AS n FROM attachment WHERE entry_id IN (${part.map(() => '?').join(',')}) GROUP BY entry_id`, part)) out[r.entry_id] = r.n;
    }
    return out;
  }
  const N = () => window.GagyebuNative;
  /** 사진 붙이기 (b64: JPEG). 새 번호 */
  function add(eid, b64, name) {
    const r = JSON.parse(N().addAttachment(eid, b64, name || ''));
    if (!r.ok) throw new Error(r.error || '사진을 넣지 못했습니다');
    return r.id;
  }
  /** 사진 내용 base64 (없으면 '') */
  function data(aid) {
    try { const r = JSON.parse(N().attachmentData(aid)); return r.ok ? r.b64 : ''; } catch (_) { return ''; }
  }
  return { listFor, del, counts, add, data };
})();
