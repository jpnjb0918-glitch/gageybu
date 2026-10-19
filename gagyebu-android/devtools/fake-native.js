/* 시험용: 안드로이드 NativeBridge 와 같은 함수들을 sql.js(SQLite 웹어셈블리)로 흉내 냄.
   APK 에는 들어가지 않는다. Playwright 의 add_init_script 로 페이지보다 먼저 넣는다. */
(function () {
  if (!/^https?:/.test(location.href)) return;
  const BASE = '/devtools/node_modules/sql.js/dist/';
  const st = { prefs: {}, saved: [], external: [], exported: null };
  window.__fake = st;

  // ── SHA-256 / HMAC / PBKDF2 (동기식, 시험용) ──
  function sha256(bytes) {
    const K = new Uint32Array([0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]);
    const H = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
    const l = bytes.length, n = ((l + 9 + 63) >> 6) << 6;
    const m = new Uint8Array(n); m.set(bytes); m[l] = 0x80;
    const dv = new DataView(m.buffer); dv.setUint32(n - 4, l * 8); dv.setUint32(n - 8, Math.floor(l / 0x20000000));
    const w = new Uint32Array(64);
    for (let o = 0; o < n; o += 64) {
      for (let i = 0; i < 16; i++) w[i] = dv.getUint32(o + i * 4);
      for (let i = 16; i < 64; i++) {
        const a = w[i - 15], b = w[i - 2];
        const s0 = ((a >>> 7) | (a << 25)) ^ ((a >>> 18) | (a << 14)) ^ (a >>> 3);
        const s1 = ((b >>> 17) | (b << 15)) ^ ((b >>> 19) | (b << 13)) ^ (b >>> 10);
        w[i] = (w[i - 16] + s0 + w[i - 7] + s1) | 0;
      }
      let [a, b, c, d, e, f, g, h] = H;
      for (let i = 0; i < 64; i++) {
        const S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^ ((e >>> 25) | (e << 7));
        const t1 = (h + S1 + ((e & f) ^ (~e & g)) + K[i] + w[i]) | 0;
        const S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^ ((a >>> 22) | (a << 10));
        const t2 = (S0 + ((a & b) ^ (a & c) ^ (b & c))) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      H[0] += a; H[1] += b; H[2] += c; H[3] += d; H[4] += e; H[5] += f; H[6] += g; H[7] += h;
    }
    const out = new Uint8Array(32); const ov = new DataView(out.buffer);
    for (let i = 0; i < 8; i++) ov.setUint32(i * 4, H[i]);
    return out;
  }
  function hmacFactory(key) {
    if (key.length > 64) key = sha256(key);
    const k = new Uint8Array(64); k.set(key);
    const ipad = k.map(x => x ^ 0x36), opad = k.map(x => x ^ 0x5c);
    return msg => { const a = new Uint8Array(64 + msg.length); a.set(ipad); a.set(msg, 64); const ih = sha256(a);
      const b = new Uint8Array(96); b.set(opad); b.set(ih, 64); return sha256(b); };
  }
  const hex = b => Array.from(b).map(x => x.toString(16).padStart(2, '0')).join('');
  const unhex = s => new Uint8Array(s.match(/../g).map(x => parseInt(x, 16)));

  window.__devNative = (async () => {
    const code = await (await fetch(BASE + 'sql-wasm.js')).text();
    (0, eval)(code);
    const SQL = await window.initSqlJs({ locateFile: f => BASE + f });
    let db = window.__initialDbBytes ? new SQL.Database(window.__initialDbBytes) : new SQL.Database();
    db.run('PRAGMA foreign_keys = ON');
    // sql.js 의 export() 는 DB 를 닫았다 다시 열어 PRAGMA 가 꺼짐 → 다시 켬 (실제 앱은 Java 에서 항상 켜 둠)
    const dump = () => { const b = db.export(); db.run('PRAGMA foreign_keys = ON'); return b; };
    window.__getDbBytes = () => Array.from(dump());
    const ok = o => JSON.stringify(Object.assign({ ok: true }, o || {}));
    const err = e => JSON.stringify({ ok: false, error: String(e && e.message || e) });
    const later = (cb, res) => setTimeout(() => window.__nativeDone(cb, res), 10);
    return {
      query(sql, args) {
        try {
          const s = db.prepare(sql); s.bind(JSON.parse(args || '[]'));
          const cols = s.getColumnNames(); const rows = [];
          while (s.step()) rows.push(s.get());
          s.free();
          return ok({ cols, rows });
        } catch (e) { return err(e); }
      },
      exec(sql, args) {
        try {
          const s = db.prepare(sql); s.bind(JSON.parse(args || '[]')); s.step(); s.free();
          const changes = db.getRowsModified();
          const head = sql.trim().toUpperCase();
          const lastId = /^(INSERT|REPLACE)/.test(head) ? (changes ? db.exec('SELECT last_insert_rowid()')[0].values[0][0] : -1) : undefined;
          return ok({ changes: /^(INSERT|REPLACE|UPDATE|DELETE)/.test(head) ? changes : 0, lastId });
        } catch (e) { return err(e); }
      },
      begin() { try { db.run('BEGIN'); return ok(); } catch (e) { return err(e); } },
      commit() { try { db.run('COMMIT'); return ok(); } catch (e) { return err(e); } },
      rollback() { try { db.run('ROLLBACK'); return ok(); } catch (e) { return err(e); } },
      pbkdf2(pw, salt, iters) {
        let key = new TextEncoder().encode(pw);
        const mac = hmacFactory(key);
        const s = unhex(salt); const first = new Uint8Array(s.length + 4); first.set(s); first[s.length + 3] = 1;
        let u = mac(first); const t = u.slice();
        for (let i = 1; i < iters; i++) { u = mac(u); for (let j = 0; j < 32; j++) t[j] ^= u[j]; }
        return ok({ hex: hex(t) });
      },
      randomHex(n) { const b = new Uint8Array(n); crypto.getRandomValues(b); return hex(b); },
      getPrefs() { return JSON.stringify(st.prefs); },
      setPref(k, v) { if (v === null) delete st.prefs[k]; else st.prefs[k] = v; },
      setBars(color, light) { st.bars = [color, light]; },
      appInfo() { return ok({ version: st.appVersion || 'dev', versionCode: 0, sdk: 0, dbPath: 'memory', dbSize: dump().length }); },
      // 새 버전: 시험이 st.releases(배열 또는 'fail')·st.dlResult 를 정해 둠. 받은 파일·설치 화면 열기는 기록만
      fetchReleases(cb) {
        st.updCalls = (st.updCalls || 0) + 1;
        if (st.releases === 'fail') { later(cb, { ok: false, error: 'Unable to resolve host "api.github.com"' }); return; }
        later(cb, { ok: true, body: JSON.stringify(st.releases || []) });
      },
      downloadUpdate(url, name, size, sha, cb) {
        st.downloads = (st.downloads || []).concat([{ url, name, size, sha }]);
        const total = Number(size) || 1000;
        [0.3, 0.7, 1].forEach((f, i) => setTimeout(() => window.__updProgress && window.__updProgress(Math.round(total * f), total), 100 + i * 200));
        setTimeout(() => {
          const r = st.dlResult || { ok: true, name };
          if (r.ok) st.files = Object.assign(st.files || {}, { [name]: true });
          window.__nativeDone(cb, r);
        }, 800);
      },
      hasUpdateFile(name) { return !!(st.files && st.files[name]); },
      installUpdate(name) { st.installs = (st.installs || []).concat([name]); return ok({}); },
      autoBackup() { return ok({ skipped: true }); },
      listBackups() { return ok({ items: [] }); },
      restoreBackup() { return err('시험 환경에는 보관본이 없습니다'); },
      openExternal(u) { st.external.push(u); },
      exitApp() { st.exited = true; },
      exportDb(name, cb) { st.exported = { name, bytes: Array.from(dump()) }; later(cb, { ok: true, size: st.exported.bytes.length }); },
      shareDb(name, cb) { st.shared = { name, bytes: Array.from(dump()) }; later(cb, { ok: true, size: st.shared.bytes.length }); },
      importDbVia(cb) { st.via = (st.via || 0) + 1; this.importDb(cb); },
      importDb(cb) {
        const b = window.__importBytes;
        if (!b) { later(cb, { ok: false, cancel: true }); return; }
        try {
          const t = new SQL.Database(new Uint8Array(b));
          const r = t.exec("SELECT 1 FROM sqlite_master WHERE type='table' AND name='entry'");
          t.close();
          if (!r.length) { later(cb, { ok: false, error: '우리집 가계부(새 버전) 백업 파일이 아닙니다.' }); return; }
        } catch (e) { later(cb, { ok: false, error: 'SQLite 자료 파일이 아니거나 손상된 파일입니다.' }); return; }
        st.kept = db.export();
        db.close();
        db = new SQL.Database(new Uint8Array(b));
        db.run('PRAGMA foreign_keys = ON');
        later(cb, { ok: true, kept: 'before-restore-test.sqlite3' });
      },
      saveText(name, mime, content, cb) { st.saved.push({ name, mime, content }); later(cb, { ok: true }); },
      openText(cb) { const t = window.__openText; later(cb, t === undefined ? { ok: false, cancel: true } : { ok: true, text: t }); },
    };
  })();
})();
