---
description: 跑冒烟测试 — 快速验证服务状态
allowed-tools: [Bash, Read]
argument-hint: [--full | --quick | 留空=标准测试]
---

# 跑冒烟测试

参数: $ARGUMENTS

## 执行逻辑

根据参数选择测试模式:

- `--full` → 完整测试（含飞书发送）
- `--quick` → 快速测试（跳过 TradingView 截图）
- 留空或其他 → 标准测试（含截图，重启 API）

### 步骤

1. 执行对应的测试命令:

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

2. 如果有 FAIL，读日志分析原因:
   ```
   cat /Users/beiduoudo/Desktop/贝多多/数据库/_index/logs/query_api.log
   ```

3. 汇报结果，格式:
   ```
   ## 测试结果
   模式: [标准/完整/快速]
   XX passed, X failed, X skipped

   [如果有 FAIL，列出失败项和原因]
   ```
