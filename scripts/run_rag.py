"""Start one RAG/portal server and the business-mode Mock Zalo simulator."""

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn

from app.core.config import Settings
from app.main import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--simulator-port", type=int, default=9000)
    parser.add_argument(
        "--data-dir", type=Path, help="Isolated SQLite/uploads/Qdrant directory for QA"
    )
    args = parser.parse_args()
    if args.port == args.simulator_port:
        raise SystemExit("Hai cổng phải khác nhau.")
    base = f"http://127.0.0.1:{args.port}"
    callback = f"http://127.0.0.1:{args.simulator_port}/api/mock/replies"
    options = {}
    if args.data_dir:
        folder = args.data_dir.resolve()
        options.update(
            database_url="sqlite:///" + str(folder / "gos.db"),
            upload_dir=folder / "uploads",
            staging_dir=folder / "staging",
            rag_vector_dir=folder / "qdrant",
        )
    settings = Settings(
        rag_enabled=True,
        rag_jobs_enabled=True,
        seed_demo_on_start=True,
        mock_webhook_mode="business",
        mock_outbound_http_enabled=True,
        mock_backend_url=base,
        mock_callback_url=callback,
        job_lease_seconds=900,
        **options,
    )
    if not settings.claude_api_key.get_secret_value() or not settings.mock_webhook_secret:
        raise SystemExit("Cần Claude API key và MOCK_WEBHOOK_SECRET trong .env.")
    env = {
        **os.environ,
        "MOCK_BACKEND_URL": base,
        "MOCK_CALLBACK_URL": callback,
        "SIMULATOR_BUSINESS_MODE": "true",
        "DATABASE_URL": settings.database_url,
        "UPLOAD_DIR": str(settings.upload_dir),
        "STAGING_DIR": str(settings.staging_dir),
        "RAG_VECTOR_DIR": str(settings.rag_vector_dir),
    }
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.simulator:create_simulator",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(args.simulator_port),
        ],
        env=env,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    try:
        print(
            f"Portal: {base}/portal | Mock Zalo: http://127.0.0.1:{args.simulator_port}", flush=True
        )
        print(
            "RAG bật: BKAI → Qdrant Top 10 → mMARCO Top 5 → Claude. Nhắn /hoi trong nhóm Machine Learning.",
            flush=True,
        )
        uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, log_level="info")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    main()
