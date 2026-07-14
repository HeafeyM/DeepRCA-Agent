"""L1 通用分析 Agent — Coordinator 6 节点函数实现。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建：intake/planner/dispatcher/collector/root_cause/reporter 6 节点</td><td>REQ: 20260713-总体架构, TECH: 04b §3.3, §3.4.1-3.4.2</td></tr>
</table>
@author xianhuimeng
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any

from deeprca.config import get_settings
from deeprca.models import (
    AnalysisReport,
    Evidence,
    EvidenceLevel,
    EvidencePool,
    ParsedAlert,
    RootCauseCandidate,
    RootCauseResult,
    SubAgentResult,
)

__all__ = [
    "intake_node",
    "planner_node",
    "dispatcher_node",
    "collector_node",
    "root_cause_node",
    "reporter_node",
    "check_timeout",
]

# 维度 → 分析函数映射（在模块加载时延迟导入，避免循环依赖）
_DIMENSION_MAP: dict[str, str] = {
    "change": "analyze_change",
    "upstream": "analyze_upstream",
    "downstream": "analyze_downstream",
    "cluster": "analyze_cluster",
    "errorlog": "analyze_errorlog",
    "problem": "analyze_problem",
}

# 线程池（全局单例，避免每次创建）
_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    """获取全局线程池单例。"""
    global _executor
    if _executor is None:
        settings = get_settings()
        _executor = ThreadPoolExecutor(max_workers=settings.max_concurrent_tasks)
    return _executor


def _now_iso() -> str:
    """当前时间 ISO 8601。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _parse_iso(ts: str) -> datetime:
    """解析 ISO 8601 时间戳。"""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return datetime.now(timezone.utc)


