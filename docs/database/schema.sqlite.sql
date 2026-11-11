-- GOS Academy MVP: thiết kế DDL v1, không phải database production hiện hữu.
-- Chạy trên database mới. Không chạy lại thay cho Alembic migration.
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
BEGIN IMMEDIATE;

CREATE TABLE users (
    id TEXT PRIMARY KEY NOT NULL,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('student','teacher','admin','service')),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE courses (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE classes (
    id TEXT PRIMARY KEY NOT NULL,
    course_id TEXT NOT NULL REFERENCES courses(id),
    name TEXT NOT NULL,
    bot_enabled INTEGER NOT NULL DEFAULT 1 CHECK (bot_enabled IN (0,1)),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','archived')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE enrollments (
    user_id TEXT NOT NULL REFERENCES users(id),
    class_id TEXT NOT NULL REFERENCES classes(id),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','suspended','left')),
    joined_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id,class_id)
);
CREATE TABLE teacher_assignments (
    teacher_id TEXT NOT NULL REFERENCES users(id),
    class_id TEXT NOT NULL REFERENCES classes(id),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    assigned_at TEXT NOT NULL,
    PRIMARY KEY (teacher_id,class_id)
);
CREATE TABLE group_bindings (
    id TEXT PRIMARY KEY NOT NULL,
    class_id TEXT NOT NULL REFERENCES classes(id),
    platform TEXT NOT NULL,
    external_group_id TEXT NOT NULL,
    display_name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at TEXT NOT NULL,
    UNIQUE (platform,external_group_id),
    UNIQUE (id,class_id)
);
CREATE TABLE external_identities (
    id TEXT PRIMARY KEY NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(id),
    platform TEXT NOT NULL,
    external_sender_id TEXT NOT NULL,
    is_bot INTEGER NOT NULL DEFAULT 0 CHECK (is_bot IN (0,1)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
    created_at TEXT NOT NULL,
    UNIQUE (platform,external_sender_id)
);

-- scope_id được sinh canonical bởi Backend, không lấy quyền từ client.
CREATE TABLE access_scopes (
    id TEXT PRIMARY KEY NOT NULL,
    scope_type TEXT NOT NULL CHECK (scope_type IN ('course','class')),
    course_id TEXT REFERENCES courses(id),
    class_id TEXT REFERENCES classes(id),
    CHECK ((scope_type='course' AND course_id IS NOT NULL AND class_id IS NULL
            AND id='course:' || course_id)
        OR (scope_type='class' AND class_id IS NOT NULL AND course_id IS NULL
            AND id='class:' || class_id))
);
CREATE TABLE documents (
    id TEXT PRIMARY KEY NOT NULL,
    title TEXT NOT NULL,
    topic TEXT NOT NULL,
    source_code TEXT,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('file','faq')),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','revoked')),
    active_version_id TEXT,
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    created_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    deleted_at TEXT,
    deleted_by TEXT REFERENCES users(id),
    delete_reason TEXT,
    CHECK ((status='active' AND active_version_id IS NOT NULL)
        OR (status IN ('draft','revoked') AND active_version_id IS NULL)),
    FOREIGN KEY (id,active_version_id) REFERENCES document_versions(document_id,id)
        DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE document_access (
    document_id TEXT NOT NULL REFERENCES documents(id),
    scope_id TEXT NOT NULL REFERENCES access_scopes(id),
    granted_by TEXT NOT NULL REFERENCES users(id),
    created_at TEXT NOT NULL,
    PRIMARY KEY (document_id,scope_id)
);
CREATE TABLE document_versions (
    id TEXT PRIMARY KEY NOT NULL,
    document_id TEXT NOT NULL REFERENCES documents(id),
    version INTEGER NOT NULL CHECK (version > 0),
    source_version TEXT,
    sha256 TEXT NOT NULL CHECK (length(sha256)=64),
    file_path TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    file_size_bytes INTEGER NOT NULL CHECK (file_size_bytes >= 0),
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','indexing','ready','active','superseded','failed','revoked')),
    extraction_config_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(extraction_config_json)),
    parser_version TEXT,
    embedding_model TEXT,
    vector_size INTEGER CHECK (vector_size > 0),
    chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    point_count INTEGER NOT NULL DEFAULT 0 CHECK (point_count >= 0),
    change_note TEXT,
    uploaded_by TEXT NOT NULL REFERENCES users(id),
    uploaded_at TEXT NOT NULL,
    indexed_at TEXT,
    activated_at TEXT,
    error_code TEXT,
    UNIQUE (document_id,version),
    UNIQUE (document_id,id)
);
-- Không đặt UNIQUE sha256: có thể khôi phục nội dung V1 bằng version V3.
CREATE UNIQUE INDEX ux_one_active_version ON document_versions(document_id) WHERE status='active';
CREATE TABLE document_chunks (
    point_id TEXT PRIMARY KEY NOT NULL,
    document_id TEXT NOT NULL,
    document_version_id TEXT NOT NULL,
    chunk_id TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    section_id TEXT,
    section_path TEXT,
    topic TEXT NOT NULL,
    page INTEGER CHECK (page > 0),
    sheet_name TEXT,
    row_start INTEGER CHECK (row_start > 0),
    row_end INTEGER CHECK (row_end >= row_start),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256)=64),
    created_at TEXT NOT NULL,
    indexed_at TEXT,
    FOREIGN KEY (document_id,document_version_id) REFERENCES document_versions(document_id,id),
    FOREIGN KEY (document_id,scope_id) REFERENCES document_access(document_id,scope_id),
    UNIQUE (document_version_id,chunk_id,scope_id)
);
CREATE TABLE ingestion_jobs (
    id TEXT PRIMARY KEY NOT NULL,
    document_version_id TEXT NOT NULL REFERENCES document_versions(id),
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','succeeded','failed','cancelled')),
    stage TEXT NOT NULL DEFAULT 'parse' CHECK (stage IN ('parse','chunk','embed','upsert','verify','activate','done')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    chunks_indexed INTEGER NOT NULL DEFAULT 0 CHECK (chunks_indexed >= 0),
    points_indexed INTEGER NOT NULL DEFAULT 0 CHECK (points_indexed >= 0),
    lease_token TEXT,
    lease_expires_at TEXT,
    next_attempt_at TEXT NOT NULL,
    error_code TEXT,
    error_message_redacted TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE UNIQUE INDEX ux_ingestion_live ON ingestion_jobs(document_version_id)
    WHERE status IN ('queued','processing');
CREATE TABLE cleanup_jobs (
    id TEXT PRIMARY KEY NOT NULL,
    document_version_id TEXT NOT NULL REFERENCES document_versions(id),
    cleanup_kind TEXT NOT NULL CHECK (cleanup_kind IN ('vectors','file')),
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','processing','succeeded','failed','cancelled')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    lease_token TEXT,
    lease_expires_at TEXT,
    next_attempt_at TEXT NOT NULL,
    error_code TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT,
    UNIQUE (document_version_id,cleanup_kind)
);

CREATE TABLE webhook_events (
    event_key TEXT PRIMARY KEY NOT NULL,
    request_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    external_event_id TEXT NOT NULL,
    raw_group_id TEXT NOT NULL,
    raw_sender_id TEXT NOT NULL,
    group_binding_id TEXT,
    class_id TEXT REFERENCES classes(id),
    user_id TEXT REFERENCES users(id),
    question_redacted TEXT,
    payload_sha256 TEXT NOT NULL CHECK (length(payload_sha256)=64),
    reply_to_external_event_id TEXT,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','processing','completed','failed','ignored','rejected')),
    outcome_code TEXT,
    accepted_at TEXT,
    processing_started_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    lease_token TEXT,
    lease_expires_at TEXT,
    next_attempt_at TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    completed_at TEXT,
    error_code TEXT,
    CHECK ((group_binding_id IS NULL AND class_id IS NULL)
        OR (group_binding_id IS NOT NULL AND class_id IS NOT NULL)),
    CHECK (accepted_at IS NULL OR (user_id IS NOT NULL AND class_id IS NOT NULL)),
    FOREIGN KEY (group_binding_id,class_id) REFERENCES group_bindings(id,class_id),
    UNIQUE (platform,external_event_id),
    UNIQUE (event_key,class_id,group_binding_id)
);
CREATE TABLE daily_usage (
    user_id TEXT NOT NULL REFERENCES users(id),
    local_date TEXT NOT NULL CHECK (length(local_date)=10),
    accepted_count INTEGER NOT NULL DEFAULT 0 CHECK (accepted_count BETWEEN 0 AND 30),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (user_id,local_date)
);
CREATE TABLE quota_reservations (
    event_key TEXT PRIMARY KEY NOT NULL REFERENCES webhook_events(event_key),
    user_id TEXT NOT NULL,
    local_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('reserved','charged','released')),
    reserved_at TEXT NOT NULL,
    charged_at TEXT,
    released_at TEXT,
    release_reason TEXT,
    FOREIGN KEY (user_id,local_date) REFERENCES daily_usage(user_id,local_date)
);
CREATE TABLE conversation_sessions (
    id TEXT PRIMARY KEY NOT NULL,
    class_id TEXT NOT NULL,
    group_binding_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','expired','closed')),
    started_at TEXT NOT NULL,
    last_hoi_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (group_binding_id,class_id) REFERENCES group_bindings(id,class_id),
    UNIQUE (id,class_id,group_binding_id)
);
CREATE UNIQUE INDEX ux_open_session ON conversation_sessions(class_id,group_binding_id) WHERE status='open';
CREATE TABLE messages (
    id TEXT PRIMARY KEY NOT NULL,
    session_id TEXT NOT NULL,
    event_key TEXT NOT NULL,
    class_id TEXT NOT NULL,
    group_binding_id TEXT NOT NULL,
    sender_user_id TEXT REFERENCES users(id),
    role TEXT NOT NULL CHECK (role IN ('user','assistant','teacher')),
    message_kind TEXT NOT NULL CHECK (message_kind IN ('question','answer','handoff','blocked','technical_error','teacher_answer')),
    text_redacted TEXT NOT NULL,
    memory_eligible INTEGER NOT NULL DEFAULT 0 CHECK (memory_eligible IN (0,1)),
    status TEXT NOT NULL DEFAULT 'committed' CHECK (status IN ('committed','withdrawn')),
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id,class_id,group_binding_id) REFERENCES conversation_sessions(id,class_id,group_binding_id),
    FOREIGN KEY (event_key,class_id,group_binding_id) REFERENCES webhook_events(event_key,class_id,group_binding_id),
    UNIQUE (event_key,message_kind)
);
CREATE TABLE support_tickets (
    id TEXT PRIMARY KEY NOT NULL,
    event_key TEXT NOT NULL UNIQUE,
    class_id TEXT NOT NULL,
    group_binding_id TEXT NOT NULL,
    student_id TEXT NOT NULL REFERENCES users(id),
    question_redacted TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    evidence_summary_redacted TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','assigned','answered','closed')),
    assignee_id TEXT REFERENCES users(id),
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    answered_at TEXT,
    closed_at TEXT,
    FOREIGN KEY (event_key,class_id,group_binding_id) REFERENCES webhook_events(event_key,class_id,group_binding_id)
);
-- MVP có một câu trả lời chính thức/ticket; mở rộng thread bằng migration sau.
CREATE TABLE ticket_replies (
    id TEXT PRIMARY KEY NOT NULL,
    ticket_id TEXT NOT NULL UNIQUE REFERENCES support_tickets(id),
    teacher_id TEXT NOT NULL REFERENCES users(id),
    answer_redacted TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE faq_entries (
    id TEXT PRIMARY KEY NOT NULL,
    source_ticket_id TEXT NOT NULL UNIQUE REFERENCES support_tickets(id),
    question_redacted TEXT NOT NULL,
    approved_answer_redacted TEXT NOT NULL,
    topic TEXT NOT NULL,
    scope_id TEXT NOT NULL REFERENCES access_scopes(id),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','approved','revoked')),
    document_id TEXT UNIQUE REFERENCES documents(id),
    created_by TEXT NOT NULL REFERENCES users(id),
    approved_by TEXT REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    approved_at TEXT,
    CHECK (status!='approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL AND document_id IS NOT NULL))
);
CREATE TABLE outbound_messages (
    id TEXT PRIMARY KEY NOT NULL,
    event_key TEXT NOT NULL,
    class_id TEXT NOT NULL,
    group_binding_id TEXT NOT NULL,
    message_kind TEXT NOT NULL CHECK (message_kind IN ('bot_result','validation_notice','policy_notice','teacher_answer')),
    reply_to_external_event_id TEXT NOT NULL,
    text_redacted TEXT NOT NULL,
    citations_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(citations_json)),
    ticket_id TEXT REFERENCES support_tickets(id),
    ticket_reply_id TEXT UNIQUE REFERENCES ticket_replies(id),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sending','sent','failed','cancelled')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    lease_token TEXT,
    lease_expires_at TEXT,
    next_attempt_at TEXT NOT NULL,
    external_message_id TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT,
    error_code TEXT,
    FOREIGN KEY (event_key,class_id,group_binding_id) REFERENCES webhook_events(event_key,class_id,group_binding_id),
    UNIQUE (event_key,message_kind)
);
CREATE TABLE rag_runs (
    id TEXT PRIMARY KEY NOT NULL,
    event_key TEXT NOT NULL UNIQUE REFERENCES webhook_events(event_key),
    status TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running','answered','insufficient_evidence','blocked','error')),
    allowed_scopes_json TEXT NOT NULL CHECK (json_valid(allowed_scopes_json)),
    active_versions_json TEXT NOT NULL CHECK (json_valid(active_versions_json)),
    memory_event_keys_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(memory_event_keys_json)),
    evidence_sufficient INTEGER CHECK (evidence_sufficient IN (0,1)),
    evidence_reason_redacted TEXT,
    latency_ms INTEGER CHECK (latency_ms >= 0),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error_code TEXT
);
-- Mỗi dòng = một provider call, kể cả embed/rerank, retry, lỗi có bill.
CREATE TABLE rag_run_attempts (
    id TEXT PRIMARY KEY NOT NULL,
    rag_run_id TEXT REFERENCES rag_runs(id),
    ingestion_job_id TEXT REFERENCES ingestion_jobs(id),
    stage TEXT NOT NULL CHECK (stage IN ('query_embed','rerank','generate','ingestion_embed')),
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
CREATE TABLE rag_citations (
    id TEXT PRIMARY KEY NOT NULL,
    rag_run_id TEXT NOT NULL REFERENCES rag_runs(id),
    ordinal INTEGER NOT NULL CHECK (ordinal > 0),
    point_id TEXT NOT NULL REFERENCES document_chunks(point_id),
    title_snapshot TEXT NOT NULL,
    page INTEGER CHECK (page > 0),
    section_path TEXT,
    evidence_excerpt_redacted TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (rag_run_id,ordinal)
);
CREATE TABLE security_events (
    id TEXT PRIMARY KEY NOT NULL,
    event_key TEXT REFERENCES webhook_events(event_key),
    request_id TEXT NOT NULL,
    actor_user_id TEXT REFERENCES users(id),
    reason_code TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('info','warning','error')),
    details_redacted_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(details_redacted_json)),
    created_at TEXT NOT NULL
);
CREATE TABLE audit_logs (
    id TEXT PRIMARY KEY NOT NULL,
    request_id TEXT NOT NULL,
    actor_user_id TEXT REFERENCES users(id),
    action TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    change_redacted_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(change_redacted_json)),
    created_at TEXT NOT NULL
);

