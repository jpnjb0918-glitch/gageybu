/* 안드로이드판(자바스크립트) 쪽: 표본 자료 만들기 + PC판 py_side.py 와 같은 계산 결과 뽑기.
   브라우저 페이지 안(앱이 뜬 상태)에서 실행한다. */
const SMS_SAMPLE = "[Web발신]\n신한카드(1234)승인 홍*동 12,500원(일시불)10/19 12:34 스타벅스 누적1,234,567원\n[Web발신]\nKB국민카드1234승인\n홍*동님\n45,000원 일시불\n10/18 19:02\n교촌치킨\n누적1,279,567원\n[Web발신]\n삼성1234승인 홍*동\n120,000원 03개월\n10/17 15:20 이마트 성수점\n누적1,399,567원\n[Web발신]\n현대카드 M 승인\n홍*동\n8,900원 일시불\n10/16 08:10\nGS25 역삼점\n누적1,408,467원\n[Web발신]\n롯데카드 2*7*승인취소 홍*동 12,500원 일시불 10/19 13:00 스타벅스\n[Web발신]\n[KB]10/15 09:00\n123-***-456\n홍길동\n입금\n3,200,000\n잔액5,000,000\n[Web발신]\n우리(1234)승인\n홍*동님\n6,000원 일시불\n10/14 21:45\n쿠팡이츠\n누적123,000원\n[Web발신]\n하나(1*2*)승인 홍*동님 23,400원 일시불 10/13 18:30 올리브영 누적1,234,567원\n[Web발신]\nNH농협카드(1234)승인 홍*동 4,500원 일시불 01/03 07:55 메가커피 총누적1,234,567원\n[카카오뱅크] 홍*동(1234) 10/12 11:20 출금 15,000원 배달의민족 잔액 123,456원\n";
const GUESS_ITEMS = [['스타벅스 강남점', false], ['메가박스 코엑스', false], ['쿠팡이츠', false], ['쿠팡', false], ['GS25 역삼점', false], ['이마트 성수점', false], ['KTX 서울', false], ['SKT 요금', false], ['넷플릭스', false], ['기차표', false], ['아무가게', false], ['홍길동', true], ['한전', false]];
const CALC_SAMPLES = ["12000+3500", "45,000/3", "(1200+800)*2", "1,000", "", "-500", "10000-2500*2", "7/2", "5/2", "-5/2", "3×4", "12÷5", "1e3", "2*(3", "10/0", "1.5*3", "0.1*3"];
const SPLIT_SAMPLES = [[{ date: '2026-01-31', item: '자동차보험', expense: 1000003, code: '60', memo: '1년치', pay: 'card' }, 12],
  [{ date: '2026-03-15', item: '상여', income: 500000, code: '00' }, 3],
  [{ date: '2026-03-15', item: 'x', expense: 5, code: '30' }, 12],
  [{ date: '2026-03-15', item: 'x', expense: 500, income: 5, code: '30' }, 2],
  [{ date: '2026-03-15', item: 'x', expense: 500, code: '30' }, 1],
  [{ date: '2026-12-31', item: '연회비', expense: 120000, code: '80' }, 61]];
const FX_SAMPLES = [['12.5', 'USD', '1,380.5'], ['3,500', 'JPY', '935.2'], ['100000', 'VND', '5.4'], ['0.99', 'EUR', '1500.55'],
  ['1', 'USD', '0.5'], ['1', 'USD', '1.49999'], ['abc', 'USD', '1300'], ['10', 'XXX', '1300'], ['10', 'USD', '0'],
  ['999999999.99', 'GBP', '1777.7777'], ['12.50', 'THB', '38.40'], ['', 'USD', '1300']];
const EMO_NAMES = ['급여', '기타 수입', '공과금', '수도세', '전기세', '가스비', '교육비', '학원비', '교재비', '식비', '식료품', '외식', '교통·통신비',
  '대중교통', '휴대폰 요금', '인터넷', '생활용품', '생필품', '보험', '보험료', '저축', '적금', '기타지출', '잡비', '미술',
  '계약금', '여행', '넷플릭스', '아기 기저귀', '술', '술값', 'TV 수신료', '반려동물', ''];
