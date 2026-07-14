"""调用链路查询工具 — query_trace。

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
async def query_trace(
    service_name: str,
    start_time: str,
    end_time: str,
    trace_id: str = "",
    limit: int = 50,
) -> dict:
    """查询调用链路数据。

    Args:
        service_name: 服务名称
        start_time: 起始时间 ISO 8601
        end_time: 结束时间 ISO 8601
        trace_id: 指定 trace ID（可选）
        limit: 返回条数上限

    Returns:
        包含调用链数据的字典
    """
    settings = get_settings()
    params: dict = {
        "service_name": service_name,
        "start_time": start_time,
        "end_time": end_time,
        "limit": limit,
    }
    if trace_id:
        params["trace_id"] = trace_id

    try:
        async with httpx.AsyncClient(timeout=settings.tool_call_timeout) as client:
            resp = await client.get(
                f"{settings.mock_monitor_api}/api/v1/traces",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            return {"service": service_name, "traces": data.get("traces", [])}
    except Exception as e:
        return {"service": service_name, "traces": [], "error": str(e)}
