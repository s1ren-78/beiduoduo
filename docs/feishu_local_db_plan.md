# 飞书全量导出到本地 + OpenClaw 本地预读实施路

## 1. 目标

你要达到的状态：

1. 飞书数据先全量拉到 Mac mini 本地。
2. 本地建立一份可查询数据库（不再每次遍历飞书）。
3. OpenClaw 和未来前端统一读本地库。
4. 后续只跑增量同步，成本和响应时间都可控。

## 2. 边界先说清

“飞书所有数据”在技术上是“你给这个应用授权范围内的所有数据”，不可能越权读取。

首版建议覆盖这 5 类：

1. Wiki/知识库结构（空间、节点）
2. Docx 文档正文
3. Drive 文件元数据与可导出内容
4. 多维表格（Bitable）
5. IM 消息（你授权的范围）

## 3. 目标架构

```text
Feishu OpenAPI
   │
   │(full + incremental)
   ▼
Sync Worker (Python)
   ├─ raw lake(JSONL/附件) -> /Users/beiduoudo/Desktop/贝多多/data/feishu/raw
   └─ normalize -> PostgreSQL(local)
                    ├─ feishu_raw_*
                    ├─ feishu_doc/bitable/message
                    └─ search_chunk(+可选向量)

Query API (FastAPI)
   ├─ /search
   ├─ /doc/{token}
   ├─ /bitable/{app}/{table}
   └─ /message/{chat}

OpenClaw / 前端
   └─ 只读 Query API（不直接扫飞书）
```

## 4. 本地目录规范（直接照这个建）

```text
/Users/beiduoudo/Desktop/贝多多/
  feishu_mirror/
    .env.example
    schema.sql
    README.md
  data/
    feishu/
      raw/
        wiki/
        docx/
        drive/
        bitable/
        im/
      checkpoints/
      exports/
```

## 5. 实施路径（按阶段执行）

## Phase A：鉴权与权限

1. 飞书开放平台创建或复用应用。
2. 配齐所需 scopes（Wiki/Docx/Drive/Bitable/IM 读取）。
3. 用 `app_id/app_secret` 获取 tenant access token。

官方文档（建议你用这些做最终校验）：

- Tenant Access Token: https://open.feishu.cn/document/server-docs/authentication-management/access-token/tenant_access_token_internal
- Wiki space list: https://open.feishu.cn/document/server-docs/docs/wiki-v2/space/list
- Wiki node list: https://open.feishu.cn/document/server-docs/docs/wiki-v2/space-node/list
- Docx raw content: https://open.feishu.cn/document/server-docs/docs/docs/docx-v1/document/raw_content
- Drive file get: https://open.feishu.cn/document/server-docs/docs/drive-v1/file/get
- Drive export: https://open.feishu.cn/document/server-docs/docs/drive-v1/export_task/create
- Bitable table list: https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table/list
- Bitable record list: https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table-record/list
- IM message list: https://open.feishu.cn/document/server-docs/im-v1/message/list

## Phase B：全量导出（一次性）

顺序建议：

1. 先拉 Wiki 空间与节点树，建立对象清单。
2. 按节点类型拉 Docx/Drive 内容。
3. 拉 Bitable（app->table->record）。
4. 拉 IM 历史消息。
5. 每个 API 分页抓取，结果写入 `data/feishu/raw/<domain>/YYYY-MM-DD/*.jsonl`。

关键要求：

1. 每个对象都记录 `source_id`, `updated_time`, `etag/hash`, `fetched_at`。
2. 全量过程同时写入 `checkpoints`（游标/时间戳），为增量准备。

## Phase C：入库与索引

1. 执行 `feishu_mirror/schema.sql` 建表。
2. 把 raw JSONL 解析后入标准化表（doc/wiki/bitable/im）。
3. 生成搜索索引（全文检索，后续可加向量检索）。

## Phase D：增量同步（常驻）

1. 每 5~15 分钟跑增量任务。
2. 用 checkpoint 按 `updated_time` 或 `page_token` 拉变化。
3. Upsert 到库，保留变更日志。

## Phase E：给 OpenClaw 和前端用

1. 起一个本地 Query API（FastAPI）。
2. OpenClaw 的主控规则改成优先查询本地 API，不再直接扫飞书。
3. 前端统一调用 Query API，同一份数据源。

## 6. 与 OpenClaw 的集成策略

建议策略：

1. 主路径：`OpenClaw -> Query API -> PostgreSQL`
2. 兜底路径：本地未命中时，才触发一次飞书实时拉取并回填数据库。

这样你后续提问时：

1. 先命中本地库（毫秒级到秒级）。
2. 没命中才补拉，且补拉后下次就命中。

## 7. 验收标准

你可以用这 6 条验收：

1. 全量导出后，本地 raw 文件存在并可追溯。
2. PostgreSQL 至少有 doc/wiki/bitable/im 四类数据。
3. 任一关键词检索返回结果 < 2 秒。
4. 增量任务能在 15 分钟内反映飞书新增/更新。
5. OpenClaw 查询优先读本地，不再每次全量遍历飞书。
6. 前端与 OpenClaw 对同一问题返回一致数据口径。

## 8. 你下一步直接做什么

1. 先补齐飞书应用 scopes
2. 在本机起 PostgreSQL。
3. 执行 `feishu_mirror/schema.sql`。
4. 开始跑全量导出任务。
5. 导完立刻切 OpenClaw 到本地 Query API 模式。

