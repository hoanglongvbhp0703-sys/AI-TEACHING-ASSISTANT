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
