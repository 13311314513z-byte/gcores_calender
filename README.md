# 机核播客日历（Gcores Podcast Calendar）

> **当前版本：v1.4.2** ｜ 版本历史见 [CHANGELOG.md](CHANGELOG.md) ｜ 语义化版本规则：MAJOR 不兼容重构 / MINOR 新增功能 / PATCH 缺陷修复

本地索引 www.gcores.com 全部官方播客（含付费/会员节目元数据），生成按日期检索的日历：
**"历史上的今天"、关键词检索与提示、参与者名单、每期高权重精华评论前三、封面头图、白天/夜间主题、离线 H5 单文件**。

- **范围**：机核官方节目（`owner-type=gcores`）+ 分类全量期数（付费期数完整收录），付费期数以"付费"徽标标识
- **内容**：仅公开元数据与公开评论文本，**不下载、不存储任何音频**
- **依赖**：Python 3.11+ 标准库（urllib / sqlite3 / http.server / FTS5），**零第三方包**
- **版本**：当前 **v1.4.1**（`py gcal.py --version`；Web 页脚与统计弹窗、离线 H5 页脚同步展示）

---

## ✨ 功能特性

### 1. 数据抓取（全量 + 增量）
| 能力 | 说明 |
|---|---|
| 全量回填 | 252 个播客频道（211 官方 + 41 用户入驻）、27 个分类、全量期数（深扫 7914 行） |
| 付费期数完整性 | 通过**分类接口**补抓（公开 /radios 列表会漏早期会员期数），如"录音笔"系列 VOL.1~764 全部收录 |
| 期数元数据 | 标题、副标题、页面简介、分类、所属频道、时长、播放数、评论数、点赞数、**封面头图**、期号(vol) |
| 参与者 | 每期参与者名单 + **头像** + 个人主页链接（/users/{id}） |
| 精华评论 | 每期按平台 score 权重降序取**前三条**，含作者昵称与头像 |
| 断点续抓 | 深扫（sweep_offset）/ 分类（categories_cursor）/ 归属（membership_cursor）/ 评论（comments_cursor）均有游标，中断后自动续跑 |
| 每日增量 | 新期数（含付费）+ 近 30 天评论/播放数刷新 |

### 2. Web 日历界面（http://127.0.0.1:8333）
- **月历置顶**：有节目的日期打点，格内显示标题预览（可点击直达机核原页）与期数计数，有声书单独计数提示
- **历史上的今天**：页面加载即展示当天跨年份的全部历史期数，**最新在前倒序展开**（无年份标签、无分页）
- **期数卡片**：右侧封面头图（点击直达原页）、分类/付费徽标、时长、评论数、播放数（付费期数显示"播放 --（会员专享）"，平台不公开）、所属频道、参与者头像列表、精华评论前三（含作者头像）
- **机核有声书隔离**：主列表默认排除有声书；当日有声书收进**默认隐藏的下拉框**（点击展开）
- **关键词搜索**：标题/副标题/简介/分类/正文全文检索（FTS5 trigram），**支持按参与者昵称搜索**，输入时**实时提示**候选词（词表/标题/参与者/拼音，含类型标注）
- **拼音 / 同音容错检索**：输入 `ximeng` 命中"西蒙"；错别字"宫崎竣"也能找到"宫崎骏"（assets/pinyin.txt 官方拼音表，零第三方依赖）
- **命中高亮 + 片段预览**：搜索结果标题/简介高亮关键词，正文显示命中上下文片段
- **组合过滤**：搜索可按 分类 / 频道 / 仅付费 / 日期范围 二次筛选（CLI 同支持）
- **频道浏览**："📻 频道"页浏览全部 252 个频道（封面/期数/付费/官方标记），点入查看频道全部期数（分页）
- **🔥 热榜**：近 7 天播放增长榜（点击按钮弹出浮窗，默认隐藏）；**播放量快照仅在每日定时任务（daily）时更新**，Web 刷新/小时级增量不触发
- **一键立即抓取**："⚡ 立即抓取最新"按钮触发后台增量抓取（新期数 + 近 30 天评论/播放刷新），轮询反馈"新增 N 期 · Xs"并自动刷新日历/当日视图/统计（离线 H5 提示重新导出）
- **快速跳转日历**：统计条右侧输入 `yyyy-mm-dd` 或使用**系统自带日历**选择日期，一键跳转目标日期的历史节目
- **统计弹窗**：8 项核心指标 + 分类分布条形图（前 12）+ 抓取时间线 + 版本
- **白天/夜间双主题**：一键切换，localStorage 记忆，首次访问跟随系统偏好；**配色/字体/图标遵循机核官方设计规范**（品牌红 `#ff3d1d`、付费金 `#dbc1a1`、官方 favicon 与字体栈）
- 外部图片（封面/头像）已处理防盗链（`referrerpolicy="no-referrer"`）

