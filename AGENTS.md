# AGENTS.md

## 项目概览

**镜衡** — 照见盲点，衡定策略

一款帮助用户形成可执行投资策略并持续复盘改进的AI投资策略思辨工具。核心功能：
- **AI多空辩论**：强制展示正反两面论据，暴露投资逻辑盲点
- **策略教练引导**：将辩论结论转化为可执行的量化策略卡片
- **卷宗系统**：追溯策略演变，归因每笔交易的决策质量

## 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | Next.js 14 + React 18 + TailwindCSS + shadcn/ui |
| **后端** | Python 3.12 + FastAPI |
| **AI** | DeepSeek (deepseek-chat)，openai SDK 直连 |
| **数据源** | AkShare (A股数据) |
| **知识库** | RAG (BGE-M3 向量检索 + SQLite向量存储) |
| **数据库** | SQLite |

## 目录结构

```
projects/
├── backend/
│   ├── app.py               # FastAPI 入口 (端口8000)：app/CORS/startup/路由注册
│   ├── schemas.py           # 共享 Pydantic 模型
│   ├── helpers.py           # 共享工具函数（卷宗删除、持仓推算、教练状态机等）
│   └── routers/             # 按职责拆分的路由
│       ├── stock.py         # /api/health、/api/rag/stats、/api/stock/search
│       ├── dossier.py       # /api/dossier/*、/api/export/dossier/*
│       ├── strategy.py      # /api/strategy/*
│       ├── transaction.py   # /api/transaction/*
│       └── debate.py        # /api/debate/*（SSE辩论、教练、金融科普）
├── frontend/
│   ├── app/
│   │   ├── page.tsx         # 首页/引导页
│   │   ├── search/          # 股票搜索页
│   │   ├── dossier/         # 卷宗列表页
│   │   └── brainstorm/      # 头脑风暴室
│   ├── components/
│   │   └── AppLayout.tsx    # 主布局组件
│   ├── lib/
│   │   └── api.ts           # 前端API调用封装
│   └── types/
│       └── index.ts         # TypeScript类型定义
├── modules/
│   └── debate/
│       ├── orchestrator.py  # 辩论编排器
│       ├── agents.py        # 多头/空头Agent Prompt
│       ├── data_card.py     # 数据卡生成
│       ├── source_tagger.py # 信源标注(简化版)
│       └── fact_check.py    # 事实校验(简化版)
├── services/
│   ├── db_init.py           # 数据库初始化
│   ├── akshare_client.py    # A股数据接口
│   ├── llm_client.py        # DeepSeek LLM调用
│   ├── market_data.py       # 行情数据
│   ├── financial_data.py    # 财务数据
│   ├── advanced_data.py     # 高级数据指标
│   ├── commission.py        # 佣金/持仓收益计算
│   ├── knowledge_base.py    # 知识库
│   └── rag/                 # RAG知识增强系统
├── data/
│   └── jingheng.db          # 主数据库
├── config.yaml              # 配置文件
├── .coze                    # 项目启动配置
└── run_backend.py           # 后端启动脚本
```

## 构建与启动

### 开发环境
```bash
# 后端启动 (端口8000)
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload

# 前端启动 (端口5000，自动热更新)
pnpm dev
```

### 生产环境
```bash
# 构建
pnpm build

# 启动
pnpm start
```

