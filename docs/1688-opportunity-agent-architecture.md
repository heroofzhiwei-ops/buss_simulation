# 1688 商机 Agent 技术架构图

> 基于 [INTEGRATION_GUIDE.md](../INTEGRATION_GUIDE.md) 与编排层设计整理。  
> 核心思路：**LangGraph 编排骨架 + 独立 Skill 仓库 + 统一能力注册表**。

---

## 总览架构图

![1688 商机 Agent 技术架构](./assets/1688-opportunity-agent-architecture.png)

---

## Mermaid 源图（可编辑）

```mermaid
flowchart TB
    subgraph Entry["接入层"]
        User["用户 / A2A Gateway"]
    end

    subgraph Orchestrator["编排层 · LangGraph Orchestrator<br/>BussAgent/orchestrator/"]
        direction TB
        Analyze["analyze<br/>意图分析 (LLM)"]
        MakePlan["make_plan"]
        Execute["execute<br/>分步执行"]
        EvalStep["evaluate<br/>step 评估"]
        Advance["advance_step"]
        Retry["prepare_retry"]
        Replan["replan"]
        FinalEval["final_evaluate"]
        Synthesize["synthesize<br/>汇总输出"]

        Analyze --> MakePlan --> Execute --> EvalStep
        EvalStep -->|continue| Advance --> Execute
        EvalStep -->|retry| Retry --> Execute
        EvalStep -->|replan| Replan --> MakePlan
        EvalStep -->|all done| FinalEval
        FinalEval -->|passed| Synthesize
        FinalEval -->|failed| Replan
    end

    subgraph OrchestrationSkills["编排类 Skill（独立 Git）"]
        Planner["Task Planner<br/>1688-opportunity-orchestration<br/>CLI: task-planner"]
        Evaluator["Task Evaluator<br/>1688-opportunity-eval<br/>CLI: task-evaluator"]
    end

    subgraph Registry["能力注册表"]
        CapReg[("config/capabilities.yaml")]
        Rubrics[("config/eval_rubrics.yaml")]
    end

    subgraph BusinessSkills["业务类 Skill（各自 Git）"]
        direction LR
        MCP["A 类 Data MCP<br/>1688-opportunity-opportunity<br/>8 个数据工具"]
        Report["B 类 Report Skill<br/>business-opp-inspiration<br/>趋势报告"]
        Agent["C 类 Opportunity Agent<br/>personalized-opportunity<br/>个性化商机"]
    end

    subgraph External["外部依赖"]
        LLM["LLM<br/>DashScope / qwen-plus"]
        Gateway["1688 Gateway API<br/>ALI_1688_AK"]
    end

    User --> Analyze
    Synthesize --> User

    MakePlan -.-> Planner
    Replan -.-> Planner
    Planner -.-> CapReg

    EvalStep -.-> Evaluator
    FinalEval -.-> Evaluator
    Evaluator -.-> Rubrics

    Execute --> MCP
    Execute --> Report
    Execute --> Agent

    MCP --> Gateway
    Report --> Gateway
    Agent --> Gateway

    Analyze -.-> LLM
    Planner -.-> LLM
    Evaluator -.-> LLM
    Synthesize -.-> LLM

    classDef orchestrator fill:#e8f4fc,stroke:#2563eb,stroke-width:2px
    classDef skill fill:#f0fdf4,stroke:#16a34a,stroke-width:2px
    classDef registry fill:#fef9c3,stroke:#ca8a04,stroke-width:2px
    classDef external fill:#f3f4f6,stroke:#6b7280,stroke-width:2px

    class Analyze,MakePlan,Execute,EvalStep,Advance,Retry,Replan,FinalEval,Synthesize orchestrator
    class Planner,Evaluator,MCP,Report,Agent skill
    class CapReg,Rubrics registry
    class LLM,Gateway external
```

**图例**：
- **实线箭头**：运行时调用 / 数据流
- **虚线箭头**：配置依赖 / Skill 委托

---

## 系统分层（自上而下）

```text
┌─────────────────────────────────────────────────────────┐
│  用户 / A2A Gateway（未来）                               │
│  输入：自然语言 query                                     │
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│  编排层 Orchestrator（LangGraph StateGraph）               │
│  本地整合项目：BussAgent/orchestrator/                    │
│  职责：状态机、路由、调用各类 Skill、汇总结果              │
└───────┬───────────────┬───────────────┬─────────────────┘
        │               │               │
        ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐
│ 编排类 Skill  │ │ 编排类 Skill  │ │  业务类 Skill         │
│ Task Planner │ │ Task Evaluator│ │  A / B / C 三类       │
│ (独立 Git)   │ │ (独立 Git)    │ │  (各自 Git 仓库)      │
└──────────────┘ └──────────────┘ └──────────────────────┘
        │               │               │
        └───────────────┴───────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────┐
│  外部依赖                                                 │
│  - LLM（DashScope / qwen-plus）                          │
│  - 1688 网关 AK（ALI_1688_AK）                           │
└─────────────────────────────────────────────────────────┘
```

---

## 编排层控制流

```text
用户 query
    │
    ▼
[analyze] ──► intent（required_tags、suggested_capabilities）
    │
    ▼
[make_plan] ──► Task Planner Skill ──► task_plan（steps[]）
    │
    ▼
[execute] ──► A/B/C 业务 Skill（按 capability_id 路由）
    │
    ▼
[evaluate] ──► Task Evaluator Skill（step 模式）
    │
    ├── continue ──► advance_step ──► execute（下一步）
    ├── retry    ──► prepare_retry ─► execute（重试）
    ├── replan   ──► replan ────────► Task Planner（replan 模式）
    └── 全部完成 ──► final_evaluate ─► Task Evaluator（final 模式）
                            │
              passed ──────► synthesize ──► 最终回答
              failed ──────► replan / mark_failed
```

---

## 仓库与部署关系

```text
                    ┌─────────────────────┐
                    │   BussAgent（本地）  │
                    │   完整整合 + E2E     │
                    └──────────┬──────────┘
                               │ 引用
         ┌─────────────────────┼─────────────────────┐
         ▼                     ▼                     ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐
│ orchestration   │  │ eval            │  │ 业务 Skill 仓库群    │
│ task-planner    │  │ task-evaluator  │  │ opportunity (MCP)   │
│                 │  │                 │  │ inspiration (报告)  │
│                 │  │                 │  │ personalized (Agent)│
└─────────────────┘  └─────────────────┘  └─────────────────────┘
```

---

## 典型链路示例

**用户**：「分析帽子品类趋势并判断有没有商机」

| 步骤 | 节点 / Skill | 说明 |
|------|--------------|------|
| 1 | analyze | intent: required_tags=[report, trend, business] |
| 2 | task-planner | step_1: opp_cate_understand；step_2: business_opp_inspiration；step_3: personalized_opportunity |
| 3–4 | execute + evaluator | 类目理解 → passed |
| 5–6 | execute + evaluator | 生意灵感报告 → rubric 检查 |
| 7–8 | execute + evaluator | 个性化商机评分 → 阈值检查 |
| 9–10 | final_evaluate + synthesize | 终评 → 自然语言回答 |

---

## 关键状态字段

| 字段 | 含义 |
|------|------|
| `query` | 用户原始请求 |
| `intent` | 意图分析结果 |
| `task_plan` | 多步执行计划 |
| `current_step_idx` | 当前执行到第几步 |
| `step_results` | 每步执行结果 |
| `eval_history` | 评估历史 |
| `final_output` | 最终汇总输出 |
