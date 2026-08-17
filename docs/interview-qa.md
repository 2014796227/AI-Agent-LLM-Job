# 面试 Q&A 准备（M6 · 2026-08-17）

> 用法：每个关键词下是「面试官最可能追问的问题 + 你的回答要点 + 代码/文档出处」。回答锚点（点到即止的深挖邀请）加粗。

## 1. 为什么自研编排内核而不用 LangGraph/CrewAI？（ADR-0001）

要点：①过程透明是产品需求（时间线要求每个事件先落库再推送，框架内部状态不暴露）；②AI 编码+人工验收的工作流下，黑盒框架放大定位成本——**本项目实测：历轮真实执行暴露 15+ 缺陷全部定位到行并修复**；③面试叙事本身就是选型证明。若迁移：AgentSpec/事件 schema 可平移。
出处：ADR-0001、蓝图 Part 3。

## 2. Multi-Agent 怎么协作？黑板是什么？

Supervisor 生成 DAG（≤6 节点，research/strategy/writer）→ 串行拓扑序执行 → 下游拿上游结论摘要（黑板 `_digest`）→ writer 成稿 → critic ≤2 轮 revise → 终态。**注意每层防御**：规划 JSON 一次纠错重试、critic 解析失败 fail-open 独立计数、writer 空输出有降级拼装（PM-001 修复）。
出处：orchestrator.py、PM-001。

## 3. 断线重连为什么不丢事件？

核心：**事件先 INSERT（bigserial 兼作 SSE 事件号）再推订阅队列**；SSE 三段式（急切订阅→回放 after 之后→实时按 seq 去重）；慢消费者队列有界→溢出标记→stream_overflow→客户端携 after 重连回放——**最终不丢，只降实时性**。心跳由内层 poll 产生 keep_alive（v16 修过外层超时摧毁生成器的自毁 bug）。
出处：events.py、test_events_replay.py 六剧本。

## 4. guarded finish 和租约是什么关系？（最常深挖）

崩溃一致性三件套：CAS 抢占（pending→running）+ 租约心跳（60s+watchdog 宽限 90s）+ **guarded finish（WHERE status='running' AND worker=本人）**。规则：**释放权唯一归状态迁移方**——编排器 finish 成功才释放预留；watchdog/recover 中断迁移时释放；取消路径不释放（由 watchdog→重启恢复链兜底）。迟到的 finish 不覆盖 interrupted，只记 M_TASK_CONF。v18 还修过对账双重释放（upsert 整列重置×残留释放循环）。
出处：tasks.py、ADR-0008、M0-记录 §5.3（演练含重启对账断言）。

## 5. 预算怎么做到"击穿前 429"？

**预留式**：POST /api/chat 先 reserve_daily（单语句 ON CONFLICT 行锁串行化，无应用层事务）预留 120k，完成时 release 归还+记实际消耗；评测路径走 create 不占预留（口径显式声明）。单任务双层：DAG/LLM/工具/token/墙钟熔断→**降级为带标注部分结果**而非失败。
出处：tasks.py reserve_daily、ADR-0002、PM-001 展示了降级实况。

## 6. 回测怎么防未来函数？

三件事：①**fill→shift 显式契约**（next_close=shift(2)，T 信号 T+1 收盘成交）；②信号全链路后复权（除权跳空不造假信号，展示层才映射不复权）；③语义契约单测固化（hhv 不含当日、exit 优先、RSI 横盘=50）。**可复现三元组 {spec, 数据工件, 引擎}，终版评测复算 10/10（1e-9）**。诚实边界：向量化近似，不建模涨跌停/停牌——方向性影响在 ADR-0004 写明。
出处：backtest.py、dsl.py、ADR-0004/0007、docs/eval/results.md。

## 7. RAG 的引用为什么可信？

