"""Mock 环境入口 — 启动 4 个模拟器 API 服务（单进程多端口）。

提供 4 个 FastAPI 子应用：
  - Monitor API (port 8002): 指标、告警、拓扑、链路
  - Log API (port 8003): 错误日志
  - Change API (port 8004): 变更记录
  - K8s API (port 8001): Pod/Deployment/Event

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建：4 个 Mock API 服务</td><td>REQ: 20260713-总体架构, TECH: 04b §3.5</td></tr>
</table>
@author DeepRCA Team
"""

from __future__ import annotations

import sys

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

# 确保 src 在 path 中
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "src"))

from deeprca.mock_env.k8s_simulator import K8sSimulator
from deeprca.mock_env.scenarios import SCENARIOS, apply_scenario, reset_scenario
from deeprca.mock_env.service_simulator import ServiceSimulator


# ─────────────────────────────────────
# 全局单例
# ─────────────────────────────────────
_k8s = K8sSimulator()
_service = ServiceSimulator()


# ─────────────────────────────────────
# Monitor API (port 8002)
# ─────────────────────────────────────
def create_monitor_app() -> FastAPI:
    app = FastAPI(title="Mock Monitor API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.get("/api/v1/metrics")
    async def get_metrics(
        service_name: str,
        metric_name: str,
        start_time: str,
        end_time: str,
        labels: dict | None = None,
    ):
        return _service.get_metrics(service_name, metric_name, start_time, end_time, labels)

    @app.get("/api/v1/alerts")
    async def get_alerts(
        service_name: str,
        time_window: int = 1800,
    ):
        return _service.get_alerts(service_name, time_window)

    @app.get("/api/v1/topology")
    async def get_topology(
        service_name: str,
        depth: int = 2,
    ):
        return _service.get_topology(service_name, depth)

    @app.get("/api/v1/traces")
    async def get_traces(
        service_name: str,
        start_time: str,
        end_time: str,
        trace_id: str = "",
        limit: int = 50,
    ):
        return _service.get_traces(service_name, start_time, end_time, trace_id, limit)

    return app


# ─────────────────────────────────────
# Log API (port 8003)
# ─────────────────────────────────────
def create_log_app() -> FastAPI:
    app = FastAPI(title="Mock Log API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.get("/api/v1/logs")
    async def get_logs(
        service_name: str,
        start_time: str,
        end_time: str,
        level: str = "ERROR",
        keyword: str = "",
        limit: int = 100,
    ):
        return _service.get_logs(service_name, start_time, end_time, level, keyword, limit)

    return app


# ─────────────────────────────────────
# Change API (port 8004)
# ─────────────────────────────────────
def create_change_app() -> FastAPI:
    app = FastAPI(title="Mock Change API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.get("/api/v1/changes")
    async def get_changes(
        service_name: str,
        time_window: int = 3600,
    ):
        return _service.get_changes(service_name, time_window)

    return app


# ─────────────────────────────────────
# K8s API (port 8001)
# ─────────────────────────────────────
def create_k8s_app() -> FastAPI:
    app = FastAPI(title="Mock K8s API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.get("/api/v1/pods")
    async def get_pods(service_name: str | None = None):
        return {"pods": _k8s.get_pods(service_name)}

    @app.get("/api/v1/deployments")
    async def get_deployments(service_name: str | None = None):
        return {"deployments": _k8s.get_deployments(service_name)}

    @app.get("/api/v1/events")
    async def get_events(service_name: str | None = None):
        return {"events": _k8s.get_events(service_name)}

    return app


# ─────────────────────────────────────
# Scenario Control API (挂在 K8s app 上)
# ─────────────────────────────────────
def create_scenario_app() -> FastAPI:
    app = FastAPI(title="Mock Scenario Control API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    @app.get("/api/v1/scenarios")
    async def list_scenarios():
        return {"scenarios": {k: {"name": v["name"], "description": v["description"]} for k, v in SCENARIOS.items()}}

    @app.post("/api/v1/scenarios/{scenario_name}/apply")
    async def apply(scenario_name: str, service_name: str = "order-service"):
        return apply_scenario(scenario_name, service_name)

    @app.post("/api/v1/scenarios/reset")
    async def reset():
        return reset_scenario()

    @app.get("/api/v1/scenarios/current")
    async def current():
        return {"active_scenario": _service.get_scenario()}

    return app


if __name__ == "__main__":
    import threading

    import uvicorn

    apps = [
        ("K8s API", create_k8s_app(), 8001),
        ("Monitor API", create_monitor_app(), 8002),
        ("Log API", create_log_app(), 8003),
        ("Change API", create_change_app(), 8004),
        ("Scenario Control", create_scenario_app(), 8005),
    ]

    threads: list[threading.Thread] = []

    def _run(name: str, app: FastAPI, port: int) -> None:
        print(f"[{name}] starting on port {port} ...")
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

    for name, app, port in apps:
        t = threading.Thread(target=_run, args=(name, app, port), daemon=True)
        t.start()
        threads.append(t)

    print("\n=== Mock Environment Started ===")
    print("  K8s API:          http://localhost:8001")
    print("  Monitor API:      http://localhost:8002")
    print("  Log API:          http://localhost:8003")
    print("  Change API:       http://localhost:8004")
    print("  Scenario Control: http://localhost:8005")
    print("================================\n")

    # 主线程保活
    for t in threads:
        t.join()
