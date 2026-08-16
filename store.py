# -*- coding: utf-8 -*-
"""SQLite 存储层：建表、upsert、查询。全部标准库 sqlite3。"""
import json
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    desc TEXT DEFAULT '',
    logo TEXT DEFAULT '',
    subscriptions_count INTEGER DEFAULT 0,
    last_seen TEXT
);

CREATE TABLE IF NOT EXISTS albums (
    id INTEGER PRIMARY KEY,
    title TEXT,
    description TEXT,
    cover TEXT,
    is_free INTEGER,
    is_require_privilege INTEGER,
    radios_count INTEGER,
    subscriptions_count INTEGER,
    owner_type TEXT,
    created_at TEXT,
    updated_at TEXT,
    is_published INTEGER,
    last_seen TEXT
);

CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY,
    title TEXT,
    subtitle TEXT,
    page_desc TEXT,
    content_text TEXT,
    category_id INTEGER,
    cover TEXT,
    published_at TEXT,
    published_date TEXT,
    duration INTEGER,
    vol TEXT,
    is_free INTEGER,
    is_require_privilege INTEGER,
    is_program_preview INTEGER,
    is_limited_free INTEGER,
    is_published INTEGER,
    is_listable INTEGER,
    is_fm INTEGER,
    is_news INTEGER,
    owner_type TEXT,
    plays INTEGER,
    likes_count INTEGER,
    comments_count INTEGER,
    album_id INTEGER,
    url TEXT
);
CREATE INDEX IF NOT EXISTS idx_episodes_date ON episodes(published_date);
CREATE INDEX IF NOT EXISTS idx_episodes_category ON episodes(category_id);
CREATE INDEX IF NOT EXISTS idx_episodes_album ON episodes(album_id);
CREATE INDEX IF NOT EXISTS idx_episodes_owner ON episodes(owner_type);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    nickname TEXT,
    thumb TEXT,
    location TEXT,
    intro TEXT,
    followers_count INTEGER,
    has_membership INTEGER,
    is_gcores_official INTEGER,
    is_pro INTEGER,
    is_deleted INTEGER,
    url TEXT,
    last_seen TEXT
);

