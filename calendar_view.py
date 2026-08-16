# -*- coding: utf-8 -*-
"""日历查询层：历史上的今天、月视图、期数卡片装配（含参与者与精华评论）。"""
from datetime import datetime, timedelta, timezone

import config

CN_TZ = timezone(timedelta(hours=8))

AUDIOBOOK_CAT_NAME = "机核有声书"


def _not_audiobook(alias="c"):
    """排除机核有声书分类（历史上的今天主列表不含有声书）。"""
    p = (alias + ".") if alias else ""
    return f"({p}name IS NULL OR {p}name != '{AUDIOBOOK_CAT_NAME}')"


def now_cn():
    return datetime.now(CN_TZ)


def today_md():
    return now_cn().strftime("%m-%d")


def _filters(official_only, alias="e"):
    """默认过滤：已发布 + （可选）仅官方。不加 is_listable —— 订阅可见（is_listable=0）
    的付费期数也是真实内容，日历与检索不应漏掉。"""
    p = (alias + ".") if alias else ""
    w = f"{p}is_published=1"
    if official_only:
        w += f" AND {p}owner_type='gcores'"
    return w


def _episode_cards(conn, rows):
    """把 episodes 行装配为卡片：分类名、专辑名、参与者、精华评论前三。"""
    if not rows:
        return []
    ids = [r["id"] for r in rows]
    qmarks = ",".join("?" * len(ids))
    djs_rows = conn.execute(
        "SELECT d.radio_id, u.id AS user_id, u.nickname, u.thumb, u.is_gcores_official "
        "FROM episode_djs d JOIN users u ON u.id=d.user_id "
        f"WHERE d.radio_id IN ({qmarks}) ORDER BY d.radio_id, d.position",
        ids,
    ).fetchall()
    com_rows = conn.execute(
        "SELECT * FROM comments WHERE radio_id IN ({}) ORDER BY radio_id, rank".format(qmarks),
        ids,
    ).fetchall()
    djs_map, com_map = {}, {}
    for d in djs_rows:
        djs_map.setdefault(d["radio_id"], []).append({
            "user_id": d["user_id"], "nickname": d["nickname"], "thumb": d["thumb"],
            "is_gcores_official": d["is_gcores_official"],
            "url": config.SITE + f"/users/{d['user_id']}",
        })
    for c in com_rows:
        com_map.setdefault(c["radio_id"], []).append({
            "id": c["id"], "rank": c["rank"], "body": c["body"], "likes_count": c["likes_count"],
            "score": c["score"], "created_at": c["created_at"], "user_id": c["user_id"],
            "nickname": c["nickname"], "thumb": c["thumb"], "is_gcores_official": c["is_gcores_official"],
        })
    cards = []
    for r in rows:
        cards.append({
            "id": r["id"], "title": r["title"], "subtitle": r["subtitle"],
            "page_desc": r["page_desc"], "published_at": r["published_at"],
            "published_date": r["published_date"], "duration": r["duration"],
            "vol": r["vol"], "is_free": r["is_free"], "is_require_privilege": r["is_require_privilege"],
            "is_program_preview": r["is_program_preview"], "plays": r["plays"],
            "likes_count": r["likes_count"], "comments_count": r["comments_count"],
            "cover": r["cover"],
            "category_id": r["category_id"], "category_name": r["category_name"] if "category_name" in r.keys() else None,
            "album_id": r["album_id"], "album_title": r["album_title"] if "album_title" in r.keys() else None,
            "url": config.SITE + f"/radios/{r['id']}",
            "djs": djs_map.get(r["id"], []),
            "comments": com_map.get(r["id"], []),
        })
    return cards


cards_from_rows = _episode_cards  # 公开别名：任意带 category_name/album_title 的 episode 行


def years_for_date(conn, md, official_only=None):
    if official_only is None:
        official_only = config.DEFAULT_OFFICIAL_ONLY
    rows = conn.execute(
        "SELECT substr(published_date,1,4) AS y, count(*) AS n "
        f"FROM episodes WHERE substr(published_date,6,5)=? AND {_filters(official_only, '')} "
        "GROUP BY y ORDER BY y",
        (md,),
    ).fetchall()
    return [{"year": int(r["y"]), "count": r["n"]} for r in rows]


def day_data(conn, md, year=None, page=1, per_page=10, official_only=None, include_audiobooks=False):
    """某月-日（MM-DD）的全部历史期数，最新一期在最上（倒序），不分年份标签。
    默认排除机核有声书；有声书单独放在 audiobooks 列表（由界面以下拉框展示）。"""
    if official_only is None:
        official_only = config.DEFAULT_OFFICIAL_ONLY
    rows = conn.execute(
        "SELECT e.*, c.name AS category_name, a.title AS album_title "
        "FROM episodes e "
        "LEFT JOIN categories c ON c.id=e.category_id "
        "LEFT JOIN albums a ON a.id=e.album_id "
        f"WHERE substr(e.published_date,6,5)=? AND {_filters(official_only, 'e')} "
        f"AND {_not_audiobook('c')} "
        "ORDER BY e.published_date DESC, e.id DESC",
        (md,),
    ).fetchall()
    episodes = _episode_cards(conn, rows)
    ab_rows = conn.execute(
        "SELECT e.*, c.name AS category_name, a.title AS album_title "
        "FROM episodes e "
        "LEFT JOIN categories c ON c.id=e.category_id "
        "LEFT JOIN albums a ON a.id=e.album_id "
        f"WHERE substr(e.published_date,6,5)=? AND {_filters(official_only, 'e')} "
        f"AND c.name = '{AUDIOBOOK_CAT_NAME}' "
        "ORDER BY e.published_date DESC, e.id DESC",
        (md,),
    ).fetchall()
    audiobooks = _episode_cards(conn, ab_rows)
    if not include_audiobooks:
        audiobooks = []
    return {
        "date": md,
        "total_episodes": len(episodes),
        "audiobooks_count": len(ab_rows),
        "audiobooks": audiobooks,
        "episodes": episodes,
    }


