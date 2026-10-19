/* 설정: 장부·계정과목·품목·암호·백업·CSV·화면 꾸미기·앱 정보 */
'use strict';
Pages.settings = (() => {
  const STICKERS = [];
  for (let i = 1; i <= 22; i++) STICKERS.push('a' + U.pad(i));
  for (let i = 1; i <= 40; i++) STICKERS.push('b' + U.pad(i));

  // 설정 첫 화면 = 묶음별 목록 (아이콘 · 이름 · 지금 값 · ›). 꾸미기·프로필·업데이트는 따로 들어가는 화면
  const SECTIONS = { deco: '화면 꾸미기', profile: '내 프로필', update: '업데이트' };
  const THEME_NAMES = { retro: '미니홈피', basic: '기본', feed: '피드 · 미니홈피 색', feed_light: '피드 · 밝게', feed_dark: '피드 · 어둡게',
    timeline: '타임라인 · 미니홈피 색', timeline_light: '타임라인 · 밝게', timeline_dark: '타임라인 · 어둡게' };
  const grp = (title, body, note, pad) => `<section class="sgroup"><h3 class="sgroup-t">${title}</h3><div class="sgroup-b${pad ? ' pad' : ''}">${body}</div>${note ? `<p class="sgroup-n">${note}</p>` : ''}</section>`;
  const row = (a, ic, label, val, cls) => `<button class="srow${cls ? ' ' + cls : ''}" data-a="${a}">${UI.icon(ic)}<span class="nm">${label}</span>${val ? `<span class="val">${U.esc(val)}</span>` : ''}${UI.icon('chevr', 'go')}</button>`;

  function render(c, p) {
    const section = p && p.section;
    if (section === 'deco') { renderDeco(c); return; }
    if (section === 'profile') { renderProfile(c); return; }
    if (section === 'update') { renderUpdate(c); return; }
    const hasPw = !!DB.getMeta('password');
    c.appendChild(UI.el(`<div class="settings">
      <button class="sme" data-a="profile"><img src="${UI.sticker(App.pref('minimi'))}" alt=""><span class="nm"><b>${U.esc(App.ledgerName())}</b>
        <small>오늘의 기분: ${U.esc(App.pref('mood'))}</small></span>${UI.icon('chevr', 'go')}</button>
      ${grp('장부', row('ledgers', 'book', '장부 관리', `${L.ledgers().length}개`) + row('codes', 'tag', '계정과목') + row('items', 'pen', '품목 자동완성')
        + row('settle', 'calendar', '결산일', `${Rep.settleDay()}일`))}
      ${grp('화면', row('deco', 'palette', '화면 꾸미기', THEME_NAMES[App.theme()]) + row('profile', 'user', '내 프로필', '미니미 · 기분 · 한마디'))}
      ${grp('백업 (PC와 주고받기)', row('export', 'upload', '백업 파일 저장', '내 파일 · 구글 드라이브') + row('share', 'send', '백업 파일 보내기', '카톡 · 디스코드 등'),
        '저장: 저장 창 왼쪽 위 ☰ 를 누르면 내 파일(내장 메모리·다운로드 등 원하는 폴더)이나 Google Drive 를 고를 수 있습니다. 보내기: 카카오톡·디스코드·메일 등 고른 앱으로 파일을 보냅니다.')}
      ${grp('백업 불러오기', row('import', 'download', '백업 파일 불러오기', '내 파일 · 구글 드라이브') + row('importapp', 'archive', '다른 앱에서 불러오기', '내 파일 앱 등')
        + row('kept', 'refresh', '앱 안 보관본', '하루 한 번 자동'),
        '불러오면 지금 자료를 백업 파일 내용으로 바꿉니다 (지금 자료는 앱 안 보관본에 남김). Google Drive 는 휴대폰에 드라이브 앱이 있어야 보입니다. 카톡으로 받은 파일은 카톡에서 저장한 뒤 내 파일에서 고르세요.')}
      ${grp('CSV (엑셀)', row('csvout', 'table', '내역 CSV로 저장') + row('csvin', 'download', 'CSV 내역 불러오기'), '불러오기 형식: 날짜, 품목, 수입, 지출, 계정코드[, 계정과목, 메모]')}
      ${grp('보안', row('pw', 'lock', hasPw ? '시작 암호 바꾸기' : '시작 암호 정하기', hasPw ? '설정됨' : '없음') + (hasPw ? row('pwoff', 'lock', '시작 암호 해제', '', 'danger') : ''))}
      ${grp('앱', row('update', 'refresh', '업데이트', App.updState().latest ? `새 버전 ${App.updState().latest.version}` : `지금 판 ${App.updState().version || '?'}`)
        + row('info', 'info', '앱 정보'))}
    </div>`));
    const sub = k => () => App.go('settings', { section: k }, true);
    const act = {
      ledgers: ledgerSheet, codes: () => App.go('codes', {}, true), items: itemSheet, settle: settleSheet,
      export: exportDb, share: shareDb, import: () => importDb(false), importapp: () => importDb(true), kept: keptSheet, csvout: csvOut, csvin: csvIn, pw: pwSheet, pwoff: pwOff,
      deco: sub('deco'), profile: sub('profile'), update: sub('update'), info: () => UI.sheet({ title: '앱 정보', body: infoHtml() }),
    };
    UI.on(c, '[data-a]', 'click', (e, b) => act[b.dataset.a]());
  }
  function renderDeco(c) {
    c.appendChild(UI.el(`<div class="settings">${decoHtml()}</div>`));
    bindDeco(c);
  }
  function renderProfile(c) {
    c.appendChild(UI.el(`<div class="settings">
      ${grp('미니미 (맨 위·프로필 그림)', `<div class="stickers">${STICKERS.map(s => `<button data-st="${s}"><img src="${UI.sticker(s)}" alt="" loading="lazy"></button>`).join('')}</div>`, '', true)}
      ${grp('오늘의 기분', `<select class="inp" data-p="mood">${App.MOODS.map(m => `<option>${U.esc(m)}</option>`).join('')}</select>`, '', true)}
      ${grp('한마디', `<input class="inp" type="text" data-p="motto" placeholder="오늘도 알뜰살뜰 (^-^)v">`, '미니홈피 테마는 맨 위 전광판에, 피드·타임라인 테마는 가계부 프로필에 나옵니다.', true)}</div>`));
    bindPrefs(c);
    const cur = App.pref('minimi');
    UI.$$('[data-st]', c).forEach(b => b.classList.toggle('on', b.dataset.st === cur));
    UI.on(c, '[data-st]', 'click', (e, b) => {
      App.setPref('minimi', b.dataset.st);
      UI.$$('[data-st]', c).forEach(x => x.classList.toggle('on', x === b));
      App.updateHeader();
    });
  }
  function renderUpdate(c) {
    c.appendChild(UI.el(`<div class="settings">${grp('새 버전', '<div class="updbox"></div>', '', true)}</div>`));
    const ub = UI.$('.updbox', c);
    drawUpd(ub);
    App.onUpd(() => { if (ub.isConnected) drawUpd(ub); });
  }

  // ── 장부 관리 ──
  function ledgerSheet() {
    const ls = L.ledgers();
    const first = L.firstLedgerId();
    const body = UI.el(`<div><ul class="list">${ls.map(l => `<li><div class="grow"><div class="main-t">${U.esc(l.name)}${l.id === App.lid ? ' <span class="chip on">지금 장부</span>' : ''}</div>
      <div class="sub">내역 ${DB.val('SELECT COUNT(*) AS v FROM entry WHERE ledger_id=?', [l.id])}건</div></div>
      <button class="btn sm" data-r="${l.id}">이름</button><button class="btn sm" data-z="${l.id}">비우기</button>${l.id === first ? '' : `<button class="btn sm danger" data-d="${l.id}">삭제</button>`}</li>`).join('')}</ul></div>`);
    const sh = UI.sheet({ title: '장부 관리', body, full: true, buttons: [{ label: '새 장부', cls: 'pri', onClick: () => { setTimeout(newLedger, 0); } }] });
    const name = id => ls.find(l => l.id === id).name;
    UI.on(body, '[data-r]', 'click', (e, b) => {
      const id = Number(b.dataset.r);
      UI.formSheet({ title: '장부 이름 바꾸기', fields: [{ k: 'name', label: '장부 이름', type: 'text', req: true }], values: { name: name(id) },
        onSave: v => { L.renameLedger(id, v.name); App.reloadLedgers(); App.dataChanged(); sh.close(); } });
    });
    UI.on(body, '[data-z]', 'click', (e, b) => {
      const id = Number(b.dataset.z);
      UI.confirm(`'${name(id)}'의 내역·예산·예약을 모두 지울까요?\n(계정과목은 남습니다. 되돌릴 수 없으니 먼저 파일로 내보내 두세요)`, '모두 지우기', true).then(ok => {
        if (ok) { L.resetLedger(id); sh.close(); App.dataChanged(); UI.toast('장부를 비웠습니다'); }
      });
    });
    UI.on(body, '[data-d]', 'click', (e, b) => {
      const id = Number(b.dataset.d);
      UI.confirm(`장부 '${name(id)}'과(와) 그 안의 모든 자료를 삭제할까요?`, '삭제', true).then(ok => {
        if (!ok) return;
        try { L.deleteLedger(id); } catch (err) { UI.alert(err.message); return; }
        sh.close(); App.reloadLedgers(); App.selectLedger(id === App.lid ? L.firstLedgerId() : App.lid);
      });
    });
  }
  function newLedger() {
    UI.formSheet({ title: '새 장부', fields: [{ k: 'name', label: '장부 이름', type: 'text', req: true },
      { k: 'how', label: '만드는 방법', type: 'select', options: [['empty', '빈 장부 (대분류 수입만)'], ['codes', `지금 장부(${App.ledgerName()})의 계정과목만 복사`], ['all', '지금 장부를 통째로 복사']] }],
    values: { how: 'codes' },
    onSave: v => {
      const lid = L.addLedger(v.name, v.how === 'empty' ? null : App.lid, v.how === 'codes');
      App.selectLedger(lid);
      UI.toast('새 장부를 만들었습니다');
    } });
  }

  // ── 품목 자동완성 ──
  function itemSheet() {
    const lid = App.lid;
    const min = parseInt(DB.getMeta('item_min_count', 1) || 1, 10) || 1;
    const words = L.itemWords(lid, 1);
    const body = UI.el(`<div><div class="form"><div class="f"><label class="l">자동완성에 보일 최소 사용 횟수</label><input type="number" data-k="min" value="${min}"></div></div>
      <ul class="list">${words.slice(0, 300).map(w => `<li><div class="grow">${U.esc(w.name)}</div><span class="muted small">${w.count}회</span><button class="btn sm danger" data-w="${U.esc(w.name)}">삭제</button></li>`).join('')}</ul></div>`);
    UI.on(body, '[data-w]', 'click', (e, b) => { L.deleteItemWord(lid, b.dataset.w); b.closest('li').remove(); });
    UI.sheet({ title: '품목 자동완성', body, full: true, buttons: [{ label: '저장', cls: 'pri', onClick: (cl, sb) => {
      const n = parseInt(UI.$('[data-k=min]', sb).value, 10);
      if (!n || n < 1) { UI.toast('1 이상으로 입력하세요'); return false; }
      DB.setMeta('item_min_count', n);
      return undefined;
    } }] });
  }
  function settleSheet() {
    UI.formSheet({ title: '결산일', fields: [{ k: 'sd', label: '결산일 (1~31)', type: 'int', hint: '5일이면 5일~다음달 4일을 한 달로 셉니다' }], values: { sd: Rep.settleDay() },
      onSave: v => { if (!v.sd || v.sd < 1 || v.sd > 31) throw new Error('1~31 사이로 입력하세요.'); DB.setMeta('settle_day', v.sd); App.dataChanged(); } });
  }

  // ── 백업 · 복원 ──
  const backupName = () => `우리집가계부-백업-${U.today()}.sqlite3`;
  /** 백업 파일 저장: 시스템 저장 창에서 위치를 마음대로 (내 파일의 아무 폴더 · Google Drive 등) */
  function exportDb() {
    App.nativeAsync('exportDb', backupName()).then(r => {
      if (r.ok) UI.alert(`백업 파일을 저장했습니다 (${Math.round(r.size / 1024)}KB).\n\n불러올 때는 설정 → 백업 불러오기에서 이 파일을 고르세요. PC판에서는 설정 → 암호 · 백업 → '백업 파일로 복원하기…'로 엽니다.`);
      else if (!r.cancel) UI.alert('저장하지 못했습니다.\n' + r.error);
    });
  }
  /** 백업 파일 보내기: 공유 창 (카카오톡·디스코드·메일·드라이브 등) */
  function shareDb() {
    if (!App.native.shareDb) { UI.alert('이 앱 판에서는 보내기를 쓸 수 없습니다. 앱을 새 버전으로 업데이트하세요.'); return; }
    App.nativeAsync('shareDb', backupName()).then(r => {
      if (!r.ok) UI.alert('보내기 창을 열지 못했습니다.\n' + r.error);
    });
  }
  /** 백업 불러오기: via=false 시스템 파일 창(내 파일·Google Drive) / via=true 앱을 먼저 고름(삼성 내 파일 등) */
  function importDb(via) {
    UI.confirm('지금 휴대폰의 자료를 고른 백업 파일 내용으로 바꿉니다.\n지금 자료는 앱 안에 보관해 두니 \'앱 안 보관본\'에서 되돌릴 수 있습니다.\n\n계속할까요?', '파일 고르기').then(ok => {
      if (!ok) return;
      App.nativeAsync(via && App.native.importDbVia ? 'importDbVia' : 'importDb').then(r => {
        if (r.ok) { App.afterReplace(); UI.alert('자료를 가져왔습니다.' + (r.kept ? `\n이전 자료 보관: ${r.kept}` : '')); }
        else if (!r.cancel) UI.alert('가져오지 못했습니다.\n' + r.error + '\n\n지금 자료는 그대로입니다.');
      });
    });
  }
  function keptSheet() {
    let items = [];
    try { const o = JSON.parse(App.native.listBackups()); items = o.items || []; } catch (_) { /* 없음 */ }
    items.sort((a, b) => b.mtime - a.mtime);
    const label = k => (k === 'autobackup' ? '자동 보관 (하루 한 번)' : k === 'corrupt' ? '손상되어 옮겨 둔 파일' : '가져오기 전 자료');
    const body = UI.el(`<div><div class="small muted" style="margin-bottom:6px">앱을 지우면 이 보관본도 함께 지워집니다. 오래 보관하려면 '파일로 내보내기'를 쓰세요.</div>
      ${items.length ? `<ul class="list">${items.map((x, i) => `<li class="tap" data-i="${i}"><div class="grow"><div class="main-t">${U.esc(x.name)}</div>
      <div class="sub">${label(x.kind)} · ${Math.round(x.size / 1024)}KB</div></div><span class="chip">되돌리기</span></li>`).join('')}</ul>` : UI.empty('보관본이 없어요')}</div>`);
    const sh = UI.sheet({ title: '앱 안 보관본', body, full: true });
    UI.on(body, '[data-i]', 'click', (e, li) => {
      const x = items[Number(li.dataset.i)];
      UI.confirm(`'${x.name}' 내용으로 자료를 바꿀까요?\n(지금 자료도 보관해 둡니다)`, '되돌리기', true).then(ok => {
        if (!ok) return;
        const r = JSON.parse(App.native.restoreBackup(x.kind, x.name));
        if (!r.ok) { UI.alert('되돌리지 못했습니다.\n' + r.error); return; }
        sh.close();
        App.afterReplace();
        UI.toast('되돌렸습니다');
      });
    });
  }

  // ── CSV ──
  function csvOut() {
    const lid = App.lid;
    const cmap = L.categoryMap(lid);
    const rows = DB.q('SELECT * FROM entry WHERE ledger_id=? ORDER BY date, id', [lid]);
    const csv = Bk.toCsv(Bk.CSV_HEADER, rows.map(r => [r.date, r.item, r.income, r.expense, r.code, L.codeLabel(cmap, r.code), r.memo]));
    App.nativeAsync('saveText', `${App.ledgerName()}_내역.csv`, 'text/csv', csv).then(r => {
      if (r.ok) UI.toast(`${rows.length}건을 저장했습니다`); else if (!r.cancel) UI.alert('저장하지 못했습니다.\n' + r.error);
    });
  }
  function csvIn() {
    App.nativeAsync('openText').then(r => {
      if (!r.ok) { if (!r.cancel) UI.alert('파일을 읽지 못했습니다.\n' + r.error); return; }
      const lid = App.lid;
      const valid = new Set(L.categories(lid).map(x => x.code));
      const [rows, errors] = Bk.readEntriesCsv(r.text, valid);
      const body = `<div><div>정상 ${rows.length}건${errors.length ? `, <span class="out">오류 ${errors.length}건</span>` : ''}</div>
        ${errors.length ? `<ul class="list small">${errors.slice(0, 50).map(([n, m]) => `<li>${n}행: ${U.esc(m)}</li>`).join('')}</ul>` : ''}
        <div class="small muted" style="margin-top:6px">정상인 행만 '${U.esc(App.ledgerName())}' 장부에 넣습니다.</div></div>`;
      UI.sheet({ title: 'CSV 내역 불러오기', body, full: errors.length > 5, buttons: [{ label: '취소' }, { label: `${rows.length}건 넣기`, cls: 'pri', onClick: () => {
        if (!rows.length) return undefined;
        DB.tx(() => rows.forEach(x => L.addEntry(lid, x, 'csv')));
        App.dataChanged();
        UI.toast(`${rows.length}건을 넣었습니다`);
        return undefined;
      } }] });
    });
  }

  // ── 암호 (PC판과 같은 방식이라 백업 파일을 옮겨도 같은 암호) ──
  function pwSheet() {
    const has = !!DB.getMeta('password');
    const fields = (has ? [{ k: 'cur', label: '지금 암호', type: 'password', req: true }] : [])
      .concat([{ k: 'pw1', label: '새 암호', type: 'password', req: true }, { k: 'pw2', label: '새 암호 한 번 더', type: 'password', req: true }]);
    UI.formSheet({ title: has ? '암호 변경' : '암호 설정', fields,
      extra: '<div class="small muted">암호를 잊으면 앱 데이터를 지워야 합니다 (PC판에서 암호를 지운 백업 파일로 다시 옮길 수는 있음).</div>',
      onSave: v => {
        if (has && !Bk.checkPassword(v.cur, DB.getMeta('password'))) throw new Error('지금 암호가 틀렸습니다.');
        if (v.pw1 !== v.pw2) throw new Error('새 암호 두 칸이 다릅니다.');
        DB.setMeta('password', Bk.hashPassword(v.pw1));
        App.dataChanged();
        UI.toast('암호를 저장했습니다');
      } });
  }
  function pwOff() {
    UI.formSheet({ title: '암호 해제', fields: [{ k: 'cur', label: '지금 암호', type: 'password', req: true }],
      onSave: v => {
        if (!Bk.checkPassword(v.cur, DB.getMeta('password'))) throw new Error('암호가 틀렸습니다.');
        DB.run("DELETE FROM meta WHERE key='password'");
        App.dataChanged();
        UI.toast('암호를 해제했습니다');
      } });
  }

  // ── 화면 꾸미기 (이 휴대폰에만 저장) ──
  function decoHtml() {
    return `${grp('테마', `<select class="inp" data-p="theme">${Object.entries(THEME_NAMES).map(([k, v]) => `<option value="${k}">${v}${k === 'retro' ? ' (2000년대 감성)' : k === 'basic' ? ' (깔끔하게)' : k === 'feed' ? ' (사진 SNS 모양)' : k === 'timeline' ? ' (짧은 글 SNS 모양)' : ''}</option>`).join('')}</select>`,
      '피드·타임라인은 화면이 SNS 앱처럼 바뀌고 휴대폰 기본 글꼴을 씁니다. 기능은 같습니다. 색은 미니홈피 색·밝게·어둡게 중에서 고릅니다.', true)}
      ${grp('글자', `<div class="form"><div class="f"><label class="l">글꼴</label><select data-p="font"><option value="pixel">도트 글꼴 (갈무리)</option><option value="system">휴대폰 기본 글꼴</option>${Object.entries(App.FONTS).map(([k, f]) => `<option value="${k}">${f[0]}</option>`).join('')}</select></div>
        <div class="f" style="margin-bottom:0"><label class="l">글자 크기 <b class="fs-v"></b></label>
        <div class="fsz"><button class="btn sm" data-fs="-1" aria-label="1픽셀 작게">－</button><input type="range" min="${App.FS_MIN}" max="${App.FS_MAX}" step="1" data-fsr aria-label="글자 크기">
        <button class="btn sm" data-fs="1" aria-label="1픽셀 크게">＋</button><button class="btn sm" data-fs="0">기본</button></div></div></div>`,
        `도트 글꼴은 미니홈피·기본 테마에서, 고운돋움·주아·개구·서툰이야기(무료 글꼴)는 모든 테마에서 쓰입니다. 글자 크기는 1픽셀씩 (${App.FS_MIN}~${App.FS_MAX}px), 바꾸면 바로 보입니다.`, true)}
      ${grp('순서', `<div class="row wrap"><button class="btn sm" data-ord="nav">메뉴 순서</button><button class="btn sm" data-ord="layout">가계부 화면 구성</button></div>`,
        '메뉴: 위 4개가 아래 탭, 나머지는 더보기 화면. 계정과목 순서는 설정 → 계정과목에서.', true)}
      ${grp('이 테마의 색', `<div class="colors"></div><div class="row" style="margin-top:8px"><button class="btn sm" data-creset>이 테마 색 모두 처음으로</button></div>`,
        '고른 색은 이 휴대폰의 지금 테마에만 쓰입니다. 나머지 색(테두리·흐린 글자 등)은 고른 색에 맞춰 바뀝니다.', true)}
      ${grp('맨 위 전광판', '<label class="check" style="margin:0"><input type="checkbox" data-p="marquee"> 흐르는 글자 보이기</label>', '미니홈피 테마에서만 보입니다.', true)}`;
  }
  /** data-p 칸 (테마·글꼴·전광판·기분·한마디): 바꾸면 바로 저장·적용 */
  function bindPrefs(c, onTheme) {
    UI.$$('[data-p]', c).forEach(x => {
      const k = x.dataset.p;
      if (x.type === 'checkbox') x.checked = App.pref(k) === 'true'; else x.value = App.pref(k) || '';
      x.addEventListener('change', () => {
        App.setPref(k, x.type === 'checkbox' ? String(x.checked) : x.value);
        App.applyTheme();
        App.updateHeader();
        if (k === 'theme' && onTheme) onTheme();
      });
    });
  }
  function bindDeco(c) {
    bindPrefs(c, () => drawColors(c));
    // 글자 크기 (1px 단위)
    const fsr = UI.$('[data-fsr]', c), fsv = UI.$('.fs-v', c);
    const showFs = () => { fsr.value = App.fontPx(); fsv.textContent = App.fontPx() + 'px'; };
    showFs();
    fsr.addEventListener('input', () => { App.setFontPx(Number(fsr.value)); App.updateHeader(); showFs(); });
    UI.$$('[data-fs]', c).forEach(b => b.addEventListener('click', () => {
      const d = Number(b.dataset.fs);
      App.setFontPx(d === 0 ? null : App.fontPx() + d);
      App.updateHeader();
      showFs();
    }));
    UI.$('[data-ord="nav"]', c).onclick = () => App.navReorderSheet();
    UI.$('[data-ord="layout"]', c).onclick = () => App.layoutReorderSheet();
    UI.$('[data-creset]', c).onclick = () => {
      App.setPref('colors_' + App.theme(), null);
      App.applyTheme();
      App.updateHeader();
      drawColors(c);
      UI.toast('처음 색으로 되돌렸습니다');
    };
    drawColors(c);
  }
  /** 지금 테마의 색 6가지 견본 (누르면 색 고르기) */
  function drawColors(c) {
    const box = UI.$('.colors', c);
    if (!box) return;
    const base = App.baseColors(), cu = App.customColors();
    box.innerHTML = App.COLOR_KEYS.map(([k, label]) => {
      const v = cu[k] || base[k];
      return `<button class="csw${cu[k] ? ' changed' : ''}" data-ck="${k}"><span class="dot" style="background:${v}"></span><span class="nm">${U.esc(label)}</span><span class="hx">${v}${cu[k] ? ' ✎' : ''}</span></button>`;
    }).join('');
    UI.on(box, '[data-ck]', 'click', (e, b) => {
      const k = b.dataset.ck, label = App.COLOR_KEYS.find(x => x[0] === k)[1];
      UI.colorPicker({ title: `${label} 색`, value: App.customColors()[k] || App.baseColors()[k], original: App.baseColors()[k],
        onPick: hex => { App.setCustomColor(k, hex); drawColors(c); },
        onReset: () => { App.setCustomColor(k, null); drawColors(c); } });
    });
  }
  // ── 업데이트: 자동 확인 켜기·끄기, 직접 확인·내려받기·설치 ──
  function drawUpd(box) {
    const s = App.updState(), l = s.latest, d = s.downloaded;
    const lines = l ? ((l.changes && l.changes.length ? l.changes : l.notes) || []) : [];
    box.innerHTML = `<div class="small" style="margin-bottom:6px">지금 판: ${U.esc(s.version || '?')}</div>
      <label class="check"><input type="checkbox" data-u="auto"${s.auto ? ' checked' : ''}> 앱을 켤 때 새 버전이 있는지 자동으로 확인</label>
      <div class="row wrap" style="margin-top:6px"><button class="btn sm pri" data-u="check"${s.busy ? ' disabled' : ''}>업데이트 확인</button>
        ${l && !(d && d.ver === l.version) ? `<button class="btn sm" data-u="dl"${s.busy ? ' disabled' : ''}>새 버전 ${U.esc(l.version)} 내려받기</button>` : ''}
        ${d ? `<button class="btn sm" data-u="inst"${s.busy ? ' disabled' : ''}>내려받은 새 버전 ${U.esc(d.ver)} 설치</button>` : ''}</div>
      <div class="small upd-st" style="margin-top:6px">${U.esc(s.status || '아직 확인하지 않았습니다.')}</div>
      ${l ? `<div class="small upd-notes"><b>새 버전 ${U.esc(l.version)} 업데이트 내용</b><br>${lines.map(x => '· ' + U.esc(x)).join('<br>') || '· (적힌 내용 없음)'}</div>` : ''}
      <div class="small muted" style="margin-top:6px">새 버전 확인 때는 GitHub 의 공개 릴리스 목록만 읽습니다. 가계부 자료는 보내지 않습니다. 받은 파일은 릴리스에 적힌 크기·SHA-256 과 맞을 때만 설치 화면을 엽니다.</div>`;
    UI.$('[data-u=auto]', box).onchange = e => App.setUpdAuto(e.target.checked);
    UI.$('[data-u=check]', box).onclick = () => App.checkUpdate(true);
    const dl = UI.$('[data-u=dl]', box);
    if (dl) dl.onclick = () => App.downloadUpdate(App.updState().latest);
    const inst = UI.$('[data-u=inst]', box);
    if (inst) inst.onclick = () => { const x = App.updState().downloaded; if (x) App.askInstall(x.name, x.ver); };
  }
  function infoHtml() {
    let info = {};
    try { info = JSON.parse(App.native.appInfo()); } catch (_) { /* 없음 */ }
    return `<div class="small" style="line-height:1.7">우리집 가계부 (안드로이드판) ${U.esc(info.version || '')}<br>
      자료 파일 크기: ${info.dbSize ? Math.round(info.dbSize / 1024) + 'KB' : '-'}<br>
      <span class="muted">글꼴 (모두 SIL Open Font License 1.1): 갈무리(Galmuri) · 고운돋움 · 주아 · 개구 · 서툰이야기 · 나눔손글씨 펜(피드 로고)<br>
      음력 계산: korean-lunar-calendar — MIT License<br>
      아늑단 이미지: 사용자가 제공한 스티커 시트에서 오려 낸 그림 (개인 사용)</span></div>`;
  }
  return { title: p => SECTIONS[p && p.section] || '설정', sticker: 'b08', sub: '내 맘대로 꾸미기', render, tab: 'more', newLedger, ledgerSheet };
})();

