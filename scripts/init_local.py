"""Create local secrets if missing and initialize a persistent demo DB without resetting data."""

import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.clock import Clock
from app.core.config import Settings
from app.db.seed import seed_demo
from app.db.session import Database


def main():
    env = Path(".env")
    if not env.exists():
        tokens = {
            secrets.token_urlsafe(32): u for u in ["admin", "teacher-gs", "teacher-ai"]
        }
        content = (
            "APP_ENV=local\nSEED_DEMO_ON_START=true\nAUTH_TOKENS_JSON="
            + json.dumps(tokens, separators=(",", ":"))
            + "\n"
        )
        with env.open("x") as stream:
            stream.write(content)
        env.chmod(0o600)
        print(
            "Created .env with random local credentials. Values are not printed; existing .env is never overwritten."
        )
    settings = Settings()
    db = Database(settings)
    try:
        db.migrate()
        seed_demo(db, Clock())
        settings.upload_dir.mkdir(parents=True, exist_ok=True)
        settings.staging_dir.mkdir(parents=True, exist_ok=True)
    finally:
        db.engine.dispose()
    print(
        "SQLite schema v5 and demo users/classes initialized. Start: .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1"
    )


if __name__ == "__main__":
    main()
