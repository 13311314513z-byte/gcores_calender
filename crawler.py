# -*- coding: utf-8 -*-
"""抓取器：全量回填 + 每日增量。仅抓取公开元数据与公开评论文本。"""
import logging
import time
from datetime import datetime

import config
import store
from gapi import GapiClient, GapiError

log = logging.getLogger("crawler")

TZ_OFFSET = "+08:00"


def now_iso():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def parse_published_date(published_at):
    """'2013-04-23T09:50:16.000+08:00' → '2013-04-23'（东八区日期）"""
    if not published_at:
        return None
    try:
        dt = datetime.fromisoformat(published_at)
        return dt.date().isoformat()
    except Exception:
        return published_at[:10]


def build_included_map(data):
    m = {}
    for item in data or []:
        m[(item.get("type"), str(item.get("id")))] = item
    return m


def parse_user(item):
    if not item:
        return None
    a = item.get("attributes", {})
    uid = item.get("id")
    return {
        "id": int(uid),
        "nickname": a.get("nickname"),
        "thumb": a.get("thumb"),
        "location": a.get("location"),
        "intro": a.get("intro"),
        "followers_count": a.get("followers-count"),
        "has_membership": a.get("has-membership"),
        "is_gcores_official": a.get("is-gcores-official"),
        "is_pro": a.get("is-pro"),
        "is_deleted": a.get("is-deleted"),
        "url": config.SITE + f"/users/{uid}",
    }


def parse_category(item):
    if not item:
        return None
    a = item.get("attributes", {})
    return {
        "id": int(item.get("id")),
        "name": a.get("name"),
        "desc": a.get("desc"),
        "logo": a.get("logo"),
        "subscriptions_count": a.get("subscriptions-count"),
    }


def parse_radio(radio_obj, included=None):
    """radio_obj: JSON:API 资源对象 → episode dict（含分类与参与者 id）。"""
    included = included or {}
    a = radio_obj.get("attributes", {})
    rel = radio_obj.get("relationships", {})
    rid = int(radio_obj.get("id"))
    ep = {
        "id": rid,
        "title": a.get("title"),
        "subtitle": a.get("desc"),
        "page_desc": a.get("excerpt") or a.get("desc") or "",
        "content_text": store.extract_draftjs_text(a.get("content")),
        "cover": a.get("cover") or a.get("thumb"),
        "published_at": a.get("published-at"),
        "published_date": parse_published_date(a.get("published-at")),
        "duration": a.get("duration"),
        "vol": a.get("vol"),
        "is_free": a.get("is-free"),
        "is_require_privilege": a.get("is-require-privilege"),
        "is_program_preview": a.get("is-program-preview"),
        "is_limited_free": a.get("is-limited-free"),
        "is_published": a.get("is-published"),
        "is_listable": a.get("is-listable"),
        "is_fm": a.get("is-fm"),
        "is_news": a.get("is-news"),
        "owner_type": a.get("owner-type"),
        "plays": a.get("plays"),
        "likes_count": a.get("likes-count"),
        "comments_count": a.get("comments-count"),
        "url": config.SITE + f"/radios/{rid}",
    }
    # 分类
    cat_data = (rel.get("category") or {}).get("data")
    if cat_data and included:
        cat_item = included.get(("categories", str(cat_data.get("id"))))
        if cat_item:
            ep["category_id"] = int(cat_item.get("id"))
            cat = parse_category(cat_item)
            if cat:
                ep["category_name"] = cat["name"]
    # 参与者（djs）
    ep["djs"] = []
    djs_data = (rel.get("djs") or {}).get("data") or []
    for d in djs_data:
        if included:
            u = included.get(("users", str(d.get("id"))))
            if u:
                ep["djs"].append(parse_user(u))
            else:
                ep["djs"].append({"id": int(d.get("id")), "nickname": None})
        else:
            ep["djs"].append({"id": int(d.get("id")), "nickname": None})
    return ep


def upsert_episode_with_related(conn, ep):
    """写入 episode + category + users + djs。"""
    if ep.get("category_name"):
        store.upsert_category(
            conn, ep["category_id"], ep["category_name"], last_seen=now_iso()
        )
    store.upsert_episode(conn, ep)
    for pos, dj in enumerate(ep.get("djs") or [], start=1):
        if dj.get("nickname") is not None:
            store.upsert_user(conn, dj, last_seen=now_iso())
        store.upsert_dj(conn, ep["id"], dj["id"], pos)


