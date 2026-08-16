# -*- coding: utf-8 -*-
"""机核播客日历 CLI。用法：
  py gcal.py init                    # 初始化数据库
  py gcal.py backfill                # 全量回填（专辑+期数深扫+归属+关键词）
  py gcal.py comments                # 精华评论前三回填
  py gcal.py incremental             # 每日增量
  py gcal.py today [--year Y] [--page N]
  py gcal.py day 04-23 [--year Y] [--page N]
  py gcal.py month 2026-08
  py gcal.py search 关键词
  py gcal.py suggest 词
  py gcal.py stats
  py gcal.py serve [--port 8000]     # 本地 Web 界面
"""
import argparse
import logging
import sys
from datetime import datetime

import config
import store
from search import format_duration

config.ensure_dirs()


def setup_logging(verbose=False):
    config.setup_logging(verbose=verbose)


def get_conn(args):
    return store.connect(args.db)


def cmd_init(args):
    conn = get_conn(args)
    store.init_schema(conn)
    print(f"数据库已初始化: {args.db}")


def cmd_backfill(args):
    from gapi import GapiClient
    import crawler
    client = GapiClient()
    conn = get_conn(args)
    store.init_schema(conn)
    crawler.backfill_albums(client, conn)
    if not args.skip_categories:
        crawler.backfill_categories(client, conn)
    if not args.skip_sweep:
        crawler.backfill_sweep(client, conn)
    if not args.skip_membership:
        crawler.backfill_album_membership(client, conn)
    store.rebuild_keywords(conn)
    print("回填完成。请运行: py gcal.py comments")


def cmd_categories(args):
    from gapi import GapiClient
    import crawler
    client = GapiClient()
    conn = get_conn(args)
    store.init_schema(conn)
    crawler.backfill_categories(client, conn)
    store.rebuild_keywords(conn)
    print("分类补抓完成。请运行: py gcal.py comments")


def cmd_sweep(args):
    from gapi import GapiClient
    import crawler
    client = GapiClient()
    conn = get_conn(args)
    store.init_schema(conn)
    crawler.backfill_sweep(client, conn)
    print("深扫刷新完成（封面/播放数等已更新）")


def cmd_membership(args):
    from gapi import GapiClient
    import crawler
    client = GapiClient()
    conn = get_conn(args)
    store.init_schema(conn)
    crawler.backfill_album_membership(client, conn)


def cmd_comments(args):
    from gapi import GapiClient
    import crawler
    client = GapiClient()
    conn = get_conn(args)
    store.init_schema(conn)
    crawler.backfill_comments(client, conn, top_n=args.top_n)


def cmd_incremental(args):
    from gapi import GapiClient
    import crawler
    client = GapiClient()
    conn = get_conn(args)
    store.init_schema(conn)
    store.init_plays_history(conn)
    crawler.incremental(client, conn)


def cmd_daily(args):
    """每日一条龙：备份 + 增量抓取 + 播放快照 + 完整性自检。"""
    from gapi import GapiClient
    import crawler
    client = GapiClient()
    conn = get_conn(args)
    store.init_schema(conn)
    store.init_plays_history(conn)
    # 1) 备份
    bak = store.backup_db(args.db)
    print(f"[1/4] 备份完成: {bak}")
    # 2) 增量抓取
    new_n = crawler.incremental(client, conn)
    print(f"[2/4] 增量完成: 新增 {new_n} 期")
    # 3) 播放量快照
    n = store.sample_plays(conn)
    print(f"[3/4] 播放快照: {n} 期已记录")
    # 4) 完整性自检
    problems = crawler.integrity_check(client, conn)
    if problems:
        print(f"[4/4] 完整性自检: ⚠️ {len(problems)} 个分类不一致 -> {problems}")
    else:
        print("[4/4] 完整性自检: ✅ 全部一致")


def cmd_backup(args):
    bak = store.backup_db(args.db)
    print(f"备份完成: {bak}")


def cmd_hot(args):
    conn = get_conn(args)
    store.init_plays_history(conn)
    rows = store.hot_episodes(conn, days=args.days, limit=args.limit)
    print(f"===== 近 {args.days} 天播放增长榜（Top {args.limit}）=====")
    if not rows:
        print("（暂无数据：每日增量时会自动记录播放快照）")
        return
    for i, r in enumerate(rows, 1):
        print(f"{i:>2}. +{r['delta']:,} 播放（共 {r['now_plays']:,}）| {r['published_date']} | {r['title']}")
        print(f"     {r['url']}")


