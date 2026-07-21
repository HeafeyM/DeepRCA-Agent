"""API 路由定义 — 将 HTTP 端点接线到 LangGraph 执行流程。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建：5 REST 端点 + WebSocket 接线到 build_coordinator_graph</td><td>REQ: 20260713-总体架构</td></tr>
</table>
@author DeepRCA Team
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from deeprca.config import get_settings
from deeprca.graph import build_coordinator_graph

__all__ = ["create_router", "analysis_store"]

# 全局分析状态存储（内存，生产环境应替换为 Redis）
analysis_store: dict[str, dict[str, Any]] = {}

# 全局编译图单例
_compiled_graph = None


def _get_graph():
    """获取编译后的图单例。"""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_coordinator_graph()
    return _compiled_graph


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
        """接收告警事件，启动 LangGraph 分析流程。

        请求体格式:
        {
            "alert_id": "alt-001",
            "service_name": "order-service",
            "alert_type": "timeout",
            "severity": "P1",
            "timestamp": "2026-07-13T10:00:00Z",
            "description": "接口超时",
            "labels": {"cluster": "prod-cluster", "env": "production", "app": "order"}
        }
        """
        # PRD-02 §7: 告警格式验证
        required_fields = ["alert_id", "service_name", "alert_type", "severity", "timestamp"]
        missing = [f for f in required_fields if not alert.get(f)]
        if missing:
            return JSONResponse(
                status_code=400,
                content={"message": f"必需字段缺失: {', '.join(missing)}", "missing_fields": missing},
            )

        # 生成 trace_id
        trace_id = f"trace-{uuid.uuid4().hex[:12]}"

        # 初始化状态
        initial_state = {
            "alert": alert,
            "task_plan": [],
            "sub_agent_results": [],
            "collected_evidence": None,
            "root_cause": None,
            "report": None,
            "messages": [],
            "trace_id": trace_id,
            "start_time": _now_iso(),
            "status": "running",
            "related_services": [],
            "degraded_mode": False,
        }

        # 存储初始状态
        analysis_store[trace_id] = {
            "status": "running",
            "start_time": _now_iso(),
            "result": None,
        }

        # 异步执行图（不阻塞 HTTP 响应）
        async def _run_analysis():
            try:
                graph = _get_graph()
                final_state = await graph.ainvoke(initial_state)
                analysis_store[trace_id]["status"] = final_state.get("status", "completed")
                analysis_store[trace_id]["result"] = final_state.get("report")
                analysis_store[trace_id]["root_cause"] = final_state.get("root_cause")
                analysis_store[trace_id]["completed_at"] = _now_iso()
            except Exception as exc:
                analysis_store[trace_id]["status"] = "failed"
                analysis_store[trace_id]["error"] = str(exc)

        # 启动后台任务
        asyncio.create_task(_run_analysis())

        # PRD-02 §6.1: 返回 websocket_url
        settings = get_settings()
        ws_url = f"ws://{settings.app_host}:{settings.app_port}/api/v1/analyze/{trace_id}/stream"

        return JSONResponse(
            status_code=202,
            content={
                "trace_id": trace_id,
                "status": "running",
                "websocket_url": ws_url,
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

        # PRD-02 §6.2: 返回进度信息
        status = record["status"]
        progress = {"total_dimensions": 6, "completed": 0, "failed": 0, "pending": 6}
        elapsed_seconds = 0
        start_time = record.get("start_time")
        if start_time:
            try:
                start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                elapsed_seconds = int((datetime.now(timezone.utc) - start_dt).total_seconds())
            except (ValueError, TypeError):
                pass

        return {
            "trace_id": trace_id,
            "status": status,
            "progress": progress,
            "elapsed_seconds": elapsed_seconds,
            "start_time": record.get("start_time"),
            "completed_at": record.get("completed_at"),
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
        if record["status"] not in ("completed", "failed"):
            return JSONResponse(
                status_code=202,
                content={"trace_id": trace_id, "status": record["status"], "message": "Analysis in progress"},
            )
        if record["status"] == "failed":
            return JSONResponse(
                status_code=500,
                content={"trace_id": trace_id, "status": "failed", "error": record.get("error", "Unknown error")},
            )

        # 解析报告 JSON
        report_raw = record.get("result")
        report = json.loads(report_raw) if isinstance(report_raw, str) else report_raw

        return {
            "trace_id": trace_id,
            "status": "completed",
            "report": report,
            "root_cause": record.get("root_cause"),
        }

    # ------------------------------------------------------------------ #
    # POST /feedback — 提交满意度反馈
    # ------------------------------------------------------------------ #
    @router.post("/feedback")
    async def submit_feedback(feedback: dict):
        """提交满意度反馈。

        请求体格式:
        {
            "trace_id": "trace-xxxx",
            "feedback_token": "abcd1234",
            "satisfaction": 4,
            "root_cause_correct": true,
            "comment": "分析准确"
        }
        """
        trace_id = feedback.get("trace_id", "")
        record = analysis_store.get(trace_id)
        if record is None:
            return JSONResponse(
                status_code=404,
                content={"message": "Trace not found"},
            )

        # 存储反馈
        record["feedback"] = feedback

        # 尝试推送到 Kafka（非阻塞，失败不影响响应）
        settings = get_settings()
        if not settings.mock_env_enabled:
            asyncio.create_task(_push_feedback_to_kafka(feedback, settings))

        return {"status": "accepted", "message": "Feedback received"}

    # ------------------------------------------------------------------ #
    # WebSocket /analyze/{trace_id}/stream — 实时推送分析进度
    # ------------------------------------------------------------------ #
    @router.websocket("/analyze/{trace_id}/stream")
    async def analysis_stream(ws: WebSocket, trace_id: str):
        """WebSocket 实时推送分析进度。"""
        await ws.accept()
        try:
            await ws.send_json({"trace_id": trace_id, "event": "connected"})

            record = analysis_store.get(trace_id)
            if record is None:
                await ws.send_json({"trace_id": trace_id, "event": "error", "message": "Trace not found"})
                await ws.close()
                return

            # 轮询状态，每秒推送一次
            while True:
                status = record.get("status", "running")
                await ws.send_json({
                    "trace_id": trace_id,
                    "event": "status",
                    "status": status,
                    "timestamp": _now_iso(),
                })

                if status in ("completed", "failed"):
                    report_raw = record.get("result")
                    report = json.loads(report_raw) if isinstance(report_raw, str) else report_raw
                    await ws.send_json({
                        "trace_id": trace_id,
                        "event": "completed" if status == "completed" else "error",
                        "report": report,
                        "root_cause": record.get("root_cause"),
                    })
                    break

                await asyncio.sleep(1.0)
        except WebSocketDisconnect:
            pass
        finally:
            await ws.close()

    return router


async def _push_feedback_to_kafka(feedback: dict, settings) -> None:
    """推送反馈到 Kafka（生产环境使用）。"""
    try:
        from aiokafka import AIOKafkaProducer
        producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        )
        await producer.start()
        try:
            await producer.send_and_wait(settings.kafka_feedback_topic, feedback)
        finally:
            await producer.stop()
    except Exception:
        pass
