/* 자산관리: 통장·카드·증권·보험·부동산/기타 */
'use strict';
const AssetForm = (() => {
  /** PC판 FormDialog 형식 → 화면 양식 */
  function fields(defs) {
    return defs.map(([k, label, kind]) => {
      const f = { k, label };
      if (kind === 'text*') { f.type = 'text'; f.req = true; }
      else if (kind.startsWith('choice:')) {
        const items = kind.slice(7).split('|');
        f.type = 'select';
        f.options = k === 'x.ptype' ? items.map((x, i) => [String(i), x]) : [['', '']].concat(items.map(x => [x, x]));
      } else if (kind === 'active') { f.type = 'select'; f.options = [['1', '사용중 (자산으로 계산)'], ['0', '사용안함 (자산 계산 안 함)']]; }
      else if (kind === 'billmonth') { f.type = 'select'; f.options = [['-2', '전전월'], ['-1', '전월'], ['0', '당월']]; }
      else if (kind === 'bank') {
        f.type = 'select';
        f.options = [['', '(없음)']].concat(A.accounts('bank').map(a => [String(a.id), `${a.company} ${a.name}`.trim()]));
      } else if (kind === 'memo') f.type = 'textarea';
      else f.type = kind;               // text/money/date/int/password
      f.kind = kind;
      return f;
    });
  }
  function toForm(row, defs) {
    const v = row ? A.mergeExtra(row) : {};
    for (const [k, , kind] of defs) {
      if (kind === 'active') v[k] = String(v[k] === undefined || v[k] === null ? 1 : v[k]);
      else if (kind === 'billmonth') v[k] = String(v[k] === undefined || v[k] === null ? -1 : v[k]);
      else if (kind === 'bank') v[k] = v[k] ? String(v[k]) : '';
      else if (k === 'x.ptype') v[k] = String(v[k] || 0);
    }
    return v;
  }
  function fromForm(v, defs) {
    const out = {};
    for (const [k, , kind] of defs) {
      let x = v[k];
      if (kind === 'active' || kind === 'billmonth' || k === 'x.ptype') x = Number(x);
      else if (kind === 'bank') x = x ? Number(x) : null;
      else if (kind === 'date') x = x || null;
      else if (kind === 'int') x = x === null || x === undefined ? 0 : x;
      else if (kind === 'money') x = x || 0;
      out[k] = x;
    }
    return out;
  }
  return { fields, toForm, fromForm };
})();

