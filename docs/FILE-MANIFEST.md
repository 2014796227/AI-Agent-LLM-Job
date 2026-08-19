# 文件清单与审查地图（FILE-MANIFEST）

> 用途：逐文件审查的索引。每个文件标注用途、来源（蓝图章节或"新增"）、审查要点。
> 蓝图本体：`docs/BLUEPRINT.md`（v20，全部代码的唯一权威来源；本清单中"蓝图§"指其章节）。
> 新增文件=蓝图未含但工程必需或文档体系所需，均已在此声明。
> v19/v20（M0 落仓与端到端补验轮）新增的执行性文件见 §六 末"v19/v20 新增"块——演练脚本可复现 M0 记录中的全部证据。

## 一、根目录

| 文件 | 用途 | 来源 | 审查要点 |
|---|---|---|---|
| `README.md` | 项目门面：性质声明/能做不能做/快速开始 | 新增（内容取自蓝图 Part 0） | 表述与蓝图 Part 0 一致 |
| `.gitignore` | 忽略 venv/缓存/env/数据卷 | 新增 | 确认 evals/fixtures 不被忽略 |

## 二、docs/（文档体系）

| 文件 | 用途 | 来源 | 审查要点 |
|---|---|---|---|
| `docs/BLUEPRINT.md` | 全量工程代码与架构契约（唯一权威） | 历次评审演化至 v20（M0 落仓+端到端补验轮） | 已多轮评审+M0 实跑；关注版本记录 |
| `docs/verification/v17-审查报告.md` | v16→v17 静态逐行审查：P0×1/P1×4/P2×3/P3×10+设计确认+误报归档 | 新增（v17 修订依据） | 分级明细与修复落点索引 |
| `docs/verification/v18-审查报告.md` | v17→v18 独立逐行复核：P1×1/P2×1/P3×6+设计确认 D-5+内容钉死×5 | 新增（v18 修订依据） | 数字推演明细与复检结论留档 |
| `docs/provenance.md` | 产出物真实性与可追溯性规范 | 蓝图 Part 0 展开 | 禁止事项与追溯链是否完备 |
| `docs/PRD.md` | 产品需求文档 v0.9（待你拍板） | 新增 | 【待你确认】标记处需逐条决策 |
| `docs/deploy.md` | 部署运维手册（备份/恢复/升级/监控） | 蓝图 Part 6 展开 | 备份顺序推导与演练步骤 |
| `docs/adr/0001~0008` | 八篇技术选型决策记录 | 新增（决策源自蓝图各轮评审） | 决策人栏留空待你签名 |
| `docs/acceptance/M0-验收清单.md` | M0 验收 checklist（你执行） | 新增 | 验收项与蓝图 Part 10 对齐 |
| `docs/acceptance/验收报告模板.md` | 逐轮验收报告模板 | 新增 | 留痕字段完整性 |
| `docs/postmortem/复盘模板.md` | 事故复盘模板 | 新增 | 证据链必填；无事故无文档 |
| `docs/verification/M0-记录.md` | M0 事实核验记录（含已完成项） | 新增 | 已记录真实环境检查数据 |
| `docs/eval/评测说明.md` | 评测集设计说明 | 新增 | 三层评测与脚本生成制 |

## 三、backend/app/（蓝图 Part 2~5，20 模块 + schema.sql + `__init__.py`）

| 文件 | 蓝图§ | 审查要点 |
|---|---|---|
| `__init__.py` | 新增（空，包结构需要） | — |
| `config.py` | Part 2 | 默认值与预算参数 |
| `logging_setup.py` | Part 2 | structlog JSON |
| `metrics.py` | Part 2 | 指标定义与 re-export |
| `db.py` | Part 2 | 池双检锁/DDL 逐条执行 |
| `schema.sql` | Part 2 | 7 表结构/reserved 列/vector(1024) |
| `llm.py` | Part 3 | async/to_thread/可中断退避/fallback 链/embed 串行锁 |
| `budget.py` | Part 3 | deadline/final_check |
| `events.py` | Part 3 | 先落库后推送/溢出闭环/三段式 replay/keep_alive 心跳/订阅上限 |
| `agents.py` | Part 3 | YAML 加载/工具名启动校验 |
| `agent_loop.py` | Part 3 | tool_call_id 顺序/安全截断/步数熔断文案 |
| `tasks.py` | Part 3 | CAS 抢占/guarded finish/watchdog 宽限/预留释放归属/建行落 reserved/启动对账 |
| `orchestrator.py` | Part 3 | Plan 互斥/拓扑序/Critic 回路/_finalize 终态序列 |
| `market.py` | Part 4 | hfq+raw 双口径/缓存版本键/列校验 |
| `artifacts.py` | Part 4 | 原子写(tmp+replace)/先行后文件 TTL |
| `backtest.py` | Part 4 | fill→shift 契约 |
| `dsl.py` | Part 4 | 操作数模型/深度/RSI横盘50/exit优先 |
| `tools.py` | Part 4 | 句柄返回/fixture 10 列校验（v18 P2-1）/ctx 贯通 |
| `rag.py` | Part 4 | 不跨页切块/embedding 回退探针/事务摄取/BM25 降级 |
| `memory.py` | Part 4 | recall_prefix/remember；注入提示须声明"事实以工具为准" |
| `ratelimit.py` | Part 5 | 滑窗+内存清理 |
| `main.py` | Part 5 | 急切订阅/心跳由内层产生+45s 兜底/admin fail-closed/低基数 metrics |

