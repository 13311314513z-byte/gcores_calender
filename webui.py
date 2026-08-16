# -*- coding: utf-8 -*-
"""本地 Web 界面：月历、历史上的今天（多年份分页）、关键词检索与提示。
纯标准库 http.server，无第三方依赖。"""
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import calendar_view
import config
import store
from search import format_duration, search, suggest

INDEX_HTML = Path(__file__).resolve().parent / "webui_index.html"


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
            rows = search(conn, q, limit=limit)
            cards = calendar_view.cards_from_rows(conn, rows)
            self._send(200, {"query": q, "results": cards})
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

        self._send(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        import logging
        logging.getLogger("webui").debug(fmt % args)


def run_server(port=8333, host="127.0.0.1", db=None):
    srv = ThreadingHTTPServer((host, port), Handler)
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
