"""카드·은행 알림 문자 붙여넣기 → 내역 후보 (날짜·금액·가맹점·카드·할부·승인/취소/입금).
여러 문자를 한꺼번에 붙여넣어도 됨 ([Web발신] 이나 빈 줄로 나눔). 확인 창에서 고친 뒤 저장한다.
안드로이드판 svc.js 의 Sms.parse 와 같은 규칙 (devtools/compat 로 결과 비교)."""
import datetime as dt
import re

# 카드사·은행 이름 (앞쪽이 먼저 맞춤)
ISSUERS = ['KB국민', 'NH농협', 'IBK기업', 'SC제일', '카카오뱅크', '토스뱅크', '케이뱅크', '새마을금고', '우체국',
           '신한', '국민', '삼성', '현대', '롯데', '우리', '하나', '농협', '비씨', 'BC', '씨티', '기업', '수협', '신협',
           '광주', '전북', '경남', '부산', '대구', '제주', '카카오페이', '네이버페이', '토스', 'KB', 'NH']
_ISSUER = re.compile('(' + '|'.join(re.escape(x) for x in ISSUERS) + ')')
_AMOUNT = re.compile(r'(?<![\d.])(\d{1,3}(?:,\d{3})+|\d+)\s*원')
_BARE = re.compile(r'(?<![\d.,])(\d{1,3}(?:,\d{3})+|\d{3,})(?![\d,]*\s*원)')
_DATE = re.compile(r'(?:(\d{4})[./-])?(\d{1,2})[./-](\d{1,2})(?![\d])')
_TIME = re.compile(r'(?<!\d)(\d{1,2}):(\d{2})(?!\d)')
_MONTHS = re.compile(r'(\d{1,2})\s*개월')
_NOISE = ('누적', '잔액', '한도', '총누적', '결제예정', '포인트')
_SKIP_LINE = re.compile(r'Web발신|승인|님(?=\s|$)|\*|누적|잔액|한도|일시불|할부|개월|^\[.*\]$|^\(.*\)$|입금|출금|결제|사용|취소')


def _split(text):
    """[Web발신]·빈 줄·'[은행이름]' 으로 시작하는 줄에서 문자를 나눔"""
    t = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
    out = []
    for part in re.split(r'\[Web발신\]|\n\s*\n', t):
        cur = []
        for ln in part.split('\n'):
            if cur and re.match(r'\s*\[[^\]]{1,12}\]', ln):
                out.append('\n'.join(cur))
                cur = []
            cur.append(ln)
        out.append('\n'.join(cur))
    return [p.strip() for p in out if p.strip()]


def _cut_noise(s):
    """'누적·잔액·한도…' 가 나오는 곳(가장 앞)부터 뒤를 버림"""
    idx = [i for i in (s.find(n) for n in _NOISE) if i >= 0]
    return s[:min(idx)] if idx else s


def _year_for(m, d, today):
    """연도가 없으면 올해, 그 날이 오늘보다 2일 넘게 뒤면 작년 (연말에 1월 문자 붙여넣기 등)"""
    y = today.year
    try:
        cand = dt.date(y, m, d)
    except ValueError:
        return None
    if cand > today + dt.timedelta(days=2):
        try:
            cand = dt.date(y - 1, m, d)
        except ValueError:
            return None
    return cand


def _amount(block):
    """'누적·잔액·한도' 바로 뒤 금액은 건너뛰고 첫 금액"""
    for m in _AMOUNT.finditer(block):
        before = block[max(0, m.start() - 5):m.start()]
        if any(n in before for n in _NOISE):
            continue
        return int(m.group(1).replace(',', ''))
    # '원' 없이 숫자만 (은행 입출금 문자: '입금\n3,200,000')
    for kw in ('입금', '출금'):
        i = block.find(kw)
        if i >= 0:
            m = _BARE.search(block, i)
            if m and not any(n in block[max(0, m.start() - 5):m.start()] for n in _NOISE):
                return int(m.group(1).replace(',', ''))
    return None


