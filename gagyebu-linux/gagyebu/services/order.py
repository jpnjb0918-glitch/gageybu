"""사용자가 정한 순서 (안드로이드판 svc.js 의 Ord 와 같은 규칙).

자료 파일 호환: 표에 칸을 더하지 않는다 (예전 판이 칸 위치로 INSERT 하는 곳이 있어서).
- 대분류 순서        → meta 'order_groups:<장부id>'  = ["0","3","1",...]
- 같은 날 내역 순서  → meta 'order_day:<장부id>'     = {"2026-10-19": [내역id, ...], ...}
- 주소록·일기 순서   → meta 'order_list:contact' / 'order_list:diary' = [id, ...]
- 소분류·메모 순서   → 원래 있던 sort 칸
규칙: 저장된 순서에 있는 것이 먼저 그 순서대로, 새로 생긴 것(목록에 없는 것)은 그 뒤에 원래 순서대로.
"""
import json

from .. import db

LIST_TABLES = ('contact', 'diary')


def _get(con, key, dflt):
    v = db.get_meta(con, key)
    if not v:
        return dflt
    try:
        out = json.loads(v)
    except ValueError:
        return dflt
    return out if isinstance(out, type(dflt)) else dflt


def _set(con, key, value):
    db.set_meta(con, key, json.dumps(value, ensure_ascii=False, separators=(',', ':')) if value else None)


def by_list(rows, ids, key=lambda r: r['id']):
    """rows(원래 순서)를 ids 순서대로. ids 에 없는 것은 뒤에 원래 순서대로."""
    if not ids:
        return list(rows)
    pos = {}
    for i, v in enumerate(ids):
        pos.setdefault(v, i)
    listed = sorted((r for r in rows if key(r) in pos), key=lambda r: pos[key(r)])
    return listed + [r for r in rows if key(r) not in pos]


# ── 대분류 ──
def group_order(con, lid):
    return [str(x) for x in _get(con, f'order_groups:{lid}', [])]


def set_group_order(con, lid, codes):
    _set(con, f'order_groups:{lid}', [str(c) for c in codes])
    con.commit()


# ── 같은 날 내역 ──
def day_orders(con, lid):
    d = _get(con, f'order_day:{lid}', {})
    return {k: [int(x) for x in v if isinstance(x, int) or str(x).isdigit()] for k, v in d.items() if isinstance(v, list)}


def set_day_order(con, lid, date, ids):
    """그 날 내역 순서 저장. 원래 순서(id 순)와 같으면 지움."""
    d = _get(con, f'order_day:{lid}', {})
    ids = [int(x) for x in ids]
    if ids == sorted(ids):
        d.pop(str(date), None)
    else:
        d[str(date)] = ids
    _set(con, f'order_day:{lid}', d)
    con.commit()


def apply_day_order(rows, orders, desc=False):
    """날짜순(같은 날은 id 순) rows 의 같은 날 안 순서를 바꿈.
    desc=True 면 날짜를 최근 것부터 — 순서를 정한 날은 정한 순서 그대로, 안 정한 날은 최근 입력이 위로."""
    out, i, n = [], 0, len(rows)
    while i < n:
        j = i
        d = str(rows[i]['date'] if not isinstance(rows[i], tuple) else rows[i][0]['date'])
        while j < n and str(rows[j]['date'] if not isinstance(rows[j], tuple) else rows[j][0]['date']) == d:
            j += 1
        grp = rows[i:j]
        key = (lambda r: r[0]['id']) if isinstance(grp[0], tuple) else (lambda r: r['id'])
        grp = sorted(grp, key=key)
        if d in orders:
            grp = by_list(grp, orders[d], key)
        elif desc:
            grp = grp[::-1]
        out.append(grp)
        i = j
    if desc:
        out.reverse()
    return [r for g in out for r in g]


# ── 주소록·일기 ──
def list_order(con, table):
    assert table in LIST_TABLES
    return [int(x) for x in _get(con, f'order_list:{table}', []) if isinstance(x, int) or str(x).isdigit()]


def set_list_order(con, table, ids):
    assert table in LIST_TABLES
    _set(con, f'order_list:{table}', [int(x) for x in ids])
    con.commit()


def merge_list_order(con, table, view_ids, new_order=None):
    """보이는 일부(검색·그룹·달)만 순서를 바꿀 때: 다른 것은 그대로 두고 이것들을 정한 순서로 뒤에 붙임.
    new_order=None 이면 이것들만 순서에서 뺌 (원래 순서로)"""
    v = {int(x) for x in view_ids}
    set_list_order(con, table, [x for x in list_order(con, table) if x not in v] + [int(x) for x in (new_order or [])])


def apply_list_order(con, table, rows):
    return by_list(rows, list_order(con, table))


# ── 소분류·메모 (sort 칸) ──
def set_category_order(con, lid, codes):
    """한 대분류 안의 소분류 순서 (codes 순서대로 sort=1,2,3…)"""
    con.executemany('UPDATE category SET sort=? WHERE ledger_id=? AND code=?',
                    [(i + 1, lid, c) for i, c in enumerate(codes)])
    con.commit()


def set_memo_order(con, ids):
    con.executemany('UPDATE memo SET sort=? WHERE id=?', [(i + 1, rid) for i, rid in enumerate(ids)])
    con.commit()