def month_data(conn, yyyy, mm, official_only=None):
    """月视图：每一天的期数 count + 最多 3 条标题预览（含 id 与跳转链接）。
    默认排除机核有声书；有声书单独计 audiobooks。"""
    if official_only is None:
        official_only = config.DEFAULT_OFFICIAL_ONLY
    ym = f"{yyyy:04d}-{mm:02d}"
    rows = conn.execute(
        "SELECT substr(e.published_date,9,2) AS d, count(*) AS n "
        "FROM episodes e "
        "LEFT JOIN categories c ON c.id=e.category_id "
        f"WHERE substr(e.published_date,1,7)=? AND {_filters(official_only, 'e')} "
        f"AND {_not_audiobook('c')} "
        "GROUP BY d ORDER BY d",
        (ym,),
    ).fetchall()
    ab_rows = conn.execute(
        "SELECT substr(e.published_date,9,2) AS d, count(*) AS n "
        "FROM episodes e "
        "LEFT JOIN categories c ON c.id=e.category_id "
        f"WHERE substr(e.published_date,1,7)=? AND {_filters(official_only, 'e')} "
        f"AND c.name = '{AUDIOBOOK_CAT_NAME}' "
        "GROUP BY d ORDER BY d",
        (ym,),
    ).fetchall()
    ab_map = {r["d"]: r["n"] for r in ab_rows}
    days = []
    for r in rows:
        prev = conn.execute(
            "SELECT e.id, e.title FROM episodes e "
            "LEFT JOIN categories c ON c.id=e.category_id "
            f"WHERE substr(e.published_date,1,7)=? AND substr(e.published_date,9,2)=? "
            f"AND {_filters(official_only, 'e')} AND {_not_audiobook('c')} "
            "ORDER BY e.published_date DESC, e.id DESC LIMIT 3",
            (ym, r["d"]),
        ).fetchall()
        days.append({
            "day": int(r["d"]),
            "count": r["n"],
            "previews": [{"id": p["id"], "title": p["title"],
                          "url": config.SITE + f"/radios/{p['id']}"} for p in prev],
            "more": max(0, r["n"] - len(prev)),
            "audiobooks": ab_map.get(r["d"], 0),
        })
    return {"year": yyyy, "month": mm, "days": days}


def stats(conn):
    base = _filters(True, '')
    out = {}
    out["episodes_total"] = conn.execute("SELECT count(*) n FROM episodes").fetchone()["n"]
    out["episodes_published"] = conn.execute(
        f"SELECT count(*) n FROM episodes WHERE {base}").fetchone()["n"]
    out["episodes_paid"] = conn.execute(
        f"SELECT count(*) n FROM episodes WHERE {base} AND is_require_privilege=1"
    ).fetchone()["n"]
    out["albums"] = conn.execute("SELECT count(*) n FROM albums").fetchone()["n"]
    out["albums_official"] = conn.execute(
        "SELECT count(*) n FROM albums WHERE owner_type='gcores'").fetchone()["n"]
    out["albums_paid"] = conn.execute(
        "SELECT count(*) n FROM albums WHERE is_require_privilege=1").fetchone()["n"]
    out["categories"] = conn.execute("SELECT count(*) n FROM categories").fetchone()["n"]
    out["comments"] = conn.execute("SELECT count(*) n FROM comments").fetchone()["n"]
    out["users"] = conn.execute("SELECT count(*) n FROM users").fetchone()["n"]
    row = conn.execute(
        f"SELECT min(published_date) mn, max(published_date) mx FROM episodes WHERE {base}"
    ).fetchone()
    out["date_range"] = [row["mn"], row["mx"]]
    out["categories_top"] = [
        {"name": r["name"], "count": r["n"]}
        for r in conn.execute(
            "SELECT c.name AS name, count(*) AS n FROM episodes e "
            "LEFT JOIN categories c ON c.id=e.category_id "
            f"WHERE {_filters(True, 'e')} AND c.name IS NOT NULL "
            "GROUP BY c.name ORDER BY n DESC LIMIT 12")
    ]
    for k in ("albums_done_at", "sweep_done_at", "membership_done_at",
              "comments_done_at", "last_incremental_at"):
        out[k] = store_get_meta(conn, k)
    return out


def store_get_meta(conn, key):
    row = conn.execute("SELECT value FROM crawl_meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None
