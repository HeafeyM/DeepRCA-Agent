"""证据收集中间件 — 将工具结果转为 Evidence。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建</td><td>REQ: 20260713-总体架构, TECH: 04b §3.2</td></tr>
</table>
@author xianhuimeng
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from deeprca.models.evidence import Evidence, EvidenceLevel, EvidencePool

logger = logging.getLogger(__name__)

__all__ = ["EvidenceCollectorMiddleware"]

# 工具名 → 分析维度映射
_TOOL_DIMENSION_MAP: dict[str, str] = {
    "query_metrics": "cluster",
    "query_error_logs": "errorlog",
    "query_recent_changes": "change",
    "query_trace": "downstream",
    "query_related_alerts": "upstream",
    "query_topology": "downstream",
}


class EvidenceCollectorMiddleware:
    """证据收集中间件。

    在 Agent 循环的 after_tool 阶段，将工具调用结果转换为
    Evidence 对象并添加到 EvidencePool 中。
    从 tool_result 提取 source, dimension, finding, confidence。
    """

    def __init__(self) -> None:
        pass

    def after_tool(
        self,
        state: dict[str, Any],
        tool_name: str,
        tool_result: dict[str, Any],
    ) -> dict[str, Any]:
        """将工具结果转换为 Evidence 并添加到证据池。

        Args:
            state: LangGraph 状态字典
            tool_name: 工具名称
            tool_result: 工具返回结果

        Returns:
            包含更新后证据池摘要的状态更新字典
        """
        # 检查工具是否执行成功
        if tool_result.get("error"):
            return {}

        # 从工具结果中提取证据信息
        dimension = _TOOL_DIMENSION_MAP.get(tool_name, "problem")
        source = tool_name
        finding = self._extract_finding(tool_name, tool_result)
        confidence = self._estimate_confidence(tool_name, tool_result)
        level = self._determine_level(confidence)

        evidence = Evidence(
            source=source,
            dimension=dimension,
            finding=finding,
            level=level,
            confidence=confidence,
            data=tool_result,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # 获取或创建证据池
        pool = self._get_or_create_pool(state)
        pool.add(evidence)

        logger.debug(
            "Collected evidence from %s: dimension=%s, confidence=%.2f",
            tool_name,
            dimension,
            confidence,
        )

        return {"collected_evidence": pool.to_summary()}

    def _get_or_create_pool(self, state: dict[str, Any]) -> EvidencePool:
        """从 state 中获取或创建 EvidencePool。

        state["collected_evidence"] 存储的是 EvidencePool.to_summary() 的结果，
        我们需要维护一个实际的 EvidencePool。由于 LangGraph state 是
        immutable 的，这里从 summary 重建 pool。
        """
        # 在实际使用中，EvidencePool 应该在 state 初始化时创建
        # 这里从现有 summary 重建，以支持中间件的链式调用
        existing_summary: dict[str, Any] | None = state.get("collected_evidence")

        if existing_summary and existing_summary.get("top_evidences"):
            pool = EvidencePool()
            for ev_dict in existing_summary["top_evidences"]:
                try:
                    level_str = ev_dict.get("level", "medium")
                    level = EvidenceLevel(level_str) if isinstance(level_str, str) else EvidenceLevel.MEDIUM
                    pool.add(
                        Evidence(
                            source=ev_dict.get("source", ""),
                            dimension=ev_dict.get("dimension", ""),
                            finding=ev_dict.get("finding", ""),
                            level=level,
                            confidence=ev_dict.get("confidence", 0.0),
                            data=ev_dict.get("data"),
                            timestamp=ev_dict.get("timestamp", ""),
                        )
                    )
                except Exception:
                    pass
            return pool

        return EvidencePool()

    def _extract_finding(self, tool_name: str, result: dict[str, Any]) -> str:
        """从工具结果中提取发现摘要。

        Args:
            tool_name: 工具名称
            result: 工具返回结果

        Returns:
            发现描述字符串
        """
        service = result.get("service", "")

        if tool_name == "query_metrics":
            data_points = result.get("data_points", [])
            if not data_points:
                return f"[{service}] 指标查询无数据返回"
            return f"[{service}] 获取到 {len(data_points)} 个指标数据点"

        if tool_name == "query_error_logs":
            logs = result.get("logs", [])
            if not logs:
                return f"[{service}] 未发现错误日志"
            return f"[{service}] 发现 {len(logs)} 条错误日志"

        if tool_name == "query_recent_changes":
            changes = result.get("changes", [])
            if not changes:
                return f"[{service}] 近期无变更记录"
            return f"[{service}] 发现 {len(changes)} 条近期变更"

        if tool_name == "query_trace":
            traces = result.get("traces", [])
            if not traces:
                return f"[{service}] 未获取到调用链数据"
            return f"[{service}] 获取到 {len(traces)} 条调用链"

        if tool_name == "query_related_alerts":
            alerts = result.get("alerts", [])
            if not alerts:
                return f"[{service}] 无关联告警"
            return f"[{service}] 发现 {len(alerts)} 条关联告警"

        if tool_name == "query_topology":
            upstream = result.get("upstream", [])
            downstream = result.get("downstream", [])
            return f"[{service}] 拓扑: 上游 {len(upstream)} 个, 下游 {len(downstream)} 个"

        return f"[{service}] 工具 {tool_name} 返回结果"

    def _estimate_confidence(self, tool_name: str, result: dict[str, Any]) -> float:
        """根据工具类型和结果质量估计置信度。

        Args:
            tool_name: 工具名称
            result: 工具返回结果

        Returns:
            置信度 0.0~1.0
        """
        # 有错误的结果置信度为 0
        if result.get("error"):
            return 0.0

        # 变更类工具置信度最高（变更往往是根因）
        if tool_name == "query_recent_changes":
            changes = result.get("changes", [])
            return 0.9 if changes else 0.3

        # 错误日志置信度较高
        if tool_name == "query_error_logs":
            logs = result.get("logs", [])
            return 0.8 if logs else 0.2

        # 指标数据置信度中等（需要进一步分析）
        if tool_name == "query_metrics":
            data_points = result.get("data_points", [])
            return 0.7 if data_points else 0.1

        # 调用链数据置信度中等
        if tool_name == "query_trace":
            traces = result.get("traces", [])
            return 0.6 if traces else 0.1

        # 关联告警置信度中等
        if tool_name == "query_related_alerts":
            alerts = result.get("alerts", [])
            return 0.5 if alerts else 0.2

        # 拓扑信息置信度较低（只是上下文）
        if tool_name == "query_topology":
            return 0.3

        return 0.3

    def _determine_level(self, confidence: float) -> EvidenceLevel:
        """根据置信度确定证据等级。

        Args:
            confidence: 置信度 0.0~1.0

        Returns:
            EvidenceLevel
        """
        if confidence >= 0.7:
            return EvidenceLevel.HIGH
        if confidence >= 0.4:
            return EvidenceLevel.MEDIUM
        return EvidenceLevel.LOW