# ─────────────────────────────────────────────
# B01: intake — 告警解析
# ─────────────────────────────────────────────
def intake_node(state: DeepRCAState) -> dict:
    """接收告警事件，提取关键字段并标准化。

    输入: state["alert"] = AlertEvent 序列化 dict
    输出: {"alert": ParsedAlert dict, "trace_id": str, "start_time": str, "status": "running"}
    """
    raw_alert = state.get("alert", {})

    # 提取标签
    labels = raw_alert.get("labels", {})
    cluster = labels.get("cluster") or labels.get("cls")
    env = labels.get("env") or labels.get("environment")
    app = labels.get("app") or labels.get("application") or raw_alert.get("service_name")

    # 构造时间窗口（告警前 30 分钟到告警时间）
    alert_ts = raw_alert.get("timestamp", _now_iso())
    alert_dt = _parse_iso(alert_ts)
    window_start = (alert_dt - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    parsed = ParsedAlert(
        alert_id=raw_alert.get("alert_id", str(uuid.uuid4())),
        service_name=raw_alert.get("service_name", "unknown"),
        alert_type=raw_alert.get("alert_type", "custom"),
        severity=raw_alert.get("severity", "P2"),
        timestamp=alert_ts,
        description=raw_alert.get("description", ""),
        labels=labels,
        time_window_start=window_start,
        time_window_end=alert_ts,
        cluster=cluster,
        env=env,
        app=app,
    )

    trace_id = f"trace-{uuid.uuid4().hex[:12]}"

    return {
        "alert": parsed.model_dump(),
        "trace_id": trace_id,
        "start_time": _now_iso(),
        "status": "running",
        "messages": [f"[intake] 解析告警: service={parsed.service_name}, severity={parsed.severity}"],
    }


# ─────────────────────────────────────────────
# B02: planner — 任务拆解
# ─────────────────────────────────────────────
def planner_node(state: DeepRCAState) -> dict:
    """任务拆解，生成 6 维度分析计划。

    输入: state["alert"] = ParsedAlert dict
    输出: {"task_plan": list[TaskPlan]}
    """
    settings = get_settings()
    alert = state.get("alert", {})
    service_name = alert.get("service_name", "unknown")
    window_start = alert.get("time_window_start", "")
    window_end = alert.get("time_window_end", "")

    task_plan: list[dict] = []

    # 6 个维度分析任务，按优先级排序
    dimensions = [
        ("change", "change_analyzer", 1),      # 变更优先级最高（最常见根因）
        ("errorlog", "errorlog_analyzer", 2),   # 错误日志次之
        ("cluster", "cluster_analyzer", 3),     # 集群资源
        ("upstream", "upstream_analyzer", 4),   # 上游流量
        ("downstream", "downstream_analyzer", 5), # 下游依赖
        ("problem", "problem_analyzer", 6),     # 已知问题匹配
    ]

    for dimension, tool_name, priority in dimensions:
        task_plan.append({
            "dimension": dimension,
            "tool_name": tool_name,
            "params": {
                "service_name": service_name,
                "start_time": window_start,
                "end_time": window_end,
                "alert": alert,
            },
            "timeout": settings.tool_call_timeout,
            "priority": priority,
        })

    # 按优先级排序
    task_plan.sort(key=lambda t: t["priority"])

    return {
        "task_plan": task_plan,
        "messages": [f"[planner] 生成 {len(task_plan)} 个分析任务"],
    }


# ─────────────────────────────────────────────
# B03: dispatcher — 并发调度
# ─────────────────────────────────────────────
async def dispatcher_node(state: DeepRCAState) -> dict:
    """并发派发 6 维度分析任务。

    使用 asyncio.gather + ThreadPoolExecutor 并发执行。
    单任务超时降级为 error result，不阻塞其他任务。
    """
    task_plan = state.get("task_plan", [])
    if not task_plan:
        return {"sub_agent_results": [], "messages": ["[dispatcher] 无任务可执行"]}

    # 延迟导入维度分析函数（PRD-03 实现，当前降级为空结果）
    try:
        from deeprca.agents.dimensions import (
            analyze_change,
            analyze_cluster,
            analyze_downstream,
            analyze_errorlog,
            analyze_problem,
            analyze_upstream,
        )

        _func_map = {
            "change": analyze_change,
            "upstream": analyze_upstream,
            "downstream": analyze_downstream,
            "cluster": analyze_cluster,
            "errorlog": analyze_errorlog,
            "problem": analyze_problem,
        }
    except ImportError:
        # PRD-03 尚未实现，所有维度返回降级结果
        _func_map = {}

    async def _run_one(task: dict) -> dict:
        """执行单个维度分析，带超时和错误降级。"""
        dimension = task["dimension"]
        params = task["params"]
        timeout = task.get("timeout", 10)

        func = _func_map.get(dimension)
        if func is None:
            return SubAgentResult(
                agent_name=f"{dimension}_analyzer",
                dimension=dimension,
                confidence=0.0,
                error=f"维度分析器尚未实现 (待 PRD-03): {dimension}",
                timestamp=_now_iso(),
            ).model_dump()

        try:
            result = await asyncio.wait_for(
                func(params.get("alert", {})),
                timeout=timeout,
            )
            return result.model_dump() if hasattr(result, "model_dump") else result
        except asyncio.TimeoutError:
            return SubAgentResult(
                agent_name=f"{dimension}_analyzer",
                dimension=dimension,
                confidence=0.0,
                error=f"分析超时 ({timeout}s)",
                timestamp=_now_iso(),
            ).model_dump()
        except Exception as e:
            return SubAgentResult(
                agent_name=f"{dimension}_analyzer",
                dimension=dimension,
                confidence=0.0,
                error=f"分析异常: {e!s}",
                timestamp=_now_iso(),
            ).model_dump()

    # 并发执行所有维度分析
    results = await asyncio.gather(*[_run_one(t) for t in task_plan])

    return {
        "sub_agent_results": list(results),
        "messages": [f"[dispatcher] 并发完成 {len(results)} 个维度分析"],
    }


# ─────────────────────────────────────────────
# B04: collector — 证据池聚合
# ─────────────────────────────────────────────
def collector_node(state: DeepRCAState) -> dict:
    """汇聚所有维度分析结果，构建证据池摘要。

    输入: state["sub_agent_results"] = list[SubAgentResult dict]
    输出: {"collected_evidence": EvidencePool summary dict}
    """
    sub_results = state.get("sub_agent_results", [])
    pool = EvidencePool()

    for result_dict in sub_results:
        agent_name = result_dict.get("agent_name", "unknown")
        dimension = result_dict.get("dimension", "unknown")
        confidence = result_dict.get("confidence", 0.0)
        findings = result_dict.get("findings", [])
        error = result_dict.get("error")

        # 错误结果记录为低等级证据
        if error:
            pool.add(Evidence(
                source=agent_name,
                dimension=dimension,
                finding=f"分析失败: {error}",
                level=EvidenceLevel.LOW,
                confidence=0.0,
                timestamp=result_dict.get("timestamp", _now_iso()),
            ))
            continue

        # 将每个 finding 转为 Evidence
        for finding in findings:
            finding_str = str(finding.get("desc", finding.get("description", finding)))
            level = EvidenceLevel.HIGH if confidence >= 0.7 else (
                EvidenceLevel.MEDIUM if confidence >= 0.4 else EvidenceLevel.LOW
            )
            pool.add(Evidence(
                source=agent_name,
                dimension=dimension,
                finding=finding_str,
                level=level,
                confidence=confidence,
                data=finding,
                timestamp=result_dict.get("timestamp", _now_iso()),
            ))

    summary = pool.to_summary()

    return {
        "collected_evidence": summary,
        "messages": [f"[collector] 汇聚 {len(pool.evidences)} 条证据"],
    }


# ─────────────────────────────────────────────
# B05+root_cause: 根因定位节点（调用 L3 Agent）
# ─────────────────────────────────────────────
async def root_cause_node(state: DeepRCAState) -> dict:
    """根因定位节点。

    调用 L3 RootCauseAgent 执行 6 步根因定位。
    如果 L3 Agent 不可用，降级为基于证据池的简单排序。
    """
    alert = state.get("alert", {})
    evidence_summary = state.get("collected_evidence", {})
    sub_agent_results = state.get("sub_agent_results", [])
    trace_id = state.get("trace_id", "")

    try:
        # 延迟导入 RootCauseAgent（Worker-3 实现）
        from deeprca.agents.root_cause import RootCauseAgent

        agent = RootCauseAgent()
        result = await agent.analyze(alert, evidence_summary, sub_agent_results)

        # 确保 trace_id 和 timestamp 存在
        if isinstance(result, dict):
            result.setdefault("trace_id", trace_id)
            result.setdefault("timestamp", _now_iso())

        return {
            "root_cause": result,
            "messages": [f"[root_cause] 根因定位完成"],
        }
    except ImportError:
        # L3 Agent 尚未实现，降级为简单排序
        return _fallback_root_cause(state)
    except Exception as e:
        return {
            "root_cause": {
                "candidates": [],
                "best_candidate": None,
                "anomalies_detected": [],
                "rule_matched": False,
                "llm_used": False,
                "trace_id": trace_id,
                "timestamp": _now_iso(),
                "error": str(e),
            },
            "messages": [f"[root_cause] 异常: {e}"],
        }


def _fallback_root_cause(state: DeepRCAState) -> dict:
    """降级根因定位：基于证据池置信度排序。"""
    sub_results = state.get("sub_agent_results", [])
    trace_id = state.get("trace_id", "")

    # 按置信度排序
    sorted_results = sorted(
        [r for r in sub_results if r.get("confidence", 0) > 0 and not r.get("error")],
        key=lambda r: r.get("confidence", 0),
        reverse=True,
    )

    candidates: list[dict] = []
    for i, result in enumerate(sorted_results[:3]):
        findings = result.get("findings", [])
        root_cause_desc = "; ".join(
            str(f.get("desc", f.get("description", f))) for f in findings[:3]
        ) or f"{result.get('dimension', 'unknown')} 维度发现异常"
        candidates.append({
            "rank": i + 1,
            "root_cause": root_cause_desc,
            "confidence": result.get("confidence", 0.0),
            "evidence_chain": result.get("evidence", []),
            "matched_rule": None,
            "source": "fallback",
        })

    best = candidates[0] if candidates else None

    return {
        "root_cause": {
            "candidates": candidates,
            "best_candidate": best,
            "anomalies_detected": [],
            "rule_matched": False,
            "llm_used": False,
            "trace_id": trace_id,
            "timestamp": _now_iso(),
        },
        "messages": ["[root_cause] 降级模式：基于置信度排序"],
    }


# ─────────────────────────────────────────────
# B06: reporter — 报告生成
# ─────────────────────────────────────────────
def reporter_node(state: DeepRCAState) -> dict:
    """生成分析报告。

    汇总根因结果、证据链、分析维度，输出 AnalysisReport。
    """
    alert = state.get("alert", {})
    root_cause = state.get("root_cause", {})
    evidence_summary = state.get("collected_evidence", {})
    sub_results = state.get("sub_agent_results", [])
    trace_id = state.get("trace_id", "")
    start_time = state.get("start_time", "")

    # 计算分析耗时
    analysis_duration = None
    if start_time:
        try:
            start_dt = _parse_iso(start_time)
            analysis_duration = (datetime.now(timezone.utc) - start_dt).total_seconds()
        except (ValueError, TypeError):
            pass

    # 提取根因信息
    best_candidate = root_cause.get("best_candidate") or {}
    candidates = root_cause.get("candidates", [])

    # 提取关键证据
    top_evidences = evidence_summary.get("top_evidences", [])
    key_evidence = [e.get("finding", "") for e in top_evidences[:5]]

    # 已分析维度
    dimensions_analyzed = list({r.get("dimension", "") for r in sub_results if r.get("dimension")})

    # 调用的子 Agent
    sub_agents_invoked = [r.get("agent_name", "") for r in sub_results]

    report = AnalysisReport(
        trace_id=trace_id,
        alert_id=alert.get("alert_id", ""),
        service_name=alert.get("service_name", "unknown"),
        severity=alert.get("severity", "P2"),
        status="completed",
        root_cause=best_candidate.get("root_cause"),
        confidence=best_candidate.get("confidence", 0.0),
        top_candidates=candidates,
        key_evidence=key_evidence,
        analysis_duration=analysis_duration,
        dimensions_analyzed=dimensions_analyzed,
        sub_agents_invoked=sub_agents_invoked,
        timestamp=_now_iso(),
        feedback_token=str(uuid.uuid4())[:8],
    )

    return {
        "report": report.model_dump_json(),
        "status": "completed",
        "messages": [f"[reporter] 报告生成完成, trace_id={trace_id}"],
    }


# ─────────────────────────────────────────────
# 超时检查条件边
# ─────────────────────────────────────────────
def check_timeout(state: DeepRCAState) -> str:
    """条件边：检查分析是否超时。

    Returns:
        "normal" → 进入 collector 节点
        "timeout" → 跳过 collector，直接进入 root_cause
    """
    settings = get_settings()
    start_time = state.get("start_time", "")

    if not start_time:
        return "normal"

    try:
        start_dt = _parse_iso(start_time)
        elapsed = (datetime.now(timezone.utc) - start_dt).total_seconds()
        if elapsed > settings.analysis_timeout:
            return "timeout"
    except (ValueError, TypeError):
        pass

    return "normal"


# 用于类型提示的导入
from deeprca.graph.state import DeepRCAState  # noqa: E402
