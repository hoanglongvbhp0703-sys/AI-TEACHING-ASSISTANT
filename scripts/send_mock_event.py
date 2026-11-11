"""Sign and send a mock event to localhost only. Never print the shared secret/headers."""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

from app.core.config import Settings
from app.integrations.mock_zalo_adapter import sign_payload
from app.schemas.event import MockEvent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="JSON file chứa một event theo MockEvent.")
    parser.add_argument("--repeat", type=int, choices=[1, 2], default=1)
    parser.add_argument(
        "--port", type=int, choices=range(1024, 65536), default=8000, metavar="PORT"
    )
    parser.add_argument("--auth-mode", choices=["hmac", "secret"], default=None)
    args = parser.parse_args()
    settings = Settings()
    if not settings.mock_webhook_secret:
        raise SystemExit("Chưa có MOCK_WEBHOOK_SECRET; hãy chạy scripts/init_local.py.")
    # Normalize once, then sign exactly the bytes sent by httpx via content=.
    event = MockEvent.model_validate_json(args.file.read_bytes())
    raw = event.model_dump_json().encode("utf-8")
    mode = args.auth_mode or settings.mock_webhook_auth_mode
    with httpx.Client(
        base_url=f"http://127.0.0.1:{args.port}", trust_env=False, timeout=10
    ) as client:
        for _ in range(args.repeat):
            headers = {"Content-Type": "application/json"}
            if mode == "hmac":
                timestamp = str(int(time.time()))
                headers.update(
                    {
                        "X-Webhook-Timestamp": timestamp,
                        "X-Webhook-Signature": sign_payload(
                            settings.mock_webhook_secret, timestamp, raw
                        ),
                    }
                )
            else:
                headers["X-Webhook-Secret"] = settings.mock_webhook_secret
            response = client.post("/api/v1/webhooks/mock-zalo", content=raw, headers=headers)
            print(response.status_code, json.dumps(response.json(), ensure_ascii=False))
            response.raise_for_status()


if __name__ == "__main__":
    main()