## 四、backend/agents/、tests/、杂项

| 文件 | 蓝图§ | 审查要点 |
|---|---|---|
| `agents/*.yaml` ×5 | Part 3 | 提示词规则与注入防护条款 |
| `tests/test_backtest.py` | Part 9 | 四类断言（数值已手算复核） |
| `tests/test_dsl.py` | Part 9 | 十类拒绝+语义断言 |
| `tests/test_events_replay.py` | Part 9 | 六个剧本（含终态立即返回/溢出/心跳不终止流） |
| `tests/test_rag_chunk.py` | Part 9 | 不跨页/页归属/扫描页拒绝 |
| `tests/__init__.py` | 新增（空，包结构需要） | — |
| `tests/conftest.py` | Part 9（v18 钉死内容） | 仅 sys.path 注入，无 fixture |
| `tests/test_compose_result.py` | Part 9（v37 新增） | _compose_result 降级三级兜底契约 |
| `requirements.txt` | Part 6 | 版本锁定 |
| `Dockerfile` | Part 6 | python:3.11-slim |
| `.env.example` | Part 6 | 三变量；不含真实密钥 |

## 五、frontend/（蓝图 Part 7）

| 文件 | 蓝图§ | 审查要点 |
|---|---|---|
| `package.json` | Part 7 | dompurify 已含 |
| `vite.config.ts` | Part 7 | dev 代理同源 |
| `tsconfig.json`、`tsconfig.node.json` | Part 7（v18 钉死内容） | verbatimModuleSyntax/lib=ES2020/noUnusedLocals 与代码约束互锁；composite 供 tsc -b references |
| `index.html` | Part 7（v18 钉死内容） | 挂载点/root、module 脚本指向 /src/main.tsx |
| `src/main.tsx`、`App.tsx` | Part 7 | — |
| `src/lib/api.ts` | Part 7 | EVENT_TYPES/subscribe 关流逻辑 |
| `src/lib/useTaskStream.ts` | Part 7 | 递归 open/seq 去重/刷新恢复 |
| `src/components/ChatBox.tsx` | Part 7 | DOMPurify/报告渲染 |
| `src/components/Timeline.tsx`、`EquityChart.tsx` | Part 7 | 假设脚注 DOM 渲染 |

## 六、deploy/、scripts/、evals/、migrations/

| 文件 | 蓝图§ | 审查要点 |
|---|---|---|
| `deploy/docker-compose.yml` | Part 6（v19 修 volumes 顶键缩进） | 三卷/DATABASE_URL/loopback 端口 |
| `deploy/nginx.conf` | Part 6 | admin deny/metrics loopback/SSE http1.1 |
| `deploy/backup.sh` | Part 6 | flock/PGPASSWORD/dump→tar→TTL 顺序 |
| `scripts/run_eval.py` | Part 8 | init_schema/fixture 归一/numbers_ok |
| `scripts/reconcile.py` | Part 6 | 零悬空断言/tmp 清理/恢复演练在 api 容器内执行 |
| `scripts/ingest.py` | Part 4 | 知识库摄取 CLI（探针先行/source_type 断言） |
| `evals/cases/backtest.yaml` | Part 8 | 三示例用例 |
| `evals/fixtures/README.md` | Part 8（v18 钉死内容） | 快照生成契约：完整 10 列双口径帧+meta 三字段（M0 生成） |
| `evals/fixtures/*.parquet` ×2 + `*.meta.json` ×2 | 新增（M0-B3 生成，脚本 m0_akshare_checks.py） | 冻结快照：600519 两个日期窗；meta=fetched_at/akshare_version/checksum |
| `migrations/001_init.sql` | Part 1 约定 | =schema.sql 快照 |
| `migrations/002_hnsw.sql` | Part 1 约定（v22 启用） | HNSW 索引；维度依据=1024（bge-m3 实测，M0-记录 §3.7），已应用验证 |

**v19 新增（M0 演练脚本，证据可复现，明细见 docs/verification/M0-记录.md）**

