/* 앱 틀: 시작·암호·화면 이동·맨 위 미니홈피 머리·아래 탭 */
'use strict';
const Pages = {};

const App = (() => {
  const MOODS = ['행복 (^-^)', '신남 (^0^)/', '알뜰 (-_-)b', '월급날 ♡(^_^)♡', '두근두근 (*^^*)',
    '텅장 (ㅠ_ㅠ)', '지름신 강림 (>_<)', '피곤 (-_-)zZ'];
  const DEFAULTS = { theme: 'retro', font: 'pixel', fontsize: 'm', marquee: 'true', minimi: 'b16', mood: MOODS[0], motto: '' };
  const SIZES = { pixel: { s: 13, m: 14, l: 16, xl: 18 }, system: { s: 14, m: 15, l: 17, xl: 19 } };
  const TABS = [['ledger', '가계부', 'a22'], ['calendar', '달력', 'b11'], ['report', '결산', 'b30'], ['assets', '자산', 'a04'], ['more', '더보기', 'a10']];
  const st = { lid: null, page: 'ledger', params: {}, history: [], prefs: {} };
  let N = null;
  let ui = {};

  // ── 기기별 설정 (자료 파일과 따로) ──
  const pref = k => (k in st.prefs ? st.prefs[k] : DEFAULTS[k]);
  function setPref(k, v) {
    if (v === null || v === undefined) delete st.prefs[k]; else st.prefs[k] = String(v);
    try { N.setPref(k, v === null || v === undefined ? null : String(v)); } catch (_) { /* 무시 */ }
  }
  function applyTheme() {
    document.body.classList.toggle('basic', pref('theme') === 'basic');
    document.body.classList.toggle('sysfont', pref('font') === 'system');
    const sz = SIZES[pref('font') === 'system' ? 'system' : 'pixel'][pref('fontsize')] || 14;
    document.body.style.setProperty('--fs', sz + 'px');
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
      <div class="navbar">${TABS.map(([k, label, s]) => `<button data-tab="${k}"><img src="${UI.sticker(s)}" alt="">${label}</button>`).join('')}</div>`;
    ui = {
      minimi: UI.$('.minimi img'), sub: UI.$('.hompy-sub'), ledger: UI.$('.ledger-pick'), pill: UI.$('.todaybar .pill'),
      marquee: UI.$('.marquee'), mqText: UI.$('.marquee span'), back: UI.$('.banner .back'), bImg: UI.$('.banner img'),
      bT: UI.$('.banner .t'), bS: UI.$('.banner .s'), tools: UI.$('.banner .tools'), content: UI.$('.content'),
    };
    UI.on(app, '.navbar button', 'click', (e, b) => go(b.dataset.tab));
    ui.back.onclick = () => back();
    ui.ledger.onchange = () => selectLedger(Number(ui.ledger.value));
    UI.$('.minimi').onclick = () => go('settings', { section: 'deco' });
  }

  function reloadLedgers() {
    const ls = L.ledgers();
    if (!ls.some(l => l.id === st.lid)) st.lid = L.firstLedgerId();
    ui.ledger.innerHTML = ls.map(l => `<option value="${l.id}"${l.id === st.lid ? ' selected' : ''}>${U.esc(l.name)}</option>`).join('');
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
    ui.marquee.classList.toggle('hidden', pref('marquee') !== 'true' || pref('theme') === 'basic');
    UI.$$('.navbar button').forEach(b => b.classList.toggle('on', b.dataset.tab === tabOf(st.page)));
  }
  const tabOf = page => (TABS.some(t => t[0] === page) ? page : (Pages[page] && Pages[page].tab) || 'more');

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
    if (st.page !== 'ledger') { go('ledger'); return true; }
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
    reloadLedgers();
    go('ledger');
    setTimeout(() => { checkRecurring(); checkReminders(); }, 350);
  }

  /** 백업 파일로 자료를 통째로 바꾼 뒤 (DB 다시 열고 처음 화면으로) */
  function afterReplace() {
    DB.open(N);
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
    MOODS, st, pref, setPref, applyTheme, go, back, render, dataChanged, fab, onBack, boot, reloadLedgers,
    updateHeader, selectLedger, afterReplace, nativeAsync, checkRecurring, ledgerName,
    get lid() { return st.lid; },
    get native() { return N; },
  };
})();

window.App = App;
document.addEventListener('DOMContentLoaded', () => App.boot());
