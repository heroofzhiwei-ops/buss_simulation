"""LLM adapter with demo-mode fallback."""

from __future__ import annotations

import json
from typing import Protocol

from orchestrator.registry import format_capabilities, search_capabilities


class LLMClient(Protocol):
    async def ainvoke(self, prompt: str, system: str | None = None) -> str:
        ...


class MockLLM:
    """Rule-based LLM for local demo without API keys."""

    async def ainvoke(self, prompt: str, system: str | None = None) -> str:
        if "生成执行计划" in prompt:
            return json.dumps(
                {
                    "steps": [
                        {
                            "id": "step_1",
                            "capability_id": "platform_data_fetch",
                            "params": {"platform": "taobao", "query": "XX品牌 销量"},
                            "depends_on": [],
                            "success_criteria": "返回至少10条有效记录",
                        },
                        {
                            "id": "step_2",
                            "capability_id": "platform_data_fetch",
                            "params": {"platform": "jd", "query": "XX品牌 销量"},
                            "depends_on": [],
                            "success_criteria": "返回至少10条有效记录",
                        },
                        {
                            "id": "step_3",
                            "capability_id": "competitor_report",
                            "params": {
                                "company_name": "XX品牌",
                                "data_sources": ["step_1", "step_2"],
                            },
                            "depends_on": ["step_1", "step_2"],
                            "success_criteria": "生成包含 SWOT 的完整报告",
                        },
                        {
                            "id": "step_4",
                            "capability_id": "biz_opportunity_agent",
                            "params": {"lead_info": {"source": "step_3"}},
                            "depends_on": ["step_3"],
                            "success_criteria": "输出商机评分与建议",
                        },
                    ],
                    "max_retries": 3,
                },
                ensure_ascii=False,
            )

        if "分析用户请求" in prompt:
            return json.dumps(
                {
                    "intent": "竞品分析+商机判断",
                    "entities": {"brand": "XX品牌", "platforms": ["taobao", "jd"]},
                    "required_tags": ["data", "report", "business"],
                    "complexity": "multi_step",
                },
                ensure_ascii=False,
            )

        if "重新规划" in prompt:
            return json.dumps(
                {
                    "steps": [
                        {
                            "id": "step_1_retry",
                            "capability_id": "market_data_search",
                            "params": {"query": "XX品牌 销量 扩大范围"},
                            "depends_on": [],
                            "success_criteria": "返回至少10条有效记录",
                        }
                    ]
                },
                ensure_ascii=False,
            )

        if "评估这一步" in prompt:
            return json.dumps(
                {
                    "passed": True,
                    "overall_score": 0.86,
                    "scores": {"relevance": 0.9, "completeness": 0.82},
                    "feedback": "满足 success_criteria",
                    "action": "continue",
                },
                ensure_ascii=False,
            )

        if "评估最终输出" in prompt:
            return json.dumps(
                {
                    "passed": True,
                    "overall_score": 0.88,
                    "scores": {"quality": 0.9, "actionability": 0.86},
                    "feedback": "最终结果完整可用",
                    "action": "continue",
                },
                ensure_ascii=False,
            )

        if "生成最终答复" in prompt:
            return (
                "## 商机分析结论\n\n"
                "- 淘宝与京东平台数据已汇总\n"
                "- 竞品报告已完成 SWOT 分析\n"
                "- 商机评分：B+，建议优先验证供应链与价格带\n"
            )

        caps = search_capabilities()
        return format_capabilities(caps)


class ProjectLLM:
    """Reuse project llm_client when API key is configured."""

    async def ainvoke(self, prompt: str, system: str | None = None) -> str:
        from llm_client import llm_call

        return await llm_call(prompt, system=system, temperature=0.2)


def create_llm(demo_mode: bool = False) -> LLMClient:
    if demo_mode:
        return MockLLM()

    from config import LLM_API_KEY

    if not LLM_API_KEY:
        return MockLLM()
    return ProjectLLM()
