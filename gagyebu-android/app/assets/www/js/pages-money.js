/* 1.8.0 기능 화면 (PC판 ui/money_ui.py 와 같은 기능, 계산은 svc-money.js):
   결제수단 · 외화로 적기 · 큰돈 나눠 적기 · 같은 곳 모아보기 · 휴지통 · 카테고리 그림 고르기 ·
   통계의 주별/결제수단/저축 · 고정비 한눈에 · 카드 실적 · 매일 입력 알림 */
'use strict';
const Money = (() => {
  const sd = () => Rep.settleDay();

  // ── 이름표: 카테고리 그림·결제수단 이름 (화면을 그릴 때마다 한 번 읽음) ──
  let memo = null;
  function forget() { memo = null; }
  function ctx() {
    const lid = App.lid;
    if (!memo || memo.lid !== lid) memo = { lid, emap: Emo.map(lid), pmap: Pay.map() };
    return memo;
  }
  /** '🛒 식료품' (그림이 없으면 이름만) */
  const cat = (cmap, code) => Emo.deco(ctx().emap, code, L.codeLabel(cmap, code));
  const payLabel = v => Pay.label(ctx().pmap, v);
  /** 결제수단 고르기 <option> 들. 카드는 💳 를 붙임. 목록에 없는 값(지운 카드 등)도 그대로 보이게 */
  function payOptions(cur, none) {
    cur = cur || '';
    let found = false;
    let h = [['', none || '(안 정함)']].concat(Pay.options()).map(([v, l]) => {
      const sel = v === cur;
      if (sel) found = true;
      return `<option value="${U.esc(v)}"${sel ? ' selected' : ''}>${U.esc(v.startsWith('card:') ? `💳 ${l}` : l)}</option>`;
    }).join('');
    if (!found) h += `<option value="${U.esc(cur)}" selected>${U.esc(payLabel(cur))}</option>`;
    return h;
  }

  // ── 외화로 적기 ──
  const CUR_WORD = { USD: '달러', JPY: '엔', EUR: '유로', CNY: '위안', GBP: '파운드', VND: '동' };
  /** 외화 금액 × 환율 → 원. onDone({won, note, expense}) */
  function fxSheet(expense, onDone) {
    const last = DB.getMeta('fx_last') || 'USD';
    const body = UI.el(`<div class="form fxs"><div class="small muted" style="margin-bottom:8px">여행에서 쓴 외화 금액과 그때 환율을 넣으면 원으로 바꿔 금액 칸에 넣고, 메모에 외화 금액을 적어 둡니다. 환율은 통화마다 기억합니다.</div>
      <div class="f"><label class="l">통화</label><select data-k="cur">${Fx.CURRENCIES.map(([c, n]) => `<option value="${c}"${c === last ? ' selected' : ''}>${c} ${U.esc(n)}</option>`).join('')}</select></div>
      <div class="f"><label class="l">외화 금액</label><input type="text" inputmode="decimal" data-k="amt" placeholder="예: 12.50" autocomplete="off"></div>
      <div class="f"><label class="l" data-rl></label><input type="text" inputmode="decimal" data-k="rate" autocomplete="off"></div>
      <div class="f toggle2"><button type="button" data-m="out" class="out">지출</button><button type="button" data-m="in" class="in">수입</button></div>
      <div class="box fx-res"><span class="small muted">원으로</span> <b data-res></b></div></div>`);
    const $ = s => UI.$(s, body);
    let out = expense !== false;
    const showMode = () => UI.$$('.toggle2 button', body).forEach(b => b.classList.toggle('on', (b.dataset.m === 'out') === out));
    const calc = () => {
      try { const [won] = Fx.convert($('[data-k=amt]').value, $('[data-k=cur]').value, $('[data-k=rate]').value); $('[data-res]').textContent = `${UI.money(won)}원`; } catch (e) { $('[data-res]').textContent = $('[data-k=amt]').value.trim() ? e.message : ''; }
    };
    const curChanged = () => {
      const c = $('[data-k=cur]').value, unit = Fx.UNIT[c], w = CUR_WORD[c] || c;
      $('[data-rl]').textContent = unit !== 1 ? `환율 (${unit}${w} = ?원)` : `환율 (1${w} = ?원)`;
      $('[data-k=rate]').value = Fx.rates()[c] || '';
      calc();
    };
    $('[data-k=cur]').onchange = curChanged;
    UI.on(body, 'input', 'input', calc);
    UI.on(body, '.toggle2 button', 'click', (e, b) => { out = b.dataset.m === 'out'; showMode(); });
    showMode();
    curChanged();
    UI.sheet({ title: '외화로 적기', body, buttons: [{ label: '취소' }, { label: '넣기', cls: 'pri', onClick: () => {
      const c = $('[data-k=cur]').value;
      let r;
      try { r = Fx.convert($('[data-k=amt]').value, c, $('[data-k=rate]').value); } catch (e) { UI.toast(e.message); return false; }
      Fx.setRate(c, $('[data-k=rate]').value);
      DB.setMeta('fx_last', c);
      onDone({ won: r[0], note: r[1], expense: out });
      return undefined;
    } }] });
    setTimeout(() => $('[data-k=amt]').focus(), 250);
  }

  // ── 큰돈 나눠 적기 ──
  /** v: 입력 칸의 내역. onDone(ids) */
  function splitSheet(lid, v, onDone) {
    const body = UI.el(`<div><div class="small muted" style="margin-bottom:8px">1년치 자동차보험·연회비처럼 한 번에 낸 큰돈을 여러 달로 나눠 적습니다. 매달 같은 날(그 달에 없으면 말일)에 들어가고, 나머지 원은 첫 달에 더합니다.</div>
      <div class="row" style="margin-bottom:8px"><label class="l" style="margin:0">몇 달로</label><button type="button" class="btn sm" data-d="-1">－</button>
        <input class="inp" type="number" inputmode="numeric" data-k="n" value="12" min="2" max="60" style="width:70px;text-align:center"><button type="button" class="btn sm" data-d="1">＋</button><span>달</span></div>
      <div class="small sp-msg"></div><ul class="list sp-list"></ul></div>`);
    const nInp = UI.$('[data-k=n]', body), msg = UI.$('.sp-msg', body), list = UI.$('.sp-list', body);
    let ok = false;
    function preview() {
      let plan;
      try { plan = Split.plan(v, nInp.value); } catch (e) { list.innerHTML = ''; msg.innerHTML = `<span class="out">${U.esc(e.message)}</span>`; ok = false; return; }
      const total = v.income || v.expense;
      msg.textContent = `${UI.money(total)}원을 ${plan.length}달로 나눠 ${plan.length}건을 넣습니다. 나중에 하나를 지우면 나머지도 함께 지울지 묻습니다.`;
      list.innerHTML = plan.map(p => `<li><div class="grow"><div class="main-t ellipsis"><span class="muted small">${U.esc(p.date)}</span> ${U.esc(p.item)}</div></div>
        <b class="${p.income ? 'in' : 'out'} nowrap">${UI.money(p.income || p.expense)}</b></li>`).join('');
      ok = true;
    }
    UI.on(body, '[data-d]', 'click', (e, b) => { nInp.value = Math.max(2, Math.min(60, (parseInt(nInp.value, 10) || 12) + Number(b.dataset.d))); preview(); });
    nInp.addEventListener('input', preview);
    preview();
    UI.sheet({ title: '나눠 적기', body, full: true, buttons: [{ label: '취소' }, { label: '나눠서 저장', cls: 'pri', onClick: () => {
      if (!ok) { UI.toast(msg.textContent || '나눌 수 없습니다'); return false; }
      let ids;
      try { ids = Split.add(lid, v, nInp.value); } catch (e) { UI.toast(e.message); return false; }
      onDone(ids);
      return undefined;
    } }] });
  }

  // ── 같은 곳 모아보기 ──
  /** 입력 칸 아래 한 줄 ("'스타벅스' 최근 3개월 3건 · 14,500원 ›"), 없으면 '' */
  function sameLine(lid, item) {
    item = (item || '').trim();
    if (!item) return '';
    const sp = Same.place(lid, item, U.today());
    if (!sp || !sp.count) return '';
    const amt = sp.expense || !sp.income ? `${UI.money(sp.expense)}원` : `수입 ${UI.money(sp.income)}원`;
    const short = Array.from(item).length <= 12 ? item : Array.from(item).slice(0, 11).join('') + '…';
    return `'${short}' 최근 3개월 ${sp.count}건 · ${amt} ›`;
  }
  function sameSheet(lid, item) {
    const sp = Same.place(lid, item, U.today());
    if (!sp) return;
    const top = Math.max(1, ...sp.months.map(m => m.expense));
    const cmap = L.categoryMap(lid);
    const body = UI.el(`<div><div class="box"><div class="small muted">최근 3개월 (${U.dotMD(sp.start)} ~ ${U.dotMD(sp.end)})</div>
      <div class="ins-big"><b class="out">${UI.money(sp.expense)}원</b> · ${sp.count}건</div>
      <div class="small">한 번에 평균 ${UI.money(sp.avg)}원${sp.income ? ` · 수입 ${UI.money(sp.income)}원` : ''}</div>
      ${sp.months.map(m => `<div class="sp-m"><span class="nm">${Number(m.ym.slice(5))}월</span>${Extra.bar(m.expense > 0 ? Math.floor(m.expense * 100 / top) : 0)}<span class="v small">${UI.money(m.expense)}원 (${m.count}건)</span></div>`).join('')}</div>
      ${Entry.listHtml(sp.rows, cmap, '')}</div>`);
    Entry.bindOpen(UI.sheet({ title: `같은 곳 — ${item}`, body, full: true }), sp.rows);
  }

  // ── 지우기 (나눠 적은 내역이면 묶음째 지울지 묻기) → 휴지통 ──
  /** ids 를 지움. 끝나면 after(지운 수) */
  async function deleteAsk(ids, after) {
    const extra = [];
    for (const i of ids) for (const x of Split.group(i)) if (!ids.includes(x) && !extra.includes(x)) extra.push(x);
    if (extra.length) {
      const v = await UI.dialog(`나눠 적은 내역입니다. 함께 나눠 적은 ${extra.length}건도 지울까요?\n(지운 내역은 휴지통에 ${Trash.KEEP_DAYS}일 동안 보관됩니다)`,
        [['취소', '', false], [`고른 것만 (${ids.length}건)`, '', 'one'], [`모두 지우기 (${ids.length + extra.length}건)`, 'danger', 'all']]);
      if (!v) return;
      if (v === 'all') ids = ids.concat(extra);
    } else if (!(await UI.confirm(`${ids.length === 1 ? '이 내역을' : `고른 내역 ${ids.length}건을`} 삭제할까요?\n(휴지통에 ${Trash.KEEP_DAYS}일 동안 보관됩니다)`, '삭제', true))) return;
    L.deleteEntries(ids);
    App.dataChanged();
    UI.toast(`${ids.length}건을 휴지통으로 옮겼어요 — ${Trash.KEEP_DAYS}일 안에 되살릴 수 있어요`, 3500);
    if (after) after(ids.length);
  }

  // ── 휴지통 ──
  const WHY = { category: '카테고리 삭제', asset: '통장 거래와 함께' };
  function trashSheet() {
    const lid = App.lid;
    const body = UI.el(`<div><div class="small muted tr-n" style="margin-bottom:6px"></div><ul class="list trl"></ul></div>`);
    const ul = UI.$('.trl', body);
    let items = [];
    function draw() {
      items = Trash.items(lid);
      const cmap = L.categoryMap(lid);
      UI.$('.tr-n', body).textContent = `지운 내역은 ${Trash.KEEP_DAYS}일 동안 여기에 보관했다가 저절로 지워집니다. 지금 ${items.length}건 — 체크한 뒤 [되살리기]를 누르면 원래 자리로 돌아갑니다.`;
      ul.innerHTML = items.length ? items.map(x => {
        const e = x.entry;
        const sub = [`${String(x.deleted).slice(5, 16).replace('-', '.')} 지움${WHY[x.why] ? ` (${WHY[x.why]})` : ''}`, e.code ? cat(cmap, e.code) : '',
          x.photos ? `사진 ${x.photos}장` : '', `${Trash.daysLeft(x.deleted)}일 남음`].filter(Boolean).map(U.esc).join(' · ');
        return `<li data-t="${x.id}"><input type="checkbox" data-c style="width:22px;height:22px"><div class="grow"><div class="main-t ellipsis"><span class="muted small">${U.esc(e.date || '')}</span> ${U.esc(e.item || '')}</div>
          <div class="sub ellipsis">${sub}</div></div><div class="right nowrap">${e.income ? `<div class="in bold">+${UI.money(e.income)}</div>` : ''}${e.expense ? `<div class="out bold">-${UI.money(e.expense)}</div>` : ''}</div></li>`;
      }).join('') : `<li class="muted">휴지통이 비어 있어요</li>`;
      UI.on(ul, 'li[data-t]', 'click', (e, li) => { if (e.target.dataset.c === undefined) { const cb = UI.$('[data-c]', li); cb.checked = !cb.checked; } });
    }
    const checked = () => UI.$$('li[data-t]', ul).filter(li => UI.$('[data-c]', li).checked).map(li => Number(li.dataset.t));
    draw();
    UI.sheet({ title: '휴지통', body, full: true, onClose: () => App.dataChanged(), buttons: [
      { label: '비우기', cls: 'danger', onClick: () => {
        const n = Trash.count(lid);
        if (!n) { UI.toast('휴지통이 비어 있어요'); return false; }
        UI.confirm(`휴지통의 ${n}건을 모두 영구 삭제할까요?\n되돌릴 수 없습니다.`, '모두 영구 삭제', true).then(ok => { if (ok) { Trash.empty(lid); draw(); } });
        return false;
      } },
      { label: '영구 삭제', onClick: () => {
        const ids = checked();
        if (!ids.length) { UI.toast('지울 것을 체크하세요'); return false; }
        UI.confirm(`체크한 ${ids.length}건을 영구 삭제할까요?\n되돌릴 수 없습니다.`, '영구 삭제', true).then(ok => { if (ok) { Trash.remove(ids); draw(); } });
        return false;
      } },
      { label: '되살리기', cls: 'pri', onClick: () => {
        const ids = checked();
        if (!ids.length) { UI.toast('되살릴 것을 체크하세요'); return false; }
        const n = Trash.restore(ids).length;
        draw();
        UI.toast(`${n}건을 되살렸어요`);
        return false;
      } }] });
  }

  // ── 카테고리 그림 고르기 ──
  /** opts: {current, name, onPick(그림 또는 '')} */
  function emojiPicker(opts) {
    const cur = opts.current || '';
    const sug = Emo.suggest(opts.name);
    const body = UI.el(`<div><div class="emogrid">${Emo.CHOICES.map(e => `<button type="button" data-e="${e}" class="${e === cur ? 'on' : ''}">${e}</button>`).join('')}</div>
      <div class="row" style="margin-top:8px"><label class="small muted">직접</label><input class="inp grow" type="text" data-x value="${U.esc(cur)}" placeholder="다른 그림을 붙여넣어도 됩니다"></div>
      <div class="row wrap" style="margin-top:8px"><button type="button" class="btn sm" data-none>그림 없애기</button>${sug ? `<button type="button" class="btn sm" data-sug>이름에 어울리는 그림 ${sug}</button>` : ''}</div></div>`);
    let sh = null;
    const pick = e => { sh.close(); opts.onPick(e); };
    UI.on(body, '[data-e]', 'click', (e, b) => pick(b.dataset.e));
    UI.$('[data-none]', body).onclick = () => pick('');
    const sb = UI.$('[data-sug]', body);
    if (sb) sb.onclick = () => pick(sug);
    sh = UI.sheet({ title: opts.name ? `그림 고르기 — ${opts.name}` : '그림 고르기', body,
      buttons: [{ label: '이 그림으로', cls: 'pri', onClick: () => { const v = UI.$('[data-x]', body).value.trim(); sh.close(); opts.onPick(v); return false; } }] });
    return sh;
  }

  // ── 설정 › 결제수단 ──
  function paySettingsSheet() {
    const body = UI.el('<div><div class="small muted pay-base" style="margin-bottom:8px"></div><div class="section-t">직접 만든 결제수단</div><ul class="list payl"></ul></div>');
    const ul = UI.$('.payl', body);
    function draw() {
      forget();
      const cards = Pay.options().filter(([v]) => v.startsWith('card:')).map(([, n]) => n);
      UI.$('.pay-base', body).innerHTML = `가계부 내역을 넣을 때 고를 결제수단입니다. 통계 › 결제수단에서 결제수단별로 모아 봅니다.<br>기본: 현금 · 카드 · 계좌이체 · 간편결제<br>${
        cards.length ? `자산의 신용카드: ${cards.map(U.esc).join(', ')}` : '자산 › 카드에 카드를 넣으면 카드마다 고를 수 있고 카드 실적도 셉니다.'}`;
      const names = Pay.custom();
      ul.innerHTML = names.length ? names.map((n, i) => `<li data-i="${i}"><div class="grow main-t ellipsis">${U.esc(n)}</div>
        <button class="btn sm" data-ren>이름</button><button class="iconbtn" data-mv="-1" aria-label="위로"${i ? '' : ' disabled'}>▲</button>
        <button class="iconbtn" data-mv="1" aria-label="아래로"${i < names.length - 1 ? '' : ' disabled'}>▼</button><button class="iconbtn" data-del aria-label="지우기">✕</button></li>`).join('')
        : '<li class="muted small">지역화폐·상품권·회사 카드처럼 따로 모아 보고 싶은 것을 [추가]로 넣으세요.</li>';
      const nameOf = b => names[Number(b.closest('li').dataset.i)];
      UI.on(ul, '[data-mv]', 'click', (e, b) => {
        const i = Number(b.closest('li').dataset.i), j = i + Number(b.dataset.mv);
        const a = names.slice();
        [a[i], a[j]] = [a[j], a[i]];
        Pay.setCustom(a);
        draw();
      });
      UI.on(ul, '[data-del]', 'click', (e, b) => {
        const n = nameOf(b);
        UI.confirm(`결제수단 '${n}'을(를) 목록에서 지울까요?\n이미 넣은 내역에는 이름이 그대로 남습니다.`, '지우기', true).then(ok => {
          if (ok) { Pay.setCustom(names.filter(x => x !== n)); draw(); App.dataChanged(); }
        });
      });
      UI.on(ul, '[data-ren]', 'click', (e, b) => {
        const n = nameOf(b);
        UI.formSheet({ title: '결제수단 이름 바꾸기', fields: [{ k: 'name', label: '새 이름', type: 'text', req: true, hint: '그 이름으로 넣은 내역·자주 쓰는 내역·고정 수입·지출도 함께 바뀝니다' }], values: { name: n },
          onSave: v => { Pay.renameCustom(n, v.name); draw(); App.dataChanged(); } });
      });
    }
    draw();
    UI.sheet({ title: '결제수단', body, full: true, buttons: [{ label: '추가', cls: 'pri', onClick: () => {
      UI.formSheet({ title: '결제수단 추가', fields: [{ k: 'name', label: '이름', type: 'text', req: true, placeholder: '예: 지역화폐, 상품권, 회사 카드' }],
        onSave: v => {
          if (Pay.KINDS.some(k => k[1] === v.name) || Pay.custom().includes(v.name)) throw new Error('같은 이름의 결제수단이 있습니다');
          Pay.setCustom(Pay.custom().concat([v.name]));
          draw();
          App.dataChanged();
        } });
      return false;
    } }] });
  }

  // ── 통계 › 주별 ──
  function weekView(c, s, rerender) {
    const lid = App.lid;
    c.appendChild(UI.monthNav(s.y, s.m, (y, m) => { s.y = y; s.m = m; rerender(); }));
    const weeks = Week.ofMonth(lid, s.y, s.m, sd());
    const wb = Week.budget(lid);
    c.appendChild(UI.el(`<ul class="list wkl">${weeks.map((w, i) => {
      const b = w.budget ? Math.floor(w.budget * w.days / 7) : 0;            // 그 달에 걸친 날만큼
      const p = U.pct(w.expense, b);
      return `<li class="tap" data-i="${i}"><span class="chip">${i + 1}주</span><div class="grow"><div class="main-t">${U.dotMD(w.start)} ~ ${U.dotMD(w.end)} <span class="small muted">(${w.days}일)</span></div>
        ${b ? `${Extra.bar(p)}<div class="sub">주간 예산 ${UI.money(b)}원의 <b class="${p > 100 ? 'out' : ''}">${p}%</b></div>` : ''}</div>
        <div class="right nowrap">${w.income ? `<div class="in small">+${UI.money(w.income)}</div>` : ''}<div class="out bold">${UI.money(w.expense)}</div></div></li>`;
    }).join('')}</ul>`));
    c.appendChild(UI.el(`<div class="small muted" style="margin-top:6px">${wb ? `주간 예산 ${UI.money(wb)}원 (달의 처음·끝 주는 그 달에 걸친 날만큼 나눠 셈). ` : '주간 예산을 정하면 주마다 예산 대비를 보여 줍니다 — 가계부 화면의 예산 막대 › 예산 정하기에서. '}한 주는 월요일부터 일요일까지입니다. 주를 누르면 그 주 내역을 봅니다.</div>`));
    UI.on(c, '.wkl li[data-i]', 'click', (e, li) => { const w = weeks[Number(li.dataset.i)]; listSheet(`${U.dotMD(w.start)} ~ ${U.dotMD(w.end)}`, L.search(lid, { start: w.start, end: w.end })); });
  }
  /** 내역 목록 창 — 제목 뒤에 건수 */
  const listSheet = (title, rows) => Entry.listSheet(`${title} (${rows.length}건)`, rows);

  // ── 통계 › 결제수단 (+ 카드 실적) ──
  function payView(c, s, rerender) {
    const lid = App.lid;
    c.appendChild(UI.monthNav(s.y, s.m, (y, m) => { s.y = y; s.m = m; rerender(); }));
    const [start, end] = U.settlePeriod(s.y, s.m, sd());
    const rows = Pay.summary(lid, start, end);
    c.appendChild(UI.el('<div class="small muted" style="margin-bottom:6px">내역을 넣을 때 고른 결제수단으로 모아 봅니다. 누르면 그 결제수단의 내역을 봅니다.</div>'));
    if (!rows.length) c.appendChild(UI.el(UI.empty('이 달에는 내역이 없어요', 'b30')));
    else {
      c.appendChild(UI.el(`<ul class="list payst">${rows.map((r, i) => `<li class="tap" data-i="${i}"><div class="grow"><div class="main-t ellipsis">${r.pay.startsWith('card:') ? '💳 ' : ''}${U.esc(r.label)}</div>
        ${Extra.bar(r.pct || 0)}<div class="sub">${r.count}건${r.pct !== null ? ` · 지출의 ${r.pct}%` : ''}</div></div>
        <div class="right nowrap">${r.income ? `<div class="in small">+${UI.money(r.income)}</div>` : ''}<div class="out bold">${UI.money(r.expense)}</div></div></li>`).join('')}</ul>`));
      UI.on(c, '.payst li[data-i]', 'click', (e, li) => {
        const r = rows[Number(li.dataset.i)];
        listSheet(r.pay ? r.label : '결제수단 안 정함', Pay.entries(lid, r.pay, start, end));
      });
    }
    const perf = perfHtml(s.y, s.m);
    if (perf) c.appendChild(UI.el(`<div>${perf}</div>`));
  }
  /** 카드 실적 (목표를 정한 카드만). 없으면 '' */
  function perfHtml(y, m) {
    const perf = Perf.cards(y, m).filter(p => p.target);
    if (!perf.length) return '';
    return `<div class="section-t">${m}월 카드 실적 <span class="small muted">(1일~말일, 모든 가계부)</span></div><ul class="list perfl">${perf.map(p => {
      const done = p.spent >= p.target;
      return `<li><div class="grow"><div class="main-t ellipsis">💳 ${U.esc(p.label)}</div>${Extra.bar(Math.min(100, p.pct || 0))}
        <div class="sub">${UI.money(p.spent)} / ${UI.money(p.target)}원 ${done ? '<b class="in">채움 ✓</b>' : `(${p.pct}% · ${UI.money(p.left)}원 남음)`}</div></div></li>`;
    }).join('')}</ul>`;
  }

  // ── 통계 › 저축 (월별 저축 추이) ──
  function savingsView(c, s, rerender) {
    const lid = App.lid;
    c.appendChild(UI.yearNav(s.y, y => { s.y = y; rerender(); }));
    const tr = Sav.trend(lid, s.y, sd());
    const top = Math.max(1, ...tr.rows.map(r => Math.abs(r.saved)));
    const rate = r => (r.rate === null ? '—' : `${r.rate}%`);
    const rcls = r => ((r.rate || 0) < 0 ? 'out' : (r.rate || 0) >= 20 ? 'in' : '');
    c.appendChild(UI.el(`<ul class="list savl">${tr.rows.map(r => `<li><span class="chip">${r.month}월</span><div class="grow">
      <div class="small">모은 돈 <b class="${r.saved < 0 ? 'out' : 'in'}">${UI.money(r.saved)}</b> · 저축률 <b class="${rcls(r)}">${rate(r)}</b></div>
      <div class="pbar"><i class="${r.saved < 0 ? 'over' : ''}" style="width:${r.saved ? Math.floor(Math.abs(r.saved) * 100 / top) : 0}%"></i></div>
      <div class="sub">수입 ${UI.money(r.income)} · 지출 ${UI.money(r.expense)}${r.saving ? ` · 저축·적금 ${UI.money(r.saving)}` : ''}</div></div>
      <div class="right nowrap"><div class="tiny muted">누계</div><div class="bold ${r.cum < 0 ? 'out' : ''}">${UI.money(r.cum)}</div></div></li>`).join('')}</ul>`));
    const t = tr.total;
    c.appendChild(UI.el(`<div class="box"><div class="kv"><b>${s.y}년 합계</b><span>저축률 <b class="${rcls(t)}">${rate(t)}</b></span></div>
      <div class="kv small"><span>수입 ${UI.money(t.income)} · 지출 ${UI.money(t.expense)}</span></div>
      <div class="kv"><span>모은 돈</span><b class="${t.saved < 0 ? 'out' : 'in'}">${UI.money(t.saved)}원</b></div></div>`));
    const cmap = L.categoryMap(lid);
    const names = tr.codes.map(x => cmap[x] || x).join(', ');
    c.appendChild(UI.el(`<div class="small muted" style="margin-top:6px">남은 돈 = 수입 − 지출. 모은 돈 = 남은 돈 + 저축·적금으로 낸 돈 (지출로 적었지만 실제로는 모은 돈). 저축률 = 모은 돈 ÷ 수입.
      ${names ? `저축·적금으로 센 세부 카테고리: ${U.esc(names)}` : '이름에 저축·적금·투자·연금이 들어간 세부 카테고리가 없어 남은 돈만 셉니다.'}</div>`));
  }

  // ── 고정비 한눈에 ──
  function fixedHtml(lid, y, m) {
    const fx = Fixed.summary(lid, y, m, sd(), U.today());
    const f = UI.money;
    if (!fx.items.length) return `<div class="small muted">${m}월에 들어갈 고정 수입·지출이 없어요.</div>`;
    const el = fx.expected_left;
    return `<div class="fixed"><div><b>${m}월 고정 지출</b> ${f(fx.out_total)}원 <span class="small muted">(나감 ${f(fx.out_done)} · 남음 ${f(fx.out_left)})</span></div>
      ${fx.in_total ? `<div><b>고정 수입</b> ${f(fx.in_total)}원 <span class="small muted">(남음 ${f(fx.in_left)})</span></div>` : ''}
      <div class="small">변동 지출 ${f(fx.variable)}원 <span class="muted">(지출 ${f(fx.expense)} − 고정으로 넣은 것 ${f(fx.fixed_expense)})</span></div>
      <div>고정비까지 빼면 이달 말 남을 돈 (예상): <b class="${el < 0 ? 'out' : 'in'}">${f(el)}원</b></div></div>`;
  }

  // ── 매일 입력 알림 (휴대폰만) ──
  const remindOn = () => App.pref('remind_on') === 'true';
  const remindTime = () => (/^\d{2}:\d{2}$/.test(App.pref('remind_time') || '') ? App.pref('remind_time') : '21:00');
  /** 앱을 켤 때 알림 예약을 다시 걸어 둠 (업데이트·재시작 뒤에도 이어지게) */
  function rearm() {
    try {
      const N = App.native;
      if (!N || !N.setReminder) return;
      const [h, m] = remindTime().split(':').map(Number);
      N.setReminder(remindOn(), h, m, false);
    } catch (_) { /* 알림은 덤 */ }
  }
  function reminderSheet() {
    const N = App.native;
    if (!N || !N.setReminder) { UI.alert('이 앱 판에서는 알림을 쓸 수 없습니다. 앱을 새 버전으로 업데이트하세요.'); return; }
    const body = UI.el(`<div class="form"><label class="check"><input type="checkbox" data-k="on"${remindOn() ? ' checked' : ''}> 매일 알림 받기</label>
      <div class="f"><label class="l">알림 시각</label><input type="time" data-k="time" value="${remindTime()}"></div>
      <div class="small muted">정한 시각에 그날 적은 내역이 하나도 없으면 "오늘 쓴 돈을 적어 볼까요?" 알림을 보냅니다. 이미 적었으면 알리지 않아요. 알림을 누르면 바로 새 내역 입력 창이 열립니다.
      휴대폰 절전 상태에 따라 몇 분 늦게 올 수 있습니다.</div>
      <div class="small rm-st" style="margin-top:6px"></div>
      <button type="button" class="btn sm" data-test style="margin-top:8px">지금 알림 한 번 보내 보기</button></div>`);
    const st = UI.$('.rm-st', body);
    const showSt = () => {
      let r = {};
      try { r = JSON.parse(N.reminderStatus()); } catch (_) { r = {}; }
      st.innerHTML = r.allowed === false ? '<span class="out">휴대폰 설정에서 이 앱의 알림이 꺼져 있어요. 켜야 알림이 옵니다 (설정 → 애플리케이션 → 우리집 가계부 → 알림).</span>' : '';
    };
    showSt();
    UI.$('[data-test]', body).onclick = () => App.nativeAsync('testReminder').then(r => { showSt(); UI.toast(r.ok ? '알림을 보냈어요. 위쪽 알림 창을 보세요' : (r.error || '알림을 보내지 못했어요')); });
    UI.sheet({ title: '매일 입력 알림', body, buttons: [{ label: '취소' }, { label: '저장', cls: 'pri', onClick: () => {
      const on = UI.$('[data-k=on]', body).checked, t = UI.$('[data-k=time]', body).value;
      if (!/^\d{2}:\d{2}$/.test(t)) { UI.toast('알림 시각을 확인하세요'); return false; }
      App.setPref('remind_on', on ? 'true' : null);
      App.setPref('remind_time', t);
      const [h, m] = t.split(':').map(Number);
      let r = {};
      try { r = JSON.parse(N.setReminder(on, h, m, true)); } catch (e) { r = { ok: false, error: e.message }; }
      if (!r.ok) { UI.alert('알림을 맞추지 못했습니다.\n' + (r.error || '')); return undefined; }
      UI.toast(on ? `매일 ${t}에 알려 드릴게요 (그날 적은 게 없을 때만)` : '매일 알림을 껐어요', 3000);
      App.dataChanged();
      return undefined;
    } }] });
  }

  // ── 앱을 켤 때 (PC판 app.py 와 같음) ──
  function onStart() {
    try { Trash.purge(); } catch (_) { /* 보관 기간 정리 실패는 무시 */ }
    try {
      if (!DB.getMeta('cat_emoji_init')) {             // 1.8.0 을 처음 열 때 한 번 카테고리 이름 보고 그림을 넣어 둠
        DB.tx(() => { for (const l of L.ledgers()) Emo.fillDefaults(l.id); DB.setMeta('cat_emoji_init', '1'); });
      }
    } catch (_) { /* 그림은 덤 */ }
    rearm();
  }

  return { forget, ctx, cat, payLabel, payOptions, fxSheet, splitSheet, sameLine, sameSheet, deleteAsk, trashSheet, emojiPicker,
    paySettingsSheet, weekView, payView, perfHtml, savingsView, fixedHtml, listSheet, reminderSheet, remindOn, remindTime, rearm, onStart };
})();
