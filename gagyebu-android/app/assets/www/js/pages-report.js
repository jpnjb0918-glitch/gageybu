/* 결산 보고서·예산·그래프 */
'use strict';
Pages.report = (() => {
  const t = U.parts(U.today());
  const s = { kind: 'monthly', y: t[0], m: t[1], start: U.iso(t[0], t[1], 1), end: U.today() };
  const KINDS = [['monthly', '월결산'], ['yearly', '년결산'], ['daily', '일일'], ['custom', '기간'], ['budget', '예산']];

  function render(c, p, tools) {
    const lid = App.lid;
    const sd = Rep.settleDay();
    const sdBtn = UI.el(`<button class="btn sm">결산일 ${sd}일</button>`);
    sdBtn.onclick = () => UI.formSheet({ title: '결산일', fields: [{ k: 'sd', label: '결산일 (1~31)', type: 'int', hint: '5일이면 5일~다음달 4일을 한 달로 셉니다 (월급날 기준 등)' }],
      values: { sd }, onSave: v => { if (!v.sd || v.sd < 1 || v.sd > 31) throw new Error('1~31 사이로 입력하세요.'); DB.setMeta('settle_day', v.sd); App.dataChanged(); } });
    tools.appendChild(sdBtn);
    c.appendChild(UI.seg(KINDS, s.kind, k => { s.kind = k; App.render(); }));
    let rep;
    if (s.kind === 'monthly' || s.kind === 'daily') {
      c.appendChild(UI.monthNav(s.y, s.m, (y, m) => { s.y = y; s.m = m; App.render(true); }));
      rep = s.kind === 'monthly' ? Rep.monthly(lid, s.y, s.m, sd) : Rep.daily(lid, s.y, s.m);
    } else if (s.kind === 'yearly' || s.kind === 'budget') {
      c.appendChild(UI.yearNav(s.y, y => { s.y = y; App.render(true); }));
      rep = s.kind === 'yearly' ? Rep.yearly(lid, s.y, sd) : Rep.budgetYear(lid, s.y);
    } else {
      const f = UI.el(`<div class="row" style="margin-bottom:8px"><input class="inp grow" type="date" data-k="start" value="${s.start}"><span>~</span><input class="inp grow" type="date" data-k="end" value="${s.end}"></div>`);
      UI.on(f, 'input', 'change', (e, x) => { if (U.isValidIso(x.value)) { s[x.dataset.k] = x.value; App.render(true); } });
      c.appendChild(f);
      if (s.end < s.start) { c.appendChild(UI.el('<div class="empty">끝 날짜가 시작 날짜보다 빠릅니다</div>')); return; }
      rep = Rep.custom(lid, s.start, s.end);
    }
    c.appendChild(UI.el(`<div class="section-t">${U.esc(rep.title)}</div>`));
    if (rep.note) c.appendChild(UI.el(`<div class="small muted" style="margin:-4px 0 6px">${U.esc(rep.note)}</div>`));
    c.appendChild(table(rep));
    UI.on(c, 'td.tap', 'click', (e, td) => cellTap(rep, Number(td.dataset.r), Number(td.dataset.c)));
  }

  function budgetYm(rep, col) {
    if (s.kind === 'budget') return rep.periods[col];
    if (s.kind === 'monthly' && col === 3) return U.ym(s.y, s.m);
    if (s.kind === 'monthly' && col === 4) { const [y, m] = U.addMonths(s.y, s.m, 1); return U.ym(y, m); }
    return null;
  }
  function table(rep) {
    let html = `<div class="tablewrap"><table class="rep"><tr><th>계정과목</th>${rep.columns.map(cn => `<th>${U.esc(cn)}</th>`).join('')}</tr>`;
    let lastGroup = null;
    rep.rows.forEach((r, ri) => {
      if (r.kind === 'cat' && r.group !== lastGroup) {
        lastGroup = r.group;
        html += `<tr class="grp"><td colspan="${rep.columns.length + 1}">${U.esc(r.group)}</td></tr>`;
      }
      const cls = r.kind === 'subtotal' ? 'sub' : r.kind === 'footer' ? 'foot' : '';
      const label = r.kind === 'cat' ? `${U.esc(r.code)} ${U.esc(r.label)}` : U.esc(r.kind === 'subtotal' ? `${r.group} 소계` : r.label);
      html += `<tr class="${cls}"><td>${label}</td>${r.values.map((v, ci) => {
        const tap = r.kind === 'cat' && (budgetYm(rep, ci) || rep.periods[ci]);
        return `<td class="${v < 0 ? 'neg' : ''}${tap ? ' tap' : ''}" data-r="${ri}" data-c="${ci}">${v === null || v === undefined ? '' : UI.money(v, r.kind === 'cat')}</td>`;
      }).join('')}</tr>`;
    });
    return UI.el(html + '</table></div>');
  }
  function cellTap(rep, ri, ci) {
    const r = rep.rows[ri];
    const lid = App.lid;
    const ymv = budgetYm(rep, ci);
    if (ymv) {
      const cur = Rep.budgets(lid, ymv)[r.code] || 0;
      UI.formSheet({ title: `예산 — ${ymv} ${r.label}`, fields: [{ k: 'amount', label: '예산 금액 (0이면 지움)', type: 'money' }], values: { amount: cur },
        onSave: v => { Rep.setBudget(lid, ymv, r.code, v.amount); App.dataChanged(); } });
      return;
    }
    const per = rep.periods[ci];
    if (!per) return;
    const rows = L.search(lid, { start: per[0], end: per[1], codes: [r.code] });
    const cmap = L.categoryMap(lid);
    const sh = UI.sheet({ title: `${r.label} (${per[0]} ~ ${per[1]})`, full: true,
      body: rows.length ? `<ul class="list">${rows.map(x => Entry.rowHtml(x, null, true, cmap)).join('')}</ul>` : UI.empty('내역이 없어요') });
    UI.on(sh.body, 'li[data-id]', 'click', (e, li) => { sh.close(); Entry.open({ entry: rows.find(x => x.id === Number(li.dataset.id)) }); });
  }
  return { title: '결산 보고서', sticker: 'b30', sub: '한 달 성적표 두근두근', render };
})();

