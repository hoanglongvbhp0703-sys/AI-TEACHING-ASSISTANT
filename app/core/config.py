from pathlib import Path
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "local"
    database_url: str = "sqlite:///./data/gos.db"
    upload_dir: Path = Path("data/uploads")
    staging_dir: Path = Path("data/staging")
    auth_tokens_json: dict[str, str] = Field(default_factory=dict)
    seed_demo_on_start: bool = False
    rag_jobs_enabled: bool = True
    rag_enabled: bool = False
    rag_vector_dir: Path = Path("data/qdrant")
    rag_model_cache: Path = Path("data/models")
    rag_embedding_model: str = "bkai-foundation-models/vietnamese-bi-encoder"
    rag_allowed_embedding_models: list[str] = Field(
        default_factory=lambda: ["bkai-foundation-models/vietnamese-bi-encoder"]
    )
    rag_reranker_model: str = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
    rag_device: str = "cpu"
    rag_cpu_threads: int = Field(default=4, ge=1, le=16)
    rag_rewrite_enabled: bool = True
    rag_rewrite_model: str | None = None
    rag_rewrite_timeout_seconds: float = Field(default=20, ge=5, le=45)
    rag_rewrite_max_tokens: int = Field(default=512, ge=64, le=1024)
    rag_llm_timeout_seconds: float = Field(default=45, ge=5, le=90)
    rag_max_output_tokens: int = Field(default=1200, ge=64, le=4096)
    claude_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices(
            "CLAUDE_API_KEY", "env_api_ai_claude", "ANTHROPIC_API_KEY", "claude_api_key"
        ),
    )
    claude_base_url: str = "https://hhtechapi.net"
    claude_model: str = "claude-sonnet-4.6"
    background_jobs_enabled: bool = True
    zalo_bot_enabled: bool = False
    zalo_bot_token: SecretStr = SecretStr("")
    job_poll_seconds: float = Field(default=1.0, ge=0.05, le=60)
    job_lease_seconds: int = Field(default=120, ge=10)
    job_max_attempts: int = Field(default=3, ge=1, le=10)
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = Field(default=5, ge=1)
    memory_max_turns: int = Field(default=5, ge=1, le=5)
    memory_ttl_minutes: int = Field(default=30, ge=1)
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    max_request_bytes: int = Field(default=11 * 1024 * 1024, ge=1024)
    sqlite_busy_timeout_ms: int = 5000

    @model_validator(mode="after")
    def local_only(self):
        if self.zalo_bot_enabled and (
            not self.zalo_bot_token.get_secret_value() or not self.background_jobs_enabled
        ):
            raise ValueError("Zalo Bot requires a token and background jobs.")
        if self.app_env not in {"local", "development", "test"}:
            raise ValueError(
                "This release supports local/development/test only; production auth is not implemented."
            )
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("This release requires a file-based SQLite URL.")
        if any(len(token) < 24 for token in self.auth_tokens_json):
            raise ValueError("Auth tokens must have at least 24 characters.")
        provider_url = urlsplit(self.claude_base_url)
        if (
            provider_url.scheme != "https"
            or not provider_url.hostname
            or provider_url.username
            or provider_url.password
            or provider_url.query
            or provider_url.fragment
            or provider_url.path.strip("/")
        ):
            raise ValueError("CLAUDE_BASE_URL must be an HTTPS origin without credentials or path.")
        if self.rag_embedding_model not in self.rag_allowed_embedding_models:
            raise ValueError("Default embedding model must be allowlisted.")
        return self
