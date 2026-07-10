# DeepRCA-Agent

基于深度学习的根本原因分析（Root Cause Analysis）故障诊断智能体系统。采用 LangGraph 状态机驱动的多 Agent 协同架构，实现从告警接入到根因定位的全自动化故障分析闭环。

## 项目背景

本项目旨在构建一个自动化的故障诊断智能体，替代传统人工排障流程。系统接收到告警后，自动执行六维度分析（变更/上游流量/下游依赖/集群状态/ErrorLog/已知问题），通过三层 Agent 协同推理定位根因，并输出可执行的修复建议。

核心设计参考：
- 美团 AIOps 故障处理助手（多 Agent 协同推理、满意度收集闭环、多维指标筛选根因定位）
- [open-swe](https://github.com/langchain-ai/open-swe)（Deep Agents + Subagent + Middleware 编排模式）

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Gateway                       │
│            REST API + WebSocket 实时推送                  │
├─────────────────────────────────────────────────────────┤
│                  General Analyzer (L1)                   │
│    Intake → Planner → Dispatcher → Collector → Reporter  │
├──────────┬──────────┬──────────┬──────────┬─────────────┤
│ DB Expert│Redis Exp │Mafka Exp │ RPC Exp  │ Change/Log  │
│  (L2)    │  (L2)    │  (L2)    │  (L2)    │   (L2)      │
├──────────┴──────────┴──────────┴──────────┴─────────────┤
│                Root Cause Agent (L3)                     │
│  指标筛选 → 多维对比 → 异常检测 → 证据排序 → 规则匹配 → LLM │
├─────────────────────────────────────────────────────────┤
│                   Mock Environment                       │
│    K8s Sim | MySQL Sim | Redis Sim | Kafka Sim | μSvc   │
└─────────────────────────────────────────────────────────┘
```

### 三层 Agent 架构

| 层级 | Agent | 职责 | 关键能力 |
|------|-------|------|----------|
| L1 | General Analyzer | 告警解析、任务规划、并发调度、报告生成 | 六维度规划、asyncio.gather 并发、证据池聚合 |
| L2 | Domain Expert (×6) | 领域专项分析（DB/Redis/Mafka/RPC/Change/ErrorLog） | 各领域 6 项检查、专属工具集、置信度聚合 |
| L3 | Root Cause Agent | 根因定位与推理 | 四分位异常检测、多维对比、专家规则引擎、LLM 推理 |

### 核心算法

- **QuantileAnomalyDetector**：四分位 IQR 异常检测，替代大模型做异常判断，降低幻觉风险
- **VolatilityDetector**：滚动标准差波动性突变检测
- **MultiDimensionComparator**：周同比（WoW）+ 日环比（DoD）双重确认
- **MetricFilter + NoiseFilter**：多维指标筛选 + 低影响抖动过滤
- **ExpertRuleEngine**：8 条专家经验规则（R001-R008），支持 `set_root_cause` / `boost_confidence` 两种动作

### 技术栈

| 类别 | 技术选型 |
|------|----------|
| Agent 编排 | LangGraph (StateGraph, 子图嵌套, Annotated reducer) |
| LLM 框架 | LangChain (@tool, Prompt 模板, 记忆管理) |
| API 层 | FastAPI + WebSocket |
| 并发处理 | asyncio.gather + ThreadPoolExecutor |
| 数据存储 | Redis (Squirrel 缓存) |
| 验证环境 | Docker Compose (K8s/MySQL/Redis/Kafka/微服务模拟器) |

## PRD 文档索引

| 文档 | 说明 |
|------|------|
| [01_overview_prd.md](prds/01_overview_prd.md) | 总体架构、技术选型、状态设计、项目目录结构、里程碑 |
| [02_general_analyzer_prd.md](prds/02_general_analyzer_prd.md) | 通用分析 Agent：六节点工作流、工具接口、验证 API |
| [03_domain_expert_prd.md](prds/03_domain_expert_prd.md) | 领域专家子 Agent：DB/Redis/Mafka/RPC/Change/ErrorLog |
| [04_root_cause_prd.md](prds/04_root_cause_prd.md) | 根因定位 Agent：异常检测算法、专家规则引擎、LLM 推理 |
| [05_mock_env_prd.md](prds/05_mock_env_prd.md) | 验证接口与模拟环境：K8s/中间件/微服务模拟器、38 个 API |
| [06_containerization_prd.md](prds/06_containerization_prd.md) | 容器化部署与冒烟测试：Dockerfile、Compose Profile、冒烟测试工作流 |

## 快速启动

### 环境要求

- Python 3.11+
- Docker & Docker Compose
- Redis 7+

### 安装

```bash
# 克隆仓库
git clone https://github.com/HeafeyM/DeepRCA-Agent.git
cd DeepRCA-Agent

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，配置以下变量：
# LLM_API_KEY=your-api-key
# LLM_MODEL=your-model-name
# REDIS_URL=redis://localhost:6379/0
# MOCK_ENV_ENABLED=true
```

### 启动服务

```bash
# 方式一：Docker Compose 一键启动（推荐）
# 完整环境（Redis + Agent + Mock Env）
docker compose --profile full up -d

# 冒烟测试（自动构建并执行，测试完毕后退出）
docker compose --profile smoke up --build --abort-on-container-exit

# 仅 Agent + Redis（对接外部 Mock）
docker compose --profile agent up -d

# 仅 Mock 环境（独立调试模拟器）
docker compose --profile mock up -d

# 方式二：本地开发模式
redis-server
uvicorn deeprca.main:app --reload --port 8000   # Agent 服务
uvicorn mock_env.main:app --reload --port 8001   # 模拟环境（另开终端）
```

### 验证

```bash
# 运行预设端到端测试场景
curl -X POST http://localhost:8000/api/v1/mock/scenarios/db_slave_delay_timeout/run

# 查看分析结果
curl http://localhost:8000/api/v1/analyze/status/{trace_id}
```

## 项目结构

```
DeepRCA-Agent/
├── prds/                           # PRD 文档
│   ├── 01_overview_prd.md
│   ├── 02_general_analyzer_prd.md
│   ├── 03_domain_expert_prd.md
│   ├── 04_root_cause_prd.md
│   └── 05_mock_env_prd.md
├── deeprca/                        # 核心代码（待实现）
│   ├── agents/
│   │   ├── general_analyzer.py     # L1 通用分析 Agent
│   │   ├── domain_experts/         # L2 领域专家 Agent
│   │   │   ├── base.py
│   │   │   ├── db_expert.py
│   │   │   ├── redis_expert.py
│   │   │   ├── mafka_expert.py
│   │   │   ├── rpc_expert.py
│   │   │   ├── change_agent.py
│   │   │   └── errorlog_agent.py
│   │   └── root_cause.py           # L3 根因定位 Agent
│   ├── algorithms/                 # 核心算法
│   │   ├── anomaly_detector.py     # 四分位+波动检测
│   │   ├── comparator.py           # 多维对比
│   │   ├── metric_filter.py        # 指标筛选+噪声过滤
│   │   └── rule_engine.py          # 专家规则引擎
│   ├── models/                     # 数据模型
│   │   ├── state.py                # DeepRCAState
│   │   ├── evidence.py             # EvidencePool
│   │   └── result.py               # 分析结果
│   ├── tools/                      # LangChain 工具
│   ├── api/                        # FastAPI 路由
│   └── main.py                     # 服务入口
├── mock_env/                       # 模拟环境（待实现）
│   ├── k8s_simulator.py
│   ├── mysql_simulator.py
│   ├── redis_simulator.py
│   ├── kafka_simulator.py
│   ├── microservice_simulator.py
│   ├── alert_simulator.py
│   └── main.py
├── tests/                          # 测试
│   ├── smoke/                      # 冒烟测试（Docker 容器内执行）
│   │   ├── conftest.py
│   │   ├── entrypoint.sh
│   │   ├── test_health.py
│   │   ├── test_e2e_scenarios.py
│   │   └── test_{module}.py
│   ├── unit/
│   └── integration/
├── deeprca/
│   └── Dockerfile                  # Agent 服务镜像
├── mock_env/
│   └── Dockerfile                  # 模拟环境镜像
├── tests/
│   └── Dockerfile                  # 冒烟测试镜像
├── docker-compose.yml              # Compose 编排（Profile: full/agent/mock/smoke）
├── requirements.txt
├── requirements-mock.txt
├── requirements-dev.txt
├── .env.example
├── .gitignore
└── README.md
```

## 开发里程碑

| 阶段 | 内容 | 周期 |
|------|------|------|
| M1 | 基础框架搭建：项目骨架、状态定义、API 入口 | 第 1 周 |
| M2 | L1 通用分析 Agent：六节点工作流、工具接口 | 第 2-3 周 |
| M3 | L2 领域专家 Agent：DB/Redis/Mafka/RPC | 第 4-5 周 |
| M4 | L3 根因定位 Agent：异常检测+规则引擎+LLM 推理 | 第 6-7 周 |
| M5 | 模拟环境：K8s/中间件/微服务模拟器 | 第 8-9 周 |
| M6 | 端到端集成：5 个预设场景验证 | 第 10 周 |
| M7 | 性能优化与文档完善 | 第 11-12 周 |

## 性能指标

| 指标 | 目标 |
|------|------|
| 端到端分析延迟 | ≤ 30s |
| 根因定位耗时 | ≤ 10s |
| 根因命中率 | ≥ 50% |
| 并发分析能力 | ≥ 10 条告警/分钟 |

## License

MIT