Pages.assets = (() => {
  const s = { tab: 'bank' };
  const TABS = [['bank', '통장'], ['card', '카드'], ['securities', '증권'], ['insurance', '보험'], ['property', '부동산·기타']];

  function render(c) {
    const sm = A.summary();
    c.appendChild(UI.el(`<div class="box">
      <div class="kv"><span>자산 합계</span><b class="in">${UI.money(sm.자산합계)}</b></div>
      <div class="kv small muted"><span>예금 ${UI.money(sm.예금)} · 증권 ${UI.money(sm.증권)} · 부동산 ${UI.money(sm.부동산)} · 기타 ${UI.money(sm.기타)}</span></div>
      <div class="kv"><span>부채 합계</span><b class="out">${UI.money(sm.부채합계)}</b></div>
      <div class="kv small muted"><span>대출 ${UI.money(sm.대출)} · 카드 미결제 ${UI.money(sm.카드)} · 기타부채 ${UI.money(sm.기타부채)}${sm.갚을돈 ? ` · 갚을 돈 ${UI.money(sm.갚을돈)}` : ''}</span></div>
      ${sm.받을돈 ? `<div class="kv small muted"><span>받을 돈 ${UI.money(sm.받을돈)} (자산에 들어감)</span></div>` : ''}
      <div class="kv" style="border-top:1px dashed var(--line);margin-top:4px;padding-top:4px"><span class="bold">순자산</span><b class="${UI.moneyCls(sm.순자산)}">${UI.money(sm.순자산)}원</b></div></div>`));
    // 1.7.0: 저축 목표 · 빌려준 돈/빌린 돈 · 통장끼리 이체
    const more = UI.el(`<div class="row wrap amore"><button class="btn sm" data-go="goals">${UI.icon('target')}저축 목표</button>
      <button class="btn sm" data-go="debts">${UI.icon('user')}빌려준·빌린 돈</button><button class="btn sm" data-tr>${UI.icon('swap')}통장끼리 이체</button></div>`);
    UI.on(more, '[data-go]', 'click', (e, b) => App.go(b.dataset.go, {}, true));
    UI.$('[data-tr]', more).onclick = () => Extra.transferSheet(null);
    c.appendChild(more);
    c.appendChild(UI.seg(TABS, s.tab, k => { s.tab = k; App.render(true); }));
    if (s.tab === 'card') renderCards(c); else renderAccounts(c, s.tab);
  }

  function renderAccounts(c, kind) {
    const list = A.accounts(kind);
    const note = { bank: '사용중인 통장의 잔액(초기 잔액 + 입금 − 출금)이 자산으로 계산됩니다.', securities: '평가금액이 자산으로 계산됩니다.',
      insurance: '보험은 자산 합계에 넣지 않고 정보만 보관합니다.', property: '취득/평가금액은 자산, 대출금액은 부채로 계산됩니다 (구분이 기타자산이면 기타·기타부채).' }[kind];
    c.appendChild(UI.el(`<div class="small muted" style="margin-bottom:6px">${note}</div>`));
    if (!list.length) c.appendChild(UI.el(UI.empty({ bank: '등록한 통장이 없어요', securities: '등록한 증권 계좌가 없어요', insurance: '등록한 보험이 없어요', property: '등록한 부동산·기타 자산이 없어요' }[kind] + '\n＋ 버튼으로 추가하세요', 'a04')));
    else {
      c.appendChild(UI.el(`<ul class="list">${list.map(a => {
        const x = A.parseExtra(a.extra);
        let right = '', sub = [a.company, a.number, a.owner].filter(Boolean).map(U.esc).join(' · ');
        if (kind === 'bank') right = `<div class="bold ${UI.moneyCls(A.accountBalance(a.id))}">${UI.money(A.accountBalance(a.id))}</div>${a.active ? '' : '<div class="tiny muted">사용안함</div>'}`;
        else if (kind === 'securities') right = `<div class="bold">${UI.money(a.valuation)}</div><div class="tiny muted">평가금액</div>`;
        else if (kind === 'insurance') right = `<div class="small">${U.esc(x.status || '')}</div><div class="tiny muted">${U.esc(x.pay_method || '')}</div>`;
        else { right = `<div class="bold">${UI.money(a.valuation)}</div>${a.loan ? `<div class="tiny out">대출 ${UI.money(a.loan)}</div>` : ''}`; sub = [A.PROPERTY_TYPES[Number(x.ptype || 0)], a.owner].filter(Boolean).map(U.esc).join(' · '); }
        return `<li class="tap${kind === 'bank' && !a.active ? ' muted' : ''}" data-id="${a.id}"><div class="grow"><div class="main-t ellipsis">${U.esc(a.name)}</div><div class="sub ellipsis">${sub}</div></div><div class="right nowrap">${right}</div></li>`;
      }).join('')}</ul>`));
      UI.on(c, 'li[data-id]', 'click', (e, li) => App.go('account', { id: Number(li.dataset.id) }, true));
    }
    App.fab(() => editAccount(kind, null), '추가');
  }

  function editAccount(kind, a, after) {
    const defs = A.FIELDS[kind];
    UI.formSheet({ title: `${A.KIND_LABEL[kind]} ${a ? '수정' : '추가'}`, fields: AssetForm.fields(defs), values: AssetForm.toForm(a, defs), full: true,
      extra: a ? '<div class="row" style="margin-top:6px"><button class="btn sm" data-up>목록에서 위로</button><button class="btn sm" data-dn>아래로</button></div>' : '',
      afterOpen: sb => {
        if (!a) return;
        UI.$('[data-up]', sb).onclick = () => { A.move('account', a.id, -1, 'kind=?', [kind]); UI.toast('순서를 바꿨습니다'); };
        UI.$('[data-dn]', sb).onclick = () => { A.move('account', a.id, 1, 'kind=?', [kind]); UI.toast('순서를 바꿨습니다'); };
      },
      onSave: v => { A.saveAccount(kind, AssetForm.fromForm(v, defs), a ? a.id : null); App.dataChanged(); if (after) after(); },
      onDelete: a ? close => UI.confirm(`'${a.name}'과(와) 그 거래 내역을 모두 삭제할까요?\n(장부에 같이 저장한 내역은 남습니다)`, '삭제', true).then(ok => {
        if (ok) { A.deleteAccount(a.id); close(); App.back(); App.dataChanged(); }
      }) : null });
  }

  // ── 신용카드 목록 ──
  function renderCards(c) {
    const list = A.cards();
    c.appendChild(UI.el('<div class="small muted" style="margin-bottom:6px">아직 결제하지 않은 카드 사용액은 부채로 계산됩니다. 할부는 회차별로 나눠 저장합니다.</div>'));
    if (!list.length) c.appendChild(UI.el(UI.empty('등록한 카드가 없어요', 'a04')));
    else {
      c.appendChild(UI.el(`<ul class="list">${list.map(k => `<li class="tap" data-id="${k.id}"><div class="grow"><div class="main-t ellipsis">${U.esc(k.name)}</div>
        <div class="sub ellipsis">${[k.company, k.number].filter(Boolean).map(U.esc).join(' · ')} · 매월 ${k.pay_day}일 결제</div></div>
        <div class="right nowrap"><div class="bold out">${UI.money(A.cardUnpaidTotal(k.id))}</div><div class="tiny muted">미결제</div></div></li>`).join('')}</ul>`));
      UI.on(c, 'li[data-id]', 'click', (e, li) => App.go('card', { id: Number(li.dataset.id) }, true));
    }
    App.fab(() => editCard(null), '카드 추가');
  }
  function editCard(k, after) {
    const defs = A.CARD_FIELDS;
    const vals = AssetForm.toForm(k, defs);
    if (!k) Object.assign(vals, { pay_day: 25, bill_from_month: '-1', bill_from_day: 1, bill_to_month: '-1', bill_to_day: 31 });
    UI.formSheet({ title: k ? '카드 수정' : '카드 추가', fields: AssetForm.fields(defs), values: vals, full: true,
      extra: '<div class="small muted">청구기간 예: 결제일 25일 · 전월 1일 ~ 전월 31일 = 지난달 한 달 사용분을 이번 달 25일에 결제</div>',
      onSave: v => {
        const o = AssetForm.fromForm(v, defs);
        for (const [key, lo, hi, dflt] of [['pay_day', 1, 31, 1], ['bill_from_day', 1, 31, 1], ['bill_to_day', 1, 31, 31]]) {
          if (!o[key]) o[key] = dflt;
          if (o[key] < lo || o[key] > hi) throw new Error('날짜(일)는 1~31 사이로 입력하세요.');
        }
        A.saveCard(o, k ? k.id : null);
        App.dataChanged();
        if (after) after();
      },
      onDelete: k ? close => UI.confirm(`카드 '${k.name}'과(와) 사용 내역을 모두 삭제할까요?`, '삭제', true).then(ok => {
        if (ok) { A.deleteCard(k.id); close(); App.back(); App.dataChanged(); }
      }) : null });
  }
  return { title: '자산관리', sticker: 'a04', sub: '통장·카드·내 재산 한눈에', render, editAccount, editCard, state: s };
})();

