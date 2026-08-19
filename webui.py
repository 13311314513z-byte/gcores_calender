# -*- coding: utf-8 -*-
"""本地 Web 界面：月历、历史上的今天（多年份分页）、关键词检索与提示。
纯标准库 http.server，无第三方依赖。"""
import json
import logging
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import calendar_view
import config
import search as search_mod
import store
from search import format_duration, search, suggest

INDEX_HTML = Path(__file__).resolve().parent / "webui_index.html"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"

config.ensure_dirs()

_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
}


class CalendarServer(ThreadingHTTPServer):
    """带后台增量抓取能力的服务器。"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db_path = None
        self._refresh_lock = threading.Lock()
        self._refresh = {"running": False, "last": None}

    def start_refresh(self):
        """触发后台增量抓取（幂等：已运行则直接返回当前状态）。"""
        with self._refresh_lock:
            if self._refresh["running"]:
                return dict(self._refresh)
            self._refresh = {"running": True, "last": self._refresh.get("last")}
            threading.Thread(target=self._do_refresh, daemon=True).start()
        return dict(self._refresh)

    def refresh_state(self):
        return dict(self._refresh)

    def _do_refresh(self):
        st = self._refresh
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            handlers=[logging.FileHandler(config.LOG_DIR / "gcal.log", encoding="utf-8")],
        )
        log = logging.getLogger("webui.refresh")
        try:
            import crawler
            from gapi import GapiClient
            client = GapiClient()
            conn = store.connect(self.db_path or config.DB_PATH)
            store.init_schema(conn)
            t0 = time.time()
            new_episodes = crawler.incremental(client, conn)
            st["last"] = {
                "ok": True,
                "new_episodes": int(new_episodes or 0),
                "seconds": round(time.time() - t0, 1),
                "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            log.info("web refresh done: %s", st["last"])
        except Exception as e:
            log.exception("web refresh failed")
            st["last"] = {
                "ok": False,
                "error": str(e),
                "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        finally:
            st["running"] = False


class Handler(BaseHTTPRequestHandler):
    server_version = "gcores-calendar/1.0"

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _db(self):
        return store.connect(getattr(self.server, "db_path", config.DB_PATH))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            html = INDEX_HTML.read_text(encoding="utf-8") if INDEX_HTML.exists() else "<h1>index missing</h1>"
            self._send(200, html, "text/html; charset=utf-8")
            return

        if path.startswith("/assets/"):
            name = path[len("/assets/"):]
            if "/" in name or ".." in name:
                self._send(404, {"error": "bad path"})
                return
            f = ASSETS_DIR / name
            if not f.is_file():
                self._send(404, {"error": "not found"})
                return
            data = f.read_bytes()
            ctype = _CONTENT_TYPES.get(f.suffix.lower(), "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            self.wfile.write(data)
            return

        if path == "/api/month":
            conn = self._db()
            try:
                y = int(qs.get("y", [calendar_view.now_cn().year])[0])
                m = int(qs.get("m", [calendar_view.now_cn().month])[0])
            except ValueError:
                self._send(400, {"error": "bad y/m"})
                return
            data = calendar_view.month_data(conn, y, m)
            self._send(200, data)
            return

        if path == "/api/day":
            conn = self._db()
            md = qs.get("d", [""])[0]
            year = int(qs["year"][0]) if qs.get("year") and qs["year"][0] else None
            page = int(qs.get("page", ["1"])[0])
            # Web 端始终带上有声书数据（界面用默认隐藏的下拉框呈现）
            data = calendar_view.day_data(conn, md, year=year, page=page,
                                          include_audiobooks=True)
            self._send(200, data)
            return

        if path == "/api/search":
            conn = self._db()
            q = qs.get("q", [""])[0]
            limit = int(qs.get("limit", ["30"])[0])

            def _opt(k):
                v = qs.get(k, [""])[0]
                return v if v else None

            paid = qs.get("paid", [""])[0]
            rows = search(
                conn, q, limit=limit,
                category=_opt("category"), album=_opt("album"),
                date_from=_opt("from"), date_to=_opt("to"),
                paid=(paid == "1") if paid in ("0", "1") else None,
            )
            cards = calendar_view.cards_from_rows(conn, rows)
            snips = {r["id"]: search_mod.snippet(q, r) for r in rows}
            for c in cards:
                c["snippet"] = snips.get(c["id"], "")
            self._send(200, {"query": q, "results": cards})
            return

        if path == "/api/categories":
            conn = self._db()
            cats = [
                {"name": r["name"], "count": r["n"]}
                for r in conn.execute(
                    "SELECT c.name AS name, count(*) AS n FROM episodes e "
                    "LEFT JOIN categories c ON c.id=e.category_id "
                    "WHERE e.is_published=1 AND e.owner_type='gcores' AND c.name IS NOT NULL "
                    "GROUP BY c.name ORDER BY n DESC")
            ]
            self._send(200, {"categories": cats})
            return

        if path == "/api/channels":
            conn = self._db()
            chans = [
                {"id": r["id"], "title": r["title"], "description": r["description"],
                 "cover": r["cover"], "radios_count": r["radios_count"],
                 "is_require_privilege": r["is_require_privilege"],
                 "owner_type": r["owner_type"],
                 "url": config.SITE + f"/albums/{r['id']}"}
                for r in conn.execute(
                    "SELECT id, title, description, cover, radios_count, "
                    "is_require_privilege, owner_type FROM albums "
                    "WHERE is_published=1 ORDER BY "
                    "(owner_type='gcores') DESC, radios_count DESC")
            ]
            self._send(200, {"channels": chans})
            return

        if path == "/api/channel":
            conn = self._db()
            cid = int(qs.get("id", ["0"])[0])
            page = max(1, int(qs.get("page", ["1"])[0]))
            per = 10
            chan = conn.execute("SELECT * FROM albums WHERE id=?", (cid,)).fetchone()
            if not chan:
                self._send(404, {"error": "channel not found"})
                return
            total = conn.execute(
                "SELECT count(*) n FROM episodes WHERE album_id=? AND is_published=1 "
                "AND owner_type='gcores'", (cid,)).fetchone()["n"]
            offset = (page - 1) * per
            rows = conn.execute(
                "SELECT e.*, c.name AS category_name, a.title AS album_title "
                "FROM episodes e "
                "LEFT JOIN categories c ON c.id=e.category_id "
                "LEFT JOIN albums a ON a.id=e.album_id "
                "WHERE e.album_id=? AND e.is_published=1 AND e.owner_type='gcores' "
                "ORDER BY e.published_date DESC, e.id DESC LIMIT ? OFFSET ?",
                (cid, per, offset)).fetchall()
            self._send(200, {
                "channel": {
                    "id": chan["id"], "title": chan["title"],
                    "description": chan["description"], "cover": chan["cover"],
                    "radios_count": chan["radios_count"],
                    "is_require_privilege": chan["is_require_privilege"],
                    "url": config.SITE + f"/albums/{chan['id']}",
                },
                "total": total, "page": page,
                "total_pages": max(1, (total + per - 1) // per),
                "episodes": calendar_view.cards_from_rows(conn, rows),
            })
            return

        if path == "/api/hot":
            conn = self._db()
            days = int(qs.get("days", ["7"])[0])
            self._send(200, {"days": days, "hot": store.hot_episodes(conn, days=days)})
            return

        if path == "/api/suggest":
            conn = self._db()
            q = qs.get("q", [""])[0]
            self._send(200, {"suggestions": suggest(conn, q)})
            return

        if path == "/api/stats":
            conn = self._db()
            self._send(200, calendar_view.stats(conn))
            return

        if path == "/api/refresh":
            self._send(200, self.server.start_refresh())
            return

        if path == "/api/refresh-status":
            self._send(200, self.server.refresh_state())
            return

        self._send(404, {"error": "not found"})

    def do_POST(self):
        """刷新抓取用 POST 触发（GET 亦可用）。"""
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/refresh":
            self._send(200, self.server.start_refresh())
            return
        self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        import logging
        logging.getLogger("webui").debug(fmt % args)


def run_server(port=8333, host="127.0.0.1", db=None):
    # pythonw（无控制台）下 sys.stdout 为 None，替换为内存流防崩溃
    if sys.stdout is None:
        sys.stdout = __import__("io").StringIO()
    srv = CalendarServer((host, port), Handler)
    srv.db_path = db or config.DB_PATH
    print(f"机核播客日历 Web 界面: http://{host}:{port}  (Ctrl+C 退出)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8333)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--db", default=None)
    a = ap.parse_args()
    run_server(a.port, a.host, a.db)
