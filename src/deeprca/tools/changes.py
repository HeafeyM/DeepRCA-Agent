"""变更记录查询工具 — query_recent_changes。

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
async def query_recent_changes(
    service_name: str,
    time_window: int = 3600,
) -> dict:
    """查询近期变更记录。

    Args:
        service_name: 服务名称
        time_window: 时间窗口（秒），默认 1 小时

    Returns:
        包含变更记录的字典
    """
    settings = get_settings()
    params: dict = {
        "service_name": service_name,
        "time_window": time_window,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.tool_call_timeout) as client:
            resp = await client.get(
                f"{settings.mock_change_api}/api/v1/changes",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            return {"service": service_name, "changes": data.get("changes", [])}
    except Exception as e:
        return {"service": service_name, "changes": [], "error": str(e)}