CREATE TABLE IF NOT EXISTS episode_djs (
    radio_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    position INTEGER,
    PRIMARY KEY (radio_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_djs_user ON episode_djs(user_id);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY,
    radio_id INTEGER NOT NULL,
    rank INTEGER,
    body TEXT,
    likes_count INTEGER,
    score REAL,
    depth INTEGER,
    created_at TEXT,
    user_id INTEGER,
    nickname TEXT,
    thumb TEXT,
    is_gcores_official INTEGER,
    fetched_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_comments_radio ON comments(radio_id, rank);

CREATE TABLE IF NOT EXISTS crawl_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS keywords (
    keyword TEXT PRIMARY KEY,
    count INTEGER DEFAULT 0
);

CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
    title, subtitle, page_desc, content_text,
    tokenize='trigram'
);
"""


def connect(path=None):
    if path is None:
        from config import DB_PATH
        path = DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_schema(conn):
    conn.executescript(SCHEMA)
    migrate(conn)
    conn.commit()


def migrate(conn):
    """轻量迁移：给已存在的库补新列。"""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(episodes)")}
    if "cover" not in cols:
        conn.execute("ALTER TABLE episodes ADD COLUMN cover TEXT")


# ---------- 通用 upsert ----------

def _set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO crawl_meta(key, value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, str(value)),
    )


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM crawl_meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _int_or_none(v):
    """保持 None（平台未公开的字段，如付费期数 plays）为 NULL。"""
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _bool(v):
    return 1 if v else 0


def upsert_category(conn, cat_id, name, desc="", logo="", subs=0, last_seen=""):
    conn.execute(
        "INSERT INTO categories(id,name,desc,logo,subscriptions_count,last_seen) "
        "VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET name=excluded.name, desc=excluded.desc, "
        "logo=excluded.logo, subscriptions_count=excluded.subscriptions_count, "
        "last_seen=excluded.last_seen",
        (cat_id, name, desc, logo, _int(subs), last_seen),
    )


def upsert_album(conn, alb, last_seen=""):
    conn.execute(
        "INSERT INTO albums(id,title,description,cover,is_free,is_require_privilege,"
        "radios_count,subscriptions_count,owner_type,created_at,updated_at,is_published,last_seen) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET title=excluded.title, description=excluded.description, "
        "cover=excluded.cover, is_free=excluded.is_free, is_require_privilege=excluded.is_require_privilege, "
        "radios_count=excluded.radios_count, subscriptions_count=excluded.subscriptions_count, "
        "owner_type=excluded.owner_type, created_at=excluded.created_at, updated_at=excluded.updated_at, "
        "is_published=excluded.is_published, last_seen=excluded.last_seen",
        (
            alb["id"], alb["title"], alb.get("description"), alb.get("cover"),
            _bool(alb.get("is_free")), _bool(alb.get("is_require_privilege")),
            _int(alb.get("radios_count")), _int(alb.get("subscriptions_count")),
            alb.get("owner_type"), alb.get("created_at"), alb.get("updated_at"),
            _bool(alb.get("is_published")), last_seen,
        ),
    )


def upsert_episode(conn, ep, fts=True):
    """ep: dict of episode fields（含 id, title, subtitle, page_desc, content_text...）"""
    conn.execute(
        "INSERT INTO episodes(id,title,subtitle,page_desc,content_text,category_id,cover,"
        "published_at,published_date,duration,vol,is_free,is_require_privilege,"
        "is_program_preview,is_limited_free,is_published,is_listable,is_fm,is_news,"
        "owner_type,plays,likes_count,comments_count,album_id,url) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET title=excluded.title, subtitle=excluded.subtitle, "
        "page_desc=excluded.page_desc, content_text=excluded.content_text, category_id=excluded.category_id, "
        "cover=excluded.cover, "
        "published_at=excluded.published_at, published_date=excluded.published_date, "
        "duration=excluded.duration, vol=excluded.vol, is_free=excluded.is_free, "
        "is_require_privilege=excluded.is_require_privilege, is_program_preview=excluded.is_program_preview, "
        "is_limited_free=excluded.is_limited_free, is_published=excluded.is_published, "
        "is_listable=excluded.is_listable, is_fm=excluded.is_fm, is_news=excluded.is_news, "
        "owner_type=excluded.owner_type, plays=excluded.plays, likes_count=excluded.likes_count, "
        "comments_count=excluded.comments_count, album_id=excluded.album_id, url=excluded.url",
        (
            ep["id"], ep.get("title"), ep.get("subtitle"), ep.get("page_desc"),
            ep.get("content_text"), ep.get("category_id"), ep.get("cover"),
            ep.get("published_at"), ep.get("published_date"), _int(ep.get("duration")),
            ep.get("vol"), _bool(ep.get("is_free")), _bool(ep.get("is_require_privilege")),
            _bool(ep.get("is_program_preview")), _bool(ep.get("is_limited_free")),
            _bool(ep.get("is_published")), _bool(ep.get("is_listable")),
            _bool(ep.get("is_fm")), _bool(ep.get("is_news")), ep.get("owner_type"),
            _int_or_none(ep.get("plays")), _int(ep.get("likes_count")), _int(ep.get("comments_count")),
            ep.get("album_id"), ep.get("url"),
        ),
    )
    if fts:
        conn.execute("DELETE FROM episodes_fts WHERE rowid=?", (ep["id"],))
        conn.execute(
            "INSERT INTO episodes_fts(rowid,title,subtitle,page_desc,content_text) VALUES(?,?,?,?,?)",
            (ep["id"], ep.get("title") or "", ep.get("subtitle") or "",
             ep.get("page_desc") or "", ep.get("content_text") or ""),
        )


def upsert_user(conn, u, last_seen=""):
    conn.execute(
        "INSERT INTO users(id,nickname,thumb,location,intro,followers_count,"
        "has_membership,is_gcores_official,is_pro,is_deleted,url,last_seen) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET nickname=excluded.nickname, thumb=excluded.thumb, "
        "location=excluded.location, intro=excluded.intro, followers_count=excluded.followers_count, "
        "has_membership=excluded.has_membership, is_gcores_official=excluded.is_gcores_official, "
        "is_pro=excluded.is_pro, is_deleted=excluded.is_deleted, url=excluded.url, "
        "last_seen=excluded.last_seen",
        (
            u["id"], u.get("nickname"), u.get("thumb"), u.get("location"), u.get("intro"),
            _int(u.get("followers_count")), _bool(u.get("has_membership")),
            _bool(u.get("is_gcores_official")), _bool(u.get("is_pro")),
            _bool(u.get("is_deleted")), u.get("url"), last_seen,
        ),
    )


def upsert_dj(conn, radio_id, user_id, position):
    conn.execute(
        "INSERT OR IGNORE INTO episode_djs(radio_id,user_id,position) VALUES(?,?,?)",
        (radio_id, user_id, position),
    )


def replace_comments(conn, radio_id, comments):
    """先删后插某期数的精华评论（rank 1..n）。"""
    conn.execute("DELETE FROM comments WHERE radio_id=?", (radio_id,))
    for i, c in enumerate(comments, start=1):
        conn.execute(
            "INSERT OR REPLACE INTO comments(id,radio_id,rank,body,likes_count,score,depth,"
            "created_at,user_id,nickname,thumb,is_gcores_official,fetched_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                c["id"], radio_id, i, c.get("body"), _int(c.get("likes_count")),
                float(c.get("score") or 0), _int(c.get("depth")), c.get("created_at"),
                c.get("user_id"), c.get("nickname"), c.get("thumb"),
                _bool(c.get("is_gcores_official")), c.get("fetched_at"),
            ),
        )


def rebuild_keywords(conn):
    """从期数标题构建关键词表（中文二元/三元组 + 英文/数字词），供提示用。"""
    import re
    conn.execute("DELETE FROM keywords")
    counter = {}
    cjk = re.compile(r"[\u4e00-\u9fff]+")
    other = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*")

    def add(k):
        k = k.strip().lower()
        if 2 <= len(k) <= 24:
            counter[k] = counter.get(k, 0) + 1

    for row in conn.execute("SELECT title FROM episodes WHERE title IS NOT NULL"):
        title = row["title"]
        for m in cjk.findall(title):
            if len(m) == 1:
                continue
            # 2..6 字滑窗
            for size in (2, 3):
                for i in range(0, len(m) - size + 1):
                    add(m[i:i + size])
        for m in other.findall(title):
            add(m)
    conn.executemany(
        "INSERT OR REPLACE INTO keywords(keyword,count) VALUES(?,?)",
        [(k, v) for k, v in counter.items()],
    )
    conn.commit()


def set_episode_album(conn, album_id, radio_ids):
    conn.executemany(
        "UPDATE episodes SET album_id=? WHERE id=?",
        [(album_id, rid) for rid in radio_ids],
    )


def extract_draftjs_text(content_json):
    """把机核 content 字段（Draft.js JSON）转为纯文本。"""
    if not content_json:
        return ""
    try:
        obj = json.loads(content_json)
    except Exception:
        return str(content_json or "")
    blocks = obj.get("blocks") if isinstance(obj, dict) else None
    if not blocks:
        return ""
    parts = [b.get("text", "") for b in blocks if isinstance(b, dict)]
    return "\n".join(p for p in parts if p)
