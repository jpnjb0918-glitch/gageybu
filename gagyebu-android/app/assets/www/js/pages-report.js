/* 결산 보고서·예산·그래프 */
'use strict';
Pages.report = (() => {
  const t = U.parts(U.today());
  const s = { kind: 'monthly', y: t[0], m: t[1], start: U.iso(t[0], t[1], 1), end: U.today(), tagAll: true };
  const KINDS = [['monthly', '월별'], ['yearly', '연간'], ['daily', '일별'], ['weekly', '주별'], ['custom', '기간'],
    ['budget', '예산'], ['savings', '저축'], ['pay', '결제수단'], ['insight', '리포트'], ['tags', '태그']];

  function render(c, p, tools) {
    const lid = App.lid;
    const sd = Rep.settleDay();
    const sdBtn = UI.el(`<button class="btn sm">월 시작일 ${sd}일</button>`);
    sdBtn.onclick = () => Pages.settings.settleSheet();
    tools.appendChild(sdBtn);
    const segEl = UI.seg(KINDS, s.kind, k => {
      if (k === 'insight' && s.kind !== 'insight') [s.y, s.m] = Ins.periodOf(U.today(), sd);    // 처음엔 오늘이 든 달 (결산일 기준)
      s.kind = k;
      App.render();
    });
    segEl.classList.add('rows');                     // 10개라 두 줄 (5개씩)
    c.appendChild(segEl);
    const again = () => App.render(true);
    if (s.kind === 'weekly') { Money.weekView(c, s, again); return; }       // 1.8.0
    if (s.kind === 'pay') { Money.payView(c, s, again); return; }
    if (s.kind === 'savings') { Money.savingsView(c, s, again); return; }
    if (s.kind === 'insight') {
      c.appendChild(UI.monthNav(s.y, s.m, (y, m) => { s.y = y; s.m = m; App.render(true); }));
      c.appendChild(UI.el(Extra.insightHtml(lid, s.y, s.m)));
      return;
    }
    if (s.kind === 'tags') { Extra.tagsView(c, lid, s, () => App.render(true)); return; }
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
    const note = [rep.note, '금액을 누르면 ' + (s.kind === 'budget' ? '예산 입력' : '그 내역')].filter(Boolean).join(' · ');
    c.appendChild(UI.el(`<div class="small muted" style="margin:-4px 0 6px">${U.esc(note)}</div>`));
    c.appendChild(table(rep));
    UI.on(c, 'td.tap', 'click', (e, td) => cellTap(rep, Number(td.dataset.r), Number(td.dataset.c)));
  }

  function budgetYm(rep, col) {
    if (s.kind === 'budget') return rep.periods[col];
    if (s.kind === 'monthly' && col === 3) return U.ym(s.y, s.m);
    if (s.kind === 'monthly' && col === 4) { const [y, m] = U.addMonths(s.y, s.m, 1); return U.ym(y, m); }
    return null;
  }
  /** 결산 표: 대분류 이름 줄 → 계정 줄(줄무늬) → 소계 줄(굵은 선으로 끝) … → 합계 줄들. 계정 줄의 0 은 비우고, 소계·합계의 0 은 흐리게 */
  function table(rep) {
    let html = `<table class="rep"><tr><th>카테고리</th>${rep.columns.map(cn => `<th>${U.esc(cn)}</th>`).join('')}</tr>`;
    let lastGroup = null, n = 0, prev = null;
    rep.rows.forEach((r, ri) => {
      if (r.kind === 'cat' && r.group !== lastGroup) {
        lastGroup = r.group;
        n = 0;
        html += `<tr class="grp"><td colspan="${rep.columns.length + 1}"><span class="gname">${U.esc(r.group)}</span></td></tr>`;
      }
      const cls = r.kind === 'subtotal' ? 'sub' : r.kind === 'footer' ? (prev === 'footer' ? 'foot' : 'foot f1') : (n++ % 2 ? 'z' : '');
      prev = r.kind;
      const label = r.kind === 'cat' ? `${U.esc(r.code)} ${U.esc(Emo.deco(Money.ctx().emap, r.code, r.label))}` : U.esc(r.kind === 'subtotal' ? `${r.group} 소계` : r.label);
      html += `<tr class="${cls}"><td>${label}</td>${r.values.map((v, ci) => {
        const tap = r.kind === 'cat' && (budgetYm(rep, ci) || rep.periods[ci]);
        const k = [v < 0 ? 'neg' : '', v === 0 && r.kind !== 'cat' ? 'z0' : '', tap ? 'tap' : ''].filter(Boolean).join(' ');
        return `<td class="${k}" data-r="${ri}" data-c="${ci}">${v === null || v === undefined ? '' : UI.money(v, r.kind === 'cat')}</td>`;
      }).join('')}</tr>`;
    });
    return UI.tableBox(html + '</table>');
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
    Entry.listSheet(`${r.label} (${per[0]} ~ ${per[1]})`, L.search(lid, { start: per[0], end: per[1], codes: [r.code] }));
  }
  /** 이달 리포트로 바로 (가계부 화면의 예산 막대에서) */
  function openInsight(y, m) { s.kind = 'insight'; s.y = y; s.m = m; App.go('report', {}, true); }
  return { title: '통계', sticker: 'b30', sub: '한 달 성적표 두근두근', render, openInsight };
})();