def cmd_keywords(args):
    conn = get_conn(args)
    store.rebuild_keywords(conn)
    print("关键词表已重建")


# ---------------- 展示 ----------------

def _card_lines(e):
    lines = []
    badges = []
    if e["category_name"]:
        badges.append(e["category_name"])
    if e.get("is_require_privilege"):
        badges.append("付费")
    elif not e.get("is_free"):
        badges.append("收费")
    badge = "[" + "|".join(badges) + "]" if badges else ""
    title = f"{e['title']} {badge}".strip()
    lines.append(title)
    if e.get("subtitle"):
        lines.append(f"  副标题: {e['subtitle']}")
    meta = []
    if e.get("duration"):
        meta.append(f"时长 {format_duration(e['duration'])}")
    if e.get("comments_count") is not None:
        meta.append(f"评论 {e['comments_count']}条")
    if e.get("plays") is not None:
        meta.append(f"播放 {e['plays']}")
    elif e.get("is_require_privilege"):
        meta.append("播放 --（会员专享）")
    if meta:
        lines.append("  " + "  ".join(meta))
    if e.get("album_title"):
        lines.append(f"  所属频道: {e['album_title']}")
    if e.get("cover"):
        lines.append(f"  头图: https://image.gcores.com/{e['cover']}")
    if e["djs"]:
        names = "、".join(f"@{d['nickname'] or d['user_id']}" for d in e["djs"])
        lines.append(f"  参与者: {names}")
    if e["comments"]:
        lines.append("  精华评论:")
        for c in e["comments"]:
            who = c["nickname"] or f"用户{c['user_id']}" if c.get("user_id") else "匿名"
            lines.append(f"    💬 {c['body'][:80]}{'…' if len(c['body'] or '') > 80 else ''} (👍{c['likes_count']} {who})")
    lines.append(f"  https://www.gcores.com/radios/{e['id']}")
    return lines


def cmd_today(args):
    import calendar_view
    conn = get_conn(args)
    md = calendar_view.today_md()
    data = calendar_view.day_data(conn, md, year=args.year, page=args.page,
                                  official_only=not args.all,
                                  include_audiobooks=True if args.audiobooks else "compact")
    _print_day(data, md, args.all, args.audiobooks)


def cmd_day(args):
    import calendar_view
    conn = get_conn(args)
    md = args.date
    data = calendar_view.day_data(conn, md, year=args.year, page=args.page,
                                  official_only=not args.all,
                                  include_audiobooks=True if args.audiobooks else "compact")
    _print_day(data, md, args.all, args.audiobooks)


def _print_day(data, md, all_flag, show_ab=False):
    if not data["episodes"] and not data["audiobooks_count"]:
        print(f"{md}：该日无历史节目记录" + ("（含全量）" if all_flag else "（官方节目）"))
        return
    scope = "全部内容" if all_flag else "官方节目"
    ab_note = f"，另有有声书 {data['audiobooks_count']} 期" if data["audiobooks_count"] else ""
    print(f"===== {md} 历史上的机核播客（{scope}，共 {data['total_episodes']} 期{ab_note}，最新在前）=====")
    if data["episodes"]:
        for e in data["episodes"]:
            print()
            for ln in _card_lines(e):
                print(ln)
    elif data["audiobooks_count"]:
        print("（该日无非有声书节目）")
    # 有声书另列（默认紧凑单行；--audiobooks 显示完整卡片）
    if data["audiobooks_count"]:
        print()
        print(f"----- 📖 机核有声书（{data['audiobooks_count']} 期 · 另列）-----")
        if show_ab:
            for e in data["audiobooks"]:
                print()
                for ln in _card_lines(e):
                    print(ln)
        else:
            for e in data["audiobooks"]:
                print(f"📖 {e['published_date']} | {e['title']} | {e['url']}")


def cmd_month(args):
    import calendar_view
    conn = get_conn(args)
    yyyy, mm = int(args.ym[:4]), int(args.ym[5:7])
    data = calendar_view.month_data(conn, yyyy, mm, official_only=not args.all)
    print(f"===== {yyyy}-{mm:02d} 机核播客月历 =====")
    for d in data["days"]:
        prev = "、".join(p["title"] for p in d["previews"])
        more = f" 等{d['count']}期" if d["count"] > len(d["previews"]) else ""
        ab = f"  📖有声书{d['audiobooks']}期另列" if d.get("audiobooks") else ""
        print(f"{d['day']:02d}日: {prev}{more}{ab}")


