"""Load selected handover materials via real ingestion. Stop other Qdrant owners first."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Settings
from app.main import create_app
from app.repositories.store import uid


async def main():
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, help="Optional isolated database/uploads/Qdrant directory"
    )
    args = parser.parse_args()
    options = {}
    if args.data_dir:
        root = args.data_dir.resolve()
        options = dict(
            database_url="sqlite:///" + str(root / "gos.db"),
            upload_dir=root / "uploads",
            staging_dir=root / "staging",
            rag_vector_dir=root / "qdrant",
        )
    files = [(p, "ML-DEMO-01") for p in sorted(Path("Machine Learning copy").rglob("*.pdf"))]
    sheets = Path("ban_giao/03_demo/tai_lieu_mau/google_sheets_demo.docx")
    if len(files) != 14 or not sheets.is_file():
        raise SystemExit(
            "Run from repository root; require 14 ML PDFs and the handover Sheets DOCX."
        )
    files.append((sheets, "GS-KPI-01"))
    app = create_app(
        Settings(
            rag_enabled=True,
            rag_jobs_enabled=True,
            seed_demo_on_start=True,
            background_jobs_enabled=False,
            mock_outbound_http_enabled=False,
            job_lease_seconds=900,
            **options,
        )
    )
    async with app.router.lifespan_context(app):
        with app.state.db.read() as s:
            admin = s.one("SELECT * FROM users WHERE id='admin' AND role='admin' AND is_active=1")
        if not admin:
            raise SystemExit("Demo admin missing/inactive; initialize demo database first.")
        for file, cid in files:
            source = "HANDOVER:" + cid + ":" + file.name
            with app.state.db.read() as s:
                existing = s.one(
                    "SELECT id FROM documents WHERE source_code=:s AND status!='revoked'", s=source
                )
            result = app.state.documents.upload(
                admin,
                uid(),
                file.read_bytes(),
                file.name,
                title=file.stem,
                topic="Machine Learning" if cid == "ML-DEMO-01" else "Google Sheets",
                scopes=["class:" + cid],
                did=existing["id"] if existing else None,
                source_code=source,
            )
            while app.state.worker.ingestion_one():
                pass
            with app.state.db.read() as s:
                version = s.one(
                    "SELECT status,chunk_count,error_code FROM document_versions WHERE id=:v",
                    v=result["version_id"],
                )
            print(file.name, version["status"], "chunks=" + str(version["chunk_count"]), flush=True)
            if version["status"] != "active":
                raise SystemExit("Ingestion failed: " + str(version["error_code"]))
    print("15 documents active. Start: .venv/bin/python scripts/run_rag.py")


if __name__ == "__main__":
    asyncio.run(main())