// ════════ 그래프 ════════
Pages.graph = (() => {
  const s = { y: Number(U.today().slice(0, 4)), month: 0, sel: '' };
  const PALETTE = ['#E0507A', '#2BB5B5', '#1F6FB2', '#F0A020', '#7A5CC6', '#3A9A3A', '#C0392B', '#24595A', '#D4A017', '#8E44AD', '#16A085', '#7F8C8D'];

  function render(c) {
    const lid = App.lid;
    c.appendChild(UI.yearNav(s.y, y => { s.y = y; App.render(true); }));
    const gs = L.groups(lid), cats = L.categories(lid);
    const ctl = UI.el(`<div class="row" style="margin-bottom:8px">
      <select class="inp grow" data-k="month"><option value="0">월별 (1~12월)</option>${Array.from({ length: 12 }, (_, i) => `<option value="${i + 1}"${s.month === i + 1 ? ' selected' : ''}>${i + 1}월 일별</option>`).join('')}</select>
      <select class="inp grow" data-k="sel"><option value="">대분류 전체</option>
        ${gs.map(g => `<option value="g:${U.esc(g.code)}"${s.sel === 'g:' + g.code ? ' selected' : ''}>(${U.esc(g.code)}) ${U.esc(g.name)} 소분류별</option>`).join('')}
        ${cats.map(x => `<option value="c:${U.esc(x.code)}"${s.sel === 'c:' + x.code ? ' selected' : ''}>${U.esc(x.code)} ${U.esc(x.name)}</option>`).join('')}</select></div>`);
    UI.$('[data-k=month]', ctl).value = String(s.month);
    UI.on(ctl, 'select', 'change', (e, x) => { s[x.dataset.k] = x.dataset.k === 'month' ? Number(x.value) : x.value; App.render(true); });
    c.appendChild(ctl);
    const o = { month: s.month || null, settleDay: Rep.settleDay() };
    if (s.sel.startsWith('g:')) o.group = s.sel.slice(2);
    if (s.sel.startsWith('c:')) o.code = s.sel.slice(2);
    const { labels, series } = Rep.graphSeries(lid, s.y, o);
    const shown = series.filter(([, v]) => v.some(x => x));
    if (!shown.length) { c.appendChild(UI.el(UI.empty('그릴 자료가 없어요', 'b26'))); return; }
    c.appendChild(UI.el(chart(labels, shown)));
    c.appendChild(UI.el(`<div class="legend">${shown.map(([n], i) => `<span><i style="background:${PALETTE[i % PALETTE.length]}"></i>${U.esc(n)}</span>`).join('')}</div>`));
    let html = `<div class="tablewrap"><table class="rep"><tr><th>항목</th>${labels.map(l => `<th>${U.esc(l)}</th>`).join('')}<th>합계</th></tr>`;
    html += shown.map(([n, v]) => `<tr><td>${U.esc(n)}</td>${v.map(x => `<td class="${x < 0 ? 'neg' : ''}">${UI.money(x, true)}</td>`).join('')}<td class="bold">${UI.money(U.sum(v))}</td></tr>`).join('');
    c.appendChild(UI.el(html + '</table></div>'));
  }
  function chart(labels, series) {
    const W = 360, H = 220, pl = 46, pr = 8, pt = 10, pb = 24;
    const all = series.flatMap(([, v]) => v);
    let max = Math.max(0, ...all), min = Math.min(0, ...all);
    if (max === min) max = min + 1;
    const step = niceStep((max - min) / 4);
    max = Math.ceil(max / step) * step;
    min = Math.floor(min / step) * step;
    const x = i => pl + (labels.length === 1 ? 0 : (i * (W - pl - pr)) / (labels.length - 1));
    const y = v => pt + ((max - v) * (H - pt - pb)) / (max - min);
    let g = '';
    for (let v = min; v <= max + 1e-9; v += step) {
      g += `<line x1="${pl}" x2="${W - pr}" y1="${y(v)}" y2="${y(v)}" stroke="${v === 0 ? '#888' : '#DCEEEE'}" stroke-width="1"/>`;
      g += `<text x="${pl - 4}" y="${y(v) + 3}" font-size="9" text-anchor="end" fill="#6F8080">${short(v)}</text>`;
    }
    const every = Math.ceil(labels.length / 12);
    labels.forEach((l, i) => { if (i % every === 0) g += `<text x="${x(i)}" y="${H - 8}" font-size="9" text-anchor="middle" fill="#6F8080">${U.esc(l)}</text>`; });
    series.forEach(([, v], k) => {
      const col = PALETTE[k % PALETTE.length];
      g += `<polyline fill="none" stroke="${col}" stroke-width="2" points="${v.map((val, i) => `${x(i).toFixed(1)},${y(val).toFixed(1)}`).join(' ')}"/>`;
      if (labels.length <= 31) g += v.map((val, i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(val).toFixed(1)}" r="2.2" fill="${col}"/>`).join('');
    });
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">${g}</svg>`;
  }
  function niceStep(raw) {
    if (raw <= 0) return 1;
    const p = Math.pow(10, Math.floor(Math.log10(raw)));
    for (const k of [1, 2, 2.5, 5, 10]) if (raw <= k * p) return k * p;
    return 10 * p;
  }
  function short(v) {
    const a = Math.abs(v);
    if (a >= 1e8) return (v / 1e8).toFixed(a % 1e8 ? 1 : 0) + '억';
    if (a >= 1e4) return (v / 1e4).toFixed(a % 1e4 ? 1 : 0) + '만';
    return String(v);
  }
  return { title: '그래프', sticker: 'b26', sub: '쑥쑥 크는 그래프 (^-^)', render, tab: 'more' };
})();
