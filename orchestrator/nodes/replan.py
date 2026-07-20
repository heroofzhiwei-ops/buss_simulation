"""Re-planning node."""

from __future__ import annotations

from typing import Any

from llm_client import parse_json_loose
from orchestrator.utils import steps_from_plan_data


async def replan(state: dict[str, Any], *, llm) -> dict[str, Any]:
    last_eval = state.get("eval_history", [])[-1] if state.get("eval_history") else {}

    prompt = f"""
当前计划执行失败，请根据反馈重新规划剩余步骤。

原始请求: {state["query"]}
当前计划: {state.get("task_plan", [])}
已执行结果: {state.get("step_results", [])}
评估反馈: {last_eval}

输出 JSON:
{{
  "steps": [
    {{
      "id": "step_retry_1",
      "capability_id": "market_data_search",
      "params": {{"query": "扩大后的 query"}},
      "depends_on": [],
      "success_criteria": "返回至少10条有效记录"
    }}
  ]
}}
"""
    raw = await llm.ainvoke(prompt, system="你是重规划器，只输出 JSON")
    plan_data = parse_json_loose(raw)

    return {
        "task_plan": steps_from_plan_data(plan_data),
        "current_step_idx": 0,
        "retry_count": int(state.get("retry_count", 0)) + 1,
        "status": "executing",
    }
