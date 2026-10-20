/* 1.7.0 기능 화면: 문자로 넣기 · 자주 쓰는 내역 · 내역 사진 · 예산 막대/예산 정하기 · 통장끼리 이체 ·
   저축 목표 · 빌려준 돈/빌린 돈 · 이달 리포트 · 태그 (PC판 ui/extras.py 와 같은 기능, 계산은 svc-extra.js) */
'use strict';
const Extra = (() => {
  const sd = () => Rep.settleDay();
  const pctText = p => (p === null || p === undefined ? '—' : `${p}%`);
  /** 막대 색: 80% 까지 보통, 80~100% 주의, 넘으면 지출색 */
  const barCls = p => (p > 100 ? 'over' : p >= 80 ? 'warn' : '');
  const bar = (p, cls) => `<div class="pbar ${cls || ''}"><i class="${barCls(p || 0)}" style="width:${Math.max(0, Math.min(100, p || 0))}%"></i></div>`;

  // ── 예산 알림 (저장 전·후 비교) ──
  const spentBefore = (lid, code, d) => { try { return code ? Ins.codeSpent(lid, code, d, sd()) : 0; } catch (_) { return 0; } };
  const alertAfter = (lid, code, d, before) => { try { return Ins.budgetAlert(lid, code, d, before, sd()); } catch (_) { return null; } };

  // ── 가계부 화면의 예산 막대 (화면 구성 'budget') ──
  function budgetCard(lid, y, m) {
    if (App.pref('budget_card') === 'false') return null;
    const today = U.today();
    const bp = Ins.budgetProgress(lid, y, m, sd(), today);
    const { start, end } = bp;
    let ns = '';
    if (start <= today) {
      const upto = end < today ? end : today;
      const n = Ins.noSpendDays(lid, start, upto).length;
      const streak = start <= today && today <= end ? Ins.noSpendStreak(lid, today) : 0;
      ns = `<div class="bc-ns">${UI.icon('heart', 'on')}무지출 <b>${n}일</b>${streak >= 2 ? ` · 오늘까지 ${streak}일째` : streak === 1 ? ' · 오늘은 아직 안 썼어요' : ''}</div>`;
    }
    const per = sd() !== 1 ? ` <span class="muted tiny">(${start.slice(5).replace('-', '.')}~${end.slice(5).replace('-', '.')})</span>` : '';
    let html;
    if (!bp.rows.length) {
      html = `<div class="box bcard empty"><div class="bc-h"><b>${m}월 예산</b>${per}<button class="btn sm" data-bset>예산 정하기</button></div>
        <div class="small muted">계정별 예산을 정하면 얼마나 썼는지 막대로 보여 주고, 80%·100%를 넘을 때 알려 드려요.</div>${ns}</div>`;
    } else {
      const over = bp.left < 0;
      const sub = over ? `<span class="out">예산보다 ${UI.money(-bp.left)}원 더 썼어요</span>`
        : start <= today && today <= end ? `남은 돈 ${UI.money(bp.left)}원 · 하루 ${UI.money(bp.per_day)}원씩 (${bp.days_left}일 남음)` : `남은 돈 ${UI.money(bp.left)}원`;
      html = `<div class="box bcard tap" data-bopen><div class="bc-h"><b>${m}월 예산</b>${per}<span class="bc-t"><b>${UI.money(bp.spent)}</b> / ${UI.money(bp.budget)} <span class="${over ? 'out' : 'muted'}">(${pctText(bp.pct)})</span></span></div>
        ${bar(bp.pct, 'big')}<div class="small muted bc-sub">${sub}</div>
        <div class="bc-rows">${bp.rows.slice(0, 3).map(r => `<div class="bc-r"><span class="nm ellipsis">${U.esc(r.name)}</span><span class="v ${r.left < 0 ? 'out' : ''}">${pctText(r.pct)}</span>${bar(r.pct)}</div>`).join('')}</div>
        ${bp.rows.length > 3 ? `<div class="tiny muted">외 ${bp.rows.length - 3}개 · 눌러서 모두 보기</div>` : ''}${ns}</div>`;
    }
    const el = UI.el(html);
    const b = UI.$('[data-bset]', el);
    if (b) b.onclick = e => { e.stopPropagation(); budgetSheet(lid, y, m); };
    if (el.dataset.bopen !== undefined) el.onclick = () => budgetDetail(lid, y, m);
    return el;
  }
  function budgetDetail(lid, y, m) {
    const bp = Ins.budgetProgress(lid, y, m, sd(), U.today());
    const body = `<div class="small muted" style="margin-bottom:6px">${bp.start} ~ ${bp.end} · ${UI.money(bp.spent)} / ${UI.money(bp.budget)}원 (${pctText(bp.pct)})</div>
      <ul class="list blist">${bp.rows.map(r => `<li><div class="grow"><div class="main-t">${U.esc(r.name)} <span class="small ${r.left < 0 ? 'out' : 'muted'}">${UI.money(r.spent)} / ${UI.money(r.budget)}</span></div>${bar(r.pct)}</div>
        <div class="right nowrap"><b class="${r.left < 0 ? 'out' : ''}">${pctText(r.pct)}</b><div class="tiny muted">${r.left < 0 ? `${UI.money(-r.left)} 넘음` : `남음 ${UI.money(r.left)}`}</div></div></li>`).join('')}</ul>`;
    UI.sheet({ title: `${y}년 ${m}월 예산`, body, full: true, buttons: [
      { label: '이달 리포트', onClick: () => { Pages.report.openInsight(y, m); } },
      { label: '예산 정하기', cls: 'pri', onClick: () => { budgetSheet(lid, y, m); } }] });
  }
  /** 계정별 그 달 예산 정하기 (같은 금액을 다음 달들에도) */
  function budgetSheet(lid, y, m) {
    const [py, pm] = U.addMonths(y, m, -1);
    const [ps, pe] = U.settlePeriod(py, pm, sd());
    const prev = Rep.sumByCode(lid, ps, pe);
    const cur = Rep.budgets(lid, U.ym(y, m)), prevBud = Rep.budgets(lid, U.ym(py, pm));
    const cats = L.categories(lid).filter(c => !U.isIncomeCode(c.code));
    const spans = [[1, `${m}월만`]].concat(m < 12 ? [[13 - m, `${m}월부터 12월까지 같게`]] : []).concat([[12, `${m}월부터 12달 동안 같게`]]);
    const body = UI.el(`<div><div class="small muted" style="margin-bottom:6px">쓰지 않을 계정은 비워 두세요. 금액 옆 계산기로 300000/4 처럼 계산도 됩니다.</div>
      <div class="form bset">${cats.map(c => `<div class="f bs-r"><label class="l">${U.esc(c.code)} ${U.esc(c.name)} <span class="tiny muted">지난달 ${UI.money(prev[c.code] || 0)}</span></label>
        <input type="text" inputmode="numeric" class="money" data-c="${U.esc(c.code)}" value="${cur[c.code] ? UI.money(cur[c.code]) : ''}" placeholder="0"></div>`).join('')}</div>
      <div class="row" style="margin:4px 0 8px"><button class="btn sm" data-prev>지난달 예산 가져오기</button><b class="grow right bs-sum"></b></div>
      <div class="f"><label class="l">적용할 달</label><select class="inp" data-span>${spans.map(([n, l]) => `<option value="${n}">${l}</option>`).join('')}</select></div></div>`);
    UI.bindMoney(body);
    const sum = () => { let t = 0; try { UI.$$('[data-c]', body).forEach(x => { t += U.calcMoney(x.value); }); UI.$('.bs-sum', body).textContent = `합계 ${UI.money(t)}원`; } catch (_) { UI.$('.bs-sum', body).textContent = ''; } };
    UI.on(body, '[data-c]', 'change', sum);
    UI.on(body, '[data-c]', 'blur', sum);
    UI.$('[data-prev]', body).onclick = () => {
      if (!Object.keys(prevBud).length) { UI.toast('지난달에 정한 예산이 없습니다'); return; }
      UI.$$('[data-c]', body).forEach(x => { const v = prevBud[x.dataset.c]; x.value = v ? UI.money(v) : ''; });
      sum();
    };
    sum();
    UI.sheet({ title: `${y}년 ${m}월 예산 정하기`, body, full: true, buttons: [{ label: '취소' }, { label: '저장', cls: 'pri', onClick: () => {
      const vals = {};
      try { UI.$$('[data-c]', body).forEach(x => { vals[x.dataset.c] = U.calcMoney(x.value); }); } catch (_) { UI.toast('금액은 숫자(또는 계산식)로 입력하세요.'); return false; }
      if (Object.values(vals).some(v => v < 0)) { UI.toast('예산은 0 이상으로 입력하세요.'); return false; }
      const n = Number(UI.$('[data-span]', body).value);
      const yms = [];
      let yy = y, mm = m;
      for (let i = 0; i < n; i++) { yms.push(U.ym(yy, mm)); [yy, mm] = U.addMonths(yy, mm, 1); }
      Rep.setBudgets(lid, yms, vals);
      App.dataChanged();
      UI.toast(n > 1 ? `${n}달 예산을 저장했습니다` : '예산을 저장했습니다');
      return undefined;
    } }] });
  }

  // ── 문자로 넣기 ──
  const SMS_HINT = '[Web발신]\n신한카드(1234)승인 홍*동 12,500원 일시불 10/19 08:41 스타벅스 누적345,600원';
  const looksSms = t => /\d[\d,]*\s*원/.test(t || '') && /\d{1,2}[./-]\d{1,2}/.test(t || '');
  function smsSheet(text, onSaved) {
    const lid = App.lid;
    const body = UI.el(`<div class="smsbox"><textarea class="inp" data-t rows="5" placeholder="카드·은행 알림 문자를 길게 눌러 복사한 뒤 여기에 붙여넣으세요. 여러 개를 한꺼번에 넣어도 됩니다.\n\n예)\n${U.esc(SMS_HINT)}"></textarea>
      <div class="row" style="margin:6px 0"><button class="btn sm" data-paste>붙여넣기</button><button class="btn sm pri" data-read>읽기</button><button class="btn sm" data-clear>지우기</button></div>
      <div class="small muted sms-st">문자 앱에서 문자를 길게 눌러 '공유 → 우리집 가계부'로 보내도 됩니다.</div><div class="sms-list"></div></div>`);
    const ta = UI.$('[data-t]', body), list = UI.$('.sms-list', body), st = UI.$('.sms-st', body);
    let found = [];
    const dup = e => !!DB.one('SELECT 1 AS x FROM entry WHERE ledger_id=? AND date=? AND item=? AND income=? AND expense=? LIMIT 1', [lid, e.date, e.item, e.income, e.expense]);
    function read() {
      found = Sms.parse(ta.value, U.today()).map(p => {
        const e = Sms.toEntry(p);
        const isDup = p.ok && dup(e);
        return { p, e, dup: isDup, on: p.ok && !isDup, code: Sms.guessCode(lid, p.item, p.kind === 'in') };
      });
      if (!found.length) { list.innerHTML = ''; st.textContent = '문자에서 내역을 찾지 못했습니다. 카드·은행 알림 문자를 그대로 붙여넣었는지 확인하세요.'; return; }
      const nDup = found.filter(x => x.dup).length, nBad = found.filter(x => !x.p.ok).length;
      st.textContent = [`${found.length}건을 찾았어요`, nDup ? `이미 넣은 것 ${nDup}건은 빼 두었어요` : '', nBad ? `날짜나 금액을 못 찾은 ${nBad}건은 고친 뒤 체크하세요` : ''].filter(Boolean).join(' · ') + '.';
      list.innerHTML = found.map((x, i) => {
        const amt = x.e.income || x.e.expense;
        return `<div class="sms-c${x.on ? '' : ' off'}" data-i="${i}"><label class="check sc-h"><input type="checkbox" data-on${x.on ? ' checked' : ''}>
          <span class="${x.p.kind === 'in' ? 'in' : 'out'} bold">${x.p.kind === 'in' ? '입금' : x.p.kind === 'cancel' ? '승인 취소' : '지출'}</span>
          <span class="tiny muted">${U.esc(x.e.memo)}${x.dup ? ' · 이미 있음' : x.p.ok ? '' : ' · 확인 필요'}</span></label>
          <div class="row"><input class="inp" type="date" data-f="date" value="${U.esc(x.e.date)}"><input class="inp money grow" type="text" inputmode="numeric" data-f="amt" value="${amt ? UI.money(amt) : ''}" placeholder="금액"></div>
          <div class="row"><input class="inp grow" type="text" data-f="item" value="${U.esc(x.e.item)}" placeholder="품목"><select class="inp" data-f="code">${UI.codeOptions(lid, x.code, x.p.kind === 'in' ? 'in' : 'out')}</select></div></div>`;
      }).join('');
      UI.bindMoney(list);
      UI.on(list, '[data-on]', 'change', (e, cb) => cb.closest('.sms-c').classList.toggle('off', !cb.checked));
    }
    UI.$('[data-read]', body).onclick = read;
    UI.$('[data-clear]', body).onclick = () => { ta.value = ''; list.innerHTML = ''; found = []; };
    UI.$('[data-paste]', body).onclick = () => {
      const fail = () => UI.toast('칸을 길게 눌러 붙여넣기 하세요');
      try {
        if (!navigator.clipboard || !navigator.clipboard.readText) { fail(); return; }
        navigator.clipboard.readText().then(t => { if (t) { ta.value = t; read(); } else fail(); }, fail);
      } catch (_) { fail(); }
    };
    if (text) { ta.value = text; setTimeout(read, 0); }
    UI.sheet({ title: '문자로 넣기', body, full: true, buttons: [{ label: '닫기' }, { label: '체크한 것 저장', cls: 'pri', onClick: () => {
      const rows = UI.$$('.sms-c', list).filter(c => UI.$('[data-on]', c).checked);
      if (!rows.length) { UI.toast('저장할 내역을 체크하세요'); return false; }
      const vals = [];
      for (const c of rows) {
        const x = found[Number(c.dataset.i)], g = k => UI.$(`[data-f=${k}]`, c).value.trim();
        const n = Number(c.dataset.i) + 1;
        let amt;
        try { amt = U.calcMoney(g('amt')); } catch (_) { UI.toast(`${n}번째: 금액은 숫자로 입력하세요`); return false; }
        if (!U.isValidIso(g('date'))) { UI.toast(`${n}번째: 날짜를 확인하세요`); return false; }
        if (!g('item')) { UI.toast(`${n}번째: 품목을 입력하세요`); return false; }
        if (!amt) { UI.toast(`${n}번째: 금액을 입력하세요`); return false; }
        if (!g('code')) { UI.toast(`${n}번째: 계정과목을 고르세요`); return false; }
        const inc = x.p.kind === 'in';
        const sign = x.p.kind === 'cancel' ? -Math.abs(amt) : amt;
        vals.push({ date: g('date'), item: g('item'), income: inc ? amt : 0, expense: inc ? 0 : sign, code: g('code'), memo: x.e.memo });
      }
      const alerts = [];
      DB.tx(() => {
        for (const v of vals) {
          const before = spentBefore(lid, v.code, v.date);
          L.addEntry(lid, v);
          const a = alertAfter(lid, v.code, v.date, before);
          if (a && !alerts.includes(a)) alerts.push(a);
        }
      });
      App.dataChanged();
      UI.toast(`${vals.length}건을 넣었어요` + (alerts.length ? ` · ⚠ ${alerts[alerts.length - 1]}` : ''), alerts.length ? 4500 : 2200);
      if (onSaved) onSaved();
      return undefined;
    } }] });
  }

  // ── 자주 쓰는 내역 ──
  const favLabel = f => `${f.item}${f.income ? ` +${UI.money(f.income)}` : f.expense ? ` ${UI.money(f.expense)}` : ''}`;
  function favoritesSheet() {
    const lid = App.lid;
    const body = UI.el('<div><div class="small muted" style="margin-bottom:6px">새 내역 입력 창 위쪽의 ★ 칩을 누르면 칸이 한 번에 채워집니다. 넣으려면 입력 칸을 채운 뒤 [＋★]를 누르세요.</div><ul class="list favl"></ul></div>');
    const ul = UI.$('.favl', body);
    function draw() {
      const cmap = L.categoryMap(lid), fs = L.favorites(lid);
      ul.innerHTML = fs.length ? fs.map((f, i) => `<li data-id="${f.id}"><div class="grow"><div class="main-t ellipsis">★ ${U.esc(f.item)}</div>
        <div class="sub ellipsis">${[f.code ? L.codeLabel(cmap, f.code) : '', f.memo].filter(Boolean).map(U.esc).join(' · ')}</div></div>
        <div class="nowrap ${f.income ? 'in' : 'out'} bold">${f.income ? '+' + UI.money(f.income) : f.expense ? UI.money(f.expense) : ''}</div>
        <button class="iconbtn" data-mv="-1" aria-label="위로"${i ? '' : ' disabled'}>▲</button><button class="iconbtn" data-mv="1" aria-label="아래로"${i < fs.length - 1 ? '' : ' disabled'}>▼</button>
        <button class="iconbtn" data-del aria-label="지우기">✕</button></li>`).join('') : `<li class="muted">아직 없어요</li>`;
      UI.on(ul, '[data-mv]', 'click', (e, b) => { L.moveFavorite(lid, Number(b.closest('li').dataset.id), Number(b.dataset.mv)); draw(); });
      UI.on(ul, '[data-del]', 'click', (e, b) => { L.deleteFavorite(Number(b.closest('li').dataset.id)); draw(); });
    }
    draw();
    UI.sheet({ title: '자주 쓰는 내역 정리', body, full: true });
  }

  // ── 내역 사진 ──
  /** 입력 창 안의 사진 칸. eid 가 있으면 바로 자료 파일에, 없으면(새 내역) pending 에 두었다가 save(eid) */
  function photoField(eid) {
    const pending = [];
    const el = UI.el(`<div class="f"><label class="l">사진 (영수증)</label><div class="photos"><div class="ph-list"></div>
      <button type="button" class="chip" data-ph="album">${UI.icon('upload')}앨범</button><button type="button" class="chip" data-ph="camera">${UI.icon('camera')}찍기</button></div></div>`);
    const box = UI.$('.ph-list', el);
    const items = () => (eid ? Att.listFor(eid).map(a => ({ id: a.id, name: a.name })) : pending.map((p, i) => ({ i, name: p.name, b64: p.b64 })));
    function draw() {
      const it = items();
      box.innerHTML = it.map((x, k) => `<button type="button" class="phth" data-k="${k}"><img alt="${U.esc(x.name || '사진')}" src="data:image/jpeg;base64,${x.b64 || Att.data(x.id)}"></button>`).join('');
      UI.on(box, '.phth', 'click', (e, b) => view(it[Number(b.dataset.k)]));
    }
    function view(x) {
      const b64 = x.b64 || Att.data(x.id);
      UI.sheet({ title: x.name || '사진', full: true, body: `<div class="ph-view"><img alt="" src="data:image/jpeg;base64,${b64}"></div>`, buttons: [
        { label: '지우기', cls: 'danger', onClick: close => {
          UI.confirm('이 사진을 지울까요?', '지우기', true).then(ok => {
            if (!ok) return;
            if (eid) { Att.del(x.id); App.dataChanged(); } else pending.splice(x.i, 1);
            close();
            draw();
          });
          return false;
        } }, { label: '닫기', cls: 'pri' }] });
    }
    UI.on(el, '[data-ph]', 'click', (e, b) => {
      App.nativeAsync('pickPhoto', b.dataset.ph === 'camera').then(r => {
        if (!r.ok) { if (!r.cancel) UI.alert('사진을 넣지 못했습니다.\n' + r.error); return; }
        if (eid) {
          try { Att.add(eid, r.b64, r.name); } catch (err) { UI.alert(err.message); return; }
          App.dataChanged();
        } else pending.push({ b64: r.b64, name: r.name });
        draw();
        UI.toast(`사진을 넣었어요 (${Math.round((r.size || 0) / 1024)}KB)`);
      });
    });
    draw();
    return { el, save: id => { for (const p of pending.splice(0)) Att.add(id, p.b64, p.name); draw(); }, count: () => items().length };
  }

  // ── 자산: 통장끼리 이체 ──
  function transferSheet(fromId) {
    const banks = A.accounts('bank').filter(a => a.active);
    if (banks.length < 2) { UI.alert('사용중인 은행통장이 두 개 이상 있어야 합니다. 통장을 먼저 추가하세요.'); return; }
    const opts = banks.map(a => [String(a.id), `${`${a.company} ${a.name}`.trim()} (잔액 ${UI.money(A.accountBalance(a.id))})`]);
    const from = String(fromId || banks[0].id), to = String((banks.find(a => String(a.id) !== from) || banks[1]).id);
    UI.formSheet({ title: '통장끼리 이체', full: true, saveLabel: '이체 기록',
      fields: [{ k: 'from', label: '보내는 통장', type: 'select', options: opts }, { k: 'to', label: '받는 통장', type: 'select', options: opts },
        { k: 'date', label: '날짜', type: 'date', req: true }, { k: 'amount', label: '금액', type: 'money' }, { k: 'memo', label: '메모', type: 'text' }],
      values: { from, to, date: U.today() },
      extra: '<div class="small muted">보내는 통장에 출금, 받는 통장에 입금이 짝으로 기록됩니다. 가계부(수입·지출)에는 넣지 않아 이달 지출이 부풀지 않아요. 한쪽을 고치거나 지우면 짝도 같이 바뀝니다.</div>',
      onSave: v => { A.transfer(Number(v.from), Number(v.to), v.date, v.amount, v.memo); App.dataChanged(); UI.toast('이체를 기록했습니다'); } });
  }

  // ── 결산: 이달 리포트 ──
  function insightHtml(lid, y, m) {
    const i = Ins.monthInsight(lid, y, m, sd(), U.today());
    const word = (p, more = '많이', less = '적게') => (p === null ? '' : p === 0 ? '똑같이' : `<b class="${p > 0 ? 'out' : 'in'}">${Math.abs(p)}% ${p > 0 ? more : less}</b>`);
    const per = `${i.start.replace(/-/g, '.')} ~ ${i.end.slice(5).replace('-', '.')}${sd() !== 1 ? ` · 결산일 ${sd()}일 기준` : ''}`;
    if (!i.days) return `<div class="ins"><div class="small muted">${per}</div><div class="empty small">아직 시작하지 않은 달입니다.</div></div>`;
    const li = [];
    if (i.prev_same) li.push(`${i.current ? '지난달 같은 기간' : '지난달'}(${UI.money(i.prev_same)}원)보다 ${word(i.change_pct)} 썼어요`);
    else if (i.expense) li.push('지난달 같은 기간에는 쓴 돈이 없어요');
    li.push(`하루 평균 ${UI.money(i.daily_avg)}원`);
    if (i.current && i.days < i.total_days) li.push(`이대로 쓰면 이달 지출은 약 <b>${UI.money(i.projected)}원</b>${i.prev_full ? ` (지난달 전체 ${UI.money(i.prev_full)}원)` : ''}`);
    if (i.biggest) li.push(`가장 큰 지출: ${U.esc(i.biggest.item)} ${UI.money(i.biggest.amount)}원 (${i.biggest.date.slice(5).replace('-', '.')})`);
    li.push(`무지출 ${i.no_spend}일${i.current && i.streak >= 1 ? ` · 오늘까지 ${i.streak}일 이어지는 중` : ''}`);
    let h = `<div class="ins"><div class="small muted">${per}</div>
      <div class="ins-big">${i.current ? `오늘까지 <b>${i.days}일</b> 동안` : '한 달 동안'} <b class="out">${UI.money(i.expense)}원</b> 썼어요 <span class="small muted">(수입 ${UI.money(i.income)}원)</span></div>
      <ul class="ins-l">${li.map(x => `<li>${x}</li>`).join('')}</ul>`;
    if (i.top.length) {
      h += `<div class="section-t">많이 쓴 곳</div><ul class="list">${i.top.map((t, n) => `<li><span class="chip">${n + 1}</span><div class="grow"><div class="main-t">${U.esc(t.name)}</div>
        <div class="sub">${t.prev ? `지난달(${UI.money(t.prev)}원)보다 ${word(t.change_pct)}` : '지난달엔 없음'}</div></div><b class="out nowrap">${UI.money(t.amount)}원</b></li>`).join('')}</ul>`;
    }
    const bp = i.budget;
    if (bp.rows.length) {
      h += `<div class="section-t">예산 <span class="small muted">${UI.money(bp.spent)} / ${UI.money(bp.budget)} (${pctText(bp.pct)})</span></div>${bar(bp.pct, 'big')}
        <ul class="list blist">${bp.rows.map(r => `<li><div class="grow"><div class="main-t">${U.esc(r.name)} <span class="small muted">${UI.money(r.spent)} / ${UI.money(r.budget)}</span></div>${bar(r.pct)}</div><b class="${r.left < 0 ? 'out' : ''}">${pctText(r.pct)}</b></li>`).join('')}</ul>`;
    }
    return h + '</div>';
  }

  // ── 결산: 태그 ──
  function tagsView(c, lid, s, rerender) {
    const range = s.tagAll ? [null, null] : [U.iso(s.y, s.m, 1), U.iso(s.y, s.m, U.monthEnd(s.y, s.m))];
    const top = UI.el(`<div class="row" style="margin-bottom:6px"><span class="chip ${s.tagAll ? 'on' : ''}" data-all>전체 기간</span><span class="small muted grow">품목이나 메모에 #여행 #회사 처럼 쓰면 계정과 따로 모아 봅니다.</span></div>`);
    UI.$('[data-all]', top).onclick = () => { s.tagAll = !s.tagAll; rerender(); };
    c.appendChild(top);
    if (!s.tagAll) c.appendChild(UI.monthNav(s.y, s.m, (y, m) => { s.y = y; s.m = m; rerender(); }));
    const rows = L.tagSummary(lid, range[0], range[1]);
    if (!rows.length) { c.appendChild(UI.el(UI.empty('아직 태그를 쓴 내역이 없어요.\n품목이나 메모에 #여행 처럼 써 보세요.', 'b30'))); return; }
    c.appendChild(UI.el(`<ul class="list tagl">${rows.map(r => `<li class="tap" data-tag="${U.esc(r.tag)}">${UI.icon('tag')}<div class="grow"><div class="main-t">#${U.esc(r.tag)}</div><div class="sub">${r.count}건</div></div>
      <div class="right nowrap">${r.expense ? `<div class="out bold">${UI.money(r.expense)}</div>` : ''}${r.income ? `<div class="in small">+${UI.money(r.income)}</div>` : ''}</div></li>`).join('')}</ul>`));
    UI.on(c, '[data-tag]', 'click', (e, li) => {
      const tag = li.dataset.tag, cmap = L.categoryMap(lid);
      const list = L.entriesWithTag(lid, tag, range[0], range[1]);
      const sh = UI.sheet({ title: `#${tag} (${list.length}건)`, full: true,
        body: `<ul class="list">${list.map(x => Entry.rowHtml(x, null, true, cmap)).join('')}</ul>` });
      UI.on(sh.body, 'li[data-id]', 'click', (ev, row) => { sh.close(); Entry.open({ entry: list.find(x => x.id === Number(row.dataset.id)) }); });
    });
  }

  return { budgetCard, budgetSheet, budgetDetail, smsSheet, looksSms, favoritesSheet, favLabel, photoField, transferSheet, insightHtml, tagsView,
    spentBefore, alertAfter, bar, pctText };
})();

