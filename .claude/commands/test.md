---
description: 跑冒烟测试 — 快速验证服务状态，失败自动分析
allowed-tools: [Bash, Read, Grep]
argument-hint: [--full | --quick | 留空=标准测试]
---

# 跑冒烟测试

参数: $ARGUMENTS

## 执行逻辑

根据参数选择测试模式:

- `--full` → 完整测试（含飞书发送）
- `--quick` → 快速测试（跳过 TradingView 截图）
- 留空或其他 → 标准测试（含截图，重启 API）

### Step 1: 执行测试

- 标准测试（默认）:
  ```
  cd /Users/beiduoudo/Desktop/贝多多/feishu_mirror && python3 tests/smoke_test.py --restart
  ```
- 完整测试 (`--full`):
  ```
  cd /Users/beiduoudo/Desktop/贝多多/feishu_mirror && python3 tests/smoke_test.py --restart --full
  ```
- 快速测试 (`--quick`):
  ```
  cd /Users/beiduoudo/Desktop/贝多多/feishu_mirror && python3 tests/smoke_test.py --quick
  ```

### Step 2: 如果有 FAIL，自动诊断

不要等用户问，直接：

1. 读最近的日志，查 ERROR 和 Traceback：
   ```
   tail -100 /Users/beiduoudo/Desktop/贝多多/数据库/_index/logs/query_api.log
   ```

2. 检查端口占用：
   ```
   lsof -ti:8788 2>/dev/null
   ```

3. 检查进程状态：
   ```
   ps aux | grep query_api | grep -v grep
   ```

4. 根据错误类型给出修复建议：
   - 端口占用 → 建议 `lsof -ti:8788 | xargs kill -9`
   - Import 错误 → 检查依赖是否安装
   - 连接超时 → 检查服务是否启动
   - Playwright 错误 → 检查浏览器是否安装

### Step 3: 汇报结果

全部通过时简短汇报：
```
## 测试通过 ✓
模式: [标准/完整/快速]
XX passed, 0 failed, X skipped (耗时 Xs)
```

有失败时详细汇报：
```
## 测试结果 ✗
模式: [标准/完整/快速]
XX passed, X failed, X skipped

### 失败项
- [测试名]: [错误原因]

### 日志关键信息
[从日志中提取的相关 ERROR/Traceback]

### 建议修复
- [具体建议]
```
