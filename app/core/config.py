from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "local"
    database_url: str = "sqlite:///./data/gos.db"
    upload_dir: Path = Path("data/uploads")
    staging_dir: Path = Path("data/staging")
    mock_ui_enabled: bool = True
    mock_webhook_secret: str = ""
    mock_webhook_auth_mode: Literal["hmac", "secret"] = "hmac"
    mock_webhook_mode: Literal["business", "connection"] = "business"
    mock_outbound_http_enabled: bool = False
    simulator_business_mode: bool = False
    mock_backend_url: str = "http://127.0.0.1:8001"
    mock_callback_url: str = "http://127.0.0.1:9000/api/mock/replies"
    webhook_signature_tolerance_seconds: int = Field(default=300, ge=1, le=3600)
    webhook_max_body_bytes: int = Field(default=64 * 1024, ge=1024, le=1024 * 1024)
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
        if self.app_env not in {"local", "development", "test"}:
            raise ValueError(
                "This release supports local/development/test only; production auth is not implemented."
            )
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("This release requires a file-based SQLite URL.")
        if any(len(token) < 24 for token in self.auth_tokens_json):
            raise ValueError("Auth tokens must have at least 24 characters.")
        if self.mock_webhook_secret and len(self.mock_webhook_secret) < 24:
            raise ValueError("Webhook secret must have at least 24 characters.")
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
        for value in [self.mock_backend_url, self.mock_callback_url]:
            parsed = urlsplit(value)
            if (
                parsed.scheme != "http"
                or parsed.hostname not in {"127.0.0.1", "localhost"}
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "Connection demo URLs must be HTTP localhost URLs without credentials/query/fragment."
                )
        if (
            urlsplit(self.mock_backend_url).path
            or urlsplit(self.mock_callback_url).path != "/api/mock/replies"
        ):
            raise ValueError("Use backend base URL and callback path /api/mock/replies.")
        return self
