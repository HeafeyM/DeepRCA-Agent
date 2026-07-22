"""错误日志查询工具 — query_error_logs。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建</td><td>REQ: 20260713-总体架构, TECH: 04b §3.3</td></tr>
</table>
@author xianhuimeng
"""

from __future__ import annotations

import httpx
from langchain_core.tools import tool

from deeprca.config import get_settings
from deeprca.tools.mock_data import mock_error_logs as _mock_error_logs


@tool
async def query_error_logs(
    service_name: str,
    start_time: str,
    end_time: str,
    level: str = "ERROR",
    keyword: str = "",
    limit: int = 100,
) -> dict:
    """查询错误日志。

    Args:
        service_name: 服务名称
        start_time: 起始时间 ISO 8601
        end_time: 结束时间 ISO 8601
        level: 日志级别
        keyword: 关键词过滤
        limit: 返回条数上限

    Returns:
        包含日志条目的字典
    """
    settings = get_settings()

    # Mock 环境直接返回模拟数据
    if settings.mock_env_enabled:
        return _mock_error_logs(service_name, start_time, end_time, level, keyword, limit)

    params: dict = {
        "service_name": service_name,
        "start_time": start_time,
        "end_time": end_time,
        "level": level,
        "limit": limit,
    }
    if keyword:
        params["keyword"] = keyword

    # NOTE: 非 Mock 模式下的 HTTP 路径为占位实现，需对接真实监控系统时重新设计。
    try:
        async with httpx.AsyncClient(timeout=settings.tool_call_timeout) as client:
            resp = await client.get(
                f"{settings.mock_log_api}/api/v1/logs",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            logs = data.get("logs", [])
            # 提取错误模式统计
            from collections import Counter
            import re as _re
            messages = [log.get("message", "") for log in logs]
            # 简单模式提取：取每条日志的前 50 个字符作为模式
            patterns = Counter()
            for msg in messages:
                # 提取关键错误模式（如 Lock wait, Connection refused 等）
                for match in _re.findall(r"([A-Z][a-z]+(?:\s+[a-z]+){1,3})", msg):
                    patterns[match] += 1
            error_patterns = [
                {"pattern": p, "count": c, "first_seen": logs[0].get("timestamp", "") if logs else ""}
                for p, c in patterns.most_common(5)
            ]
            return {
                "service": service_name,
                "total": len(logs),
                "logs": logs,
                "error_patterns": error_patterns,
            }
    except Exception as e:
        return {"service": service_name, "total": 0, "logs": [], "error_patterns": [], "error": str(e)}
