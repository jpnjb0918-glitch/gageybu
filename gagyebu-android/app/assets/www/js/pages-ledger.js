/* 가계부(내역)·검색·예약 화면 */
'use strict';

// ════════ 내역 입력·수정 창 (가계부·달력·검색에서 같이 씀) ════════
const Entry = (() => {
  /** opts: {entry(수정할 행), copy(새 내역에 그대로 채울 행: '다시 입력'), date(새로 입력할 날짜), onSaved} */
  function open(opts) {
    const lid = App.lid;
    const e = opts.entry;
    const v0 = e || opts.copy || null;          // 칸에 채울 값 (수정할 행 또는 복사할 행)
    let mode = v0 ? (v0.income && v0.expense ? 'both' : v0.income ? 'in' : 'out') : 'out';
    const firstCode = m => { const c = L.categories(lid).find(x => (m === 'in') === U.isIncomeCode(x.code)); return c ? c.code : ''; };
    const minCount = parseInt(DB.getMeta('item_min_count', 1) || 1, 10) || 1;
    const words = L.itemWords(lid, minCount).map(w => w.name);
    const body = UI.el(`<div class="form">
      <div class="f toggle2"><button data-m="out" class="out">지출</button><button data-m="in" class="in">수입</button></div>
      <div class="f"><label class="l">날짜</label><input type="date" data-k="date" value="${U.esc(e ? e.date : opts.date || U.today())}"></div>
      <div class="f" data-box="out"><label class="l">지출 금액</label><input type="text" inputmode="numeric" class="money" data-k="expense" value="${v0 && v0.expense ? UI.money(v0.expense) : ''}" placeholder="0"></div>
      <div class="f" data-box="in"><label class="l">수입 금액</label><input type="text" inputmode="numeric" class="money" data-k="income" value="${v0 && v0.income ? UI.money(v0.income) : ''}" placeholder="0"></div>
      <div class="f"><label class="l">품목</label><input type="text" data-k="item" value="${U.esc(v0 ? v0.item : '')}" placeholder="예: 점심, 전기세" autocomplete="off">
        <div class="suggest"></div></div>
      <div class="f"><label class="l">계정과목</label><select data-k="code"></select></div>
      <div class="f"><label class="l">메모</label><input type="text" data-k="memo" value="${U.esc(v0 ? v0.memo || '' : '')}"></div>
      <div class="small muted" data-both>${mode === 'both' ? '' : '<a href="#" data-showboth>수입·지출 모두 입력하기</a>'}</div>
    </div>`);
    UI.bindMoney(body);
    const $ = s => UI.$(s, body);
    const codeSel = $('[data-k=code]');
    function fillCodes(keep) {
      const cur = keep || codeSel.value || (v0 ? v0.code : firstCode(mode === 'in' ? 'in' : 'out'));
      codeSel.innerHTML = UI.codeOptions(lid, cur, mode === 'in' ? 'in' : 'out');
    }
    function setMode(m, user) {
      mode = m;
      UI.$$('.toggle2 button', body).forEach(b => b.classList.toggle('on', b.dataset.m === m || m === 'both'));
      $('[data-box=out]').classList.toggle('hidden', m === 'in');
      $('[data-box=in]').classList.toggle('hidden', m === 'out');
      if (user && m !== 'both') {
        // 수입/지출을 바꾸면 계정도 그쪽 첫 계정으로 (이미 맞는 쪽이면 그대로)
        if (U.isIncomeCode(codeSel.value) !== (m === 'in')) codeSel.value = firstCode(m);
        fillCodes(codeSel.value);
        const other = m === 'in' ? 'expense' : 'income', mine = m === 'in' ? 'income' : 'expense';
        const o = $(`[data-k=${other}]`);
        if (o.value && !$(`[data-k=${mine}]`).value) { $(`[data-k=${mine}]`).value = o.value; }
        o.value = '';
      }
    }
    fillCodes(v0 ? v0.code : firstCode('out'));
    setMode(mode, false);
    UI.on(body, '.toggle2 button', 'click', (ev, b) => setMode(b.dataset.m, true));
    const sb = $('[data-showboth]');
    if (sb) sb.onclick = ev => { ev.preventDefault(); setMode('both'); sb.remove(); };

    // 품목 자동완성 + 예전에 쓴 계정 자동 선택 (원본 '품목 자동입력')
    const itemInp = $('[data-k=item]'), sug = $('.suggest');
    function autoCode() {
      const it = itemInp.value.trim();
      if (!it) return;
      const c = L.lastCodeForItem(lid, it);
      if (c && UI.$$('option', codeSel).some(o => o.value === c)) {
        codeSel.value = c;
        const m = U.isIncomeCode(c) ? 'in' : 'out';
        if (mode !== 'both' && m !== mode) setMode(m, true);
      }
    }
    function showSuggest() {
      const t = itemInp.value.trim().toLowerCase();
      const list = (t ? words.filter(w => w.toLowerCase().includes(t) && w !== itemInp.value.trim()) : words).slice(0, 10);
      sug.innerHTML = list.map(w => `<span class="chip" data-w="${U.esc(w)}">${U.esc(w)}</span>`).join('');
      UI.on(sug, '.chip', 'click', (ev, c) => { itemInp.value = c.dataset.w; sug.innerHTML = ''; autoCode(); });
    }
    itemInp.addEventListener('input', showSuggest);
    itemInp.addEventListener('focus', showSuggest);
    itemInp.addEventListener('change', autoCode);

    function value() {
      const v = {
        date: $('[data-k=date]').value, item: itemInp.value.trim(), code: codeSel.value, memo: $('[data-k=memo]').value.trim(),
        income: 0, expense: 0,
      };
      try {
        if (mode !== 'out') v.income = U.parseMoney($('[data-k=income]').value);
        if (mode !== 'in') v.expense = U.parseMoney($('[data-k=expense]').value);
      } catch (_) { throw new Error('금액은 숫자로 입력하세요.'); }
      if (!U.isValidIso(v.date)) throw new Error('날짜를 확인하세요.');
      if (!v.item) throw new Error('품목을 입력하세요.');
      if (!v.income && !v.expense) throw new Error('금액을 입력하세요.');
      if (!v.code) throw new Error('계정과목을 고르세요. (설정 → 계정과목에서 만들 수 있습니다)');
      return v;
    }
    function save(keepOpen) {
      let v;
      try { v = value(); } catch (err) { UI.toast(err.message); return false; }
      if (e) {
        const cur = L.getEntry(e.id);
        if (!cur || cur.ledger_id !== lid) { UI.alert('이 내역은 지금 장부에 없습니다. 창을 닫고 다시 고르세요.'); return false; }
        L.updateEntry(e.id, v);
      } else {
        L.addEntry(lid, v);
        if (!words.includes(v.item)) words.unshift(v.item);
      }
      App.dataChanged();
      if (opts.onSaved) opts.onSaved(v);
      if (keepOpen) {
        UI.toast(`저장했습니다: ${v.item} ${UI.money(v.income || v.expense)}원`);
        itemInp.value = ''; $('[data-k=income]').value = ''; $('[data-k=expense]').value = ''; $('[data-k=memo]').value = '';
        sug.innerHTML = '';
        return false;
      }
      UI.toast('저장했습니다');
      return undefined;
    }
    const buttons = [];
    if (e) {
      buttons.push({ label: '삭제', cls: 'danger', onClick: close => {
        UI.confirm(`이 내역을 삭제할까요?\n${e.date} ${e.item}`, '삭제', true).then(ok => {
          if (!ok) return;
          L.deleteEntries([e.id]);
          close();
          App.dataChanged();
          if (opts.onSaved) opts.onSaved(null);
          UI.toast('삭제했습니다');
        });
        return false;
      } });
    } else {
      buttons.push({ label: '저장 후 계속', onClick: () => save(true) });
    }
    buttons.push({ label: e ? '수정 저장' : '저장', cls: 'pri', onClick: () => save(false) });
    UI.sheet({ title: e ? '내역 수정' : opts.copy ? '다시 입력 (복사)' : '새 내역 입력', body, buttons, full: true });
    if (!e && !opts.copy) setTimeout(() => $('[data-k=expense]').focus(), 250);
  }

  /** 내역 한 줄 (가계부·검색·달력 공용) */
  function rowHtml(r, bal, showDate, cmap) {
    const amt = [r.income ? `<div class="in bold">+${UI.money(r.income)}</div>` : '', r.expense ? `<div class="out bold">-${UI.money(r.expense)}</div>` : ''].join('');
    const sub = [L.codeLabel(cmap, r.code), r.memo].filter(Boolean).map(U.esc).join(' · ');
    return `<li class="tap" data-id="${r.id}"><div class="grow"><div class="main-t ellipsis">${showDate ? `<span class="muted small">${U.shortDate(r.date)}</span> ` : ''}${U.esc(r.item)}</div>
      <div class="sub ellipsis">${sub}</div></div><div class="right nowrap">${amt}${bal !== null && bal !== undefined ? `<div class="tiny muted">잔액 ${UI.money(bal)}</div>` : ''}</div></li>`;
  }
  return { open, rowHtml };
})();

