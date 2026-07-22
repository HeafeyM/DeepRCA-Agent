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
from deeprca.tools.mock_data import mock_recent_changes as _mock_recent_changes


@tool
async def query_recent_changes(
    service_name: str,
    time_range: str = "24h",
    change_type: str = "",
) -> dict:
    """查询近期变更记录。

    Args:
        service_name: 服务名称
        time_range: 时间范围 (1h/6h/24h/7d)
        change_type: 变更类型过滤 (deploy/config/scale/rollback)

    Returns:
        包含变更记录的字典
    """
    settings = get_settings()

    # Mock 环境直接返回模拟数据
    if settings.mock_env_enabled:
        return _mock_recent_changes(service_name, time_range, change_type)

    # 将时间范围转为秒
    range_map = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800}
    time_window = range_map.get(time_range, 86400)

    params: dict = {
        "service_name": service_name,
        "time_window": time_window,
    }
    if change_type:
        params["change_type"] = change_type

    # NOTE: 非 Mock 模式下的 HTTP 路径为占位实现，需对接真实变更系统时重新设计。
    try:
        async with httpx.AsyncClient(timeout=settings.tool_call_timeout) as client:
            resp = await client.get(
                f"{settings.mock_change_api}/api/v1/changes",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()
            changes = data.get("changes", [])
            return {
                "service": service_name,
                "total": len(changes),
                "changes": changes,
            }
    except Exception as e:
        return {"service": service_name, "total": 0, "changes": [], "error": str(e)}