// ════════ 그래프 ════════
Pages.graph = (() => {
  const s = { y: Number(U.today().slice(0, 4)), month: 0, sel: '' };
  // PC판 graph_page.PALETTE 와 같은 색 (첫 줄 = 수입은 파랑, 다음 지출 계정들은 색상이 겹치지 않게). 어두운 테마는 조금 밝게
  const PALETTE = ['#2F6FBE', '#D9534F', '#3A9A5B', '#E0912F', '#8A5CC2', '#1AA3A3', '#C2577F', '#7A7A2A', '#5B6B7A', '#B5651D', '#4A8F2A', '#A33A3A'];
  const lighten = h => '#' + [1, 3, 5].map(i => Math.round(parseInt(h.slice(i, i + 2), 16) + (255 - parseInt(h.slice(i, i + 2), 16)) * 0.3).toString(16).padStart(2, '0')).join('');
  /** 그래프 종류 — 열쇠는 PC판 graph_page.KINDS 와 같음. 고른 것은 이 휴대폰에 기억 (graph_kind) */
  const KINDS = [
    ['line', '꺾은선', '기간별 금액을 선으로 이어요'],
    ['bar', '막대', '기간마다 항목별 막대를 나란히 세워요'],
    ['stack', '누적 막대', '항목 막대를 쌓아요 — 높이가 그 기간 합계'],
    ['area', '영역', '꺾은선 아래를 칠해 크기를 비교해요'],
    ['cum', '누계', '처음부터 차례로 더해 간 금액 (누계)'],
    ['hbar', '가로 막대', '항목별 합계를 큰 것부터'],
    ['pie', '원', '항목별 합계의 비율 (합계가 0보다 큰 항목만)'],
    ['donut', '도넛', '항목별 합계의 비율, 가운데에 합계 (0보다 큰 항목만)'],
  ];
  const kind = () => { const k = App.pref('graph_kind'); return KINDS.some(([x]) => x === k) ? k : 'line'; };
  const col = i => (document.body.classList.contains('dark') ? lighten : (h => h))(PALETTE[i % PALETTE.length]);
  const cut = (t, n) => (t.length > n ? t.slice(0, n - 1) + '…' : t);
  const f1 = v => v.toFixed(1);
  const W = 360;

  function render(c) {
    const lid = App.lid;
    c.appendChild(UI.yearNav(s.y, y => { s.y = y; App.render(true); }));
    const gs = L.groups(lid), cats = L.categories(lid);
    const ctl = UI.el(`<div class="row" style="margin-bottom:8px">
      <select class="inp grow" data-k="month"><option value="0">월별 (1~12월)</option>${Array.from({ length: 12 }, (_, i) => `<option value="${i + 1}"${s.month === i + 1 ? ' selected' : ''}>${i + 1}월 일별</option>`).join('')}</select>
      <select class="inp grow" data-k="sel"><option value="">카테고리 전체</option>
        ${gs.map(g => `<option value="g:${U.esc(g.code)}"${s.sel === 'g:' + g.code ? ' selected' : ''}>(${U.esc(g.code)}) ${U.esc(g.name)} 세부 카테고리별</option>`).join('')}
        ${cats.map(x => `<option value="c:${U.esc(x.code)}"${s.sel === 'c:' + x.code ? ' selected' : ''}>${U.esc(x.code)} ${U.esc(x.name)}</option>`).join('')}</select></div>`);
    UI.$('[data-k=month]', ctl).value = String(s.month);
    UI.on(ctl, 'select', 'change', (e, x) => { s[x.dataset.k] = x.dataset.k === 'month' ? Number(x.value) : x.value; App.render(true); });
    c.appendChild(ctl);
    const kc = UI.el(`<div class="gkind">${KINDS.map(([k, label]) => `<button class="chip" data-g="${k}">${label}</button>`).join('')}</div>`);
    c.appendChild(kc);
    const o = { month: s.month || null, settleDay: Rep.settleDay() };
    if (s.sel.startsWith('g:')) o.group = s.sel.slice(2);
    if (s.sel.startsWith('c:')) o.code = s.sel.slice(2);
    const { labels, series } = Rep.graphSeries(lid, s.y, o);
    const shown = series.filter(([, v]) => v.some(x => x));
    if (!shown.length) { c.appendChild(UI.el(UI.empty('그릴 자료가 없어요', 'b26'))); return; }
    const box = UI.el('<div class="gbox"></div>');
    c.appendChild(box);
    const show = () => {
      const k = kind();
      UI.$$('button', kc).forEach(b => b.classList.toggle('on', b.dataset.g === k));
      box.innerHTML = draw(labels, shown, k);
    };
    UI.on(kc, 'button', 'click', (e, b) => { App.setPref('graph_kind', b.dataset.g === 'line' ? null : b.dataset.g); show(); });
    show();
    let html = `<table class="rep"><tr><th>항목</th>${labels.map(l => `<th>${U.esc(l)}</th>`).join('')}<th>합계</th></tr>`;
    html += shown.map(([n, v], i) => `<tr class="${i % 2 ? 'z' : ''}"><td>${U.esc(n)}</td>${v.map(x => `<td class="${x < 0 ? 'neg' : ''}">${UI.money(x, true)}</td>`).join('')}<td class="bold">${UI.money(U.sum(v))}</td></tr>`).join('');
    c.appendChild(UI.tableBox(html + '</table>'));
  }

  /** 그래프 + 범례 HTML */
  function draw(labels, series, k) {
    const note = `<div class="small muted gnote">${U.esc(KINDS.find(([x]) => x === k)[2])}</div>`;
    if (k === 'pie' || k === 'donut') {
      const r = pie(series, k === 'donut');
      if (!r) return note + `<div class="empty small">합계가 0보다 큰 항목이 없어 비율로 그릴 수 없어요</div>`;
      return note + r;
    }
    const svg = k === 'hbar' ? hbar(series) : xy(labels, series, k);
    return note + svg + `<div class="legend">${series.map(([n], i) => `<span><i style="background:${col(i)}"></i>${U.esc(n)}</span>`).join('')}</div>`;
  }

  /** 축 범위 (아래 min, 위 max, 눈금 간격 step) — PC판 graph_page._scale 과 같은 규칙.
      조금만 음수(환불 등)일 때 눈금 한 칸을 통째로 비우지 않도록 아래쪽은 값보다 조금만 더 내림 */
  function scale(vals) {
    let max = Math.max(0, ...vals), min = Math.min(0, ...vals);
    if (max === min) max = min + 1;
    const step = niceStep((max - min) / 4);
    let lo = Math.floor(min / step + 1e-9) * step;
    if (min < 0 && lo < min - step * 0.5) lo = min - (max - min) * 0.05;
    let hi = Math.ceil(max / step - 1e-9) * step;
    if (max > 0 && hi > max + step * 0.5) hi = max + (max - min) * 0.05;
    return { step, max: hi, min: lo };
  }
  /** 축 범위 안의 눈금 값들 (0 포함) */
  const ticks = sc => { const out = []; for (let k = Math.ceil(sc.min / sc.step - 1e-9); k * sc.step <= sc.max + sc.step * 1e-6; k++) out.push(k * sc.step); return out; };

  /** 꺾은선·누계·영역·막대·누적 막대 (가로축 = 달 또는 날) */
  function xy(labels, series, k) {
    const H = 220, pl = 46, pr = 16, pt = 10, pb = 24;      // 오른쪽 여백: 마지막 달 이름(12월)이 잘리지 않게
    const n = labels.length;
    const data = k === 'cum' ? series.map(([nm, v]) => { let a = 0; return [nm, v.map(x => (a += x))]; }) : series;
    const pos = labels.map((_, i) => U.sum(data.map(([, v]) => Math.max(0, v[i]))));
    const neg = labels.map((_, i) => U.sum(data.map(([, v]) => Math.min(0, v[i]))));
    const sc = scale(k === 'stack' ? pos.concat(neg) : data.flatMap(([, v]) => v));
    const bars = k === 'bar' || k === 'stack';
    const slot = (W - pl - pr) / Math.max(1, n);
    const x = bars ? (i => pl + slot * (i + 0.5)) : (i => pl + (n === 1 ? (W - pl - pr) / 2 : (i * (W - pl - pr)) / (n - 1)));
    const y = v => pt + ((sc.max - v) * (H - pt - pb)) / (sc.max - sc.min);
    let g = '';
    for (const v of ticks(sc)) {
      if (v) g += `<line class="gl" x1="${pl}" x2="${W - pr}" y1="${f1(y(v))}" y2="${f1(y(v))}" stroke="#DCEEEE" stroke-width="1"/>`;
      g += `<text class="gt" x="${pl - 4}" y="${f1(y(v) + 3)}" font-size="9" text-anchor="end" fill="#6F8080">${short(v)}</text>`;
    }
    const every = Math.ceil(n / 12);
    labels.forEach((l, i) => { if (i % every === 0) g += `<text class="gt" x="${f1(x(i))}" y="${H - 8}" font-size="9" text-anchor="middle" fill="#6F8080">${U.esc(l)}</text>`; });
    let body = '';
    if (k === 'bar') {
      const bw = (slot * 0.8) / data.length;
      data.forEach(([, v], si) => v.forEach((val, i) => {
        if (!val) return;
        const y0 = y(0), y1 = y(val);
        body += `<rect x="${f1(pl + slot * i + slot * 0.1 + bw * si)}" y="${f1(Math.min(y0, y1))}" width="${f1(Math.max(0.6, bw - 0.4))}" height="${f1(Math.max(0.6, Math.abs(y1 - y0)))}" fill="${col(si)}"/>`;
      }));
    } else if (k === 'stack') {
      const up = labels.map(() => 0), dn = labels.map(() => 0), bw = slot * 0.7;
      data.forEach(([, v], si) => v.forEach((val, i) => {
        if (!val) return;
        const base = val > 0 ? up[i] : dn[i], top = base + val;
        if (val > 0) up[i] = top; else dn[i] = top;
        const y0 = y(base), y1 = y(top);
        body += `<rect x="${f1(pl + slot * i + slot * 0.15)}" y="${f1(Math.min(y0, y1))}" width="${f1(Math.max(0.6, bw))}" height="${f1(Math.max(0.6, Math.abs(y1 - y0)))}" class="sg" fill="${col(si)}" stroke="#fff" stroke-width="0.4"/>`;
      }));
    } else {
      if (k === 'area') {
        data.forEach(([, v], si) => {
          const pts = v.map((val, i) => `${f1(x(i))},${f1(y(val))}`).join(' ');
          body += `<polygon points="${f1(x(0))},${f1(y(0))} ${pts} ${f1(x(n - 1))},${f1(y(0))}" fill="${col(si)}" fill-opacity="0.18"/>`;
        });
      }
      data.forEach(([, v], si) => {
        body += `<polyline fill="none" stroke="${col(si)}" stroke-width="2" points="${v.map((val, i) => `${f1(x(i))},${f1(y(val))}`).join(' ')}"/>`;
        if (n <= 31) body += v.map((val, i) => `<circle cx="${f1(x(i))}" cy="${f1(y(val))}" r="2.2" fill="${col(si)}"/>`).join('');
      });
    }
    g += body + `<line class="gl0" x1="${pl}" x2="${W - pr}" y1="${f1(y(0))}" y2="${f1(y(0))}" stroke="#888" stroke-width="1"/>`;
    return `<svg class="chart" data-kind="${k}" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">${g}</svg>`;
  }

  /** 가로 막대: 항목별 합계, 큰 것부터 */
  function hbar(series) {
    const items = series.map(([nm, v], i) => [nm, U.sum(v), col(i)]).sort((a, b) => b[1] - a[1]);
    const rowH = 24, pt = 6, pb = 18, nameW = 100, pr = 50, H = pt + items.length * rowH + pb;
    const sc = scale(items.map(it => it[1]));
    const x = v => nameW + ((v - sc.min) * (W - nameW - pr)) / (sc.max - sc.min);
    let g = '';
    for (const v of ticks(sc)) {
      g += `<line class="${v ? 'gl' : 'gl0'}" x1="${f1(x(v))}" x2="${f1(x(v))}" y1="${pt}" y2="${H - pb}" stroke="${v ? '#DCEEEE' : '#888'}" stroke-width="1"/>`;
      g += `<text class="gt" x="${f1(x(v))}" y="${H - 5}" font-size="9" text-anchor="middle" fill="#6F8080">${short(v)}</text>`;
    }
    items.forEach(([nm, t, c], i) => {
      const yy = pt + i * rowH, a = x(Math.min(0, t)), b = x(Math.max(0, t));
      g += `<text class="gv" x="${nameW - 5}" y="${f1(yy + rowH / 2 + 3.5)}" font-size="10" text-anchor="end" fill="#333">${U.esc(cut(nm, 9))}</text>`;
      g += `<rect x="${f1(a)}" y="${yy + 5}" width="${f1(Math.max(0.6, b - a))}" height="${rowH - 10}" rx="2" fill="${c}"/>`;
      g += `<text class="gt" x="${f1(b + 3)}" y="${f1(yy + rowH / 2 + 3)}" font-size="9" fill="#6F8080">${short(t)}</text>`;
    });
    return `<svg class="chart" data-kind="hbar" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">${g}</svg>`;
  }

  /** 원·도넛: 합계가 0보다 큰 항목의 비율. 그릴 것이 없으면 null */
  function pie(series, hole) {
    const all = series.map(([nm, v], i) => [nm, U.sum(v), col(i)]);
    const items = all.filter(it => it[1] > 0);
    if (!items.length) return null;
    const tot = U.sum(items.map(it => it[1]));
    const H = 220, cx = W / 2, cy = H / 2, r = 96, r0 = hole ? 54 : 0;
    const pt = (a, rr) => `${f1(cx + rr * Math.cos(a))},${f1(cy + rr * Math.sin(a))}`;
    let a = -Math.PI / 2, g = '', lab = '';
    for (const [, t, c] of items) {
      const da = (t / tot) * 2 * Math.PI, b = a + da;
      if (items.length === 1) {
        g += `<path d="M${cx - r},${cy}a${r},${r} 0 1,0 ${2 * r},0a${r},${r} 0 1,0 ${-2 * r},0Z${r0 ? `M${cx - r0},${cy}a${r0},${r0} 0 1,0 ${2 * r0},0a${r0},${r0} 0 1,0 ${-2 * r0},0Z` : ''}" fill="${c}" fill-rule="evenodd"/>`;
      } else {
        const big = da > Math.PI ? 1 : 0;
        g += r0
          ? `<path d="M${pt(a, r)}A${r},${r} 0 ${big},1 ${pt(b, r)}L${pt(b, r0)}A${r0},${r0} 0 ${big},0 ${pt(a, r0)}Z" class="sg" fill="${c}" stroke="#fff" stroke-width="1"/>`
          : `<path d="M${cx},${cy}L${pt(a, r)}A${r},${r} 0 ${big},1 ${pt(b, r)}Z" class="sg" fill="${c}" stroke="#fff" stroke-width="1"/>`;
      }
      if (t / tot >= 0.06) {
        const m = (a + b) / 2, rr = r0 ? (r + r0) / 2 : r * 0.62;
        lab += `<text x="${f1(cx + rr * Math.cos(m))}" y="${f1(cy + rr * Math.sin(m) + 3.5)}" font-size="10" font-weight="700" text-anchor="middle" fill="#fff" stroke="rgba(0,0,0,.35)" stroke-width="2" paint-order="stroke">${Math.round((t / tot) * 100)}%</text>`;
      }
      a = b;
    }
    if (r0) {
      lab += `<text class="gt" x="${cx}" y="${cy - 6}" font-size="10" text-anchor="middle" fill="#6F8080">합계</text>`;
      lab += `<text class="gv" x="${cx}" y="${cy + 12}" font-size="15" font-weight="700" text-anchor="middle" fill="#333">${short(tot)}</text>`;
    }
    const skipped = all.length - items.length;
    const pct = t => `${((t / tot) * 100).toFixed(1)}%`;
    return `<svg class="chart" data-kind="${hole ? 'donut' : 'pie'}" viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">${g}${lab}</svg>` +
      `<div class="legend">${items.map(([nm, t, c]) => `<span><i style="background:${c}"></i>${U.esc(nm)} <b>${pct(t)}</b></span>`).join('')}</div>` +
      (skipped ? `<div class="small muted">합계가 0 이하인 ${skipped}개 항목은 비율에서 뺐어요</div>` : '');
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
    return String(Math.round(v));
  }
  return { title: '그래프', sticker: 'b26', sub: '쑥쑥 크는 그래프 (^-^)', render, tab: 'more', KINDS };
})();
