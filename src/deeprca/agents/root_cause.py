"""L3 根因定位 Agent。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建</td><td>REQ: 20260713-总体架构, TECH: 04b §3.4.3-3.4.4</td></tr>
</table>
@author xianhuimeng
"""

from __future__ import annotations

import json
import logging
import time

import numpy as np

from deeprca.config.settings import get_settings
from deeprca.detection.comparator import MultiDimensionComparator
from deeprca.detection.filters import ExpertRuleEngine, MetricFilter
from deeprca.detection.quantile import QuantileAnomalyDetector
from deeprca.detection.volatility import VolatilityDetector
from deeprca.models.result import RootCauseCandidate, RootCauseResult

logger = logging.getLogger(__name__)


class RootCauseAgent:
    """L3 根因定位 Agent。6步流程。"""

    def __init__(self) -> None:
        self.detector = QuantileAnomalyDetector()
        self.volatility_detector = VolatilityDetector()
        self.comparator = MultiDimensionComparator()
        self.metric_filter = MetricFilter()
        self.rule_engine = ExpertRuleEngine()
        self._settings = get_settings()

    # ------------------------------------------------------------------ #
    #  主入口
    # ------------------------------------------------------------------ #

    async def analyze(
        self,
        alert: dict,
        evidence_summary: dict,
        sub_agent_results: list[dict],
    ) -> dict:
        """6步根因定位:
        1. 证据筛选: 从 sub_agent_results 提取高置信度 findings
        2. 基线对比: 对关键指标做周同比/日环比
        3. 异常检测: 四分位 IQR + 波动检测
        4. 多维度对比 + 置信度排序
        5. 专家规则引擎匹配 (R001-R008)
        6. LLM 根因推理（仅当规则未命中时）

        Returns: RootCauseResult 序列化 dict
        """
        trace_id = alert.get("trace_id", "")

        # --- Step 1: 证据筛选 ---
        high_confidence_findings = self._extract_high_confidence_findings(
            sub_agent_results
        )

        # --- Step 2: 基线对比 ---
        baseline_comparisons = self._perform_baseline_comparison(alert)

        # --- Step 3: 异常检测 ---
        anomalies = self._run_anomaly_detection(alert)

        # --- Step 4: 多维度对比 + 置信度排序 ---
        sorted_findings = self._sort_by_confidence(high_confidence_findings)

        # --- Step 5: 专家规则引擎匹配 ---
        matched_rules = self.rule_engine.evaluate(
            evidence_summary, sub_agent_results, alert, anomalies
        )

        rule_set = [r for r in matched_rules if r.get("root_cause")]
        boost_rules = [r for r in matched_rules if r.get("boost")]

        # 如果命中 set_root_cause 规则，直接返回
        if rule_set:
            return self._build_rule_result(
                rule_set, boost_rules, anomalies, trace_id
            )

        # --- Step 6: LLM 根因推理 ---
        return await self._run_llm_reasoning(
            sorted_findings, anomalies, baseline_comparisons,
            evidence_summary, boost_rules, trace_id,
        )

    # ------------------------------------------------------------------ #
    #  Step 1: 证据筛选
    # ------------------------------------------------------------------ #

    def _extract_high_confidence_findings(
        self, sub_agent_results: list[dict]
    ) -> list[dict]:
        """从 sub_agent_results 提取高置信度（>= 0.5）findings。"""
        findings: list[dict] = []
        for result in sub_agent_results:
            confidence = result.get("confidence", 0.0)
            if confidence < 0.5:
                continue
            for finding in result.get("findings", []):
                finding_entry = {
                    "agent_name": result.get("agent_name", ""),
                    "dimension": result.get("dimension", ""),
                    "confidence": confidence,
                    **finding,
                }
                findings.append(finding_entry)
        return findings

    # ------------------------------------------------------------------ #
    #  Step 2: 基线对比
    # ------------------------------------------------------------------ #

    def _perform_baseline_comparison(self, alert: dict) -> list[dict]:
        """对关键指标做周同比/日环比。"""
        comparisons: list[dict] = []
        metrics = alert.get("metrics", {})

        for metric_name, metric_data in metrics.items():
            if not isinstance(metric_data, dict):
                continue
            current = metric_data.get("current")
            baselines = {
                "last_week": metric_data.get("last_week"),
                "yesterday": metric_data.get("yesterday"),
            }
            if current is None or baselines["last_week"] is None:
                continue
            result = self.comparator.compare(float(current), baselines)
            result["metric"] = metric_name
            comparisons.append(result)

        return comparisons

    # ------------------------------------------------------------------ #
    #  Step 3: 异常检测
    # ------------------------------------------------------------------ #

    def _run_anomaly_detection(self, alert: dict) -> list[dict]:
        """四分位 IQR + 波动检测。"""
        anomalies: list[dict] = []
        metrics = alert.get("metrics", {})

        for metric_name, metric_data in metrics.items():
            if not isinstance(metric_data, dict):
                continue

            # 四分位 IQR 检测
            baseline = metric_data.get("baseline_series", [])
            current = metric_data.get("current")
            if baseline and current is not None:
                iqr_result = self.detector.detect(baseline, float(current))
                if iqr_result["is_anomaly"]:
                    anomalies.append({
                        "metric": metric_name,
                        "type": "iqr_anomaly",
                        "value": float(current),
                        "score": iqr_result["score"],
                        "deviation": iqr_result["deviation"],
                        "bounds": iqr_result["bounds"],
                        "median": iqr_result["median"],
                    })

            # 波动检测
            series = metric_data.get("time_series", [])
            if series and len(series) >= 5:
                vol_results = self.volatility_detector.detect(series)
                spikes = [r for r in vol_results if r["is_spike"]]
                if spikes:
                    anomalies.append({
                        "metric": metric_name,
                        "type": "volatility_spike",
                        "spike_count": len(spikes),
                        "spikes": spikes[:3],  # 取前3个突变点
                    })

        return anomalies

    # ------------------------------------------------------------------ #
    #  Step 4: 置信度排序
    # ------------------------------------------------------------------ #

    def _sort_by_confidence(self, findings: list[dict]) -> list[dict]:
        """按置信度降序排序。"""
        return sorted(
            findings,
            key=lambda f: f.get("confidence", 0.0),
            reverse=True,
        )

    # ------------------------------------------------------------------ #
    #  Step 5: 规则命中结果构建
    # ------------------------------------------------------------------ #

    def _build_rule_result(
        self,
        rule_set: list[dict],
        boost_rules: list[dict],
        anomalies: list[dict],
        trace_id: str,
    ) -> dict:
        """规则命中时构建 Top-3 候选。"""
        # 取最高置信度的规则作为 Top-1
        rule_set_sorted = sorted(
            rule_set, key=lambda r: r.get("confidence", 0.0), reverse=True
        )

        candidates: list[dict] = []
        base_confidence = rule_set_sorted[0]["confidence"]
        total_boost = sum(r.get("boost", 0.0) for r in boost_rules)
        boosted_confidence = min(base_confidence + total_boost, 1.0)

        # Top-1: 主规则
        candidates.append({
            "rank": 1,
            "root_cause": rule_set_sorted[0]["root_cause"],
            "confidence": round(boosted_confidence, 4),
            "evidence_chain": [r["rule_id"] for r in rule_set_sorted]
            + [r["rule_id"] for r in boost_rules],
            "matched_rule": rule_set_sorted[0]["rule_id"],
            "source": "rule",
        })

        # Top-2 / Top-3: 其他命中的规则
        for idx, rule in enumerate(rule_set_sorted[1:], start=2):
            if idx > 3:
                break
            candidates.append({
                "rank": idx,
                "root_cause": rule["root_cause"],
                "confidence": round(rule["confidence"], 4),
                "evidence_chain": [rule["rule_id"]],
                "matched_rule": rule["rule_id"],
                "source": "rule",
            })

        # 补充候选至 Top-3
        while len(candidates) < 3:
            candidates.append({
                "rank": len(candidates) + 1,
                "root_cause": "其他潜在因素需进一步分析",
                "confidence": 0.3,
                "evidence_chain": [],
                "matched_rule": None,
                "source": "rule",
            })

        best = candidates[0]
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")

        return RootCauseResult(
            candidates=[RootCauseCandidate(**c) for c in candidates],
            best_candidate=RootCauseCandidate(**best),
            anomalies_detected=anomalies,
            rule_matched=True,
            llm_used=False,
            trace_id=trace_id,
            timestamp=timestamp,
        ).model_dump()

    # ------------------------------------------------------------------ #
    #  Step 6: LLM 根因推理
    # ------------------------------------------------------------------ #

    async def _run_llm_reasoning(
        self,
        sorted_findings: list[dict],
        anomalies: list[dict],
        baseline_comparisons: list[dict],
        evidence_summary: dict,
        boost_rules: list[dict],
        trace_id: str,
    ) -> dict:
        """规则未命中时调用 LLM 推理，不可用时降级。"""
        prompt = self._build_llm_prompt(
            sorted_findings, anomalies, baseline_comparisons, evidence_summary
        )

        try:
            llm_response = await self._call_llm(prompt)
            candidates = self._parse_llm_response(llm_response, boost_rules)
            llm_used = True
        except Exception as exc:
            logger.warning("LLM 不可用，降级返回: %s", exc)
            candidates = self._build_fallback_candidates()
            llm_used = False

        best = candidates[0]
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%S%z")

        return RootCauseResult(
            candidates=[RootCauseCandidate(**c) for c in candidates],
            best_candidate=RootCauseCandidate(**best),
            anomalies_detected=anomalies,
            rule_matched=False,
            llm_used=llm_used,
            trace_id=trace_id,
            timestamp=timestamp,
        ).model_dump()

    def _build_llm_prompt(
        self,
        sorted_findings: list[dict],
        anomalies: list[dict],
        baseline_comparisons: list[dict],
        evidence_summary: dict,
    ) -> str:
        """构造 LLM 推理 prompt。"""
        findings_text = json.dumps(sorted_findings[:5], ensure_ascii=False, indent=2)
        anomalies_text = json.dumps(anomalies[:5], ensure_ascii=False, indent=2)
        comparisons_text = json.dumps(baseline_comparisons[:5], ensure_ascii=False, indent=2)
        summary_text = json.dumps(evidence_summary, ensure_ascii=False, indent=2)

        return (
            "你是一个故障诊断专家。根据以下证据和异常检测结果，推断最可能的根因。\n\n"
            f"## 证据摘要\n{summary_text}\n\n"
            f"## 高置信度发现\n{findings_text}\n\n"
            f"## 检测到的异常\n{anomalies_text}\n\n"
            f"## 基线对比\n{comparisons_text}\n\n"
            "## 要求\n"
            "请输出 Top-3 根因候选，按可能性从高到低排序。\n"
            "输出 JSON 格式:\n"
            '{"candidates": ['
            '{"rank": 1, "root_cause": "...", "confidence": 0.8, "evidence_chain": ["..."]},'
            ' {"rank": 2, ...}, {"rank": 3, ...}'
            "]}"
        )

    async def _call_llm(self, prompt: str) -> str:
        """调用 LLM，返回原始响应文本。"""
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(
            model=self._settings.llm_model,
            openai_api_base=self._settings.llm_api_base,
            openai_api_key=self._settings.llm_api_key,
            max_tokens=self._settings.llm_max_tokens,
            timeout=self._settings.llm_timeout,
            temperature=0.1,
        )
        response = await llm.ainvoke(prompt)
        return response.content if hasattr(response, "content") else str(response)

    def _parse_llm_response(
        self, response: str, boost_rules: list[dict]
    ) -> list[dict]:
        """解析 LLM 响应为候选列表。"""
        total_boost = sum(r.get("boost", 0.0) for r in boost_rules)

        try:
            # 尝试提取 JSON
            text = response.strip()
            if text.startswith("```"):
                # 去除 markdown 代码块
                lines = text.split("\n")
                text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

            data = json.loads(text)
            raw_candidates = data.get("candidates", [])

            candidates: list[dict] = []
            for raw in raw_candidates[:3]:
                confidence = float(raw.get("confidence", 0.5))
                confidence = min(confidence + total_boost, 1.0)
                candidates.append({
                    "rank": raw.get("rank", len(candidates) + 1),
                    "root_cause": raw.get("root_cause", ""),
                    "confidence": round(confidence, 4),
                    "evidence_chain": raw.get("evidence_chain", []),
                    "matched_rule": None,
                    "source": "llm",
                })

            if not candidates:
                candidates = self._build_fallback_candidates()

            # 确保 rank 连续
            for idx, c in enumerate(candidates, start=1):
                c["rank"] = idx

            return candidates

        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("LLM 响应解析失败: %s, 降级返回", exc)
            return self._build_fallback_candidates()

    def _build_fallback_candidates(self) -> list[dict]:
        """LLM 不可用时降级候选。"""
        return [
            {
                "rank": 1,
                "root_cause": "无法确定根因，建议人工分析",
                "confidence": 0.3,
                "evidence_chain": [],
                "matched_rule": None,
                "source": "llm",
            },
            {
                "rank": 2,
                "root_cause": "可能存在多因素叠加，需进一步排查",
                "confidence": 0.2,
                "evidence_chain": [],
                "matched_rule": None,
                "source": "llm",
            },
            {
                "rank": 3,
                "root_cause": "监控数据不足，建议补充采集后重新分析",
                "confidence": 0.1,
                "evidence_chain": [],
                "matched_rule": None,
                "source": "llm",
            },
        ]
