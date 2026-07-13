"""指标筛选器与专家规则引擎。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建</td><td>REQ: 20260713-总体架构, TECH: 04b §3.4.3-3.4.4</td></tr>
</table>
@author xianhuimeng
"""

from __future__ import annotations

import re


class MetricFilter:
    """指标筛选器。筛选高QPS、高失败率、TP99突变的指标。"""

    DEFAULT_THRESHOLDS = {
        "error_rate": 0.05,
        "tp99_deviation": 3.0,
        "qps_deviation": 3.0,
    }

    def filter_anomalies(self, metrics: dict, thresholds: dict | None = None) -> list[dict]:
        """筛选异常指标。

        Args:
            metrics: 指标数据字典，如:
                {"error_rate": 0.1, "tp99": 200, "tp99_baseline": 50,
                 "qps": 1000, "qps_baseline": 300}
            thresholds: 阈值覆盖，默认 {"error_rate": 0.05,
                "tp99_deviation": 3.0, "qps_deviation": 3.0}

        Returns:
            [{"metric": str, "value": float, "threshold": float, "type": str}]
        """
        if thresholds is None:
            thresholds = self.DEFAULT_THRESHOLDS

        results: list[dict] = []

        # 错误率筛选
        error_rate = metrics.get("error_rate")
        if error_rate is not None:
            threshold = thresholds.get("error_rate", self.DEFAULT_THRESHOLDS["error_rate"])
            if error_rate > threshold:
                results.append({
                    "metric": "error_rate",
                    "value": float(error_rate),
                    "threshold": threshold,
                    "type": "error_rate",
                })

        # TP99 偏离筛选
        tp99 = metrics.get("tp99")
        tp99_baseline = metrics.get("tp99_baseline")
        if tp99 is not None and tp99_baseline is not None and tp99_baseline != 0:
            tp99_dev = tp99 / tp99_baseline
            threshold = thresholds.get("tp99_deviation", self.DEFAULT_THRESHOLDS["tp99_deviation"])
            if tp99_dev > threshold:
                results.append({
                    "metric": "tp99",
                    "value": round(float(tp99_dev), 4),
                    "threshold": threshold,
                    "type": "tp99_deviation",
                })

        # QPS 偏离筛选
        qps = metrics.get("qps")
        qps_baseline = metrics.get("qps_baseline")
        if qps is not None and qps_baseline is not None and qps_baseline != 0:
            qps_dev = qps / qps_baseline
            threshold = thresholds.get("qps_deviation", self.DEFAULT_THRESHOLDS["qps_deviation"])
            if qps_dev > threshold:
                results.append({
                    "metric": "qps",
                    "value": round(float(qps_dev), 4),
                    "threshold": threshold,
                    "type": "qps_deviation",
                })

        return results


class ExpertRuleEngine:
    """专家规则引擎。8条确定性规则。"""

    RULES = [
        {
            "id": "R001",
            "pattern": "deployment + error_rate_spike",
            "action": "set_root_cause",
            "root_cause": "近期变更导致错误率上升",
            "confidence": 0.85,
        },
        {
            "id": "R002",
            "pattern": "db_slow_query + latency_spike",
            "action": "set_root_cause",
            "root_cause": "数据库慢查询导致延迟突增",
            "confidence": 0.85,
        },
        {
            "id": "R003",
            "pattern": "redis_memory_high + hit_rate_drop",
            "action": "set_root_cause",
            "root_cause": "Redis 内存不足导致命中率下降",
            "confidence": 0.80,
        },
        {
            "id": "R004",
            "pattern": "kafka_consumer_lag + backlog",
            "action": "set_root_cause",
            "root_cause": "Kafka 消费积压导致处理延迟",
            "confidence": 0.80,
        },
        {
            "id": "R005",
            "pattern": "rpc_failure_rate_high",
            "action": "set_root_cause",
            "root_cause": "RPC 调用失败率过高",
            "confidence": 0.75,
        },
        {
            "id": "R006",
            "pattern": "resource_exhaustion",
            "action": "boost_confidence",
            "boost": 0.15,
            "description": "资源耗尽加剧异常",
        },
        {
            "id": "R007",
            "pattern": "upstream_traffic_anomaly",
            "action": "boost_confidence",
            "boost": 0.10,
            "description": "上游流量异常",
        },
        {
            "id": "R008",
            "pattern": "multiple_anomalies",
            "action": "boost_confidence",
            "boost": 0.20,
            "description": "多维度异常叠加",
        },
    ]

    def _build_context_text(
        self,
        evidence_pool_summary: dict,
        sub_agent_results: list[dict],
        alert: dict,
        anomalies: list[dict],
    ) -> str:
        """将所有上下文信息拼接为文本，用于关键词匹配。"""
        parts: list[str] = []

        # 证据摘要
        top_evidences = evidence_pool_summary.get("top_evidences", [])
        for ev in top_evidences:
            if isinstance(ev, dict):
                parts.append(ev.get("finding", ""))
                parts.append(ev.get("dimension", ""))
            else:
                parts.append(str(ev))

        # 子 Agent findings
        for result in sub_agent_results:
            for finding in result.get("findings", []):
                if isinstance(finding, dict):
                    parts.append(finding.get("description", ""))
                    parts.append(finding.get("type", ""))
                    parts.append(finding.get("metric", ""))
                else:
                    parts.append(str(finding))
            parts.append(result.get("dimension", ""))

        # 告警信息
        parts.append(alert.get("alert_name", ""))
        parts.append(alert.get("description", ""))
        parts.append(alert.get("service", ""))

        # 异常列表
        for anomaly in anomalies:
            parts.append(anomaly.get("metric", ""))
            parts.append(anomaly.get("type", ""))

        return " ".join(p for p in parts if p).lower()

    def _match_pattern(self, pattern: str, context_text: str) -> bool:
        """匹配 pattern 中的关键词组合。

        pattern 格式: "keyword1 + keyword2" 表示需要同时包含两个关键词。
        单个关键词时直接匹配。
        """
        keywords = [kw.strip().lower() for kw in pattern.split("+")]
        return all(kw in context_text for kw in keywords if kw)

    def evaluate(
        self,
        evidence_pool_summary: dict,
        sub_agent_results: list[dict],
        alert: dict,
        anomalies: list[dict],
    ) -> list[dict]:
        """评估所有规则。

        匹配逻辑: 检查 findings 中的关键词和异常类型。
        set_root_cause → 返回 {"matched": True, "rule_id": ..., "root_cause": ..., "confidence": ...}
        boost_confidence → 返回 {"matched": True, "rule_id": ..., "boost": ..., "description": ...}
        未匹配 → 返回空列表
        """
        context_text = self._build_context_text(
            evidence_pool_summary, sub_agent_results, alert, anomalies
        )

        matched_rules: list[dict] = []

        for rule in self.RULES:
            pattern = rule.get("pattern", "")
            if not self._match_pattern(pattern, context_text):
                continue

            if rule["action"] == "set_root_cause":
                matched_rules.append({
                    "matched": True,
                    "rule_id": rule["id"],
                    "root_cause": rule["root_cause"],
                    "confidence": rule["confidence"],
                })
            elif rule["action"] == "boost_confidence":
                matched_rules.append({
                    "matched": True,
                    "rule_id": rule["id"],
                    "boost": rule["boost"],
                    "description": rule.get("description", ""),
                })

        return matched_rules
