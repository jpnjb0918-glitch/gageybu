"""금액·날짜·결산기간 공통 함수."""
import calendar
import datetime as dt
import hashlib
import os
import re

INCOME_GROUP = '0'          # 계정코드 첫 자리가 0 이면 수입, 나머지는 지출 (원본과 동일)
CODE_CHARS = '0123456789abcdefghijklmnopqrstuvwxyz'


def is_income_code(code):
    return (code or '')[:1] == INCOME_GROUP


def fmt_money(v, blank_zero=False):
    v = int(round(v or 0))
    if blank_zero and v == 0:
        return ''
    return f'{v:,}'


MONEY_LIMIT = 10 ** 15          # 1,000조 원 — 이보다 큰 금액은 입력 실수로 봄


def parse_money(s):
    """'1,000' / '1000원' / '' / '-500' / '1000000.0000'(원본 Currency) → int.
    숫자가 아니거나(inf, 1e30 등) 너무 크면 ValueError."""
    if s is None:
        return 0
    if isinstance(s, int):
        v = s
    elif isinstance(s, float):
        if s != s or s in (float('inf'), float('-inf')):
            raise ValueError('금액이 아닙니다')
        v = int(round(s))
    else:
        t = re.sub(r'[,\s원₩]', '', str(s))
        if t in ('', '-', '+'):
            return 0
        if not re.fullmatch(r'[+-]?\d+(\.\d+)?', t):
            raise ValueError(f'금액이 아닙니다: {s!r}')
        from decimal import ROUND_HALF_UP, Decimal
        v = int(Decimal(t).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if abs(v) >= MONEY_LIMIT:
        raise ValueError('금액이 너무 큽니다')
    return v


def calc_money(s):
    """금액 칸 계산기: '12000+3500', '45,000/3', '(1200+800)*2', '2만 3천' 은 아님 — 숫자와 + - * / × ÷ ( ) 만.
    결과는 원 단위로 반올림(0.5 는 0 에서 먼 쪽). 식이 아니면 parse_money 와 같음. 잘못된 식은 ValueError.
    안드로이드판 util.js calcMoney 와 같은 규칙"""
    t = re.sub(r'[,\s원₩]', '', str(s or '')).replace('×', '*').replace('÷', '/').replace('x', '*').replace('X', '*')
    if not re.search(r'\d[-+*/]|[)*/(]', t):
        return parse_money(t)
    toks = re.findall(r'\d+(?:\.\d+)?|[-+*/()]', t)
    if ''.join(toks) != t:
        raise ValueError(f'계산할 수 없는 식입니다: {s!r}')
    pos = 0

    def peek():
        return toks[pos] if pos < len(toks) else None

    def take():
        nonlocal pos
        pos += 1
        return toks[pos - 1]

    def expr():
        v = term()
        while peek() in ('+', '-'):
            v = v + term() if take() == '+' else v - term()
        return v

    def term():
        v = factor()
        while peek() in ('*', '/'):
            op = take()
            r = factor()
            if op == '/' and r == 0:
                raise ValueError('0으로 나눌 수 없습니다')
            v = v * r if op == '*' else v / r
        return v

    def factor():
        tok = peek()
        if tok in ('+', '-'):
            take()
            return factor() if tok == '+' else -factor()
        if tok == '(':
            take()
            v = expr()
            if take() != ')':
                raise ValueError('괄호가 맞지 않습니다')
            return v
        if tok is None or not tok[0].isdigit():
            raise ValueError('계산할 수 없는 식입니다')
        return float(take())

    try:
        v = expr()
    except (IndexError, TypeError):
        raise ValueError(f'계산할 수 없는 식입니다: {s!r}') from None
    if pos != len(toks):
        raise ValueError(f'계산할 수 없는 식입니다: {s!r}')
    v = int(abs(v) + 0.5 + 1e-9) * (1 if v >= 0 else -1)
    if abs(v) >= MONEY_LIMIT:
        raise ValueError('금액이 너무 큽니다')
    return v


def today():
    return dt.date.today()


def to_date(s):
    if isinstance(s, dt.datetime):
        return s.date()
    if isinstance(s, dt.date):
        return s
    return dt.date.fromisoformat(str(s)[:10])


def iso(d):
    return to_date(d).isoformat()


def month_end(y, m):
    return calendar.monthrange(y, m)[1]


def add_months(y, m, n):
    k = y * 12 + (m - 1) + n
    return k // 12, k % 12 + 1


def clamp_day(y, m, d):
    return dt.date(y, m, min(max(1, d), month_end(y, m)))


def settle_period(y, m, settle_day=1):
    """결산일 기준 '해당 월' 기간. 결산일 5일이면 5일~다음달 4일 (원본 도움말 기준)."""
    settle_day = max(1, min(31, int(settle_day or 1)))
    start = clamp_day(y, m, settle_day)
    ny, nm = add_months(y, m, 1)
    end = clamp_day(ny, nm, settle_day) - dt.timedelta(days=1)
    return start, end


def hash_password(pw, salt=None):
    salt = salt or os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac('sha256', pw.encode('utf-8'), bytes.fromhex(salt), 120_000).hex()
    return f'pbkdf2${salt}${h}'


def check_password(pw, stored):
    if not stored:
        return True
    try:
        _, salt, _h = stored.split('$')
    except ValueError:
        return False
    return hash_password(pw, salt) == stored


WEATHER = ['맑음', '구름 조금', '흐림', '소나기', '비', '비 온 후 갬', '눈', '비 또는 눈', '천둥번개']
