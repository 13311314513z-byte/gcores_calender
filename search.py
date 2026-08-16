# -*- coding: utf-8 -*-
"""检索层：FTS5 trigram 全文检索 + 短词 LIKE 回退 + 关键词自动提示。"""
import re

import config

_WS = re.compile(r"\s+")


def _fts_query(q):
    """把用户输入转成 trigram 可用的 FTS5 查询：按空白分词，逐词加引号。"""
    terms = [t.strip() for t in _WS.split(q) if t.strip()]
    return " ".join('"' + t.replace('"', '""') + '"' for t in terms)


def _base_where(official_only):
    w = "e.is_published=1"
    if official_only:
        w += " AND e.owner_type='gcores'"
    return w


def search(conn, q, limit=30, official_only=None):
    """关键词检索：标题/副标题/简介/正文（FTS5）+ 分类名（LIKE）+ 参与者昵称。"""
    if official_only is None:
        official_only = config.DEFAULT_OFFICIAL_ONLY
    q = (q or "").strip()
    if not q:
        return []
    base_w = _base_where(official_only)
    like = "%" + q + "%"
    rows = []
    if len(q) >= 3:
        try:
            rows = conn.execute(
                "SELECT e.*, c.name AS category_name, a.title AS album_title "
                "FROM episodes_fts f JOIN episodes e ON e.id=f.rowid "
                "LEFT JOIN categories c ON c.id=e.category_id "
                "LEFT JOIN albums a ON a.id=e.album_id "
                f"WHERE episodes_fts MATCH ? AND {base_w} "
                "ORDER BY e.published_date DESC, e.id DESC LIMIT ?",
                (_fts_query(q), limit),
            ).fetchall()
        except Exception:
            rows = []
    if len(rows) < limit:
        extra = conn.execute(
            "SELECT e.*, c.name AS category_name, a.title AS album_title "
            "FROM episodes e "
            "LEFT JOIN categories c ON c.id=e.category_id "
            "LEFT JOIN albums a ON a.id=e.album_id "
            f"WHERE {base_w} AND (e.title LIKE ? OR e.subtitle LIKE ? "
            "OR e.page_desc LIKE ? OR c.name LIKE ?) "
            "ORDER BY e.published_date DESC, e.id DESC LIMIT ?",
            (like, like, like, like, limit - len(rows)),
        ).fetchall()
        seen = {r["id"] for r in rows}
        rows.extend(r for r in extra if r["id"] not in seen)
    # 参与者昵称匹配（用户搜索）
    if len(rows) < limit:
        user_rows = conn.execute(
            "SELECT DISTINCT e.*, c.name AS category_name, a.title AS album_title "
            "FROM episodes e "
            "LEFT JOIN categories c ON c.id=e.category_id "
            "LEFT JOIN albums a ON a.id=e.album_id "
            f"WHERE {base_w} AND EXISTS ("
            "SELECT 1 FROM episode_djs d JOIN users u ON u.id=d.user_id "
            "WHERE d.radio_id=e.id AND u.nickname LIKE ?) "
            "ORDER BY e.published_date DESC, e.id DESC LIMIT ?",
            (like, limit - len(rows)),
        ).fetchall()
        seen = {r["id"] for r in rows}
        rows.extend(r for r in user_rows if r["id"] not in seen)
    return rows


def suggest(conn, prefix, limit=10):
    """关键词提示：词表前缀匹配 + 标题前缀匹配 + 参与者昵称匹配。"""
    prefix = (prefix or "").strip().lower()
    if not prefix:
        return []
    out = []
    for row in conn.execute(
        "SELECT keyword, count FROM keywords WHERE keyword LIKE ? "
        "ORDER BY count DESC, length(keyword) ASC LIMIT ?",
        (prefix + "%", limit),
    ):
        out.append({"keyword": row["keyword"], "count": row["count"]})
    if len(out) < limit:
        n = limit - len(out)
        for row in conn.execute(
            "SELECT title FROM episodes WHERE title LIKE ? AND is_published=1 "
            "ORDER BY published_date DESC LIMIT ?",
            (prefix + "%", n),
        ):
            out.append({"keyword": row["title"], "count": None, "is_title": True})
    if len(out) < limit:
        n = limit - len(out)
        for row in conn.execute(
            "SELECT DISTINCT u.nickname FROM episode_djs d "
            "JOIN users u ON u.id=d.user_id "
            "WHERE u.nickname LIKE ? LIMIT ?",
            (prefix + "%", n),
        ):
            out.append({"keyword": row["nickname"], "count": None, "is_user": True})
    return out


def format_duration(seconds):
    """秒 → '1小时23分' / '45分钟' / '32秒'。"""
    try:
        s = int(seconds or 0)
    except (TypeError, ValueError):
        return ""
    if s <= 0:
        return ""
    if s < 60:
        return f"{s}秒"
    m = s // 60
    if m < 60:
        return f"{m}分钟"
    h, mm = divmod(m, 60)
    if h >= 24:
        d, hh = divmod(h, 24)
        return f"{d}天{hh}小时"
    return f"{h}小时{mm}分"