# ---------------- 全量回填 ----------------

def backfill_albums(client, conn):
    """抓全部专辑（252 个左右，10/页）。"""
    offset = 0
    total = 0
    while True:
        resp = client.list_albums(offset)
        items = resp.get("data", [])
        if not items:
            break
        for alb in items:
            a = alb.get("attributes", {})
            store.upsert_album(conn, {
                "id": int(alb.get("id")),
                "title": a.get("title"),
                "description": a.get("description"),
                "cover": a.get("cover"),
                "is_free": a.get("is-free"),
                "is_require_privilege": a.get("is-require-privilege"),
                "radios_count": a.get("radios-count"),
                "subscriptions_count": a.get("subscriptions-count"),
                "owner_type": a.get("owner-type"),
                "created_at": a.get("created-at"),
                "updated_at": a.get("updated-at"),
                "is_published": a.get("is-published"),
            }, last_seen=now_iso())
            total += 1
        conn.commit()
        log.info("albums offset=%d total=%d", offset, total)
        rc = int((resp.get("meta") or {}).get("record-count", 0))
        if offset + len(items) >= rc:
            break
        offset += len(items)
    log.info("albums done: %d", total)
    store._set_meta(conn, "albums_done_at", now_iso())
    conn.commit()
    return total


def backfill_sweep(client, conn):
    """深扫 /radios?include=category,djs 全量期数（约 30000 行，10/页，支持断点续抓）。"""
    offset = int(store.get_meta(conn, "sweep_offset", 0) or 0)
    total = 0
    first_meta = None
    if offset > 0:
        log.info("sweep resume from offset=%d", offset)
    while True:
        resp = client.list_radios(offset)
        items = resp.get("data", [])
        if not items:
            break
        if first_meta is None:
            first_meta = resp.get("meta", {})
        included = build_included_map(resp.get("included"))
        for radio_obj in items:
            ep = parse_radio(radio_obj, included)
            upsert_episode_with_related(conn, ep)
            total += 1
        conn.commit()
        if offset % 50 == 0:
            store._set_meta(conn, "sweep_offset", offset)
            conn.commit()
            log.info("sweep offset=%d rows=%d", offset, total)
        rc = int(first_meta.get("record-count", 0))
        if rc and offset + len(items) >= rc:
            break
        offset += len(items)
    log.info("sweep done: %d rows", total)
    store._set_meta(conn, "sweep_done_at", now_iso())
    store._set_meta(conn, "sweep_rows", total)
    store._set_meta(conn, "sweep_offset", 0)
    conn.commit()
    return total


def backfill_categories(client, conn):
    """按分类全量补抓：/categories/{id}/radios 是付费期数的完整数据源
    （公开 /radios 列表会漏掉早期会员/付费期数，如录音笔 VOL.1~237）。"""
    cats = conn.execute("SELECT id, name FROM categories ORDER BY id").fetchall()
    cursor = int(store.get_meta(conn, "categories_cursor", 0) or 0)
    done = 0
    for cat in cats:
        cid = cat["id"]
        if cid <= cursor:
            continue
        offset = 0
        n = 0
        while True:
            resp = client.get(
                f"/categories/{cid}/radios",
                {"page[offset]": offset, "include": "category,djs"},
            )
            items = resp.get("data", [])
            if not items:
                break
            included = build_included_map(resp.get("included"))
            for radio_obj in items:
                ep = parse_radio(radio_obj, included)
                if not ep.get("category_id"):
                    ep["category_id"] = cid
                upsert_episode_with_related(conn, ep)
                n += 1
            conn.commit()
            rc = int((resp.get("meta") or {}).get("record-count", 0))
            if rc and offset + len(items) >= rc:
                break
            offset += len(items)
        store._set_meta(conn, "categories_cursor", cid)
        conn.commit()
        done += 1
        log.info("categories done=%d/%d (cat %s: %d episodes)", done, len(cats), cid, n)
    store._set_meta(conn, "categories_done_at", now_iso())
    store._set_meta(conn, "categories_cursor", 0)
    conn.commit()
    log.info("categories backfill finished: %d categories", done)


