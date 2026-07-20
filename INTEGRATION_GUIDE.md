# 商机 Agent 编排层 × 三类 Skill 本地整合指南

> **本文档用途**：给本地 AI（Cursor / Copilot / Claude Code 等）看的**整合说明书**。  
> 按本文档执行，可将 `orchestrator/` 编排骨架与三类 Skill 能力拼装成可运行的 Planner + Eval Agent。

---

## 1. 整合目标

把以下四块拼成一个闭环系统：

```text
A2A 请求
  → Query 分析（analyze）
  → 任务规划（make_plan）
  → 分步执行（execute：调 MCP / Skill / 子 Agent）
  → 实时评估（evaluate：step 级 + final 级）
  → 不满足则 retry / replan
  → 汇总输出（synthesize）
```

**三类 Skill 的分工**：

| 类型 | 目录建议 | 编排层视角 | 典型入参 |
|------|----------|------------|----------|
| **A. 数据 MCP** | `skills/data_mcp/` | `type=mcp` | `query` 或 `platform + query` |
| **B. 报告分析 Skill** | `skills/report/` | `type=skill` | 结构化业务对象 + 前序 step 输出 |
| **C. 商机 Agent** | `skills/opportunity/` | `type=a2a_agent` | `lead_info` / 商机上下文 |

编排层**不关心**具体实现，只认 **Capability Registry** 里的 `capability_id` 和 `input_schema`。

---

## 2. 推荐本地目录结构

整合时，请把代码整理成如下结构（路径名可微调，但职责不要混）：

```text
<你的工作目录>/
├── INTEGRATION_GUIDE.md          # 本文档
├── orchestrator/                 # LangGraph 编排层（已有骨架）
│   ├── graph.py                  # 状态图与控制流（少改）
│   ├── registry.py               # ★ 能力注册表（重点改）
│   ├── state.py                  # 状态结构（按需扩展）
│   ├── nodes/                    # 分析/规划/执行/评估节点
│   └── tools/                    # ★ 执行适配层（重点改）
│       ├── mcp_client.py         # 对接 A 类数据 MCP
│       ├── skill_runner.py       # 对接 B 类报告 Skill
│       └── a2a_client.py         # 对接 C 类商机 Agent
├── skills/
│   ├── data_mcp/                 # A 类：数据 MCP Server / 配置
│   │   ├── servers.yaml          # MCP server 列表与 endpoint
│   │   └── tools/                # 各 tool 的 schema 描述
│   ├── report/                   # B 类：报告分析 Skill
│   │   ├── competitor_analysis/  # 每个 skill 一个子目录
│   │   │   ├── SKILL.md          # skill 说明（给 AI / Planner 用）
│   │   │   ├── schema.json       # 入参/出参 JSON Schema
│   │   │   └── run.py            # 执行入口 async def run(params) -> dict
│   │   └── market_trend/
│   └── opportunity/              # C 类：商机 Agent
│       ├── agent_card.json       # A2A Agent Card
│       └── ...                   # 现有商机 agent 代码
├── config/
│   ├── capabilities.yaml         # ★ 推荐：统一能力清单（可生成到 registry.py）
│   └── eval_rubrics.yaml         # 各 step 的评估标准
└── tests/
    └── test_integration.py       # 整合后的冒烟测试
```

**原则**：

1. **编排层不侵入 Skill 内部逻辑**，只通过 `tools/` 适配器调用。
2. **所有可被 Planner 选择的能力**必须出现在 Registry（或 `capabilities.yaml`）。
3. **一类能力一种适配器**，不要在 `execute.py` 里写死业务逻辑。

---

## 3. 架构设计（给 AI 的理解框架）

### 3.1 协议分层

```text
┌─────────────────────────────────────────────┐
│  A2A Gateway（未来）                          │
│  contextId ↔ LangGraph thread_id           │
└────────────────────┬────────────────────────┘
                     │
┌────────────────────▼────────────────────────┐
│  Orchestrator（LangGraph StateGraph）        │
│  analyze → make_plan → execute → evaluate  │
└──────┬──────────────┬──────────────┬────────┘
       │              │              │
   MCP 协议        Skill 调用      A2A 协议
       │              │              │
┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼──────┐
│ data_mcp/   │ │ report/   │ │opportunity/│
└─────────────┘ └───────────┘ └────────────┘
```