def _merchant(block, issuer):
    lines = [ln.strip() for ln in block.split('\n') if ln.strip()]
    # 1) 시간 뒤에 같은 줄로 붙은 글 (한 줄 문자: '... 10/19 12:34 스타벅스 누적1,234원')
    for ln in lines:
        m = _TIME.search(ln)
        if m:
            rest = ' '.join(_AMOUNT.sub(' ', _cut_noise(ln[m.end():])).split())
            rest = re.sub(r'^(출금|입금|승인|결제|사용|일시불)\s*', '', rest).strip(' ,·-')
            if rest and not re.fullmatch(r'[\d,\s]+', rest) and rest not in ('입금', '출금', '승인', '취소'):
                return rest
    # 2) 여러 줄 문자: 카드사·이름·금액·날짜·누적 줄을 뺀 나머지 중 첫 줄
    for ln in lines:
        if _SKIP_LINE.search(ln) or _AMOUNT.search(ln) or _DATE.search(ln) or _TIME.search(ln):
            continue
        if issuer and issuer in ln:
            continue
        if re.fullmatch(r'[\d,\-\s]+', ln):
            continue
        return ln
    return ''


def parse(text, today=None):
    """붙여넣은 글 → [{'date','time','amount','kind','item','card','months','ok','raw'}]
    kind: 'out'(지출) · 'cancel'(승인 취소 → 지출을 빼는 내역) · 'in'(입금). ok=False 면 날짜나 금액을 못 찾음"""
    today = today or dt.date.today()
    out = []
    for block in _split(text):
        flat = ' '.join(block.split())
        im = _ISSUER.search(block)
        issuer = im.group(1) if im else ''
        card = ''
        if issuer:
            cm = re.search(re.escape(issuer) + r'\s*(카드|은행|뱅크|체크|페이)?', block)
            card = (issuer + (cm.group(1) or '')) if cm else issuer
        if '취소' in flat:
            kind = 'cancel'
        elif '입금' in flat and '출금' not in flat:
            kind = 'in'
        else:
            kind = 'out'
        amount = _amount(block)
        dm = None
        for m in _DATE.finditer(block):
            mo, dd = int(m.group(2)), int(m.group(3))
            if 1 <= mo <= 12 and 1 <= dd <= 31:
                dm = m
                break
        date = None
        if dm:
            mo, dd = int(dm.group(2)), int(dm.group(3))
            if dm.group(1):
                try:
                    date = dt.date(int(dm.group(1)), mo, dd)
                except ValueError:
                    date = None
            else:
                date = _year_for(mo, dd, today)
        tm = _TIME.search(block)
        months = 1
        mm = _MONTHS.search(block)
        if mm:
            months = max(1, int(mm.group(1)))
        item = _merchant(block, issuer)
        if not item:
            item = f'{card or "카드"} {"입금" if kind == "in" else "승인"}'.strip()
        out.append({'date': date.isoformat() if date else '', 'time': f'{int(tm.group(1)):02d}:{tm.group(2)}' if tm else '',
                    'amount': amount or 0, 'kind': kind, 'item': item, 'card': card, 'months': months,
                    'ok': bool(amount and date), 'raw': flat})
    return out


