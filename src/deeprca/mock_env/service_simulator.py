"""服务模拟器 — 生成监控指标、日志、链路、拓扑、变更、告警模拟数据。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建：6 类数据生成器</td><td>REQ: 20260713-总体架构, TECH: 04b §3.5</td></tr>
</table>
@author DeepRCA Team
"""

from __future__ import annotations

import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _iso_range(start: str, end: str, points: int = 60) -> list[str]:
    """生成时间戳序列。"""
    try:
        s = datetime.fromisoformat(start.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        s = datetime.now(timezone.utc) - timedelta(minutes=30)
        e = datetime.now(timezone.utc)
    if e <= s:
        e = s + timedelta(minutes=30)
    delta = (e - s) / max(points - 1, 1)
    return [(s + delta * i).strftime("%Y-%m-%dT%H:%M:%S+00:00") for i in range(points)]


class ServiceSimulator:
    """服务级数据模拟器。

    管理各服务的指标、日志、链路、拓扑、变更、告警数据。
    支持场景注入（通过 scenarios 模块触发）。
    """

    SERVICES = [
        "order-service",
        "payment-service",
        "user-service",
        "inventory-service",
        "gateway-service",
        "db-proxy",
        "redis-cluster",
        "kafka-broker",
    ]

    def __init__(self) -> None:
        self._topology: dict[str, dict] = {}
        self._changes: list[dict] = []
        self._alerts: list[dict] = []
        self._active_scenario: str | None = None
        self._scenario_data: dict[str, Any] = {}
        self._init_topology()

    def _init_topology(self) -> None:
        """初始化服务拓扑关系。"""
        self._topology = {
            "order-service": {
                "upstream": ["gateway-service"],
                "downstream": ["payment-service", "inventory-service", "user-service"],
            },
            "payment-service": {
                "upstream": ["order-service"],
                "downstream": ["db-proxy", "redis-cluster"],
            },
            "inventory-service": {
                "upstream": ["order-service"],
                "downstream": ["db-proxy"],
            },
            "user-service": {
                "upstream": ["order-service", "gateway-service"],
                "downstream": ["db-proxy", "redis-cluster"],
            },
            "gateway-service": {
                "upstream": [],
                "downstream": ["order-service", "user-service"],
            },
            "db-proxy": {
                "upstream": ["payment-service", "inventory-service", "user-service"],
                "downstream": [],
            },
            "redis-cluster": {
                "upstream": ["payment-service", "user-service"],
                "downstream": [],
            },
            "kafka-broker": {
                "upstream": [],
                "downstream": [],
            },
        }

    # ─────────────────────────────────────
    # 指标
    # ─────────────────────────────────────
    def get_metrics(
        self,
        service_name: str,
        metric_name: str,
        start_time: str,
        end_time: str,
        labels: dict | None = None,
    ) -> dict:
        """生成时序指标数据。"""
        timestamps = _iso_range(start_time, end_time, 60)
        scenario = self._active_scenario

        # 基线值范围
        baselines = {
            "qps": (800, 1200),
            "error_rate": (0.1, 0.5),
            "tp99": (50, 120),
            "cpu_usage": (15, 45),
            "memory_usage": (30, 60),
        }
        lo, hi = baselines.get(metric_name, (0, 100))

        data_points: list[dict] = []
        mid_idx = len(timestamps) // 2

        for i, ts in enumerate(timestamps):
            # 场景注入：在时间序列后半段产生异常
            if scenario and i >= mid_idx:
                if scenario == "pod_crash" and metric_name in ("error_rate", "cpu_usage"):
                    val = round(random.uniform(lo + 50, hi + 80), 2) if metric_name == "error_rate" else round(random.uniform(85, 98), 1)
                elif scenario == "db_slow_query" and metric_name == "tp99":
                    val = round(random.uniform(800, 2000), 2)
                elif scenario == "redis_timeout" and metric_name == "tp99":
                    val = round(random.uniform(500, 1500), 2)
                elif scenario == "traffic_spike" and metric_name == "qps":
                    val = round(random.uniform(3000, 5000), 2)
                else:
                    val = round(random.uniform(lo, hi), 2)
            else:
                val = round(random.uniform(lo, hi), 2)

            data_points.append({"timestamp": ts, "value": val})

        return {"service": service_name, "metric": metric_name, "data_points": data_points}

    # ─────────────────────────────────────
    # 日志
    # ─────────────────────────────────────
    def get_logs(
        self,
        service_name: str,
        start_time: str,
        end_time: str,
        level: str = "ERROR",
        keyword: str = "",
        limit: int = 100,
    ) -> dict:
        """生成错误日志数据。"""
        scenario = self._active_scenario
        log_templates = {
            "pod_crash": [
                "Connection refused to {svc}",
                "Pod {pod} CrashLoopBackOff, restarting...",
                "Health check failed for {svc}",
                "java.net.ConnectException: Connection refused",
            ],
            "db_slow_query": [
                "SQL execution timeout after 3000ms: SELECT * FROM orders WHERE...",
                "HikariPool-1 - Connection is not available, request timed out",
                "Deadlock found when trying to get lock; try restarting transaction",
            ],
            "redis_timeout": [
                "Redis command timeout: GET user:session:*",
                "JedisConnectionException: Could not get a resource from the pool",
                "Redis pipeline execution failed: timeout",
            ],
            "deployment_failure": [
                "NullPointerException at com.order.service.OrderService.process()",
                "Failed to bind properties under 'spring.datasource.url'",
                "Bean creation exception: OrderController",
            ],
        }

        templates = log_templates.get(scenario, [
            "Unexpected error in {svc}",
            "Request processing failed",
            "Service unavailable: {svc}",
        ])

        logs: list[dict] = []
        timestamps = _iso_range(start_time, end_time, min(limit, 50))
        for i, ts in enumerate(timestamps):
            tpl = random.choice(templates)
            msg = tpl.format(svc=service_name, pod=f"{service_name}-{random.randint(1000, 9999)}")
            if keyword and keyword.lower() not in msg.lower():
                continue
            logs.append({
                "timestamp": ts,
                "level": level,
                "service": service_name,
                "message": msg,
                "trace_id": f"trace-{random.randint(100000, 999999)}",
                "host": f"node-{random.randint(1, 5)}",
            })

        return {"service": service_name, "logs": logs[:limit]}

    # ─────────────────────────────────────
    # 链路追踪
    # ─────────────────────────────────────
    def get_traces(
        self,
        service_name: str,
        start_time: str,
        end_time: str,
        trace_id: str = "",
        limit: int = 50,
    ) -> dict:
        """生成调用链路数据。"""
        scenario = self._active_scenario
        downstream = self._topology.get(service_name, {}).get("downstream", [])

        traces: list[dict] = []
        timestamps = _iso_range(start_time, end_time, min(limit, 30))

        for ts in timestamps:
            tid = trace_id or f"trace-{random.randint(100000, 999999)}"
            spans: list[dict] = [{
                "span_id": f"span-{random.randint(1000, 9999)}",
                "service": service_name,
                "operation": f"{service_name}.handle_request",
                "duration_ms": round(random.uniform(5, 30), 2),
                "status": "OK",
                "timestamp": ts,
            }]

            # 添加下游调用 span
            for ds in downstream[:3]:
                duration = round(random.uniform(10, 50), 2)
                status = "OK"
                if scenario and random.random() > 0.6:
                    if scenario == "db_slow_query" and "db" in ds:
                        duration = round(random.uniform(500, 2000), 2)
                        status = "SLOW"
                    elif scenario == "redis_timeout" and "redis" in ds:
                        duration = round(random.uniform(300, 1000), 2)
                        status = "ERROR"
                    elif scenario == "pod_crash":
                        status = "ERROR"
                        duration = round(random.uniform(1, 5), 2)

                spans.append({
                    "span_id": f"span-{random.randint(1000, 9999)}",
                    "service": ds,
                    "operation": f"{ds}.process",
                    "duration_ms": duration,
                    "status": status,
                    "timestamp": ts,
                    "parent_span_id": spans[0]["span_id"],
                })

            traces.append({
                "trace_id": tid,
                "spans": spans,
                "total_duration_ms": sum(s["duration_ms"] for s in spans),
                "timestamp": ts,
            })

        return {"service": service_name, "traces": traces}

    # ─────────────────────────────────────
    # 拓扑
    # ─────────────────────────────────────
    def get_topology(self, service_name: str, depth: int = 2) -> dict:
        """返回服务拓扑关系。"""
        topo = self._topology.get(service_name, {})
        upstream = self._collect_upstream(service_name, depth)
        downstream = self._collect_downstream(service_name, depth)

        return {
            "service": service_name,
            "upstream": upstream,
            "downstream": downstream,
        }

    def _collect_upstream(self, service: str, depth: int, visited: set | None = None) -> list[dict]:
        if depth <= 0 or service not in self._topology:
            return []
        visited = visited or set()
        if service in visited:
            return []
        visited.add(service)
        result: list[dict] = []
        for up in self._topology.get(service, {}).get("upstream", []):
            result.append({"service": up, "relation": "upstream", "depth": 1})
            result.extend(
                {"service": s["service"], "relation": "upstream", "depth": s["depth"] + 1}
                for s in self._collect_upstream(up, depth - 1, visited)
            )
        return result

    def _collect_downstream(self, service: str, depth: int, visited: set | None = None) -> list[dict]:
        if depth <= 0 or service not in self._topology:
            return []
        visited = visited or set()
        if service in visited:
            return []
        visited.add(service)
        result: list[dict] = []
        for ds in self._topology.get(service, {}).get("downstream", []):
            result.append({"service": ds, "relation": "downstream", "depth": 1})
            result.extend(
                {"service": s["service"], "relation": "downstream", "depth": s["depth"] + 1}
                for s in self._collect_downstream(ds, depth - 1, visited)
            )
        return result

    # ─────────────────────────────────────
    # 变更记录
    # ─────────────────────────────────────
    def get_changes(self, service_name: str, time_window: int = 3600) -> dict:
        """生成变更记录数据。"""
        scenario = self._active_scenario
        now = datetime.now(timezone.utc)
        changes: list[dict] = []

        if scenario == "deployment_failure":
            changes.append({
                "change_id": f"chg-{random.randint(10000, 99999)}",
                "service": service_name,
                "type": "deployment",
                "operator": "ci-bot",
                "description": f"Deployed {service_name}:v1.2.4 (config change)",
                "timestamp": (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                "version": "v1.2.4",
                "previous_version": "v1.2.3",
            })
        else:
            # 基线：偶尔有配置变更
            if random.random() > 0.5:
                changes.append({
                    "change_id": f"chg-{random.randint(10000, 99999)}",
                    "service": service_name,
                    "type": "config",
                    "operator": "admin",
                    "description": "Updated timeout configuration",
                    "timestamp": (now - timedelta(minutes=random.randint(30, 120))).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    "version": "v1.2.3",
                    "previous_version": "v1.2.3",
                })

        return {"service": service_name, "changes": changes}

    # ─────────────────────────────────────
    # 关联告警
    # ─────────────────────────────────────
    def get_alerts(self, service_name: str, time_window: int = 1800) -> dict:
        """生成关联告警数据。"""
        scenario = self._active_scenario
        now = datetime.now(timezone.utc)
        alerts: list[dict] = []

        if scenario:
            downstream = self._topology.get(service_name, {}).get("downstream", [])
            for ds in downstream[:2]:
                alerts.append({
                    "alert_id": f"alt-{random.randint(10000, 99999)}",
                    "service": ds,
                    "alert_type": "custom",
                    "severity": random.choice(["P1", "P2"]),
                    "description": f"{ds} latency increased",
                    "timestamp": (now - timedelta(minutes=random.randint(1, 15))).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    "labels": {"cluster": "prod", "env": "production"},
                })

        return {"service": service_name, "alerts": alerts}

    # ─────────────────────────────────────
    # 场景管理
    # ─────────────────────────────────────
    def set_scenario(self, name: str | None, data: dict | None = None) -> None:
        """设置当前活跃场景。"""
        self._active_scenario = name
        self._scenario_data = data or {}

    def get_scenario(self) -> str | None:
        return self._active_scenario

    def reset(self) -> None:
        """重置到基线状态。"""
        self._active_scenario = None
        self._scenario_data.clear()
        self._changes.clear()
        self._alerts.clear()
