/* 금액·날짜·결산기간 공통 함수 (PC판 gagyebu/util.py 이식).
   날짜는 늘 'YYYY-MM-DD' 문자열로 다룬다 (시간대 영향 없음). */
'use strict';
const U = (() => {
  const INCOME_GROUP = '0';
  const CODE_CHARS = '0123456789abcdefghijklmnopqrstuvwxyz';
  const MONEY_LIMIT = 1e15;
  const WEEKDAYS = '월화수목금토일';           // 0=월 (파이썬 weekday 와 같음)
  const WEATHER = ['맑음', '구름 조금', '흐림', '소나기', '비', '비 온 후 갬', '눈', '비 또는 눈', '천둥번개'];

  const isIncomeCode = code => (code || '').slice(0, 1) === INCOME_GROUP;

  function fmtMoney(v, blankZero) {
    v = Math.round(Number(v) || 0);
    if (blankZero && v === 0) return '';
    return v.toLocaleString('en-US');
  }

  /** '1,000' / '1000원' / '' / '-500' → 정수. 숫자가 아니면 Error */
  function parseMoney(s) {
    if (s === null || s === undefined) return 0;
    let v;
    if (typeof s === 'number') {
      if (!isFinite(s)) throw new Error('금액이 아닙니다');
      v = Math.round(s);
    } else {
      const t = String(s).replace(/[,\s원₩]/g, '');
      if (t === '' || t === '-' || t === '+') return 0;
      if (!/^[+-]?\d+(\.\d+)?$/.test(t)) throw new Error('금액이 아닙니다: ' + s);
      const neg = t.startsWith('-');
      const [ip, fp] = t.replace(/^[+-]/, '').split('.');
      v = Number(ip) + ((fp && Number(fp[0]) >= 5) ? 1 : 0);   // 반올림(절댓값 기준, 파이썬 ROUND_HALF_UP)
      if (neg) v = -v;
    }
    if (Math.abs(v) >= MONEY_LIMIT) throw new Error('금액이 너무 큽니다');
    return v;
  }

  /** 금액 칸 계산기: '12000+3500', '45,000/3', '(1200+800)*2' — 숫자와 + - * / × ÷ ( ) 만.
      결과는 원 단위 반올림(0.5 는 0 에서 먼 쪽). 식이 아니면 parseMoney. PC판 util.calc_money 와 같은 규칙 */
  function calcMoney(s) {
    const t = String(s === null || s === undefined ? '' : s).replace(/[,\s원₩]/g, '').replace(/×/g, '*').replace(/÷/g, '/').replace(/[xX]/g, '*');
    if (!/\d[-+*/]|[)*/(]/.test(t)) return parseMoney(t);
    const toks = t.match(/\d+(?:\.\d+)?|[-+*/()]/g) || [];
    if (toks.join('') !== t) throw new Error('계산할 수 없는 식입니다: ' + s);
    let pos = 0;
    const peek = () => (pos < toks.length ? toks[pos] : null);
    const take = () => toks[pos++];
    const bad = () => { throw new Error('계산할 수 없는 식입니다: ' + s); };
    function expr() { let v = term(); while (peek() === '+' || peek() === '-') v = take() === '+' ? v + term() : v - term(); return v; }
    function term() {
      let v = factor();
      while (peek() === '*' || peek() === '/') {
        const op = take(), r = factor();
        if (op === '/' && r === 0) throw new Error('0으로 나눌 수 없습니다');
        v = op === '*' ? v * r : v / r;
      }
      return v;
    }
    function factor() {
      const tok = peek();
      if (tok === '+' || tok === '-') { take(); return tok === '+' ? factor() : -factor(); }
      if (tok === '(') { take(); const v = expr(); if (take() !== ')') throw new Error('괄호가 맞지 않습니다'); return v; }
      if (tok === null || !/^\d/.test(tok)) bad();
      return parseFloat(take());
    }
    const v = expr();
    if (pos !== toks.length) bad();
    const r = Math.floor(Math.abs(v) + 0.5 + 1e-9) * (v >= 0 ? 1 : -1);
    if (Math.abs(r) >= MONEY_LIMIT) throw new Error('금액이 너무 큽니다');
    return r;
  }

  // ── 날짜 ──
  const pad = (n, w = 2) => String(n).padStart(w, '0');
  const iso = (y, m, d) => `${pad(y, 4)}-${pad(m)}-${pad(d)}`;
  const parts = s => { const [y, m, d] = String(s).slice(0, 10).split('-').map(Number); return [y, m, d]; };
  function isValidIso(s) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(String(s || ''))) return false;
    const [y, m, d] = parts(s);
    return m >= 1 && m <= 12 && d >= 1 && d <= monthEnd(y, m);
  }
  function today() { const t = new Date(); return iso(t.getFullYear(), t.getMonth() + 1, t.getDate()); }
  const ord = s => { const [y, m, d] = parts(s); return Date.UTC(y, m - 1, d) / 86400000; };
  const fromOrd = n => { const t = new Date(n * 86400000); return iso(t.getUTCFullYear(), t.getUTCMonth() + 1, t.getUTCDate()); };
  const addDays = (s, n) => fromOrd(ord(s) + n);
  const weekday = s => (new Date(ord(s) * 86400000).getUTCDay() + 6) % 7;   // 0=월
  const monthEnd = (y, m) => new Date(Date.UTC(y, m, 0)).getUTCDate();
  function addMonths(y, m, n) { const k = y * 12 + (m - 1) + n; return [Math.floor(k / 12), ((k % 12) + 12) % 12 + 1]; }
  const clampDay = (y, m, d) => iso(y, m, Math.min(Math.max(1, d), monthEnd(y, m)));
  /** 결산일 기준 '해당 월' 기간. 결산일 5일이면 5일~다음달 4일 */
  function settlePeriod(y, m, settleDay) {
    settleDay = Math.max(1, Math.min(31, parseInt(settleDay || 1, 10) || 1));
    const start = clampDay(y, m, settleDay);
    const [ny, nm] = addMonths(y, m, 1);
    return [start, addDays(clampDay(ny, nm, settleDay), -1)];
  }
  const ym = (y, m) => `${pad(y, 4)}-${pad(m)}`;
  const monthLabel = (y, m) => `${y}년 ${m}월`;
  const dateLabel = s => { const [y, m, d] = parts(s); return `${y}.${pad(m)}.${pad(d)} (${WEEKDAYS[weekday(s)]})`; };
  const shortDate = s => { const [, m, d] = parts(s); return `${m}/${d}`; };

  // ── 화면 도우미 ──
  const esc = s => String(s === null || s === undefined ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  const sum = arr => arr.reduce((a, b) => a + (b || 0), 0);

  return { INCOME_GROUP, CODE_CHARS, MONEY_LIMIT, WEEKDAYS, WEATHER, isIncomeCode, fmtMoney, parseMoney, calcMoney,
    pad, iso, parts, isValidIso, today, ord, fromOrd, addDays, weekday, monthEnd, addMonths, clampDay,
    settlePeriod, ym, monthLabel, dateLabel, shortDate, esc, sum };
})();
