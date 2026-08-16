# -*- coding: utf-8 -*-
"""导出可双击打开的 H5 单文件入口（自包含索引快照，无需启动 Web 服务）。

用法：py gcal.py export-h5 [--out 机核播客日历.html]
"""
import json
import re
import sys
from pathlib import Path

import config
import store

config.ensure_dirs()

BASE_DIR = Path(__file__).resolve().parent
OUT_DEFAULT = BASE_DIR / "机核播客日历.html"

DATA_LAYER_START = "// ===DATA-LAYER-START==="
DATA_LAYER_END = "// ===DATA-LAYER-END==="

AUDIOBOOK = "机核有声书"


# ---------------- 快照构建 ----------------

def build_snapshot(conn):
    """从索引库提取 UI 所需的全部数据。"""
    # 期数：仅官方已发布（含订阅可见与付费），供日历/搜索使用
    episodes = []
    for r in conn.execute(
        "SELECT e.id, e.title, e.subtitle, e.page_desc, e.published_at, e.published_date, "
        "e.duration, e.is_free, e.is_require_privilege, e.plays, e.comments_count, "
        "e.cover, e.url, c.name AS category_name, a.title AS album_title "
        "FROM episodes e "
        "LEFT JOIN categories c ON c.id=e.category_id "
        "LEFT JOIN albums a ON a.id=e.album_id "
        "WHERE e.is_published=1 AND e.owner_type='gcores' "
        "ORDER BY e.id"):
        episodes.append({
            "id": r["id"], "t": r["title"], "s": r["subtitle"], "pd": r["page_desc"] or "",
            "pa": r["published_at"], "p": r["published_date"],
            "du": r["duration"], "f": r["is_free"], "pr": r["is_require_privilege"],
            "pl": r["plays"], "cc": r["comments_count"], "cv": r["cover"], "u": r["url"],
            "cn": r["category_name"], "at": r["album_title"],
        })
    # 参与者（djs）
    djs = {}
    for r in conn.execute(
        "SELECT d.radio_id, d.position, u.id AS user_id, u.nickname, u.thumb, "
        "u.is_gcores_official FROM episode_djs d JOIN users u ON u.id=d.user_id "
        "ORDER BY d.radio_id, d.position"):
        djs.setdefault(r["radio_id"], []).append(
            {"uid": r["user_id"], "n": r["nickname"], "th": r["thumb"], "off": r["is_gcores_official"]})
    # 精华评论（前三，正文截断）
    comments = {}
    for r in conn.execute(
        "SELECT radio_id, body, likes_count, nickname, thumb FROM comments "
        "ORDER BY radio_id, rank"):
        body = (r["body"] or "")[:300]
        comments.setdefault(r["radio_id"], []).append(
            {"b": body, "l": r["likes_count"], "n": r["nickname"], "th": r["thumb"]})
    # 关键词提示表
    keywords = [{"k": r["keyword"], "c": r["count"]}
                for r in conn.execute(
                    "SELECT keyword, count FROM keywords ORDER BY count DESC")]
    # 统计
    def meta(k):
        row = conn.execute("SELECT value FROM crawl_meta WHERE key=?", (k,)).fetchone()
        return row["value"] if row else None

    base = "is_published=1 AND owner_type='gcores'"
    row = conn.execute(f"SELECT min(published_date) mn, max(published_date) mx FROM episodes WHERE {base}").fetchone()
    stats = {
        "episodes_total": conn.execute("SELECT count(*) n FROM episodes").fetchone()["n"],
        "episodes_published": conn.execute(f"SELECT count(*) n FROM episodes WHERE {base}").fetchone()["n"],
        "episodes_paid": conn.execute(
            f"SELECT count(*) n FROM episodes WHERE {base} AND is_require_privilege=1").fetchone()["n"],
        "albums": conn.execute("SELECT count(*) n FROM albums").fetchone()["n"],
        "albums_official": conn.execute(
            "SELECT count(*) n FROM albums WHERE owner_type='gcores'").fetchone()["n"],
        "categories": conn.execute("SELECT count(*) n FROM categories").fetchone()["n"],
        "comments": conn.execute("SELECT count(*) n FROM comments").fetchone()["n"],
        "users": conn.execute("SELECT count(*) n FROM users").fetchone()["n"],
        "date_range": [row["mn"], row["mx"]],
        "categories_top": [
            {"name": r["name"], "count": r["n"]}
            for r in conn.execute(
                "SELECT c.name AS name, count(*) AS n FROM episodes e "
                "LEFT JOIN categories c ON c.id=e.category_id "
                f"WHERE {base} AND c.name IS NOT NULL GROUP BY c.name ORDER BY n DESC LIMIT 12")
        ],
        "albums_done_at": meta("albums_done_at"),
        "sweep_done_at": meta("sweep_done_at"),
        "membership_done_at": meta("membership_done_at"),
        "comments_done_at": meta("comments_done_at"),
        "last_incremental_at": meta("last_incremental_at"),
    }
    return {
        "episodes": episodes,
        "djs": djs,
        "comments": comments,
        "keywords": keywords,
        "stats": stats,
        "generated_at": meta("last_incremental_at") or "",
    }


# ---------------- 内嵌数据层 JS ----------------