CREATE INDEX ix_classes_course ON classes(course_id);
CREATE INDEX ix_enrollment_class_status ON enrollments(class_id,status);
CREATE INDEX ix_teacher_class ON teacher_assignments(class_id,is_active);
CREATE INDEX ix_identity_user ON external_identities(user_id);
CREATE INDEX ix_groups_class ON group_bindings(class_id,is_active);
CREATE INDEX ix_access_scope ON document_access(scope_id,document_id);
CREATE INDEX ix_documents_topic ON documents(topic,status,updated_at);
CREATE INDEX ix_chunks_version ON document_chunks(document_version_id,scope_id);
CREATE INDEX ix_ingestion_due ON ingestion_jobs(status,next_attempt_at);
CREATE INDEX ix_cleanup_due ON cleanup_jobs(status,next_attempt_at);
CREATE INDEX ix_events_due ON webhook_events(status,next_attempt_at);
CREATE INDEX ix_events_user_time ON webhook_events(user_id,accepted_at);
CREATE INDEX ix_events_class_time ON webhook_events(class_id,received_at);
CREATE INDEX ix_quota_user_date ON quota_reservations(user_id,local_date,status);
CREATE INDEX ix_messages_session ON messages(session_id,created_at,id);
CREATE INDEX ix_tickets_class_status ON support_tickets(class_id,status,created_at);
CREATE INDEX ix_outbound_group ON outbound_messages(group_binding_id,created_at,id);
CREATE INDEX ix_outbound_due ON outbound_messages(status,next_attempt_at);
CREATE INDEX ix_run_calls ON rag_run_attempts(rag_run_id,stage,attempt_no);
CREATE INDEX ix_ingestion_calls ON rag_run_attempts(ingestion_job_id);
CREATE INDEX ix_security_time ON security_events(created_at,reason_code);
CREATE INDEX ix_audit_entity ON audit_logs(entity_type,entity_id,created_at);

