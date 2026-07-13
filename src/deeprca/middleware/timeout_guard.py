"""超时守卫中间件 — 分析超时检测与降级。

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

from deeprca.config import get_settings

logger = logging.getLogger(__name__)

__all__ = ["TimeoutGuardMiddleware"]


class TimeoutGuardMiddleware:
    """超时守卫中间件。

    在 Agent 循环的 before_model 阶段检查分析是否超时。
    超时则设置 state["status"] = "timeout"，
    返回信号让编排图跳过后续维度收集，直接进入 root_cause 降级。
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    def before_model(self, state: dict[str, Any]) -> dict[str, Any]:
        """检查分析是否超时。

        Args:
            state: LangGraph 状态字典

        Returns:
            如果超时，返回 {"status": "timeout", "messages": [...]}；
            否则返回空字典。
        """
        start_time_str: str = state.get("start_time", "")

        if not start_time_str:
            return {}

        try:
            # 支持多种 ISO 8601 格式
            start_time = _parse_iso_timestamp(start_time_str)
            now = datetime.now(timezone.utc)

            # 确保时区一致后计算差值
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)

            elapsed = (now - start_time).total_seconds()
            timeout_seconds = self._settings.analysis_timeout

            if elapsed >= timeout_seconds:
                logger.warning(
                    "Analysis timeout: elapsed=%.1fs, limit=%ds, trace_id=%s",
                    elapsed,
                    timeout_seconds,
                    state.get("trace_id", ""),
                )
                return {
                    "status": "timeout",
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                f"分析已超时（耗时 {elapsed:.1f}s，"
                                f"阈值 {timeout_seconds}s），跳过后续维度收集，"
                                f"直接进入根因定位降级流程。"
                            ),
                        }
                    ],
                }
        except Exception as e:
            logger.error("Failed to check timeout: %s", e)

        return {}


def _parse_iso_timestamp(ts: str) -> datetime:
    """解析 ISO 8601 时间戳，兼容带/不带时区的格式。

    Args:
        ts: 时间戳字符串

    Returns:
        datetime 对象
    """
    # 尝试直接解析
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        pass

    # 兼容 "Z" 结尾的 UTC 时间
    if ts.endswith("Z"):
        try:
            return datetime.fromisoformat(ts[:-1] + "+00:00")
        except ValueError:
            pass

    # 兼容不带时区的格式
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        pass

    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise ValueError(f"Unparseable timestamp: {ts}")