# 가게 이름 → 흔한 계정 이름 (위에서부터 맞춤. 사용자 계정 이름에 이 낱말이 들어 있으면 그 계정)
HINTS = [
    (r'영화|CGV|메가박스|롯데시네마|공연|티켓|전시', ['문화', '여가', '잡비']),
    (r'스타벅스|커피|카페|이디야|투썸|메가MGC|빽다방|폴바셋|할리스|공차|배스킨|던킨|파리바게|뚜레쥬르|베이커리', ['카페', '간식', '외식', '식비']),
    (r'배달|요기요|쿠팡이츠|치킨|피자|버거|맥도날드|롯데리아|맘스터치|분식|김밥|식당|국밥|고기|횟집|족발|보쌈|초밥|돈까스|반점|짬뽕', ['배달', '외식', '식비']),
    (r'이마트24|GS25|CU|씨유|세븐일레븐|미니스톱|편의점', ['편의점', '간식', '식료품', '식비']),
    (r'마트|홈플러스|코스트코|트레이더스|하나로|식자재|정육|청과|노브랜드|더프레시|컬리', ['식료품', '장보기', '식비']),
    (r'택시|카카오T|버스|지하철|코레일|KTX|SRT|티머니|교통|주유|에너지|칼텍스|오일|충전소|하이패스|주차', ['대중교통', '교통', '주유', '차량']),
    (r'SKT|KT|LG유플러스|U\+|통신|알뜰폰', ['휴대폰', '통신']),
    (r'약국|병원|의원|치과|한의원|안과|피부과|정형외과|내과', ['병원', '의료', '약']),
    (r'다이소|올리브영|쿠팡|11번가|G마켓|지마켓|옥션|무신사|오늘의집|생활', ['생필품', '생활용품', '쇼핑']),
    (r'학원|교습|서점|교보문고|영풍문고|YES24|알라딘', ['학원비', '교재비', '교육']),
    (r'넷플릭스|유튜브|멜론|디즈니|티빙|웨이브|왓챠|스포티파이|구독', ['구독', '문화', '잡비']),
    (r'보험', ['보험료', '보험']),
    (r'한전|전기요금', ['전기세', '전기']),
    (r'도시가스|가스요금', ['가스비', '가스']),
    (r'수도요금|상수도', ['수도세', '수도']),
]


def guess_code(con, lid, item, income=False):
    """새 내역의 계정 고르기: ① 예전에 같은 품목으로 쓴 계정 ② 가게 이름으로 짐작 ③ 가장 많이 쓴 지출 계정 ④ 첫 계정.
    안드로이드판 Sms.guessCode 와 같은 순서"""
    from . import ledger as L
    from ..util import is_income_code
    item = (item or '').strip()
    c = L.last_code_for_item(con, lid, item) if item else None
    if c and is_income_code(c) == bool(income):
        return c
    cats = [(r['code'], r['name']) for r in L.categories(con, lid)]
    if income:
        inc = [x for x in cats if is_income_code(x[0])]
        return next((cd for cd, nm in inc if '기타' in nm), inc[0][0] if inc else '')
    exp = [x for x in cats if not is_income_code(x[0])]
    for pat, names in HINTS:
        if re.search(pat, item, re.I):
            for want in names:
                hit = next((cd for cd, nm in exp if want in nm), None)
                if hit:
                    return hit
    r = con.execute("SELECT code, COUNT(*) n FROM entry WHERE ledger_id=? AND expense>0 AND substr(code,1,1)<>'0' "
                    'GROUP BY code ORDER BY n DESC, code LIMIT 1', (lid,)).fetchone()
    if r and any(cd == r['code'] for cd, _n in exp):
        return r['code']
    return exp[0][0] if exp else ''


def to_entry(p, con=None):
    """후보 하나 → 내역 값 (수입·지출). 취소는 지출을 음수로 (그 달 지출에서 빠짐).
    con 을 주면 결제수단도 짐작 (1.8.0: 은행 → 계좌이체, 자산에 넣은 카드 → 그 카드, 그 밖 → 카드)"""
    memo = ' '.join(x for x in (p['card'], f"{p['months']}개월" if p['months'] > 1 else '', p['time']) if x)
    pay = ''
    if con is not None:
        from .money import guess_pay
        pay = guess_pay(con, p['card'], p['kind'])
    if p['kind'] == 'in':
        return {'date': p['date'], 'item': p['item'], 'income': p['amount'], 'expense': 0, 'memo': memo, 'pay': pay}
    sign = -1 if p['kind'] == 'cancel' else 1
    return {'date': p['date'], 'item': p['item'] + (' (취소)' if p['kind'] == 'cancel' else ''), 'income': 0,
            'expense': sign * p['amount'], 'memo': memo, 'pay': pay}
