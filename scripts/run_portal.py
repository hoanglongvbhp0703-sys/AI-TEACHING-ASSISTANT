"""Run the local user portal, with all RAG jobs disabled."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn

from app.core.config import Settings
from app.main import create_app, create_portal_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--data-dir", type=Path, help="Optional isolated directory for QA data.")
    args = parser.parse_args()
    if args.data_dir:
        folder = args.data_dir.resolve()
        app = create_app(
            Settings(
                _env_file=None,
                database_url="sqlite:///" + str(folder / "gos.db"),
                upload_dir=folder / "uploads",
                staging_dir=folder / "staging",
                seed_demo_on_start=True,
                rag_jobs_enabled=False,
                background_jobs_enabled=True,
            )
        )
    else:
        app = create_portal_app()
    print(f"Cổng học tập: http://127.0.0.1:{args.port}/portal — xem trạng thái RAG tại /api/v1/health", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
