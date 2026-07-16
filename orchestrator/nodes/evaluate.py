"""Step and final evaluation nodes."""

from __future__ import annotations

from typing import Any

from llm_client import parse_json_loose
from orchestrator.state import EvalResult
from orchestrator.utils import get_current_step, get_last_step_result


def _deterministic_step_eval(step, result: dict[str, Any]) -> EvalResult | None:
    if result.get("status") == "failed":
        return EvalResult(
            target=step.id,
            passed=False,
            overall_score=0.0,
            scores={},
            feedback=result.get("error") or "执行失败",
            action="retry",
        )

    output = result.get("output")
    if output is None or output == "" or output == []:
        return EvalResult(
            target=step.id,
            passed=False,
            overall_score=0.0,
            scores={"non_empty": 0.0},
            feedback="输出为空",
            action="retry",
        )

    if isinstance(output, list) and len(output) < 10:
        return EvalResult(
            target=step.id,
            passed=False,
            overall_score=round(len(output) / 10, 2),
            scores={"data_count": len(output) / 10},
            feedback=f"数据量不足，仅 {len(output)} 条，建议扩大 query 或换能力",
            action="retry",
        )

    return None


async def evaluate_step(state: dict[str, Any], *, llm) -> dict[str, Any]:
    step = get_current_step(state)
    result = get_last_step_result(state).to_dict()

    quick_eval = _deterministic_step_eval(step, result)
    if quick_eval:
        return {"eval_history": state.get("eval_history", []) + [quick_eval.to_dict()]}

    prompt = f"""
评估这一步是否满足 success_criteria。

success_criteria: {step.success_criteria}
step output: {result.get("output")}

输出 JSON:
{{
  "passed": true,
  "overall_score": 0.0,
  "scores": {{"relevance": 0.8, "completeness": 0.7}},
  "feedback": "具体反馈",
  "action": "continue"
}}
"""
    raw = await llm.ainvoke(prompt, system="你是 step 评估器，只输出 JSON")
    judge = parse_json_loose(raw)

    eval_result = EvalResult(
        target=step.id,
        passed=bool(judge.get("passed", False)),
        overall_score=float(judge.get("overall_score", 0.0)),
        scores={k: float(v) for k, v in judge.get("scores", {}).items()},
        feedback=str(judge.get("feedback", "")),
        action=judge.get("action", "continue"),
    )
    return {"eval_history": state.get("eval_history", []) + [eval_result.to_dict()]}


async def evaluate_final(state: dict[str, Any], *, llm) -> dict[str, Any]:
    prompt = f"""
评估最终输出是否满足用户请求。

用户请求: {state["query"]}
执行轨迹: {state.get("step_results", [])}

输出 JSON:
{{
  "passed": true,
  "overall_score": 0.0,
  "scores": {{"quality": 0.8, "actionability": 0.7}},
  "feedback": "具体反馈",
  "action": "continue"
}}
"""
    raw = await llm.ainvoke(prompt, system="你是最终评估器，只输出 JSON")
    judge = parse_json_loose(raw)

    eval_result = EvalResult(
        target="final",
        passed=bool(judge.get("passed", False)),
        overall_score=float(judge.get("overall_score", 0.0)),
        scores={k: float(v) for k, v in judge.get("scores", {}).items()},
        feedback=str(judge.get("feedback", "")),
        action=judge.get("action", "replan"),
    )
    return {"eval_history": state.get("eval_history", []) + [eval_result.to_dict()]}
