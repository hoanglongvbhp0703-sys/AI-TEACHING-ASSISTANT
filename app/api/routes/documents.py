import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile

from app.api.deps import ok, staff
from app.core.errors import AppError, require
from app.schemas.common import Envelope
from app.schemas.documents import ReindexInput
from app.services.access_service import check_class, check_document, document_scopes

router = APIRouter(tags=["Documents & ingestion"])


def parsed(raw, kind):
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        raise AppError(422, "invalid_metadata", "Metadata JSON không hợp lệ.") from None
    require(isinstance(value, kind), 422, "invalid_metadata", "Metadata JSON sai kiểu.")
    return value


async def read_upload(file, settings):
    data = bytearray()
    while part := await file.read(64 * 1024):
        data.extend(part)
        require(
            len(data) <= settings.max_upload_bytes,
            413,
            "file_too_large",
            "File vượt giới hạn upload.",
        )
    return bytes(data)


@router.get("/documents", response_model=Envelope[Any])
def documents(
    request: Request,
    query: str = Query("", max_length=200),
    topic: str = Query("", max_length=200),
    class_id: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user=Depends(staff),
):
    with request.app.state.db.read() as s:
        if class_id:
            check_class(s, user, class_id)
        result = []
        for doc in s.all("SELECT * FROM documents ORDER BY updated_at DESC,id"):
            scopes = document_scopes(s, doc["id"])
            if class_id:
                course = s.one("SELECT course_id FROM classes WHERE id=:c", c=class_id)["course_id"]
                if not set(scopes).intersection({"class:" + class_id, "course:" + course}):
                    continue
            try:
                check_document(s, user, doc["id"])
            except AppError as error:
                if error.status == 403:
                    continue
                raise
            if (
                query.casefold() not in (doc["title"] + " " + doc["topic"]).casefold()
                or topic.casefold() not in doc["topic"].casefold()
            ):
                continue
            current = (
                s.one(
                    "SELECT version FROM document_versions WHERE id=:v", v=doc["active_version_id"]
                )
                if doc["active_version_id"]
                else None
            )
            result.append(
                {
                    **doc,
                    "scope_ids": scopes,
                    "active_version": current["version"] if current else None,
                    "latest_version": (
                        s.one(
                            "SELECT MAX(version) AS n FROM document_versions WHERE document_id=:d",
                            d=doc["id"],
                        )
                        or {}
                    ).get("n"),
                }
            )
        return ok(
            request,
            {
                "items": result[offset : offset + limit],
                "total": len(result),
                "limit": limit,
                "offset": offset,
            },
        )


@router.post("/documents", status_code=202, response_model=Envelope[Any])
async def upload(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=300),
    topic: str = Form(..., min_length=1, max_length=200),
    scope_ids: str = Form(...),
    extraction_config: str = Form("{}"),
    source_code: str | None = Form(None, max_length=100),
    source_version: str | None = Form(None, max_length=100),
    user=Depends(staff),
):
    require(
        bool(title.strip()) and bool(topic.strip()),
        422,
        "invalid_metadata",
        "Cần tên và chủ đề không rỗng.",
    )
    data = await read_upload(file, request.app.state.settings)
    result = request.app.state.documents.upload(
        user,
        request.state.request_id,
        data,
        file.filename,
        title.strip(),
        topic.strip(),
        parsed(scope_ids, list),
        parsed(extraction_config, dict),
        source_code=source_code,
        source_version=source_version,
    )
    if result["status"] == "stored":
        response.status_code = 201
    return ok(request, result)


@router.get("/documents/{document_id}", response_model=Envelope[Any])
def document(document_id: str, request: Request, user=Depends(staff)):
    with request.app.state.db.read() as s:
        doc = check_document(s, user, document_id)
        versions = s.all(
            "SELECT id,version,source_version,status,sha256,original_filename,file_size_bytes,uploaded_at,indexed_at,activated_at,error_code,(SELECT j.id FROM ingestion_jobs j WHERE j.document_version_id=document_versions.id ORDER BY j.created_at DESC,j.rowid DESC LIMIT 1) AS job_id FROM document_versions WHERE document_id=:d ORDER BY version DESC",
            d=document_id,
        )
        return ok(
            request, {**doc, "scope_ids": document_scopes(s, document_id), "versions": versions}
        )


@router.post("/documents/{document_id}/versions", status_code=202, response_model=Envelope[Any])
async def version(
    document_id: str,
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    change_note: str = Form("", max_length=2000),
    extraction_config: str | None = Form(None),
    user=Depends(staff),
):
    data = await read_upload(file, request.app.state.settings)
    result = request.app.state.documents.upload(
        user,
        request.state.request_id,
        data,
        file.filename,
        did=document_id,
        change_note=change_note,
        config=parsed(extraction_config, dict) if extraction_config is not None else None,
    )
    if result["status"] == "unchanged":
        response.status_code = 200
    elif result["status"] == "stored":
        response.status_code = 201
    return ok(request, result)


@router.delete("/documents/{document_id}", response_model=Envelope[Any])
def revoke(document_id: str, request: Request, user=Depends(staff)):
    return ok(
        request, request.app.state.documents.revoke(user, document_id, request.state.request_id)
    )


@router.get("/ingestion-jobs/{job_id}", response_model=Envelope[Any])
def job(job_id: str, request: Request, user=Depends(staff)):
    with request.app.state.db.read() as s:
        return ok(request, request.app.state.documents.job(s, user, job_id))


@router.post("/ingestion-jobs/{job_id}/retry", status_code=202, response_model=Envelope[Any])
def retry(job_id: str, request: Request, user=Depends(staff)):
    return ok(request, request.app.state.documents.retry(user, job_id, request.state.request_id))


@router.post("/documents/{document_id}/reindex", status_code=202, response_model=Envelope[Any])
def reindex(document_id: str, body: ReindexInput, request: Request, user=Depends(staff)):
    return ok(
        request,
        request.app.state.documents.reindex(user, document_id, body, request.state.request_id),
    )
