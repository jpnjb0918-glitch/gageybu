"""음력↔양력 변환 (한국천문연구원 기준 데이터, korean_lunar_calendar MIT 라이선스 포함)."""
import datetime as dt
from functools import lru_cache

from .vendor.korean_lunar_calendar import KoreanLunarCalendar

# 변환할 수 있는 해: 1000~2050 (데이터 범위)


@lru_cache(maxsize=4096)
def solar_to_lunar(d):
    """date → (음력년, 월, 일, 윤달여부) 또는 지원 범위 밖이면 None"""
    c = KoreanLunarCalendar()
    if not c.setSolarDate(d.year, d.month, d.day):
        return None
    return c.lunarYear, c.lunarMonth, c.lunarDay, bool(c.isIntercalation)


@lru_cache(maxsize=4096)
def lunar_to_solar(ly, lm, ld, leap=False):
    """음력 → 양력 date. 그 달에 없는 날(30·31일)이면 그 달 말일로 (원본: '말일은 31일로 지정')."""
    c = KoreanLunarCalendar()
    for day in range(ld, 28, -1) if ld > 29 else (ld,):
        if c.setLunarDate(ly, lm, day, leap):
            return dt.date(c.solarYear, c.solarMonth, c.solarDay)
    return None


def lunar_label(d):
    r = solar_to_lunar(d)
    if not r:
        return ''
    _, m, day, leap = r
    return f"음 {'윤' if leap else ''}{m}.{day}"
