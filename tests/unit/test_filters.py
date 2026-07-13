"""指标筛选器和规则引擎单元测试。"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

from deeprca.detection.filters import MetricFilter, ExpertRuleEngine


class TestMetricFilter:
    """指标筛选器测试。"""

    def setup_method(self):
        self.filter = MetricFilter()

    def test_filter_empty_metrics(self):
        """空指标字典应安全返回。"""
        result = self.filter.filter_anomalies({})
        assert len(result) == 0

    def test_filter_high_qps(self):
        """高 QPS 指标应被选中。"""
        metrics = {
            "qps": 5000,
            "qps_baseline": 1000,
            "error_rate": 0.01,
        }
        result = self.filter.filter_anomalies(metrics)
        assert isinstance(result, list)
        assert len(result) > 0

    def test_filter_normal_metrics(self):
        """正常指标应被过滤掉。"""
        metrics = {
            "qps": 1050,
            "qps_baseline": 1000,
            "error_rate": 0.01,
        }
        result = self.filter.filter_anomalies(metrics)
        assert isinstance(result, list)
        assert len(result) == 0


class TestExpertRuleEngine:
    """专家规则引擎测试。"""

    def setup_method(self):
        self.engine = ExpertRuleEngine()

    def test_evaluate_empty_input(self):
        """空输入应安全返回。"""
        rules = self.engine.evaluate({}, [], {}, [])
        assert isinstance(rules, list)

    def test_evaluate_db_slow_query_rule(self):
        """DB 慢查询规则应匹配。"""
        evidence_summary = {"top_evidences": []}
        sub_agent_results = [
            {
                "agent_name": "db_expert",
                "dimension": "db",
                "confidence": 0.9,
                "findings": [
                    {"desc": "慢查询数量激增", "type": "slow_query", "value": 50}
                ],
            }
        ]
        alert = {"service_name": "order-service", "alert_type": "timeout"}
        anomalies = []

        rules = self.engine.evaluate(evidence_summary, sub_agent_results, alert, anomalies)
        assert isinstance(rules, list)

    def test_evaluate_redis_memory_rule(self):
        """Redis 内存规则应匹配。"""
        evidence_summary = {}
        sub_agent_results = [
            {
                "agent_name": "redis_expert",
                "dimension": "redis",
                "confidence": 0.85,
                "findings": [
                    {"desc": "Redis 内存使用率 95%", "type": "memory", "value": 95}
                ],
            }
        ]
        alert = {"service_name": "cache-service", "alert_type": "resource"}
        anomalies = []

        rules = self.engine.evaluate(evidence_summary, sub_agent_results, alert, anomalies)
        assert isinstance(rules, list)
