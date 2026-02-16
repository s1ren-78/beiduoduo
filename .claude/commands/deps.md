---
description: 检查过期依赖和安全漏洞 — Python + Node.js
allowed-tools: [Bash, Read]
---

# 依赖健康检查

## 检查范围

本项目有两套依赖：
- Python: `feishu_mirror/requirements.txt`
- Node.js: `report-db-plugin/package.json`

## 流程

### 1. Python 依赖检查

#### 过期检查
```bash
cd /Users/beiduoudo/Desktop/贝多多/feishu_mirror && pip3 list --outdated --format=columns 2>/dev/null
```

#### 安全漏洞检查
优先用 `pip-audit`，没装就用 `pip3 check`：
```bash
pip-audit -r /Users/beiduoudo/Desktop/贝多多/feishu_mirror/requirements.txt 2>/dev/null || pip3 check 2>/dev/null
```

### 2. Node.js 依赖检查

#### 过期检查
```bash
cd /Users/beiduoudo/Desktop/贝多多/report-db-plugin && npm outdated 2>/dev/null
```

#### 安全漏洞检查
```bash
cd /Users/beiduoudo/Desktop/贝多多/report-db-plugin && npm audit 2>/dev/null
```

### 3. 汇报结果

用表格格式汇总：

```
## 依赖健康报告

### Python (feishu_mirror)
| 包名 | 当前版本 | 最新版本 | 状态 |
|------|---------|---------|------|

### Node.js (report-db-plugin)
| 包名 | 当前版本 | 最新版本 | 状态 |
|------|---------|---------|------|

### 安全漏洞
- [列出发现的漏洞，没有就写"未发现已知漏洞"]

### 建议
- [只列出需要关注的项，不要建议升级所有东西]
```

### 注意
- 只报告**有意义的**过期项（major/minor 版本差距），patch 版本差异不用报
- 如果某个工具没装（如 pip-audit），提示用户可以装，但不阻塞检查
- 不要自动升级任何依赖，只报告
