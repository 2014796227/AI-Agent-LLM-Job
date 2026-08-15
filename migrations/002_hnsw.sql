-- 002：HNSW 向量索引（M0 实测维度=1024 后启用）
-- 实测依据：BAAI/bge-m3 @ SiliconFlow 返回 1024 维（2026-08-15，
-- docs/verification/M0-记录.md §3.7），与 schema.sql 的 vector(1024) 匹配；
-- 智谱 embedding-3/-2 维度实测待按量余额（回填后本文件不变——DDL 同为 1024）。
CREATE INDEX IF NOT EXISTS idx_chunks_emb ON chunks
  USING hnsw(embedding vector_cosine_ops);
