"""Text-only structured extraction. Page/heading/sheet/FAQ boundaries survive chunking."""

import json
import re
import unicodedata
from pathlib import Path

from app.core.errors import AppError


def normalized(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def blocks(path):
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        for page, source in enumerate(reader.pages, 1):
            text = source.extract_text() or ""
            lines = [normalized(line) for line in text.splitlines() if normalized(line)]
            if lines:
                yield {"text": "\n".join(lines), "page": page, "section_path": lines[0][:200]}
    elif suffix == ".docx":
        from docx import Document

        heading = "Nội dung"
        pending = []
        document = Document(path)
        for item in document.iter_inner_content():
            if hasattr(item, "text"):
                if item.style and item.style.name.startswith("Heading"):
                    if pending:
                        yield {"text": "\n".join(pending), "section_path": heading}
                    heading, pending = item.text, []
                else:
                    pending.append(item.text)
            else:
                pending.extend(" | ".join(cell.text for cell in row.cells) for row in item.rows)
        if pending:
            yield {"text": "\n".join(pending), "section_path": heading}
    elif suffix == ".xlsx":
        from openpyxl import load_workbook

        book = load_workbook(path, read_only=True, data_only=True, keep_links=False)
        try:
            for sheet in book:
                for number, row in enumerate(sheet.iter_rows(values_only=True), 1):
                    text = " | ".join(str(value) if value is not None else "" for value in row)
                    if text.strip(" |"):
                        yield {
                            "text": text,
                            "section_path": sheet.title,
                            "sheet_name": sheet.title,
                            "row_start": number,
                            "row_end": number,
                        }
        finally:
            book.close()
    elif suffix == ".json":
        data = json.loads(Path(path).read_bytes())
        for number, faq in enumerate(data if isinstance(data, list) else [data], 1):
            yield {
                "text": f"Câu hỏi: {faq['question']}\nTrả lời: {faq['answer']}",
                "section_path": f"FAQ {number}",
            }
    else:
        raise AppError(422, "unsupported_source", "Định dạng tài liệu không được hỗ trợ.")


def chunks(path, size=900, overlap=100, fits=None, on_progress=None):
    result = []
    for block in blocks(path):
        text = normalized(block.pop("text"))
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start + (end - start) // 2, end)
                if boundary > start:
                    end = boundary
            while fits and not fits(text[start:end]):
                end = start + (end - start) // 2
                if end <= start:
                    raise AppError(
                        422, "tokenization_failure", "Không thể chia văn bản theo giới hạn model."
                    )
            content = text[start:end].strip()
            if content:
                result.append({**block, "text": content, "chunk_id": f"CH{len(result) + 1:06d}"})
            if end == len(text):
                break
            # Preserve progress even when tokenizer reduces chunks below requested overlap.
            start = max(start + 1, end - min(overlap, (end - start) // 4))
        if on_progress:
            on_progress(len(result))
    if not result:
        raise AppError(
            422, "empty_extracted_text", "Không đọc được văn bản; PDF scan cần OCR trước."
        )
    return result
