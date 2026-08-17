# AlphaDesk · 量化投研 Multi-Agent 工作台

> **项目性质声明**：个人求职作品。**模拟量化私募内部 AI 投研工具的生产形态**——架构、组件选型、工程流程按生产标准取舍（ADR 记录），但它是单机演示部署，**不是真实生产系统，不是合规投研终端**。数据与输出仅供研究演示，**不构成投资建议**。

## 能做什么

1. 自然语言研究需求 → Supervisor 分解 → 多 Agent 协作（research/strategy/writer + critic 反思回路）→ 带图表与引用的投研报告（数据来自 AKShare 真实历史行情）；跨任务标的记忆（Memory：按标的存最近分析摘要，规划时注入背景参考）
2. 白名单内策略（双均线交叉/动量阈值/N日新高新低突破/RSI 超买超卖及其布尔组合，单标的，仅做多）→ DSL 结构化 → 确定性编译 → 向量化回测（净值曲线 + 指标，带假设边界脚注）
3. 内置知识库问答（公开披露文件 + 策展方法论库），答案带**可定位到原 PDF 页**的引用
4. 每次任务展示完整 Agent 执行轨迹（断线/刷新可完整重建），凭 trace_id 可复现
5. 一键评测跑分与版本效果对比（脚本生成制报告）

## 不能做什么（明示边界）

- 不能实盘交易、不对接下单通道、无实时盘中行情（收盘后批处理口径）
- 不能保证数据达到生产级准确性与一致性（免费数据源，有质量校验但无 SLA）
- 不输出合规意义的投资建议
- 不支持账号体系与多用户高并发（访客模式 + IP 限流 + 每日/单任务双层 token 预算熔断）
- 白名单之外（机器学习预测/多标的/网格/套利等）明确拒绝，不伪造结果
- 不支持扫描版 PDF OCR、不执行 LLM 生成的任意代码
- 回测为向量化近似（成交价/可交易性假设见 ADR-0004），不替代事件驱动引擎

## 当前状态

**已上线：http://43.156.248.38**（新加坡腾讯云轻量，单机 Compose 三容器）。**全部里程碑完成（2026-08-17）**：M0 事实核验（29 单测/真实链路端到端，15+ 项实测缺陷修复留痕）→ M1 GitHub+CI（Actions 全绿）→ M2/M3 上线+Multi-Agent 内核（评测复算 10/10 全真）→ M4 知识库（年报节选×3+方法论 120 条经本人审核；引用可点开原页）→ M5 评测与加固（46 用例 0 失败：cite 15/17、备份链演练+每日 cron、限流验证）→ M6 收尾（真实复盘 PM-001、ADR 八篇终审、架构图、演示脚本、面试 Q&A）。免费运行模式（LLM=flash 免费层，embedding=硅基 bge-m3）；架构/边界如实声明见 `docs/architecture.md`。

里程碑：M0 ✅ → M1 ✅ → M2/M3 ✅ → M4 ✅ → M5 ✅ → M6 ✅。M2 前本 README 如实描述为"单 Agent 阶段"。

## 技术栈（纯智谱 GLM 单厂商）

GLM-4.6（规划/撰写/审查）+ GLM-4.7-Flash（免费：工具调用/摘要/评测裁判）+ embedding 三层回退链（智谱 embedding-3→embedding-2→硅基 bge-m3，均 1024 维探针校验）· FastAPI(async) · PostgreSQL 16 + pgvector · 自研轻量 Multi-Agent 编排内核 · React+Vite+TS+ECharts · Docker Compose 三容器。

## 快速开始（本地开发）

```bash
# 后端（Python 3.11 venv）
cd backend && python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env   # 填入 ZHIPU_API_KEY
pytest                 # 单测（M0 验收项）

# 前端（Node 20+）
cd frontend && npm install && npm run dev   # Vite 代理 /api → :8000
```

## 文件索引

见 `docs/FILE-MANIFEST.md`（逐文件审查地图）。架构契约与全部核心代码：`docs/BLUEPRINT.md`。选型决策：`docs/adr/`。

## 贡献与真实性声明

本人负责：产品需求定义（`docs/PRD.md`）、技术选型决策（`docs/adr/`，决策人署名）、质量验收（`docs/acceptance/`）、复盘主持（`docs/postmortem/`，只记录真实发生的事故）、知识库语料策展。代码由 AI 编码助手按蓝图实现，本人做需求拆解、过程监督与验收测试——如实呈现，不写"独立开发"。

---
*研究演示用途，非投资建议 · 数据来自公开免费源（AKShare）· 回测为向量化近似*
