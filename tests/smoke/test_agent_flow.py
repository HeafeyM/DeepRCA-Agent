"""Agent 分析流程冒烟测试 — PRD-06 §10。

通过 Agent HTTP API 提交告警，验证完整分析流程:
POST /analyze → GET /status → GET /result
"""

from __future__ import annotations

import time

import pytest

ALERT = {
    "alert_id": "smoke-agent-001",
    "service_name": "order-service",
    "alert_type": "timeout",
    "severity": "P1",
    "timestamp": "2026-07-21T10:00:00Z",
    "description": "order-service 调用 payment-service 接口超时",
    "labels": {"cluster": "prod-cluster-01", "env": "production", "app": "order-service"},
}


def test_submit_analysis(agent_client):
    """提交分析请求应返回 202 + trace_id。"""
    resp = agent_client.post("/api/v1/analyze", json=ALERT)
    assert resp.status_code == 202
    data = resp.json()
    assert "trace_id" in data
    assert data["status"] == "running"


def test_get_status(agent_client):
    """提交后应能查询到运行状态。"""
    resp = agent_client.post("/api/v1/analyze", json=ALERT)
    trace_id = resp.json()["trace_id"]

    status_resp = agent_client.get(f"/api/v1/analyze/{trace_id}/status")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["trace_id"] == trace_id
    assert data["status"] in ("running", "completed", "failed", "timeout")


def test_get_result_completed(agent_client):
    """分析完成后应能获取结果。"""
    resp = agent_client.post("/api/v1/analyze", json=ALERT)
    trace_id = resp.json()["trace_id"]

    # 轮询等待完成（最多 120 秒）
    for _ in range(60):
        status_resp = agent_client.get(f"/api/v1/analyze/{trace_id}/status")
        status_data = status_resp.json()
        if status_data["status"] in ("completed", "failed"):
            break
        time.sleep(2)

    result_resp = agent_client.get(f"/api/v1/analyze/{trace_id}/result")
    assert result_resp.status_code == 200
    result_data = result_resp.json()
    assert "report" in result_data or "error" in result_data


def test_missing_fields_returns_400(agent_client):
    """缺少必需字段应返回 400。"""
    bad_alert = {"alert_id": "bad-001"}  # 缺少 service_name, alert_type 等
    resp = agent_client.post("/api/v1/analyze", json=bad_alert)
    assert resp.status_code == 400


def test_feedback_endpoint(agent_client):
    """反馈端点应正常接收。"""
    # 先提交分析获取 trace_id
    resp = agent_client.post("/api/v1/analyze", json=ALERT)
    trace_id = resp.json()["trace_id"]

    feedback_resp = agent_client.post("/api/v1/feedback", json={
        "trace_id": trace_id,
        "feedback_token": "test-token",
        "satisfaction": 4,
        "root_cause_correct": True,
        "comment": "分析准确",
    })
    assert feedback_resp.status_code == 200