## 核心API端点

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api/health` | GET | 健康检查 |
| `/api/stock/search` | GET | 股票搜索 |
| `/api/dossier/list` | GET | 获取卷宗列表 |
| `/api/dossier/create` | POST | 创建卷宗 |
| `/api/dossier/{id}` | GET | 获取卷宗详情 |
| `/api/dossier/{id}/detail` | GET | 获取卷宗完整详情（含策略、交易、持仓） |
| `/api/dossier/{id}/strategies` | GET | 获取策略版本列表 |
| `/api/dossier/{id}/transactions` | GET | 获取交易记录列表 |
| `/api/strategy/{id}` | PUT | 更新策略版本内容 |
| `/api/transaction/create` | POST | 创建交易记录 |
| `/api/debate/run` | POST | 运行辩论（同步） |
| `/api/debate/stream` | GET | SSE流式辩论 |

## 数据库表结构

| 表名 | 说明 |
|------|------|
| `dossier` | 卷宗（用户对某只股票的投资档案） |
| `strategy_version` | 策略版本（可编辑） |
| `"transaction"` | 交易记录（不可编辑） |
| `debate_record` | 辩论记录 |
| `agent_conversation` | Agent对话记录 |

## 开发规范

### 前端
- 使用 shadcn/ui 组件库
- API调用统一通过 `lib/api.ts`
- 类型定义统一在 `types/index.ts`

### 后端
- FastAPI路由顺序：静态路由放在动态路由之前
- 数据库操作使用 `services/db_init.py` 的 `get_db()`
- SQLite保留关键字（如 `transaction`）需要用双引号包裹

## 注意事项

1. **端口规范**：前端5000，后端8000
2. **路由顺序**：FastAPI静态路由必须放在动态路由之前
3. **SQL保留字**：`transaction` 等保留字需用双引号包裹
4. **中文搜索**：AkShare支持中文股票名称搜索

## MVP P0 分阶段开发计划

### 阶段1 ✅ 已完成
- 清理冗余代码
- 搭建基础框架
- 首页/搜索页/卷宗列表页

### 阶段2 ✅ 已完成
- 头脑风暴室完整实现
- SSE流式辩论实时推送
- 裁判裁决系统

### 阶段3 ✅ 已完成
- 卷宗详情页（概览/策略版本/交易记录三个Tab）
- 策略版本管理（查看历史版本，编辑策略内容）
- 交易记录录入（买入/卖出，不可编辑删除）
- 持仓推算（累计买入卖出、平均成本、已实现盈亏）

### 阶段4 ✅ 已完成
- 收益曲线 API（按交易记录计算累计收益）
- 数据导出（JSON/CSV）

## 常见问题：代码修改未生效

**现象**：后端或前端代码已修改，但用户看到的内容没有变化。

### 原因分析

| 层级 | 原因 | 解决方案 |
|------|------|----------|
| **后端Python** | `__pycache__` 缓存旧模块 | 清理缓存并重启 |
| **后端uvicorn** | `--reload` 有时未检测到改动 | 手动重启进程 |
| **前端React** | State 持久化（旧会话数据） | 刷新页面或开始新会话 |
| **前端Next.js** | `.next` 缓存旧编译产物 | 删除 `.next` 目录 |
| **浏览器** | 缓存旧页面/JS | 硬刷新 Ctrl+F5 |

### 标准排查流程

```bash
# 1. 清理Python缓存
cd /workspace/projects && rm -rf modules/__pycache__ modules/debate/__pycache__ backend/__pycache__ services/__pycache__

# 2. 重启后端（杀掉所有uvicorn进程，重新启动）
pkill -f "uvicorn backend.app"
cd /workspace/projects && python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 &

# 3. 验证后端生效（直接调用API检查返回内容）
curl -s -X POST -H 'Content-Type: application/json' -d '{"..."}' http://localhost:8000/api/debate/coach

# 4. 清理Next.js缓存（如果前端编译异常）
cd /workspace/projects/frontend && rm -rf .next

# 5. 前端生效：用户需刷新页面或开始新会话
# React state 在页面刷新时清空，旧会话数据不会自动更新
```

### 关键提醒

⚠️ **Prompt修改特别注意**：
- LLM Prompt 修改后，**必须用 curl 直接测试后端 API** 验证返回内容是否变化
- 用户看到的旧内容可能是**旧会话的 React State**，不是代码未生效
- 告知用户：**刷新页面** 或 **开始新辩论会话** 才能看到变化

⚠️ **React State 持久化**：
- 前端没有 localStorage 缓存，但 React State 在当前会话中持久存在
- 辩论完成后教练初始化，消息存入 `coachMessages` state
- 修改 Prompt 后，**已存在的教练消息不会自动更新**
- 只有新的辩论会话才会使用新 Prompt