// ════════ 가계부 ════════
Pages.ledger = (() => {
  const t = U.parts(U.today());
  const s = { y: t[0], m: t[1], all: false, desc: true, limit: 300 };
  // ── 피드·타임라인 테마용 목록 (기능은 같고 모양만 SNS 앱처럼) ──
  const AV_COLORS = ['#E8833A', '#E0525B', '#9457D6', '#3B7DDD', '#2E9E5B', '#139A9A', '#D24E8E', '#66788F'];
  const hashOf = str => { let h = 0; for (const ch of String(str || '')) h = (h * 31 + ch.codePointAt(0)) >>> 0; return h; };
  function avatar(label) {
    const s0 = String(label || '');
    const s1 = /^\(미분류/.test(s0) ? '?' : s0;
    const ini = Array.from(s1.replace(/[\s()[\]·.,_-]/g, ''))[0] || '?';
    return `<div class="av" style="background:${AV_COLORS[hashOf(s1) % AV_COLORS.length]}">${U.esc(ini)}</div>`;
  }
  const man = v => (Math.abs(v) >= 10000 ? `${(v / 10000).toFixed(Math.abs(v) >= 100000 ? 0 : 1).replace(/\.0$/, '')}만` : UI.money(v));
  const amtSpans = r => [r.income ? `<span class="in">+${UI.money(r.income)}</span>` : '', r.expense ? `<span class="out">-${UI.money(r.expense)}</span>` : ''].filter(Boolean).join(' ');
  // 게시물 사진 칸에 붙일 고양이 (날짜마다 다르게)
  const TILE_STK = ['a02', 'a03', 'a05', 'a06', 'a07', 'a08', 'a09', 'a11', 'a12', 'a14', 'a15', 'a16', 'a17', 'a18', 'a20', 'a21',
    'b01', 'b03', 'b04', 'b05', 'b06', 'b07', 'b09', 'b10', 'b12', 'b13', 'b14', 'b15', 'b16', 'b17', 'b18', 'b19', 'b20', 'b22',
    'b24', 'b25', 'b27', 'b28', 'b29', 'b31', 'b32', 'b34', 'b35', 'b36', 'b37', 'b39', 'b40'];
  /** 지출 많은 계정과목 (코드별) */
  function topCats(rows, cmap, n) {
    const by = new Map();
    for (const [r] of rows) if (r.expense) { const e = by.get(r.code) || [0, 0]; e[0] += r.expense; e[1]++; by.set(r.code, e); }
    return [...by].sort((a, b) => b[1][0] - a[1][0]).slice(0, n).map(([code, [v, cnt]]) => ({ code, label: L.codeLabel(cmap, code), v, cnt }));
  }
  const periodLabel = () => (s.all ? '전체 기간' : `${s.m}월`);

  // ── 피드: 하루 = 게시물 한 개 (머리 · 사진 칸 · 아이콘 줄 · 합계 · 내역 글 · 잔액) ──
  const CAP_LIMIT = 4;
  function capRow(r, cmap, hidden) {
    const sub = [L.codeLabel(cmap, r.code), r.memo].filter(Boolean).join(' · ');
    return `<li class="tap${hidden ? ' x' : ''}" data-id="${r.id}"><div class="it"><b>${U.esc(r.item || '(품목 없음)')}</b><span>${U.esc(sub)}</span></div><div class="am">${amtSpans(r)}</div></li>`;
  }
  function feedPost(d, list, cmap, bal) {
    const di = U.sum(list.map(([r]) => r.income)), de = U.sum(list.map(([r]) => r.expense)), n = list.length;
    const [y, m, dd] = U.parts(d);
    const first = list[0][0].item || '(품목 없음)';
    const stamp = `'${String(y).slice(2)} ${String(m).padStart(2, '0')} ${String(dd).padStart(2, '0')}`;
    const ord = n > 1 ? `<button class="iconbtn dayord" data-d="${d}" aria-label="이 날 내역 순서 바꾸기" title="순서 바꾸기">${UI.icon('sort')}</button>` : '';
    const dots = n > 1 ? `<div class="pdots">${Array.from({ length: Math.min(n, 5) }, (_, i) => `<i class="${i ? '' : 'on'}"></i>`).join('')}</div>` : '';
    return `<article class="post" data-day="${d}">
      <header class="ph"><div class="ring"><img src="${UI.sticker(App.pref('minimi'))}" alt=""></div>
        <div class="grow"><div class="pt">${U.dateLabel(d)}</div><div class="ps ellipsis">${U.esc(App.ledgerName())} · ${n}건</div></div>
        <button class="iconbtn pmenu" data-d="${d}" aria-label="이 날 메뉴" title="이 날 메뉴">${UI.icon('dots')}</button></header>
      <div class="ptile t${dd % 5}"><span class="stamp">${stamp}</span><div class="big">${de ? `-${UI.money(de)}` : `+${UI.money(di)}`}</div>
        <div class="cap">${U.esc(n > 1 ? `${first} 외 ${n - 1}건` : first)}</div><img class="stk" src="${UI.sticker(TILE_STK[hashOf(d) % TILE_STK.length])}" alt=""></div>${dots}
      <div class="pa"><span class="ind${di ? ' on' : ''}" title="${di ? '수입이 있는 날' : '수입 없는 날'}">${UI.icon('heart', di ? 'on' : '')}</span>
        <button class="iconbtn" data-add="${d}" aria-label="이 날 새 내역" title="이 날 새 내역">${UI.icon('comment')}</button>${ord}
        <button class="iconbtn" data-cal="${d}" aria-label="달력에서 보기" title="달력에서 보기">${UI.icon('calendar')}</button></div>
      <div class="plike">${de ? `지출 <span class="out">-${UI.money(de)}</span>` : ''}${di && de ? ' · ' : ''}${di ? `수입 <span class="in">+${UI.money(di)}</span>` : ''}</div>
      <ul class="pcap">${list.map(([r], i) => capRow(r, cmap, i >= CAP_LIMIT)).join('')}</ul>
      ${n > CAP_LIMIT ? `<button class="pmore" data-more>내역 ${n}개 모두 보기</button>` : ''}
      <div class="ptime">잔액 ${UI.money(bal)}원</div></article>`;
  }
  function dayMenu(d, n) {
    const items = [['add', 'comment', '이 날 새 내역'], ['cal', 'calendar', '달력에서 이 날 보기']];
    if (n > 1) items.splice(1, 0, ['ord', 'sort', '이 날 내역 순서 바꾸기']);
    const body = UI.el(`<ul class="menu-list">${items.map(([k, ic, l]) => `<li data-k="${k}">${UI.icon(ic)}<span class="nm">${l}</span></li>`).join('')}</ul>`);
    const sh = UI.sheet({ title: U.dateLabel(d), body });
    UI.on(body, 'li', 'click', (e, li) => { sh.close(); dayAction(li.dataset.k, d); });
  }
  function dayAction(k, d) {
    if (k === 'add') Entry.open({ date: d });
    else if (k === 'ord') dayOrderSheet(d);
    else if (k === 'cal') App.go('calendar', { date: d }, true);
  }

  // ── 타임라인: 한 건 = 글 한 개 (얼굴 · 이름 @계정 · 날짜 · 메모 · 금액 · 아이콘 줄) ──
  function tweet(r, bal, cmap) {
    const cat = L.codeLabel(cmap, r.code);
    return `<li class="tap tw" data-id="${r.id}">${avatar(cat)}<div class="grow">
      <div class="l1"><b>${U.esc(r.item || '(품목 없음)')}</b><span class="meta">@${U.esc(cat.replace(/\s+/g, ''))} · ${U.shortDate(r.date)}</span></div>
      ${r.memo ? `<div class="txt">${U.esc(r.memo)}</div>` : ''}<div class="money">${amtSpans(r)}</div>
      <div class="acts"><button class="iconbtn" data-edit="${r.id}" aria-label="수정" title="수정">${UI.icon('comment')}</button>
        <button class="iconbtn" data-copy="${r.id}" aria-label="다시 입력" title="다시 입력 (복사)">${UI.icon('repeat')}</button>
        <span class="ind" title="${r.income ? '수입' : '지출'}">${UI.icon('heart', r.income ? 'on' : '')}</span>
        <span class="ind" title="이 내역까지의 잔액">${UI.icon('stats')}${UI.money(bal)}</span></div></div></li>`;
  }

  function dayHtml(theme, d, list, cmap, bal) {
    const di = U.sum(list.map(([r]) => r.income)), de = U.sum(list.map(([r]) => r.expense));
    const sums = `${di ? `<span class="in">+${UI.money(di)}</span> ` : ''}${de ? `<span class="out">-${UI.money(de)}</span>` : ''}`;
    if (theme === 'feed') return feedPost(d, list, cmap, bal);
    if (theme === 'timeline') {
      const ord = list.length > 1 ? `<button class="iconbtn dayord" data-d="${d}" aria-label="이 날 내역 순서 바꾸기" title="순서 바꾸기">${UI.icon('sort')}</button>` : '';
      return `<section class="tl-grp"><div class="tl-day"><span>${U.dateLabel(d)}</span><span class="sums">${sums}${ord}</span></div>
        <ul class="tw-list">${list.map(([r, b]) => tweet(r, b, cmap)).join('')}</ul></section>`;
    }
    const ord = list.length > 1 ? `<button class="iconbtn dayord" data-d="${d}" aria-label="이 날 내역 순서 바꾸기" title="순서 바꾸기">⇅</button>` : '';
    return `<div class="dayhead"><span>${U.dateLabel(d)}</span><span class="sums">${sums}${ord}</span></div>
      <ul class="list">${list.map(([r, b]) => Entry.rowHtml(r, b, false, cmap)).join('')}</ul>`;
  }
  /** 같은 날 내역 순서 바꾸기 (PC판과 같은 자료 파일에 저장 → PC에서도 같은 순서) */
  function dayOrderSheet(d) {
    const lid = App.lid;
    const cmap = L.categoryMap(lid);
    const rows = L.entriesWithBalance(lid, d, d).map(([r]) => r);
    UI.reorder({ title: `${U.dateLabel(d)} 내역 순서`, hint: '같은 날 안에서의 순서입니다. 잔액도 이 순서로 계산됩니다.',
      items: rows.map(r => ({ key: r.id, label: r.item || '(품목 없음)',
        sub: [L.codeLabel(cmap, r.code), r.income ? `+${UI.money(r.income)}` : '', r.expense ? `-${UI.money(r.expense)}` : ''].filter(Boolean).join(' · ') })),
      onSave: keys => { Ord.setDayOrder(lid, d, keys.map(Number)); App.dataChanged(); },
      onReset: () => { Ord.setDayOrder(lid, d, rows.map(r => r.id).sort((a, b) => a - b)); App.dataChanged(); } });
  }
  /** 계정과목 하나를 이 기간으로 검색 화면에서 */
  function searchCat(code) {
    const start = s.all ? '' : U.iso(s.y, s.m, 1), end = s.all ? '' : U.iso(s.y, s.m, U.monthEnd(s.y, s.m));
    Pages.search.openWith({ start, end, codes: [code] });
  }

  function render(c, p, tools) {
    const lid = App.lid;
    const theme = App.layoutOf(App.theme()) || App.theme();     // 'feed' | 'timeline' | 'retro' | 'basic'
    const sns = theme === 'feed' || theme === 'timeline';
    const start = U.iso(s.y, s.m, 1), end = U.iso(s.y, s.m, U.monthEnd(s.y, s.m));
    let rows = s.all ? L.entriesWithBalance(lid) : L.entriesWithBalance(lid, start, end);
    const endBal = new Map();
    for (const [r, b] of rows) endBal.set(r.date, b);              // 그날 마지막 잔액 (날짜 순서대로 계산된 값)
    if (s.desc) rows = Ord.applyDayOrder(rows, Ord.dayOrders(lid), true);   // 최근 날짜 위로 (순서를 정한 날은 그 순서 그대로)
    const cmap = L.categoryMap(lid);
    const csvBtn = UI.el(`<button class="iconbtn" title="CSV로 저장" aria-label="CSV로 저장">${sns ? UI.icon('download') : '⤓'}</button>`);
    csvBtn.onclick = () => exportCsv(rows);
    tools.appendChild(csvBtn);
    const lay = UI.el(`<button class="iconbtn" title="화면 구성 순서" aria-label="화면 구성 순서">${sns ? UI.icon('sliders') : '☰'}</button>`);
    lay.onclick = () => App.layoutReorderSheet();
    tools.appendChild(lay);
    const reload = () => { s.limit = 300; App.render(); };
    const [inc, exp] = L.totals(lid, start, end);
    const bal = L.currentBalance(lid, U.today());
    const [, texp] = L.totals(lid, U.today(), U.today());
    // 화면 덩어리 (순서는 설정 → 화면 꾸미기 → 가계부 화면 구성, 또는 위의 ☰)
    const part = {
      monthnav: () => UI.monthNav(s.y, s.m, (y, m) => { s.y = y; s.m = m; s.all = false; s.limit = 300; App.render(); }),
      stories: () => {
        if (theme === 'feed') {
          const top = topCats(rows, cmap, 12);
          const el = UI.el(`<div class="ig-hl"><button class="hl new" data-new><div class="ring">${UI.icon('add')}</div><div class="nm">새 내역</div></button>
            ${top.map(x => `<button class="hl" data-code="${U.esc(x.code)}" title="${U.esc(x.label)} 검색"><div class="ring">${avatar(x.label)}</div><div class="nm">${U.esc(x.label)}</div><div class="amt out">${man(x.v)}</div></button>`).join('')}</div>`);
          UI.$('[data-new]', el).onclick = () => newEntry();
          UI.on(el, '[data-code]', 'click', (e, b) => searchCat(b.dataset.code));
          return el;
        }
        if (theme === 'timeline') {
          const top = topCats(rows, cmap, 3);
          if (!top.length) return null;
          const el = UI.el(`<div class="tw-trend"><h3>${periodLabel()}에 많이 쓴 곳</h3>${top.map((x, i) =>
            `<button class="tr" data-code="${U.esc(x.code)}"><div class="k">${i + 1} · 지출 순위</div><b>#${U.esc(x.label.replace(/\s+/g, ''))}</b><div class="k">${UI.money(x.v)}원 · ${x.cnt}건</div></button>`).join('')}</div>`);
          UI.on(el, '[data-code]', 'click', (e, b) => searchCat(b.dataset.code));
          return el;
        }
        return null;
      },
      stats: () => {
        if (theme === 'feed') {
          const mood = App.pref('mood'), motto = (App.pref('motto') || '').trim();
          const el = UI.el(`<div class="ig-prof"><div class="ig-top"><button class="ring ig-av" data-me aria-label="미니미 바꾸기"><img src="${UI.sticker(App.pref('minimi'))}" alt=""></button>
            <div class="ig-stats"><div><b class="in">${UI.money(inc)}</b><span>${s.m}월 수입</span></div><div><b class="out">${UI.money(exp)}</b><span>${s.m}월 지출</span></div>
            <div><b class="${UI.moneyCls(inc - exp)}">${UI.money(inc - exp)}</b><span>차액</span></div></div></div>
            <div class="ig-name">${U.esc(App.ledgerName())}</div>
            <div class="ig-bio">오늘의 기분: ${U.esc(mood)}${motto ? `\n${U.esc(motto)}` : ''}
<span class="k">오늘 지출</span> ${UI.money(texp)}원 · <span class="k">현재 잔액</span> <b class="${UI.moneyCls(bal)}">${UI.money(bal)}원</b></div></div>`);
          UI.$('[data-me]', el).onclick = () => App.go('settings', { section: 'deco' });
          return el;
        }
        if (theme === 'timeline') {
          const nIn = rows.filter(([r]) => r.income).length, nOut = rows.filter(([r]) => r.expense).length;
          return UI.el(`<div class="tw-pin tw"><img class="me" src="${UI.sticker(App.pref('minimi'))}" alt=""><div class="grow">
            <div class="pinl">${UI.icon('pin')}고정된 글</div>
            <div class="l1"><b>${U.esc(App.ledgerName())}</b><span class="meta">@${s.m}월_요약 · ${s.y}.${s.m}</span></div>
            <div class="txt">${s.m}월 수입 <b class="in">${UI.money(inc)}원</b>, 지출 <b class="out">${UI.money(exp)}원</b>
차액 <b class="${UI.moneyCls(inc - exp)}">${UI.money(inc - exp)}원</b> · 현재&nbsp;잔액&nbsp;<b class="${UI.moneyCls(bal)}">${UI.money(bal)}원</b>
오늘의 기분: ${U.esc(App.pref('mood'))}</div>
            <div class="acts"><span class="ind" title="내역 건수">${UI.icon('comment')}${rows.length}</span><span class="ind" title="수입 건수">${UI.icon('heart')}${nIn}</span>
              <span class="ind" title="지출 건수">${UI.icon('repeat')}${nOut}</span><span class="ind" title="오늘 지출">${UI.icon('stats')}${UI.money(texp)}</span></div></div></div>`);
        }
        return UI.el(`<div class="box"><div class="stats">
          <div><div class="k">이달 수입</div><div class="v in">${UI.money(inc)}</div></div>
          <div><div class="k">이달 지출</div><div class="v out">${UI.money(exp)}</div></div>
          <div><div class="k">차액</div><div class="v ${UI.moneyCls(inc - exp)}">${UI.money(inc - exp)}</div></div></div>
          <div class="kv small" style="margin-top:6px;border-top:1px dashed var(--line);padding-top:5px"><span>현재 잔액 (오늘까지)</span><b class="${UI.moneyCls(bal)}">${UI.money(bal)}원</b></div></div>`);
      },
      opts: () => {
        if (theme === 'feed') {
          const o = UI.el(`<div class="ig-tabs"><button data-o="month" class="${s.all ? '' : 'on'}">${UI.icon('grid')}${s.m}월</button>
            <button data-o="all" class="${s.all ? 'on' : ''}">${UI.icon('all')}전체 기간</button>
            <button data-o="desc">${UI.icon('sort')}${s.desc ? '최근 것 위로' : '오래된 것 위로'}</button></div>`);
          UI.on(o, 'button', 'click', (e, b) => { const k = b.dataset.o; if (k === 'desc') s.desc = !s.desc; else s.all = k === 'all'; reload(); });
          return o;
        }
        if (theme === 'timeline') {
          const o = UI.el(`<div class="tw-tabs"><button data-o="month" class="${s.all ? '' : 'on'}"><span>${s.m}월</span></button>
            <button data-o="all" class="${s.all ? 'on' : ''}"><span>전체 기간</span></button>
            <button data-o="desc" class="srt${s.desc ? ' on' : ''}" title="${s.desc ? '최근 것 위로 (누르면 오래된 것 위로)' : '오래된 것 위로 (누르면 최근 것 위로)'}" aria-label="정렬 바꾸기">${UI.icon('sort')}</button></div>`);
          UI.on(o, 'button', 'click', (e, b) => { const k = b.dataset.o; if (k === 'desc') s.desc = !s.desc; else s.all = k === 'all'; reload(); });
          return o;
        }
        const o = UI.el(`<div class="row" style="margin-bottom:4px"><span class="chip ${s.all ? 'on' : ''}" data-o="all">전체 기간</span>
          <span class="chip ${s.desc ? 'on' : ''}" data-o="desc">최근 것을 위로</span></div>`);
        UI.on(o, '.chip', 'click', (e, x) => { s[x.dataset.o] = !s[x.dataset.o]; reload(); });
        return o;
      },
      list: () => {
        if (!rows.length) return UI.el(UI.empty(s.all ? '아직 입력한 내역이 없어요.\n＋ 버튼으로 첫 내역을 입력하세요.' : '이 달에는 내역이 없어요.'));
        const box = UI.el('<div class="ledger-wrap"></div>');
        const shown = rows.slice(0, s.limit);
        const byDay = new Map();
        for (const [r, b] of shown) { if (!byDay.has(r.date)) byDay.set(r.date, []); byDay.get(r.date).push([r, b]); }
        let html = '';
        for (const [d, list] of byDay) html += dayHtml(theme, d, list, cmap, endBal.get(d));
        box.appendChild(UI.el(`<div class="ledger-list">${html}</div>`));
        if (rows.length > s.limit) {
          const more = UI.el(`<button class="btn block" style="margin-top:10px">더 보기 (${rows.length - s.limit}건 남음)</button>`);
          more.onclick = () => { s.limit += 300; App.render(true); };
          box.appendChild(more);
        }
        const byId = new Map(shown.map(([r]) => [r.id, r]));
        UI.on(box, 'li[data-id]', 'click', (e, li) => Entry.open({ entry: byId.get(Number(li.dataset.id)) }));
        UI.on(box, '.dayord', 'click', (e, b) => { e.stopPropagation(); dayOrderSheet(b.dataset.d); });
        UI.on(box, '[data-add]', 'click', (e, b) => { e.stopPropagation(); Entry.open({ date: b.dataset.add }); });
        UI.on(box, '[data-cal]', 'click', (e, b) => { e.stopPropagation(); dayAction('cal', b.dataset.cal); });
        UI.on(box, '.pmenu', 'click', (e, b) => { e.stopPropagation(); dayMenu(b.dataset.d, byDay.get(b.dataset.d).length); });
        UI.on(box, '[data-more]', 'click', (e, b) => { const post = b.closest('.post'); post.classList.add('open'); b.remove(); });
        UI.on(box, '.ptile', 'click', (e, tile) => { const post = tile.closest('.post'); const mb = UI.$('[data-more]', post); if (mb) mb.click(); });
        UI.on(box, '[data-edit]', 'click', (e, b) => { e.stopPropagation(); Entry.open({ entry: byId.get(Number(b.dataset.edit)) }); });
        UI.on(box, '[data-copy]', 'click', (e, b) => { e.stopPropagation(); Entry.open({ copy: byId.get(Number(b.dataset.copy)), date: U.today() }); });
        UI.on(box, '.ind', 'click', e => e.stopPropagation());
        return box;
      },
    };
    for (const k of App.ledgerLayout()) {
      const node = part[k] ? part[k]() : null;
      if (node) c.appendChild(node);
    }
    const tabs = UI.$('.tw-tabs', c);
    if (tabs) c.style.setProperty('--tabs-h', tabs.offsetHeight + 'px');
    function newEntry() {
      const today = U.today();
      const inView = today >= start && today <= end;
      Entry.open({ date: inView || s.all ? today : start, onSaved: v => {
        if (v && !s.all) { const [y, m] = U.parts(v.date); if (y !== s.y || m !== s.m) { s.y = y; s.m = m; App.render(); } }
      } });
    }
    App.fab(newEntry, '새 내역');
  }
  function exportCsv(rows) {
    const cmap = L.categoryMap(App.lid);
    const csv = Bk.toCsv(['날짜', '품목', '수입', '지출', '잔액', '계정과목', '메모'],
      rows.map(([r, b]) => [r.date, r.item, r.income, r.expense, b, L.codeLabel(cmap, r.code), r.memo]));
    const name = s.all ? `가계부내역_전체.csv` : `가계부내역_${U.ym(s.y, s.m)}.csv`;
    App.nativeAsync('saveText', name, 'text/csv', csv).then(r => UI.toast(r.ok ? 'CSV 파일을 저장했습니다' : (r.cancel ? '취소했습니다' : '저장 실패: ' + r.error)));
  }
  return { title: '가계부', sticker: 'a22', sub: '들어오고 나간 돈 차곡차곡 ♪', render, state: s };
})();

// ════════ 검색 ════════
Pages.search = (() => {
  const s = { start: '', end: '', text: '', codes: [], amount: '', side: '수입+지출', op: '같은 금액', order: 'date', desc: true, ran: false };
  function render(c) {
    const lid = App.lid;
    const cmap = L.categoryMap(lid);
    const f = UI.el(`<div class="form">
      <div class="row"><div class="f grow"><label class="l">시작일</label><input type="date" data-k="start" value="${s.start}"></div>
        <div class="f grow"><label class="l">종료일</label><input type="date" data-k="end" value="${s.end}"></div></div>
      <div class="row wrap" style="margin:-4px 0 10px"><span class="chip" data-q="month">이번 달</span><span class="chip" data-q="year">올해</span><span class="chip" data-q="all">전체</span></div>
      <div class="f"><label class="l">품목·메모에 들어간 글자</label><input type="text" data-k="text" value="${U.esc(s.text)}" placeholder="예: 커피"></div>
      <div class="f"><label class="l">계정과목 (여러 개 가능)</label><div class="row wrap codes"></div><button class="btn sm" data-pick style="margin-top:6px">계정 고르기</button></div>
      <div class="f"><label class="l">금액</label><input type="text" inputmode="numeric" class="money" data-k="amount" value="${s.amount}">
        <div class="row" style="margin-top:6px"><select class="grow" data-k="side">${['수입+지출', '수입', '지출'].map(x => `<option${x === s.side ? ' selected' : ''}>${x}</option>`).join('')}</select>
        <select class="grow" data-k="op">${Object.keys(L.AMOUNT_OPS).map(x => `<option${x === s.op ? ' selected' : ''}>${x}</option>`).join('')}</select></div></div>
      <div class="row"><select class="grow" data-k="order">${[['date', '날짜순'], ['item', '품목순'], ['income', '수입순'], ['expense', '지출순'], ['code', '계정순']].map(([k, v]) => `<option value="${k}"${k === s.order ? ' selected' : ''}>${v}</option>`).join('')}</select>
        <label class="check"><input type="checkbox" data-k="desc"${s.desc ? ' checked' : ''}> 거꾸로</label></div>
      <button class="btn pri block" data-go style="margin-top:8px">검색</button></div>`);
    UI.bindMoney(f);
    c.appendChild(f);
    const codesBox = UI.$('.codes', f);
    const drawCodes = () => {
      codesBox.innerHTML = s.codes.length ? s.codes.map(k => `<span class="chip on">${U.esc(k)} ${U.esc(L.codeLabel(cmap, k))}</span>`).join('') : '<span class="muted small">(전체)</span>';
    };
    drawCodes();
    const read = () => {
      UI.$$('[data-k]', f).forEach(x => { s[x.dataset.k] = x.type === 'checkbox' ? x.checked : x.value; });
    };
    UI.on(f, '[data-q]', 'click', (e, x) => {
      const [y, m] = U.parts(U.today());
      const q = x.dataset.q;
      UI.$('[data-k=start]', f).value = q === 'month' ? U.iso(y, m, 1) : q === 'year' ? U.iso(y, 1, 1) : '';
      UI.$('[data-k=end]', f).value = q === 'month' ? U.iso(y, m, U.monthEnd(y, m)) : q === 'year' ? U.iso(y, 12, 31) : '';
    });
    UI.$('[data-pick]', f).onclick = () => {
      const cats = L.categories(lid);
      const body = UI.el(`<div>${L.groups(lid).map(g => {
        const cs = cats.filter(x => x.code.slice(0, 1) === g.code);
        if (!cs.length) return '';
        return `<div class="section-t">(${U.esc(g.code)}) ${U.esc(g.name)}</div>` + cs.map(x => `<label class="check"><input type="checkbox" value="${U.esc(x.code)}"${s.codes.includes(x.code) ? ' checked' : ''}> ${U.esc(x.code)} ${U.esc(x.name)}</label>`).join('');
      }).join('')}</div>`);
      UI.sheet({ title: '계정 고르기', body, full: true, buttons: [
        { label: '모두 해제', onClick: (cl, sb) => { UI.$$('input', sb).forEach(i => { i.checked = false; }); return false; } },
        { label: '확인', cls: 'pri', onClick: (cl, sb) => { s.codes = UI.$$('input:checked', sb).map(i => i.value); drawCodes(); } }] });
    };
    const out = UI.el('<div style="margin-top:12px"></div>');
    c.appendChild(out);
    const run = () => {
      read();
      let amount = null;
      try { amount = s.amount.trim() ? U.parseMoney(s.amount) : null; } catch (_) { UI.toast('금액은 숫자로 입력하세요.'); return; }
      const rows = L.search(lid, { start: s.start || null, end: s.end || null, text: s.text.trim(), codes: s.codes, amount,
        amountSide: s.side, amountOp: s.op, order: s.order, desc: s.desc });
      s.ran = true;
      const inc = U.sum(rows.map(r => r.income)), exp = U.sum(rows.map(r => r.expense));
      out.innerHTML = `<div class="box"><div class="stats"><div><div class="k">건수</div><div class="v">${rows.length}</div></div>
        <div><div class="k">수입 합계</div><div class="v in">${UI.money(inc)}</div></div><div><div class="k">지출 합계</div><div class="v out">${UI.money(exp)}</div></div></div></div>` +
        (rows.length ? `<ul class="list">${rows.slice(0, 1000).map(r => Entry.rowHtml(r, null, true, cmap).replace('<span class="muted small">' + U.shortDate(r.date), '<span class="muted small">' + r.date)).join('')}</ul>` +
          (rows.length > 1000 ? `<div class="muted small center">앞의 1,000건만 보여 줍니다</div>` : '') : UI.empty('조건에 맞는 내역이 없어요', 'b23'));
      const byId = new Map(rows.map(r => [r.id, r]));
      UI.on(out, 'li[data-id]', 'click', (e, li) => Entry.open({ entry: byId.get(Number(li.dataset.id)), onSaved: () => setTimeout(run, 0) }));
    };
    UI.$('[data-go]', f).onclick = run;
    if (s.ran) run();
  }
  /** 조건을 채워 검색 화면을 열고 바로 검색 (피드·타임라인의 계정과목 동그라미·트렌드에서) */
  function openWith(o) {
    Object.assign(s, { start: o.start || '', end: o.end || '', text: o.text || '', codes: o.codes || [], amount: '', ran: true });
    App.go('search', {}, true);
  }
  return { title: '검색', sticker: 'b23', sub: '그때 그 지출, 어디 갔지?', render, openWith, tab: 'more' };
})();

// ════════ 예약 (매월 고정 수입·지출 자동입력) ════════
Pages.recurring = (() => {
  function render(c) {
    const lid = App.lid;
    const cmap = L.categoryMap(lid);
    const top = UI.el(`<div class="row wrap" style="margin-bottom:8px"><button class="btn sm" data-now>지금 입력할 예약 보기</button><button class="btn sm" data-log>입력 기록</button></div>`);
    UI.$('[data-now]', top).onclick = () => {
      const [due, later] = R.pending(lid);
      if (due.length) pendingSheet(due, later); else UI.toast('오늘까지 입력할 예약이 없습니다');
    };
    UI.$('[data-log]', top).onclick = () => logSheet(null);
    c.appendChild(top);
    c.appendChild(UI.el('<div class="small muted" style="margin-bottom:6px">매달 정해진 날 들어오고 나가는 돈(월급·관리비·적금 등)을 등록해 두면, 앱을 열 때 입력할지 물어봅니다.</div>'));
    const rules = R.rules(lid);
    if (!rules.length) c.appendChild(UI.el(UI.empty('등록한 예약이 없어요', 'b38')));
    else {
      c.appendChild(UI.el(`<ul class="list">${rules.map(r => `<li class="tap" data-id="${r.id}"><span class="chip">${r.day}일</span>
        <div class="grow"><div class="main-t ellipsis">${U.esc(r.item)}</div><div class="sub ellipsis">${U.esc(L.codeLabel(cmap, r.code))} · ${r.start}~${r.end || '계속'}</div></div>
        <div class="right nowrap">${r.income ? `<div class="in bold">+${UI.money(r.income)}</div>` : ''}${r.expense ? `<div class="out bold">-${UI.money(r.expense)}</div>` : ''}</div></li>`).join('')}</ul>`));
      UI.on(c, 'li[data-id]', 'click', (e, li) => ruleSheet(rules.find(r => r.id === Number(li.dataset.id))));
    }
    App.fab(() => ruleSheet(null), '예약 추가');
  }
  function ruleSheet(r) {
    const lid = App.lid;
    const fields = [
      { k: 'item', label: '품목', type: 'text', req: true },
      { k: 'expense', label: '지출 금액', type: 'money' },
      { k: 'income', label: '수입 금액', type: 'money' },
      { k: 'code', label: '계정과목', type: 'code', lid, mode: r && r.income ? 'in' : 'out' },
      { k: 'day', label: '자동입력일 (매월)', type: 'int', hint: '31일로 하면 매달 말일 (짧은 달은 자동으로 말일)' },
      { k: 'start', label: '시작 적용일', type: 'date', req: true },
      { k: 'end', label: '종료 적용일 (비우면 계속)', type: 'date' },
      { k: 'memo', label: '메모', type: 'text' }];
    const vals = r ? Object.assign({}, r) : { day: Number(U.today().slice(8)), start: U.today() };
    UI.formSheet({ title: r ? '예약 수정' : '예약 추가', fields, values: vals, full: true,
      extra: r ? '<button class="btn sm" data-hist style="margin-top:4px">이 예약의 입력 기록</button>' : '',
      afterOpen: sb => { const h = UI.$('[data-hist]', sb); if (h) h.onclick = () => logSheet(r); },
      onSave: v => {
        if (!v.income && !v.expense) throw new Error('수입 또는 지출 금액을 입력하세요.');
        if (!v.code) throw new Error('계정과목을 고르세요.');
        if (!v.day || v.day < 1 || v.day > 31) throw new Error('자동입력일은 1~31 사이로 입력하세요.');
        if (v.end && v.end < v.start) throw new Error('종료 적용일이 시작 적용일보다 빠릅니다.');
        R.saveRule(lid, v, r ? r.id : null);
        App.dataChanged();
        UI.toast('저장했습니다');
      },
      onDelete: r ? close => UI.confirm(`예약 '${r.item}'을(를) 삭제할까요?\n(이미 장부에 입력된 내역은 그대로 남습니다)`, '삭제', true).then(ok => {
        if (ok) { R.deleteRule(r.id); close(); App.dataChanged(); }
      }) : null });
  }
  function logSheet(r) {
    const lid = App.lid;
    const rows = R.log(r ? { rid: r.id } : { lid }).reverse();
    UI.sheet({ title: r ? `입력 기록 — ${r.item}` : '예약 입력 기록', full: true,
      body: rows.length ? `<ul class="list">${rows.map(x => `<li><div class="grow"><div class="main-t">${x.date} ${U.esc(x.item || '')}</div>
        <div class="sub">${x.skipped ? '건너뜀 (입력 안 함)' : '장부에 입력함'}</div></div>
        <div class="right">${x.income ? `<div class="in">+${UI.money(x.income)}</div>` : ''}${x.expense ? `<div class="out">-${UI.money(x.expense)}</div>` : ''}</div></li>`).join('')}</ul>`
        : UI.empty('기록이 없어요', 'b38') });
  }
  /** 원본의 '오늘까지 자동으로 입력될 예약 내용' */
  function pendingSheet(due, later) {
    const lid = App.lid;
    const cmap = L.categoryMap(lid);
    const t = U.parts(U.today());
    const monthStart = U.iso(t[0], t[1], 1);
    const old = due.filter(it => it.date < monthStart).length;
    const body = UI.el(`<div>
      <div class="small" style="margin-bottom:6px"><b>오늘까지 입력될 예약 (${due.length}건)</b> — 입력할 것만 체크하세요</div>
      ${old ? `<div class="small out" style="margin-bottom:6px">이번 달 이전 날짜 ${old}건은 기본으로 체크하지 않았습니다 (이미 직접 입력했을 수 있음)</div>` : ''}
      <ul class="list">${due.map((it, i) => `<li><input type="checkbox" data-i="${i}" style="width:22px;height:22px"${it.date >= monthStart ? ' checked' : ''}>
        <div class="grow"><div class="main-t ellipsis">${it.date} ${U.esc(it.rule.item)}</div><div class="sub">${U.esc(L.codeLabel(cmap, it.rule.code))}</div></div>
        <div class="right nowrap">${it.rule.income ? `<div class="in">+${UI.money(it.rule.income)}</div>` : ''}${it.rule.expense ? `<div class="out">-${UI.money(it.rule.expense)}</div>` : ''}</div></li>`).join('')}</ul>
      ${later.length ? `<div class="section-t">오늘 이후 이달에 남은 예약 (${later.length}건, 그날이 되면 입력)</div>
      <ul class="list">${later.map(it => `<li class="muted"><div class="grow">${it.date} ${U.esc(it.rule.item)}</div><div>${UI.money(it.rule.income || it.rule.expense)}</div></li>`).join('')}</ul>` : ''}
    </div>`);
    const checked = sb => UI.$$('input[data-i]:checked', sb).map(x => due[Number(x.dataset.i)]);
    UI.sheet({ title: '예약된 수입·지출 자동입력', body, full: true, buttons: [
      { label: '나중에' },
      { label: '건너뛰기', onClick: (close, sb) => {
        const items = checked(sb);
        if (!items.length) { UI.toast('체크한 항목이 없습니다'); return false; }
        UI.confirm(`${items.length}건을 장부에 입력하지 않고 "건너뜀"으로 기록할까요?\n(다음부터 다시 묻지 않습니다)`).then(ok => {
          if (ok) { R.apply(lid, items, true); close(); App.dataChanged(); }
        });
        return false;
      } },
      { label: '체크한 것 입력', cls: 'pri', onClick: (close, sb) => {
        const items = checked(sb);
        if (!items.length) { UI.toast('체크한 항목이 없습니다'); return false; }
        R.apply(lid, items, false);
        App.dataChanged();
        UI.toast(`${items.length}건을 입력했습니다`);
        return undefined;
      } }] });
  }
  return { title: '예약 입력', sticker: 'b38', sub: '매달 알아서 척척', render, pendingSheet, tab: 'more' };
})();
