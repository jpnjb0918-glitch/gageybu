"""카테고리 그림(이모지) (1.8.0): 가계부마다 meta 'cat_emoji:<가계부 번호>' = {카테고리 번호: 그림}.
카테고리(한 글자 번호)와 세부 카테고리(두 글자 번호) 모두. 예전 판은 이 값을 모르므로 그냥 이름만 보인다.
휴대폰(안드로이드 7.0)에서도 보이도록 오래된 이모지(유니코드 9 이하)만 쓴다. 안드로이드판 svc-money.js 의 Emo 와 같음."""
import re

from .. import db

# 고르기 창에 보일 그림
CHOICES = ['💰', '💵', '💴', '💳', '🏦', '📈', '🐷', '🎁',
           '🍚', '🍜', '🍔', '🍕', '🍰', '☕', '🍺', '🛒', '🍎', '🏪',
           '🚌', '🚇', '🚕', '🚗', '⛽', '\u2708\ufe0f', '🚲', '🎫',
           '🏠', '💡', '💧', '🔥', '📱', '🌐', '📺', '🔧',
           '🎓', '📚', '\u270f\ufe0f', '🏥', '💊', '☔', '👕', '💄',
           '🎬', '🎮', '🎵', '⚽', '🐶', '👶', '💒', '🙏',
           '📦', '📝', '\u2764\ufe0f', '⭐']

# 이름에 이 낱말이 들어 있으면 이 그림 (위에서부터 맞춤)
HINTS = [
    (r'급여|월급|상여|보너스|수입', '💰'), (r'용돈', '💵'), (r'이자|배당|투자|주식|펀드', '📈'),
    (r'저축|적금|예금|청약|연금', '🐷'), (r'대출|카드대금|할부', '🏦'),
    (r'관리비|월세|주거|공과금', '🏠'), (r'수도', '💧'), (r'전기', '💡'), (r'가스|난방', '🔥'),
    (r'학원|교육|학비|등록금', '🎓'), (r'교재|책|도서', '📚'),
    (r'카페|커피|간식|디저트', '☕'), (r'배달|치킨|피자', '🍔'), (r'외식|식당', '🍜'), (r'^술$|술값|주류|회식', '🍺'),
    (r'식료품|장보기|마트|식비|식재료', '🛒'), (r'편의점', '🏪'),
    (r'택시', '🚕'), (r'주유|자동차|차량|주차|정비', '🚗'), (r'교통|버스|지하철|기차', '🚌'),
    (r'휴대폰|통신|전화', '📱'), (r'인터넷|와이파이', '🌐'), (r'구독|넷플릭스|OTT|음악', '🎵'), (r'TV|방송', '📺'),
    (r'병원|의료|치과', '🏥'), (r'약국|약값|의약|약품', '💊'), (r'보험', '☔'),
    (r'옷|의류|쇼핑|패션', '👕'), (r'미용|화장|뷰티|헤어', '💄'), (r'생필품|생활용품|생활', '📦'),
    (r'영화|문화|공연|여가|취미', '🎬'), (r'게임', '🎮'), (r'운동|헬스|스포츠', '⚽'), (r'여행|휴가', '\u2708\ufe0f'),
    (r'경조사|선물|축의|부의', '🎁'), (r'결혼|웨딩', '💒'), (r'반려|애완|강아지|고양이', '🐶'), (r'육아|아기|유아|어린이', '👶'),
    (r'기부|헌금|후원', '🙏'), (r'수리|공구|집수리', '🔧'), (r'잡비|기타', '📝'),
]


def suggest(name):
    """이름으로 어울리는 그림 (없으면 '')"""
    for pat, e in HINTS:
        if re.search(pat, name or '', re.I):
            return e
    return ''


def emoji_map(con, lid):
    v = db.get_json(con, f'cat_emoji:{lid}', {})
    return {str(k): str(e) for k, e in v.items() if e} if isinstance(v, dict) else {}


def set_emoji(con, lid, code, emoji):
    d = emoji_map(con, lid)
    e = (emoji or '').strip()[:4]          # 그림 하나 (변형 문자 포함 최대 4글자)
    if e:
        d[code] = e
    else:
        d.pop(code, None)
    db.set_json(con, f'cat_emoji:{lid}', d)
    con.commit()


def fill_defaults(con, lid, overwrite=False):
    """그림이 없는 카테고리·세부 카테고리에 이름으로 어울리는 그림 넣기. 반환: 넣은 수"""
    d = emoji_map(con, lid)
    n = 0
    rows = [(r['code'], r['name']) for r in con.execute('SELECT code, name FROM cat_group WHERE ledger_id=? ORDER BY code', (lid,))]
    rows += [(r['code'], r['name']) for r in con.execute('SELECT code, name FROM category WHERE ledger_id=? ORDER BY code', (lid,))]
    for code, name in rows:
        if d.get(code) and not overwrite:
            continue
        e = suggest(name)
        if e and d.get(code) != e:
            d[code] = e
            n += 1
    db.set_json(con, f'cat_emoji:{lid}', d)
    con.commit()
    return n


def deco(emap, code, name):
    """'🛒 식료품' (그림이 없으면 이름만). 세부 카테고리에 그림이 없으면 카테고리 그림을 씀"""
    e = emap.get(code) or (emap.get(code[:1]) if code and len(code) > 1 else '')
    return f'{e} {name}' if e else name
