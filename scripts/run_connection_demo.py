"""Run the two local demo servers; --check verifies the HTTP round trip then stops them."""

import argparse
import hashlib
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from sqlalchemy.engine import make_url

from app.core.config import Settings


def business_state(settings):
    path = make_url(settings.database_url).database
    with sqlite3.connect(path) as db:
        names = [
            row[0]
            for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        ]
        result = {}
        for name in names:
            rows = db.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()
            result[name] = {
                "rows": len(rows),
                "sha256": hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode()).hexdigest(),
            }
        return result


def wait_ready(client, url, processes):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if any(process.poll() is not None for process in processes):
            raise RuntimeError("Không khởi động được server; kiểm tra cổng đang sử dụng.")
        try:
            response = client.get(url, timeout=0.5)
            if response.status_code == 200:
                return response.json()["data"]
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise RuntimeError("Server chưa sẵn sàng sau 15 giây.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    if not settings.mock_webhook_secret:
        raise SystemExit("Chạy scripts/init_local.py trước để cấu hình secret demo.")
    backend_port = urlsplit(settings.mock_backend_url).port
    simulator_port = urlsplit(settings.mock_callback_url).port
    if not backend_port or not simulator_port or backend_port == simulator_port:
        raise SystemExit("Cần hai cổng local khác nhau cho backend và giả lập.")
    root = Path(__file__).resolve().parents[1]
    processes = []
    try:
        for target, port in [
            ("app.main:create_connection_app", backend_port),
            ("app.simulator:create_simulator", simulator_port),
        ]:
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        target,
                        "--factory",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(port),
                        "--workers",
                        "1",
                        "--log-level",
                        "warning",
                    ],
                    cwd=root,
                )
            )
        simulator_url = f"http://127.0.0.1:{simulator_port}"
        with httpx.Client(timeout=10, trust_env=False) as client:
            health = wait_ready(client, settings.mock_backend_url + "/api/v1/health", processes)
            wait_ready(client, simulator_url + "/health", processes)
            assert health["webhook_mode"] == "connection" and health["background_jobs"] is False
            print("Giả lập:", simulator_url, flush=True)
            if args.check:
                before = business_state(settings)
                response = client.post(
                    simulator_url + "/api/mock/messages",
                    json={"text": "Xin chào, kiểm tra kết nối hai chiều"},
                )
                response.raise_for_status()
                item = response.json()["data"]
                assert item["error"] is None and item["http_status"] == 200
                assert item["receipt"]["data"]["callback_status"] == "delivered"
                assert item["callback"]["reply_to_event_id"] == item["event_id"]
                repeated = client.post(
                    simulator_url + "/api/mock/messages/" + item["event_id"] + "/retry"
                ).json()["data"]
                assert repeated["receipt"]["data"]["status"] == "duplicate_ignored"
                assert repeated["callback"]["reply_id"] == item["callback"]["reply_id"]
                assert business_state(settings) == before
                report = {
                    "passed": True,
                    "transport": "real HTTP localhost",
                    "webhook_http_status": item["http_status"],
                    "callback_status": "delivered",
                    "event_id": item["event_id"],
                    "reply_id": item["callback"]["reply_id"],
                    "duplicate": "ignored",
                    "business_tables_unchanged": True,
                }
                path = root / "data/exports/connection-check.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
                print(json.dumps(report, ensure_ascii=False), flush=True)
            else:
                print("Nhấn Ctrl+C để dừng hai server demo.", flush=True)
                while all(process.poll() is None for process in processes):
                    time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