// ════════ 저축 목표 ════════
Pages.goals = (() => {
  function render(c) {
    const today = U.today();
    c.appendChild(UI.el('<div class="small muted" style="margin-bottom:6px">여행 자금·비상금처럼 목표를 정하고 모을 때마다 기록하세요. 통장 잔액과는 따로 셉니다.</div>'));
    const gs = Goal.goals();
    if (!gs.length) c.appendChild(UI.el(UI.empty('아직 저축 목표가 없어요\n＋ 버튼으로 만들어 보세요', 'a04')));
    else {
      c.appendChild(UI.el(`<ul class="list goall">${gs.map(g => {
        const s = Goal.goalStatus(g, today);
        const due = g.due ? (s.days_left >= 0 ? `D-${s.days_left}` : '날짜 지남') : '';
        return `<li class="tap${g.done ? ' muted' : ''}" data-id="${g.id}">${UI.icon('target')}<div class="grow"><div class="main-t ellipsis">${U.esc(g.name)}${g.done ? ' ✓' : ''}</div>
          ${g.target ? Extra.bar(s.pct) : ''}<div class="sub">${UI.money(s.saved)}${g.target ? ` / ${UI.money(g.target)}원 (${s.pct}%)` : '원 모음'}${due ? ` · ${due}` : ''}${s.per_month && !g.done ? ` · 한 달에 ${UI.money(s.per_month)}원씩` : ''}</div></div></li>`;
      }).join('')}</ul>`));
      UI.on(c, 'li[data-id]', 'click', (e, li) => goalSheet(gs.find(g => g.id === Number(li.dataset.id))));
    }
    App.fab(() => editGoal(null), '목표 추가');
  }
  const FIELDS = [{ k: 'name', label: '목표 이름', type: 'text', req: true }, { k: 'target', label: '목표 금액', type: 'money' },
    { k: 'due', label: '목표 날짜 (없으면 비움)', type: 'date' }, { k: 'memo', label: '메모', type: 'text' }, { k: 'done', label: '이뤘어요 (끝난 목표)', type: 'check' }];
  function editGoal(g) {
    UI.formSheet({ title: g ? '저축 목표 수정' : '새 저축 목표', fields: FIELDS, values: g || {}, full: true,
      onSave: v => { Goal.saveGoal(v, g ? g.id : null); App.dataChanged(); },
      onDelete: g ? close => UI.confirm(`'${g.name}' 목표와 모은 기록을 모두 지울까요?`, '삭제', true).then(ok => { if (ok) { Goal.deleteGoal(g.id); close(); App.dataChanged(); } }) : null });
  }
  function goalSheet(g) {
    const s = Goal.goalStatus(g, U.today());
    const txs = Goal.goalTxs(g.id).reverse();
    const body = UI.el(`<div><div class="box"><div class="kv"><b>${U.esc(g.name)}</b><span>${g.due ? U.esc(g.due) : ''}</span></div>${g.target ? Extra.bar(s.pct, 'big') : ''}
      <div class="kv small"><span>모은 돈 ${UI.money(s.saved)}원${g.target ? ` / ${UI.money(g.target)}원` : ''}</span><b>${g.target ? s.pct + '%' : ''}</b></div>
      ${s.left && s.per_month && !g.done ? `<div class="small muted">목표 날짜까지 한 달에 ${UI.money(s.per_month)}원씩</div>` : !s.left && g.target ? '<div class="small in">목표를 다 모았어요!</div>' : ''}</div>
      <div class="form"><div class="row"><input class="inp" type="date" data-k="date" value="${U.today()}"><input class="inp money grow" type="text" inputmode="numeric" data-k="amount" placeholder="금액"></div>
      <div class="row" style="margin-top:6px"><button class="btn sm pri" data-add="1">모았어요 (+)</button><button class="btn sm" data-add="-1">꺼내 썼어요 (−)</button></div></div>
      <div class="section-t">기록 (${txs.length})</div>${txs.length ? `<ul class="list">${txs.map(t => `<li class="tap" data-t="${t.id}"><div class="grow">${t.date}${t.memo ? ` · ${U.esc(t.memo)}` : ''}</div><b class="${t.amount < 0 ? 'out' : 'in'}">${t.amount > 0 ? '+' : ''}${UI.money(t.amount)}</b></li>`).join('')}</ul>` : '<div class="muted small">아직 기록이 없어요</div>'}</div>`);
    UI.bindMoney(body);
    const sh = UI.sheet({ title: '저축 목표', body, full: true, buttons: [{ label: '목표 수정', onClick: () => { editGoal(g); } }, { label: '닫기', cls: 'pri' }] });
    UI.on(body, '[data-add]', 'click', (e, b) => {
      let amt;
      try { amt = U.calcMoney(UI.$('[data-k=amount]', body).value); } catch (_) { UI.toast('금액은 숫자로 입력하세요'); return; }
      const d = UI.$('[data-k=date]', body).value;
      if (!amt || amt <= 0) { UI.toast('금액을 입력하세요'); return; }
      if (!U.isValidIso(d)) { UI.toast('날짜를 확인하세요'); return; }
      Goal.addGoalTx(g.id, d, Number(b.dataset.add) * amt);
      sh.close();
      App.dataChanged();
      goalSheet(DB.one('SELECT * FROM goal WHERE id=?', [g.id]));
    });
    UI.on(body, 'li[data-t]', 'click', (e, li) => UI.confirm('이 기록을 지울까요?', '지우기', true).then(ok => {
      if (!ok) return;
      Goal.deleteGoalTx(Number(li.dataset.t));
      sh.close();
      App.dataChanged();
      goalSheet(DB.one('SELECT * FROM goal WHERE id=?', [g.id]));
    }));
  }
  return { title: '저축 목표', sticker: 'a04', sub: '차곡차곡 모으는 중', render, tab: 'assets' };
})();

