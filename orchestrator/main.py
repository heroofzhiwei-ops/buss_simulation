"""CLI entry for orchestrator demo."""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from typing import Any

from orchestrator.graph import build_graph
from orchestrator.state import initial_state


async def run_task(
    query: str,
    *,
    context_id: str | None = None,
    demo_mode: bool = True,
    stream: bool = True,
) -> dict[str, Any]:
    app = build_graph(demo_mode=demo_mode)
    config = {"configurable": {"thread_id": context_id or str(uuid.uuid4())}}
    state = initial_state(query=query, context_id=config["configurable"]["thread_id"])

    if stream:
        async for event in app.astream(state, config=config, stream_mode="updates"):
            node_name, update = next(iter(event.items()))
            payload = {
                "node": node_name,
                "status": update.get("status"),
                "current_step_idx": update.get("current_step_idx"),
            }
            if update.get("eval_history"):
                payload["eval"] = update["eval_history"][-1]
            print(f"[stream] {json.dumps(payload, ensure_ascii=False)}")
        final_state = (await app.aget_state(config)).values
    else:
        final_state = await app.ainvoke(state, config=config)
    return {
        "status": final_state.get("status"),
        "final_output": final_state.get("final_output"),
        "task_plan": final_state.get("task_plan"),
        "step_results": final_state.get("step_results"),
        "eval_history": final_state.get("eval_history"),
        "error": final_state.get("error"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="LangGraph Task Planner / Eval Orchestrator")
    parser.add_argument(
        "--query",
        default="帮我分析淘宝和京东上 XX 品牌的竞品情况，并判断有没有商机",
        help="用户请求",
    )
    parser.add_argument("--context-id", default="", help="A2A contextId / LangGraph thread_id")
    parser.add_argument(
        "--demo",
        action="store_true",
        default=True,
        help="使用 mock LLM（默认开启）",
    )
    parser.add_argument(
        "--real-llm",
        action="store_true",
        help="使用项目 .env 中的真实 LLM（需要 LLM_API_KEY）",
    )
    parser.add_argument("--no-stream", action="store_true", help="关闭流式日志")
    args = parser.parse_args()

    result = asyncio.run(
        run_task(
            args.query,
            context_id=args.context_id or None,
            demo_mode=not args.real_llm,
            stream=not args.no_stream,
        )
    )

    print("\n=== RESULT ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
