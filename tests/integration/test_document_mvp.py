import json

from tests.conftest import auth, drain, upload


def detail(c, did):
    return c.get("/api/v1/documents/" + did, headers=auth()).json()["data"]


def test_document_acl_without_sections_and_reject_legacy_config(rig):
    app, c, backend, _ = rig
    scopes = ["class:GS-KPI-01", "class:ML-DEMO-01"]
    result = upload(c, user="admin", scopes=scopes)
    assert result.status_code == 202
    info = result.json()["data"]
    drain(app)
    with app.state.db.read() as s:
        assert {
            r["scope_id"]
            for r in s.all(
                "SELECT scope_id FROM document_chunks WHERE document_version_id=:v",
                v=info["version_id"],
            )
        } == set(scopes)
    assert upload(c, config={"section_scopes": {"CH1": ["class:GS-KPI-01"]}}).status_code == 422


def test_explicit_target_no_guessing_and_automatic_version(rig):
    app, c, _, _ = rig
    first = upload(c).json()["data"]
    second = upload(c).json()["data"]
    assert first["document_id"] != second["document_id"]
    assert first["version"] == second["version"] == 1
    drain(app)
    changed = c.post(
        "/api/v1/documents/" + first["document_id"] + "/versions",
        headers=auth("teacher-gs"),
        files={
            "file": (
                "totally-different.json",
                b'{"question":"Changed","answer":"Answer"}',
                "application/json",
            )
        },
    ).json()["data"]
    assert changed["document_id"] == first["document_id"] and changed["version"] == 2
    assert len(detail(c, second["document_id"])["versions"]) == 1


def test_reindex_same_hash_model_change_and_failure_keeps_active(rig):
    app, c, backend, _ = rig
    original = upload(c).json()["data"]
    drain(app)
    did = original["document_id"]
    url = "/api/v1/documents/" + did + "/reindex"
    assert c.post(url, headers=auth("teacher-ai"), json={}).status_code == 403
    backend.fail_index = True
    result = c.post(
        url,
        headers=auth("teacher-gs"),
        json={
            "extraction_config": {
                "embedding_model": "TEST-NEW",
                "chunk_size": 512,
                "chunk_overlap": 64,
            }
        },
    )
    assert result.status_code == 202
    pending = result.json()["data"]
    assert pending["document_id"] == did and pending["version"] == 2
    assert detail(c, did)["active_version_id"] == original["version_id"]
    assert c.post(url, headers=auth(), json={}).status_code == 409
    drain(app)
    assert detail(c, did)["active_version_id"] == original["version_id"]
    backend.fail_index = False
    assert (
        c.post("/api/v1/ingestion-jobs/" + pending["job_id"] + "/retry", headers=auth()).status_code
        == 202
    )
    drain(app)
    doc = detail(c, did)
    assert doc["active_version_id"] == pending["version_id"]
    assert doc["versions"][0]["sha256"] == doc["versions"][1]["sha256"]
    with app.state.db.read() as s:
        assert (
            s.one(
                "SELECT embedding_model FROM document_versions WHERE id=:v", v=pending["version_id"]
            )["embedding_model"]
            == "TEST-NEW"
        )
    again = c.post(url, headers=auth(), json={})
    assert again.status_code == 202 and again.json()["data"]["version"] == 3


def test_changed_processing_config_same_file_and_disabled_rag(rig):
    app, c, _, _ = rig
    info = upload(c).json()["data"]
    drain(app)
    result = c.post(
        "/api/v1/documents/" + info["document_id"] + "/versions",
        headers=auth(),
        data={"extraction_config": json.dumps({"parser_revision": "parser-v2"})},
        files={
            "file": ("faq.json", b'{"question":"Question","answer":"Answer"}', "application/json")
        },
    )
    assert result.status_code == 202 and result.json()["data"]["version"] == 2
    app.state.settings.rag_jobs_enabled = False
    assert (
        c.post(
            "/api/v1/documents/" + info["document_id"] + "/reindex", headers=auth(), json={}
        ).status_code
        == 409
    )


def test_incomplete_document_acl_cannot_activate(rig):
    app, c, backend, _ = rig
    index = backend.index
    backend.index = lambda *args: index(*args)[:1]
    info = upload(c, user="admin", scopes=["class:GS-KPI-01", "class:ML-DEMO-01"]).json()["data"]
    drain(app)
    assert detail(c, info["document_id"])["active_version_id"] is None
    with app.state.db.read() as s:
        assert (
            s.one("SELECT error_code FROM ingestion_jobs WHERE id=:j", j=info["job_id"])[
                "error_code"
            ]
            == "incomplete_document_acl"
        )


def test_wrong_model_cannot_replace_active_and_old_citations_rejected(rig):
    from app.services.outbound_service import citation_valid

    app, c, backend, _ = rig
    original = upload(c).json()["data"]
    drain(app)
    did = original["document_id"]
    with app.state.db.read() as s:
        point = s.one(
            "SELECT * FROM document_chunks WHERE document_version_id=:v", v=original["version_id"]
        )
        citation = {**point, "evidence_excerpt": "Evidence"}
        assert citation_valid(s, {"class_id": "GS-KPI-01"}, citation)
    index = backend.index

    def wrong_model(*args):
        chunks = index(*args)
        for chunk in chunks:
            chunk["embedding_model"] = "WRONG-MODEL"
        return chunks

    backend.index = wrong_model
    pending = c.post(
        "/api/v1/documents/" + did + "/reindex",
        headers=auth(),
        json={"extraction_config": {"embedding_model": "TEST-NEW"}},
    ).json()["data"]
    drain(app)
    assert detail(c, did)["active_version_id"] == original["version_id"]
    with app.state.db.read() as s:
        assert (
            s.one("SELECT error_code FROM ingestion_jobs WHERE id=:j", j=pending["job_id"])[
                "error_code"
            ]
            == "embedding_model_mismatch"
        )
    backend.index = index
    c.post("/api/v1/ingestion-jobs/" + pending["job_id"] + "/retry", headers=auth())
    drain(app)
    with app.state.db.read() as s:
        assert not citation_valid(s, {"class_id": "GS-KPI-01"}, citation)
        # Old points still exist pending cleanup; Backend active gate rejects them.
        assert s.one("SELECT point_id FROM document_chunks WHERE point_id=:p", p=point["point_id"])
