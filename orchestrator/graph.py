"""LangGraph orchestrator assembly."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from orchestrator.llm import LLMClient, create_llm
from orchestrator.nodes.analyze import analyze_query
from orchestrator.nodes.evaluate import evaluate_final, evaluate_step
from orchestrator.nodes.execute import execute_step
from orchestrator.nodes.plan import plan
from orchestrator.nodes.replan import replan
from orchestrator.nodes.synthesize import synthesize
from orchestrator.state import OrchestratorState
from orchestrator.tools.a2a_client import A2AClient
from orchestrator.tools.mcp_client import MCPClient
from orchestrator.tools.skill_runner import SkillRunner


def route_after_step_eval(state: OrchestratorState) -> str:
    eval_history = state.get("eval_history", [])
    if not eval_history:
        return "failed"

    last_eval = eval_history[-1]
    action = last_eval.get("action", "continue")
    passed = bool(last_eval.get("passed", False))
    retry_count = int(state.get("retry_count", 0))
    max_retries = int(state.get("max_retries", 3))

    if action == "abort":
        return "failed"
    if not passed:
        if retry_count >= max_retries:
            return "failed"
        if action == "replan":
            return "replan"
        return "retry_step"

    next_idx = int(state.get("current_step_idx", 0)) + 1
    if next_idx < len(state.get("task_plan", [])):
        return "next_step"
    return "final_eval"


def route_after_final_eval(state: OrchestratorState) -> str:
    last_eval = state.get("eval_history", [])[-1]
    if bool(last_eval.get("passed", False)):
        return "synthesize"
    if int(state.get("retry_count", 0)) >= int(state.get("max_retries", 3)):
        return "failed"
    return "replan"


def build_graph(
    *,
    llm: LLMClient | None = None,
    demo_mode: bool = False,
    mcp: MCPClient | None = None,
    skills: SkillRunner | None = None,
    a2a: A2AClient | None = None,
):
    llm = llm or create_llm(demo_mode=demo_mode)
    mcp = mcp or MCPClient()
    skills = skills or SkillRunner()
    a2a = a2a or A2AClient()

    graph = StateGraph(OrchestratorState)

    async def _analyze(state: OrchestratorState) -> dict[str, Any]:
        return await analyze_query(state, llm=llm)

    async def _plan(state: OrchestratorState) -> dict[str, Any]:
        return await plan(state, llm=llm)

    async def _execute(state: OrchestratorState) -> dict[str, Any]:
        return await execute_step(state, mcp=mcp, skills=skills, a2a=a2a)

    async def _evaluate(state: OrchestratorState) -> dict[str, Any]:
        return await evaluate_step(state, llm=llm)

    async def _final_evaluate(state: OrchestratorState) -> dict[str, Any]:
        return await evaluate_final(state, llm=llm)

    async def _replan(state: OrchestratorState) -> dict[str, Any]:
        return await replan(state, llm=llm)

    async def _synthesize(state: OrchestratorState) -> dict[str, Any]:
        return await synthesize(state, llm=llm)

    async def _advance_step(state: OrchestratorState) -> dict[str, Any]:
        return {
            "current_step_idx": int(state.get("current_step_idx", 0)) + 1,
            "status": "executing",
        }

    async def _prepare_retry(state: OrchestratorState) -> dict[str, Any]:
        return {
            "retry_count": int(state.get("retry_count", 0)) + 1,
            "status": "executing",
        }

    async def _mark_failed(state: OrchestratorState) -> dict[str, Any]:
        last_eval = state.get("eval_history", [])[-1] if state.get("eval_history") else {}
        return {
            "status": "failed",
            "error": last_eval.get("feedback", "执行失败，超过最大重试次数"),
        }

    graph.add_node("analyze", _analyze)
    graph.add_node("make_plan", _plan)
    graph.add_node("execute", _execute)
    graph.add_node("evaluate", _evaluate)
    graph.add_node("advance_step", _advance_step)
    graph.add_node("prepare_retry", _prepare_retry)
    graph.add_node("replan", _replan)
    graph.add_node("final_evaluate", _final_evaluate)
    graph.add_node("synthesize", _synthesize)
    graph.add_node("mark_failed", _mark_failed)

    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "make_plan")
    graph.add_edge("make_plan", "execute")
    graph.add_edge("execute", "evaluate")
    graph.add_edge("advance_step", "execute")
    graph.add_edge("prepare_retry", "execute")
    graph.add_edge("replan", "execute")
    graph.add_edge("synthesize", END)
    graph.add_edge("mark_failed", END)

    graph.add_conditional_edges(
        "evaluate",
        route_after_step_eval,
        {
            "retry_step": "prepare_retry",
            "next_step": "advance_step",
            "replan": "replan",
            "final_eval": "final_evaluate",
            "failed": "mark_failed",
        },
    )

    graph.add_conditional_edges(
        "final_evaluate",
        route_after_final_eval,
        {
            "synthesize": "synthesize",
            "replan": "replan",
            "failed": "mark_failed",
        },
    )

    return graph.compile(checkpointer=MemorySaver())
