"""Run the portal, RAG worker and optional official Zalo Bot in one process."""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn

from app.core.config import Settings
from app.main import create_app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument("--data-dir", type=Path, help="Isolated SQLite/uploads/Qdrant directory")
    args = parser.parse_args()
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
        job_lease_seconds=900,
        **options,
    )
    if not settings.claude_api_key.get_secret_value():
        raise SystemExit("Cần Claude API key trong .env.")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    print(f"Portal: http://127.0.0.1:{args.port}/portal", flush=True)
    print("RAG: BKAI → Qdrant Top 10 → mMARCO Top 5 → Claude.", flush=True)
    if settings.zalo_bot_enabled:
        print("Zalo Bot bật: polling trong backend. Gắn lớp tại Portal → Kết nối Zalo.", flush=True)
    uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
