# ADR-0005：PostgreSQL + pgvector 存储与知识库设计

- 状态：已接受（HNSW 索引待 M0 实测维度后启用；M0 实测备注：当前 key 的 embedding-3/embedding-2 均报 1113 余额不足——维度实测与 embedding-2 带 dimensions 行为观察待按量付费余额后补，M0-记录 §3）
- 日期：2026-08-15
- 决策人：＿＿＿＿（待签名）
- 关联：蓝图 schema.sql / rag.py；第三轮评审（维度上限问题）；PRD【待你确认】2

## 决策 1：存储 = PostgreSQL 16 + pgvector（单库承载关系/向量/任务/事件）

备选：SQLite（演示够用）与 Chroma/Milvus（专用向量库）。选 PG 的理由：**生产一致性**（企业投研工具标配）而非规模需要；compose 一个容器；任务表/事件表/向量/工件登记同库事务（如 RAG 摄取的 DELETE+INSERT 原子性）。取舍：SQLite+numpy 暴力检索其实够用，但"为模拟生产形态选 PG"本身就是 ADR 叙事（第四轮评审拍板）。

## 决策 2：embedding 维度治理

- 智谱 `embedding-3`（默认 2048 维，dimensions 可选 256/512/1024/2048）**默认维度超过 pgvector HNSW 索引 2000 维上限**——必须显式 `dimensions=1024`
- 社区有 dimensions 配置与返回维度不匹配的真实反馈 → 启动探针实测；探针失败自动回退 embedding-2（固定 1024 维）；摄取侧整批校验、失败不写库；检索侧降级 BM25（字符二元组分词，免 jieba 依赖）并明示
- DDL `vector(1024)` 以 M0 实测为准（实测记录回填 docs/verification/M0-记录.md）

## 决策 3：引用定位 = 页级（不做字符偏移）

chunks 表只存 page + seq（v13 起移除 char_start/char_end）：字符偏移在 PDF 文本层上脆弱且精度存疑；引用点击 → 服务端 pymupdf 渲染原页 PNG + 报告内 `[[doc_id#页码]]` 标记。取舍：无法高亮到句，但页级跳转对演示足够且永不错误（chunk 不跨页，v13 契约 + 单测）。

## 决策 4：文档原页接口无鉴权（PRD 待确认项）

知识库内容本身为公开披露文件（巨潮年报等）；页级 PNG 无鉴权是产品决策（演示零摩擦）。风险=被爬取渲染页，受 IP 限流约束。若你否决，改为访客令牌即可（改动小）。

## 后果与妥协

- RAG 语料来源红线：只入官方公开文件（source_type='official'）与你审核的策展内容（'curated'，标注"AI 生成初稿+人工审核"）；付费研报仅可作为用户上传（P2）
- HNSW 索引在量级 <1 万 chunk 时收益有限，启用主要为生产形态完整
