# 求职介绍语 v2（2026-08-17 · 含 v36 数据溯源能力 · 依据真实项目状态撰写，未夸大）

> 仓库 PUBLIC ✅、线上 demo 200 ✅。链接放简历时建议：`demo: http://43.156.248.38 · code: github.com/2014796227/AI-Agent-LLM-Job`

## 一、HR 版（简历项目栏/招聘平台作品介绍，~120 字）

**AlphaDesk · 量化投研 AI Agent 工作台**（个人作品，已上线可试用）

输入一句自然语言（如"分析贵州茅台近三年走势并回测均线策略"），AI 自动规划任务、多智能体协作调取真实行情数据、执行策略回测、生成带图表与**可点击原文引用**的投研报告，全过程时间线可视化、可回放。系统覆盖大模型应用开发全链路（多智能体编排、RAG 知识库、工具调用、评测体系），已部署上线并配有完整架构文档与自动化测试。匹配 **AI Agent / 大模型应用开发** 岗位。

*（如平台有标签栏可加：LangChain-free 自研编排 · Function Calling · RAG · 向量检索 · FastAPI · Docker）*

## 二、技术面试官版（项目自述/简历技术描述，~300 字）

**AlphaDesk · 量化投研 Multi-Agent 工作台**（线上 demo + 开源，Docker Compose 三容器：FastAPI 异步 + PostgreSQL16/pgvector + React/ECharts，GitHub Actions CI）

- **自研编排内核（约 2k 行，ADR 记录取舍不用 LangGraph）**：Supervisor DAG 规划（≤6 节点）→ research/strategy/writer + critic 反思回路；任务状态机 CAS 抢占 + 租约心跳 + watchdog，**guarded finish 保证崩溃一致性**（迟到 finish 不覆盖 interrupted、预留释放权唯一）；双层 token 预算：单任务五维熔断降级为带标注部分结果、日预算预留式击穿前 429。
- **确定性回测**：LLM 仅把自然语言策略翻译为 pydantic 严格 Schema 的白名单 DSL（无 eval/exec），向量化引擎 hfq 全链路 + fill→shift 契约防未来函数；**评测三元组本地复算 10/10 全真（1e-9 容差）**。
- **RAG 页级可信引用**：不跨页切块 → `[[doc#页]]` 引用前端可点击渲染原 PDF 页；embedding 三层回退链（智谱 e3→e2→硅基 bge-m3，1024 维探针校验）+ HNSW；引用断言命中 15/17。
- **事件溯源与可观测**：task_events 先落库再推 SSE（bigserial 兼作事件号），断线 Last-Event-ID 回放不丢事件；结构化日志 + trace_id 贯穿 + Prometheus 十余指标。
- **质量与工程文化**：46 用例三层评测（确定性断言/LLM 裁判/人工）100% 脚本生成制报告；29 单测；真实生产事故复盘（PM-001）与 15+ 缺陷"验证驱动修复"全留痕（蓝图 v4→v31 版本史即过程证据）；备份链生产演练零悬空 + 每日 cron。

**角色如实**：本人负责需求定义与 PRD 拍板、八项技术选型决策（ADR 决策人）、验收与复盘主持、知识库语料策展审核；代码由 AI 编码助手按本人蓝图实现——**"用 AI Agent 工作流交付 Agent 产品"本身就是这个岗位工作方式的证明**。

## 三、简历极简版（一行项目描述，备用）

量化投研 Multi-Agent 工作台（已上线）：自研 DAG 编排内核 + 白名单 DSL 确定性回测（评测复算 10/10）+ 页级可验证 RAG + 事件溯源 SSE，46 用例三层评测 0 失败，Docker/CI 全链路工程化。

## 四、投递使用提醒（本人）

1. **附两个链接**：demo + GitHub（仓库已 PUBLIC）
2. **提前 2 分钟打开 demo 预热**；免费模式任务约 5~7 分钟——HR 初筛只看页面与报告样式即可，不必等任务跑完；技术面按 `docs/demo-script.md` 演示
3. 角色口径全链路一致（README/provenance/面试 Q&A §12 已对齐），不写"独立开发"
4. 技术面深挖准备：`docs/interview-qa.md`（12 主题）