def cmd_search(args):
    from search import search
    conn = get_conn(args)
    rows = search(conn, args.q, limit=args.limit, official_only=not args.all,
                  category=args.category, paid=args.paid, album=args.album,
                  date_from=args.frm, date_to=args.to)
    print(f"===== 搜索「{args.q}」共 {len(rows)} 条 =====")
    for r in rows:
        e = {
            "id": r["id"], "title": r["title"], "subtitle": r["subtitle"],
            "page_desc": r["page_desc"], "duration": r["duration"],
            "comments_count": r["comments_count"], "plays": r["plays"],
            "is_free": r["is_free"], "is_require_privilege": r["is_require_privilege"],
            "is_program_preview": r["is_program_preview"],
            "category_name": r["category_name"], "album_title": r["album_title"],
            "published_date": r["published_date"], "djs": [], "comments": [],
        }
        print()
        print(f"[{r['published_date']}] {e['title']}")
        if e["subtitle"]:
            print(f"  副标题: {e['subtitle']}")
        print(f"  {r['url']}")


def cmd_suggest(args):
    from search import suggest
    conn = get_conn(args)
    for s in suggest(conn, args.q, limit=args.limit):
        tag = "（标题）" if s.get("is_title") else f"(出现{s['count']}次)"
        print(f"{s['keyword']} {tag}")


def cmd_stats(args):
    import calendar_view
    conn = get_conn(args)
    s = calendar_view.stats(conn)
    print("===== 索引统计 =====")
    print(f"版本: {config.APP_NAME} v{s['version']}")
    print(f"期数(全量): {s['episodes_total']}   已发布官方: {s['episodes_published']}   付费: {s['episodes_paid']}")
    print(f"播客频道(系列): {s['albums']} (官方 {s['albums_official']})   分类: {s['categories']}")
    print(f"精华评论: {s['comments']}   用户: {s['users']}")
    print(f"日期范围: {s['date_range'][0]} ~ {s['date_range'][1]}")
    print(f"albums: {s['albums_done_at']}  sweep: {s['sweep_done_at']}  membership: {s['membership_done_at']}")
    print(f"comments: {s['comments_done_at']}  最近增量: {s['last_incremental_at']}")


def cmd_channel(args):
    import calendar_view
    conn = get_conn(args)
    chan = conn.execute("SELECT * FROM albums WHERE id=?", (args.id,)).fetchone()
    if not chan:
        print(f"频道 {args.id} 不存在")
        return
    total = conn.execute(
        "SELECT count(*) n FROM episodes WHERE album_id=? AND is_published=1 "
        "AND owner_type='gcores'", (args.id,)).fetchone()["n"]
    per = args.per
    offset = (args.page - 1) * per
    rows = conn.execute(
        "SELECT e.*, c.name AS category_name, a.title AS album_title "
        "FROM episodes e "
        "LEFT JOIN categories c ON c.id=e.category_id "
        "LEFT JOIN albums a ON a.id=e.album_id "
        "WHERE e.album_id=? AND e.is_published=1 AND e.owner_type='gcores' "
        "ORDER BY e.published_date DESC, e.id DESC LIMIT ? OFFSET ?",
        (args.id, per, offset)).fetchall()
    print(f"===== 📻 {chan['title']}（共 {total} 期，第 {args.page} 页）=====")
    if chan["description"]:
        print(f"简介: {chan['description']}")
    print(f"原页: https://www.gcores.com/albums/{args.id}")
    for r in rows:
        e = calendar_view.cards_from_rows(conn, [r])[0]
        print()
        for ln in _card_lines(e):
            print(ln)


def cmd_export_h5(args):
    from export_h5 import export_h5
    export_h5(db_path=args.db, out_path=args.out)


def cmd_serve(args):
    from webui import run_server
    run_server(port=args.port, db=args.db, host=args.host)


