# Beiduoduo Report Mirror Runbook

这个目录现在承载“贝多多单 Bot 研报查询系统”的后端实现：

1. 本地研报导入（`/Users/beiduoudo/Desktop/贝多多/数据库`）
2. 飞书白名单同步（space/folder/doc）
3. PostgreSQL 结构化索引
4. Query API（给 OpenClaw 和网页前端）

## 目录约定

- 研报源目录：`/Users/beiduoudo/Desktop/贝多多/数据库`
- 索引目录：`/Users/beiduoudo/Desktop/贝多多/数据库/_index`
- raw 落盘：`/Users/beiduoudo/Desktop/贝多多/数据库/_index/raw`
- checkpoint：`/Users/beiduoudo/Desktop/贝多多/数据库/_index/checkpoints`
- logs：`/Users/beiduoudo/Desktop/贝多多/数据库/_index/logs`

## 1) 一次性初始化

### A. 安装 Python 依赖

```bash
cd /Users/beiduoudo/Desktop/贝多多/feishu_mirror
python3 -m pip install -r requirements.txt
```

### B. 准备 PostgreSQL（推荐 Postgres.app）

- 确保 `127.0.0.1:5432` 可连接，数据库名 `beiduoduo`。

### C. 创建 schema

```bash
psql "postgresql://beiduoduo:change_me@127.0.0.1:5432/beiduoduo" \
  -f /Users/beiduoudo/Desktop/贝多多/feishu_mirror/schema.sql
```

### D. 配置环境变量

```bash
cp /Users/beiduoudo/Desktop/贝多多/feishu_mirror/.env.example /Users/beiduoudo/Desktop/贝多多/feishu_mirror/.env
```

然后把 `.env` 里的 `FEISHU_APP_ID / FEISHU_APP_SECRET` 改成你的值。

## 2) 同步任务

### 本地全量导入（首跑）

```bash
cd /Users/beiduoudo/Desktop/贝多多/feishu_mirror
python3 ingest_local_full.py
```

### 本地增量导入（周期）

```bash
cd /Users/beiduoudo/Desktop/贝多多/feishu_mirror
python3 ingest_local_incremental.py
```

### 飞书全量同步（白名单）

> 先在 `report_whitelist` 表中插入白名单条目（`space`/`folder`/`doc`）。可直接参考 `whitelist.sql.example`。

```bash
cd /Users/beiduoudo/Desktop/贝多多/feishu_mirror
python3 sync_feishu_full.py
```

### 飞书增量同步（白名单）

```bash
cd /Users/beiduoudo/Desktop/贝多多/feishu_mirror
python3 sync_feishu_incremental.py
```

## 3) Query API

启动服务：

```bash
cd /Users/beiduoudo/Desktop/贝多多/feishu_mirror
python3 query_api.py
```

默认监听：`127.0.0.1:8788`。

### API 列表

- `GET /v1/search?q=&top_k=&source=&tag=&from=&to=`
- `GET /v1/docs/{doc_id}`
- `POST /v1/sync/run`
- `GET /v1/sync/status`
- `GET /health`

## 4) 定时策略

已提供脚本自动写入 crontab：

```bash
cd /Users/beiduoudo/Desktop/贝多多/feishu_mirror
./setup_cron.sh
```

会安装三条任务：

1. 每 10 分钟本地增量
2. 每 15 分钟飞书增量
3. 每日 02:30 校验型全量（`sync_all_full.py`）

## 5) OpenClaw 对接原则

1. 贝多多优先调用 `report_search`。
2. 未命中时调用 `report_sync_now(scope=feishu, mode=incremental, reason=miss)`。
3. 补拉后重查并返回引用。

## 6) 当前支持格式

- 支持：`pdf`, `docx`, `md`, `pptx`, `xlsx`
- 暂不支持：`xmind`（会记录到 `report_source_file` 且 `is_supported=false`）
