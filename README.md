# 机核播客日历（Gcores Podcast Calendar）

本地索引 www.gcores.com 全部官方播客节目（含付费节目元数据），生成按日期检索的日历，
支持"历史上的今天"、关键词检索与提示、参与者名单（个人页链接）、每期高权重精华评论前三。

- **范围**：机核官方节目（`owner-type=gcores`），付费期数以"付费"徽标标识
- **内容**：仅公开元数据与公开评论文本，**不下载、不存储任何音频**
- **合规**：遵循 robots.txt（不抓 /search 等）、低频限速（默认 1 请求/秒 + 抖动）、仅本地个人使用
- **依赖**：Python 3.11+ 标准库（urllib / sqlite3 / http.server），零第三方包

## 快速开始

```powershell
# 1. 初始化数据库
py gcal.py init

# 2. 全量回填（专辑 + 分类补抓[含完整付费期数] + 期数深扫 + 分类/参与者，约 30 分钟）
py gcal.py backfill

# 3. 节目归属补录（可断点续抓，约 10 分钟）
py gcal.py membership

# 4. 精华评论前三回填（约 1 小时，可断点续抓）
py gcal.py comments

# 5. 启动 Web 日历界面
py gcal.py serve
# 浏览器打开 http://127.0.0.1:8333（如需换端口：py gcal.py serve --port 9000）
```

## 命令行用法

```powershell
py gcal.py today                    # 历史上的今天
py gcal.py day 04-23                # 指定月-日（--year 2020 --page 2 分页）
py gcal.py month 2026-08            # 月历
py gcal.py search 宫崎骏            # 关键词检索（标题/副标题/简介/分类/正文）
py gcal.py suggest 宫               # 关键词提示
py gcal.py stats                    # 索引统计
py gcal.py incremental              # 每日增量（新期数 + 近30天评论刷新）
py gcal.py backfill --skip-sweep    # 跳过深扫（只按节目收录）
py gcal.py --all day 04-23          # 包含非官方（机组用户）内容
```

## 定时任务（Windows）

```powershell
powershell -ExecutionPolicy Bypass -File install_task.ps1
```
创建两个任务：每日 12:00（中午）增量校验 + 每 6 小时轻量增量；日志在 `logs/gcal.log`。

## 数据来源（已实测的公开 JSON:API）

| 接口 | 用途 |
|---|---|
| `GET /gapi/v1/albums?page[offset]=N` | 全部节目（252 个） |
| `GET /gapi/v1/categories/{id}/radios?page[offset]=N&include=category,djs` | 按分类全量期数（**付费/会员期数的完整来源**，公开 /radios 列表会漏早期付费期数） |
| `GET /gapi/v1/radios?page[offset]=N&include=category,djs` | 全量期数（实际可访问约 7914 行，含分类与参与者） |
| `GET /gapi/v1/albums/{id}/radios` | 节目→期数归属 |
| `GET /gapi/v1/radios/{id}/comments?page[offset]=0&include=user` | 按 score 权重降序的评论，取前三 |
| `GET /gapi/v1/latest-radios?include=radio` | 每日增量入口 |

> 注：付费/会员期数的播放数（plays）平台 API 不公开（返回 null），工具显示"播放 --（会员专享）"；免费期数播放数在每日增量中刷新。

## 目录结构

```
gcores_calendar/
├── gcal.py            # CLI 入口
├── gapi.py            # API 客户端（限速/重试）
├── crawler.py         # 回填 + 增量
├── store.py           # SQLite 存储
├── search.py          # FTS5 检索 + 提示
├── calendar_view.py   # 日历查询
├── webui.py           # Web 服务器
├── webui_index.html   # 日历页面
├── install_task.ps1   # 计划任务安装
├── config.py / config.toml(可选)   # 配置
├── data/gcores_calendar.db         # 索引库
└── logs/gcal.log                   # 日志
```