- **MCP**：垂直集成，连接数据源 / 工具。
- **A2A**：水平集成，编排层委派给商机子 Agent。
- **Skill**：本地 Python 模块（或后续暴露为 MCP），由 `skill_runner` 加载执行。

### 3.2 核心抽象：Capability

每个可被规划的能力，统一描述为：

```yaml
# config/capabilities.yaml 示例
capabilities:
  - id: platform_data_fetch
    type: mcp
    description: 按平台+query 拉取商品数据
    input_schema:
      platform: { type: string, enum: [taobao, jd, pdd] }
      query: { type: string }
    tags: [data, platform]
    mcp_server: data-mcp
    mcp_tool: fetch_by_platform

  - id: competitor_report
    type: skill
    description: 生成竞品 SWOT 报告
    input_schema:
      company_name: { type: string }
      data_sources: { type: array }
    tags: [report, analysis]
    skill_path: skills/report/competitor_analysis

  - id: biz_opportunity_agent
    type: a2a_agent
    description: 商机评分与机会判断
    input_schema:
      lead_info: { type: object }
    tags: [business, opportunity]
    agent_card_url: http://localhost:8001/.well-known/agent.json
```

Planner 只看 `id / description / input_schema / tags`，由 Registry 负责映射到真实调用。

### 3.3 状态流转

| 状态字段 | 含义 | 谁写入 |
|----------|------|--------|
| `query` | 原始用户请求 | 入口 |
| `intent` | 意图/实体/所需 tags | `analyze` |
| `task_plan` | Step 列表（注意：不要用 `plan` 作字段名） | `make_plan` / `replan` |
| `current_step_idx` | 当前执行到第几步 | `advance_step` |
| `step_results` | 每步执行结果 | `execute` |
| `eval_history` | 每步/最终评估记录 | `evaluate` |
| `retry_count` | 重试/重规划次数 | `prepare_retry` / `replan` |
| `final_output` | 最终汇总 | `synthesize` |

### 3.4 控制流（LangGraph 条件边）

```text
evaluate(step):
  ├─ passed & 还有下一步 → advance_step → execute
  ├─ passed & 无下一步   → final_evaluate
  ├─ failed & retry      → prepare_retry → execute
  ├─ failed & replan     → replan → execute
  └─ failed & 超限       → mark_failed → END

final_evaluate:
  ├─ passed → synthesize → END
  ├─ failed → replan（未超限）
  └─ 超限   → mark_failed → END
```

---

## 4. 本地 AI 整合步骤（按顺序执行）

> **给 AI 的指令**：严格按 Phase 0 → 5 顺序执行，每完成一阶段运行测试，通过后再进入下一阶段。

### Phase 0：盘点现有资产

1. 列出 `skills/data_mcp/` 下所有 MCP server 和 tool，记录：
   - server 名称、连接方式（stdio / HTTP）
   - 每个 tool 的 name、description、inputSchema
2. 列出 `skills/report/` 下每个 skill 目录，确认是否有统一入口函数。
3. 列出 `skills/opportunity/` 的 A2A Agent Card 或 HTTP endpoint。
4. 输出一份 **能力清单草稿**（Markdown 表格），供 Phase 1 使用。

**验收**：能力清单位完整，无「不知道怎么调」的灰色条目。

---

### Phase 1：注册能力（Registry）

**改动文件**：`orchestrator/registry.py`（或新建 `config/capabilities.yaml` + 加载器）

**AI 要做的事**：

1. 把 Phase 0 的能力清单写入 Registry，每个能力一个唯一 `id`。
2. `tags` 要覆盖 Planner 路由需求，建议统一词表：
   - 数据类：`data`, `search`, `platform`, `market`
   - 报告类：`report`, `analysis`, `trend`, `competitor`
   - 商机类：`business`, `opportunity`, `scoring`
3. `input_schema` 必须与真实接口一致，否则 Planner 生成的 params 会对不上。
4. 删除或保留 mock 能力均可，但 **生产用的能力必须来自真实 skill**。

**代码模板**：

```python
# orchestrator/registry.py
REGISTRY["your_real_tool"] = Capability(
    id="your_real_tool",
    type="mcp",
    description="从 skills/data_mcp 目录同步的真实描述",
    input_schema={"query": "string"},
    tags=["data", "search"],
    mcp_server="your-mcp-server",
    mcp_tool="actual_tool_name",
)
```

