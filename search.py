# -*- coding: utf-8 -*-
"""检索层：FTS5 trigram 全文检索 + 短词 LIKE 回退 + 参与者昵称 + 拼音/同音容错 + 组合过滤。"""
import re

import config
import pinyin as P

_WS = re.compile(r"\s+")

# 进程级拼音索引缓存
_py_index = None
_py_nick_index = None


def _fts_query(q):
    """把用户输入转成 trigram 可用的 FTS5 查询：按空白分词，逐词加引号。"""
    terms = [t.strip() for t in _WS.split(q) if t.strip()]
    return " ".join('"' + t.replace('"', '""') + '"' for t in terms)


def _base_where(official_only):
    w = "e.is_published=1"
    if official_only:
        w += " AND e.owner_type='gcores'"
    return w


def _extra_where(category=None, paid=None, album=None, date_from=None, date_to=None):
    conds, params = [], []
    if category:
        conds.append("c.name = ?")
        params.append(category)
    if paid is not None:
        conds.append("e.is_require_privilege = ?")
        params.append(1 if paid else 0)
    if album:
        conds.append("a.title = ?")
        params.append(album)
    if date_from:
        conds.append("e.published_date >= ?")
        params.append(date_from)
    if date_to:
        conds.append("e.published_date <= ?")
        params.append(date_to)
    return (" AND " + " AND ".join(conds)) if conds else "", params


def _build_py_index(conn):
    global _py_index
    if _py_index is not None:
        return _py_index
    idx = {}
    rows = conn.execute(
        "SELECT e.id, e.title, e.subtitle, c.name AS cn FROM episodes e "
        "LEFT JOIN categories c ON c.id=e.category_id WHERE e.is_published=1"
    ).fetchall()
    dj = {}
    for r in conn.execute(
        "SELECT d.radio_id, u.nickname FROM episode_djs d "
        "JOIN users u ON u.id=d.user_id"):
        dj.setdefault(r["radio_id"], []).append(r["nickname"] or "")
    for r in rows:
        text = " ".join([r["title"] or "", r["subtitle"] or "", r["cn"] or ""]
                        + dj.get(r["id"], []))
        idx[r["id"]] = P.pinyinize(text)
    _py_index = idx
    return idx


def _build_py_nick_index(conn):
    global _py_nick_index
    if _py_nick_index is not None:
        return _py_nick_index
    _py_nick_index = [
        {"nickname": r["nickname"], "py": P.pinyinize(r["nickname"] or "")}
        for r in conn.execute("SELECT DISTINCT nickname FROM users WHERE nickname IS NOT NULL")
    ]
    return _py_nick_index


def _pinyin_matches(conn, pq, base_w, extra_w, extra_params, limit):
    """按拼音串子串匹配期数 id，再按过滤条件取行。"""
    idx = _build_py_index(conn)
    ids = [eid for eid, py in idx.items() if pq in py]
    if not ids:
        return []
    qmarks = ",".join("?" * len(ids))
    return conn.execute(
        "SELECT e.*, c.name AS category_name, a.title AS album_title "
        "FROM episodes e "
        "LEFT JOIN categories c ON c.id=e.category_id "
        "LEFT JOIN albums a ON a.id=e.album_id "
        f"WHERE e.id IN ({qmarks}) AND {base_w}{extra_w} "
        "ORDER BY e.published_date DESC, e.id DESC LIMIT ?",
        ids + extra_params + [limit],
    ).fetchall()


def snippet(q, row, width=60):
    """命中片段：在页面简介/正文中定位关键词，返回上下文窗口。"""
    ql = q.lower()
    for field in ("page_desc", "content_text"):
        text = row[field] or ""
        if not text:
            continue
        i = text.lower().find(ql)
        if i >= 0:
            start = max(0, i - width)
            end = min(len(text), i + len(q) + width)
            prefix = "…" if start > 0 else ""
            suffix = "…" if end < len(text) else ""
            return prefix + text[start:end].replace("\n", " ").strip() + suffix
    return ""


def search(conn, q, limit=30, official_only=None, category=None, paid=None,
           album=None, date_from=None, date_to=None):
    """关键词检索：FTS5 全文 + 短词 LIKE + 参与者昵称 + 拼音/同音容错 + 组合过滤。"""
    if official_only is None:
        official_only = config.DEFAULT_OFFICIAL_ONLY
    q = (q or "").strip()
    if not q:
        return []
    base_w = _base_where(official_only)
    extra_w, extra_params = _extra_where(category, paid, album, date_from, date_to)
    like = "%" + q + "%"
    rows = []
    if len(q) >= 3 and not P.has_latin(q):
        try:
            rows = conn.execute(
                "SELECT e.*, c.name AS category_name, a.title AS album_title "
                "FROM episodes_fts f JOIN episodes e ON e.id=f.rowid "
                "LEFT JOIN categories c ON c.id=e.category_id "
                "LEFT JOIN albums a ON a.id=e.album_id "
                f"WHERE episodes_fts MATCH ? AND {base_w}{extra_w} "
                "ORDER BY e.published_date DESC, e.id DESC LIMIT ?",
                (_fts_query(q), *extra_params, limit),
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
            f"OR e.page_desc LIKE ? OR c.name LIKE ?){extra_w} "
            "ORDER BY e.published_date DESC, e.id DESC LIMIT ?",
            (like, like, like, like, *extra_params, limit - len(rows)),
        ).fetchall()
        seen = {r["id"] for r in rows}
        rows.extend(r for r in extra if r["id"] not in seen)
    # 参与者昵称匹配
    if len(rows) < limit:
        user_rows = conn.execute(
            "SELECT DISTINCT e.*, c.name AS category_name, a.title AS album_title "
            "FROM episodes e "
            "LEFT JOIN categories c ON c.id=e.category_id "
            "LEFT JOIN albums a ON a.id=e.album_id "
            f"WHERE {base_w} AND EXISTS ("
            "SELECT 1 FROM episode_djs d JOIN users u ON u.id=d.user_id "
            f"WHERE d.radio_id=e.id AND u.nickname LIKE ?){extra_w} "
            "ORDER BY e.published_date DESC, e.id DESC LIMIT ?",
            (like, *extra_params, limit - len(rows)),
        ).fetchall()
        seen = {r["id"] for r in rows}
        rows.extend(r for r in user_rows if r["id"] not in seen)
    # 拼音 / 同音容错匹配
    if len(rows) < limit:
        pq = P.pinyinize(q)
        if pq and (P.has_latin(q) or len(q) >= 2):
            py_rows = _pinyin_matches(conn, pq, base_w, extra_w, extra_params,
                                      limit - len(rows))
            seen = {r["id"] for r in rows}
            rows.extend(r for r in py_rows if r["id"] not in seen)
    return rows


def suggest(conn, prefix, limit=10):
    """关键词提示：词表前缀 + 标题前缀 + 参与者昵称 + 拼音前缀。"""
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
    # 拼音前缀提示（拉丁输入，如 ximeng → 西蒙）
    if len(out) < limit and P.has_latin(prefix):
        n = limit - len(out)
        for nick in _build_py_nick_index(conn):
            if nick["py"].startswith(prefix):
                out.append({"keyword": nick["nickname"], "count": None, "is_user": True})
                if len(out) >= limit:
                    break
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
