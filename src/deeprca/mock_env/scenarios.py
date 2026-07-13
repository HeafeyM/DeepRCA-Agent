"""故障场景定义 — 预置 6 类常见故障场景，可动态注入和重置。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建：6 类预置场景</td><td>REQ: 20260713-总体架构, TECH: 04b §3.5</td></tr>
</table>
@author DeepRCA Team
"""

from __future__ import annotations

from typing import Any

from deeprca.mock_env.k8s_simulator import K8sSimulator
from deeprca.mock_env.service_simulator import ServiceSimulator

__all__ = ["SCENARIOS", "apply_scenario", "reset_scenario"]


# 全局单例（mock_env main.py 启动时初始化）
_k8s: K8sSimulator | None = None
_service: ServiceSimulator | None = None


def _get_singletons() -> tuple[K8sSimulator, ServiceSimulator]:
    global _k8s, _service
    if _k8s is None:
        _k8s = K8sSimulator()
    if _service is None:
        _service = ServiceSimulator()
    return _k8s, _service


# ─────────────────────────────────────
# 场景定义
# ─────────────────────────────────────
SCENARIOS: dict[str, dict[str, Any]] = {
    "pod_crash": {
        "name": "Pod 崩溃 (CrashLoopBackOff)",
        "description": "目标服务 Pod 进入 CrashLoopBackOff 状态，频繁重启",
        "k8s_action": "inject_pod_crash",
        "k8s_params": {"count": 2},
        "service_scenario": "pod_crash",
        "expected_root_cause": "Pod CrashLoopBackOff — 容器启动失败导致服务不可用",
        "key_metrics": ["error_rate", "cpu_usage"],
        "key_logs": ["CrashLoopBackOff", "Connection refused"],
    },
    "resource_pressure": {
        "name": "资源压力 (CPU/内存飙高)",
        "description": "目标服务 CPU/内存使用率飙升至 90%+，响应变慢",
        "k8s_action": "inject_resource_pressure",
        "k8s_params": {},
        "service_scenario": "resource_pressure",
        "expected_root_cause": "CPU/Memory 资源耗尽 — 节点资源不足导致服务降级",
        "key_metrics": ["cpu_usage", "memory_usage", "tp99"],
        "key_logs": ["OutOfMemoryError", "CPU throttling"],
    },
    "db_slow_query": {
        "name": "数据库慢查询",
        "description": "下游 DB-Proxy 出现慢查询，TP99 飙升至 800ms+",
        "k8s_action": None,
        "k8s_params": {},
        "service_scenario": "db_slow_query",
        "expected_root_cause": "DB 慢查询 — SQL 缺少索引或数据量激增导致查询超时",
        "key_metrics": ["tp99", "error_rate"],
        "key_logs": ["SQL execution timeout", "Connection is not available"],
    },
    "redis_timeout": {
        "name": "Redis 超时",
        "description": "Redis 连接池耗尽，缓存读写超时",
        "k8s_action": None,
        "k8s_params": {},
        "service_scenario": "redis_timeout",
        "expected_root_cause": "Redis 连接池耗尽 — 缓存击穿导致大量请求直穿 DB",
        "key_metrics": ["tp99", "error_rate"],
        "key_logs": ["Redis command timeout", "JedisConnectionException"],
    },
    "traffic_spike": {
        "name": "流量突增",
        "description": "入口 QPS 突增至 3000+，服务处理能力不足",
        "k8s_action": None,
        "k8s_params": {},
        "service_scenario": "traffic_spike",
        "expected_root_cause": "流量突增 — 入口流量超出服务承载能力导致排队降级",
        "key_metrics": ["qps", "tp99"],
        "key_logs": ["Request queue full", "Rate limit exceeded"],
    },
    "deployment_failure": {
        "name": "部署失败 (新版本 Bug)",
        "description": "新版本部署引入 Bug，NullPointerException 频发",
        "k8s_action": "inject_deployment",
        "k8s_params": {"image_tag": "v1.2.4"},
        "service_scenario": "deployment_failure",
        "expected_root_cause": "部署引入 Bug — v1.2.4 版本 NullPointerException 导致请求失败",
        "key_metrics": ["error_rate"],
        "key_logs": ["NullPointerException", "Bean creation exception"],
    },
}


def apply_scenario(scenario_name: str, service_name: str = "order-service") -> dict[str, Any]:
    """应用故障场景。

    Args:
        scenario_name: 场景名称（见 SCENARIOS keys）
        service_name: 目标服务名

    Returns:
        包含场景信息和应用结果的字典

    Raises:
        ValueError: 未知场景名
    """
    if scenario_name not in SCENARIOS:
        raise ValueError(f"未知场景: {scenario_name}, 可用: {list(SCENARIOS.keys())}")

    scenario = SCENARIOS[scenario_name]
    k8s, service = _get_singletons()

    # 重置到基线
    k8s.reset()
    service.reset()

    # 应用 K8s 场景
    k8s_result: dict | None = None
    k8s_action = scenario.get("k8s_action")
    if k8s_action and hasattr(k8s, k8s_action):
        method = getattr(k8s, k8s_action)
        params = scenario.get("k8s_params", {})
        try:
            method(service_name, **params) if params else method(service_name)
            k8s_result = {"action": k8s_action, "service": service_name, "params": params}
        except TypeError:
            method(service_name)
            k8s_result = {"action": k8s_action, "service": service_name}

    # 应用服务级场景
    service.set_scenario(scenario.get("service_scenario"))

    return {
        "scenario": scenario_name,
        "service": service_name,
        "description": scenario["description"],
        "expected_root_cause": scenario["expected_root_cause"],
        "k8s_result": k8s_result,
        "applied_at": _now_iso(),
    }


def reset_scenario() -> dict[str, str]:
    """重置所有模拟器到基线状态。"""
    k8s, service = _get_singletons()
    k8s.reset()
    service.reset()
    return {"status": "reset", "timestamp": _now_iso()}


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
