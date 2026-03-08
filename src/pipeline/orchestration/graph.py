"""
LangGraph 파이프라인 그래프 빌더.

노드 흐름:
  START
    → load_data
    → detect_scenario        (Case C)
    → build_context          (Case D)
    → request_llm
    → validate_resp ──────── conditional edge
        ├── "pass"         → generate_report → END
        ├── "retry"        → retry → request_llm  (루프)
        └── "force_report" → force_report → END
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from src.pipeline.orchestration.state import PipelineState
from src.pipeline.orchestration import nodes


def build_graph() -> "CompiledGraph":
    """
    파이프라인 StateGraph를 빌드하고 컴파일하여 반환.

    Returns:
        langgraph.graph.CompiledGraph
    """
    graph = StateGraph(PipelineState)

    # 노드 등록
    graph.add_node("load_data",        nodes.load_data)
    graph.add_node("detect_scenario",  nodes.detect_scenario)
    graph.add_node("build_context",    nodes.build_context)
    graph.add_node("request_llm",      nodes.request_llm)
    graph.add_node("retry",            nodes.retry)
    graph.add_node("generate_report",  nodes.generate_report)
    graph.add_node("force_report",     nodes.force_report)

    # 엣지 연결
    graph.add_edge(START,              "load_data")
    graph.add_edge("load_data",        "detect_scenario")
    graph.add_edge("detect_scenario",  "build_context")
    graph.add_edge("build_context",    "request_llm")

    # Case B: 신뢰도 검증 conditional edge
    graph.add_conditional_edges(
        "request_llm",
        nodes.validate_resp,
        {
            "pass":         "generate_report",
            "retry":        "retry",
            "force_report": "force_report",
        },
    )

    # 재시도 루프: retry → request_llm
    graph.add_edge("retry", "request_llm")

    # 종료 노드
    graph.add_edge("generate_report", END)
    graph.add_edge("force_report",    END)

    return graph.compile()
