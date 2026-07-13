"""API 路由定义骨架 — REST 端点 + WebSocket。

当前版本提供端点骨架，图调用在 PRD-02 完成后接线。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建：5 REST 端点骨架 + WebSocket 骨架</td><td>REQ: 20260713-总体架构</td></tr>
</table>
@author DeepRCA Team
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

__all__ = ["create_router", "analysis_store"]

# 全局分析状态存储（内存，生产环境应替换为 Redis）
analysis_store: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def create_router() -> APIRouter:
    """创建 API v1 路由器。"""
    router = APIRouter(prefix="/api/v1", tags=["DeepRCA Agent"])

    # ------------------------------------------------------------------ #
    # POST /analyze — 提交故障分析请求
    # ------------------------------------------------------------------ #
    @router.post("/analyze")
    async def submit_analysis(alert: dict):
        """接收告警事件，启动 LangGraph 分析流程。"""
        # TODO: PRD-02 接线到 build_coordinator_graph
        trace_id = f"trace-{uuid.uuid4().hex[:12]}"
        analysis_store[trace_id] = {
            "status": "pending",
            "start_time": _now_iso(),
            "result": None,
        }
        return JSONResponse(
            status_code=202,
            content={
                "trace_id": trace_id,
                "status": "accepted",
                "message": "Analysis started (skeleton — graph not wired yet)",
            },
        )

    # ------------------------------------------------------------------ #
    # GET /analyze/{trace_id}/status — 查询分析状态
    # ------------------------------------------------------------------ #
    @router.get("/analyze/{trace_id}/status")
    async def get_analysis_status(trace_id: str):
        """查询分析状态。"""
        record = analysis_store.get(trace_id)
        if record is None:
            return JSONResponse(
                status_code=404,
                content={"trace_id": trace_id, "message": "Trace not found"},
            )
        return {
            "trace_id": trace_id,
            "status": record["status"],
            "start_time": record.get("start_time"),
        }

    # ------------------------------------------------------------------ #
    # GET /analyze/{trace_id}/result — 获取分析结果
    # ------------------------------------------------------------------ #
    @router.get("/analyze/{trace_id}/result")
    async def get_analysis_result(trace_id: str):
        """获取分析结果。"""
        record = analysis_store.get(trace_id)
        if record is None:
            return JSONResponse(
                status_code=404,
                content={"trace_id": trace_id, "message": "Trace not found"},
            )
        return {
            "trace_id": trace_id,
            "status": record["status"],
            "report": record.get("result"),
        }

    # ------------------------------------------------------------------ #
    # POST /feedback — 提交满意度反馈
    # ------------------------------------------------------------------ #
    @router.post("/feedback")
    async def submit_feedback(feedback: dict):
        """提交满意度反馈。"""
        # TODO: PRD-07 接线到 Kafka
        return {"status": "accepted", "message": "Feedback received (skeleton)"}

    # ------------------------------------------------------------------ #
    # WebSocket /analyze/{trace_id}/stream — 实时推送分析进度
    # ------------------------------------------------------------------ #
    @router.websocket("/analyze/{trace_id}/stream")
    async def analysis_stream(ws: WebSocket, trace_id: str):
        """WebSocket 实时推送分析进度。"""
        await ws.accept()
        try:
            await ws.send_json({"trace_id": trace_id, "event": "connected"})
            # TODO: PRD-02 接线到图执行进度推送
            record = analysis_store.get(trace_id)
            if record is None:
                await ws.send_json({"trace_id": trace_id, "event": "error", "message": "Trace not found"})
            else:
                await ws.send_json({"trace_id": trace_id, "event": "status", "status": record["status"]})
        except WebSocketDisconnect:
            pass
        finally:
            await ws.close()

    return router