def backfill_album_membership(client, conn):
    """补录 album_id：每个专辑拉 /albums/{id}/radios（断点续抓）。"""
    rows = conn.execute(
        "SELECT id FROM albums WHERE is_published=1 AND radios_count>0 ORDER BY id"
    ).fetchall()
    cursor = int(store.get_meta(conn, "membership_cursor", 0) or 0)
    done = 0
    skipped = 0
    for r in rows:
        album_id = r["id"]
        if album_id <= cursor:
            skipped += 1
            continue
        offset = 0
        ids = []
        while True:
            resp = client.list_album_radios(album_id, offset)
            items = resp.get("data", [])
            if not items:
                break
            for radio_obj in items:
                ids.append(int(radio_obj.get("id")))
            if len(items) < 10:
                break
            offset += len(items)
        if ids:
            store.set_episode_album(conn, album_id, ids)
        store._set_meta(conn, "membership_cursor", album_id)
        conn.commit()
        done += 1
        if done % 25 == 0:
            log.info("membership albums=%d/%d (skipped=%d)", done, len(rows), skipped)
    log.info("album membership done: %d albums (skipped=%d)", done, skipped)
    store._set_meta(conn, "membership_done_at", now_iso())
    conn.commit()


def parse_comment(comment_obj, included):
    a = comment_obj.get("attributes", {})
    cid = int(comment_obj.get("id"))
    user = None
    user_data = ((comment_obj.get("relationships") or {}).get("user") or {}).get("data")
    if user_data and included:
        user = parse_user(included.get(("users", str(user_data.get("id")))))
    return {
        "id": cid,
        "body": a.get("body"),
        "likes_count": a.get("likes-count"),
        "score": a.get("score"),
        "depth": a.get("depth"),
        "created_at": a.get("created-at"),
        "user_id": user["id"] if user else None,
        "nickname": user["nickname"] if user else None,
        "thumb": user["thumb"] if user else None,
        "is_gcores_official": user["is_gcores_official"] if user else None,
        "fetched_at": now_iso(),
    }


def fetch_top_comments(client, radio_id, top_n=3):
    """拉某期数按 score 权重降序的前 top_n 条精华评论（depth=0 优先）。"""
    resp = client.list_comments(radio_id, 0)
    included = build_included_map(resp.get("included"))
    comments = [parse_comment(c, included) for c in resp.get("data", [])]
    top_level = [c for c in comments if c["depth"] == 0]
    rest = [c for c in comments if c["depth"] != 0]
    ranked = (top_level + rest)[:top_n]
    return ranked


def backfill_comments(client, conn, top_n=3):
    """为已发布官方期数抓精华评论前三（断点续抓；只处理还没有评论的期数）。"""
    cursor = int(store.get_meta(conn, "comments_cursor", 0) or 0)
    rows = conn.execute(
        "SELECT e.id FROM episodes e WHERE e.is_published=1 AND e.owner_type='gcores' "
        "AND NOT EXISTS (SELECT 1 FROM comments c WHERE c.radio_id=e.id) AND e.id>? "
        "ORDER BY e.id",
        (cursor,),
    ).fetchall()
    log.info("comments backfill: %d episodes missing comments (cursor=%d)", len(rows), cursor)
    done = 0
    errors = 0
    for r in rows:
        rid = r["id"]
        if rid <= cursor:
            continue
        try:
            ranked = fetch_top_comments(client, rid, top_n)
            store.replace_comments(conn, rid, ranked)
            done += 1
        except GapiError as e:
            errors += 1
            if "404" in str(e) or "400" in str(e) or "403" in str(e):
                log.warning("comments skip rid=%d: %s", rid, e)
                done += 1  # 不重试的硬错误也推进游标
            else:
                log.warning("comments retry later rid=%d: %s", rid, e)
                break  # 软错误：保留游标，下次续
        except Exception as e:
            log.warning("comments error rid=%d: %s", rid, e)
            break
        if done % 50 == 0:
            store._set_meta(conn, "comments_cursor", rid)
            conn.commit()
            log.info("comments done=%d errors=%d cursor=%d", done, errors, rid)
    store._set_meta(conn, "comments_cursor", rows[-1]["id"] if rows else cursor)
    store._set_meta(conn, "comments_done_at", now_iso())
    conn.commit()
    log.info("comments backfill finished: done=%d errors=%d", done, errors)


