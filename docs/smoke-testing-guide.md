# DeepRCA-Agent 冒烟测试教程

> 本文档随每个里程碑完成追加更新。最新版本对应 M1-M5 完成 + M6 冒烟测试框架就绪。

## 1. 环境准备

### 1.1 系统要求

| 项目 | 最低版本 | 推荐 |
|------|----------|------|
| Python | 3.10+ | 3.11+ |
| pip | 23.0+ | 最新 |
| Docker | 24.0+ | 最新 |
| Docker Compose | v2.20+ | 最新 |

### 1.2 克隆仓库

```bash
git clone <仓库地址>
cd DeepRCA-Agent
```

### 1.3 方式 A：本地运行（无需 Docker）

适用于开发调试，仅运行 LangGraph 图层面的端到端测试，不启动 HTTP 服务。

```bash
# 1. 创建虚拟环境
python -m venv venv

# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

# 2. 安装依赖（使用国内镜像加速）
pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，至少设置 MOCK_ENV_ENABLED=true
# LLM_API_KEY 可留空，系统自动降级为 fallback 模式

# 4. 运行全部测试
python -m pytest tests/ -v --tb=short

# 5. 仅运行冒烟测试
python -m pytest tests/smoke/ -v --tb=short

# 6. 仅运行单元测试
python -m pytest tests/unit/ -v --tb=short
```

### 1.4 方式 B：Docker Compose 全链路冒烟测试

适用于 CI/CD 和远程机器验证，自动启动 Redis + Kafka + Agent + Mock 环境 + 测试容器。

```bash
# 一键执行冒烟测试（构建镜像 → 启动服务 → 运行测试 → 退出）
docker compose --profile smoke up --build --abort-on-container-exit

# 查看测试输出
docker compose logs smoke-test

# 清理
docker compose --profile smoke down -v
```

### 1.5 方式 C：Docker Compose 开发环境

适用于需要交互调试的场景，启动全部服务但不含测试容器。

```bash
# 启动完整环境（Redis + Kafka + Agent + Mock Env）
docker compose --profile full up -d

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f agent

# 手动触发测试
curl -X POST http://localhost:8000/api/v1/mock/scenarios/db_slow_query/run

# 查看分析结果
curl http://localhost:8000/api/v1/analyze/status/{trace_id}

# 停止
docker compose --profile full down -v
```

## 2. 测试用例说明

### 2.1 单元测试（tests/unit/）— 42 个用例

| 测试文件 | 用例数 | 验证内容 |
|----------|--------|----------|
| `test_quantile.py` | 9 | 四分位 IQR 异常检测：正常值/高异常/低异常/空基线/单点/边界值/中位数/偏差 |
| `test_volatility.py` | 5 | 波动突变检测：稳定序列/突发尖峰/空序列/短序列/返回字段完整性 |
| `test_comparator.py` | 6 | 多维度对比：正常/显著增长/显著下降/缺失基线/零基线/非空返回 |
| `test_filters.py` | 6 | 指标筛选 + 专家规则引擎：空输入/高 QPS/正常指标/DB 慢查询规则/Redis 内存规则 |
| `test_graph.py` | 9 | LangGraph 图构建：图编译/intake 解析/planner 六维度/collector 聚合/reporter 报告/超时检查 |
| `test_scenarios.py` | 5 | Mock 场景完整性：非空/必需字段/DB 场景/OOM 场景/Kafka 场景 |

### 2.2 冒烟测试（tests/smoke/）— 9 个用例

端到端验证 LangGraph 图从告警输入到报告生成的完整流程，使用 6 个预设 Mock 场景。

| 测试用例 | 场景 | alert_type | 验证点 |
|----------|------|------------|--------|
| `test_graph_compiles` | — | — | LangGraph 图成功编译 |
| `test_pod_crash_scenario` | Pod 崩溃 | error_rate | status / trace_id / task_plan=6 / report 非空 |
| `test_resource_pressure_scenario` | 资源压力 | resource | status / task_plan=6 |
| `test_db_slow_query_scenario` | DB 慢查询 | timeout | status / task_plan=6 / report 非空 |
| `test_redis_timeout_scenario` | Redis 超时 | timeout | status / task_plan=6 |
| `test_traffic_spike_scenario` | 流量突增 | timeout | status / task_plan=6 |
| `test_deployment_failure_scenario` | 部署失败 | error_rate | status / task_plan=6 / report 非空 |
| `test_report_is_valid_json` | 通用超时 | timeout | report 为合法 JSON 且含 trace_id 或 root_cause |
| `test_all_scenarios_covered` | — | — | 6 个预设场景全部注册 |

### 2.3 运行参数说明

```bash
# 显示详细输出（含 print）
python -m pytest tests/smoke/ -v -s --tb=long

# 只运行特定场景
python -m pytest tests/smoke/test_smoke.py::TestSmokeEndToEnd::test_db_slow_query_scenario -v

# 生成测试报告
python -m pytest tests/ -v --html=report.html --self-contained-html

# 并行加速（需安装 pytest-xdist）
python -m pytest tests/ -v -n auto
```

## 3. Docker Compose Profile 说明

| Profile | 启动的服务 | 用途 |
|---------|-----------|------|
| `infra` | redis, kafka | 仅基础设施 |
| `mock` | mock-env | 仅模拟环境 |
| `dev` | redis, kafka, agent, mock-env | 开发调试 |
| `smoke` | redis, kafka, agent, mock-env, smoke-test | 全链路冒烟测试 |
| `full` | redis, kafka, agent, mock-env | 完整环境（不含测试） |

## 4. 预期输出

全部测试通过时输出示例：

```
============================== 51 passed, 1 warning in 17.72s ========================
```

测试失败时排查步骤：
1. 确认 Python 版本 >= 3.10（`python --version`）
2. 确认依赖已安装（`pip install -e ".[dev]"`）
3. 确认 `.env` 文件存在且 `MOCK_ENV_ENABLED=true`
4. Docker 模式下确认所有容器健康（`docker compose ps`）
5. 查看详细错误（`python -m pytest tests/ -v --tb=long`）

## 5. 里程碑完成记录

每个里程碑完成后在此追加更新。

### M1-M5 完成（2026-07-13）

**已完成模块：**
- M1 基础框架：LangGraph `StateGraph`、`DeepRCAState`、配置管理（`settings.py`）
- M2 通用分析 Agent：6 节点工作流（intake → planner → dispatcher → collector → root_cause → reporter）+ 6 维度分析工具
- M3 领域专家子 Agent：DB / Redis / Mafka / RPC 四个子图，各自 6 项检查
- M4 根因定位 Agent：`QuantileAnomalyDetector` + `VolatilityDetector` + `MultiDimensionComparator` + `MetricFilter` + `ExpertRuleEngine`
- M5 Mock 环境：6 个预设场景（Pod 崩溃 / 资源压力 / DB 慢查询 / Redis 超时 / 流量突增 / 部署失败）+ K8s 模拟器 + Service 模拟器

**测试覆盖：**
- 42 个单元测试（异常检测算法 / 图节点 / 场景完整性）
- 9 个冒烟测试（6 场景端到端 + 图编译 + JSON 校验 + 场景覆盖）
- 全部 51 个测试通过，执行时间 ~18s

**已知限制：**
- LLM 降级为 fallback 模式（无 `OPENAI_API_KEY` 时自动使用规则引擎替代）
- Python 3.10 环境兼容（`requires-python` 已从 >=3.11 放宽至 >=3.10）
- `tests/integration/` 目录为空，API 端到端测试待 M8 补充
