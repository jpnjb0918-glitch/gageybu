/* 더보기·주소록·일기장·메모장 */
'use strict';
Pages.more = {
  title: '더보기', sticker: 'a10', sub: '이것저것 다 있어요',
  render(c, p, tools) {
    const ord = UI.el('<button class="btn sm">메뉴 순서</button>');
    ord.onclick = () => App.navReorderSheet();
    tools.appendChild(ord);
    const tiles = App.moreKeys();
    c.appendChild(UI.el(`<div class="tiles">${tiles.map(k => { const [l, st] = App.navLabel(k); return `<button class="tile" data-p="${k}"><img src="${UI.sticker(st)}" alt="">${l}</button>`; }).join('')}</div>`));
    UI.on(c, '[data-p]', 'click', (e, b) => App.go(b.dataset.p, {}, true));
  },
};

// ════════ 주소록 ════════
Pages.contacts = (() => {
  const FIELDS = [['name', '성명'], ['mobile', '휴대폰'], ['tel1', '전화1'], ['tel2', '전화2'], ['fax', '팩스번호'], ['email', '전자우편'],
    ['homepage', '홈페이지'], ['address', '주소'], ['zipcode', '우편번호'], ['memo', '메모'], ['grp', '그룹']];
  const s = { q: '', grp: '' };
  const labels = () => { const cu = DB.getJson('address_labels', {}) || {}; return FIELDS.map(([k, v]) => [k, cu[k] || v]); };
  const typeOf = k => (k === 'memo' ? 'textarea' : ['mobile', 'tel1', 'tel2', 'fax'].includes(k) ? 'tel' : k === 'email' ? 'email' : 'text');

  function render(c, p, tools) {
    const ren = UI.el('<button class="btn sm">항목 이름</button>');
    ren.onclick = renameLabels;
    tools.appendChild(ren);
    const ordb = UI.el('<button class="btn sm">순서</button>');
    tools.appendChild(ordb);
    const lab = Object.fromEntries(labels());
    const f = UI.el(`<div class="row" style="margin-bottom:8px"><input class="inp grow" type="text" placeholder="찾을 글자 (이름·전화·메모…)" value="${U.esc(s.q)}"></div>`);
    const inp = UI.$('input', f);
    inp.addEventListener('input', () => { s.q = inp.value; draw(); });
    c.appendChild(f);
    const groups = DB.q("SELECT DISTINCT grp FROM contact WHERE grp<>'' ORDER BY grp").map(r => r.grp);
    if (groups.length) {
      const gb = UI.el(`<div class="row wrap" style="margin-bottom:6px"><span class="chip ${s.grp ? '' : 'on'}" data-g="">전체</span>${groups.map(g => `<span class="chip ${s.grp === g ? 'on' : ''}" data-g="${U.esc(g)}">${U.esc(g)}</span>`).join('')}</div>`);
      UI.on(gb, '[data-g]', 'click', (e, x) => { s.grp = x.dataset.g; App.render(true); });
      c.appendChild(gb);
    }
    const box = UI.el('<div></div>');
    c.appendChild(box);
    function draw() {
      let where = '', args = [];
      const conds = [];
      if (s.q.trim()) { conds.push('(' + FIELDS.map(([k]) => `${k} LIKE ?`).join(' OR ') + ')'); args = args.concat(FIELDS.map(() => `%${s.q.trim()}%`)); }
      if (s.grp) { conds.push('grp=?'); args.push(s.grp); }
      where = conds.join(' AND ');
      const rows = Ord.applyListOrder('contact', Cal.simpleList('contact', 'name', where, args));
      box.innerHTML = rows.length ? `<div class="small muted">${rows.length}명</div><ul class="list">${rows.map(r => `<li class="tap" data-id="${r.id}"><div class="grow"><div class="main-t ellipsis">${U.esc(r.name)}${r.grp ? ` <span class="tiny muted">${U.esc(r.grp)}</span>` : ''}</div>
        <div class="sub ellipsis">${U.esc(r.mobile || r.tel1 || r.email || '')}</div></div></li>`).join('')}</ul>` : UI.empty(s.q ? '찾는 사람이 없어요' : `아직 등록한 ${lab.name ? '연락처' : ''}가 없어요`, 'a13');
      UI.on(box, 'li[data-id]', 'click', (e, li) => view(rows.find(r => r.id === Number(li.dataset.id))));
      ordb.onclick = () => {
        if (rows.length < 2) { UI.toast('순서를 바꿀 연락처가 2명 이상이어야 합니다'); return; }
        UI.reorder({ title: '주소록 순서', hint: (s.q || s.grp ? '지금 보이는 사람들끼리의 순서입니다.\n' : '') + '새로 추가한 사람은 맨 아래에 붙습니다. PC판에서도 같은 순서로 보입니다.',
          items: rows.map(r => ({ key: r.id, label: r.name, sub: [r.grp, r.mobile || r.tel1].filter(Boolean).join(' · ') })),
          onSave: keys => { Ord.mergeListOrder('contact', rows.map(r => r.id), keys.map(Number)); App.dataChanged(); },
          onReset: () => { Ord.mergeListOrder('contact', rows.map(r => r.id), null); App.dataChanged(); }, resetLabel: '이름순으로' });
      };
    }
    draw();
    App.fab(() => edit(null), '연락처 추가');
  }
  function view(r) {
    const lab = labels();
    const tel = v => v ? `<a href="tel:${U.esc(v.replace(/[^0-9+]/g, ''))}">${U.esc(v)}</a>` : '';
    const body = `<div>${lab.filter(([k]) => r[k] && k !== 'name').map(([k, l]) => {
      let v = U.esc(r[k]);
      if (['mobile', 'tel1', 'tel2'].includes(k)) v = tel(r[k]);
      else if (k === 'email') v = `<a href="mailto:${U.esc(r[k])}">${U.esc(r[k])}</a>`;
      else if (k === 'homepage') v = `<a href="${/^https?:/i.test(r[k]) ? '' : 'http://'}${U.esc(r[k])}">${U.esc(r[k])}</a>`;
      else if (k === 'memo') v = `<span style="white-space:pre-wrap">${v}</span>`;
      return `<div class="kv" style="padding:6px 0;border-bottom:1px dashed var(--line)"><span class="muted">${U.esc(l)}</span><span class="right">${v}</span></div>`;
    }).join('')}</div>`;
    const buttons = [];
    if (r.mobile) buttons.push({ label: '문자', onClick: () => { App.native.openExternal('sms:' + r.mobile.replace(/[^0-9+]/g, '')); return false; } });
    buttons.push({ label: '수정', cls: 'pri', onClick: () => { setTimeout(() => edit(r), 0); } });
    const sh = UI.sheet({ title: r.name, body, buttons });
    UI.on(sh.body, 'a', 'click', (e, a) => { e.preventDefault(); App.native.openExternal(a.getAttribute('href')); });
  }
  function edit(r) {
    const fields = labels().map(([k, l]) => ({ k, label: l, type: typeOf(k), req: k === 'name' }));
    UI.formSheet({ title: r ? '연락처 수정' : '연락처 추가', fields, values: r || {}, full: true,
      onSave: v => { Cal.simpleSave('contact', v, r ? r.id : null); App.dataChanged(); },
      onDelete: r ? close => UI.confirm(`'${r.name}'을(를) 삭제할까요?`, '삭제', true).then(ok => { if (ok) { Cal.simpleDelete('contact', r.id); close(); App.dataChanged(); } }) : null });
  }
  function renameLabels() {
    const cur = labels();
    UI.formSheet({ title: '항목 이름 바꾸기', fields: cur.map(([k, l]) => ({ k, label: FIELDS.find(f => f[0] === k)[1], type: 'text' })),
      values: Object.fromEntries(cur), full: true,
      extra: '<div class="small muted">비우면 원래 이름으로 돌아갑니다. (PC판과 같이 저장됩니다)</div>',
      onSave: v => {
        const custom = {};
        for (const [k, def] of FIELDS) if (v[k] && v[k] !== def) custom[k] = v[k];
        DB.setJson('address_labels', custom);
        App.dataChanged();
      } });
  }
  return { title: '주소록', sticker: 'a13', sub: '우리 일촌 연락처', render, tab: 'more' };
})();

