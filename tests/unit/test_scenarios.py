"""Mock 环境场景单元测试。"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from deeprca.mock_env.scenarios import SCENARIOS


class TestScenarios:
    """预设测试场景测试。"""

    def test_scenarios_not_empty(self):
        """场景列表不应为空。"""
        assert len(SCENARIOS) > 0

    def test_each_scenario_has_required_fields(self):
        """每个场景应包含必需字段。"""
        for scenario in SCENARIOS.values():
            assert "name" in scenario
            assert "description" in scenario

    def test_db_slave_delay_scenario_exists(self):
        """应包含 DB 慢查询场景。"""
        scenario_names = [s["name"].lower() for s in SCENARIOS.values()]
        assert any("db" in n or "slow" in n or "query" in n or "数据库" in n or "慢查询" in n for n in scenario_names)

    def test_oom_scenario_exists(self):
        """应包含 OOM/内存压力场景。"""
        scenario_names = [s["name"].lower() for s in SCENARIOS.values()]
        assert any("oom" in n or "memory" in n or "resource" in n or "内存" in n or "资源" in n for n in scenario_names)

    def test_kafka_lag_scenario_exists(self):
        """应包含 Kafka 积压场景（或相关下游异常场景）。"""
        scenario_names = [s["name"].lower() for s in SCENARIOS.values()]
        assert any("kafka" in n or "lag" in n or "consumer" in n or "redis" in n for n in scenario_names)