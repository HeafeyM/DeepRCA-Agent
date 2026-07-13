"""K8s 模拟器 — 生成 Pod/Deployment/Event 模拟数据。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建</td><td>REQ: 20260713-总体架构, TECH: 04b §3.5</td></tr>
</table>
@author xianhuimeng
"""

from __future__ import annotations

import random
import time
from typing import Any


class K8sSimulator:
    """K8s 资源状态模拟器。内存中生成并管理 Pod、Deployment、Event 数据。"""

    def __init__(self) -> None:
        self._deployments: dict[str, dict] = {}
        self._pods: list[dict] = []
        self._events: list[dict] = []
        self._scenario: str | None = None
        self._init_baseline()

    def _init_baseline(self) -> None:
        """初始化基线数据。"""
        services = ["order-service", "payment-service", "user-service", "inventory-service"]
        for svc in services:
            self._deployments[svc] = {
                "name": svc,
                "namespace": "production",
                "replicas": 3,
                "ready_replicas": 3,
                "image": f"registry.internal/{svc}:v1.2.3",
                "created_at": "2026-07-10T08:00:00Z",
            }
            for i in range(3):
                self._pods.append({
                    "name": f"{svc}-{random.randint(1000,9999)}-{i}",
                    "service": svc,
                    "namespace": "production",
                    "status": "Running",
                    "ready": True,
                    "restarts": 0,
                    "cpu_usage": round(random.uniform(15, 45), 1),
                    "memory_usage": round(random.uniform(30, 60), 1),
                    "node": f"node-{random.randint(1,5)}",
                    "age_hours": random.randint(1, 72),
                })
        self._events.append({
            "type": "Normal",
            "reason": "Started",
            "message": "All pods running normally",
            "service": "system",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    def get_pods(self, service_name: str | None = None) -> list[dict]:
        """获取 Pod 列表。"""
        if service_name:
            return [p for p in self._pods if p["service"] == service_name]
        return self._pods

    def get_deployments(self, service_name: str | None = None) -> list[dict]:
        """获取 Deployment 列表。"""
        if service_name:
            dep = self._deployments.get(service_name)
            return [dep] if dep else []
        return list(self._deployments.values())

    def get_events(self, service_name: str | None = None) -> list[dict]:
        """获取 Event 列表。"""
        if service_name:
            return [e for e in self._events if e.get("service") == service_name]
        return self._events

    def inject_pod_crash(self, service_name: str, count: int = 1) -> None:
        """注入 Pod 崩溃场景。"""
        pods = [p for p in self._pods if p["service"] == service_name]
        for pod in pods[:count]:
            pod["status"] = "CrashLoopBackOff"
            pod["ready"] = False
            pod["restarts"] += random.randint(3, 10)
            self._events.append({
                "type": "Warning",
                "reason": "BackOff",
                "message": f"Pod {pod['name']} CrashLoopBackOff",
                "service": service_name,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            })

    def inject_resource_pressure(self, service_name: str) -> None:
        """注入资源压力场景。"""
        for pod in self._pods:
            if pod["service"] == service_name:
                pod["cpu_usage"] = round(random.uniform(85, 98), 1)
                pod["memory_usage"] = round(random.uniform(80, 95), 1)

    def inject_deployment(self, service_name: str, image_tag: str = "v1.2.4") -> None:
        """注入新部署。"""
        dep = self._deployments.get(service_name)
        if dep:
            dep["image"] = f"registry.internal/{service_name}:{image_tag}"
            dep["ready_replicas"] = dep["replicas"]
        self._events.append({
            "type": "Normal",
            "reason": "Deployment",
            "message": f"Deployed {service_name}:{image_tag}",
            "service": service_name,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    def reset(self) -> None:
        """重置到基线状态。"""
        self._deployments.clear()
        self._pods.clear()
        self._events.clear()
        self._scenario = None
        self._init_baseline()
