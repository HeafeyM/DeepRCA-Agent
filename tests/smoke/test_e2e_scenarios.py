"""端到端场景冒烟测试 — PRD-06 §5.5 / §10。

通过 Mock 环境的 run_scenario_e2e 端点验证 8 个预设场景的完整链路:
注入故障 → 生成告警 → Agent 分析 → 根因匹配 → 置信度校验
"""

from __future__ import annotations

import pytest

# PRD-05 §6 定义了 8 个预设场景，冒烟测试覆盖全部场景
SCENARIOS = [
    "db_slave_delay_timeout",
    "oom_restart",
    "kafka_consumer_lag",
    "change_induced_failure",
    "redis_memory_pressure",
    "traffic_spike_saturation",
    "rpc_circuit_breaker",
    "multi_dimension_anomaly",
]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_e2e_scenario(reset_mock, run_scenario, scenario):
    """端到端场景冒烟测试。"""
    result = run_scenario(scenario)
    assert result["status"] == "passed", (
        f"Scenario {scenario} failed: actual={result.get('actual_root_cause')}, "
        f"expected={result.get('expected_root_cause')}, "
        f"matched={result.get('root_cause_matched')}, "
        f"confidence={result.get('actual_confidence')}/{result.get('expected_confidence_min')}"
    )
    assert result["root_cause_matched"] is True
    assert result["actual_confidence"] >= result["expected_confidence_min"]
