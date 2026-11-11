-- Extend the provider-call audit, preserving all historical IDs/usage/order.
BEGIN IMMEDIATE;
CREATE TABLE rag_run_attempts_v4 (
    id TEXT PRIMARY KEY NOT NULL,
    rag_run_id TEXT REFERENCES rag_runs(id),
    ingestion_job_id TEXT REFERENCES ingestion_jobs(id),
    stage TEXT NOT NULL CHECK (stage IN ('query_rewrite','query_embed','rerank','generate','ingestion_embed')),
    attempt_no INTEGER NOT NULL CHECK (attempt_no > 0),
    call_key TEXT NOT NULL UNIQUE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('started','succeeded','failed','unknown')),
    input_tokens INTEGER CHECK (input_tokens >= 0),
    output_tokens INTEGER CHECK (output_tokens >= 0),
    estimated_cost_usd_micros INTEGER CHECK (estimated_cost_usd_micros >= 0),
    pricing_snapshot_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(pricing_snapshot_json)),
    provider_request_id TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_code TEXT,
    CHECK ((rag_run_id IS NOT NULL AND ingestion_job_id IS NULL)
        OR (rag_run_id IS NULL AND ingestion_job_id IS NOT NULL))
);
INSERT INTO rag_run_attempts_v4 SELECT * FROM rag_run_attempts ORDER BY rowid;
DROP TABLE rag_run_attempts;
ALTER TABLE rag_run_attempts_v4 RENAME TO rag_run_attempts;
CREATE INDEX ix_run_calls ON rag_run_attempts(rag_run_id,stage,attempt_no);
CREATE INDEX ix_ingestion_calls ON rag_run_attempts(ingestion_job_id);
ALTER TABLE rag_runs ADD COLUMN query_rewrite_json TEXT NOT NULL DEFAULT '{}' CHECK(json_valid(query_rewrite_json));
PRAGMA user_version=4;
COMMIT;
