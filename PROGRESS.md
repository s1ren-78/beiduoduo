# PROGRESS — 贝多多项目进度

## 2026-02-17 全面优化 — 可靠性 + 性能 + Bot 体验 + 数据库

### 完成了什么
- **Phase 1 可靠性**：消灭所有 `except: pass`，全部改为 `_log.warning`；feishu_api token buffer 120s→300s、JSON decode guard、pagination 日志；kol_briefing Claude 重试+[摘要]前缀区分 fallback
- **Phase 2 性能**：FRED 缓存（macro_indicator 1h TTL、macro_overview 6h TTL）；yf.Ticker LRU 缓存（maxsize=64）避免重复 HTTP session
- **Phase 3 Bot 体验**：4 个搜索 tool 加 USE WHEN / NOT FOR 指引，减少 bot 选错工具
- **Phase 4 数据库**：新增 3 个索引（report_type、direction+time、extracted_at）；FTS rank 取反变正数（越大越好）
- **Phase 5 输入校验**：chart_render 日期解析失败显式 raise ValueError；/v1/search from >= to 返回 400
- **Phase 6 测试**：新增 3 个冒烟测试（invalid date range、positive score、macro cache）
- 冒烟测试全绿：55 pass / 0 fail / 4 skip
- Plugin 同步到 installPath + gateway 重启 + session 重置

### 踩坑记录
- ❌ test_macro_cached 第一次失败：因为 test_macro_overview 已经暖了缓存，两次调用都是 0s
  ✅ 测试改为：如果首次 < 1s（已缓存），只检查第二次也 < 1s

### 改动文件
- `feishu_mirror/query_api.py` — cache_write 日志、from/to 校验
- `feishu_mirror/lib/feishu_api.py` — token buffer、JSON guard、pagination 日志
- `feishu_mirror/lib/openbb_api.py` — TTL 缓存、LRU Ticker、insider 日志
- `feishu_mirror/lib/chart_render.py` — cleanup 日志、日期解析校验
- `feishu_mirror/lib/kol_briefing.py` — 搜索降级日志、Claude 重试
- `feishu_mirror/lib/db.py` — FTS rank 取反
- `feishu_mirror/schema.sql` — 3 个新索引
- `report-db-plugin/index.js` — tool 描述优化
- `feishu_mirror/tests/smoke_test.py` — 3 个新测试

## 2026-02-17 OpenBB 数据平台集成 — 宏观/基本面/外汇/期权

