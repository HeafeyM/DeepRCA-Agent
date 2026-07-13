"""错误恢复中间件 — 工具调用失败时的降级处理。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建</td><td>REQ: 20260713-总体架构, TECH: 04b §3.2</td></tr>
</table>
@author xianhuimeng
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["ErrorRecoveryMiddleware"]


class ErrorRecoveryMiddleware:
    """错误恢复中间件。

    在 Agent 循环的 after_tool 阶段，如果工具调用失败（返回 error），
    进行降级处理：记录错误日志并返回空结果而非中断流程。
    确保单个工具失败不会阻断整个分析流程。
    """

    # 工具名 → 空结果模板
    _EMPTY_RESULTS: dict[str, dict[str, Any]] = {
        "query_metrics": {"service": "", "metric": "", "data_points": [], "error": None},
        "query_error_logs": {"service": "", "logs": [], "error": None},
        "query_recent_changes": {"service": "", "changes": [], "error": None},
        "query_trace": {"service": "", "traces": [], "error": None},
        "query_related_alerts": {"service": "", "alerts": [], "error": None},
        "query_topology": {"service": "", "upstream": [], "downstream": [], "error": None},
    }

    def after_tool(
        self,
        state: dict[str, Any],
        tool_name: str,
        tool_result: dict[str, Any],
    ) -> dict[str, Any]:
        """检查工具结果是否有错误，有则降级处理。

        Args:
            state: LangGraph 状态字典
            tool_name: 工具名称
            tool_result: 工具返回结果

        Returns:
            状态更新字典（可能包含降级后的 messages 和修正后的结果提示）
        """
        if not self._is_error(tool_result):
            return {}

        error_msg = tool_result.get("error", "unknown error")
        trace_id = state.get("trace_id", "")
        service_name = state.get("alert", {}).get("service_name", "")

        logger.warning(
            "Tool %s failed for service %s (trace_id=%s): %s — applying fallback",
            tool_name,
            service_name,
            trace_id,
            error_msg,
        )

        # 返回降级信号到 messages
        fallback_result = self._get_fallback_result(tool_name, tool_result)

        return {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"工具 {tool_name} 调用失败（错误: {error_msg}），"
                        f"已降级为空结果，继续分析流程。"
                    ),
                }
            ],
            # 提示后续节点该工具结果已降级
            "_tool_fallback": {tool_name: True},
        }

    def _is_error(self, tool_result: dict[str, Any]) -> bool:
        """判断工具结果是否为错误结果。

        Args:
            tool_result: 工具返回结果

        Returns:
            True 如果结果包含错误
        """
        error = tool_result.get("error")
        if error is not None and error != "":
            return True
        return False

    def _get_fallback_result(self, tool_name: str, original_result: dict[str, Any]) -> dict[str, Any]:
        """获取降级后的空结果。

        Args:
            tool_name: 工具名称
            original_result: 原始（失败的）工具结果

        Returns:
            降级后的空结果字典
        """
        # 从模板获取空结果，保留 service 字段
        template = self._EMPTY_RESULTS.get(tool_name, {})
        fallback = dict(template)
        if "service" in original_result:
            fallback["service"] = original_result["service"]
        # 清除 error 字段
        fallback.pop("error", None)
        fallback["degraded"] = True
        return fallback
