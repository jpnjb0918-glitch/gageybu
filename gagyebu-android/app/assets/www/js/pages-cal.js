/* 달력(일정·기념일·하루 내역)·기념일 관리 */
'use strict';
Pages.calendar = (() => {
  const t = U.parts(U.today());
  const s = { y: t[0], m: t[1], sel: null };
  const COLORS = [['', '기본'], ['#B8EBE4', '민트'], ['#FFE3EC', '분홍'], ['#FFE066', '노랑'], ['#CFE3FF', '하늘'], ['#E2D6FF', '보라'], ['#D9F2C2', '연두']];

  /** 달력 칸이 좁아서 10만 원 이상은 '만' 단위로 (예: 3,200,000 → 320만) */
  const short = v => (Math.abs(v) >= 100000 ? `${Math.round(v / 10000).toLocaleString('en-US')}만` : UI.money(v));

  function render(c, p, tools) {
    const lid = App.lid;
    const ab = UI.el('<button class="btn sm">기념일</button>');
    ab.onclick = () => App.go('anniv', {}, true);
    tools.appendChild(ab);
    c.appendChild(UI.monthNav(s.y, s.m, (y, m) => { s.y = y; s.m = m; App.render(); }));
    const grid = Cal.monthGrid(s.y, s.m);
    const g0 = grid[0][0], g1 = grid[5][6];
    const sch = Cal.schedules(g0, g1);
    const ann = Cal.anniversariesBetween(g0, g1);
    const sums = {};
    for (const r of DB.q('SELECT date, SUM(income) AS i, SUM(expense) AS e FROM entry WHERE ledger_id=? AND date BETWEEN ? AND ? GROUP BY date', [lid, g0, g1])) sums[r.date] = r;
    const today = U.today();
    let html = '<table class="cal"><tr>' + '일월화수목금토'.split('').map(d => `<th>${d}</th>`).join('') + '</tr>';
    for (const week of grid) {
      html += '<tr>';
      week.forEach((d, i) => {
        const other = Number(d.slice(5, 7)) !== s.m;
        const an = ann[d] || [];
        const hol = an.some(a => a[1]);
        const lu = Lunar.solarToLunar(d);
        const showLu = lu && (lu.d === 1 || lu.d === 15);
        const cls = [other ? 'other' : '', i === 0 ? 'sun' : '', i === 6 ? 'sat' : '', hol ? 'hol' : '', d === today ? 'today' : '', d === s.sel ? 'sel' : ''].join(' ');
        const sm = sums[d];
        html += `<td class="${cls}" data-d="${d}"><span class="dn">${Number(d.slice(8))}</span>${showLu ? `<span class="lu">${lu.m}.${lu.d}</span>` : ''}
          ${an.slice(0, 1).map(a => `<div class="an">${U.esc(a[0])}</div>`).join('')}
          ${(sch[d] || []).slice(0, 2).map(x => `<div class="sc" style="${x.bg ? `background:${U.esc(x.bg)}` : ''}">${U.esc(x.text)}</div>`).join('')}
          ${sm && sm.i ? `<div class="mi">+${short(sm.i)}</div>` : ''}${sm && sm.e ? `<div class="mo">-${short(sm.e)}</div>` : ''}</td>`;
      });
      html += '</tr>';
    }
    html += '</table>';
    c.appendChild(UI.el(`<div>${html}</div>`));
    const [mi, me] = L.totals(lid, U.iso(s.y, s.m, 1), U.iso(s.y, s.m, U.monthEnd(s.y, s.m)));
    c.appendChild(UI.el(`<div class="small muted" style="margin-top:6px">이달 수입 <span class="in">${UI.money(mi)}</span> · 지출 <span class="out">${UI.money(me)}</span> — 날짜를 누르면 그날 일정·내역을 봅니다</div>`));
    UI.on(c, 'td[data-d]', 'click', (e, td) => { s.sel = td.dataset.d; daySheet(td.dataset.d); UI.$$('td.sel', c).forEach(x => x.classList.remove('sel')); td.classList.add('sel'); });
    App.fab(() => scheduleSheet(null, s.sel || today), '일정 추가');
  }

  function daySheet(d) {
    const lid = App.lid;
    const lu = Lunar.label(d);
    const an = Cal.anniversariesBetween(d, d)[d] || [];
    const sch = Cal.schedules(d, d)[d] || [];
    const rows = DB.q('SELECT * FROM entry WHERE ledger_id=? AND date=? ORDER BY id', [lid, d]);
    const cmap = L.categoryMap(lid);
    const inc = U.sum(rows.map(r => r.income)), exp = U.sum(rows.map(r => r.expense));
    const body = UI.el(`<div>
      <div class="muted small">${U.esc(lu)}</div>
      ${an.length ? `<div style="margin:6px 0">${an.map(a => `<span class="chip" style="${a[1] ? 'color:var(--out)' : ''}">${U.esc(a[0])}</span>`).join(' ')}</div>` : ''}
      <div class="section-t">일정</div>
      ${sch.length ? `<ul class="list">${sch.map(x => `<li class="tap" data-s="${x.id}"><span class="chip" style="${x.bg ? `background:${U.esc(x.bg)}` : ''}">&nbsp;</span><div class="grow">${U.esc(x.text)}${x.remind_days ? ` <span class="tiny muted">(${x.remind_days}일 전 알림)</span>` : ''}${x.group_id ? ' <span class="tiny muted">반복</span>' : ''}</div></li>`).join('')}</ul>` : '<div class="muted small">일정이 없어요</div>'}
      <div class="section-t">내역 ${rows.length ? `<span class="small"><span class="in">+${UI.money(inc)}</span> <span class="out">-${UI.money(exp)}</span></span>` : ''}</div>
      ${rows.length ? `<ul class="list">${rows.map(r => Entry.rowHtml(r, null, false, cmap)).join('')}</ul>` : '<div class="muted small">내역이 없어요</div>'}
    </div>`);
    const sh = UI.sheet({ title: U.dateLabel(d), body, full: true, buttons: [
      { label: '＋ 일정', onClick: () => { scheduleSheet(null, d); } },
      { label: '＋ 내역', cls: 'pri', onClick: () => { Entry.open({ date: d }); } }] });
    UI.on(sh.body, 'li[data-s]', 'click', (e, li) => { sh.close(); scheduleSheet(sch.find(x => x.id === Number(li.dataset.s)), d); });
    UI.on(sh.body, 'li[data-id]', 'click', (e, li) => { sh.close(); Entry.open({ entry: rows.find(r => r.id === Number(li.dataset.id)) }); });
  }

  function scheduleSheet(x, d) {
    const colorOpts = COLORS;
    if (x) {
      const fields = [{ k: 'text', label: '내용', type: 'text', req: true },
        { k: 'remind_days', label: '미리 알려주기 (며칠 전, 0=안 함)', type: 'int' },
        { k: 'bg', label: '색', type: 'select', options: colorOpts }];
      UI.formSheet({ title: `일정 수정 (${x.date})`, fields, values: { text: x.text, remind_days: x.remind_days, bg: x.bg || '' },
        onSave: v => { Cal.updateSchedule(x.id, v.text, v.remind_days || 0, v.bg || null, x.fg); App.dataChanged(); },
        onDelete: close => {
          const ask = x.group_id ? UI.sheet({ title: '반복 일정 삭제', body: '<div>이 날짜 것만 지울까요, 반복으로 만든 같은 묶음을 모두 지울까요?</div>', buttons: [
            { label: '이 날짜만', onClick: () => { Cal.deleteSchedule(x.id); close(); App.dataChanged(); } },
            { label: '묶음 전체', cls: 'danger', onClick: () => { const n = Cal.deleteScheduleGroup(x.group_id); close(); App.dataChanged(); UI.toast(`${n}개를 지웠습니다`); } }] }) : null;
          if (!ask) UI.confirm('이 일정을 삭제할까요?', '삭제', true).then(ok => { if (ok) { Cal.deleteSchedule(x.id); close(); App.dataChanged(); } });
        } });
      return;
    }
    const fields = [{ k: 'date', label: '날짜', type: 'date', req: true }, { k: 'text', label: '내용', type: 'text', req: true },
      { k: 'remind_days', label: '미리 알려주기 (며칠 전, 0=안 함)', type: 'int' },
      { k: 'bg', label: '색', type: 'select', options: colorOpts },
      { k: 'rtype', label: '반복', type: 'select', options: [['none', '반복 안 함'], ['every', '매 N 일/주/월/년'], ['weekdays', '요일 묶음'], ['nth', '매달 N번째 X요일']] },
      { k: 'n', label: '간격 N', type: 'int' },
      { k: 'unit', label: '단위', type: 'select', options: [['일', '일'], ['주', '주'], ['월', '월'], ['년', '년']] },
      { k: 'set', label: '요일 묶음', type: 'select', options: Object.keys(Cal.WEEKDAY_SETS).map(k => [k, k]) },
      { k: 'nth', label: '몇 번째', type: 'select', options: Cal.ORDINALS.map((o, i) => [i, o]) },
      { k: 'weekday', label: '요일', type: 'select', options: Cal.WEEKDAY_NAMES.map((o, i) => [i, o]) },
      { k: 'until', label: '반복 끝나는 날', type: 'date' }];
    const [y, m] = U.parts(d);
    const sh = UI.formSheet({ title: '일정 추가', fields, full: true,
      values: { date: d, remind_days: 0, rtype: 'none', n: 1, unit: '주', nth: 0, weekday: U.weekday(d), until: U.iso(y + 1, m, Math.min(Number(d.slice(8)), U.monthEnd(y + 1, m))) },
      afterOpen: sb => {
        const show = () => {
          const t = UI.$('[data-k=rtype]', sb).value;
          const vis = { n: t === 'every' || t === 'nth', unit: t === 'every', set: t === 'weekdays', nth: t === 'nth', weekday: t === 'nth', until: t !== 'none' };
          for (const k of Object.keys(vis)) UI.$(`[data-k=${k}]`, sb).closest('.f').classList.toggle('hidden', !vis[k]);
        };
        UI.$('[data-k=rtype]', sb).onchange = show;
        show();
      },
      onSave: v => {
        const rule = v.rtype === 'every' ? { type: 'every', n: v.n || 1, unit: v.unit } : v.rtype === 'weekdays' ? { type: 'weekdays', set: v.set }
          : v.rtype === 'nth' ? { type: 'nth', nth: Number(v.nth), weekday: Number(v.weekday), n: v.n || 1 } : { type: 'none' };
        if (rule.type !== 'none' && (!v.until || v.until < v.date)) throw new Error('반복 끝나는 날을 시작 날짜 이후로 정하세요.');
        const n = Cal.addSchedule(v.date, v.text, v.remind_days || 0, v.bg || null, null, rule, v.until);
        App.dataChanged();
        UI.toast(n > 1 ? `일정 ${n}개를 만들었습니다` : '일정을 저장했습니다');
      } });
    return sh;
  }
  return { title: '달력', sticker: 'b11', sub: '기념일 잊지 말기 ☆', render };
})();