// ════════ 계정과목 편집 ════════
Pages.codes = (() => {
  function render(c) {
    const lid = App.lid;
    c.appendChild(UI.el(`<div class="small muted" style="margin-bottom:6px">'${U.esc(App.ledgerName())}' 장부의 계정과목입니다. 계정코드 첫 글자가 대분류이고, 0으로 시작하면 수입입니다.
      순서는 입력할 때 고르는 목록과 결산 보고서에 그대로 쓰이고, PC판에서도 같습니다.</div>`));
    const gs = L.groups(lid), cats = L.categories(lid);
    const gb = UI.el('<div class="row" style="margin-bottom:6px"><button class="btn sm" data-gord>대분류 순서 바꾸기</button></div>');
    c.appendChild(gb);
    let html = '';
    for (const g of gs) {
      const n = cats.filter(x => x.code.slice(0, 1) === g.code).length;
      html += `<div class="dayhead"><span class="tap" data-g="${U.esc(g.code)}">(${U.esc(g.code)}) ${U.esc(g.name)} <span class="small muted">편집 ›</span></span>
        <span class="sums">${n > 1 ? `<button class="btn sm" data-cord="${U.esc(g.code)}">소분류 순서</button>` : ''}</span></div><ul class="list">`;
      html += cats.filter(x => x.code.slice(0, 1) === g.code).map(x => `<li class="tap" data-c="${U.esc(x.code)}"><span class="chip">${U.esc(x.code)}</span><div class="grow">${U.esc(x.name)}</div></li>`).join('');
      html += `<li class="tap muted" data-add="${U.esc(g.code)}">＋ 소분류 추가</li></ul>`;
    }
    c.appendChild(UI.el(`<div>${html}</div>`));
    UI.$('[data-gord]', gb).onclick = () => UI.reorder({ title: '대분류 순서', items: L.groups(lid).map(g => ({ key: g.code, label: `(${g.code}) ${g.name}` })),
      onSave: keys => { Ord.setGroupOrder(lid, keys); App.dataChanged(); },
      onReset: () => { Ord.setGroupOrder(lid, []); App.dataChanged(); }, resetLabel: '코드 순으로' });
    UI.on(c, '[data-cord]', 'click', (e, b) => {
      const g = b.dataset.cord;
      const list = L.categories(lid, g);
      UI.reorder({ title: `소분류 순서 (${g})`, items: list.map(x => ({ key: x.code, label: `${x.code} ${x.name}` })),
        onSave: keys => { Ord.setCategoryOrder(lid, keys); App.dataChanged(); },
        onReset: () => { Ord.setCategoryOrder(lid, list.map(x => x.code).sort()); App.dataChanged(); }, resetLabel: '코드 순으로' });
    });
    UI.on(c, '[data-g]', 'click', (e, x) => groupSheet(x.dataset.g));
    UI.on(c, '[data-c]', 'click', (e, x) => catSheet(x.dataset.c));
    UI.on(c, '[data-add]', 'click', (e, x) => addCat(x.dataset.add));
    App.fab(addGroup, '대분류 추가');
  }
  function addGroup() {
    const lid = App.lid;
    const used = new Set(L.groups(lid).map(g => g.code));
    const free = U.CODE_CHARS.split('').filter(ch => !used.has(ch));
    if (!free.length) { UI.alert('더 만들 수 있는 대분류 코드가 없습니다.'); return; }
    UI.formSheet({ title: '대분류 추가', fields: [{ k: 'code', label: '대분류 코드', type: 'select', options: free.map(f => [f, f === '0' ? '0 (수입)' : f]) },
      { k: 'name', label: '이름', type: 'text', req: true }],
    onSave: v => { L.setGroup(lid, v.code, v.name); App.dataChanged(); } });
  }
  function groupSheet(code) {
    const lid = App.lid;
    const g = L.groups(lid).find(x => x.code === code);
    UI.formSheet({ title: `대분류 (${code})`, fields: [{ k: 'name', label: '이름', type: 'text', req: true, hint: code === '0' ? '0번(수입) 대분류 이름은 바꿀 수 없습니다' : '' }],
      values: { name: g.name },
      onSave: v => { L.setGroup(lid, code, v.name); App.dataChanged(); },
      onDelete: code === '0' ? null : close => UI.confirm(`대분류 (${code}) ${g.name}을(를) 삭제할까요?`, '삭제', true).then(ok => {
        if (!ok) return;
        try { L.deleteGroup(lid, code); close(); App.dataChanged(); } catch (err) { UI.alert(err.message); }
      }) });
  }
  function addCat(g) {
    const lid = App.lid;
    const used = new Set(L.categories(lid).map(x => x.code));
    const free = U.CODE_CHARS.split('').map(ch => g + ch).filter(c => !used.has(c));
    if (!free.length) { UI.alert('이 대분류에는 더 만들 수 있는 코드가 없습니다.'); return; }
    UI.formSheet({ title: '소분류 추가', fields: [{ k: 'code', label: '계정코드', type: 'select', options: free.map(f => [f, f]) }, { k: 'name', label: '이름', type: 'text', req: true }],
      onSave: v => { L.setCategory(lid, v.code, v.name); App.dataChanged(); } });
  }
  function catSheet(code) {
    const lid = App.lid;
    const x = L.categories(lid).find(c => c.code === code);
    const use = L.categoryUsage(lid, code);
    const others = L.categories(lid).filter(c => c.code !== code);
    UI.formSheet({ title: `계정과목 ${code}`, fields: [{ k: 'name', label: '이름', type: 'text', req: true }], values: { name: x.name },
      extra: `<div><div class="small muted">사용: 내역 ${use.entry}건 · 예약 ${use.recurring}건 · 예산 ${use.budget}건</div>
        <div class="row wrap" style="margin-top:8px"><button class="btn sm" data-up>위로</button><button class="btn sm" data-dn>아래로</button></div>
        <div class="section-t">다른 계정으로 합치기</div><div class="row"><select class="inp grow" data-to>${others.map(o => `<option value="${U.esc(o.code)}">${U.esc(o.code)} ${U.esc(o.name)}</option>`).join('')}</select><button class="btn sm" data-merge>합치기</button></div>
        <div class="small muted">이 계정의 내역·예약·예산을 고른 계정으로 옮기고 이 계정은 지웁니다.</div></div>`,
      afterOpen: sb => {
        UI.$('[data-up]', sb).onclick = () => { L.moveCategoryOrder(lid, code, -1); App.dataChanged(); UI.toast('순서를 바꿨습니다'); };
        UI.$('[data-dn]', sb).onclick = () => { L.moveCategoryOrder(lid, code, 1); App.dataChanged(); UI.toast('순서를 바꿨습니다'); };
        UI.$('[data-merge]', sb).onclick = () => {
          const to = UI.$('[data-to]', sb).value;
          if (!to) return;
          UI.confirm(`${code} ${x.name} → ${to} 로 합칠까요?`, '합치기', true).then(ok => {
            if (!ok) return;
            try { L.mergeCategory(lid, code, to); UI.closeTop(); App.dataChanged(); UI.toast('합쳤습니다'); } catch (err) { UI.alert(err.message); }
          });
        };
      },
      onSave: v => { L.setCategory(lid, code, v.name); App.dataChanged(); },
      onDelete: close => UI.confirm(`계정 ${code} ${x.name}을(를) 삭제할까요?\n이 계정으로 입력한 내역 ${use.entry}건·예약 ${use.recurring}건·예산 ${use.budget}건도 함께 지워집니다.\n(내역을 남기려면 '다른 계정으로 합치기'를 쓰세요)`, '삭제', true).then(ok => {
        if (ok) { L.deleteCategory(lid, code); close(); App.dataChanged(); }
      }) });
  }
  return { title: '계정과목', sticker: 'b08', sub: '대분류·소분류 편집', render, tab: 'more' };
})();
