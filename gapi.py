# -*- coding: utf-8 -*-
"""机核 gapi 客户端：标准库 urllib，带限速、重试、退避。"""
import http.client
import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request

import config


class GapiError(Exception):
    pass


class GapiClient:
    def __init__(self, base=None, interval=None, max_retries=None, user_agent=None):
        config.apply_config()
        self.base = base or config.API_BASE
        self.interval = interval if interval is not None else config.REQUEST_INTERVAL
        self.max_retries = max_retries if max_retries is not None else config.MAX_RETRIES
        self.user_agent = user_agent or config.USER_AGENT
        self._last_ts = 0.0
        self.requests = 0

    def _throttle(self):
        now = time.monotonic()
        gap = now - self._last_ts
        need = self.interval + random.uniform(0, config.INTERVAL_JITTER)
        if gap < need:
            time.sleep(need - gap)
        self._last_ts = time.monotonic()

    def get(self, path, params=None, retries=None):
        """GET 一个 JSON:API 资源；失败重试，4xx 抛 GapiError。"""
        retries = self.max_retries if retries is None else retries
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode(params)
        last_err = None
        for attempt in range(retries + 1):
            self._throttle()
            req = urllib.request.Request(url, headers={
                "User-Agent": self.user_agent,
                "Accept": "application/vnd.api+json, application/json;q=0.9, */*;q=0.5",
                "Accept-Language": "zh-CN,zh;q=0.9",
            })
            try:
                with urllib.request.urlopen(req, timeout=config.TIMEOUT) as resp:
                    raw = resp.read()
                    self.requests += 1
                    return json.loads(raw.decode("utf-8"))
            except urllib.error.HTTPError as e:
                self.requests += 1
                if e.code in (429, 500, 502, 503, 504):
                    last_err = e
                    wait = config.RETRY_BASE * (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(min(wait, 30))
                    continue
                if e.code in (400, 404, 403, 401):
                    raise GapiError(f"{e.code} {url}: {e.reason}")
                last_err = e
                time.sleep(1.0)
            except (urllib.error.URLError, OSError, TimeoutError,
                    http.client.HTTPException) as e:
                last_err = e
                wait = config.RETRY_BASE * (2 ** attempt) + random.uniform(0, 1)
                time.sleep(min(wait, 30))
        raise GapiError(f"give up after {retries + 1} attempts: {url}: {last_err}")

    # ---------- 具体接口 ----------
    def list_albums(self, offset=0):
        """GET /albums?page[offset]=N → {data:[...], meta:{record-count}}"""
        return self.get("/albums", {"page[offset]": offset})

    def get_album(self, album_id):
        return self.get(f"/albums/{album_id}")

    def list_album_radios(self, album_id, offset=0):
        return self.get(f"/albums/{album_id}/radios", {"page[offset]": offset})

    def list_radios(self, offset=0, include="category,djs"):
        params = {"page[offset]": offset}
        if include:
            params["include"] = include
        return self.get("/radios", params)

    def get_radio(self, radio_id, include="category,djs,user"):
        params = {"include": include} if include else None
        return self.get(f"/radios/{radio_id}", params)

    def latest_radios(self):
        return self.get("/latest-radios")

    def list_comments(self, radio_id, offset=0, include="user"):
        params = {"page[offset]": offset}
        if include:
            params["include"] = include
        return self.get(f"/radios/{radio_id}/comments", params)