| 文件 | 用途 |
|---|---|
| `scripts/m0_akshare_checks.py` | B1/B2/B3：双口径拉取+hfq 重叠实证+快照生成（含故障预判#1） |
| `scripts/m0_drill_guarded_finish.py` | D2：watchdog 中断/迟到 finish 不覆盖/重启对账断言（api 容器内） |
| `scripts/m0_drill_concurrency.py` | D3 容器内：并发 to_thread 网络IO+事件循环 lag+心跳续租 |
| `scripts/m0_drill_concurrency_http.py` | D3 HTTP 面：双任务并行提交+healthz 时延监测 |
| `scripts/m0_drill_bm25_fallback.py` | C3 代码级：向量→BM25 查询级降级（api 容器内） |
| `frontend/package-lock.json` | npm 锁定依赖（M1 CI 前置；E2 首装生成） |

**v20 新增（M0 端到端补验轮）**

| 文件 | 用途 |
|---|---|
| `backend/.dockerignore` | 防止含密钥的 .env 被烤进镜像（蓝图 Part 6 v20 钉死） |
| `.github/workflows/ci.yml` | M1 CI：ubuntu+Py3.11+pytest / node20+npm ci+tsc -b（蓝图 Part 6 v20 钉死，待 GitHub push 后首跑） |
| `scripts/m0_llm_checks.py` | §3 GLM/embedding 实测（逐项容错，quota 差异记录） |
| `scripts/m0_e2e_task.py` | 端到端真实任务驱动：POST /api/chat→SSE 经 nginx→终态报告断言 |

**v22 新增（embedding 三层回退链）**

| 文件 | 用途 |
|---|---|
| `scripts/m0_drill_vector.py` | 向量检索 drill：bge-m3 真实嵌入入库→近邻命中→HNSW 验证（api 容器内） |
| `migrations/002_hnsw.sql` | 见上表（从"待定"转为已启用） |

**M2 部署轮新增（2026-08-15，线上 http://43.156.248.38）**

| 文件 | 用途 |
|---|---|
| `scripts/deploy_ssh.py` | 部署用 SSH 执行器（paramiko；密码走环境变量不落盘；put 带重试——该服务器新连接首次 SFTP open 偶发被拒，单连接多操作即过） |
| `scripts/m0_e2e_task.py`（增强） | BASE_URL/TIMEOUT_S 环境变量化（线上验收复用同一脚本） |
| `scripts/m0_seed_cache.py` | 线上行情缓存预灌（东财海外 IP 限流兜底，diskcache API 从 fixture 灌入） |
| `docs/acceptance/M2-验收报告.md` | M2 上线验收留痕 |

**求职轮新增（2026-08-17）**

| 文件 | 用途 |
|---|---|
| `docs/resume-pitch.md` | HR 版/技术版/极简版介绍语（依据真实状态撰写）+ 投递提醒 |
| `docs/pm/产品文档.md` | AI 产品经理定位版产品文档（16 项访谈决策：背景/用户/痛点/优先级/流程图/边界/埋点方案） |

| `docs/resume-final.md` | 求职材料终版（v36 状态：HR 介绍语 + 技术面试官简历项目经历完整格式 + 精简版） |

**M5/M6 轮新增（2026-08-16~17）**

| 文件 | 用途 |
|---|---|
| `docs/acceptance/M5-验收报告.md` | M5 验收留痕（备份链/限流/评测全量） |
| `docs/acceptance/M6-验收报告.md` | M6 收尾验收留痕 |
| `docs/eval/results.md` | 全量评测终版报告（100% 脚本生成，2026-08-17T02:52Z） |
| `docs/postmortem/PM-001-空报告事件.md` | 真实生产事故复盘（Issue #7，证据链五项） |
| `docs/architecture.md` | 架构说明（Mermaid ×4） |
| `docs/demo-script.md` | 演示脚本定稿（三条+分镜话术） |
| `docs/interview-qa.md` | 面试 Q&A（12 主题+速查） |

**M4 知识库轮新增（2026-08-15）**

| 文件 | 用途 |
|---|---|
| `scripts/m4_prepare_corpus.py` | 语料制备：年报按章节标记摘页节选（含 garbage 压缩）+ 方法论 120 条 AI 初稿 PDF 生成（条目正文内嵌可审） |

## 七、审查建议顺序

1. `docs/FILE-MANIFEST.md`（本文件）→ 2. `README.md` → 3. `docs/PRD.md`（含待拍板项）→ 4. `docs/provenance.md` → 5. ADR 0001~0008 → 6. 后端按 db/schema → llm → budget → events → agents → agent_loop → tasks → orchestrator → market → artifacts → dsl → backtest → tools → rag → ratelimit → main → 7. agents/*.yaml → 8. tests/ → 9. 部署四件套 + scripts → 10. 前端 → 11. `docs/verification/M0-记录.md`（已含真实环境数据）+ `docs/acceptance/M0-验收清单.md`
