"""冒烟测试 — 端到端验证 LangGraph 图在预设场景下的完整执行流程。

覆盖 6 个预设 Mock 场景，验证:
1. 告警解析 (intake_node)
2. 任务规划 (planner_node)
3. 并发收集 (dispatcher_node)
4. 证据聚合 (collector_node)
5. 根因定位 (root_cause_node)
6. 报告生成 (reporter_node)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

import pytest
from deeprca.graph import build_coordinator_graph
from deeprca.mock_env.scenarios import SCENARIOS


class TestSmokeEndToEnd:
    """端到端冒烟测试。"""

    @pytest.fixture(scope="class")
    def compiled_graph(self):
        """编译图，整个测试类共享。"""
        return build_coordinator_graph()

    @pytest.fixture
    def base_alert(self):
        """基础告警事件。alert_type 必须是合法枚举值: timeout/error_rate/resource/custom。"""
        return {
            "alert_id": "smoke-test-001",
            "service_name": "order-service",
            "alert_type": "timeout",
            "severity": "P1",
            "timestamp": "2026-07-13T10:00:00Z",
            "description": "接口响应超时",
            "labels": {
                "cluster": "prod-cluster",
                "env": "production",
                "app": "order-service",
            },
        }

    async def _run_graph(self, compiled_graph, alert):
        """执行图并返回最终状态（async，因 dispatcher/root_cause 节点为 async）。"""
        initial_state = {
            "alert": alert,
            "task_plan": [],
            "sub_agent_results": [],
            "collected_evidence": None,
            "root_cause": None,
            "report": None,
            "messages": [],
            "trace_id": "smoke-trace-001",
            "start_time": "2026-07-13T10:00:00+00:00",
            "status": "running",
        }
        return await compiled_graph.ainvoke(initial_state)

    def test_graph_compiles(self, compiled_graph):
        """图应成功编译。"""
        assert compiled_graph is not None

    async def test_pod_crash_scenario(self, compiled_graph, base_alert):
        """Pod 崩溃场景端到端测试。"""
        alert = {**base_alert, "alert_type": "error_rate", "description": "Pod CrashLoopBackOff 导致错误率飙升"}
        final_state = await self._run_graph(compiled_graph, alert)

        assert final_state["status"] in ("completed", "timeout")
        assert final_state["trace_id"] is not None
        assert len(final_state["task_plan"]) == 6
        assert final_state["report"] is not None

    async def test_resource_pressure_scenario(self, compiled_graph, base_alert):
        """资源压力场景端到端测试。"""
        alert = {**base_alert, "alert_type": "resource", "description": "CPU/Memory 飙高"}
        final_state = await self._run_graph(compiled_graph, alert)

        assert final_state["status"] in ("completed", "timeout")
        assert len(final_state["task_plan"]) == 6

    async def test_db_slow_query_scenario(self, compiled_graph, base_alert):
        """DB 慢查询场景端到端测试。"""
        alert = {**base_alert, "alert_type": "timeout", "description": "数据库慢查询导致超时"}
        final_state = await self._run_graph(compiled_graph, alert)

        assert final_state["status"] in ("completed", "timeout")
        assert len(final_state["task_plan"]) == 6
        assert final_state["report"] is not None

    async def test_redis_timeout_scenario(self, compiled_graph, base_alert):
        """Redis 超时场景端到端测试。"""
        alert = {**base_alert, "alert_type": "timeout", "description": "Redis 连接超时"}
        final_state = await self._run_graph(compiled_graph, alert)

        assert final_state["status"] in ("completed", "timeout")
        assert len(final_state["task_plan"]) == 6

    async def test_traffic_spike_scenario(self, compiled_graph, base_alert):
        """流量突增场景端到端测试。"""
        alert = {**base_alert, "alert_type": "timeout", "description": "QPS 突增导致响应超时"}
        final_state = await self._run_graph(compiled_graph, alert)

        assert final_state["status"] in ("completed", "timeout")
        assert len(final_state["task_plan"]) == 6

    async def test_deployment_failure_scenario(self, compiled_graph, base_alert):
        """部署失败场景端到端测试。"""
        alert = {**base_alert, "alert_type": "error_rate", "description": "新版本部署引入 Bug"}
        final_state = await self._run_graph(compiled_graph, alert)

        assert final_state["status"] in ("completed", "timeout")
        assert len(final_state["task_plan"]) == 6
        assert final_state["report"] is not None

    async def test_report_is_valid_json(self, compiled_graph, base_alert):
        """报告应为合法 JSON 字符串。"""
        import json

        alert = {**base_alert, "alert_type": "timeout", "description": "接口超时"}
        final_state = await self._run_graph(compiled_graph, alert)

        report = final_state.get("report")
        if report:
            parsed = json.loads(report) if isinstance(report, str) else report
            assert "trace_id" in parsed or "root_cause" in parsed

    def test_all_scenarios_covered(self):
        """6 个预设场景均应存在。"""
        expected_scenarios = {
            "pod_crash",
            "resource_pressure",
            "db_slow_query",
            "redis_timeout",
            "traffic_spike",
            "deployment_failure",
        }
        assert expected_scenarios.issubset(set(SCENARIOS.keys()))