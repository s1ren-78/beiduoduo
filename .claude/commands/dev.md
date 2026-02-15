---
description: TDD 开发模式 — 先测试后交付，自己迭代到全绿再汇报
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, Task, AskUserQuestion, EnterPlanMode, ExitPlanMode, TaskCreate, TaskUpdate, TaskList, TaskGet]
argument-hint: <需求描述>
---

# TDD 开发模式

用户需求: $ARGUMENTS

## 你的工作流程 — 严格按顺序执行

### Phase 1: 理解需求 (不写代码)

1. 读 CLAUDE.md 了解项目约定
2. 读相关源码，理解当前实现
3. 用 1-2 句话总结你理解的需求，告诉用户，等确认
4. 如果需求不明确，用 AskUserQuestion 追问，**不要猜**

### Phase 2: 先写测试 (定义"完成"的标准)

1. 在 `feishu_mirror/tests/smoke_test.py` 里新增测试用例，覆盖这次需求的验收标准
2. 如果需求涉及新端点/新功能，写对应的 `test_xxx()` 函数
3. 如果是 bug 修复，写一个能复现 bug 的测试（改完后应该 PASS）
4. 运行测试确认新用例是 FAIL（证明测试有效，不是空测试）:
   ```
   cd /Users/beiduoudo/Desktop/贝多多/feishu_mirror && python3 tests/smoke_test.py --restart --quick
   ```

### Phase 3: 实现代码

1. 用 TaskCreate 建任务列表，拆分实现步骤
2. 逐步实现，每改一个文件就保存

### Phase 4: 自测迭代 (关键！)

1. 运行完整测试:
   ```
   cd /Users/beiduoudo/Desktop/贝多多/feishu_mirror && python3 tests/smoke_test.py --restart
   ```
2. 如果有 FAIL:
   - 读日志: `cat /Users/beiduoudo/Desktop/贝多多/数据库/_index/logs/query_api.log`
   - 分析原因，修复代码
   - 重跑测试
   - **重复直到 0 FAIL**
3. 如果涉及飞书发送，跑 `--full` 模式:
   ```
   python3 tests/smoke_test.py --restart --full
   ```
4. 如果改了 `report-db-plugin/index.js`:
   ```
   /Users/beiduoudo/.openclaw/bin/openclaw gateway restart
   ```

### Phase 5: 交付

**只有测试全绿后**才能向用户汇报。汇报格式:

```
## 完成

### 改了什么
- [简述改动]

### 测试结果
XX passed, 0 failed, X skipped

### 需要你验证的
- [如果有测试覆盖不到的场景，明确告诉用户]
```

## 红线 — 绝对不能做的事

- **不要**在测试没跑过的情况下说"改好了"
- **不要** `except: pass` 吞掉异常而不加 logging
- **不要**删掉已有的测试用例
- **不要**让测试靠放宽断言来"通过"（比如把 `< 10s` 改成 `< 60s`）
- **不要**跳过 Phase 2，直接写代码不写测试

## 常用命令速查

```bash
# 快速测试（跳过 TradingView 截图）
python3 tests/smoke_test.py --quick

# 标准测试（含截图）
python3 tests/smoke_test.py --restart

# 完整测试（含飞书发送）
python3 tests/smoke_test.py --restart --full

# 查日志
cat /Users/beiduoudo/Desktop/贝多多/数据库/_index/logs/query_api.log

# 杀 API
lsof -ti:8788 | xargs kill -9

# 重启 Gateway
/Users/beiduoudo/.openclaw/bin/openclaw gateway restart
```
