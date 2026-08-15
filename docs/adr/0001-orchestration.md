# ADR-0001：自研轻量 Multi-Agent 编排内核（不使用 LangGraph/CrewAI）

- 状态：已接受（蓝图 v6 起）
- 日期：2026-08-15
- 决策人：＿＿＿＿（待签名）
- 关联：蓝图 Part 3（events/agents/agent_loop/orchestrator）；第五轮评审

## 背景

系统需要 Multi-Agent 协作（Supervisor 规划 + research/strategy/writer 专家 + critic 反思回路），候选人框架有 LangGraph、CrewAI、AutoGen 等。

## 备选方案

1. **LangGraph**：行业标准关键词，图编排/状态管理/持久化内置
2. **CrewAI / AutoGen**：开箱即用的多 Agent 协作
3. **自研轻量内核**（AgentSpec 声明式定义 + BaseAgent 循环 + Supervisor DAG + TaskContext 黑板）

## 决策

选 3：自研轻量内核（核心约 2~3 千行，见蓝图 orchestrator/agent_loop）。

## 理由

1. **每一行都能讲清原理**：面试深挖"你的多 Agent 怎么协作"时，回答到事件总线、guarded finish、租约恢复这一层，而非框架配置层
2. **调试与修复可控**：开发方式是 AI 编码 + 本人验收，黑盒框架会放大"出问题难定位"的成本（历轮评审证明：自研代码的每个缺陷都能被逐行审计并修复）
3. **过程透明是产品需求**："Agent 执行时间线可视化"要求每个事件先落库再推送——框架的内部状态不暴露这些
4. ADR 本身即面试叙事："为什么不用 LangGraph"比"用了 LangGraph"更能证明选型能力

## 后果与妥协

- 失去框架生态（现成 checkpoint/重放/并发图执行）；v1 以串行拓扑执行（并行=P2），TaskContext 黑板 + 事件日志承担 checkpoint 职责
- 需自建：预算熔断、租约、事件持久化、断线重连——全部已在蓝图实现并有单测
- 若未来迁移 LangGraph：AgentSpec/事件 schema 可平移，迁移成本可控
