# 机核播客日历（Gcores Podcast Calendar）

本地索引 www.gcores.com 全部官方播客（含付费/会员节目元数据），生成按日期检索的日历：
**"历史上的今天"、关键词检索与提示、参与者名单、每期高权重精华评论前三、封面头图、白天/夜间主题**。

- **范围**：机核官方节目（`owner-type=gcores`）+ 分类全量期数（付费期数完整收录），付费期数以"付费"徽标标识
- **内容**：仅公开元数据与公开评论文本，**不下载、不存储任何音频**
- **依赖**：Python 3.11+ 标准库（urllib / sqlite3 / http.server / FTS5），**零第三方包**
- **版本**：当前 **v1.3.0**（`py gcal.py --version`；Web 页脚与统计弹窗、离线 H5 页脚同步展示）。版本规则与历史见 [CHANGELOG.md](CHANGELOG.md)（语义化：MAJOR 重构 / MINOR 新功能 / PATCH 修复）

---

## ✨ 功能特性

### 1. 数据抓取（全量 + 增量）
| 能力 | 说明 |
|---|---|
| 全量回填 | 252 个播客频道（211 官方 + 41 用户入驻）、27 个分类、全量期数 |
| 付费期数完整性 | 通过**分类接口**补抓（公开 /radios 列表会漏早期会员期数），如"录音笔"系列 VOL.1~764 全部收录 |
| 期数元数据 | 标题、副标题、页面简介、分类、所属频道、时长、播放数、评论数、点赞数、**封面头图**、期号(vol) |
| 参与者 | 每期参与者名单 + **头像** + 个人主页链接（/users/{id}） |
| 精华评论 | 每期按平台 score 权重降序取**前三条**，含作者昵称与头像 |
| 断点续抓 | 深扫、节目归属、评论回填均有游标，中断后自动续跑 |
| 每日增量 | 新期数（含付费）+ 近 30 天评论/播放数刷新 |

### 2. Web 日历界面（http://127.0.0.1:8333）
- **月历置顶**：有节目的日期打点，格内显示标题预览（可点击直达机核原页）与期数计数，有声书单独计数提示
- **历史上的今天**：页面加载即展示当天跨年份的全部历史期数，**最新在前倒序展开**（无年份标签、无分页）
- **期数卡片**：右侧封面头图（点击直达原页）、分类/付费徽标、时长、评论数、播放数（付费期数显示"播放 --（会员专享）"，平台不公开）、所属频道、参与者头像列表、精华评论前三（含作者头像）
- **机核有声书隔离**：主列表默认排除有声书；当日有声书收进**默认隐藏的下拉框**（点击展开）
- **关键词搜索**：标题/副标题/简介/分类/正文全文检索（FTS5 trigram），**支持按参与者昵称搜索**（如搜"白广大"可找到其参与的所有期数），输入时**实时提示**候选词（含"（参与者）"标注）
- **一键立即抓取**：顶部"⚡ 立即抓取最新"按钮触发后台增量抓取（新期数 + 近 30 天评论/播放刷新），完成后自动提示"新增 N 期 · Xs"并刷新日历、当日视图与统计（离线 H5 版会提示重新导出快照）
- **快速跳转日历**：统计条右侧支持输入 `yyyy-mm-dd` 或使用**系统自带日历**选择日期，一键跳转到目标日期的历史节目
- **统计弹窗**：8 项核心指标 + 分类分布条形图（前 12）+ 各阶段抓取时间线
- **白天/夜间双主题**：一键切换，localStorage 记忆，首次访问跟随系统偏好；**配色与字体遵循机核官方设计规范**（品牌红 `#ff3d1d`、付费金 `#dbc1a1`、官方图标与字体栈）
- 所有外部图片（封面/头像）已处理防盗链（no-referrer），本地界面可正常加载

### 3. 命令行
```powershell
py gcal.py today                    # 历史上的今天（默认排除有声书）
py gcal.py day 04-23                # 指定月-日（--audiobooks 含有声书，--all 含非官方）
py gcal.py month 2026-08            # 月历
py gcal.py search 宫崎骏            # 关键词检索
py gcal.py suggest 宫               # 关键词提示
py gcal.py stats                    # 索引统计
py gcal.py serve                    # 启动 Web 界面（默认 127.0.0.1:8333）
```

### 4. 定时抓取（Windows 计划任务）
- 每日 **12:00** 增量校验 + 每 6 小时轻量增量（`install_task.ps1` 一键安装，无需管理员）
- 使用 pythonw 无窗口运行，日志写入 `logs/gcal.log`

