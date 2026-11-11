from pathlib import Path

import pytest

from app.jobs.runner import Worker
from app.services.progress_service import index_progress
from tests.conftest import auth, drain, upload


def test_index_percentage_uses_real_counts():
    progress = index_progress(
        {
            "stage": "embed",
            "status": "processing",
            "chunks_total": 32,
            "chunks_indexed": 16,
            "points_total": 32,
            "points_indexed": 0,
            "error_code": None,
        }
    )
    assert progress["percent"] == 47 and progress["chunks_done"] == 16
    failed = index_progress(
        {
            "stage": "upsert",
            "status": "failed",
            "chunks_indexed": 0,
            "points_indexed": 0,
            "error_code": "embedding_unconfigured",
        }
    )
    assert failed["percent"] == 0 and "chưa cấu hình" in failed["label"]


def test_document_failure_log_retry_and_terminal_progress(rig):
    app, c, backend, _ = rig
    backend.fail_index = True
    info = upload(c).json()["data"]
    drain(app)
    job = c.get("/api/v1/ingestion-jobs/" + info["job_id"], headers=auth()).json()["data"]
    assert job["progress"]["status"] == "failed"
    assert job["progress"]["error_code"] == "test_index_failure"
    doc = c.get("/api/v1/documents/" + info["document_id"], headers=auth()).json()["data"]
    assert doc["versions"][0]["job_id"] == info["job_id"]
    log_file = Path(app.state.settings.upload_dir).parent / "logs/backend.log"
    logs = log_file.read_text()
    assert "document_uploaded" in logs and "ingestion_failed" in logs and info["job_id"] in logs
    backend.fail_index = False
    retried = c.post("/api/v1/ingestion-jobs/" + info["job_id"] + "/retry", headers=auth()).json()[
        "data"
    ]
    drain(app)
    done = c.get("/api/v1/ingestion-jobs/" + retried["job_id"], headers=auth()).json()["data"]
    assert done["progress"]["percent"] == 100 and done["progress"]["status"] == "succeeded"


def test_rejected_upload_logs_request_id_without_file_contents(rig):
    app, c, _, _ = rig
    response = upload(c, data=b"PRIVATE FILE TEXT THAT IS NOT JSON")
    assert response.status_code == 422
    request_id = response.json()["request_id"]
    logs = (Path(app.state.settings.upload_dir).parent / "logs/backend.log").read_text()
    assert request_id in logs and "invalid_document" in logs
    assert "PRIVATE FILE TEXT" not in logs


def test_one_worker_per_database_and_unconfigured_worker_does_not_steal(rig):
    app, _, backend, clock = rig
    worker = app.state.worker
    worker.start()
    other = Worker(app.state.db, clock, app.state.settings, backend, app.state.events)
    try:
        with pytest.raises(RuntimeError, match="worker khác"):
            other.start()
    finally:
        other.stop()
        worker.stop()