// ════════ 빌려준 돈·빌린 돈 ════════
Pages.debts = (() => {
  const s = { done: false };
  function render(c) {
    const [lend, borrow] = Goal.debtTotals();
    c.appendChild(UI.el(`<div class="box"><div class="kv"><span>받을 돈 (빌려준 돈)</span><b class="in">${UI.money(lend)}원</b></div>
      <div class="kv"><span>갚을 돈 (빌린 돈)</span><b class="out">${UI.money(borrow)}원</b></div><div class="tiny muted">자산관리의 자산 합계·부채 합계에 들어갑니다.</div></div>`));
    const opt = UI.el(`<div class="row" style="margin-bottom:6px"><span class="chip ${s.done ? 'on' : ''}" data-done>끝난 것도 보기</span></div>`);
    UI.$('[data-done]', opt).onclick = () => { s.done = !s.done; App.render(true); };
    c.appendChild(opt);
    const ds = Goal.debts(s.done);
    const today = U.today();
    if (!ds.length) c.appendChild(UI.el(UI.empty('기록이 없어요\n＋ 버튼으로 추가하세요', 'a04')));
    else {
      c.appendChild(UI.el(`<ul class="list">${ds.map(d => {
        const left = Goal.debtLeft(d), late = !d.done && d.due && d.due < today;
        return `<li class="tap${d.done ? ' muted' : ''}" data-id="${d.id}"><span class="chip ${d.kind === 'lend' ? 'in' : 'out'}">${d.kind === 'lend' ? '빌려줌' : '빌림'}</span>
          <div class="grow"><div class="main-t ellipsis">${U.esc(d.person)}${d.memo ? ` <span class="small muted">${U.esc(d.memo)}</span>` : ''}</div>
          <div class="sub">${d.date || ''}${d.due ? ` · 갚기로 한 날 ${d.due}` : ''}${late ? ' · <b class="out">기한 지남</b>' : ''}${d.done ? ' · 끝남' : ''}</div></div>
          <div class="right nowrap"><b class="${d.kind === 'lend' ? 'in' : 'out'}">${UI.money(left)}</b><div class="tiny muted">/ ${UI.money(d.amount)}</div></div></li>`;
      }).join('')}</ul>`));
      UI.on(c, 'li[data-id]', 'click', (e, li) => debtSheet(ds.find(d => d.id === Number(li.dataset.id))));
    }
    App.fab(() => editDebt(null), '추가');
  }
  const FIELDS = [{ k: 'kind', label: '구분', type: 'select', options: [['lend', '빌려준 돈 (받을 돈)'], ['borrow', '빌린 돈 (갚을 돈)']] },
    { k: 'person', label: '누구', type: 'text', req: true }, { k: 'amount', label: '금액', type: 'money' },
    { k: 'date', label: '빌려준/빌린 날', type: 'date' }, { k: 'due', label: '갚기로 한 날 (없으면 비움)', type: 'date' }, { k: 'memo', label: '메모', type: 'text' }];
  function editDebt(d) {
    UI.formSheet({ title: d ? '수정' : '빌려준 돈·빌린 돈 추가', fields: FIELDS, values: d || { kind: 'lend', date: U.today() }, full: true,
      onSave: v => {
        if (d) v.done = Goal.debtPaid(d.id) >= v.amount && v.amount > 0;
        Goal.saveDebt(v, d ? d.id : null);
        App.dataChanged();
      },
      onDelete: d ? close => UI.confirm(`${d.person} — ${Goal.KINDS[d.kind]} 기록을 모두 지울까요?`, '삭제', true).then(ok => { if (ok) { Goal.deleteDebt(d.id); close(); App.dataChanged(); } }) : null });
  }
  function debtSheet(d) {
    const pays = Goal.payments(d.id).reverse();
    const left = Goal.debtLeft(d), verb = d.kind === 'lend' ? '받았어요' : '갚았어요';
    const body = UI.el(`<div><div class="box"><div class="kv"><b>${U.esc(d.person)}</b><span>${Goal.KINDS[d.kind]} ${UI.money(d.amount)}원</span></div>
      <div class="kv"><span>${d.kind === 'lend' ? '받은' : '갚은'} 돈 ${UI.money(Goal.debtPaid(d.id))}원</span><b>남은 돈 ${UI.money(left)}원</b></div></div>
      ${left > 0 ? `<div class="form"><div class="row"><input class="inp" type="date" data-k="date" value="${U.today()}"><input class="inp money grow" type="text" inputmode="numeric" data-k="amount" placeholder="금액" value="${UI.money(left)}"></div>
      <div class="row" style="margin-top:6px"><button class="btn sm pri" data-pay>${verb}</button></div></div>` : '<div class="small in" style="margin:6px 0">다 끝났어요!</div>'}
      <div class="section-t">기록 (${pays.length})</div>${pays.length ? `<ul class="list">${pays.map(p => `<li class="tap" data-p="${p.id}"><div class="grow">${p.date}${p.memo ? ` · ${U.esc(p.memo)}` : ''}</div><b>${UI.money(p.amount)}</b></li>`).join('')}</ul>` : '<div class="muted small">아직 기록이 없어요</div>'}</div>`);
    UI.bindMoney(body);
    const sh = UI.sheet({ title: Goal.KINDS[d.kind], body, full: true, buttons: [{ label: '수정', onClick: () => { editDebt(d); } }, { label: '닫기', cls: 'pri' }] });
    const reopen = () => { sh.close(); App.dataChanged(); const x = DB.one('SELECT * FROM debt WHERE id=?', [d.id]); if (x) debtSheet(x); };
    const pay = UI.$('[data-pay]', body);
    if (pay) pay.onclick = () => {
      let amt;
      try { amt = U.calcMoney(UI.$('[data-k=amount]', body).value); } catch (_) { UI.toast('금액은 숫자로 입력하세요'); return; }
      const dt = UI.$('[data-k=date]', body).value;
      if (!amt || amt <= 0) { UI.toast('금액을 입력하세요'); return; }
      if (!U.isValidIso(dt)) { UI.toast('날짜를 확인하세요'); return; }
      Goal.addPayment(d.id, dt, amt);
      reopen();
    };
    UI.on(body, 'li[data-p]', 'click', (e, li) => UI.confirm('이 기록을 지울까요?', '지우기', true).then(ok => { if (ok) { Goal.deletePayment(Number(li.dataset.p)); reopen(); } }));
  }
  return { title: '빌려준 돈·빌린 돈', sticker: 'a04', sub: '잊지 말고 받기·갚기', render, tab: 'assets' };
})();
