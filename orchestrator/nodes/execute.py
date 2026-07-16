"""Step execution node."""

from __future__ import annotations

import time
from typing import Any

from orchestrator.registry import get_capability
from orchestrator.state import StepResult
from orchestrator.tools.a2a_client import A2AClient
from orchestrator.tools.mcp_client import MCPClient
from orchestrator.tools.skill_runner import SkillRunner
from orchestrator.utils import get_current_step, resolve_params


async def execute_step(
    state: dict[str, Any],
    *,
    mcp: MCPClient,
    skills: SkillRunner,
    a2a: A2AClient,
) -> dict[str, Any]:
    step = get_current_step(state)
    cap = get_capability(step.capability_id)
    params = resolve_params(step.params, state.get("step_results", []))
    attempt = sum(1 for item in state.get("step_results", []) if item.get("step_id") == step.id) + 1
    params["_attempt"] = attempt

    started = time.time()
    try:
        if cap.type == "mcp":
            output = await mcp.call(cap.mcp_server, cap.mcp_tool, params)
        elif cap.type == "skill":
            output = await skills.run(cap.skill_path, params)
        elif cap.type == "a2a_agent":
            output = await a2a.invoke(cap.agent_card_url, params)
        else:
            raise ValueError(f"Unsupported capability type: {cap.type}")

        result = StepResult(
            step_id=step.id,
            capability_id=step.capability_id,
            status="success",
            output=output,
            latency_ms=int((time.time() - started) * 1000),
        )
    except Exception as exc:  # noqa: BLE001 - surface execution errors to eval loop
        result = StepResult(
            step_id=step.id,
            capability_id=step.capability_id,
            status="failed",
            output=None,
            error=str(exc),
            latency_ms=int((time.time() - started) * 1000),
        )

    return {
        "step_results": state.get("step_results", []) + [result.to_dict()],
        "status": "evaluating",
    }
