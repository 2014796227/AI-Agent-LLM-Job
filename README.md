# AlphaDesk · 可信的 AI 投研助手（多 Agent LLM 应用系统）

> **一句话定义**：多 Agent 协作的投研报告生成系统——一句话提问，DAG 规划调度 research / strategy / writer 三个 Agent 并经 critic 审查回路，产出带**可核查证据链**（数据溯源 + 页级引用 + 确定性回测）的研究报告。
>
> **求职方向**：AI 应用开发（Python / LLM 应用工程）。本仓库为个人作品：**系统架构与技术决策本人负责**（8 篇 ADR 决策人、工程蓝图作者），编码由 AI 结对完成、本人联调验收——「AI 协作工程工作流」本身就是本作品的方法论。

## 技术栈速览

`Python 3.11` · `FastAPI` · `PostgreSQL 16 + pgvector(HNSW)` · `自研 Multi-Agent 编排` · `RAG（页级引用 + 三层回退）` · `事件溯源 + SSE` · `双层 Token 预算/限流降级` · `pytest 32 用例 + 46 例评测集` · `Docker Compose` · `GitHub Actions CI`

## 核心工程能力（AI 应用开发视角）

| 模块 | 实现要点 |
|---|---|
| **Multi-Agent 编排内核** | Supervisor 生成 DAG 计划（Pydantic 校验 + 拒答分支）→ 拓扑排序执行 → 黑板上下文传递；critic 审查回路 ≤2 轮修订，解析失败 fail-open 独立计数防死循环 |
| **工具调用安全** | 4 工具白名单按 Agent 分配；**工件句柄化**——LLM 仅接触 artifact_id + 摘要，全量数据服务端流转，token 可控且防注入 |
| **RAG 页级引用** | PDF 不跨页切块（引用可定位到原 PDF 页）→ pgvector/HNSW 检索；embedding 三层回退链（探针选层），查询失败自动降级 BM25（CJK 二元组） |
| **确定性回测** | 白名单策略 DSL（精确 JSON Schema）+ pandas 向量化计算；评测三元组复算 **10/10 全真（误差 <1e-9）**，LLM 不参与数值计算 |
| **可靠性工程** | 任务租约 + 心跳续租 + guarded finish(CAS) + 崩溃恢复；429 限流分级退避（5s/15s/30s）；双层预算（单任务 + 全局日限）；失败如实报告 + 降级部分结果兜底 |
| **可观测** | 事件溯源（task_events bigserial）+ SSE 断线 Last-Event-ID 回放；Prometheus 指标（token/预算降级/finish 冲突）；IP 滑窗限流 |

## 产品功能

1. **一句话投研报告**：多 Agent 协作生成带图表与引用的报告，执行时间线实时可见、断线回放
2. **白名单策略回测**：自然语言策略 → 净值曲线 + 指标 + 假设边界脚注（白名单外明确拒绝）
3. **可溯源知识库问答**：引用 `[[doc#页]]` 点击渲染官方年报原 PDF 页；120 条人工审核方法论库
4. **数据溯源面板**：行情标注来源/行数/拉取时间，可用任意行情 App 当场核对
5. **失败可解释**：失败原因分类 + 应对建议 + 带标注的部分结果

完整产品定义（用户/痛点/优先级/边界/埋点）见 `docs/pm/产品文档.md`——工程与产品双视角是本作品的特色。

## 质量与过程证据

- **46 例评测集 0 失败**（backtest/rag/refuse/report 四类，`docs/eval/`），pytest 32 用例
- **37 个版本 git 演进史** + 8 篇 ADR + 真实 postmortem + 上线验收记录（`docs/acceptance/`）
- 上线后由真实用户反馈触发 6 轮修复增强（v32→v37），每次含定位/修复/线上验证/留痕

## 快速开始（本地运行）

```bash
# 后端（Python 3.11 venv）
cd backend && python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env   # 填入 ZHIPU_API_KEY
pytest

# 前端（Node 20+）
cd frontend && npm install && npm run dev   # Vite 代理 /api → :8000

# 或 Docker Compose（db + api + web）
cd deploy && docker compose up -d
```

## 明示边界

不构成投资建议；不能实盘交易；回测为历史模拟；免费数据源无 SLA（已做双源回退）；**AI 会错**——数字可核查 ≠ 结论正确，请批判使用。

## 文档索引

`docs/BLUEPRINT.md`（工程权威，4052 行）· `docs/architecture.md`（架构图）· `docs/adr/` ×8（技术决策）· `docs/pm/产品文档.md` + `docs/PRD.md`（产品视角）· `docs/eval/results.md`（评测报告）· `docs/acceptance/`（验收）· `docs/postmortem/`（复盘）

## 真实性声明

本人负责：系统架构设计、全部技术选型决策（ADR 决策人）、工程蓝图、验收标准与质量把关、评测体系设计、badcase 定位与修复方向、知识库语料策展；编码由 AI 结对完成。项目如实呈现「AI 协作工程」工作流，不宣称纯手写。

---
*研究演示用途，非投资建议 · 行情：东方财富/腾讯财经（AKShare 公开接口）· 知识库：巨潮资讯网官方年报 · 回测为向量化近似*
