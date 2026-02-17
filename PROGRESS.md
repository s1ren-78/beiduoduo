# PROGRESS — 贝多多项目进度

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