### 5. 离线 H5 单文件入口（可双击打开）
- `py gcal.py export-h5` 生成**自包含的 `机核播客日历.html`**（内嵌全部索引快照：期数/评论/参与者/关键词）
- **双击文件**即可在浏览器打开完整日历界面，**无需启动服务、无需联网**（数据为导出时刻的快照）
- 与在线版同款界面：月历、历史上的今天、有声书下拉框、搜索与提示、统计弹窗、双主题
- 数据更新后重新执行 `py gcal.py export-h5` 即可刷新快照

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
py gcal.py today                    # 历史上的今天（有声书在下方另列）
py gcal.py day 04-23                # 指定月-日（--year 2020 --page 2）
py gcal.py month 2026-08            # 月历
py gcal.py search 宫崎骏            # 关键词检索（标题/副标题/简介/分类/正文/参与者昵称）
py gcal.py suggest 宫               # 关键词提示
py gcal.py stats                    # 索引统计
py gcal.py incremental              # 每日增量（新期数 + 近30天评论/播放刷新）
py gcal.py sweep                    # 重跑期数深扫（刷新封面/播放数等）
py gcal.py categories               # 按分类补抓（付费期数完整数据源）
py gcal.py comments                 # 精华评论前三（断点续抓）
py gcal.py membership               # 节目归属补录（断点续抓）
py gcal.py keywords                 # 重建关键词提示表
py gcal.py export-h5                # 导出可双击打开的离线 H5 单文件（机核播客日历.html）
py gcal.py --all day 04-23          # 包含非官方（机组用户）内容
py gcal.py day 04-23 --audiobooks   # 有声书以完整卡片另列（默认紧凑单行另列）
```

## 定时任务（Windows）

```powershell
powershell -ExecutionPolicy Bypass -File install_task.ps1
```
创建两个任务：**每日 12:00（中午）增量校验** + 每 6 小时轻量增量；日志在 `logs/gcal.log`。

## 数据规模（当前索引实例）

| 指标 | 数量 |
|---|---|
| 期数（全量） | 7914 |
| 官方已发布期数 | 6419（其中付费 1263） |
| 播客频道 | 252（官方 211 + 用户入驻 41） |
| 分类 | 27 |
| 精华评论 | 13931 |
| 参与者/用户 | 678 |
| 日期范围 | 2010-05-10 ~ 2026-08-15 |

> 术语：**期数** = 每一集播客（如"录音笔VOL.764"）；**播客频道** = 长期更新的系列（如"游戏茶话会"，含 90 期）；**分类** = 内容标签（如 Gadio Pro、会员专享、机核有声书）。

## 数据来源（已实测的公开 JSON:API）

| 接口 | 用途 |
|---|---|
| `GET /gapi/v1/albums?page[offset]=N` | 全部播客频道（252 个） |
| `GET /gapi/v1/categories/{id}/radios?page[offset]=N&include=category,djs` | 按分类全量期数（**付费/会员期数的完整来源**） |
| `GET /gapi/v1/radios?page[offset]=N&include=category,djs` | 全量期数深扫（约 7914 行，含分类与参与者） |
| `GET /gapi/v1/albums/{id}/radios` | 频道→期数归属 |
| `GET /gapi/v1/radios/{id}/comments?page[offset]=0&include=user` | 按 score 权重降序的评论，取前三 |
| `GET /gapi/v1/latest-radios?include=radio` | 每日增量入口 |
| `POST /api/refresh`（本地 Web） | 触发后台增量抓取；`GET /api/refresh-status` 轮询状态 |

> 注：付费/会员期数的播放数（plays）平台 API 不公开（返回 null），工具显示"播放 --（会员专享）"；免费期数播放数在每日增量中刷新。

## 合规与边界

- 只抓取**公开元数据与公开评论文本**，不存储、不下载任何音频（付费音频受平台保护，工具不做任何绕过）
- 遵循 robots.txt（不抓 /search、/account 等）、低频限速（默认 1 请求/秒 + 抖动）、指数退避重试
- 封面/头像通过 CDN 公开地址加载（no-referrer 处理防盗链），仅本地个人使用

## 目录结构

```
gcores_calendar/
├── gcal.py            # CLI 入口（init/backfill/comments/serve/today/day/...）
├── gapi.py            # API 客户端（限速/重试/退避）
├── crawler.py         # 回填（频道/分类/深扫/归属/评论）+ 每日增量
├── store.py           # SQLite 存储（表结构 + 迁移 + upsert）
├── search.py          # FTS5 trigram 检索 + 短词回退 + 关键词提示
├── calendar_view.py   # 日历/日/月查询 + 卡片装配 + 统计
├── webui.py           # Web 服务器（纯 http.server + JSON API）
├── webui_index.html   # 日历页面（月历/日详情/搜索/统计弹窗/双主题）
├── export_h5.py       # 离线 H5 单文件导出器（内嵌快照数据层）
├── 机核播客日历.html  # （生成物）可双击打开的离线入口
├── install_task.ps1   # Windows 计划任务安装（每日12:00 + 每6小时）
├── config.py / config.toml(可选)   # 配置（限速/范围/增量天数）
├── data/gcores_calendar.db         # 索引库（SQLite + FTS5）
└── logs/gcal.log                   # 抓取日志
```
