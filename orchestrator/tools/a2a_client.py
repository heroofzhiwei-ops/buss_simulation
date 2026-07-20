"""Mock A2A client for sub-agent delegation."""

from __future__ import annotations

from typing import Any


class A2AClient:
    async def invoke(self, agent_card_url: str | None, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "agent_card_url": agent_card_url,
            "opportunity_score": "B+",
            "confidence": 0.78,
            "recommendation": "建议优先验证供应链与价格带，再推进渠道测试",
            "input": params,
        }