**不跨页切块**（页码永远准，单测固化）→ 页级引用 [[doc#页码]] → 前端点击渲染原 PDF 页（doc_page 端点）。语料 100% 标注来源：年报=官方公开文件，方法论=AI 初稿+本人逐条审核（120 条全过）。**评测 cite 15/17**，未命中 2 例沉淀回归。 embedding 维度治理：探针+双侧断言+三层回退（智谱 e3→e2→硅基 bge-m3），查询级降级明示+独立计数。
出处：rag.py、ADR-0005、M4-验收报告。

## 8. 评测体系怎么设计的？

三层：确定性断言（工具轨迹/spec 结构比对/三元组复算/引用命中——**全自动不掺 LLM**）→ LLM-as-judge（免费裁判，辅助不替代——终版 True15/False24，解析不稳如实记录）→ 人工抽查。报告 100% 脚本生成（commit+时间戳+八列），人工只允许末尾追加结论。46 用例含**正确拒绝类**（拒绝=通过）。评测基础设施本身踩过的坑（静默终止→断点续跑→非法 spec 崩溃→看门狗自匹配）全部留痕 v28~v31——可当 SRE 素材讲。
出处：评测说明、run_eval.py、M5-验收报告。

## 9. 讲一个真实事故（必考）

PM-001（用户线上反馈）：任务 done 但报告为空。5-Why 到机制层：东财限流→无数据→critic 连续打回→**writer 空 content 无防御**→空报告静默入库。修复=机制性保证（空修订保留原稿/全程空则黑板拼降级报告）。教训：静态审查两轮没抓到，**四条件叠加的真实路径只有真实执行才暴露**；M0 起全部验收先跑真。
出处：docs/postmortem/PM-001、Issue #7。

## 10. 免费运行模式是什么？（会被问"为什么不全用最好的模型"）

约束驱动的真实工程：coding-plan 型 key 余额受限（4.6 间歇 1113、embedding 持续 1113、flash 免费稳定）→ env 覆盖全量 flash + 墙钟 600s + 重试 4×(2s/4s/8s) 吸收 429-1305；embedding 引入硅基免费 bge-m3 补齐 RAG。**代价如实声明**（任务 6~11 分钟、refusal 边界 5/8、裁判不稳），充值即回标准分工——架构上这叫"降级路径也是产品"。
出处：ADR-0002 后记、M0-记录 §3.6。

## 11. 部署与数据安全？

单机 Compose 三容器（ADR-006，多实例需 Redis 化的边界声明）；备份顺序推导（**先 dump 后 tar ⇒ 恢复集零悬空在数学上不可能违反**——生产真跑对账 7/7）；每日 04:00 cron；工件 tmp→fsync→os.replace 原子写；.env 双 ignore（git+docker，曾修过 COPY 烤密钥进镜像的隐患）；nginx admin/metrics 双 403 + 回环。
出处：ADR-0006、M2/M5 验收报告。

## 12. 你的角色？（如实口径，别说过头）

本人：需求定义与 PRD 拍板、八项技术选型决策（ADR 决策人）、验收与复盘主持、语料策展与逐条审核；代码由 AI 编码助手按蓝图实现、本人过程监督与验收。**"用 AI Agent 工作流交付 Agent 产品"本身是岗位能力的证明**；每项贡献可回指文档/issue/提交。
出处：provenance.md §二。

## 高频追问速查

- SSE 与 WebSocket 取舍？→ 单向推送+浏览器原生重连+Last-Event-ID 回放，够用且少一层状态。
- 为什么 pgvector 不用专用向量库？→ 生产一致性（同库事务：摄取 DELETE+INSERT 原子）+规模<1万 chunk，HNSW 已启用。
- 工件 TTL 与复现矛盾？→ 7 天内事件级复现，之外靠评测报告+备份（ADR-0008 边界）。
- 下一步 roadmap？→ Supervisor 拒绝边界加固（Issue #2）、数据源预热/换源（#1）、并行 DAG（ADR-0001 P2）。