# ---------------- 每日增量 ----------------

def incremental(client, conn):
    """每日增量：新期数（详情+评论）+ 新专辑 + 近 N 天评论刷新。"""
    log.info("incremental start")
    t0 = time.time()

    # 1) 新专辑
    try:
        resp = client.list_albums(0)
        for alb in resp.get("data", []):
            a = alb.get("attributes", {})
            store.upsert_album(conn, {
                "id": int(alb.get("id")), "title": a.get("title"),
                "description": a.get("description"), "cover": a.get("cover"),
                "is_free": a.get("is-free"),
                "is_require_privilege": a.get("is-require-privilege"),
                "radios_count": a.get("radios-count"),
                "subscriptions_count": a.get("subscriptions-count"),
                "owner_type": a.get("owner-type"),
                "created_at": a.get("created-at"), "updated_at": a.get("updated-at"),
                "is_published": a.get("is-published"),
            }, last_seen=now_iso())
        conn.commit()
    except GapiError as e:
        log.warning("incremental albums failed: %s", e)

    # 2) 新期数：latest-radios?include=radio → 未见过的 id 拉详情
    new_ids = []
    try:
        resp = client.get("/latest-radios", {"include": "radio"})
        for item in resp.get("data", []):
            rel = (item.get("relationships") or {}).get("radio") or {}
            rd = rel.get("data")
            if rd:
                rid = int(rd.get("id"))
                row = conn.execute("SELECT 1 FROM episodes WHERE id=?", (rid,)).fetchone()
                if not row:
                    new_ids.append(rid)
    except GapiError as e:
        log.warning("latest-radios failed: %s", e)
    # 备用路径：新专辑的首期
    try:
        for alb in conn.execute(
            "SELECT id FROM albums ORDER BY id DESC LIMIT 5"
        ).fetchall():
            resp = client.list_album_radios(alb["id"], 0)
            for radio_obj in resp.get("data", []):
                rid = int(radio_obj.get("id"))
                if not conn.execute("SELECT 1 FROM episodes WHERE id=?", (rid,)).fetchone():
                    new_ids.append(rid)
    except GapiError as e:
        log.warning("album-radios incremental failed: %s", e)

    new_ids = sorted(set(new_ids))
    log.info("incremental: %d new episodes", len(new_ids))
    for rid in new_ids:
        try:
            resp = client.get_radio(rid)
            included = build_included_map(resp.get("included"))
            ep = parse_radio(resp.get("data"), included)
            upsert_episode_with_related(conn, ep)
            conn.commit()
            try:
                ranked = fetch_top_comments(client, rid)
                store.replace_comments(conn, rid, ranked)
                conn.commit()
            except GapiError as e:
                log.warning("incremental comments rid=%d: %s", rid, e)
        except GapiError as e:
            log.warning("incremental radio rid=%d: %s", rid, e)
            continue

    # 3) 近 N 天期数评论刷新 + 播放/点赞/评论数刷新（免费期数跟上最新值；付费期数 plays 保持 NULL）
    days = config.INCREMENTAL_COMMENT_DAYS
    recent = conn.execute(
        "SELECT id FROM episodes WHERE is_published=1 "
        "AND owner_type='gcores' AND published_date>=date('now','localtime','-%d days')" % days
    ).fetchall()
    log.info("incremental: refresh comments/plays for %d recent episodes", len(recent))
    for r in recent:
        rid = r["id"]
        try:
            ranked = fetch_top_comments(client, rid)
            store.replace_comments(conn, rid, ranked)
        except GapiError as e:
            log.warning("refresh comments rid=%d: %s", rid, e)
        try:
            d = client.get_radio(rid, include="")
            attrs = (d.get("data") or {}).get("attributes", {})
            conn.execute(
                "UPDATE episodes SET plays=?, likes_count=?, comments_count=? WHERE id=?",
                (attrs.get("plays"), attrs.get("likes-count"), attrs.get("comments-count"), rid),
            )
            conn.commit()
        except GapiError as e:
            log.warning("refresh plays rid=%d: %s", rid, e)

    store._set_meta(conn, "last_incremental_at", now_iso())
    conn.commit()
    log.info("incremental done in %.1fs (%d new)", time.time() - t0, len(new_ids))
    return len(new_ids)