### 3. 离线 H5 单文件入口（可双击打开）
- `py gcal.py export-h5` 生成**自包含的 `机核播客日历.html`**（内嵌全部索引快照：期数/评论/参与者/关键词/**拼音索引/频道列表/热榜**，favicon 内联 base64）
- **双击文件**即可在浏览器打开完整日历界面，**无需启动服务、无需联网**（数据为导出时刻的快照）
- 与在线版同款界面与逻辑：月历、历史上的今天、有声书下拉框、搜索（含拼音/过滤/高亮）、频道浏览、统计弹窗、双主题
- 数据更新后重新执行 `py gcal.py export-h5` 刷新快照

### 4. 命令行
```powershell
py gcal.py today / day 04-23        # 历史上的今天 / 指定日期（有声书默认紧凑另列）
py gcal.py month 2026-08            # 月历
py gcal.py search 宫崎骏            # 检索（含参与者昵称/拼音/同音）
py gcal.py suggest 宫               # 关键词提示
py gcal.py stats / hot / channel 51 # 统计 / 热榜 / 频道期数
py gcal.py serve                    # 启动 Web 界面（默认 127.0.0.1:8333）
```

### 5. 定时抓取与数据守护（Windows 计划任务）
- 每日 **12:00** 执行**"一条龙"**（`py gcal.py daily`）：① 数据库备份（保留 7 份，`data/backups/`）→ ② 增量抓取 → ③ 播放量快照（热榜数据源）→ ④ 数据完整性自检（逐分类比对 API 计数，不一致告警）
- 每 6 小时轻量增量（`install_task.ps1` 一键安装，无需管理员；pythonw 无窗口运行）
- **Web 服务保活**：`py gcal.py ensure-web` 看门狗（检测 8333 未监听则以独立进程拉起）；计划任务 `GcoresCalendarWatchdog` 每小时自动检测重启；`GcoresCalendarWeb` 登录自启（需管理员创建）
- 日志自动轮转（5MB × 5 份）；SQLite 连接统一 `busy_timeout=10s`，多任务并发安全

---

## 🔧 执行逻辑

### 抓取链路（数据流）
```
机核 gapi（JSON:API）
  ├─ /albums            → albums 表（252 频道）
  ├─ /categories/{id}/radios → episodes 表（27 分类全量，付费完整性关键）
  ├─ /radios 深扫        → episodes 表（7914 行，含分类/参与者/封面）
  ├─ /albums/{id}/radios → 补录 album_id 归属
  ├─ /radios/{id}/comments → comments 表（score 权重前三 + 用户）
  └─ /latest-radios      → 每日增量新期数入口
        ↓
SQLite（WAL）→ Web API / 离线 H5 快照 / CLI
```

### 断点续抓机制
| 游标 | 位置 | 说明 |
|---|---|---|
| `sweep_offset` | crawl_meta | 深扫按页记录，中断后从该偏移续扫 |
| `categories_cursor` | crawl_meta | 按分类 id 记录，跳过已完成分类 |
| `membership_cursor` | crawl_meta | 按频道 id 记录，跳过已完成频道 |
| `comments_cursor` | crawl_meta | 按期数 id 记录；只处理"尚无评论"的期数 |

### 每日流程（daily）
```
backup_db（WAL checkpoint → 复制 → 清理旧备份）
  → incremental（latest-radios 新期数详情+评论 → 近30天评论/播放刷新）
  → sample_plays（全量官方期数 plays/likes/comments 快照，每日一次幂等）
  → integrity_check（27 分类 库内数 vs API record-count，告警日志）
```

### Web 架构
- 纯标准库 `http.server`（ThreadingHTTPServer），每请求独立 SQLite 连接（WAL 并发读）
- 增量抓取在**后台线程**执行（`POST /api/refresh` 触发 + `/api/refresh-status` 轮询），不阻塞页面
- 页面 HTML 每次请求实时读取（改 `webui_index.html` 刷新即生效，无需重启）
- 主题在 `<head>` 内联脚本于 CSS 生效前应用（无闪烁）；离线 H5 由导出器替换数据层（`// ===DATA-LAYER-START===` 标记），UI 逻辑 100% 复用

### 限速与合规
- 默认 1 请求/秒 + 0.4s 抖动，429/5xx 指数退避（2s×2^n）重试 4 次；网络异常（含 IncompleteRead）一并重试
- 仅抓公开元数据与公开评论；不触碰音频；遵循 robots.txt

---

## 快速开始

```powershell
# 1. 初始化数据库
py gcal.py init

# 2. 全量回填（频道 + 分类补抓[含完整付费期数] + 期数深扫，约 30 分钟）
py gcal.py backfill

# 3. 节目归属补录（可断点续抓，约 10 分钟）
py gcal.py membership

# 4. 精华评论前三回填（约 1 小时，可断点续抓，只补缺失）
py gcal.py comments

# 5. 启动 Web 日历界面
py gcal.py serve
# 浏览器打开 http://127.0.0.1:8333（如需换端口：py gcal.py serve --port 9000）
```

## 命令行用法（完整）

```powershell
# —— 数据抓取 ——
py gcal.py init                    # 初始化数据库
py gcal.py backfill                # 全量回填（--skip-categories/--skip-sweep/--skip-membership）
py gcal.py categories              # 按分类补抓（付费期数完整数据源）
py gcal.py sweep                   # 重跑期数深扫（刷新封面/播放数等）
py gcal.py membership              # 节目归属补录（断点续抓）
py gcal.py comments                # 精华评论前三（断点续抓，只补缺失）
py gcal.py incremental             # 每日增量（新期数 + 近30天评论/播放刷新；不含播放快照）
py gcal.py daily                   # 一条龙：备份 + 增量 + 播放快照 + 完整性自检
py gcal.py backup                  # 备份索引库（保留最近7份）
py gcal.py keywords                # 重建关键词提示表

# —— 查询展示 ——
py gcal.py today                   # 历史上的今天（有声书在下方另列）
py gcal.py day 04-23               # 指定月-日（--year 2020 --page 2 --audiobooks --all）
py gcal.py month 2026-08           # 月历
py gcal.py search 宫崎骏           # 关键词检索（标题/副标题/简介/分类/正文/参与者昵称/拼音）
py gcal.py search 录音笔 --paid 1 --category 会员专享 --from 2024-01-01 --to 2026-12-31
py gcal.py suggest 宫              # 关键词提示
py gcal.py channel 51              # 查看频道期数（--page --per）
py gcal.py hot                     # 近 7 天播放增长榜（--days --limit）
py gcal.py stats                   # 索引统计（含版本）

# —— 服务与导出 ——
py gcal.py serve                   # 启动 Web 界面（--port --host --db）
py gcal.py ensure-web              # 看门狗：Web 未监听则以独立进程启动（供计划任务调用）
py gcal.py export-h5               # 导出离线 H5 单文件（机核播客日历.html）
py gcal.py --version               # 版本号
py gcal.py --all day 04-23         # 全局选项：包含非官方（机组用户）内容
```

## 本地 Web API 一览

| 接口 | 说明 |
|---|---|
| `GET /` | 日历页面（HTML） |
| `GET /api/month?y=&m=` | 月视图（期数/预览/有声书计数） |
| `GET /api/day?d=MM-DD` | 历史上的今天（主列表 + 有声书另列，倒序展开） |
| `GET /api/search?q=&category=&album=&paid=&from=&to=` | 检索（FTS/昵称/拼音 + 过滤 + 片段） |
| `GET /api/suggest?q=` | 关键词提示 |
| `GET /api/categories` / `GET /api/channels` | 分类 / 频道列表 |
| `GET /api/channel?id=&page=` | 频道期数（分页） |
| `GET /api/hot?days=` | 近 N 天播放增长榜 |
| `GET /api/stats` | 统计（含版本、分类分布、抓取时间线） |
| `POST /api/refresh` / `GET /api/refresh-status` | 触发后台增量抓取 / 轮询状态 |
| `GET /assets/*` | 静态资源（官方图标等） |

## 定时任务（Windows）

```powershell
powershell -ExecutionPolicy Bypass -File install_task.ps1
```
创建两个任务：**每日 12:00 一条龙（backup+增量+快照+自检）** + 每 6 小时轻量增量；日志在 `logs/gcal.log`。

## 数据规模（当前索引实例）

| 指标 | 数量 |
|---|---|
| 期数（全量） | 7914 |
| 官方已发布期数 | 6419（其中付费 1263） |
| 播客频道 | 252（官方 211 + 用户入驻 41） |
| 分类 | 27 |
| 精华评论 | 16827（覆盖 5700 期，持续补全中） |
| 参与者/用户 | 678 |
| 播放量快照 | 6419 期（每日 daily 更新） |
| 关键词表 | 78486 |
| 日期范围 | 2010-05-10 ~ 2026-08-15 |

> 术语：**期数** = 每一集播客（如"录音笔VOL.764"）；**播客频道** = 长期更新的系列（如"游戏茶话会"，含 90 期）；**分类** = 内容标签（如 Gadio Pro、会员专享、机核有声书）。

## 数据模型（SQLite）

```
albums(频道) ──< episodes(期数) >── categories(分类)
users(用户) <── episode_djs(参与者) ── episodes
users <── comments(精华评论前三, rank 1..3) ── episodes
episodes <── plays_history(播放量快照, 每日一采样)
keywords(提示词表) + episodes_fts(FTS5 trigram 全文索引)
crawl_meta(断点游标/时间戳)
```

## 数据来源（已实测的公开 JSON:API）

| 接口 | 用途 |
|---|---|
| `GET /gapi/v1/albums?page[offset]=N` | 全部播客频道（252 个） |
| `GET /gapi/v1/categories/{id}/radios?page[offset]=N&include=category,djs` | 按分类全量期数（**付费/会员期数的完整来源**） |
| `GET /gapi/v1/radios?page[offset]=N&include=category,djs` | 全量期数深扫（约 7914 行，含分类与参与者） |
| `GET /gapi/v1/albums/{id}/radios` | 频道→期数归属 |
| `GET /gapi/v1/radios/{id}/comments?page[offset]=0&include=user` | 按 score 权重降序的评论，取前三 |
| `GET /gapi/v1/latest-radios?include=radio` | 每日增量入口 |

> 注：付费/会员期数的播放数（plays）平台 API 不公开（返回 null），工具显示"播放 --（会员专享）"；免费期数播放数在每日增量中刷新。

## 合规与边界

- 只抓取**公开元数据与公开评论文本**，不存储、不下载任何音频（付费音频受平台保护，工具不做任何绕过）
- 遵循 robots.txt（不抓 /search、/account 等）、低频限速（默认 1 请求/秒 + 抖动）、指数退避重试
- 封面/头像通过 CDN 公开地址加载（no-referrer 处理防盗链），仅本地个人使用

## 目录结构

```
gcores_calendar/
├── gcal.py            # CLI 入口（全部命令 + --version）
├── gapi.py            # API 客户端（限速/重试/退避）
├── crawler.py         # 回填（频道/分类/深扫/归属/评论）+ 增量 + 完整性自检
├── store.py           # SQLite 存储（表结构/迁移/upsert/备份/播放快照/热榜）
├── search.py          # FTS5 检索 + 昵称 + 拼音/同音 + 过滤 + 片段
├── pinyin.py          # 拼音转换（assets/pinyin.txt 官方拼音表，零依赖）
├── calendar_view.py   # 日历/日/月查询 + 卡片装配 + 统计
├── webui.py           # Web 服务器（纯 http.server + JSON API + 静态资源）
├── webui_index.html   # 日历页面（全部界面逻辑 + 数据层标记）
├── export_h5.py       # 离线 H5 导出器（内嵌快照/拼音索引/频道/热榜）
├── 机核播客日历.html  # （生成物）可双击打开的离线入口
├── install_task.ps1   # Windows 计划任务安装（每日12:00 一条龙 + 每6小时）
├── assets/            # 官方图标（favicon/logo）+ pinyin.txt 拼音表
├── config.py / config.toml(可选)   # 配置（限速/范围/增量天数）
├── data/gcores_calendar.db         # 索引库（SQLite + FTS5 + plays_history）
├── data/backups/                   # 数据库备份（保留 7 份）
└── logs/gcal.log                   # 抓取日志（轮转 5MB×5）
```