// ════════ 일기장 ════════
Pages.diary = (() => {
  const t = U.parts(U.today());
  const s = { y: t[0], m: t[1], q: '' };
  function render(c, p, tools) {
    c.appendChild(UI.monthNav(s.y, s.m, (y, m) => { s.y = y; s.m = m; s.q = ''; App.render(); }));
    const f = UI.el(`<div class="row" style="margin-bottom:8px"><input class="inp grow" type="text" placeholder="제목·내용 찾기 (전체 기간)" value="${U.esc(s.q)}"></div>`);
    const inp = UI.$('input', f);
    inp.addEventListener('change', () => { s.q = inp.value.trim(); App.render(); });
    c.appendChild(f);
    const rows = Ord.applyListOrder('diary', s.q ? Cal.simpleList('diary', 'date DESC, id DESC', 'title LIKE ? OR content LIKE ?', [`%${s.q}%`, `%${s.q}%`])
      : Cal.simpleList('diary', 'date DESC, id DESC', 'substr(date,1,7)=?', [U.ym(s.y, s.m)]));
    if (!rows.length) c.appendChild(UI.el(UI.empty(s.q ? '찾는 일기가 없어요' : '이 달에 쓴 일기가 없어요', 'b33')));
    else {
      c.appendChild(UI.el(`<ul class="list">${rows.map(r => `<li class="tap" data-id="${r.id}"><div class="grow"><div class="main-t ellipsis">${U.esc(r.title || '(제목 없음)')}</div>
        <div class="sub ellipsis">${U.dateLabel(r.date)} · ${U.esc(U.WEATHER[r.weather] || '')} · ${U.esc((r.content || '').split('\n')[0].slice(0, 40))}</div></div></li>`).join('')}</ul>`));
      UI.on(c, 'li[data-id]', 'click', (e, li) => edit(rows.find(r => r.id === Number(li.dataset.id))));
    }
    if (rows.length > 1) {
      const ordb = UI.el('<button class="btn sm">순서</button>');
      ordb.onclick = () => UI.reorder({ title: '일기 순서', hint: `${s.q ? '찾은 일기' : `${s.m}월 일기`}끼리의 순서입니다. 새로 쓴 일기는 맨 아래에 붙습니다.`,
        items: rows.map(r => ({ key: r.id, label: r.title || '(제목 없음)', sub: U.dateLabel(r.date) })),
        onSave: keys => { Ord.mergeListOrder('diary', rows.map(r => r.id), keys.map(Number)); App.dataChanged(); },
        onReset: () => { Ord.mergeListOrder('diary', rows.map(r => r.id), null); App.dataChanged(); }, resetLabel: '날짜순으로' });
      tools.appendChild(ordb);
    }
    App.fab(() => edit(null), '일기 쓰기');
  }
  function edit(r) {
    const fields = [{ k: 'date', label: '날짜', type: 'date', req: true }, { k: 'weather', label: '날씨', type: 'select', options: U.WEATHER.map((w, i) => [String(i), w]) },
      { k: 'title', label: '제목', type: 'text' }, { k: 'content', label: '내용', type: 'textarea' }];
    const vals = r ? Object.assign({}, r, { weather: String(r.weather) }) : { date: U.today(), weather: '0' };
    UI.formSheet({ title: r ? '일기 수정' : '일기 쓰기', fields, values: vals, full: true,
      afterOpen: sb => { const ta = UI.$('textarea', sb); ta.style.minHeight = '42vh'; },
      onSave: v => { v.weather = Number(v.weather); Cal.simpleSave('diary', v, r ? r.id : null); App.dataChanged(); },
      onDelete: r ? close => UI.confirm('이 일기를 삭제할까요?', '삭제', true).then(ok => { if (ok) { Cal.simpleDelete('diary', r.id); close(); App.dataChanged(); } }) : null });
  }
  return { title: '일기장', sticker: 'b33', sub: '오늘 하루 끄적끄적', render, tab: 'more' };
})();

