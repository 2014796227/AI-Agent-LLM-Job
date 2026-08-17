# ADR-0008：ArtifactStore 句柄化数据流与事件日志单一事实源

- 状态：已接受
- 日期：2026-08-15
- 决策人：＿＿＿＿（待签名）
- 关联：蓝图 artifacts.py / events.py / tasks.py(guarded finish)；第二、五、七轮评审

## 决策 1：LLM 上下文只含句柄+摘要（ArtifactStore）

工具间大块数据（行情/回测结果）经服务端工件仓库按 artifact_id 流转；LLM 只见 {artifact_id, rows, stats, preview}。解决的问题（第二轮评审 P0）：数据工具返回 30 行摘要则回测无数据，返回 3 年日线则上下文爆炸。收益：上下文恒定小、回测数据完整、trace→artifact→结果全链可复现。配套端点：前端图表按 artifact_id 直拉曲线（不过 LLM）。

## 决策 2：事件先落库后推送；task_events 为单一事实源

每事件先 INSERT（id=全局 bigserial，兼作 SSE 事件号）再推订阅队列。断线/刷新=Last-Event-ID/`?after` 回放重建时间线；评测 trace 断言、Critic 审查依据、复盘证据全部取自该表。订阅队列有界（溢出→stream_overflow→客户端重连回放，最终不丢）。

## 决策 3：终态顺序 = guarded finish 成功 → 再 emit 终态事件

- guarded finish（WHERE status='running' AND worker_id=本人）：迟到的执行协程**不能覆盖** watchdog 写入的 interrupted（第七轮评审 P0-2）
- finish 失败（状态已被迁移）→ 跳过终态事件与预留释放（迁移方已做）→ M_TASK_CONF 计数
- 顺序取 finish→emit 而非反向（v12 曾用反向）：回放段"已见终态事件→立即返回"使两序等价终止，但 finish→emit 消除"emit 已发而 finish 冲突"的矛盾事件；毫秒级间隙由 replay 双源终态判定（事件∨状态）兜底，均有单测
- 预留释放权随之唯一化：**完成状态迁移的一方释放**（编排器仅 finish 成功后；watchdog/recover 在中断迁移时；取消路径不释放，由 watchdog→启动恢复链兜底）——机制上杜绝双重释放

## 后果与妥协

- 事件表随任务 TTL 清理（默认 7 天）：复现窗口=7 天内，之外依赖评测报告与日志归档
- 慢消费者场景丢弃实时性换内存安全（事件已落库，回放可补）——/metrics bus_dropped 可观测
## 后记（2026-08-17 终审）

事件单一事实源在断线重连（Last-Event-ID 回放）、公网 SSE（nginx 不缓冲，41 事件实证）、评测断言（46 用例全部基于 task_events 复核）、PM-001 复盘（事件级重放定位）四条链路经受住生产验证；工件原子写+备份零悬空对账成立。pagecache 有界性（v17 F-1）维持。