const GUESS_PAY = [['신한카드', 'out'], ['KB국민카드', 'out'], ['현대카드', 'out'], ['삼성', 'out'], ['카카오뱅크', 'out'], ['', 'out'],
  ['네이버페이', 'out'], ['하나', 'in'], ['롯데카드', 'cancel'], ['신한체크', 'out']];
window.__compat = {
  build() {
    const lid = L.firstLedgerId();
    const add = (d, item, inc, exp, code, memo) => L.addEntry(lid, { date: d, item, income: inc || 0, expense: exp || 0, code: code || '30', memo: memo || '' });
    for (const [y, m] of [[2025, 11], [2025, 12], [2026, 1], [2026, 2], [2026, 8], [2026, 9], [2026, 10]]) {
      add(U.iso(y, m, 1), '관리비', 0, 180000, '10');
      add(U.iso(y, m, 5), '전기세', 0, 40000 + m * 1000, '11');
      add(U.iso(y, m, 10), '급여', 3200000, 0, '00');
      add(U.iso(y, m, 12), '점심', 0, 9000, '31', '회사 앞');
      add(U.iso(y, m, 12), '점심', 0, 11000, '31');
      add(U.iso(y, m, 25), '마트', 0, 87300, '30');
      add(U.iso(y, m, 28), '환불', 15000, 0, '31');
    }
    add('2026-10-03', '용돈', 50000, 0, '01');
    add('2026-10-16', '커피', 0, 4500, '31');
    add('2026-10-16', '택시', 0, 13200, '40');
    L.setCategory(lid, '32', '간식');
    add('2026-09-09', '붕어빵', 0, 3000, '32');
    L.setGroup(lid, '9', '여가');
    L.setCategory(lid, '90', '영화');
    add('2026-09-20', '영화관', 0, 15000, '90');
    add('2026-09-21', '알수없음', 0, 1000, 'zz');
    L.moveCategoryOrder(lid, '31', -1);
    Rep.setBudget(lid, '2026-10', '30', 400000);
    Rep.setBudget(lid, '2026-10', '31', 150000);
    Rep.setBudget(lid, '2026-11', '31', 120000);
    Rep.setBudget(lid, '2026-10', '00', 3200000);
    Rep.setBudget(lid, '2026-10', '32', 5000);
    L.mergeCategory(lid, '32', '31');
    const r1 = R.saveRule(lid, { item: '적금', expense: 300000, code: '70', day: 25, start: '2026-07-01' });
    R.saveRule(lid, { item: '월세', expense: 500000, code: '10', day: 31, start: '2026-08-01', end: '2026-12-31' });
    R.saveRule(lid, { item: '보너스', income: 1000000, code: '01', day: 20, start: '2026-10-01' });
    const [due] = R.pending(lid, '2026-09-30');
    R.apply(lid, due.filter(x => x.rule.id === r1).slice(0, 2));
    R.apply(lid, due.filter(x => x.rule.id !== r1).slice(0, 1), true);
    R.saveRule(lid, Object.assign({}, R.rules(lid).find(r => r.id === r1), { day: 10 }), r1);   // 고쳐도 지난 달 다시 안 나오게
    const lid2 = L.addLedger('비상금 장부', lid, true);
    L.addEntry(lid2, { date: '2026-10-02', item: '비상금', income: 100000, code: '00' });
    const lid3 = L.addLedger('복사본', lid, false);
    L.addEntry(lid3, { date: '2026-10-04', item: '복사 뒤 입력', expense: 777, code: '31' });
    const b1 = A.saveAccount('bank', { company: '국민', name: '월급통장', opening: 1500000, 'x.password': '1234', active: 1 });
    A.saveAccount('bank', { company: '신한', name: '예전통장', opening: 300000, active: 0 });
    A.addTx(b1, { date: '2026-10-10', summary: '급여', deposit: 3200000 });
    A.addTx(b1, { date: '2026-10-11', summary: '마트', withdraw: 52000 }, lid, '30');
    const s1 = A.saveAccount('securities', { company: '키움', name: '주식', valuation: 2500000, deposit: 100000 });
    A.saveAccount('securities', { valuation: 2600000, 'x.valued_on': '2026-10-15' }, s1);
    A.saveAccount('insurance', { company: '삼성', name: '실손', 'x.status': '정상', 'x.pay_method': '월납' });
    A.saveAccount('property', { name: '아파트', 'x.ptype': 0, valuation: 400000000, loan: 150000000 });
    A.saveAccount('property', { name: '자동차', 'x.ptype': 5, valuation: 20000000, loan: 5000000 });
    const c1 = A.saveCard({ company: '현대', name: 'M카드', pay_day: 25, bill_from_month: -1, bill_from_day: 1, bill_to_month: -1, bill_to_day: 31, bank_account_id: b1 });
    const c2 = A.saveCard({ company: '삼성', name: '탭탭', pay_day: 14, bill_from_month: -2, bill_from_day: 31, bill_to_month: -1, bill_to_day: 30 });
    A.addCardPurchase(c1, '2026-09-03', '노트북', 1000000, 30000, 3);
    A.addCardPurchase(c1, '2026-09-30', '편의점', 5300);
    A.addCardPurchase(c2, '2026-10-01', '주유', 70000);
    A.addCardPurchase(c2, '2026-10-02', '나눔', 100001, 0, 3);
    const tx = A.cardTxs(c1, '2026-10').map(r => r.id);
    A.payCard(tx, '2026-10-25', b1, lid, '80');
    const tx2 = A.cardTxs(c2, '2026-11').map(r => r.id);
    A.payCard(tx2.slice(0, 1), '2026-11-14', null, lid, '80');
    A.unpayCard(tx2.slice(0, 1));
    Cal.addSchedule('2026-10-20', '치과', 7);
    Cal.addSchedule('2026-10-05', '운동', 0, null, null, { type: 'weekdays', set: '월, 수, 금' }, '2026-10-31');
    Cal.addSchedule('2026-01-31', '정산', 0, null, null, { type: 'every', n: 1, unit: '월' }, '2026-12-31');
    Cal.addSchedule('2026-10-01', '모임', 0, '#FFE3EC', null, { type: 'nth', nth: 4, weekday: 4, n: 1 }, '2027-03-31');
    Cal.saveAnniversary({ title: '엄마 생신', month: 3, day: 30, lunar: true });
    Cal.saveAnniversary({ title: '결혼기념일', month: 2, day: 29 });
    Cal.simpleSave('contact', { name: '홍길동', mobile: '010-1234-5678', grp: '친구' });
    Cal.simpleSave('diary', { date: '2026-10-16', weather: 2, title: '흐림', content: '오늘은' });
    Cal.simpleSave('memo', { title: '장보기', content: '우유\n계란', created: '2026-10-16 09:00', sort: 1 });
    Cal.simpleSave('contact', { name: '가나다', mobile: '010-1111-2222' });
    Cal.simpleSave('contact', { name: '나중에', grp: '친구' });
    Cal.simpleSave('diary', { date: '2026-10-15', title: '어제', content: '' });
    Cal.simpleSave('diary', { date: '2026-10-16', title: '오늘 두 번째', content: '' });
    Cal.simpleSave('memo', { title: '할 일', content: '', created: '2026-10-16 10:00', sort: 2 });
    Cal.simpleSave('memo', { title: '책 목록', content: '', created: '2026-10-16 11:00', sort: 3 });
    Ord.setGroupOrder(lid, ['3', '0', '9', '1']);
    Ord.setCategoryOrder(lid, ['31', '30']);
    let ids = [];
    for (const d of ['2026-10-12', '2026-10-16', '2026-09-12']) {
      ids = DB.q('SELECT id FROM entry WHERE ledger_id=? AND date=? ORDER BY id', [lid, d]).map(r => r.id);
      Ord.setDayOrder(lid, d, ids.slice().reverse());
    }
    Ord.setDayOrder(lid, '2026-09-12', ids.slice().sort((a, b) => a - b));
    const cids = Cal.simpleList('contact', 'name').map(r => r.id);
    Ord.setListOrder('contact', cids.slice().reverse().slice(0, 2));
    const dids = Cal.simpleList('diary', 'date DESC, id DESC').map(r => r.id);
    Ord.setListOrder('diary', dids.slice().reverse());
    const mids = Cal.simpleList('memo', 'sort, id').map(r => r.id);
    Ord.setMemoOrder([mids[2], mids[0], mids[1]]);
    // 1.7.0
    const f1 = L.saveFavorite(lid, { item: '지하철', expense: 1500, code: '40' });
    L.saveFavorite(lid, { item: '점심', expense: 9000, code: '31', memo: '#회사' });
    L.saveFavorite(lid, { item: '용돈', income: 50000, code: '01' });
    L.moveFavorite(lid, f1, 1);
    add('2026-10-14', '기차표', 0, 59800, '40', '#여행 #부산');
    add('2026-10-15', '숙소', 0, 120000, '80', '#여행');
    add('2026-09-15', '회식', 0, 30000, '31', '#회사 #여행지');
    add('2026-10-16', '김장 재료', 0, 250000, '30');
    add('2026-10-16', '송별회', 0, 180000, '31', '#회사');
    const b2 = A.accounts('bank').find(a => a.name === '예전통장').id;
    const [, t2] = A.transfer(b1, b2, '2026-10-12', 200000, '비상금');
    A.transfer(b2, b1, '2026-10-13', 50000);
    A.updateTx(t2, { date: '2026-10-12', summary: '이체 ← 월급통장', deposit: 180000, withdraw: 0, memo: '고침' });
    const g1 = Goal.saveGoal({ name: '여행 자금', target: 1200000, due: '2027-03-31' });
    Goal.addGoalTx(g1, '2026-09-25', 300000);
    Goal.addGoalTx(g1, '2026-10-10', 150000);
    Goal.saveGoal({ name: '비상금', target: 0 });
    const d1 = Goal.saveDebt({ kind: 'lend', person: '철수', amount: 50000, date: '2026-10-01', due: '2026-11-01' });
    Goal.addPayment(d1, '2026-10-05', 20000);
    const d2 = Goal.saveDebt({ kind: 'borrow', person: '영희', amount: 30000, date: '2026-10-02' });
    Goal.addPayment(d2, '2026-10-09', 30000);
    Goal.saveDebt({ kind: 'borrow', person: '민수', amount: 70000, date: '2026-10-03', memo: '책값' });
    const e1 = DB.val("SELECT id FROM entry WHERE item='숙소'");
    DB.run("INSERT INTO attachment(entry_id,name,mime,data,created) VALUES(?,?,?,X'FFD8FF00',?)", [e1, 'receipt.jpg', 'image/jpeg', '2026-10-16 09:00']);
    DB.run("INSERT INTO attachment(entry_id,name,mime,data,created) VALUES(?,?,?,X'FFD8FF01',?)", [e1, 'receipt2.jpg', 'image/jpeg', '2026-10-16 09:01']);
    Rep.setBudgets(lid, ['2026-11', '2026-12'], { '30': 300000, '31': 0, '40': 50000 });
    DB.setMeta('settle_day', 25);
    DB.setMeta('password', Bk.hashPassword('1111'));
    DB.setJson('address_labels', { tel1: '집전화' });
    // 1.8.0: 결제수단·나눠 적기·외화 환율·매주/매년·주간/전체 예산·카테고리 그림·휴지통
    const c3 = A.saveCard({ company: '신한', name: 'Deep Dream', pay_day: 14, 'x.perf': 300000 });
    A.saveCard({ 'x.perf': 200000 }, c1);
    const add2 = (d, item, exp, code, pay, inc) => L.addEntry(lid, { date: d, item, income: inc || 0, expense: exp || 0, code: code || '31', pay: pay || '' });
    add2('2026-10-02', '스타벅스', 4800, '31', `card:${c3}`);
    add2('2026-10-09', '스타벅스', 5200, '31', `card:${c3}`);
    add2('2026-08-30', '스타벅스', 4500, '31', 'cash');
    add2('2026-07-10', '스타벅스', 4100, '31', 'cash');
    add2('2026-10-09', '스타벅스 (취소)', -5200, '31', `card:${c3}`);
    add2('2026-10-07', '편의점', 3000, '30', 'pay');
    add2('2026-10-08', '시장', 12000, '30', 'etc:지역화폐');
    add2('2026-10-06', '버스', 1500, '40', `card:${c1}`);
    add2('2026-09-06', '버스', 1500, '40', `card:${c1}`);
    add2('2026-10-06', '용돈 받음', 0, '01', 'bank', 20000);
    Pay.setCustom(['지역화폐', '상품권', '지역화폐', ' ', '현금']);
    add2('2026-10-09', '꽃집', 8000, '30', 'etc:상품권');
    Pay.renameCustom('상품권', '온누리상품권');
    Split.add(lid, { date: '2026-01-31', item: '자동차보험', expense: 1200005, code: '60', pay: `card:${c3}`, memo: '1년치' }, 12);
    Fx.setRate('USD', '1,380.5');
    Fx.setRate('JPY', '935.2');
    R.saveRule(lid, { item: '용돈', expense: 30000, code: '80', start: '2026-09-01', cycle: 'W', wday: 4, every: 2, pay: 'cash' });
    R.saveRule(lid, { item: '자동차세', expense: 200000, code: '60', start: '2025-01-01', cycle: 'Y', ymonth: 6, day: 30, end: '2030-12-31' });
    const wr = R.saveRule(lid, { item: '주간 회비', income: 10000, code: '01', start: '2026-10-01', cycle: 'W', wday: 0, end: '2026-11-30' });
    R.saveRule(lid, { item: '연말 정산', income: 300000, code: '01', start: '2026-01-01', cycle: 'Y', ymonth: 2, day: 31 });
    const [due2] = R.pending(lid, '2026-10-12');
    R.apply(lid, due2.filter(x => x.rule.id === wr).slice(0, 1));
    Week.setBudget(lid, 150000);
    TBud.set(lid, ['2026-10', '2026-11'], 1400000);
    TBud.set(lid, ['2026-11'], 0);
    Emo.set(lid, '31', '🍜');
    Emo.fillDefaults(lid);
    Emo.set(lid, '30', '');
    Emo.set(lid, '9', '🎬🎬🎬🎬🎬');
    const tE = DB.val("SELECT id FROM entry WHERE item='숙소'");
    L.deleteEntries([tE, DB.val("SELECT id FROM entry WHERE item='편의점' AND pay='pay'")]);
    Trash.restore(Trash.items(lid).filter(x => x.entry.item === '숙소').map(x => x.id));
    L.deleteEntries([DB.val("SELECT id FROM entry WHERE item='시장'")]);
    L.setCategory(lid, '33', '지울것');
    add2('2026-10-01', '지울 내역', 1000, '33');
    L.deleteCategory(lid, '33');
  },

  dump() {
    const TODAY = '2026-10-16';
    const res = {};
    const rep = r => ({ title: r.title, columns: r.columns, note: r.note, rows: r.rows, periods: r.periods });
    for (const led of L.ledgers()) {
      const lid = led.id, k = `L${lid}`;
      res[k + '.ewb'] = L.entriesWithBalance(lid).map(([r, b]) => [r.id, b]);
      res[k + '.ewb_oct'] = L.entriesWithBalance(lid, '2026-10-01', '2026-10-31').map(([r, b]) => [r.id, b]);
      res[k + '.cur'] = L.currentBalance(lid, TODAY);
      res[k + '.groups'] = L.groups(lid);
      res[k + '.cats'] = L.categories(lid);
      res[k + '.words'] = L.itemWords(lid, 1);
      for (const sd of [1, 25]) {
        for (const [y, m] of [[2026, 10], [2026, 1], [2025, 12]]) res[`${k}.monthly.${y}.${m}.${sd}`] = rep(Rep.monthly(lid, y, m, sd));
        res[`${k}.yearly.2026.${sd}`] = rep(Rep.yearly(lid, 2026, sd));
      }
      res[k + '.daily'] = rep(Rep.daily(lid, 2026, 10));
      res[k + '.custom'] = rep(Rep.custom(lid, '2026-09-01', '2026-10-16'));
      res[k + '.budget'] = rep(Rep.budgetYear(lid, 2026));
      for (const [g, c, mo] of [[null, null, null], ['3', null, null], [null, '31', null], [null, null, 10]]) {
        const o = { settleDay: 25 };
        if (g) o.group = g;
        if (c) o.code = c;
        if (mo) o.month = mo;
        res[`${k}.graph.${g === null ? 'None' : g}.${c === null ? 'None' : c}.${mo === null ? 'None' : mo}`] = Rep.graphSeries(lid, 2026, o);
      }
      res[k + '.search1'] = L.search(lid, { text: '점심' }).map(r => r.id);
      res[k + '.search2'] = L.search(lid, { start: '2026-09-01', codes: ['31', '30'], order: 'expense', desc: true }).map(r => r.id);
      res[k + '.search3'] = L.search(lid, { amount: 9000, amountSide: '지출', amountOp: '크거나 같은 금액' }).map(r => r.id);
      res[k + '.search4'] = L.search(lid, { start: '2026-10-01' }).map(r => r.id);
      res[k + '.search5'] = L.search(lid, { start: '2026-09-01', desc: true }).map(r => r.id);
      res[k + '.dayord'] = Ord.dayOrders(lid);
      res[k + '.ewb_desc'] = Ord.applyDayOrder(L.entriesWithBalance(lid), Ord.dayOrders(lid), true).map(([r, b]) => [r.id, b]);
      const [due, later] = R.pending(lid, TODAY);
      res[k + '.pending'] = [due.map(x => [x.rule.id, x.date]), later.map(x => [x.rule.id, x.date])];
      res[k + '.rules'] = R.rules(lid);
      res[k + '.fav'] = L.favorites(lid);
      res[k + '.tags'] = L.tagSummary(lid);
      res[k + '.tags_oct'] = L.tagSummary(lid, '2026-10-01', '2026-10-31');
      res[k + '.tag_travel'] = L.entriesWithTag(lid, '여행').map(r => r.id);
      for (const sd of [1, 25]) {
        for (const [y, m] of [[2026, 10], [2026, 9], [2026, 11]]) {
          res[`${k}.bprog.${y}.${m}.${sd}`] = Ins.budgetProgress(lid, y, m, sd, TODAY);
          res[`${k}.insight.${y}.${m}.${sd}`] = Ins.monthInsight(lid, y, m, sd, TODAY);
        }
        res[`${k}.codespent.${sd}`] = ['30', '31', '40'].flatMap(c => ['2026-10-01', '2026-10-24', '2026-10-25'].map(d => Ins.codeSpent(lid, c, d, sd)));
        res[`${k}.alert.${sd}`] = ['30', '31'].flatMap(c => [0, 100000, 130000, 330000, 400000].map(b => Ins.budgetAlert(lid, c, '2026-10-16', b, sd)));
      }
      res[k + '.pay_sum'] = Pay.summary(lid, '2026-10-01', '2026-10-31');
      res[k + '.pay_sum_all'] = Pay.summary(lid, '2020-01-01', '2030-12-31');
      res[k + '.pay_ent'] = Pay.entries(lid, 'cash', '2026-01-01', '2026-12-31').map(r => r.id);
      res[k + '.search_pay'] = L.search(lid, { pays: ['pay', 'cash', 'etc:지역화폐'] }).map(r => r.id);
      for (const it of ['스타벅스', '버스', '', '없는가게']) {
        const sp = Same.place(lid, it, TODAY);
        res[`${k}.same.${it}`] = sp === null ? null : Object.assign({}, sp, { rows: sp.rows.map(r => r.id) });
      }
      res[k + '.week'] = ['2026-10-16', '2026-10-05', '2026-10-26'].map(d => Week.progress(lid, d, TODAY));
      res[k + '.weeks'] = [1, 25].map(sd => Week.ofMonth(lid, 2026, 10, sd));
      res[k + '.sav'] = [1, 25].map(sd => Sav.trend(lid, 2026, sd));
      res[k + '.fixed'] = [9, 10, 11].flatMap(m => [1, 25].map(sd => Fixed.summary(lid, 2026, m, sd, TODAY)));
      res[k + '.tbud'] = ['2026-10', '2026-11'].map(ym => TBud.get(lid, ym));
      res[k + '.talert'] = [0, 1500000, 1700000, 2500000].flatMap(b => [1, 25].map(sd => TBud.alert(lid, '2026-10-16', b, sd)));
      res[k + '.mspent'] = [1, 25].map(sd => TBud.monthSpent(lid, '2026-10-16', sd));
      res[k + '.mcal'] = MCal.events(lid, '2026-09-25', '2026-11-05', TODAY);
      const sid = DB.val("SELECT MIN(id) FROM entry WHERE ledger_id=? AND origin LIKE 'split:%'", [lid]);
      res[k + '.split_grp'] = sid ? Split.group(sid) : [];
      res[k + '.split_one'] = Split.group(DB.val('SELECT MIN(id) FROM entry WHERE ledger_id=?', [lid]) || 0);
      res[k + '.trash'] = Trash.items(lid);
      res[k + '.trash_n'] = Trash.count(lid);
      res[k + '.emoji'] = Emo.map(lid);
      const emap = Emo.map(lid);
      res[k + '.deco'] = L.categories(lid).map(c => Emo.deco(emap, c.code, c.name)).concat([Emo.deco(emap, 'zz', '없음')]);
      res[k + '.ruletext'] = R.rules(lid).map(r => R.ruleText(r));
      res[k + '.occ'] = R.rules(lid).map(r => R.occurrences(r, '2025-06-01', '2027-07-01'));
      res[k + '.status'] = R.rules(lid).map(r => R.occurrences(r, '2026-09-01', '2026-11-30').map(d => R.statusOf(r, d, TODAY)));
      res[k + '.nospend'] = Ins.noSpendDays(lid, '2026-09-25', '2026-10-16');
      res[k + '.streak'] = ['2026-10-16', '2026-10-11', '2026-10-09'].map(d => Ins.noSpendStreak(lid, d));
    }
    res['order.contact'] = Ord.applyListOrder('contact', Cal.simpleList('contact', 'name')).map(r => r.id);
    res['order.contact.grp'] = Ord.applyListOrder('contact', Cal.simpleList('contact', 'name', 'grp=?', ['친구'])).map(r => r.id);
    res['order.diary'] = Ord.applyListOrder('diary', Cal.simpleList('diary', 'date DESC, id DESC')).map(r => r.id);
    res['order.memo'] = Cal.simpleList('memo', 'sort, id').map(r => r.id);
    res['assets.summary'] = A.summary();
    res.goals = Goal.goals().map(g => [g, Goal.goalStatus(g, TODAY), Goal.goalTxs(g.id)]);
    res.debts = Goal.debts().map(d => [d, Goal.debtPaid(d.id), Goal.debtLeft(d), Goal.payments(d.id)]);
    res['debts.open'] = Goal.debts(false).map(d => d.id);
    res['debt.totals'] = Goal.debtTotals();
    const eids = DB.q('SELECT id FROM entry ORDER BY id').map(r => r.id);
    const cnt = Att.counts(eids);
    res['att.counts'] = {};
    for (const k2 of Object.keys(cnt)) res['att.counts'][String(k2)] = cnt[k2];
    res['att.list'] = Object.keys(cnt).map(Number).sort((a, b) => a - b).map(e => Att.listFor(e));
    res.sms = Sms.parse(SMS_SAMPLE, '2026-10-20');
    res['sms.entries'] = res.sms.map(p => Sms.toEntry(p));
    res['sms.jan'] = Sms.parse('[Web발신]\n신한카드(1234)승인 홍*동 9,900원(일시불)12/30 23:59 넷플릭스', '2027-01-02');
    const lid1 = L.firstLedgerId();
    res.guess = GUESS_ITEMS.map(([it, inc]) => Sms.guessCode(lid1, it, inc));
    res.calc = CALC_SAMPLES.map(t => { try { return U.calcMoney(t); } catch (e) { return 'ERR'; } });
    for (const a of A.accounts()) {
      res[`acct.${a.id}`] = A.accountTxs(a.id).map(([r, b]) => [r.id, b]);
      res[`acct.${a.id}.bal`] = A.accountBalance(a.id);
    }
    for (const c of A.cards()) {
      res[`card.${c.id}`] = A.cardTxs(c.id);
      res[`card.${c.id}.unpaid`] = A.cardUnpaidTotal(c.id);
      res[`card.${c.id}.paydates`] = Array.from({ length: 40 }, (_, i) => A.payDateFor(c, U.addDays('2026-01-01', i * 11)));
    }
    res.anniv = Cal.anniversariesBetween('2025-12-01', '2027-02-28');
    res.sched = Cal.schedules('2026-01-01', '2027-12-31');
    res.remind = Cal.reminders(TODAY);
    res.grid = Cal.monthGrid(2026, 10);
    const rules = [{ type: 'every', n: 2, unit: '주' }, { type: 'every', n: 1, unit: '월' }, { type: 'every', n: 1, unit: '년' },
      { type: 'weekdays', set: '화, 목' }, { type: 'nth', nth: 2, weekday: 1, n: 2 }, { type: 'nth', nth: 4, weekday: 6, n: 1 }];
    res.repeat = rules.map(r => Cal.expandRepeat('2024-01-31', '2026-03-01', r));
    const lun = [];
    for (let d = '1950-01-01'; d <= '2050-12-31'; d = U.addDays(d, 97)) {
      const r = Lunar.solarToLunar(d);
      lun.push([d, r ? [r.y, r.m, r.d, r.leap] : null]);
    }
    res.lunar = lun;
    const l2 = [];
    for (const y of [2020, 2026, 2033]) for (const m of [1, 4, 8, 12]) for (const dd of [1, 15, 29, 30]) l2.push(Lunar.lunarToSolar(y, m, dd, false));
    res.lunar2 = l2;
    res.pay_opts = Pay.options();
    try { Pay.renameCustom('지역화폐', '온누리상품권'); res.rename_err = ''; } catch (e) { res.rename_err = e.message; }
    res.pay_custom = Pay.custom();
    res.guess_pay = GUESS_PAY.map(([t, kd]) => Pay.guess(t, kd));
    res['sms.entries.pay'] = res.sms.map(p => Sms.toEntry(p, true));
    const err = f => { try { return f(); } catch (e) { return 'ERR:' + e.message; } };
    res.split_plan = SPLIT_SAMPLES.map(([e, n]) => err(() => Split.plan(e, n)));
    res.fx = FX_SAMPLES.map(([a, c, r]) => err(() => Fx.convert(a, c, r)));
    res.fx_rates = Fx.rates();
    res.card_perf = [9, 10].map(m => Perf.cards(2026, m));
    res.emo_suggest = EMO_NAMES.map(n => Emo.suggest(n));
    res.week_bounds = ['2026-10-12', '2026-10-18', '2026-10-19', '2027-01-01'].map(d => Week.bounds(d));
    res.saving_codes = Sav.codes(L.firstLedgerId());
    res.trash_all = Trash.count();
    res.trash_left = ['2026-10-01', '2026-10-30', '2026-10-31', '2026-11-05'].map(d => Trash.daysLeft('2026-10-01 10:00:00', d));
    res.meta = {};
    for (const r of DB.q("SELECT * FROM meta WHERE key<>'password'")) res.meta[r.key] = r.value;
    res.pw = [Bk.checkPassword('1111', DB.getMeta('password')), Bk.checkPassword('1112', DB.getMeta('password'))];
    return res;
  },
};
