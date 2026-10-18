/* 음력↔양력 (PC판 gagyebu/lunar.py 이식, 같은 저자의 자료·알고리즘) */
'use strict';
const Lunar = (() => {
  const s2l = new Map();
  const l2s = new Map();

  /** 'YYYY-MM-DD' → {y, m, d, leap} 또는 지원 범위 밖이면 null */
  function solarToLunar(s) {
    if (s2l.has(s)) return s2l.get(s);
    const [y, m, d] = U.parts(s);
    const c = new window.KoreanLunarCalendar();
    let r = null;
    if (c.setSolarDate(y, m, d)) {
      const l = c.getLunarCalendar();
      r = { y: l.year, m: l.month, d: l.day, leap: !!l.intercalation };
    }
    s2l.set(s, r);
    return r;
  }

  /** 음력 → 양력 'YYYY-MM-DD'. 그 달에 없는 날(30일)이면 그 달 말일로 */
  function lunarToSolar(ly, lm, ld, leap) {
    const key = `${ly}-${lm}-${ld}-${leap ? 1 : 0}`;
    if (l2s.has(key)) return l2s.get(key);
    const c = new window.KoreanLunarCalendar();
    const days = ld > 29 ? [] : [ld];
    if (ld > 29) for (let day = ld; day > 28; day--) days.push(day);
    let r = null;
    for (const day of days) {
      if (c.setLunarDate(ly, lm, day, !!leap)) {
        const s = c.getSolarCalendar();
        r = U.iso(s.year, s.month, s.day);
        break;
      }
    }
    l2s.set(key, r);
    return r;
  }

  function label(s) {
    const r = solarToLunar(s);
    if (!r) return '';
    return `음 ${r.leap ? '윤' : ''}${r.m}.${r.d}`;
  }

  return { solarToLunar, lunarToSolar, label };
})();