**验收**：`python -c "from orchestrator.registry import REGISTRY; print(len(REGISTRY))"` 能打印预期数量。

---

### Phase 2：适配执行层（tools/）

#### 2A. 数据 MCP → `orchestrator/tools/mcp_client.py`

**设计思路**：

- 一个 `MCPClient` 管理多个 server 连接（连接池 / lazy connect）。
- `call(server, tool, params)` 根据 server 路由到对应 MCP 连接。
- 删掉 mock 分支，改为真实 SDK 调用。

**AI 要做的事**：

1. 读取 `skills/data_mcp/servers.yaml`（若无则创建），加载 server 配置。
2. 使用 MCP Python SDK 建立连接，例如：

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPClient:
    async def call(self, server: str, tool: str, params: dict) -> Any:
        # 1. 根据 server 名获取连接配置
        # 2. 调用 session.call_tool(tool, params)
        # 3. 解析返回 content，统一成 Python dict / list
        ...
```

3. 约定返回格式：优先 `list[dict]` 或 `dict`，方便 eval 做数据量检查。
4. 超时、重试、错误包装为统一异常，让 `execute` 节点能记录 `status=failed`。

**注意**：不同 MCP 的入参差异（仅 `query` vs `platform+query`）由 Registry 的 `input_schema` 描述，**不要在 mcp_client 里写业务 if-else**。

---

#### 2B. 报告 Skill → `orchestrator/tools/skill_runner.py`

**设计思路**：

- 每个 skill 是独立目录，`skill_path` 指向该目录。
- 统一入口：`async def run(params: dict) -> dict`。

**AI 要做的事**：

1. 约定 skill 目录结构：

```text
skills/report/<skill_name>/
├── SKILL.md        # 自然语言说明，供 Planner prompt 引用
├── schema.json     # JSON Schema
└── run.py          # async def run(params) -> dict
```

2. 改造 `SkillRunner`：

```python
import importlib.util
from pathlib import Path

