---
description: 智能提交 — 质量检查 + 自动分析变更 + 生成 commit message
allowed-tools: [Bash, Read, Glob, Grep]
argument-hint: [commit message，留空则自动生成]
---

# 智能提交

用户提供的 commit message: $ARGUMENTS

## 流程

### Step 1: 检查变更

运行 `git status` 和 `git diff --stat` 查看当前变更。
如果没有任何变更（无 untracked、无 modified），直接告诉用户"没有可提交的变更"并结束。

### Step 2: 快速质量检查

只检查关键问题，不跑完整测试：

1. 检查是否有敏感文件被改动（.env、credentials、API key 等）：
   ```
   git diff --cached --name-only | grep -iE '\.env|credential|secret|apikey' || true
   ```
   如果有，**警告用户**，但不阻止提交。

2. 检查 Python 语法错误（只检查改动的 .py 文件）：
   ```
   git diff --name-only -- '*.py' | xargs -I {} python3 -m py_compile {} 2>&1
   ```
   如果有语法错误，**阻止提交**，列出错误。

### Step 3: 分析变更 & 生成 commit message

1. 运行 `git diff` 查看具体改动内容
2. 运行 `git log --oneline -5` 了解最近的 commit 风格

如果用户提供了 commit message，直接用。
如果用户没提供（$ARGUMENTS 为空），根据变更自动生成：

- 前缀规则：
  - 改了测试文件 → `test: `
  - 改了文档/README → `docs: `
  - 改了依赖 → `deps: `
  - 新增功能 → `feat: `
  - 修 bug → `fix: `
  - 重构 → `refactor: `
  - 其他 → `update: `
- 用中文写 message，简洁一句话

### Step 4: 执行提交

1. `git add` 相关文件（不要用 `git add -A`，按文件名添加）
2. 用 heredoc 格式提交：
   ```
   git commit -m "$(cat <<'EOF'
   生成的 commit message

   Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
   EOF
   )"
   ```

### Step 5: 汇报

```
## 已提交 ✓

commit: <hash 前 7 位>
message: <commit message>
files: <改动文件数> 个文件, +<增加行数> -<删除行数>
```

**不要自动 push**。如果用户需要 push，让他们单独说。
