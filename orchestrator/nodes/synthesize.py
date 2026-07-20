"""Final synthesis node."""

from __future__ import annotations

from typing import Any


async def synthesize(state: dict[str, Any], *, llm) -> dict[str, Any]:
    prompt = f"""
根据多步执行结果，生成最终答复。

用户请求: {state["query"]}
执行结果: {state.get("step_results", [])}

要求：结构化、可执行、面向商机分析场景。
"""
    final_output = await llm.ainvoke(prompt, system="你是商机分析助手")
    return {"final_output": final_output, "status": "done"}
