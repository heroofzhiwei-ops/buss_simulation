# LangGraph Task Planner / Eval Orchestrator

基于 LangGraph 的商机分析编排骨架，实现：

`A2A 请求 → Query 分析 → 计划生成 → 逐步执行 → 实时 Eval → 不满足则重试/重规划 → 最终汇总`

## 快速开始

```bash
# 1. 安装 orchestrator 依赖
pip install -r orchestrator/requirements.txt

# 2. 运行 demo（无需 LLM_API_KEY，使用 mock LLM + mock MCP/Skill/A2A）
python -m orchestrator.main

# 3. 自定义 query
python -m orchestrator.main --query "分析淘宝京东 XX 品牌竞品并判断商机"

# 4. 使用真实 LLM（复用项目根目录 .env 中的 LLM_API_KEY）
python -m orchestrator.main --real-llm --query "你的请求"
```

## 目录结构

```text
orchestrator/
├── state.py              # 全局状态 + Step/Eval 数据结构
├── registry.py           # MCP / Skill / A2A 能力注册表
├── llm.py                # LLM 适配层（mock / 项目 llm_client）
├── graph.py              # LangGraph 图组装
├── main.py               # CLI 入口
├── nodes/
│   ├── analyze.py        # Query 分析
│   ├── plan.py           # 生成 step 计划
│   ├── execute.py        # 执行当前 step
│   ├── evaluate.py       # step / final eval
│   ├── replan.py         # 根据 eval 反馈重规划
│   └── synthesize.py     # 汇总最终结果
└── tools/
    ├── mcp_client.py     # MCP 调用（当前为 mock）
    ├── skill_runner.py   # Skill 调用（当前为 mock）
    └── a2a_client.py     # A2A 子 agent 调用（当前为 mock）
```

## 控制流

```text
analyze → make_plan → execute → evaluate
                ↑    ↓ retry
                └── replan
evaluate → advance_step → execute (下一步)
evaluate → final_evaluate → synthesize → END
evaluate / final_evaluate → mark_failed → END
```

## 对接现有系统

1. **Data MCP**：在 `tools/mcp_client.py` 替换为真实 MCP SDK 调用
2. **Report Skills**：在 `tools/skill_runner.py` 对接现有 skill 执行器
3. **商机 Agent**：在 `tools/a2a_client.py` 使用 `a2a-sdk` 调用子 agent
4. **能力注册**：在 `registry.py` 补充真实 MCP tool schema 和 Agent Card

## A2A 集成建议

- `contextId` 映射到 LangGraph `thread_id`，支持断点续跑
- `main.run_task()` 的 stream 输出可直接转为 A2A SSE 事件
- Orchestrator 自身可暴露为 A2A Server，Agent Card 声明 `planning` / `evaluation` 能力