def main(argv=None):
    # pythonw（无控制台）下 sys.stdout/stderr 为 None，替换为内存流防崩溃
    import io
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="gcal", description="机核播客日历索引工具")
    p.add_argument("--version", action="version",
                   version=f"{config.APP_NAME} v{config.VERSION}")
    p.add_argument("--db", default=str(config.DB_PATH), help="SQLite 数据库路径")
    p.add_argument("--all", action="store_true", help="包含非官方（机组用户）内容")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="初始化数据库")
    sp.set_defaults(fn=cmd_init)

    sp = sub.add_parser("backfill", help="全量回填")
    sp.add_argument("--skip-categories", action="store_true")
    sp.add_argument("--skip-sweep", action="store_true")
    sp.add_argument("--skip-membership", action="store_true")
    sp.set_defaults(fn=cmd_backfill)

    sp = sub.add_parser("categories", help="按分类补抓（付费期数完整数据源）")
    sp.set_defaults(fn=cmd_categories)

    sp = sub.add_parser("sweep", help="重跑期数深扫（刷新封面/播放数等）")
    sp.set_defaults(fn=cmd_sweep)

    sp = sub.add_parser("membership", help="补录节目归属（断点续抓）")
    sp.set_defaults(fn=cmd_membership)

    sp = sub.add_parser("comments", help="精华评论前三回填")
    sp.add_argument("--top-n", type=int, default=3)
    sp.set_defaults(fn=cmd_comments)

    sp = sub.add_parser("incremental", help="每日增量")
    sp.set_defaults(fn=cmd_incremental)

    sp = sub.add_parser("daily", help="每日一条龙：备份+增量+播放快照+完整性自检")
    sp.set_defaults(fn=cmd_daily)

    sp = sub.add_parser("backup", help="备份索引库（保留最近7份）")
    sp.set_defaults(fn=cmd_backup)

    sp = sub.add_parser("hot", help="近 N 天播放增长榜")
    sp.add_argument("--days", type=int, default=7)
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(fn=cmd_hot)

    sp = sub.add_parser("keywords", help="重建关键词提示表")
    sp.set_defaults(fn=cmd_keywords)

    sp = sub.add_parser("today", help="历史上的今天")
    sp.add_argument("--year", type=int, default=None)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--audiobooks", action="store_true", help="包含机核有声书")
    sp.set_defaults(fn=cmd_today)

    sp = sub.add_parser("day", help="某月-日的历史节目，如 04-23")
    sp.add_argument("date", help="MM-DD")
    sp.add_argument("--year", type=int, default=None)
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--audiobooks", action="store_true", help="包含机核有声书")
    sp.set_defaults(fn=cmd_day)

    sp = sub.add_parser("month", help="月历，如 2026-08")
    sp.add_argument("ym", help="YYYY-MM")
    sp.set_defaults(fn=cmd_month)

    sp = sub.add_parser("search", help="关键词检索")
    sp.add_argument("q")
    sp.add_argument("--limit", type=int, default=30)
    sp.add_argument("--category", default=None, help="按分类过滤（如 Gadio Pro）")
    sp.add_argument("--paid", type=int, choices=[0, 1], default=None, help="1=仅付费 0=仅免费")
    sp.add_argument("--album", default=None, help="按频道标题过滤")
    sp.add_argument("--from", dest="frm", default=None, help="起始日期 yyyy-mm-dd")
    sp.add_argument("--to", dest="to", default=None, help="结束日期 yyyy-mm-dd")
    sp.set_defaults(fn=cmd_search)

    sp = sub.add_parser("suggest", help="关键词提示")
    sp.add_argument("q")
    sp.add_argument("--limit", type=int, default=10)
    sp.set_defaults(fn=cmd_suggest)

    sp = sub.add_parser("stats", help="索引统计")
    sp.set_defaults(fn=cmd_stats)

    sp = sub.add_parser("export-h5", help="导出可双击打开的离线 H5 单文件")
    sp.add_argument("--out", default=None, help="输出文件路径")
    sp.set_defaults(fn=cmd_export_h5)

    sp = sub.add_parser("channel", help="查看频道期数")
    sp.add_argument("id", type=int, help="频道 id")
    sp.add_argument("--page", type=int, default=1)
    sp.add_argument("--per", type=int, default=10)
    sp.set_defaults(fn=cmd_channel)

    sp = sub.add_parser("serve", help="启动本地 Web 界面")
    sp.add_argument("--port", type=int, default=8333)
    sp.add_argument("--host", default="127.0.0.1")
    sp.set_defaults(fn=cmd_serve)

    args = p.parse_args(argv)
    setup_logging(args.verbose)
    args.fn(args)


if __name__ == "__main__":
    main()
