"""Mock skill runner for report analysis skills."""

from __future__ import annotations

from typing import Any


class SkillRunner:
    async def run(self, skill_path: str | None, params: dict[str, Any]) -> dict[str, Any]:
        company = params.get("company_name", "未知品牌")
        sources = params.get("data_sources", [])
        return {
            "skill": skill_path,
            "company_name": company,
            "summary": f"{company} 竞品分析完成",
            "swot": {
                "strengths": ["供应链稳定", "价格带有优势"],
                "weaknesses": ["品牌认知偏弱"],
                "opportunities": ["内容电商增长", "跨境需求"],
                "threats": ["同质化竞争"],
            },
            "source_count": len(sources),
        }
