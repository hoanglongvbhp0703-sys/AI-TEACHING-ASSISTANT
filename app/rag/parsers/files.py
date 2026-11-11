import io
import json
import zipfile

from app.core.errors import AppError, require

MIMES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".json": "application/json",
}


def validate_file(data, suffix):
    require(suffix in MIMES, 422, "invalid_document", "Chỉ nhận PDF, DOCX, XLSX hoặc FAQ JSON.")
    require(bool(data), 422, "invalid_document", "File rỗng.")
    try:
        if suffix in {".docx", ".xlsx"}:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                require(
                    sum(i.file_size for i in archive.infolist()) <= 50 * 1024 * 1024,
                    422,
                    "invalid_document",
                    "File giải nén vượt giới hạn 50 MB.",
                )
                require(
                    not any(i.flag_bits & 1 for i in archive.infolist()),
                    422,
                    "invalid_document",
                    "Không nhận file được mã hóa.",
                )
        if suffix == ".pdf":
            from pypdf import PdfReader

            require(data.startswith(b"%PDF-"), 422, "invalid_document", "Nội dung không phải PDF.")
            pdf = PdfReader(io.BytesIO(data))
            require(
                not pdf.is_encrypted and len(pdf.pages) > 0,
                422,
                "invalid_document",
                "PDF rỗng hoặc được mã hóa.",
            )
        elif suffix == ".docx":
            from docx import Document

            Document(io.BytesIO(data))
        elif suffix == ".xlsx":
            from openpyxl import load_workbook

            workbook = load_workbook(
                io.BytesIO(data), read_only=True, data_only=True, keep_links=False
            )
            workbook.close()
        else:
            value = json.loads(data)
            pairs = value if isinstance(value, list) else [value]
            require(
                0 < len(pairs) <= 1000
                and all(
                    isinstance(p, dict)
                    and isinstance(p.get("question"), str)
                    and p["question"].strip()
                    and isinstance(p.get("answer"), str)
                    and p["answer"].strip()
                    for p in pairs
                ),
                422,
                "invalid_document",
                "FAQ JSON phải chứa question và answer không rỗng.",
            )
    except AppError:
        raise
    except Exception:
        raise AppError(
            422, "invalid_document", "Không đọc được định dạng hoặc nội dung file."
        ) from None
    return MIMES[suffix]