// ════════ 기념일 관리 ════════
Pages.anniv = (() => {
  function render(c) {
    const list = Cal.anniversaries();
    c.appendChild(UI.el('<div class="small muted" style="margin-bottom:6px">해마다 돌아오는 날(생일·결혼기념일 등). 음력으로 정하면 해마다 양력 날짜를 알아서 찾아 줍니다.</div>'));
    c.appendChild(UI.el(`<ul class="list">${list.map(a => `<li class="tap" data-id="${a.id}"><div class="grow"><div class="main-t">${U.esc(a.title)}${a.holiday ? ' <span class="tiny out">휴일</span>' : ''}</div>
      <div class="sub">${a.lunar ? '음력' : '양력'} ${a.month}월 ${a.day}일${a.year ? ` (${a.year}년만)` : ' · 매년'}</div></div></li>`).join('')}</ul>`));
    UI.on(c, 'li[data-id]', 'click', (e, li) => edit(list.find(a => a.id === Number(li.dataset.id))));
    App.fab(() => edit(null), '기념일 추가');
  }
  function edit(a) {
    const fields = [{ k: 'title', label: '이름', type: 'text', req: true }, { k: 'month', label: '월', type: 'int', req: true },
      { k: 'day', label: '일', type: 'int', req: true }, { k: 'lunar', label: '음력 날짜', type: 'check' },
      { k: 'holiday', label: '휴일 (달력에 빨간 날)', type: 'check' }, { k: 'year', label: '그 해만 (비우면 매년)', type: 'int' }];
    UI.formSheet({ title: a ? '기념일 수정' : '기념일 추가', fields, values: a || { lunar: false, holiday: false },
      extra: a ? '<div class="row" style="margin-top:6px"><button class="btn sm" data-up>위로</button><button class="btn sm" data-dn>아래로</button></div>' : '',
      afterOpen: sb => {
        if (!a) return;
        UI.$('[data-up]', sb).onclick = () => { A.move('anniversary', a.id, -1); App.dataChanged(); };
        UI.$('[data-dn]', sb).onclick = () => { A.move('anniversary', a.id, 1); App.dataChanged(); };
      },
      onSave: v => {
        if (v.month < 1 || v.month > 12 || v.day < 1 || v.day > 31) throw new Error('날짜를 확인하세요.');
        Cal.saveAnniversary(v, a ? a.id : null);
        App.dataChanged();
      },
      onDelete: a ? close => UI.confirm(`'${a.title}'을(를) 삭제할까요?`, '삭제', true).then(ok => { if (ok) { Cal.deleteAnniversary(a.id); close(); App.dataChanged(); } }) : null });
  }
  return { title: '기념일 관리', sticker: 'b11', sub: '해마다 돌아오는 날', render, tab: 'calendar' };
})();
