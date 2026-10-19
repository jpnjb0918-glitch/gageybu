/* 앱 틀: 시작·암호·화면 이동·맨 위 미니홈피 머리·아래 탭 */
'use strict';
const Pages = {};

const App = (() => {
  const MOODS = ['행복 (^-^)', '신남 (^0^)/', '알뜰 (-_-)b', '월급날 ♡(^_^)♡', '두근두근 (*^^*)',
    '텅장 (ㅠ_ㅠ)', '지름신 강림 (>_<)', '피곤 (-_-)zZ'];
  const DEFAULTS = { theme: 'retro', font: 'pixel', fontsize: 'm', marquee: 'true', minimi: 'b16', mood: MOODS[0], motto: '' };
  const SIZES = { pixel: { s: 13, m: 14, l: 16, xl: 18 }, system: { s: 14, m: 15, l: 17, xl: 19 } };
  // 메뉴: 순서는 사용자가 바꿀 수 있음 (앞 4개 = 아래 탭, 나머지 = 더보기 화면)
  const NAV = { ledger: ['가계부', 'a22'], calendar: ['달력', 'b11'], report: ['결산', 'b30'], assets: ['자산', 'a04'],
    search: ['검색', 'b23'], graph: ['그래프', 'b26'], recurring: ['예약 입력', 'b38'], anniv: ['기념일', 'b11'],
    contacts: ['주소록', 'a13'], diary: ['일기장', 'b33'], memo: ['메모장', 'a19'], settings: ['설정', 'b08'], help: ['도움말', 'b02'] };
  const NAV_TABS = 4;
  const MORE = ['더보기', 'a10'];
  // 가계부 화면 구성: 덩어리 순서도 바꿀 수 있음
  const LAYOUT = { monthnav: '달 이동 (◀ 10월 ▶)', stories: '지출 많은 계정 동그라미 (피드 테마)', stats: '이달 수입·지출 요약', opts: '보기 설정 (전체 기간·최근 것 위로)', list: '내역 목록' };
  const st = { lid: null, page: 'ledger', params: {}, history: [], prefs: {} };
  let N = null;
  let ui = {};

  // ── 기기별 설정 (자료 파일과 따로) ──
  const pref = k => (k in st.prefs ? st.prefs[k] : DEFAULTS[k]);
  const prefJson = (k, dflt) => { try { const v = JSON.parse(pref(k) || 'null'); return v === null ? dflt : v; } catch (_) { return dflt; } };
  function keyOrder(saved, all) {
    const out = [];
    for (const k of Array.isArray(saved) ? saved : []) if (all.includes(k) && !out.includes(k)) out.push(k);
    return out.concat(all.filter(k => !out.includes(k)));
  }
  const navOrder = () => keyOrder(prefJson('nav_order', []), Object.keys(NAV));
  const tabKeys = () => navOrder().slice(0, NAV_TABS).concat(['more']);
  const moreKeys = () => navOrder().slice(NAV_TABS);
  const navLabel = k => (k === 'more' ? MORE : NAV[k] || [k, 'b16']);
  const ledgerLayout = () => keyOrder(prefJson('ledger_layout', []), Object.keys(LAYOUT));
  function setPref(k, v) {
    if (v === null || v === undefined) delete st.prefs[k]; else st.prefs[k] = String(v);
    try { N.setPref(k, v === null || v === undefined ? null : String(v)); } catch (_) { /* 무시 */ }
  }
  // ── 테마 색 바꾸기: 테마마다 6가지 색 (나머지 색은 이 색들로 자동 계산) ──
  const COLOR_KEYS = [['accent', '포인트 (단추·강조)'], ['bg', '바탕'], ['card', '카드·창'], ['ink', '글자'], ['in', '수입 글자'], ['out', '지출 글자']];
  const BASE_COLORS = {
    retro: { accent: '#FF8FB1', bg: '#347C7C', card: '#FFFFFF', ink: '#1A1A1A', in: '#1F6FB2', out: '#D23F6E' },
    basic: { accent: '#347C7C', bg: '#EEF2F2', card: '#FFFFFF', ink: '#1A1A1A', in: '#1F6FB2', out: '#D23F6E' },
    feed: { accent: '#E0507A', bg: '#347C7C', card: '#FFFFFF', ink: '#1A1A1A', in: '#1F6FB2', out: '#D23F6E' },
    feed_light: { accent: '#E5487E', bg: '#FAFAFA', card: '#FFFFFF', ink: '#1F1F1F', in: '#2F6FDB', out: '#E0336A' },
    feed_dark: { accent: '#F0568C', bg: '#000000', card: '#000000', ink: '#F2F2F2', in: '#5B9BF5', out: '#F45C84' },
    timeline: { accent: '#347C7C', bg: '#347C7C', card: '#FFFFFF', ink: '#1A1A1A', in: '#1F6FB2', out: '#D23F6E' },
    timeline_light: { accent: '#1D8FE1', bg: '#FFFFFF', card: '#FFFFFF', ink: '#16191C', in: '#1D8FE1', out: '#E0336A' },
    timeline_dark: { accent: '#2A9BEA', bg: '#000000', card: '#000000', ink: '#E6E8EA', in: '#52AEF2', out: '#F45C84' },
  };
  const baseColors = t => Object.assign({}, BASE_COLORS[t || theme()]);
  function customColors(t) {
    const v = prefJson('colors_' + (t || theme()), {});
    const out = {};
    for (const [k] of COLOR_KEYS) { const h = UI.normHex(v && v[k]); if (h) out[k] = h; }
    return out;
  }
  function setCustomColor(k, hex, t) {
    t = t || theme();
    const cu = customColors(t);
    if (hex && UI.normHex(hex) && UI.normHex(hex) !== BASE_COLORS[t][k]) cu[k] = UI.normHex(hex); else delete cu[k];
    setPref('colors_' + t, Object.keys(cu).length ? JSON.stringify(cu) : null);
    applyTheme();
    updateHeader();
  }
  const rgb = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  const hex = a => '#' + a.map(x => Math.max(0, Math.min(255, Math.round(x))).toString(16).padStart(2, '0')).join('').toUpperCase();
  const mix = (a, b, t) => { const x = rgb(a), y = rgb(b); return hex(x.map((v, i) => v + (y[i] - v) * t)); };
  const lum = h => { const [r, g, b] = rgb(h).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const COLOR_VARS = ['--accent', '--accent-soft', '--bg', '--card', '--surface', '--surface-2', '--grid', '--sep', '--ink', '--muted', '--line',
    '--in', '--out', '--mint', '--mint-pale', '--mint-row', '--teal', '--teal-dark', '--pink', '--pink-dark', '--pink-pale', '--dash', '--ring', '--on-bg',
    '--page', '--on-top', '--on-top-2'];
  /** 고른 색을 화면 변수에 넣음 (고친 색이 없으면 테마 원래 색 그대로) */
  function applyColors(t) {
    const bs = document.body.style;
    COLOR_VARS.forEach(v => bs.removeProperty(v));
    const cu = customColors(t);
    if (!Object.keys(cu).length) return null;
    const c = Object.assign(baseColors(t), cu);
    const darkCard = lum(c.card) < 0.18;
    const surface = darkCard ? mix(c.card, c.ink, 0.06) : c.card;
    const set = (k, v) => bs.setProperty(k, v);
    set('--ink', c.ink); set('--in', c.in); set('--out', c.out);
    set('--card', c.card); set('--surface', surface);
    set('--surface-2', mix(c.card, c.ink, 0.045)); set('--mint-row', mix(c.card, c.ink, 0.045));
    set('--grid', mix(c.card, c.ink, 0.09)); set('--sep', mix(c.card, c.ink, 0.09));
    set('--muted', mix(c.ink, c.card, 0.45));
    set('--accent', c.accent); set('--accent-soft', mix(c.card, c.accent, 0.15));
    set('--bg', c.bg);
    set('--on-bg', lum(c.bg) < 0.4 ? '#FFFFFF' : '#1A1A1A');
    if (t === 'retro') {
      set('--teal', c.bg); set('--teal-dark', mix(c.bg, '#000000', 0.3));
      set('--pink', c.accent); set('--pink-dark', mix(c.accent, '#000000', 0.18)); set('--pink-pale', mix(c.card, c.accent, 0.18));
      set('--mint-pale', mix(c.card, c.bg, 0.1)); set('--mint', mix(c.card, c.bg, 0.3)); set('--dash', mix(c.card, c.bg, 0.6)); set('--line', mix(c.card, c.bg, 0.6));
    } else if (t === 'basic') {
      set('--teal', c.accent); set('--teal-dark', mix(c.accent, c.ink, 0.35));
      set('--mint-pale', mix(c.card, c.bg, 0.6)); set('--mint', mix(c.card, c.accent, 0.2)); set('--line', mix(c.card, c.ink, 0.15));
    } else {
      set('--teal-dark', c.ink); set('--mint-pale', c.card); set('--mint', mix(c.card, c.ink, 0.07));
      set('--line', mix(c.card, c.ink, 0.14)); set('--pink-pale', mix(c.card, c.out, 0.12));
      if (layoutOf(t) === 'feed') set('--ring', `linear-gradient(45deg, ${mix(c.accent, '#FFC861', 0.55)}, ${c.accent} 55%, ${mix(c.accent, '#8B5CF6', 0.55)})`);
      if (variantOf(t) === 'mh') {          // 미니홈피 색: 맨 위는 바탕색 그대로, 그 위 글자는 바탕에 맞춰
        const onTop = lum(c.bg) < 0.4 ? '#FFFFFF' : '#1A1A1A';
        set('--on-top', onTop); set('--on-top-2', mix(onTop, c.bg, 0.3));
        set('--page', layoutOf(t) === 'feed' ? mix(c.card, c.bg, 0.1) : c.card);
      }
    }
    return c;
  }

  // 테마: retro(미니홈피) · basic(기본) · 피드(사진 SNS 느낌)·타임라인(짧은 글 SNS 느낌) × 미니홈피 색/밝게/어둡게
  //   feed, timeline = 미니홈피 색 · feed_light, timeline_light = 흰 바탕 · feed_dark, timeline_dark = 검은 바탕 (PC판 theme.py 와 같은 이름)
  const THEMES = ['retro', 'basic', 'feed', 'feed_light', 'feed_dark', 'timeline', 'timeline_light', 'timeline_dark'];
  const theme = () => (THEMES.includes(pref('theme')) ? pref('theme') : 'retro');
  // 글자 크기: 1px 단위 (fontpx). 정하지 않았으면 예전 4단계(fontsize) 값 그대로
  const FS_MIN = 10, FS_MAX = 26;
  function fontPx() {
    const v = parseInt(pref('fontpx'), 10);
    if (v >= FS_MIN && v <= FS_MAX) return v;
    const sys = isSns() || pref('font') === 'system';
    return SIZES[sys ? 'system' : 'pixel'][pref('fontsize')] || (sys ? 15 : 14);
  }
  /** px 로 정하기 (null 이면 기본 크기로) */
  function setFontPx(px) {
    if (px === null) { setPref('fontpx', null); setPref('fontsize', null); } else setPref('fontpx', Math.max(FS_MIN, Math.min(FS_MAX, Math.round(px))));
    applyTheme();
  }
  const layoutOf = t => (/^feed/.test(t || '') ? 'feed' : /^timeline/.test(t || '') ? 'timeline' : null);
  const variantOf = t => (!layoutOf(t) ? null : /_light$/.test(t) ? 'light' : /_dark$/.test(t) ? 'dark' : 'mh');
  const isSns = () => !!layoutOf(theme());
  function applyTheme() {
    const t = theme(), sns = isSns();
    const cl = document.body.classList;
    cl.toggle('basic', t === 'basic');
    cl.toggle('sns', sns);
    cl.toggle('feed', layoutOf(t) === 'feed');
    cl.toggle('tl', layoutOf(t) === 'timeline');
    cl.toggle('dark', variantOf(t) === 'dark');
    cl.toggle('mh', variantOf(t) === 'mh');
    const sys = sns || pref('font') === 'system';        // SNS 테마는 휴대폰 기본 글꼴
    cl.toggle('sysfont', sys);
    document.body.style.setProperty('--fs', fontPx() + 'px');
    const title = document.querySelector('.hompy-title');
    if (title) title.textContent = t === 'retro' ? '☆ 우리집 가계부 ☆' : '우리집 가계부';
    const c = applyColors(t);
    // 상태 표시줄 색: 미니홈피·미니홈피 색 SNS 테마는 진한 바탕색, 밝게·어둡게는 맨 위 줄(카드) 색
    const v = variantOf(t);
    let bar = v === 'dark' ? '#000000' : (v === 'light' ? '#FFFFFF' : '#24595A');
    if (c && (t === 'retro' || v === 'mh')) bar = mix(c.bg, '#000000', 0.3);
    else if (c && sns) bar = c.card;
    try {
      if (N && N.setBars) N.setBars(bar, lum(bar) > 0.5);
    } catch (_) { /* 오래된 앱 껍데기면 무시 */ }
  }

  // ── 맨 위 머리 ──
  function renderShell() {
    const app = document.getElementById('app');
    app.innerHTML = `
      <div class="topbar">
        <div class="line1">
          <div class="minimi"><img alt=""></div>
          <div class="grow"><div class="hompy-title">☆ 우리집 가계부 ☆</div><div class="hompy-sub"></div></div>
          <select class="ledger-pick"></select>
        </div>
        <div class="todaybar"><span class="pill"></span></div>
        <div class="marquee"><span></span></div>
      </div>
      <div class="main"><div class="card-main">
        <div class="banner"><button class="back hidden">◀</button><img alt=""><div class="grow"><div class="t"></div><div class="s"></div></div><div class="tools"></div></div>
        <div class="content"></div>
      </div></div>
      <div class="navbar"></div>`;
    ui = {
      minimi: UI.$('.minimi img'), sub: UI.$('.hompy-sub'), ledger: UI.$('.ledger-pick'), pill: UI.$('.todaybar .pill'),
      marquee: UI.$('.marquee'), mqText: UI.$('.marquee span'), back: UI.$('.banner .back'), bImg: UI.$('.banner img'),
      bT: UI.$('.banner .t'), bS: UI.$('.banner .s'), tools: UI.$('.banner .tools'), content: UI.$('.content'),
    };
    drawNav();
    ui.back.onclick = () => back();
    ui.ledger.onchange = () => {
      const v = ui.ledger.value;
      if (v === '__new' || v === '__manage') {          // 목록 끝: 새 장부 만들기 / 장부 관리
        ui.ledger.value = String(st.lid);
        if (v === '__new') Pages.settings.newLedger(); else Pages.settings.ledgerSheet();
        return;
      }
      selectLedger(Number(v));
    };
    UI.$('.minimi').onclick = () => go('settings', { section: 'deco' });
  }

  function drawNav() {
    const nav = UI.$('.navbar');
    if (!nav) return;
    nav.innerHTML = tabKeys().map(k => { const [label, s] = navLabel(k); return `<button data-tab="${k}"><img src="${UI.sticker(s)}" alt="">${label}</button>`; }).join('');
    UI.on(nav, 'button', 'click', (e, b) => go(b.dataset.tab));
    UI.$$('.navbar button').forEach(b => b.classList.toggle('on', b.dataset.tab === tabOf(st.page)));
  }
  /** 메뉴 순서 바꾸기 창 */
  function navReorderSheet() {
    UI.reorder({ title: '메뉴 순서', hint: `위에서 ${NAV_TABS}개가 아래 탭에 나오고, 나머지는 '더보기' 화면에 이 순서대로 나옵니다.`,
      items: navOrder().map((k, i) => ({ key: k, label: NAV[k][0], sub: i < NAV_TABS ? '아래 탭' : '더보기' })),
      subFor: i => (i < NAV_TABS ? `아래 탭 ${i + 1}번째` : '더보기 화면'),
      onSave: keys => { setPref('nav_order', JSON.stringify(keys)); drawNav(); render(true); },
      onReset: () => { setPref('nav_order', null); drawNav(); render(true); } });
  }
  function layoutReorderSheet() {
    UI.reorder({ title: '가계부 화면 구성', hint: '가계부 화면에 나오는 덩어리의 위아래 순서입니다.',
      items: ledgerLayout().map(k => ({ key: k, label: LAYOUT[k] })),
      onSave: keys => { setPref('ledger_layout', JSON.stringify(keys)); render(true); },
      onReset: () => { setPref('ledger_layout', null); render(true); } });
  }

  function reloadLedgers() {
    const ls = L.ledgers();
    if (!ls.some(l => l.id === st.lid)) st.lid = L.firstLedgerId();
    ui.ledger.innerHTML = ls.map(l => `<option value="${l.id}"${l.id === st.lid ? ' selected' : ''}>${U.esc(l.name)}</option>`).join('') +
      '<option disabled>──────────</option><option value="__new">＋ 새 장부 만들기</option><option value="__manage">장부 관리…</option>';
  }
  const ledgerName = () => { const l = L.ledgers().find(x => x.id === st.lid); return l ? l.name : ''; };

  function updateHeader() {
    const t = U.today();
    const [y, m] = U.parts(t);
    const m0 = U.iso(y, m, 1), m1 = U.iso(y, m, U.monthEnd(y, m));
    const bal = L.currentBalance(st.lid, t);
    const [inc, exp] = L.totals(st.lid, m0, m1);
    const [, texp] = L.totals(st.lid, t, t);
    ui.minimi.src = UI.sticker(pref('minimi'));
    ui.sub.textContent = `오늘의 기분: ${pref('mood')}`;
    ui.pill.innerHTML = `<b class="t">TODAY</b> ${UI.money(texp)} <span class="muted">|</span> <b class="m">이달</b> ${UI.money(exp)} <span class="muted">|</span> 잔액 ${UI.money(bal)}`;
    const motto = (pref('motto') || '').replace(/\n/g, ' ') || '오늘도 알뜰살뜰 (^-^)v';
    ui.mqText.textContent = `♬ ${y}년 ${m}월 ${Number(t.slice(8))}일 ☆ ${ledgerName()} 잔액 ${UI.money(bal)}원 ☆ 이번 달 수입 ${UI.money(inc)}원 · 지출 ${UI.money(exp)}원 ☆ ${motto} ☆`;
    ui.marquee.classList.toggle('hidden', pref('marquee') !== 'true' || theme() !== 'retro');
    UI.$$('.navbar button').forEach(b => b.classList.toggle('on', b.dataset.tab === tabOf(st.page)));
  }
  const tabOf = page => (tabKeys().includes(page) ? page : 'more');

  // ── 화면 이동 ──
  function go(page, params, sub) {
    if (!Pages[page]) return;
    UI.$$('.fab').forEach(x => x.remove());
    if (sub) st.history.push({ page: st.page, params: st.params });
    else st.history = [];
    st.page = page;
    st.params = params || {};
    render();
  }
  function back() {
    const h = st.history.pop();
    if (!h) return false;
    st.page = h.page;
    st.params = h.params;
    render();
    return true;
  }
  function render(keepScroll) {
    const P = Pages[st.page];
    const top = keepScroll ? ui.content.scrollTop : 0;
    UI.$$('.fab').forEach(x => x.remove());
    ui.back.classList.toggle('hidden', !st.history.length);
    ui.bImg.src = UI.sticker(P.sticker || 'b16');
    ui.bT.textContent = typeof P.title === 'function' ? P.title(st.params) : P.title;
    ui.bS.textContent = P.sub || '';
    ui.tools.innerHTML = '';
    ui.content.innerHTML = '';
    updateHeader();
    try {
      P.render(ui.content, st.params, ui.tools);
    } catch (e) {
      let info = {};
      try { info = JSON.parse(N.appInfo()); } catch (_) { /* 없음 */ }
      if (info.dbOpen === false) { recovery(info.openError || e.message); return; }
      ui.content.innerHTML = `<div class="empty">화면을 그리는 중 문제가 생겼습니다.<br><span class="small">${U.esc(e.message)}</span></div>`;
      console.error(e);
    }
    ui.content.scrollTop = top;
  }
  /** 자료가 바뀌면 머리와 지금 화면을 다시 그림 (스크롤 위치 유지) */
  function dataChanged() { render(true); }
  function fab(onClick, label) {
    const b = UI.el(`<button class="fab" aria-label="${U.esc(label || '추가')}">＋</button>`);
    b.onclick = onClick;
    document.body.appendChild(b);
    return b;
  }

  function selectLedger(lid) {
    st.lid = lid;
    setPref('last_lid', lid);
    reloadLedgers();
    render();
    checkRecurring();
  }

  /** 안드로이드 뒤로 버튼: 창 → 하위 화면 → 가계부 탭 순서로 닫고, 더 닫을 게 없으면 false (앱 종료) */
  function onBack() {
    if (UI.closeTop()) return true;
    if (back()) return true;
    const home = tabKeys()[0];                // 첫 번째 탭이 처음 화면
    if (st.page !== home) { go(home); return true; }
    return false;
  }

  // ── 시작할 때 확인 (PC판과 같음) ──
  function checkRecurring() {
    const [due, later] = R.pending(st.lid);
    if (due.length) Pages.recurring.pendingSheet(due, later);
  }
  function checkReminders() {
    const rs = Cal.reminders();
    if (rs.length) UI.alert('다가오는 일정\n\n' + rs.slice(0, 20).map(r => `· ${r.date}  ${r.text}`).join('\n'));
  }

  // ── 암호 ──
  function login(stored) {
    return new Promise(resolve => {
      const app = document.getElementById('app');
      app.innerHTML = `<div class="login"><img src="${UI.sticker('a01')}" alt="">
        <div class="hompy-title">☆ 우리집 가계부 ☆</div><div class="small" style="margin-bottom:14px">암호를 입력하세요</div>
        <div class="dialog"><input class="inp" type="password" autocomplete="off" placeholder="암호">
          <div class="msg small out" style="margin:8px 0 10px;min-height:1.2em"></div>
          <div class="btns"><button class="btn" data-forgot>잊었어요</button><button class="btn pri" data-ok>들어가기</button></div></div></div>`;
      const inp = UI.$('.login input'), msg = UI.$('.login .msg');
      let tries = 0;
      const tryIt = () => {
        msg.textContent = '확인 중…';
        setTimeout(() => {
          if (Bk.checkPassword(inp.value, stored)) { resolve(); return; }
          tries++;
          msg.textContent = `암호가 틀렸습니다 (${tries}회). 다시 입력하세요.`;
          inp.select();
        }, 30);
      };
      UI.$('[data-ok]').onclick = tryIt;
      inp.addEventListener('keydown', e => { if (e.key === 'Enter') tryIt(); });
      UI.$('[data-forgot]').onclick = () => UI.alert('암호를 잊었을 때\n\n' +
        '· PC판에서 같은 자료의 암호를 지운 뒤 백업 파일로 다시 옮겨 오세요 (가져오기는 들어간 뒤 설정에서).\n' +
        '· 또는 휴대폰 설정 → 애플리케이션 → 우리집 가계부 → 저장공간 → 데이터 삭제 (모든 자료가 지워집니다).');
      setTimeout(() => inp.focus(), 200);
    });
  }

  function fatal(msg) {
    document.getElementById('app').innerHTML = `<div class="login"><img src="${UI.sticker('b21')}" alt=""><div class="dialog"><div class="msg">${U.esc(msg)}</div></div></div>`;
  }

  async function boot() {
    if (!Object.fromEntries || !Array.prototype.flatMap || !String.prototype.padStart) {
      fatal('휴대폰의 "Android System WebView"(또는 Chrome)가 너무 오래되었습니다.\n플레이 스토어에서 업데이트한 뒤 다시 여세요.');
      return;
    }
    N = window.GagyebuNative || (window.__devNative ? await window.__devNative : null);
    if (!N) { fatal('이 화면은 안드로이드 앱 안에서 열어야 합니다.'); return; }
    window.GagyebuNative = N;
    try { st.prefs = JSON.parse(N.getPrefs() || '{}'); } catch (_) { st.prefs = {}; }
    applyTheme();
    try { DB.open(N); } catch (e) { recovery('자료 파일을 열 수 없습니다.\n' + e.message); return; }
    let info = {};
    try { info = JSON.parse(N.appInfo()); } catch (_) { /* 없음 */ }
    try { N.autoBackup(7); } catch (_) { /* 보관 실패는 무시 */ }
    try { L.ensureDefaultLedgers(); } catch (_) { /* 장부 추가 실패는 무시 (자료는 그대로) */ }
    const pw = DB.getMeta('password');
    if (pw) await login(pw);
    start();
    if (info.corruptMoved) {
      setTimeout(() => UI.alert(`자료 파일이 손상되어 열 수 없었습니다.\n손상된 파일은 지우지 않고 앱 안에 따로 옮겨 두었습니다 (${info.corruptMoved}).\n\n설정 → 백업 · 복원 → '앱 안 보관본'에서 자동 보관본으로 되돌리거나, PC 백업 파일을 가져오세요.`), 600);
    }
  }

  /** 자료 파일을 못 열 때: 앱 안 보관본이나 PC 백업 파일로 되살리기 */
  function recovery(msg) {
    let items = [];
    try { items = (JSON.parse(N.listBackups()).items || []).filter(x => x.kind !== 'corrupt').sort((a, b) => b.mtime - a.mtime); } catch (_) { /* 없음 */ }
    document.getElementById('app').innerHTML = `<div class="login"><img src="${UI.sticker('b21')}" alt="">
      <div class="dialog"><div class="msg">${U.esc(msg)}</div>
      <div class="small" style="margin-bottom:8px">앱 안 보관본이나 PC 백업 파일로 되살릴 수 있습니다.</div>
      <div class="btns" style="flex-direction:column;align-items:stretch">${items.slice(0, 5).map((x, i) => `<button class="btn" data-i="${i}">${U.esc(x.name)} 로 되돌리기</button>`).join('')}
      <button class="btn pri" data-imp>PC 백업 파일 가져오기</button></div></div></div>`;
    UI.on(document, '[data-i]', 'click', (e, b) => {
      const x = items[Number(b.dataset.i)];
      const r = JSON.parse(N.restoreBackup(x.kind, x.name));
      if (r.ok) location.reload(); else UI.alert('되돌리지 못했습니다.\n' + r.error);
    });
    UI.$('[data-imp]').onclick = () => nativeAsync('importDb').then(r => {
      if (r.ok) location.reload(); else if (!r.cancel) UI.alert('가져오지 못했습니다.\n' + r.error);
    });
  }

  function start() {
    st.lid = Number(pref('last_lid')) || null;
    renderShell();
    applyTheme();
    reloadLedgers();
    go(tabKeys()[0]);
    setTimeout(() => { checkRecurring(); checkReminders(); }, 350);
    setTimeout(() => checkUpdate(false), 2500);       // 켤 때 새 버전 확인 (설정 → 업데이트에서 끌 수 있음)
  }

  // ── 새 버전 (GitHub 릴리스, 태그 android-v<버전>) — PC판 services/update.py 와 같은 규칙 ──
  // 켤 때 자동 확인(설정에서 끌 수 있음) → "업데이트하시겠습니까?" → 내려받기 → "지금 설치할까요?" → 안드로이드 설치 화면
  const UPD_PREFIX = 'android-v';
  const UPD_HINT = '설정 → 업데이트에서 언제든 직접 새 버전을 확인하고, 내려받아 설치할 수 있습니다.';
  const upd = { latest: null, busy: false, status: '', listeners: [] };
  const parseVer = s => { const m = /^v?(\d+)\.(\d+)(?:\.(\d+))?$/.exec(String(s || '').trim()); return m ? [+m[1], +m[2], +(m[3] || 0)] : null; };
  const verCmp = (a, b) => (a[0] - b[0]) || (a[1] - b[1]) || (a[2] - b[2]);
  const newerVer = (a, b) => { const x = parseVer(a), y = parseVer(b); return !!(x && y && verCmp(x, y) > 0); };
  /** 릴리스 설명에서 '## 업데이트 내용' 바로 아래 목록(- 로 시작하는 줄)만 */
  function notesOf(body, limit = 8) {
    const out = [];
    let on = false;
    for (const line of String(body || '').split(/\r?\n/)) {
      const t = line.trim();
      if (!on) { on = t.startsWith('#') && t.includes('업데이트 내용'); continue; }
      if ('-*·'.includes(t[0] || 'x')) out.push(t.replace(/^[-*·\s]+/, '').trim());
      else if (out.length || t) break;
    }
    return out.slice(0, limit);
  }
  const relOk = r => r && typeof r === 'object' && !r.draft && !r.prerelease && String(r.tag_name || '').startsWith(UPD_PREFIX) && parseVer(String(r.tag_name).slice(UPD_PREFIX.length));
  function pickLatest(list) {
    let best = null;
    for (const r of Array.isArray(list) ? list : []) {
      if (!relOk(r)) continue;
      const ver = String(r.tag_name).slice(UPD_PREFIX.length);
      if (best && verCmp(parseVer(ver), parseVer(best.version)) <= 0) continue;
      const name = `gagyebu-android-${ver}.apk`;
      const a = (r.assets || []).find(x => x.name === name);
      const dg = String((a && a.digest) || '');
      best = { version: ver, tag: r.tag_name, page: r.html_url || 'https://github.com/jpnjb0918-glitch/gageybu/releases', notes: notesOf(r.body),
        asset: a ? { name, url: a.browser_download_url || '', size: Number(a.size) || 0, sha256: dg.startsWith('sha256:') ? dg.slice(7).toLowerCase() : '' } : null };
    }
    return best;
  }
  /** 지금 판보다 새 릴리스들의 업데이트 내용 (오래된 것부터, 같은 줄은 한 번만) */
  function changesSince(list, cur, limit = 10) {
    const rows = (Array.isArray(list) ? list : []).filter(r => relOk(r) && newerVer(String(r.tag_name).slice(UPD_PREFIX.length), cur))
      .map(r => [parseVer(String(r.tag_name).slice(UPD_PREFIX.length)), notesOf(r.body, 20)]).sort((a, b) => verCmp(a[0], b[0]));
    const out = [];
    rows.forEach(([, ns]) => ns.forEach(n => { if (!out.includes(n)) out.push(n); }));
    return out.slice(-limit);
  }
  const appVersion = () => { try { return String(JSON.parse(N.appInfo()).version || ''); } catch (_) { return ''; } };
  const updAuto = () => pref('update_auto') !== 'false';
  function setUpdAuto(on) { setPref('update_auto', on ? null : 'false'); }
  function updStatus(s) { upd.status = s; upd.listeners.forEach(f => { try { f(); } catch (_) { /* 화면이 바뀜 */ } }); }
  function onUpd(f) { upd.listeners = [f]; }          // 설정 화면이 하나만 등록
  function updSummary(l) {
    const lines = (l.changes && l.changes.length ? l.changes : l.notes) || [];
    return `새 버전 ${l.version}이(가) 있습니다. (지금 ${appVersion()})\n\n업데이트 내용\n` +
      (lines.length ? lines.map(x => '· ' + x).join('\n') : '· (적힌 내용 없음 — 내려받기 페이지에서 볼 수 있어요)');
  }
  const yesNo = msg => UI.dialog(msg, [['아니요', '', false], ['예', 'pri', true]]);
  /** 새 버전 확인. manual=false(켤 때)는 설정에서 끈 경우 안 하고, 인터넷이 안 되거나 최신이면 조용히 끝냄 */
  async function checkUpdate(manual) {
    if (upd.busy || (!manual && !updAuto())) return;
    const cur = appVersion();
    if (!parseVer(cur)) { if (manual) UI.alert(`이 판(${cur || '?'})은 버전 번호가 없어 새 버전을 확인할 수 없습니다.`); return; }
    if (!manual && UI.isOpen()) { setTimeout(() => checkUpdate(false), 2000); return; }     // 예약 입력 창 등이 닫힌 뒤에
    upd.busy = true;
    updStatus('새 버전을 확인하는 중…');
    const r = await nativeAsync('fetchReleases');
    upd.busy = false;
    let list = null;
    if (r.ok) { try { list = JSON.parse(r.body); } catch (e) { r.ok = false; r.error = '릴리스 목록을 읽지 못했습니다'; } }
    if (!r.ok) {
      updStatus('확인하지 못했습니다: ' + r.error);
      if (manual) UI.alert(`새 버전을 확인하지 못했습니다.\n인터넷 연결을 확인해 주세요.\n\n(${r.error})`);
      return;
    }
    const l = pickLatest(list);
    if (!l || !newerVer(l.version, cur)) {
      upd.latest = null;
      updStatus(`지금 판(${cur})이 최신입니다.`);
      if (manual) UI.alert(`지금 판(${cur})이 최신입니다.`);
      return;
    }
    l.changes = changesSince(list, cur);
    upd.latest = l;
    updStatus(`새 버전 ${l.version}이(가) 있습니다.`);
    if (await yesNo(updSummary(l) + '\n\n업데이트하시겠습니까?')) downloadUpdate(l);
    else if (!manual) UI.alert(UPD_HINT);
  }
  function downloadUpdate(l) {
    if (!l || upd.busy) return;
    if (!l.asset) { UI.alert('이 릴리스에 APK 파일이 없습니다. 내려받기 페이지를 엽니다.'); N.openExternal(l.page); return; }
    upd.busy = true;
    updStatus('내려받는 중…');
    const sh = UI.sheet({ title: '새 버전 내려받기', body: `<div class="upd-dl"><div class="small">새 버전 ${U.esc(l.version)}을(를) 내려받는 중입니다.<br><span class="muted">휴대폰 알림 창에서도 볼 수 있어요.</span></div>
      <div class="upbar"><i></i></div><div class="small muted uppct">0%</div></div>` });
    window.__updProgress = (got, total) => {
      const pct = total > 0 ? Math.min(100, Math.floor(got * 100 / total)) : 0;
      const bar = UI.$('.upbar i', sh.el), txt = UI.$('.uppct', sh.el);
      if (bar) bar.style.width = pct + '%';
      if (txt) txt.textContent = total > 0 ? `${pct}%  (${(got / 1048576).toFixed(1)} / ${(total / 1048576).toFixed(1)} MB)` : `${(got / 1048576).toFixed(1)} MB`;
    };
    nativeAsync('downloadUpdate', l.asset.url, l.asset.name, String(l.asset.size || 0), l.asset.sha256 || '').then(r => {
      upd.busy = false;
      window.__updProgress = null;
      sh.close();
      if (!r.ok) { updStatus('내려받지 못했습니다: ' + r.error); UI.alert(`새 버전을 내려받지 못했습니다.\n\n(${r.error})`); return; }
      setPref('update_file', l.asset.name);
      setPref('update_file_ver', l.version);
      updStatus(`새 버전 ${l.version}을(를) 내려받았습니다. 설치를 기다리는 중입니다.`);
      askInstall(l.asset.name, l.version);
    });
  }
  async function askInstall(name, ver) {
    const yes = await yesNo(`새 버전 ${ver}을(를) 내려받았습니다.\n지금 설치할까요?\n\n안드로이드 설치 화면이 열립니다. 처음이면 '이 출처 허용'을 켜 달라는 화면이 먼저 나올 수 있어요. 가계부 자료는 그대로 남습니다.`);
    if (!yes) { UI.alert('설정 → 업데이트의 [내려받은 새 버전 설치]로 나중에 설치할 수 있습니다.'); return; }
    let r;
    try { r = JSON.parse(N.installUpdate(name)); } catch (e) { r = { ok: false, error: e.message }; }
    if (!r.ok) UI.alert('설치 화면을 열지 못했습니다.\n\n(' + r.error + ')');
  }
  /** 받아 두고 아직 설치하지 않은 새 버전 {name, ver} 또는 null */
  function downloadedUpdate() {
    const name = pref('update_file'), ver = pref('update_file_ver');
    let has = false;
    try { has = !!(name && N.hasUpdateFile && N.hasUpdateFile(name)); } catch (_) { has = false; }
    return has && newerVer(ver, appVersion()) ? { name, ver } : null;
  }
  const updState = () => ({ latest: upd.latest, busy: upd.busy, status: upd.status, auto: updAuto(), version: appVersion(), downloaded: downloadedUpdate() });

  /** 백업 파일로 자료를 통째로 바꾼 뒤 (DB 다시 열고 처음 화면으로) */
  function afterReplace() {
    DB.open(N);
    try { L.ensureDefaultLedgers(); } catch (_) { /* 무시 */ }
    st.lid = L.firstLedgerId();
    reloadLedgers();
    go('ledger');
    checkRecurring();
  }

  /** 안드로이드 쪽 비동기 작업(파일 선택 창) 결과 받기 */
  const waiting = {};
  let seq = 0;
  window.__nativeDone = (id, res) => { const f = waiting[id]; delete waiting[id]; if (f) f(res); };
  function nativeAsync(fnName, ...args) {
    return new Promise(resolve => {
      const id = 'cb' + (++seq);
      waiting[id] = resolve;
      N[fnName](...args, id);
    });
  }

  return {
    MOODS, NAV, LAYOUT, st, pref, layoutOf, variantOf, fontPx, setFontPx, FS_MIN, FS_MAX, checkUpdate, downloadUpdate, askInstall, updState, setUpdAuto, onUpd, setPref, prefJson, applyTheme, theme, isSns, go, back, navOrder, moreKeys, navLabel,
    ledgerLayout, drawNav, navReorderSheet, layoutReorderSheet, COLOR_KEYS, baseColors, customColors, setCustomColor, render, dataChanged, fab, onBack, boot, reloadLedgers,
    updateHeader, selectLedger, afterReplace, nativeAsync, checkRecurring, ledgerName,
    get lid() { return st.lid; },
    get native() { return N; },
  };
})();

window.App = App;
document.addEventListener('DOMContentLoaded', () => App.boot());