// ════════ 메모장 ════════
Pages.memo = (() => {
  const s = { q: '', order: 0 };
  const ORDERS = [['sort, id', '내가 정한 순서'], ['title, id', '제목순'], ['created DESC, id DESC', '최근 것 위로']];
  function render(c, p, tools) {
    const ordb = UI.el('<button class="btn sm">순서</button>');
    ordb.onclick = () => {
      const all = Cal.simpleList('memo', 'sort, id');
      if (all.length < 2) { UI.toast('메모가 2개 이상이어야 합니다'); return; }
      UI.reorder({ title: '메모 순서', hint: "'내가 정한 순서'로 볼 때의 순서입니다. 새 메모는 맨 아래에 붙습니다.",
        items: all.map(r => ({ key: r.id, label: r.title || (r.content || '').split('\n')[0].slice(0, 30) || '(빈 메모)', sub: r.created || '' })),
        onSave: keys => { Ord.setMemoOrder(keys.map(Number)); s.order = 0; App.dataChanged(); } });
    };
    tools.appendChild(ordb);
    const f = UI.el(`<div class="row" style="margin-bottom:8px"><input class="inp grow" type="text" placeholder="찾을 글자" value="${U.esc(s.q)}">
      <select class="inp" style="width:auto">${ORDERS.map(([, l], i) => `<option value="${i}"${i === s.order ? ' selected' : ''}>${l}</option>`).join('')}</select></div>`);
    UI.$('input', f).addEventListener('change', e => { s.q = e.target.value.trim(); App.render(); });
    UI.$('select', f).onchange = e => { s.order = Number(e.target.value); App.render(); };
    c.appendChild(f);
    const rows = Cal.simpleList('memo', ORDERS[s.order][0], s.q ? 'title LIKE ? OR content LIKE ?' : '', s.q ? [`%${s.q}%`, `%${s.q}%`] : []);
    if (!rows.length) c.appendChild(UI.el(UI.empty('메모가 없어요', 'a19')));
    else {
      c.appendChild(UI.el(`<ul class="list">${rows.map(r => `<li class="tap" data-id="${r.id}"><div class="grow"><div class="main-t ellipsis">${U.esc(r.title || (r.content || '').split('\n')[0].slice(0, 30) || '(빈 메모)')}</div>
        <div class="sub ellipsis">${U.esc(r.created || '')} ${U.esc((r.content || '').replace(/\n/g, ' ').slice(0, 50))}</div></div></li>`).join('')}</ul>`));
      UI.on(c, 'li[data-id]', 'click', (e, li) => edit(rows.find(r => r.id === Number(li.dataset.id))));
    }
    App.fab(() => edit(null), '메모 추가');
  }
  function edit(r) {
    const fields = [{ k: 'title', label: '제목', type: 'text' }, { k: 'content', label: '내용', type: 'textarea' }];
    UI.formSheet({ title: r ? '메모 수정' : '새 메모', fields, values: r || {}, full: true,
      extra: r ? '<div class="row" style="margin-top:6px"><button class="btn sm" data-up>위로</button><button class="btn sm" data-dn>아래로</button><span class="small muted">(내가 정한 순서)</span></div>' : '',
      afterOpen: sb => {
        UI.$('textarea', sb).style.minHeight = '45vh';
        if (!r) return;
        UI.$('[data-up]', sb).onclick = () => { A.move('memo', r.id, -1); App.dataChanged(); UI.toast('순서를 바꿨습니다'); };
        UI.$('[data-dn]', sb).onclick = () => { A.move('memo', r.id, 1); App.dataChanged(); UI.toast('순서를 바꿨습니다'); };
      },
      onSave: v => {
        if (!v.title && !v.content) throw new Error('제목이나 내용을 입력하세요.');
        if (!r) {
          const now = new Date();
          v.created = `${U.today()} ${U.pad(now.getHours())}:${U.pad(now.getMinutes())}`;
          v.sort = DB.val('SELECT COALESCE(MAX(sort),0)+1 AS v FROM memo');
        }
        Cal.simpleSave('memo', v, r ? r.id : null);
        App.dataChanged();
      },
      onDelete: r ? close => UI.confirm('이 메모를 삭제할까요?', '삭제', true).then(ok => { if (ok) { Cal.simpleDelete('memo', r.id); close(); App.dataChanged(); } }) : null });
  }
  return { title: '메모장', sticker: 'a19', sub: '잊기 전에 메모!', render, tab: 'more' };
})();