class SkillRunner:
    async def run(self, skill_path: str | None, params: dict) -> dict:
        module_path = Path(skill_path) / "run.py"
        spec = importlib.util.spec_from_file_location("skill", module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return await module.run(params)
```

3. 若现有 skill 是同步函数，在 `run.py` 里包一层 `async def run`。
4. 若现有 skill 入口不统一，AI 应为每个 skill 写薄适配层 `run.py`，**不要改 orchestrator 主流程**。

---

#### 2C. 商机 Agent → `orchestrator/tools/a2a_client.py`

**设计思路**：

- 编排层是 A2A Client，商机 Agent 是 A2A Server。
- 通过 Agent Card 发现 endpoint，发送 task，等待 result。

**AI 要做的事**：

1. 读取 `skills/opportunity/agent_card.json`。
2. 使用 `a2a-sdk` 实现：

```python
class A2AClient:
    async def invoke(self, agent_card_url: str | None, params: dict) -> dict:
        # 1. 加载 Agent Card
        # 2. 构造 A2A Task（message = 序列化后的 params 或自然语言）
        # 3. 发送并等待完成（支持 SSE 流式可选）
        # 4. 解析 result 为 dict
        ...
```

3. `contextId` 建议与 LangGraph `thread_id` 对齐，便于多轮会话。
4. 返回结构建议包含：`opportunity_score`, `recommendation`, `evidence` 等，供 eval 和 synthesize 使用。

---

### Phase 3：参数引用与 Step 依赖

**改动文件**：`orchestrator/utils.py`（`resolve_params`）

Planner 生成的 plan 里，后序 step 可引用前序 step 输出：

```json
{
  "id": "step_3",
  "capability_id": "competitor_report",
  "params": {
    "company_name": "XX品牌",
    "data_sources": ["step_1", "step_2"]
  },
  "depends_on": ["step_1", "step_2"]
}
```

`resolve_params` 会把 `"step_1"` 替换为 `step_results` 中对应 output。

**AI 要做的事**：

1. 确认三类 skill 的入参命名与 plan 中的引用一致。
2. 若 skill 需要复杂对象，在 `run.py` 里做从「原始 MCP 输出」到「skill 入参」的转换，而不是在 Planner 里拼复杂逻辑。
3. 可选：在 `execute` 前增加 `depends_on` 完成度检查。

---

### Phase 4：评估标准（Eval）适配

**改动文件**：

- `orchestrator/nodes/evaluate.py`（通用逻辑）
- `config/eval_rubrics.yaml`（各 capability 的专项规则，推荐新建）

**分层评估策略**：

| 层级 | 方式 | 适用 |
|------|------|------|
| L1 | 确定性：空结果、异常、schema | 所有 step |
| L2 | 规则：`success_criteria`、数据量阈值 | 数据 MCP |
| L3 | LLM Judge：相关性、完整性 | 报告 / 商机 |
| L4 | Agent Judge（可选）：调工具验真 | 高价值终评 |

**AI 要做的事**：

1. 在 `eval_rubrics.yaml` 为每个 `capability_id` 定义：

```yaml
platform_data_fetch:
  min_records: 10
  required_fields: [platform, title, sales]

competitor_report:
  required_sections: [swot, summary]

biz_opportunity_agent:
  required_fields: [opportunity_score, recommendation]
  min_score: 0.6
```

2. 在 `_deterministic_step_eval` 中按 `capability_id` 加载 rubric，替代硬编码。
3. 为报告类 skill 增加「必要字段 / 必要章节」检查。
4. 为商机 agent 增加「评分阈值」检查。

**验收**：故意返回不足数据时，能触发 `retry`；故意缺字段时，能触发 `replan` 或 `failed`。

---

### Phase 5：端到端验证

**AI 要做的事**：

1. 编写 `tests/test_integration.py`：

```python
import asyncio
from orchestrator.main import run_task

async def test_full_pipeline():
    result = await run_task(
        "分析淘宝京东 XX 品牌竞品并判断商机",
        demo_mode=False,  # 使用真实后端
        stream=False,
    )
    assert result["status"] == "done"
    assert result["final_output"]
```

2. 运行：

```bash
pip install -r orchestrator/requirements.txt
pip install -r requirements.txt
python -m orchestrator.main --real-llm --no-stream
```

3. 检查输出中的 `task_plan`、`step_results`、`eval_history` 是否符合预期。

---

## 5. 给本地 AI 的执行 Prompt 模板

整合时，可直接把下面这段贴给 Cursor / AI：

```text
请阅读 INTEGRATION_GUIDE.md，按 Phase 0-5 整合商机 Agent 编排层与三类 Skill：

工作目录结构：
- orchestrator/：LangGraph 编排骨架
- skills/data_mcp/：数据 MCP
- skills/report/：报告分析 Skill
- skills/opportunity/：商机 A2A Agent

要求：
1. 不要修改 LangGraph 控制流（graph.py 的条件边），除非发现 bug
2. 所有能力注册到 orchestrator/registry.py
3. 分别改造 tools/mcp_client.py、skill_runner.py、a2a_client.py
4. 每个 report skill 提供统一 run.py 入口
5. 新增 config/eval_rubrics.yaml 并接入 evaluate.py
6. 完成后运行 python -m orchestrator.main --real-llm 验证

约束：
- 编排层不写业务逻辑，只做调度与评估
- 不改 skill 内部核心算法，只加适配层
- 保持 task_plan 字段名，节点名用 make_plan
```

---

## 6. 关键设计决策（避免 AI 整合时走弯路）

### 6.1 不要做的事

| 反模式 | 原因 |
|--------|------|
| 在 `execute.py` 里按业务写 if-else | 破坏可扩展性，应走 Registry |
| 状态字段命名为 `plan` | 与 LangGraph 节点名冲突，导致 plan 丢失 |
| Planner 直接拼复杂报告逻辑 | Planner 只选能力和参数，转换放在 skill 适配层 |
| 跳过 eval 直接 synthesize | 失去 retry/replan 闭环 |
| 三类能力共用一个 adapter | 协议不同，应分 mcp / skill / a2a 三个 client |

### 6.2 应该做的事

| 最佳实践 | 说明 |
|----------|------|
| 能力清单单一数据源 | `capabilities.yaml` → 生成/加载到 Registry |
| 统一错误格式 | `{status, error, output}` 便于 eval |
| 保留执行轨迹 | `step_results` + `eval_history` 用于调试和 A2A 流式推送 |
| 先通一条链路再扩展 | 1 个 MCP + 1 个 report + 1 个 opportunity，再批量注册 |
| 评估标准外置 | rubric 放 yaml，不散落在代码里 |

### 6.3 扩展方向（整合完成后再做）

1. **A2A Server 暴露**：把 `orchestrator/main.run_task` 包成 A2A endpoint。
2. **并行 step**：无依赖的 data fetch 用 LangGraph `Send` 并行。
3. **MCP 作为 Agent Card 注册中心**：参考 Google `a2a_mcp` sample。
4. **观测**：接入 LangSmith / MLflow 记录 trace 和 eval 分数。

---

## 7. 整合完成检查清单

- [ ] `skills/data_mcp/` 中每个 tool 都在 Registry 有对应 `capability_id`
- [ ] `skills/report/` 中每个 skill 有 `run.py` + `schema.json` + `SKILL.md`
- [ ] `skills/opportunity/` 的 Agent Card 可被 `a2a_client` 加载
- [ ] `mcp_client.py` 能真实调用至少一个 MCP tool
- [ ] `skill_runner.py` 能加载并执行至少一个 report skill
- [ ] `a2a_client.py` 能调用商机 agent 并返回结构化结果
- [ ] `evaluate.py` 能按 capability 应用 rubric
- [ ] `python -m orchestrator.main --real-llm` 端到端 `status=done`
- [ ] `eval_history` 中有 step 级和 final 级记录
- [ ] 失败场景能触发 retry 或 replan（至少手动测一次）

---

## 8. 文件改动速查表

| 文件 | 整合时是否必改 | 改动内容 |
|------|----------------|----------|
| `orchestrator/registry.py` | ✅ 必改 | 注册真实能力 |
| `orchestrator/tools/mcp_client.py` | ✅ 必改 | 接 MCP SDK |
| `orchestrator/tools/skill_runner.py` | ✅ 必改 | 动态加载 report skill |
| `orchestrator/tools/a2a_client.py` | ✅ 必改 | 接 a2a-sdk |
| `orchestrator/nodes/evaluate.py` | ⚠️ 建议改 | 加载 eval rubrics |
| `config/capabilities.yaml` | ⚠️ 建议新增 | 能力单一数据源 |
| `config/eval_rubrics.yaml` | ⚠️ 建议新增 | 评估标准外置 |
| `orchestrator/graph.py` | ❌ 少改 | 仅修 bug |
| `orchestrator/nodes/execute.py` | ❌ 少改 | 仅修 bug |
| `skills/**` 核心逻辑 | ❌ 少改 | 只加适配入口 |

---

## 9. 常见问题

**Q: Planner 选了不存在的 capability_id？**  
A: 检查 Registry 是否注册；检查 Planner prompt 中 `format_capabilities` 是否包含该能力。

**Q: step_2 拿不到 step_1 的输出？**  
A: 检查 plan 中 `data_sources: ["step_1"]` 的 step id 是否与 step_1 的 `id` 完全一致。

**Q: eval 一直 retry 但不 replan？**  
A: 检查 eval 返回的 `action` 字段；`retry_count` 达到 `max_retries` 后应 `failed`。

**Q: 真实 LLM 规划的 JSON 解析失败？**  
A: 项目已有 `llm_client.parse_json_loose`，确保 plan/analyze 节点使用它。

**Q: 三类 skill 能否都暴露成 MCP？**  
A: 可以。统一 `type=mcp` 即可，但 report / opportunity 若已是 Python 模块或 A2A，用对应 adapter 更直接。

---

## 10. 参考：当前骨架中的关键入口

| 入口 | 路径 | 作用 |
|------|------|------|
| 图组装 | `orchestrator/graph.py` | LangGraph 状态机 |
| 能力注册 | `orchestrator/registry.py` | Planner 的能力菜单 |
| 执行分发 | `orchestrator/nodes/execute.py` | 按 type 调三个 client |
| 参数解析 | `orchestrator/utils.py` | 前序 step 输出引用 |
| CLI 演示 | `orchestrator/main.py` | 本地跑通入口 |
| 使用说明 | `orchestrator/README.md` | 骨架快速开始 |

---

*文档版本：v1.0 | 适用于 orchestrator 骨架 + 三类 Skill 本地整合*
