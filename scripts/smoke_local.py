"""Read-only HTTP smoke test against this machine's local API; never print tokens."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.core.config import Settings


def main():
    settings = Settings()
    token = next(
        (token for token, user in settings.auth_tokens_json.items() if user == "admin"), None
    )
    if not token:
        raise SystemExit("Missing local admin token; run scripts/init_local.py first.")
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=5, trust_env=False) as client:
        for path in [
            "/api/v1/health",
            "/api/v1/auth/me",
            "/api/v1/classes",
            "/openapi.json",
            "/docs",
        ]:
            response = client.get(path, headers={"Authorization": "Bearer " + token})
            print(path, response.status_code)
            response.raise_for_status()
            if path == "/api/v1/health":
                print(response.json()["data"])


if __name__ == "__main__":
    main()
