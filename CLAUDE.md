# 贝多多 — Claude Code 开发规范

## 项目结构

```
feishu_mirror/          # 主 Python 服务 (FastAPI on :8788)
  query_api.py          # API 入口
  lib/chart_render.py   # K线图渲染 (TradingView + mplfinance)
  lib/feishu_api.py     # 飞书 API 客户端
  lib/market_api.py     # 行情数据 (yfinance + Artemis)
  tests/smoke_test.py   # 冒烟测试
report-db-plugin/       # OpenClaw 插件 (Node.js)
  index.js              # 工具注册
数据库/_index/logs/     # 日志目录
```

## 开发流程 — 必须遵守

### 改完代码后，自己跑测试，不要让用户当测试员

每次修改 `feishu_mirror/` 或 `report-db-plugin/` 后，**必须**按以下顺序验证：

#### 1. 重启 API + 跑冒烟测试

```bash
cd /Users/beiduoudo/Desktop/贝多多/feishu_mirror
python3 tests/smoke_test.py --restart
```

所有 PASS 才算通过。如果有 FAIL，修复后重跑，直到全绿。

#### 2. 完整测试（含飞书发送）

```bash
python3 tests/smoke_test.py --restart --full
```

这会实际往飞书发图，验证端到端链路。

#### 3. 快速测试（跳过 TradingView）

```bash
python3 tests/smoke_test.py --quick
```

只跑数据接口和本地渲染，适合改了非截图相关代码时用。

#### 4. 如果改了插件 (report-db-plugin/index.js)

```bash
/Users/beiduoudo/.openclaw/bin/openclaw gateway restart
```

然后跑完整测试确认。

### 测试不通过就不要告诉用户"好了"

- 不要在测试未通过时就说"改好了，你试试"
- 不要吞掉异常 (`except: pass`) 而不加 logging
- 查 log 确认没有 ERROR: `cat 数据库/_index/logs/query_api.log`

## 关键技术约束

### Playwright (TradingView 截图)

- **线程亲和性**: Playwright sync API 绑定创建它的线程。绝对不能在 `ThreadPoolExecutor` 的短命工作线程里创建浏览器
- **浏览器复用**: `_get_browser()` 使用 `threading.Lock` + 全局实例，进程级复用
- **页面加载**: 用 `domcontentloaded` + `wait_for_selector("canvas")`，不要用 `networkidle`（TradingView 会加载大量 analytics JS，networkidle 要等 20s+）
- **清理**: `atexit.register(_cleanup_playwright)` 确保进程退出时关闭 Chromium

### 飞书图片发送

- `open_id` 来源: 插件 `resolveFeishuOwner()` → 从 openclaw config 或 hardcoded fallback 获取
- Owner open_id: `ou_ec332c4e35a82229099b7a04b89488ee`
- 如果 `sent_to` 不在响应里，说明飞书发送失败了

### 常见坑

| 坑 | 原因 | 解法 |
|----|------|------|
| `python` 命令不存在 | macOS 默认只有 `python3` | 始终用 `python3` |
| 端口 8788 被占用 | 旧进程没杀干净 | `lsof -ti:8788 \| xargs kill -9` |
| TradingView 截图 30s | 用了 `networkidle` | 改用 `domcontentloaded` |
| 第二次截图崩溃 | Playwright 在已死的线程上 | 不要用 ThreadPoolExecutor 包 Playwright |
| chart_render 500 | bot 只传 symbol 不传 data，TV 失败后 fallback 需要 data | 加 `if not data: raise 400` |
| 图没发到飞书 | `resolveFeishuOwner` 拿不到 open_id | hardcoded fallback |

## Slash Commands

| 命令 | 用途 |
|------|------|
| `/dev <需求>` | TDD 开发模式：理解需求 → 先写测试 → 实现 → 自测迭代到全绿 → 交付 |
| `/test [--full\|--quick]` | 快速跑冒烟测试，默认标准模式（含截图+重启） |

- `/dev` 强制走 5 个 Phase，测试全绿前不交付
- `/test` 不带参数 = `smoke_test.py --restart`，`--full` 含飞书发送，`--quick` 跳过截图

## 服务管理

```bash
# Query API
lsof -ti:8788 | xargs kill -9    # 停
cd feishu_mirror && nohup python3 query_api.py > ../数据库/_index/logs/query_api.log 2>&1 &  # 启

# Gateway
/Users/beiduoudo/.openclaw/bin/openclaw gateway restart
/Users/beiduoudo/.openclaw/bin/openclaw health
```