### 完成了什么
- 新增 `lib/openbb_api.py` — 统一封装 FRED（宏观）、yfinance（股票基本面/外汇/期权）、FMP（内部人交易）
- 新增 10 个 API 端点：/v1/macro/*, /v1/equity/*, /v1/forex/*, /v1/options/*
- 新增 10 个 Bot Tool：macro_indicator, macro_overview, equity_profile, equity_ratios, equity_analysts, equity_insiders, equity_institutions, forex_quote, forex_history, options_chain
- 新增 4 个冒烟测试：test_equity_profile, test_forex_quote, test_options_chain, test_macro_overview
- 冒烟测试全绿（47 pass / 0 fail / 5 skip），Gateway 已重启
- 新增 `fred_api_key` 和 `fmp_api_key` 到 Settings + .env

### 踩坑记录

#### 坑 1: pip install 破坏已有依赖版本
- ❌ `pip3 install openbb[yfinance]` 把 yfinance 从 1.1.0 降到 0.2.66，破坏了已有的 `market_api.py`
- ✅ **铁律：安装新包前，先记录关键依赖版本（`pip3 freeze | grep yfinance`），装完立刻验证版本没变，变了就手动恢复**
- ✅ 以后涉及 pip install 大包，先跑 `pip3 install --dry-run` 看它要改什么

#### 坑 2: 只改了源码没同步到 plugin 安装目录
- ❌ 改了 `/Users/beiduoudo/beiduoduo/report-db-plugin/index.js`，但 gateway 读的是 `~/.openclaw/extensions/openclaw-report-db/index.js`（安装路径），两份文件不同步
- ❌ 以为 `openclaw gateway restart` 就够了，实际上 gateway 不会从 sourcePath 重新拷贝
- ✅ **铁律：改完 plugin 后，必须手动 `cp` 到 installPath，或者用 `openclaw plugin install --force` 重装**
- ✅ 验证方法：`diff sourcePath/index.js installPath/index.js` 确认一致

#### 坑 3: openclaw.json 的 tools.allow 白名单要完整
- ❌ 新注册了 10 个 tool，但没加到 `agents.list[0].tools.allow`，导致 bot 看不到这些 tool
- ❌ gateway 报 `allowlist contains unknown entries ... Ignoring allowlist`，整个白名单被丢弃
- ❌ 尝试用 `alsoAllow` 修复，但 openclaw 不允许 `allow` 和 `alsoAllow` 同时存在
- ✅ **铁律：新增 bot tool = 改 index.js + cp 到 installPath + 改 openclaw.json allow 列表，三步缺一不可**

#### 坑 4: bot session 缓存了旧的 tool 列表
- ❌ gateway 重启后 bot 仍然不用新 tool，因为旧 session（79% context）里的 system prompt 没有新 tool
- ✅ 重置 session：`echo '{}' > ~/.openclaw/agents/main/sessions/sessions.json` + 重启 gateway
- ✅ **铁律：新增 tool 后必须重置 session，否则 bot 不知道有新工具可用**

#### 坑 5: .env 改了但没重启 API
- ❌ 加了 FRED_API_KEY 到 .env，但 API 进程还是旧的环境变量，/v1/macro/overview 报 "key not set"
- ✅ **铁律：改了 .env 就要重启 API 进程（`lsof -ti:8788 | xargs kill -9` + 重启）**

### 下次注意事项（新增 tool 完整 checklist）
1. `pip3 freeze | grep 关键包` — 记录版本
2. `pip3 install xxx` — 装完检查版本没变
3. 改 `report-db-plugin/index.js` — 新增 Schema + tool 注册
4. `cp index.js ~/.openclaw/extensions/openclaw-report-db/index.js` — 同步到安装路径
5. `diff` 确认两份文件一致
6. 改 `~/.openclaw/openclaw.json` — `agents.list[0].tools.allow` 加入新 tool 名
7. 改 `.env` — 新增 API key
8. 重启 API（`lsof -ti:8788 | xargs kill -9` + 启动）
9. 跑冒烟测试确认 API 端点正常
10. `openclaw gateway restart` — 重启 gateway
11. 重置 session — `echo '{}' > sessions.json` + 再次重启 gateway
12. 让用户在飞书上实际测一次，确认 bot 调了正确的 tool

## 2026-02-17 研报结构化 — 全量提取 + Bot Tool 注册

### 完成了什么
- **全量提取完成**：111 篇研报 × 3 层，全部走 Claude Code 包月额度（$0 额外 API 费用）
  - report_meta_enriched: 111 篇（100%）
  - report_thesis: 155 条投资论点（100 篇有论点）
  - report_metric: 1,230 条财务指标（109 篇有指标）
- **Bot Tool 注册**：在 `report-db-plugin/index.js` 新增 3 个 Schema + 5 个 tool
  - `report_structured_list` — 按公司/赛道/类型搜索结构化研报
  - `report_structured_get` — 获取单篇研报元数据+论点+指标
  - `report_theses` — 跨研报查投资论点（看多/看空/中性）
  - `report_metrics` — 跨研报查财务指标
  - `report_structurize_stats` — 查看提取进度
- Gateway 重启 + 冒烟测试全绿（36 pass / 0 fail）
- **提取方式**：14 个 Claude Code 子 agent 并行处理，用 `_dump_doc.py` 预导出 + `_ingest_extraction.py` 入库

### 踩坑记录
- ❌ `structurize.py` 调 Anthropic API（按量计费），用户以为包月覆盖
  ✅ **铁律：以后默认走 Claude Code 包月额度，API key 只留给贝多多 bot 用**
- ❌ `report_metric.period` 有 NOT NULL 约束，部分文档数据无明确时间
  ✅ 用报告发布年份（如 "2025"）作为默认值，提取时就不能填 null
- ❌ `report_metric` 有 UNIQUE(doc_id, company, period, metric) 约束，同一公司不同维度指标名容易重复
  ✅ 用描述性指标名区分（如 `revenue` vs `hardware_revenue` vs `subscription_revenue`）
- ❌ PPT 类文档大量乱码（encoding artifacts from PDF/PPT export）
  ✅ 只提取能明确读到的内容，theses/metrics 可为空列表，不要猜

### 下次注意事项
- `structurize.py` 仍可用于 API 模式提取（新研报入库时），但日常优先走 Claude Code
- 子 agent 并行提取模式：先 `_dump_doc.py` 导出到 /tmp/bdd_docs/，再批量处理
- 新增研报时只需跑未处理的（支持断点续跑，自动跳过已处理）

## 2026-02-17 研报结构化代码实现

### 完成了什么
- 新增 3 张表（report_meta_enriched, report_thesis, report_metric）到 schema.sql
- 新增 `lib/db_structured.py` — DB 操作层（upsert + 查询）
- 新增 `structurize.py` — CLI 入口，3 层 Claude 提取（Haiku 元数据/指标 + Sonnet 论点）
- 新增 5 个 API 接口：/v1/reports/structured, /v1/reports/{id}/structured, /v1/theses, /v1/metrics, /v1/reports/stats
- 冒烟测试新增 test_structurize_dry_run + test_structured_api，全绿

### 踩坑记录
- ❌ structurize.py dry-run 时 summary print 和 JSON 都输出到 stdout，导致测试 json.loads 失败
  ✅ summary 输出改到 stderr，stdout 保持纯 JSON

## 2026-02-17 KOL 观点日报

### 完成了什么
- 新增 KOL 观点日报模块（kol_config.json + kol_briefing.py + kol_push.py）
- DuckDuckGo 搜索 + YouTube 自动搜索 + Playwright 抓取 + Claude Haiku 摘要
- 飞书 Schema 2.0 卡片，按 Crypto/Tech 分栏推送
- launchd 定时任务每天 07:00 自动执行
- 冒烟测试新增 kol_push dry-run + send 用例，全绿
- GitHub SSH 配置 + 代码推送完成

### 踩坑记录
- ❌ 搜索词 "Brian Armstrong Coinbase" 太泛，搜到说唱歌手 Rich Brian
  ✅ 用引号精确匹配 `"Brian Armstrong" CEO crypto`
- ❌ Claude 输出了解释文字（"说明：提供的文章与此人无关..."）被当成观点
  ✅ prompt 严格约束只输出 bullet point，解析时只保留 `•` 开头的行
- ❌ DuckDuckGo 间歇性报 "Unsupported protocol version" 导致某些 KOL 无结果
  ✅ 加了重试 + 24h→周级 freshness fallback
- ❌ Satya Nadella 第一次搜索完全失败
  ✅ 每个 KOL 配多组 search_queries，提高命中率

### 下次注意事项
- DuckDuckGo 在此环境不稳定（LibreSSL 2.8.3 兼容性问题），重试机制必须有
- YouTube 页面 Playwright 抓不到视频内容，只用搜索摘要
- 飞书卡片 markdown 里 `<font color>` 标签可用，但不支持所有 HTML
- `.env` 在 .gitignore 中，API key 不会被提交

## 2026-02-17 研报批量提取（_ingest_extraction.py 人工模式）

### 完成了什么
- 人工阅读 8 篇研报文档并提取结构化 JSON（无需 Claude API，直接由 Agent 提取）
- 8 篇均成功写入 SQLite：L1（元数据）+ L2（投资论点）+ L3（量化指标）
- 文档覆盖：汽车在线、加密交易所数据包、比特经济理论、谷歌AI竞争格局、生物科技出海、游戏直播（斗鱼）、B站财报、现制茶饮（奈雪/喜茶）

### 踩坑记录
- ❌ report_metric.period 字段不允许 NULL（NOT NULL 约束），但文档中有些数据没有明确时间
  ✅ 提取时所有 period 必须填字符串，对于无明确时间的数据用报告发布年份（如 "2021"）作为默认值，绝不能填 null
- ❌ 批量提取时第一次没检查 schema 约束，第 3 个文档就报 IntegrityError
  ✅ 提取完所有 JSON 后先用脚本扫描 null period 再批量 ingest，或提取时就不写 null

### 下次注意事项
- `_ingest_extraction.py` 读取 stdin JSON，格式严格按规范：period 必须是字符串
- metrics 中的 null period 要在写 JSON 时就处理掉，用年份字符串（"2021"、"2025"等）替代
- 对于 PPT 类文档（大量 NLVC 水印、garbled text），只提取能明确读到的内容，theses/metrics 可为空列表