// ════════ 통장(계좌) 하나 ════════
Pages.account = (() => {
  function render(c, p, tools) {
    const a = DB.one('SELECT * FROM account WHERE id=?', [p.id]);
    if (!a) { c.appendChild(UI.el(UI.empty('삭제된 항목입니다'))); return; }
    const x = A.parseExtra(a.extra);
    const edit = UI.el('<button class="btn sm">정보 수정</button>');
    edit.onclick = () => Pages.assets.editAccount(a.kind, a);
    tools.appendChild(edit);
    if (a.kind === 'bank') {
      const tr = UI.el(`<button class="btn sm">이체</button>`);
      tr.onclick = () => Extra.transferSheet(a.id);
      tools.appendChild(tr);
    }
    const bal = A.accountBalance(a.id);
    const info = AssetFormInfo(a, x);
    c.appendChild(UI.el(`<div class="box"><div class="kv"><b>${U.esc(a.name)}</b><span class="muted small">${U.esc(A.KIND_LABEL[a.kind])}</span></div>${info}
      ${a.kind === 'bank' ? `<div class="kv" style="margin-top:4px"><span>현재 잔액</span><b class="${UI.moneyCls(bal)}">${UI.money(bal)}원</b></div>` : ''}</div>`));
    const txs = A.accountTxs(a.id).reverse();
    c.appendChild(UI.el(`<div class="section-t">거래 내역 (${txs.length}건)</div>`));
    if (!txs.length) c.appendChild(UI.el(UI.empty('거래 내역이 없어요', 'a04')));
    else {
      c.appendChild(UI.el(`<ul class="list">${txs.map(([t, b]) => `<li class="tap" data-t="${t.id}"><div class="grow"><div class="main-t ellipsis"><span class="muted small">${t.date}</span> ${U.esc(t.summary)}</div>
        <div class="sub ellipsis">${U.esc(t.memo || '')}${t.entry_id ? ' · 장부에도 저장됨' : ''}${t.link_id ? ' · 이체 (짝 거래와 함께 바뀜)' : ''}</div></div>
        <div class="right nowrap">${t.deposit ? `<div class="in bold">+${UI.money(t.deposit)}</div>` : ''}${t.withdraw ? `<div class="out bold">-${UI.money(t.withdraw)}</div>` : ''}
        <div class="tiny muted">${a.kind === 'bank' ? '잔액' : '누계'} ${UI.money(b)}</div></div></li>`).join('')}</ul>`));
      UI.on(c, 'li[data-t]', 'click', (e, li) => txSheet(a, txs.find(([t]) => t.id === Number(li.dataset.t))[0]));
    }
    App.fab(() => txSheet(a, null), '거래 추가');
  }
  function AssetFormInfo(a, x) {
    const defs = A.FIELDS[a.kind];
    const v = A.mergeExtra(a);
    return defs.filter(([k, , kind]) => !['name', 'memo'].includes(k) && kind !== 'password').map(([k, label, kind]) => {
      let val = v[k];
      if (val === null || val === undefined || val === '') return '';
      if (kind === 'money') val = UI.money(val);
      else if (kind === 'active') val = val ? '사용중' : '사용안함';
      else if (k === 'x.ptype') val = A.PROPERTY_TYPES[Number(val)] || '';
      if (kind === 'money' && !v[k]) return '';
      return `<div class="kv small"><span class="muted">${U.esc(label)}</span><span>${U.esc(val)}</span></div>`;
    }).join('') + (a.memo ? `<div class="small" style="margin-top:4px;white-space:pre-wrap">${U.esc(a.memo)}</div>` : '');
  }
  function txSheet(a, t) {
    const lid = App.lid;
    const fields = [{ k: 'date', label: '거래일자', type: 'date', req: true }, { k: 'summary', label: '적요', type: 'text' },
      { k: 'deposit', label: '입금액', type: 'money' }, { k: 'withdraw', label: '출금액', type: 'money' }, { k: 'memo', label: '메모', type: 'text' }];
    if (!t) {
      fields.push({ k: 'to_ledger', label: `장부(${App.ledgerName()})에도 같이 저장 (입금→수입, 출금→지출)`, type: 'check' });
      fields.push({ k: 'code', label: '장부 계정과목', type: 'code', lid, mode: 'out' });
    }
    UI.formSheet({ title: t ? '거래 수정' : '거래 추가', fields, values: t || { date: U.today() }, full: true,
      afterOpen: sb => {
        const chk = UI.$('[data-k=to_ledger]', sb);
        if (!chk) return;
        const box = UI.$('[data-k=code]', sb).closest('.f');
        const sync = () => box.classList.toggle('hidden', !chk.checked);
        chk.onchange = sync;
        sync();
      },
      onSave: v => {
        if (!v.deposit && !v.withdraw) throw new Error('입금액 또는 출금액을 입력하세요.');
        if (t) A.updateTx(t.id, v);
        else {
          if (v.to_ledger && !v.code) throw new Error('장부 계정과목을 고르세요.');
          A.addTx(a.id, v, v.to_ledger ? lid : null, v.to_ledger ? v.code : null);
        }
        App.dataChanged();
      },
      onDelete: t ? close => {
        const go = withEntry => { A.deleteTx(t.id, withEntry); close(); App.dataChanged(); };
        if (t.entry_id) {
          UI.sheet({ title: '거래 삭제', body: '<div>이 거래는 장부에도 저장되어 있습니다. 장부 내역도 같이 지울까요?</div>', buttons: [
            { label: '거래만 삭제', onClick: () => go(false) }, { label: '장부 내역도 삭제', cls: 'danger', onClick: () => go(true) }] });
        } else UI.confirm('이 거래를 삭제할까요?', '삭제', true).then(ok => { if (ok) go(false); });
      } : null });
  }
  return { title: p => { const a = p && DB.one('SELECT name FROM account WHERE id=?', [p.id]); return a ? a.name : '계좌'; },
    sticker: 'a04', sub: '거래 내역', render, tab: 'assets' };
})();