-- Active pointer chỉ được trỏ vào version đã verify; quan hệ cùng document do FK đảm bảo.
CREATE TRIGGER document_activate_verified
BEFORE UPDATE OF active_version_id ON documents
WHEN NEW.active_version_id IS NOT NULL
BEGIN
    SELECT RAISE(ABORT,'version_not_ready') WHERE NOT EXISTS (
        SELECT 1 FROM document_versions v WHERE v.id=NEW.active_version_id
        AND v.document_id=NEW.id AND v.status IN ('ready','active')
    );
END;
-- Lịch sử nhóm đã nhận event không được đổi sang lớp khác; tạo group binding mới
-- chỉ khi nền tảng có external_group_id mới. Rebind cần migration nghiệp vụ riêng.
CREATE TRIGGER prevent_group_rebind
BEFORE UPDATE OF class_id ON group_bindings
WHEN NEW.class_id != OLD.class_id
BEGIN
    SELECT RAISE(ABORT,'group_rebind_requires_history_policy');
END;
COMMIT;

-- Authentication migration v2
-- Add password credentials and durable login sessions without changing business data.
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS user_credentials (
    user_id TEXT PRIMARY KEY NOT NULL REFERENCES users(id),
    username TEXT NOT NULL UNIQUE CHECK (length(username) BETWEEN 3 AND 64 AND username=lower(username)),
    password_hash TEXT NOT NULL CHECK (password_hash LIKE '$argon2id$%'),
    failed_attempts INTEGER NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
    locked_until TEXT,
    last_login_at TEXT,
    password_changed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_sessions (
    id TEXT PRIMARY KEY NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(id),
    token_hash TEXT NOT NULL UNIQUE CHECK (length(token_hash)=64),
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_user_expires ON auth_sessions(user_id,expires_at);
PRAGMA user_version=2;
COMMIT;

-- Stable student numbers are scoped to a class; login sessions may be class-scoped.
BEGIN IMMEDIATE;
ALTER TABLE enrollments ADD COLUMN student_number INTEGER CHECK (student_number > 0);
WITH numbered AS (
 SELECT user_id,class_id,ROW_NUMBER() OVER(PARTITION BY class_id ORDER BY joined_at,user_id) AS n FROM enrollments
)
UPDATE enrollments SET student_number=(SELECT n FROM numbered n WHERE n.user_id=enrollments.user_id AND n.class_id=enrollments.class_id);
CREATE UNIQUE INDEX ux_enrollment_class_number ON enrollments(class_id,student_number);
CREATE TRIGGER tr_assign_student_number AFTER INSERT ON enrollments
WHEN NEW.student_number IS NULL
BEGIN
 UPDATE enrollments SET student_number=(SELECT COALESCE(MAX(student_number),0)+1 FROM enrollments WHERE class_id=NEW.class_id)
 WHERE user_id=NEW.user_id AND class_id=NEW.class_id;
END;
CREATE TRIGGER tr_student_number_immutable BEFORE UPDATE OF student_number ON enrollments
WHEN OLD.student_number IS NOT NULL AND NEW.student_number IS NOT OLD.student_number
BEGIN SELECT RAISE(ABORT,'student_number is immutable'); END;
ALTER TABLE auth_sessions ADD COLUMN class_id TEXT REFERENCES classes(id);
PRAGMA user_version=3;
COMMIT;

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
