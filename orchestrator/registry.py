"""Capability registry for MCP tools, Skills, and A2A agents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class Capability:
    id: str
    type: Literal["mcp", "skill", "a2a_agent"]
    description: str
    input_schema: dict[str, str]
    tags: list[str]
    mcp_server: str | None = None
    mcp_tool: str | None = None
    skill_path: str | None = None
    agent_card_url: str | None = None

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "description": self.description,
            "input_schema": self.input_schema,
            "tags": self.tags,
        }


REGISTRY: dict[str, Capability] = {
    "market_data_search": Capability(
        id="market_data_search",
        type="mcp",
        description="按 query 搜索市场数据",
        input_schema={"query": "string"},
        tags=["data", "search", "market"],
        mcp_server="data-mcp",
        mcp_tool="search_by_query",
    ),
    "platform_data_fetch": Capability(
        id="platform_data_fetch",
        type="mcp",
        description="按平台 + query 拉取平台数据",
        input_schema={"platform": "string", "query": "string"},
        tags=["data", "platform"],
        mcp_server="data-mcp",
        mcp_tool="fetch_by_platform",
    ),
    "competitor_report": Capability(
        id="competitor_report",
        type="skill",
        description="基于多源数据生成竞品分析报告",
        input_schema={"company_name": "string", "data_sources": "list"},
        tags=["report", "analysis", "competitor"],
        skill_path="skills/competitor_analysis",
    ),
    "biz_opportunity_agent": Capability(
        id="biz_opportunity_agent",
        type="a2a_agent",
        description="商机识别、评分与机会判断",
        input_schema={"lead_info": "object"},
        tags=["business", "opportunity"],
        agent_card_url="https://biz-agent.example.com/.well-known/agent.json",
    ),
}


def get_capability(capability_id: str) -> Capability:
    if capability_id not in REGISTRY:
        raise KeyError(f"Unknown capability: {capability_id}")
    return REGISTRY[capability_id]


def search_capabilities(tags: list[str] | None = None) -> list[Capability]:
    caps = list(REGISTRY.values())
    if not tags:
        return caps
    tag_set = set(tags)
    return [cap for cap in caps if tag_set & set(cap.tags)]


def format_capabilities(caps: list[Capability]) -> str:
    lines = []
    for cap in caps:
        lines.append(
            f"- {cap.id} ({cap.type}): {cap.description}; "
            f"input={cap.input_schema}; tags={cap.tags}"
        )
    return "\n".join(lines)