// ════════ 카드 하나 ════════
Pages.card = (() => {
  const s = { ym: null, cid: null, sel: new Set() };
  function render(c, p, tools) {
    const k = DB.one('SELECT * FROM card WHERE id=?', [p.id]);
    if (!k) { c.appendChild(UI.el(UI.empty('삭제된 카드입니다'))); return; }
    if (s.cid !== k.id) { s.cid = k.id; s.ym = null; s.sel.clear(); }
    if (!s.ym) {
      const nxt = DB.val('SELECT MIN(substr(pay_date,1,7)) AS v FROM card_tx WHERE card_id=? AND paid=0', [k.id]);
      s.ym = nxt || U.today().slice(0, 7);
    }
    const edit = UI.el('<button class="btn sm">카드 정보</button>');
    edit.onclick = () => Pages.assets.editCard(k);
    tools.appendChild(edit);
    const [y, m] = U.parts(s.ym + '-01');
    c.appendChild(UI.el(`<div class="box small"><div class="kv"><b>${U.esc(k.name)}</b><span>${U.esc(k.company)}</span></div>
      <div class="kv"><span class="muted">결제일</span><span>매월 ${k.pay_day}일</span></div>
      <div class="kv"><span class="muted">청구기간</span><span>${A.BILL_MONTHS[String(k.bill_from_month)]} ${k.bill_from_day}일 ~ ${A.BILL_MONTHS[String(k.bill_to_month)]} ${k.bill_to_day}일</span></div>
      <div class="kv"><span class="muted">전체 미결제</span><b class="out">${UI.money(A.cardUnpaidTotal(k.id))}원</b></div></div>`));
    c.appendChild(UI.monthNav(y, m, (yy, mm) => { s.ym = U.ym(yy, mm); s.sel.clear(); App.render(true); }, (yy, mm) => `${yy}년 ${mm}월 결제분`));
    const rows = A.cardTxs(k.id, s.ym);
    const tot = U.sum(rows.map(r => r.amount + r.fee)), unpaid = U.sum(rows.filter(r => !r.paid).map(r => r.amount + r.fee));
    c.appendChild(UI.el(`<div class="kv small" style="margin-bottom:4px"><span>이달 결제 금액 ${UI.money(tot)}</span><span class="out">미결제 ${UI.money(unpaid)}</span></div>`));
    if (!rows.length) c.appendChild(UI.el(UI.empty('이 달에 결제할 사용 내역이 없어요', 'a04')));
    else {
      c.appendChild(UI.el(`<ul class="list">${rows.map(r => `<li data-t="${r.id}"><input type="checkbox" data-c="${r.id}" style="width:22px;height:22px"${s.sel.has(r.id) ? ' checked' : ''}>
        <div class="grow tap" data-open="${r.id}"><div class="main-t ellipsis">${U.esc(r.summary)}${r.months > 1 ? ` <span class="chip">${r.seq}/${r.months}회</span>` : ''}</div>
        <div class="sub">사용 ${r.date} · 결제 ${r.pay_date}${r.fee ? ` · 수수료 ${UI.money(r.fee)}` : ''}</div></div>
        <div class="right nowrap"><div class="bold">${UI.money(r.amount + r.fee)}</div><div class="tiny ${r.paid ? 'in' : 'out'}">${r.paid ? '결제완료' : '미결제'}</div></div></li>`).join('')}</ul>`));
      UI.on(c, 'input[data-c]', 'change', (e, x) => { const id = Number(x.dataset.c); if (x.checked) s.sel.add(id); else s.sel.delete(id); });
      UI.on(c, '[data-open]', 'click', (e, x) => groupSheet(k, rows.find(r => r.id === Number(x.dataset.open))));
      const bar = UI.el(`<div class="row wrap" style="margin-top:10px"><button class="btn sm" data-all>모두 선택</button><button class="btn sm pri" data-pay>선택 결제 처리</button><button class="btn sm" data-unpay>결제 취소</button></div>`);
      UI.$('[data-all]', bar).onclick = () => { rows.forEach(r => s.sel.add(r.id)); App.render(true); };
      UI.$('[data-pay]', bar).onclick = () => paySheet(k, rows.filter(r => s.sel.has(r.id) && !r.paid));
      UI.$('[data-unpay]', bar).onclick = () => {
        const ids = rows.filter(r => s.sel.has(r.id) && r.paid).map(r => r.id);
        if (!ids.length) { UI.toast('결제완료인 항목을 골라 주세요'); return; }
        UI.confirm('선택한 결제를 취소할까요?\n같은 결제로 처리된 다른 회차도 함께 미결제가 되고, 그때 통장·장부에 남긴 기록도 지워집니다.', '결제 취소', true).then(ok => {
          if (!ok) return;
          const n = A.unpayCard(ids);
          s.sel.clear();
          App.dataChanged();
          UI.toast(`${n}건을 미결제로 되돌렸습니다`);
        });
      };
      c.appendChild(bar);
    }
    App.fab(() => purchaseSheet(k), '사용 내역 추가');
  }
  function purchaseSheet(k) {
    const fields = [{ k: 'date', label: '사용일자', type: 'date', req: true }, { k: 'summary', label: '사용처', type: 'text', req: true },
      { k: 'total', label: '사용 금액 (할부면 전체 금액)', type: 'money' }, { k: 'fee_total', label: '수수료 (전체)', type: 'money' },
      { k: 'months', label: '할부 개월 (일시불 = 1)', type: 'int' }, { k: 'pay_date', label: '첫 결제일', type: 'date', hint: '사용일자를 고르면 청구기간에 맞춰 자동으로 정해집니다' },
      { k: 'memo', label: '메모', type: 'text' }];
    const d = U.today();
    UI.formSheet({ title: `사용 내역 추가 — ${k.name}`, fields, full: true, values: { date: d, months: 1, pay_date: A.payDateFor(k, d) },
      afterOpen: sb => { const di = UI.$('[data-k=date]', sb); di.onchange = () => { if (U.isValidIso(di.value)) UI.$('[data-k=pay_date]', sb).value = A.payDateFor(k, di.value); }; },
      onSave: v => {
        if (!v.total) throw new Error('사용 금액을 입력하세요.');
        if (v.months && (v.months < 1 || v.months > 60)) throw new Error('할부 개월은 1~60 사이로 입력하세요.');
        A.addCardPurchase(k.id, v.date, v.summary, v.total, v.fee_total, v.months || 1, v.pay_date || null, v.memo);
        s.ym = (v.pay_date || A.payDateFor(k, v.date)).slice(0, 7);
        App.dataChanged();
      } });
  }
  function groupSheet(k, r) {
    const all = DB.q('SELECT * FROM card_tx WHERE card_id=? AND group_id=? ORDER BY seq', [k.id, r.group_id]);
    UI.sheet({ title: r.summary, body: `<div class="small"><div class="kv"><span>사용일자</span><span>${r.date}</span></div>
      <div class="kv"><span>전체 금액</span><span>${UI.money(r.total)}${r.fee_total ? ` (+수수료 ${UI.money(r.fee_total)})` : ''}</span></div>
      <div class="kv"><span>할부</span><span>${r.months > 1 ? `${r.months}개월` : '일시불'}</span></div>${r.memo ? `<div>${U.esc(r.memo)}</div>` : ''}</div>
      <ul class="list">${all.map(x => `<li><div class="grow">${x.seq}회 · ${x.pay_date}</div><div>${UI.money(x.amount + x.fee)}</div><div class="tiny ${x.paid ? 'in' : 'out'}">${x.paid ? '결제완료' : '미결제'}</div></li>`).join('')}</ul>`,
    buttons: [{ label: '이 사용 내역 삭제 (전 회차)', cls: 'danger', onClick: close => {
      if (all.some(x => x.paid)) { UI.alert('이미 결제 처리한 회차가 있습니다. 결제를 먼저 취소한 뒤 삭제하세요.'); return false; }
      UI.confirm(`'${r.summary}' ${all.length}회차를 모두 삭제할까요?`, '삭제', true).then(ok => { if (ok) { A.deleteCardGroup(k.id, r.group_id); close(); App.dataChanged(); } });
      return false;
    } }, { label: '닫기', cls: 'pri' }] });
  }
  function paySheet(k, rows) {
    if (!rows.length) { UI.toast('미결제 항목을 골라 주세요'); return; }
    const total = U.sum(rows.map(r => r.amount + r.fee));
    const lid = App.lid;
    const fields = [{ k: 'date', label: '결제일', type: 'date', req: true },
      { k: 'bank', label: '결제 통장 (출금 기록)', type: 'select', options: [['', '(기록 안 함)']].concat(A.accounts('bank').map(a => [String(a.id), `${a.company} ${a.name}`.trim()])) },
      { k: 'to_ledger', label: `장부(${App.ledgerName()})에 지출로 기록`, type: 'check' }, { k: 'code', label: '장부 계정과목', type: 'code', lid, mode: 'out' }];
    UI.formSheet({ title: `결제 처리 — ${rows.length}건 ${UI.money(total)}원`, fields, full: true,
      values: { date: rows[0].pay_date, bank: k.bank_account_id ? String(k.bank_account_id) : '' },
      afterOpen: sb => { const chk = UI.$('[data-k=to_ledger]', sb), box = UI.$('[data-k=code]', sb).closest('.f'); const f = () => box.classList.toggle('hidden', !chk.checked); chk.onchange = f; f(); },
      onSave: v => {
        if (v.to_ledger && !v.code) throw new Error('장부 계정과목을 고르세요.');
        const n = A.payCard(rows.map(r => r.id), v.date, v.bank ? Number(v.bank) : null, v.to_ledger ? lid : null, v.to_ledger ? v.code : null);
        s.sel.clear();
        App.dataChanged();
        UI.toast(`${UI.money(n)}원을 결제 처리했습니다`);
      } });
  }
  return { title: p => { const k = p && DB.one('SELECT name FROM card WHERE id=?', [p.id]); return k ? k.name : '카드'; },
    sticker: 'a04', sub: '결제월별 사용 내역', render, tab: 'assets' };
})();
