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
    params: dict = {
        "service_name": service_name,
        "start_time": start_time,
        "end_time": end_time,
        "level": level,
        "limit": limit,
    }
    if keyword:
        params["keyword"] = keyword

    try:
        async with httpx.AsyncClient(timeout=settings.tool_call_timeout) as client:
            resp = await client.get(
                f"{settings.mock_log_api}/api/v1/logs",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            return {"service": service_name, "logs": data.get("logs", [])}
    except Exception as e:
        return {"service": service_name, "logs": [], "error": str(e)}
