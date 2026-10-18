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

  /** ◀ 2026년 10월 ▶ */
  function monthNav(y, m, onChange, labelFn) {
    const nav = el(`<div class="monthnav"><button data-d="-1">◀</button><div class="lbl"></div><button data-d="1">▶</button></div>`);
    const lbl = $('.lbl', nav);
    const show = () => { lbl.textContent = labelFn ? labelFn(y, m) : U.monthLabel(y, m); };
    show();
    on(nav, 'button', 'click', (e, b) => { [y, m] = U.addMonths(y, m, Number(b.dataset.d)); show(); onChange(y, m); });
    lbl.onclick = () => { const t = U.parts(U.today()); y = t[0]; m = t[1]; show(); onChange(y, m); };
    return nav;
  }
  function yearNav(y, onChange) {
    const nav = el(`<div class="monthnav"><button data-d="-1">◀</button><div class="lbl"></div><button data-d="1">▶</button></div>`);
    const lbl = $('.lbl', nav);
    const show = () => { lbl.textContent = `${y}년`; };
    show();
    on(nav, 'button', 'click', (e, b) => { y += Number(b.dataset.d); show(); onChange(y); });
    return nav;
  }
  function seg(items, current, onChange) {
    const s = el(`<div class="seg">${items.map(([k, label]) => `<button data-k="${k}" class="${k === current ? 'on' : ''}">${U.esc(label)}</button>`).join('')}</div>`);
    on(s, 'button', 'click', (e, b) => { $$('button', s).forEach(x => x.classList.toggle('on', x === b)); onChange(b.dataset.k); });
    return s;
  }
  const empty = (msg, st) => `<div class="empty"><img src="${sticker(st || 'b39')}" alt="">${U.esc(msg)}</div>`;

  return { $, $$, el, on, sticker, money, moneyCls, toast, sheet, closeTop, isOpen, alert: alertBox, confirm,
    formHtml, form, readForm, formSheet, bindMoney, codeOptions, monthNav, yearNav, seg, empty };
})();