EMBEDDED_LAYER = r"""
// ===== 内嵌快照数据层（离线 H5，替代网络 API）=====
const __D = window.__GCAL_DATA__;
const __AB = "机核有声书";
const __IS_AB = e => e.cn === __AB;

function __sortDesc(es) {
  return es.slice().sort((a, b) =>
    (b.p || "").localeCompare(a.p || "") || (b.id - a.id));
}
function __card(e) {
  const dj = (__D.djs[e.id] || []).map(d => ({
    user_id: d.uid, nickname: d.n, thumb: d.th, is_gcores_official: d.off,
    url: "https://www.gcores.com/users/" + d.uid,
  }));
  const com = (__D.comments[e.id] || []).map(c => ({
    body: c.b, likes_count: c.l, nickname: c.n, thumb: c.th,
  }));
  return {
    id: e.id, title: e.t, subtitle: e.s, page_desc: e.pd,
    published_at: e.pa, published_date: e.p, duration: e.du,
    is_free: e.f, is_require_privilege: e.pr, plays: e.pl,
    comments_count: e.cc, cover: e.cv, url: e.u,
    category_name: e.cn, album_title: e.at, djs: dj, comments: com,
  };
}

async function api(path) {
  const u = new URL(path, location.href);
  const q = u.searchParams;
  // file:// 协议下 pathname 带盘符前缀（如 /C:/api/month），用后缀匹配
  const p = u.pathname;
  if (p.endsWith("/api/month")) {
    const y = +q.get("y"), m = +q.get("m");
    const ym = `${y}-${String(m).padStart(2, "0")}`;
    const days = {};
    for (const e of __D.episodes) {
      if (!e.p || !e.p.startsWith(ym)) continue;
      const d = +e.p.slice(8, 10);
      if (!days[d]) days[d] = {day: d, count: 0, previews: [], audiobooks: 0};
      const day = days[d];
      if (__IS_AB(e)) day.audiobooks++;
      else {
        day.count++;
        if (day.previews.length < 3)
          day.previews.push({id: e.id, title: e.t, url: e.u});
      }
    }
    const list = Object.values(days).sort((a, b) => a.day - b.day);
    for (const d of list) d.more = Math.max(0, d.count - d.previews.length);
    return {year: y, month: m, days: list};
  }
  if (p.endsWith("/api/day")) {
    const md = q.get("d");
    const all = __D.episodes.filter(e => e.p && e.p.slice(5, 10) === md);
    const main = __sortDesc(all.filter(e => !__IS_AB(e)));
    const ab = __sortDesc(all.filter(e => __IS_AB(e)));
    return {
      date: md,
      total_episodes: main.length,
      audiobooks_count: ab.length,
      audiobooks: ab.map(__card),
      episodes: main.map(__card),
    };
  }
  if (p.endsWith("/api/search")) {
    const qq = (q.get("q") || "").toLowerCase();
    const limit = +q.get("limit") || 50;
    if (!qq) return {query: qq, results: []};
    const hits = __D.episodes.filter(e =>
      (e.t || "").toLowerCase().includes(qq) ||
      (e.s || "").toLowerCase().includes(qq) ||
      (e.pd || "").toLowerCase().includes(qq) ||
      (e.cn || "").toLowerCase().includes(qq));
    return {query: qq, results: __sortDesc(hits).slice(0, limit).map(__card)};
  }
  if (p.endsWith("/api/suggest")) {
    const pre = (q.get("q") || "").toLowerCase();
    const out = [];
    if (pre) {
      for (const k of __D.keywords) {
        if (k.k.toLowerCase().startsWith(pre)) {
          out.push({keyword: k.k, count: k.c});
          if (out.length >= 10) break;
        }
      }
      if (out.length < 10) {
        for (const e of __sortDesc(__D.episodes)) {
          if ((e.t || "").toLowerCase().startsWith(pre)) {
            out.push({keyword: e.t, count: null, is_title: true});
            if (out.length >= 10) break;
          }
        }
      }
    }
    return {suggestions: out};
  }
  if (p.endsWith("/api/stats")) return __D.stats;
  return {};
}
"""


# ---------------- 导出 ----------------

def export_h5(db_path=None, out_path=None):
    conn = store.connect(db_path)
    snapshot = build_snapshot(conn)
    html = (BASE_DIR / "webui_index.html").read_text(encoding="utf-8")

    # 1) 替换数据层
    pattern = re.compile(
        re.escape(DATA_LAYER_START) + r".*?" + re.escape(DATA_LAYER_END),
        re.S)
    if not pattern.search(html):
        raise RuntimeError("webui_index.html 缺少数据层标记")
    html = pattern.sub(EMBEDDED_LAYER.strip(), html)

    # 2) 注入快照数据（插在主脚本之前）
    data_script = ("<script>window.__GCAL_DATA__ = " +
                   json.dumps(snapshot, ensure_ascii=False) + ";</script>")
    last_script = html.rfind("<script>")
    if last_script < 0:
        raise RuntimeError("未找到主脚本位置")
    html = html[:last_script] + data_script + html[last_script:]

    # 3) 标题注明离线快照
    html = html.replace(
        "<title>机核播客日历</title>",
        "<title>机核播客日历（离线 H5）</title>")

    out = Path(out_path) if out_path else OUT_DEFAULT
    out.write_text(html, encoding="utf-8")
    size_mb = out.stat().st_size / 1024 / 1024
    print(f"已导出: {out}")
    print(f"大小: {size_mb:.1f} MB | 期数: {len(snapshot['episodes'])} | "
          f"评论: {sum(len(v) for v in snapshot['comments'].values())} | "
          f"关键词: {len(snapshot['keywords'])}")
    print("双击该文件即可在浏览器中打开（无需启动服务）")
    return str(out)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    out = sys.argv[1] if len(sys.argv) > 1 else None
    export_h5(out_path=out)
