"""Orchestrator shared state and dataclasses."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, TypedDict


@dataclass
class Step:
    id: str
    capability_id: str
    params: dict[str, Any]
    depends_on: list[str] = field(default_factory=list)
    success_criteria: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Step":
        return cls(
            id=data["id"],
            capability_id=data["capability_id"],
            params=data.get("params", {}),
            depends_on=data.get("depends_on", []),
            success_criteria=data.get("success_criteria", ""),
        )


@dataclass
class StepResult:
    step_id: str
    capability_id: str
    status: Literal["success", "failed", "skipped"]
    output: Any
    error: str | None = None
    latency_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StepResult":
        return cls(**data)


@dataclass
class EvalResult:
    target: str
    passed: bool
    overall_score: float
    scores: dict[str, float]
    feedback: str
    action: Literal["continue", "retry", "replan", "abort"]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvalResult":
        return cls(**data)


class OrchestratorState(TypedDict):
    query: str
    context_id: str
    intent: dict[str, Any]
    task_plan: list[dict[str, Any]]
    current_step_idx: int
    retry_count: int
    max_retries: int
    step_results: list[dict[str, Any]]
    eval_history: list[dict[str, Any]]
    status: Literal[
        "analyzing",
        "planning",
        "executing",
        "evaluating",
        "replanning",
        "synthesizing",
        "done",
        "failed",
    ]
    final_output: str | None
    error: str | None


def initial_state(query: str, context_id: str = "", max_retries: int = 3) -> OrchestratorState:
    return OrchestratorState(
        query=query,
        context_id=context_id,
        intent={},
        task_plan=[],
        current_step_idx=0,
        retry_count=0,
        max_retries=max_retries,
        step_results=[],
        eval_history=[],
        status="analyzing",
        final_output=None,
        error=None,
    )
