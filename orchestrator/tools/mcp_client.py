"""Mock MCP client for local development."""

from __future__ import annotations

from typing import Any


class MCPClient:
    """Replace with real MCP SDK client in production."""

    async def call(self, server: str, tool: str, params: dict[str, Any]) -> Any:
        if tool == "search_by_query":
            query = params.get("query", "")
            return [
                {"title": f"{query} 商品-{idx}", "sales": 100 + idx * 7}
                for idx in range(1, 16)
            ]

        if tool == "fetch_by_platform":
            platform = params.get("platform", "unknown")
            query = params.get("query", "")
            attempt = int(params.get("_attempt", 1))
            # 第一次调用返回稀疏数据，触发 eval retry；第二次返回充足数据
            if platform == "taobao" and attempt == 1 and "扩大" not in query:
                return [
                    {"platform": platform, "title": f"{query}-{idx}", "sales": idx * 3}
                    for idx in range(1, 4)
                ]
            return [
                {"platform": platform, "title": f"{query}-{idx}", "sales": 50 + idx * 5}
                for idx in range(1, 16)
            ]

        raise ValueError(f"Unknown MCP tool: {server}/{tool}")
