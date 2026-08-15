from prometheus_client import (Counter, Gauge, generate_latest,
                               CONTENT_TYPE_LATEST)

M_HTTP      = Counter("http_requests_total", "HTTP请求", ["path", "code"])
M_LLM_TOKEN = Counter("llm_tokens_total", "LLM token用量", ["model"])
M_TASK      = Counter("task_status_total", "任务终态", ["status"])
M_BUDGET    = Counter("budget_exceeded_total", "预算熔断", ["reason"])
M_EMB_DIM   = Gauge("embedding_dim_ok", "启动探针维度校验(1/0)")
M_ORPHAN    = Counter("artifacts_orphaned_reclaimed_total", "回收孤儿工件数")
M_BUS_DROP  = Counter("bus_dropped_events_total", "订阅队列溢出次数")
M_ADMIN     = Counter("admin_ops_total", "管理操作", ["op", "ip"])
M_EMIT_FAIL = Counter("event_emit_fail_total", "事件落库失败次数")
M_TASK_CONF = Counter("task_finish_conflict_total", "finish状态冲突(被watchdog等先行迁移)")
M_CRITIC_FAILOPEN = Counter("critic_parse_failopen_total",
                            "critic输出解析失败且重试失败(放行)——独立计数,非预算事件")
M_RAG_FALLBACK = Counter("rag_search_fallback_total",
                         "检索查询级向量→BM25降级次数(与探针级embedding_dim_ok互补)")
