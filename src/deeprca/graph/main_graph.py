"""LangGraph 主编排图骨架。

节点函数的具体实现将在 PRD-02 中完成。
当前版本定义图的拓扑结构（6 节点 + 条件边），
节点函数为占位 stub。

@changelog
<table>
<tr><th>版本</th><th>变更说明</th><th>关联</th></tr>
<tr><td>0.1.0</td><td>初始创建：build_coordinator_graph 骨架（6节点+条件边，占位 stub）</td><td>REQ: 20260713-总体架构, TECH: 04b §3.4.1</td></tr>
</table>
@author DeepRCA Team
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, StateGraph

from deeprca.graph.state import DeepRCAState

__all__ = ["build_coordinator_graph"]


# ---- 占位节点函数（PRD-02 中替换为真实实现） ---- #

def intake_node(state: DeepRCAState) -> dict[str, Any]:
    """Intake: 接收告警，提取关键字段。"""
    # TODO: PRD-02 实现
    return {"status": "running"}


def planner_node(state: DeepRCAState) -> dict[str, Any]:
    """Planner: 任务拆解，生成分析维度列表。"""
    # TODO: PRD-02 实现
    return {"task_plan": []}


def dispatcher_node(state: DeepRCAState) -> dict[str, Any]:
    """Dispatcher: 并发派发分析任务到子 Agent。"""
    # TODO: PRD-02 实现
    return {"sub_agent_results": []}


def collector_node(state: DeepRCAState) -> dict[str, Any]:
    """Collector: 汇聚子 Agent 分析结果。"""
    # TODO: PRD-02 实现
    return {"collected_evidence": None}


def root_cause_node(state: DeepRCAState) -> dict[str, Any]:
    """Root Cause: 根因定位，融合告警+专家经验。"""
    # TODO: PRD-04 实现
    return {"root_cause": None}


def reporter_node(state: DeepRCAState) -> dict[str, Any]:
    """Reporter: 生成分析报告，推送通知。"""
    # TODO: PRD-02 实现
    return {"report": "{}", "status": "completed"}


def check_timeout(state: DeepRCAState) -> str:
    """条件边函数：检查分析超时。"""
    # TODO: PRD-02 实现
    return "normal"


def build_coordinator_graph():
    """构建 L1 通用分析 Agent 主编排图。

    节点流转:
        intake → planner → dispatcher → [normal: collector | timeout: root_cause]
        collector → root_cause → reporter → END

    Returns:
        CompiledStateGraph: 编译后的 LangGraph 图
    """
    graph: StateGraph = StateGraph(DeepRCAState)

    # 添加 6 个节点（当前为占位 stub）
    graph.add_node("intake", intake_node)
    graph.add_node("planner", planner_node)
    graph.add_node("dispatcher", dispatcher_node)
    graph.add_node("collector", collector_node)
    graph.add_node("root_cause", root_cause_node)
    graph.add_node("reporter", reporter_node)

    # 设置入口
    graph.set_entry_point("intake")

    # 线性边
    graph.add_edge("intake", "planner")
    graph.add_edge("planner", "dispatcher")

    # 条件边：超时降级
    graph.add_conditional_edges(
        "dispatcher",
        check_timeout,
        {
            "normal": "collector",
            "timeout": "root_cause",
        },
    )

    # 汇聚到根因定位
    graph.add_edge("collector", "root_cause")
    graph.add_edge("root_cause", "reporter")
    graph.add_edge("reporter", END)

    return graph.compile()
