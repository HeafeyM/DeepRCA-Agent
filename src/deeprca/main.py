"""FastAPI 应用入口 — REST 端点 + WebSocket。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建：FastAPI 骨架 + 5 端点 + WebSocket</td><td>REQ: 20260713-总体架构, TECH: 04b §3.3.5</td></tr>
<tr><td>0.2.0</td><td>移除 inline placeholder，接线到 routes.py create_router()</td><td>REQ: 20260713-API 接线</td></tr>
</table>
@author DeepRCA Team
"""

from __future__ import annotations

import sys

from fastapi import FastAPI

from deeprca.api.routes import create_router
from deeprca.config import get_settings

__all__ = ["create_app"]


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    settings = get_settings()

    app = FastAPI(
        title="DeepRCA-Agent",
        description="LLM Agent 驱动的故障诊断智能体系统",
        version="0.2.0",
    )

    # --- Health Check ---
    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "version": "0.2.0", "env": settings.app_env}

    # --- API v1 路由 ---
    app.include_router(create_router())

    return app


# Windows EventLoop 兼容 (RISK-DA002 用户决策: 方案1)
if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())