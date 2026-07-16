"""Query analysis node."""

from __future__ import annotations

import json
from typing import Any

from llm_client import parse_json_loose


async def analyze_query(state: dict[str, Any], *, llm) -> dict[str, Any]:
    prompt = f"""
分析用户请求，输出 JSON：
{{
  "intent": "意图类型",
  "entities": {{}},
  "required_tags": ["data", "report"],
  "complexity": "single_step | multi_step"
}}

用户请求：{state["query"]}
"""
    raw = await llm.ainvoke(prompt, system="你是 query 分析器，只输出 JSON")
    intent = parse_json_loose(raw)
    if not intent:
        intent = json.loads(raw) if raw.strip().startswith("{") else {"intent": state["query"]}

    return {"intent": intent, "status": "planning"}
