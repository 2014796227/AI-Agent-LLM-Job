CREATE TABLE IF NOT EXISTS tasks(
  id            uuid PRIMARY KEY,
  trace_id      text NOT NULL,
  status        text NOT NULL,
  input         text NOT NULL,
  plan          jsonb,
  context       jsonb NOT NULL DEFAULT '{}',
  result        jsonb,
  error         text,
  worker_id     text,
  reserved      bigint NOT NULL DEFAULT 0,
  heartbeat_at  timestamptz,
  lease_expires_at timestamptz,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);

CREATE TABLE IF NOT EXISTS task_events(
  id         bigserial PRIMARY KEY,
  task_id    uuid NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  type       text NOT NULL,
  payload    jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_events_task ON task_events(task_id, id);

CREATE TABLE IF NOT EXISTS artifacts(
  id         text PRIMARY KEY,
  kind       text NOT NULL,
  path       text NOT NULL,
  meta       jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_artifacts_expires ON artifacts(expires_at);

CREATE TABLE IF NOT EXISTS docs(
  id          text PRIMARY KEY,
  title       text NOT NULL,
  source_url  text,
  source_type text NOT NULL CHECK (source_type IN ('official','curated')),
  pages       int,
  file_path   text,
  checksum    text,
  ingested_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks(
  id        bigserial PRIMARY KEY,
  doc_id    text NOT NULL REFERENCES docs(id) ON DELETE CASCADE,
  chunk     text NOT NULL,
  page      int NOT NULL DEFAULT 0,
  seq       int NOT NULL,
  embedding vector(1024),
  meta      jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id, seq);
-- HNSW 索引在 M0 实测维度后以 migrations/002_hnsw.sql 启用：
-- CREATE INDEX IF NOT EXISTS idx_chunks_emb ON chunks
--   USING hnsw(embedding vector_cosine_ops);

CREATE TABLE IF NOT EXISTS memories(
  key        text PRIMARY KEY,
  value      jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS usage_day(
  day       date PRIMARY KEY,
  tokens    bigint NOT NULL DEFAULT 0,
  reserved  bigint NOT NULL DEFAULT 0,
  llm_calls int NOT NULL DEFAULT 0,
  tasks     int NOT NULL DEFAULT 0
);
