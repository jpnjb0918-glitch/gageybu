/* 화면 부품: 아래에서 올라오는 창, 알림, 확인 창, 입력 양식, 월 이동 막대 등 */
'use strict';
const UI = (() => {
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  function el(html) {
    const t = document.createElement('template');
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }
  /** root 안의 sel 요소마다 이벤트 연결 (fn(e, 요소)) */
  function on(root, sel, evt, fn) {
    $$(sel, root).forEach(x => x.addEventListener(evt, e => fn(e, x)));
  }
  const sticker = id => `img/stickers/${id}.png`;
  const money = (v, blankZero) => U.fmtMoney(v, blankZero);
  const moneyCls = v => (v < 0 ? 'neg' : '');

  // ── 알림 ──
  let toastTimer = null;
  function toast(msg, ms) {
    const old = $('.toast');
    if (old) old.remove();
    const t = el(`<div class="toast">${U.esc(msg)}</div>`);
    document.body.appendChild(t);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.remove(), ms || 1900);
  }

  // ── 겹쳐 뜨는 창 (뒤로 버튼으로 닫힘) ──
  const stack = [];
  function push(overlay, close) {
    document.body.appendChild(overlay);
    const item = { overlay, close };
    stack.push(item);
    return item;
  }
  function pop(item) {
    const i = stack.indexOf(item);
    if (i >= 0) stack.splice(i, 1);
    item.overlay.remove();
  }
  /** 맨 위 창 닫기. 닫았으면 true */
  function closeTop() {
    const top = stack[stack.length - 1];
    if (!top) return false;
    top.close();
    return true;
  }
  const isOpen = () => stack.length > 0;

  /** opts: {title, body(문자열|요소), buttons:[{label, cls, onClick(close) → false면 안 닫힘}], full, onClose} */
  function sheet(opts) {
    const ov = el(`<div class="overlay"><div class="sheet${opts.full ? ' full' : ''}">
      <div class="sh"><div class="t">${U.esc(opts.title || '')}</div><button class="iconbtn" data-x>✕</button></div>
      <div class="sb"></div><div class="sf"></div></div></div>`);
    const sb = $('.sb', ov), sf = $('.sf', ov);
    if (typeof opts.body === 'string') sb.innerHTML = opts.body; else if (opts.body) sb.appendChild(opts.body);
    let item = null, closed = false;
    function close() {
      if (closed) return;
      closed = true;
      pop(item);
      if (opts.onClose) opts.onClose();
    }
    (opts.buttons || []).forEach(b => {
      const btn = el(`<button class="btn ${b.cls || ''}">${U.esc(b.label)}</button>`);
      btn.onclick = () => {
        let r;
        try { r = b.onClick ? b.onClick(close, sb) : undefined; } catch (e) { alertBox(e.message); return; }
        if (r !== false) close();
      };
      sf.appendChild(btn);
    });
    if (!(opts.buttons || []).length) sf.remove();
    $('[data-x]', ov).onclick = close;
    ov.addEventListener('click', e => { if (e.target === ov) close(); });
    item = push(ov, close);
    return { el: ov, body: sb, close };
  }

  function dialog(msg, buttons) {
    return new Promise(resolve => {
      const ov = el(`<div class="overlay center"><div class="dialog"><div class="msg">${U.esc(msg)}</div><div class="btns"></div></div></div>`);
      let item = null;
      const finish = v => { pop(item); resolve(v); };
      buttons.forEach(([label, cls, v]) => {
        const b = el(`<button class="btn ${cls}">${U.esc(label)}</button>`);
        b.onclick = () => finish(v);
        $('.btns', ov).appendChild(b);
      });
      item = push(ov, () => finish(buttons.length > 1 ? false : true));
    });
  }
  const alertBox = msg => dialog(msg, [['확인', 'pri', true]]);
  const confirm = (msg, ok, danger) => dialog(msg, [['취소', '', false], [ok || '확인', danger ? 'danger' : 'pri', true]]);

  // ── 입력 양식 ──
  /** fields: [{k, label, type, req, options:[[값, 이름]], placeholder, hint, lid(code형식), mode}]
      type: text|password|money|int|date|month|select|textarea|check|code|tel|email */
  function formHtml(fields, values) {
    values = values || {};
    return '<div class="form">' + fields.map(f => {
      const v = values[f.k];
      const id = 'f_' + f.k.replace(/[^a-z0-9_]/gi, '_');
      const lab = `<label class="l" for="${id}">${U.esc(f.label)}${f.req ? ' <span class="req">*</span>' : ''}</label>`;
      const ph = f.placeholder ? ` placeholder="${U.esc(f.placeholder)}"` : '';
      const hint = f.hint ? `<div class="hint">${U.esc(f.hint)}</div>` : '';
      let inp;
      switch (f.type) {
        case 'money':
          inp = `<input id="${id}" data-k="${f.k}" type="text" inputmode="numeric" class="money" value="${v ? money(v) : ''}"${ph}>`;
          break;
        case 'int':
          inp = `<input id="${id}" data-k="${f.k}" type="number" inputmode="numeric" value="${v === null || v === undefined ? '' : U.esc(v)}"${ph}>`;
          break;
        case 'date': case 'month': case 'password': case 'tel': case 'email':
          inp = `<input id="${id}" data-k="${f.k}" type="${f.type}" value="${U.esc(v || '')}"${ph}>`;
          break;
        case 'textarea':
          inp = `<textarea id="${id}" data-k="${f.k}"${ph}>${U.esc(v || '')}</textarea>`;
          break;
        case 'check':
          return `<div class="f"><label class="check"><input id="${id}" data-k="${f.k}" type="checkbox"${v ? ' checked' : ''}> ${U.esc(f.label)}</label>${hint}</div>`;
        case 'select':
          inp = `<select id="${id}" data-k="${f.k}">${f.options.map(([ov, ol]) => `<option value="${U.esc(ov)}"${String(ov) === String(v === null || v === undefined ? '' : v) ? ' selected' : ''}>${U.esc(ol)}</option>`).join('')}</select>`;
          break;
        case 'code':
          inp = `<select id="${id}" data-k="${f.k}">${codeOptions(f.lid, v, f.mode, f.blank)}</select>`;
          break;
        default:
          inp = `<input id="${id}" data-k="${f.k}" type="text" value="${U.esc(v === null || v === undefined ? '' : v)}"${ph}>`;
      }
      return `<div class="f">${lab}${inp}${hint}</div>`;
    }).join('') + '</div>';
  }
  /** 금액 칸: 입력하는 대로 세 자리 쉼표 */
  function bindMoney(root) {
    $$('input.money', root).forEach(inp => {
      inp.addEventListener('input', () => {
        const neg = inp.value.trim().startsWith('-');
        const digits = inp.value.replace(/[^0-9]/g, '').replace(/^0+(?=\d)/, '');
        inp.value = (neg ? '-' : '') + (digits ? Number(digits).toLocaleString('en-US') : '');
      });
    });
  }
  function form(fields, values) {
    const f = el(formHtml(fields, values));
    bindMoney(f);
    return f;
  }
  /** 양식 값 읽기. 잘못된 칸이 있으면 Error(안내 문구) */
  function readForm(root, fields) {
    const out = {};
    for (const f of fields) {
      const x = $(`[data-k="${f.k}"]`, root);
      if (!x) continue;
      let v;
      if (f.type === 'check') v = x.checked;
      else if (f.type === 'money') {
        try { v = U.parseMoney(x.value); } catch (e) { throw new Error(`${f.label}: 금액은 숫자로 입력하세요.`); }
      } else if (f.type === 'int') {
        v = x.value.trim() === '' ? null : parseInt(x.value, 10);
        if (v !== null && isNaN(v)) throw new Error(`${f.label}: 숫자로 입력하세요.`);
      } else v = x.value.trim ? x.value.trim() : x.value;
      if (f.type === 'date' && v && !U.isValidIso(v)) throw new Error(`${f.label}: 날짜를 확인하세요.`);
      if (f.req && (v === '' || v === null || v === undefined)) throw new Error(`${f.label}을(를) 입력하세요.`);
      out[f.k] = v;
    }
    return out;
  }
  /** 양식 창: 저장을 누르면 onSave(values) (Error 를 던지면 안내하고 창 유지) */
  function formSheet(opts) {
    const body = form(opts.fields, opts.values);
    if (opts.extra) body.appendChild(typeof opts.extra === 'string' ? el(opts.extra) : opts.extra);
    const buttons = [];
    if (opts.onDelete) buttons.push({ label: opts.deleteLabel || '삭제', cls: 'danger', onClick: close => { opts.onDelete(close); return false; } });
    buttons.push({ label: opts.saveLabel || '저장', cls: 'pri', onClick: (close, sb) => {
      let v;
      try { v = readForm(sb, opts.fields); } catch (e) { toast(e.message); return false; }
      try { const r = opts.onSave(v, sb); if (r === false) return false; } catch (e) { alertBox(e.message); return false; }
      return undefined;
    } });
    const s = sheet({ title: opts.title, body, buttons, full: opts.full, onClose: opts.onClose });
    if (opts.afterOpen) opts.afterOpen(s.body);
    return s;
  }

  /** 계정과목 고르기 (대분류별 묶음). mode: 'in' 이면 수입 먼저, 'out' 이면 지출 먼저 */
  function codeOptions(lid, current, mode, blank) {
    const gs = L.groups(lid);
    const cats = L.categories(lid);
    let order = gs.slice();
    if (mode === 'out') order = gs.filter(g => g.code !== '0').concat(gs.filter(g => g.code === '0'));
    let html = blank ? `<option value="">${U.esc(blank)}</option>` : '';
    let found = !current;
    for (const g of order) {
      const cs = cats.filter(c => c.code.slice(0, 1) === g.code);
      if (!cs.length) continue;
      html += `<optgroup label="(${U.esc(g.code)}) ${U.esc(g.name)}">` + cs.map(c => {
        const sel = c.code === current;
        if (sel) found = true;
        return `<option value="${U.esc(c.code)}"${sel ? ' selected' : ''}>${U.esc(c.code)} ${U.esc(c.name)}</option>`;
      }).join('') + '</optgroup>';
    }
    if (!found) html = `<option value="${U.esc(current)}" selected>(미분류 ${U.esc(current)})</option>` + html;
    return html;
  }

  /** ◀ 2026년 10월 ▾ ▶ — 가운데 글자를 누르면 연·월을 바로 고르는 창 */
  /** 달 이동 단추 글자: 피드·타임라인은 선 아이콘, 그 밖은 ◀ ▶ */
  const arrows = () => (document.body.classList.contains('sns') ? [icon('chevl'), icon('chevr')] : ['◀', '▶']);
  function monthNav(y, m, onChange, labelFn) {
    const [pv, nx] = arrows();
    const nav = el(`<div class="monthnav"><button data-d="-1" aria-label="앞 달">${pv}</button><div class="lbl" role="button" aria-label="연·월 고르기"></div><button data-d="1" aria-label="다음 달">${nx}</button></div>`);
    const lbl = $('.lbl', nav);
    const show = () => { lbl.innerHTML = `${U.esc(labelFn ? labelFn(y, m) : U.monthLabel(y, m))}<span class="dd">▾</span>`; };
    show();
    on(nav, 'button', 'click', (e, b) => { [y, m] = U.addMonths(y, m, Number(b.dataset.d)); show(); onChange(y, m); });
    lbl.onclick = () => monthPicker({ y, m, onPick: (ny, nm) => { y = ny; m = nm; show(); onChange(y, m); } });
    return nav;
  }
  /** ◀ 2026년 ▾ ▶ */
  function yearNav(y, onChange) {
    const [pv, nx] = arrows();
    const nav = el(`<div class="monthnav"><button data-d="-1" aria-label="앞 해">${pv}</button><div class="lbl" role="button" aria-label="연도 고르기"></div><button data-d="1" aria-label="다음 해">${nx}</button></div>`);
    const lbl = $('.lbl', nav);
    const show = () => { lbl.innerHTML = `${y}년<span class="dd">▾</span>`; };
    show();
    on(nav, 'button', 'click', (e, b) => { y += Number(b.dataset.d); show(); onChange(y); });
    lbl.onclick = () => monthPicker({ y, yearOnly: true, onPick: ny => { y = ny; show(); onChange(y); } });
    return nav;
  }
  /** 연·월 고르기 창. opts: {y, m, yearOnly, onPick(y, m)}
      위: 연도 12개씩 (‹ › 로 12해씩 넘김), 아래: 1~12월. 달을 누르면 바로 그 달로 (연도만 고를 때는 연도를 누르면 바로) */
  function monthPicker(opts) {
    const MIN = 1900, MAX = 2100;
    const [ty, tm] = U.parts(U.today());
    let selY = opts.y, p0 = Math.max(MIN, Math.min(MAX - 11, opts.y - 5));
    const body = el(`<div class="mpick">
      <div class="mp-y"><button data-p="-1" aria-label="앞 12해">‹</button><b class="mp-range"></b><button data-p="1" aria-label="다음 12해">›</button></div>
      <div class="mp-grid mp-years"></div>
      ${opts.yearOnly ? '' : '<div class="small muted mp-sub"></div><div class="mp-grid mp-months"></div>'}</div>`);
    let sh = null;
    const pick = (yy, mm) => { sh.close(); opts.onPick(yy, mm); };
    function draw() {
      $('.mp-range', body).textContent = `${p0} ~ ${p0 + 11}년`;
      $('[data-p="-1"]', body).disabled = p0 <= MIN;
      $('[data-p="1"]', body).disabled = p0 + 11 >= MAX;
      $('.mp-years', body).innerHTML = Array.from({ length: 12 }, (_, i) => p0 + i).map(yy =>
        `<button data-y="${yy}" class="${yy === selY ? 'on' : ''}${yy === ty ? ' now' : ''}">${yy}</button>`).join('');
      if (opts.yearOnly) return;
      $('.mp-sub', body).textContent = `${selY}년의 몇 월로 갈까요?`;
      $('.mp-months', body).innerHTML = Array.from({ length: 12 }, (_, i) => i + 1).map(mm =>
        `<button data-m="${mm}" class="${selY === opts.y && mm === opts.m ? 'on' : ''}${selY === ty && mm === tm ? ' now' : ''}">${mm}월</button>`).join('');
    }
    body.addEventListener('click', e => {            // 격자는 다시 그리므로 위임으로
      const b = e.target.closest('button');
      if (!b || b.disabled) return;
      if (b.dataset.p) { p0 = Math.max(MIN, Math.min(MAX - 11, p0 + 12 * Number(b.dataset.p))); draw(); }
      else if (b.dataset.y) {
        const yy = Number(b.dataset.y);
        if (opts.yearOnly) { pick(yy); return; }
        selY = yy;
        draw();
      } else if (b.dataset.m) pick(selY, Number(b.dataset.m));
    });
    draw();
    sh = sheet({ title: opts.yearOnly ? '연도 고르기' : '연·월 고르기', body,
      buttons: [{ label: opts.yearOnly ? '올해' : '이번 달', onClick: close => { close(); opts.onPick(ty, tm); return false; } }] });
    return sh;
  }
  function seg(items, current, onChange) {
    const s = el(`<div class="seg">${items.map(([k, label]) => `<button data-k="${k}" class="${k === current ? 'on' : ''}">${U.esc(label)}</button>`).join('')}</div>`);
    on(s, 'button', 'click', (e, b) => { $$('button', s).forEach(x => x.classList.toggle('on', x === b)); onChange(b.dataset.k); });
    return s;
  }
  const empty = (msg, st) => `<div class="empty"><img src="${sticker(st || 'b39')}" alt="">${U.esc(msg)}</div>`;

  // ── 선 아이콘 (피드·타임라인 테마). class="f" 인 부분은 '켜짐'일 때 채움 ──
  const ICONS = {
    home: '<path class="f" d="M3.5 10.2 12 3.3l8.5 6.9V19.6a1.4 1.4 0 0 1-1.4 1.4H15v-6.2H9V21H4.9a1.4 1.4 0 0 1-1.4-1.4z"/>',
    search: '<circle cx="10.8" cy="10.8" r="7"/><path d="m20.5 20.5-4.7-4.7"/>',
    plus: '<rect x="3" y="3" width="18" height="18" rx="5.5"/><path d="M12 7.8v8.4M7.8 12h8.4"/>',
    add: '<path d="M12 4.5v15M4.5 12h15"/>',
    heart: '<path class="f" d="M12 20.2s-7.6-4.6-9.3-9.3C1.5 7.6 3.7 4.4 7 4.4c2 0 3.4 1.1 5 3 1.6-1.9 3-3 5-3 3.3 0 5.5 3.2 4.3 6.5-1.7 4.7-9.3 9.3-9.3 9.3z"/>',
    comment: '<path class="f" d="M20.6 11.6a8.6 8.6 0 0 1-12.4 7.7L3.4 20.6l1.4-4.6a8.6 8.6 0 1 1 15.8-4.4z"/>',
    send: '<path d="M21.3 2.7 10.2 13.8"/><path class="f" d="M21.3 2.7 14.2 21l-4-7.2-7.3-4z"/>',
    bookmark: '<path class="f" d="M6 3.2h12v17.6l-6-4.9-6 4.9z"/>',
    calendar: '<rect x="3.2" y="4.6" width="17.6" height="16.4" rx="3"/><path d="M3.2 9.6h17.6M8 2.6v4M16 2.6v4"/>',
    report: '<rect x="4.8" y="4" width="14.4" height="17" rx="2.6"/><path d="M9 4V2.8h6V4M8.6 10h6.8M8.6 13.8h6.8M8.6 17.6h4"/>',
    wallet: '<path d="M4.5 7.4H19a2 2 0 0 1 2 2V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6.4A2.4 2.4 0 0 1 5.4 4H16.6v3.4"/><circle cx="16.4" cy="14.2" r="1.3"/>',
    chart: '<path d="M3.5 20.5h17M7 17V11.5M12 17V6.5M17 17v-3.6"/>',
    repeat: '<path d="M4.5 8 7.5 5l3 3M7.5 5.6V15a3 3 0 0 0 3 3h3M19.5 16l-3 3-3-3M16.5 18.4V9a3 3 0 0 0-3-3h-3"/>',
    gift: '<rect x="3.4" y="8" width="17.2" height="4.4" rx="1"/><path d="M5 12.4V20a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-7.6M12 8v13M12 8S10.6 3.6 8.2 4.1 6.4 8 12 8zm0 0s1.4-4.4 3.8-3.9S17.6 8 12 8z"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/>',
    book: '<path d="M4 4.6A1.6 1.6 0 0 1 5.6 3H20v15H5.6A1.6 1.6 0 0 0 4 19.6zM4 19.6A1.6 1.6 0 0 0 5.6 21H20v-3"/>',
    note: '<path d="M5 3h10l4 4v14H5z"/><path d="M15 3v4h4M8.5 12h7M8.5 16h5"/>',
    gear: '<path d="M19.25 10.53 L21.52 10.76 L21.52 13.24 L19.25 13.47 L18.17 16.09 L19.61 17.85 L17.85 19.61 L16.09 18.17 L13.47 19.25 L13.24 21.52 L10.76 21.52 L10.53 19.25 L7.91 18.17 L6.15 19.61 L4.39 17.85 L5.83 16.09 L4.75 13.47 L2.48 13.24 L2.48 10.76 L4.75 10.53 L5.83 7.91 L4.39 6.15 L6.15 4.39 L7.91 5.83 L10.53 4.75 L10.76 2.48 L13.24 2.48 L13.47 4.75 L16.09 5.83 L17.85 4.39 L19.61 6.15 L18.17 7.91Z"/><circle cx="12" cy="12" r="3"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.4 9.3a2.7 2.7 0 0 1 5.2.9c0 1.8-2.6 2.3-2.6 3.9M12 17.3v.1"/>',
    dots: '<circle class="dot" cx="5" cy="12" r="1.5"/><circle class="dot" cx="12" cy="12" r="1.5"/><circle class="dot" cx="19" cy="12" r="1.5"/>',
    more: '<circle cx="12" cy="12" r="9"/><circle class="dot" cx="7.8" cy="12" r="1.2"/><circle class="dot" cx="12" cy="12" r="1.2"/><circle class="dot" cx="16.2" cy="12" r="1.2"/>',
    back: '<path d="M15 4.5 7.5 12l7.5 7.5"/>',
    arrowleft: '<path d="M20 12H4.5M10.5 5.5 4 12l6.5 6.5"/>',
    chevl: '<path d="M14.5 6 8.5 12l6 6"/>',
    chevr: '<path d="M9.5 6l6 6-6 6"/>',
    chevd: '<path d="m6 9.5 6 6 6-6"/>',
    sort: '<path d="M8 4v16M4.5 7.5 8 4l3.5 3.5M16 20V4M12.5 16.5 16 20l3.5-3.5"/>',
    download: '<path d="M12 3.5v11M7.5 10.5 12 15l4.5-4.5M4 17.5V20h16v-2.5"/>',
    sliders: '<path d="M4 7h10M18 7h2M4 17h4M12 17h8"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
    bell: '<path class="f" d="M6 16.4V11a6 6 0 1 1 12 0v5.4l1.6 2.1H4.4z"/><path d="M10 21h4"/>',
    pin: '<path d="M14.6 3.4 20.6 9.4l-2.5.9-3.7 3.7.4 4.4-2 2-3.6-3.6L4 21l3.2-5.2-3.6-3.6 2-2 4.4.4 3.7-3.7z"/>',
    stats: '<path d="M5 20.5V13M10 20.5V7M15 20.5v-9M20 20.5V4"/>',
    pen: '<path d="M4 20l1.1-4.2L16.3 4.6a2 2 0 0 1 2.8 0l.3.3a2 2 0 0 1 0 2.8L8.2 18.9z"/><path d="M14.5 6.4l3.1 3.1"/>',
    grid: '<rect x="3.5" y="3.5" width="17" height="17" rx="2.5"/><path d="M9.2 3.5v17M14.8 3.5v17M3.5 9.2h17M3.5 14.8h17"/>',
    all: '<path d="M7 9c-2.2 0-3.6 1.4-3.6 3S4.8 15 7 15c3.5 0 6.5-6 10-6 2.2 0 3.6 1.4 3.6 3S19.2 15 17 15c-3.5 0-6.5-6-10-6z"/>',
    upload: '<path d="M12 15V4M7.5 8.5 12 4l4.5 4.5M4 17.5V20h16v-2.5"/>',
    archive: '<rect x="3" y="4" width="18" height="5" rx="1.5"/><path d="M5 9v10a1.5 1.5 0 0 0 1.5 1.5h11A1.5 1.5 0 0 0 19 19V9M10 13h4"/>',
    lock: '<rect x="4.5" y="10.5" width="15" height="10" rx="2.5"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
    refresh: '<path d="M20 11a8 8 0 0 0-14.3-4.9L4 8M4 4v4h4M4 13a8 8 0 0 0 14.3 4.9L20 16M20 20v-4h-4"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.6v.1"/>',
    tag: '<path d="M3.5 12.2V4.5a1 1 0 0 1 1-1h7.7l8.3 8.3a1.5 1.5 0 0 1 0 2.1l-6.2 6.2a1.5 1.5 0 0 1-2.1 0z"/><circle class="dot" cx="8" cy="8" r="1.4"/>',
    print: '<path d="M7 8V3.5h10V8"/><rect x="3.5" y="8" width="17" height="9" rx="2.2"/><path d="M7 13.5h10v7H7z"/>',
    palette: '<path d="M12 3a9 9 0 1 0 0 18c1.2 0 1.8-.8 1.8-1.7 0-1.1-.9-1.6-.9-2.6 0-1 .8-1.7 1.8-1.7h2.1A4.2 4.2 0 0 0 21 10.8C21 6.5 17 3 12 3z"/><circle class="dot" cx="7.5" cy="11.5" r="1.3"/><circle class="dot" cx="10" cy="7.5" r="1.3"/><circle class="dot" cx="14.5" cy="7.5" r="1.3"/>',
    table: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M3.5 9.5h17M3.5 14.5h17M9.5 9.5v10"/>',
    list: '<path d="M8.5 6.5h12M8.5 12h12M8.5 17.5h12"/><circle class="dot" cx="4.5" cy="6.5" r="1.2"/><circle class="dot" cx="4.5" cy="12" r="1.2"/><circle class="dot" cx="4.5" cy="17.5" r="1.2"/>',
  };
  /** 아이콘 SVG 문자열 (name: ICONS 의 이름) */
  const icon = (name, cls) => `<svg class="ic${cls ? ' ' + cls : ''}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ICONS.dots}</svg>`;

  // ── 순서 바꾸기 창: ☰ 를 끌거나 ▲▼ 로 옮기고 저장 ──
  /** opts: {title, hint, items:[{key, label, sub}], subFor(i, key) (옮길 때마다 둘째 줄 다시 쓰기), onSave(keys), onReset(), resetLabel} */
  function reorder(opts) {
    const body = el(`<div>${opts.hint ? `<div class="small muted" style="margin-bottom:8px;white-space:pre-line">${U.esc(opts.hint)}</div>` : ''}<ul class="list reorder"></ul></div>`);
    const ul = $('ul', body);
    ul.innerHTML = opts.items.map(it => `<li data-key="${U.esc(String(it.key))}"><span class="grip" aria-label="끌어서 옮기기">☰</span>
      <div class="grow"><div class="main-t ellipsis">${U.esc(it.label)}</div>${it.sub ? `<div class="sub ellipsis">${U.esc(it.sub)}</div>` : ''}</div>
      <button class="iconbtn mv" data-mv="-1" aria-label="위로">▲</button><button class="iconbtn mv" data-mv="1" aria-label="아래로">▼</button></li>`).join('');
    const refresh = () => { if (opts.subFor) $$('li', ul).forEach((li, i) => { const sEl = $('.sub', li); if (sEl) sEl.textContent = opts.subFor(i, li.dataset.key); }); };
    const mark = li => { refresh(); li.classList.add('moved'); setTimeout(() => li.classList.remove('moved'), 350); };
    ul.addEventListener('click', e => {
      const b = e.target.closest('[data-mv]');
      if (!b) return;
      const li = b.closest('li');
      if (b.dataset.mv === '-1' && li.previousElementSibling) ul.insertBefore(li, li.previousElementSibling);
      else if (b.dataset.mv === '1' && li.nextElementSibling) ul.insertBefore(li.nextElementSibling, li);
      mark(li);
    });
    let drag = null;
    ul.addEventListener('pointerdown', e => {
      const g = e.target.closest('.grip');
      if (!g) return;
      e.preventDefault();
      drag = { li: g.closest('li'), id: e.pointerId };
      drag.li.classList.add('dragging');
      try { g.setPointerCapture(e.pointerId); } catch (_) { /* 무시 */ }
    });
    ul.addEventListener('pointermove', e => {
      if (!drag || e.pointerId !== drag.id) return;
      e.preventDefault();
      const y = e.clientY;
      const sc = ul.closest('.sb');
      if (sc) {
        const r = sc.getBoundingClientRect();
        if (y < r.top + 36) sc.scrollTop -= 14; else if (y > r.bottom - 36) sc.scrollTop += 14;
      }
      let before = null;
      for (const o of $$('li', ul)) {
        if (o === drag.li) continue;
        const r = o.getBoundingClientRect();
        if (y < r.top + r.height / 2) { before = o; break; }
      }
      if (before !== drag.li.nextElementSibling) ul.insertBefore(drag.li, before);
    });
    const end = e => {
      if (!drag || (e && e.pointerId !== drag.id)) return;
      drag.li.classList.remove('dragging');
      mark(drag.li);
      drag = null;
    };
    ul.addEventListener('pointerup', end);
    ul.addEventListener('pointercancel', end);
    const buttons = [];
    if (opts.onReset) buttons.push({ label: opts.resetLabel || '기본 순서로', onClick: () => { opts.onReset(); toast('기본 순서로 되돌렸습니다'); } });
    buttons.push({ label: '저장', cls: 'pri', onClick: () => { opts.onSave($$('li', ul).map(li => li.dataset.key)); toast('순서를 저장했습니다'); } });
    return sheet({ title: opts.title, body, buttons, full: opts.items.length > 8 });
  }

  // ── 색 고르기 창: 고른 색 견본 + 색상·채도·밝기 막대 + 직접 입력(#RRGGBB) ──
  const SWATCHES = ['#E5487E', '#FF8FB1', '#E0336A', '#F45C84', '#FF6B4A', '#F2994A', '#F2C94C', '#FFE066',
    '#27AE60', '#2E9E5B', '#6FCF97', '#139A9A', '#4BD5D5', '#347C7C', '#1D8FE1', '#2F6FDB',
    '#56CCF2', '#3B7DDD', '#9457D6', '#BB6BD9', '#8E44AD', '#66788F', '#8A8A8A', '#1F1F1F',
    '#000000', '#16191C', '#24595A', '#EEF2F2', '#F5F8FA', '#FAFAFA', '#FFF7EC', '#FFFFFF'];
  function hexToHsl(hex) {
    const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255);
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2;
    let h = 0, s = 0;
    if (mx !== mn) {
      const d = mx - mn;
      s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
      h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
      h *= 60;
    }
    return [Math.round(h), Math.round(s * 100), Math.round(l * 100)];
  }
  function hslToHex(h, s, l) {
    s /= 100; l /= 100;
    const k = n => (n + h / 30) % 12, a = s * Math.min(l, 1 - l);
    const f = n => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
    return '#' + [f(0), f(8), f(4)].map(x => Math.round(x * 255).toString(16).padStart(2, '0')).join('').toUpperCase();
  }
  const normHex = v => {
    let x = String(v || '').trim().replace(/^#?/, '#').toUpperCase();
    if (/^#[0-9A-F]{3}$/.test(x)) x = '#' + x.slice(1).split('').map(ch => ch + ch).join('');
    return /^#[0-9A-F]{6}$/.test(x) ? x : null;
  };
  /** opts: {title, value, original, onPick(hex), onReset()} */
  function colorPicker(opts) {
    let cur = normHex(opts.value) || '#000000';
    const body = el(`<div class="cpick">
      <div class="row" style="margin-bottom:10px"><div class="cp-prev"></div><div class="grow small">
        <div>지금 고른 색 <b class="cp-hex"></b></div><div class="muted">처음 색 ${U.esc(opts.original || '')} <span class="cp-orig"></span></div></div></div>
      <div class="cp-sw">${SWATCHES.map(c => `<button data-c="${c}" style="background:${c}" aria-label="${c}"></button>`).join('')}</div>
      <label class="small muted">색상</label><input type="range" min="0" max="359" data-h class="cp-h">
      <label class="small muted">채도</label><input type="range" min="0" max="100" data-s>
      <label class="small muted">밝기</label><input type="range" min="0" max="100" data-l>
      <div class="row" style="margin-top:8px"><label class="small muted">직접 입력</label><input class="inp grow" data-x type="text" maxlength="7" placeholder="#RRGGBB" autocapitalize="characters"></div>
    </div>`);
    const H = $('[data-h]', body), S = $('[data-s]', body), Lr = $('[data-l]', body), X = $('[data-x]', body);
    $('.cp-orig', body).style.background = opts.original || 'transparent';
    function show(fromSliders) {
      $('.cp-prev', body).style.background = cur;
      $('.cp-hex', body).textContent = cur;
      if (!fromSliders) { const [h, s, l] = hexToHsl(cur); H.value = h; S.value = s; Lr.value = l; }
      S.style.background = `linear-gradient(90deg, ${hslToHex(Number(H.value), 0, Number(Lr.value))}, ${hslToHex(Number(H.value), 100, Number(Lr.value))})`;
      Lr.style.background = `linear-gradient(90deg, #000, ${hslToHex(Number(H.value), Number(S.value), 50)}, #fff)`;
      if (document.activeElement !== X) X.value = cur;
      $$('.cp-sw button', body).forEach(b => b.classList.toggle('on', b.dataset.c === cur));
    }
    [H, S, Lr].forEach(r => r.addEventListener('input', () => { cur = hslToHex(Number(H.value), Number(S.value), Number(Lr.value)); show(true); }));
    X.addEventListener('input', () => { const v = normHex(X.value); if (v) { cur = v; show(); } });
    on(body, '.cp-sw button', 'click', (e, b) => { cur = b.dataset.c; show(); });
    show();
    const buttons = [];
    if (opts.onReset) buttons.push({ label: '처음 색', onClick: () => opts.onReset() });
    buttons.push({ label: '이 색으로', cls: 'pri', onClick: () => opts.onPick(cur) });
    return sheet({ title: opts.title, body, buttons });
  }

  /** 표 상자: <table> HTML → 머리줄·첫 칸이 붙어 있는 스크롤 상자. 옆으로 더 있으면 오른쪽 끝에 그늘 + '옆으로 밀어 보기' */
  function tableBox(tableHtml) {
    const box = el(`<div class="tbox"><div class="tbox-hint" hidden>← 옆으로 밀면 더 있어요 →</div><div class="tablewrap">${tableHtml}</div></div>`);
    const wrap = box.querySelector('.tablewrap'), hint = box.querySelector('.tbox-hint');
    const upd = () => {
      const wide = wrap.scrollWidth > wrap.clientWidth + 2;
      hint.hidden = !wide;
      box.classList.toggle('more', wide && wrap.scrollLeft + wrap.clientWidth < wrap.scrollWidth - 2);
    };
    wrap.addEventListener('scroll', upd, { passive: true });
    requestAnimationFrame(upd);
    box.update = upd;
    return box;
  }

  return { $, $$, el, on, sticker, money, moneyCls, toast, sheet, closeTop, isOpen, alert: alertBox, confirm, tableBox,
    formHtml, form, readForm, formSheet, bindMoney, codeOptions, monthNav, yearNav, monthPicker, seg, dialog, empty, reorder, colorPicker, icon, ICONS,
    normHex, hexToHsl, hslToHex };
})();