// ════════ 도움말 ════════
Pages.help = {
  title: '도움말', sticker: 'b02', sub: '처음이라면 읽어 보세요', tab: 'more',
  render(c) {
    c.appendChild(UI.el(`<div class="small" style="line-height:1.7">
      <div class="section-t">PC와 자료 주고받기</div>
      <b>PC → 휴대폰</b><br>① PC판 설정 → 암호 · 백업 → <b>지금 백업하기</b>를 누르면 백업 폴더 안 backup(날짜) 폴더에 gagyebu.sqlite3 파일이 생깁니다.<br>② 그 파일을 휴대폰으로 옮깁니다 (USB, 카카오톡 나에게 보내기, 구글 드라이브 등).<br>③ 이 앱 설정 → 백업·복원 → <b>파일에서 가져오기</b>로 그 파일을 고릅니다.<br>
      <b>휴대폰 → PC</b><br>① 이 앱 설정 → 백업·복원 → <b>파일로 내보내기</b>로 저장합니다.<br>② 그 파일을 PC로 옮긴 뒤 PC판 설정 → 암호 · 백업 → <b>백업 파일로 복원하기…</b>로 엽니다.<br>
      <div class="muted">두 곳에서 따로 입력한 뒤 합치는 기능은 없습니다. 한쪽에서 입력하고 파일을 옮겨 이어서 쓰세요. 가져오기 전 자료는 앱 안에 자동 보관됩니다.</div>
      <div class="section-t">입력</div>
      · 가계부 화면의 ＋ 버튼으로 입력합니다. 품목을 예전과 같게 쓰면 계정이 자동으로 골라집니다.<br>
      · 내역을 누르면 고치거나 지울 수 있습니다.<br>
      · 달력에서 날짜를 누르면 그날 일정과 내역을 봅니다.<br>
      · ◀ 2026년 10월 ▾ ▶ 의 가운데 글자를 누르면 연·월을 바로 고를 수 있습니다.<br>
      · 매달 같은 수입·지출은 <b>예약 입력</b>에 등록하면 앱을 열 때 입력할지 물어봅니다.
      <div class="section-t">장부 · 글자 크기</div>
      · 맨 위 장부 목록에서 생활비·용돈·비상금·여행 장부로 바꿔 따로 적을 수 있습니다.<br>
      · 목록 맨 아래 <b>＋ 새 장부 만들기</b>로 장부를 더 만들고, <b>장부 관리…</b>에서 이름 바꾸기·비우기·삭제를 합니다.<br>
      · 설정 → 화면 꾸미기 → <b>글자 크기</b>에서 1픽셀씩 키우거나 줄입니다.
      <div class="section-t">자료 보관</div>
      · 자료는 휴대폰 안에만 저장됩니다 (인터넷으로 보내지 않음).<br>
      · 새 버전 확인 때만 인터넷(GitHub 릴리스 목록)에 접속합니다. 설정 → 업데이트에서 끌 수 있어요.<br>
      · 하루 한 번 앱 안에 자동 사본을 만들어 최근 7개를 보관합니다. <b>앱을 지우면 앱 안 사본도 함께 지워지니</b>, 가끔 <b>파일로 내보내기</b>로 따로 보관하세요.
    </div>`));
  },
};
