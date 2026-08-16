# -*- coding: utf-8 -*-
"""机核播客日历工具 - 配置（全部标准库，无第三方依赖）"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "gcores_calendar.db"
CONFIG_PATH = BASE_DIR / "config.toml"

# ---- 站点 ----
SITE = "https://www.gcores.com"
API_BASE = SITE + "/gapi/v1"
USER_AGENT = "gcores-calendar/1.0 (personal local indexer; metadata only; +local)"

# ---- 抓取参数 ----
PAGE_SIZE = 10            # 服务端每页固定 10 条
REQUEST_INTERVAL = 1.0    # 基础请求间隔（秒），礼貌限速
INTERVAL_JITTER = 0.4     # 抖动范围（秒）
MAX_RETRIES = 4           # 失败重试次数
RETRY_BASE = 2.0          # 指数退避基数（秒）
TIMEOUT = 30              # 单请求超时（秒）

# ---- 增量策略 ----
INCREMENTAL_COMMENT_DAYS = 30   # 每日增量只刷新近 N 天期数的评论
WEEKLY_REFRESH_DAYS = 7         # 每周刷新多少天内期数的点赞/评论数（暂未启用，预留）

# ---- 范围 ----
DEFAULT_OFFICIAL_ONLY = True    # 默认只看机核官方(owner-type=gcores)内容


def load_toml():
    """读取 config.toml（若存在）覆盖默认值。"""
    cfg = {}
    try:
        import tomllib
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "rb") as f:
                cfg = tomllib.load(f)
    except Exception:
        cfg = {}
    return cfg


def apply_config():
    global REQUEST_INTERVAL, MAX_RETRIES, DEFAULT_OFFICIAL_ONLY
    global USER_AGENT, INCREMENTAL_COMMENT_DAYS
    c = load_toml()
    crawl = c.get("crawl", {})
    if "request_interval" in crawl:
        REQUEST_INTERVAL = float(crawl["request_interval"])
    if "max_retries" in crawl:
        MAX_RETRIES = int(crawl["max_retries"])
    if "user_agent" in crawl and crawl["user_agent"]:
        USER_AGENT = str(crawl["user_agent"])
    scope = c.get("scope", {})
    if "official_only" in scope:
        DEFAULT_OFFICIAL_ONLY = bool(scope["official_only"])
    inc = c.get("incremental", {})
    if "comment_days" in inc:
        INCREMENTAL_COMMENT_DAYS = int(inc["comment_days"])


def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
