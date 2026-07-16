"""Shared helpers for orchestrator nodes."""

from __future__ import annotations

from typing import Any

from orchestrator.state import Step, StepResult


def resolve_params(params: dict[str, Any], step_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Replace step id references in params with actual step outputs."""
    resolved: dict[str, Any] = {}
    result_by_step = {item["step_id"]: item for item in step_results}

    for key, value in params.items():
        if isinstance(value, str) and value in result_by_step:
            resolved[key] = result_by_step[value].get("output")
        elif isinstance(value, list):
            resolved[key] = [
                result_by_step[item].get("output") if isinstance(item, str) and item in result_by_step else item
                for item in value
            ]
        else:
            resolved[key] = value
    return resolved


def get_current_step(state: dict[str, Any]) -> Step:
    task_plan = state.get("task_plan", [])
    idx = state.get("current_step_idx", 0)
    if idx >= len(task_plan):
        raise IndexError("No current step in task_plan")
    return Step.from_dict(task_plan[idx])


def get_last_step_result(state: dict[str, Any]) -> StepResult:
    results = state.get("step_results", [])
    if not results:
        raise ValueError("No step results available")
    return StepResult.from_dict(results[-1])


def steps_from_plan_data(plan_data: dict[str, Any]) -> list[dict[str, Any]]:
    return [Step.from_dict(item).to_dict() for item in plan_data.get("steps", [])]
