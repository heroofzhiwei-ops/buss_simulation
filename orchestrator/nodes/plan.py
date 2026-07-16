"""Task planning node."""

from __future__ import annotations

from typing import Any

from llm_client import parse_json_loose
from orchestrator.registry import format_capabilities, search_capabilities
from orchestrator.utils import steps_from_plan_data


async def plan(state: dict[str, Any], *, llm) -> dict[str, Any]:
    tags = state.get("intent", {}).get("required_tags")
    candidates = search_capabilities(tags=tags)

    prompt = f"""
根据用户请求和可用能力，生成执行计划。

用户请求: {state["query"]}
意图分析: {state["intent"]}
可用能力:
{format_capabilities(candidates)}

输出 JSON:
{{
  "steps": [
    {{
      "id": "step_1",
      "capability_id": "platform_data_fetch",
      "params": {{"platform": "taobao", "query": "..."}},
      "depends_on": [],
      "success_criteria": "返回至少10条有效记录"
    }}
  ],
  "max_retries": 3
}}
"""
    raw = await llm.ainvoke(prompt, system="你是任务规划器，只输出 JSON")
    plan_data = parse_json_loose(raw)
    steps = steps_from_plan_data(plan_data)

    return {
        "task_plan": steps,
        "current_step_idx": 0,
        "retry_count": 0,
        "max_retries": int(plan_data.get("max_retries", state.get("max_retries", 3))),
        "status": "executing",
    }
