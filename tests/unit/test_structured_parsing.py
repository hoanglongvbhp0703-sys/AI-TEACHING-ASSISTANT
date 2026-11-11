from app.rag.parsers.structure import chunks


def test_docx_headings_and_token_budget(tmp_path):
    from docx import Document

    path = tmp_path / "source.docx"
    doc = Document()
    doc.add_heading("Chương Một", level=1)
    doc.add_paragraph("Học máy là một lĩnh vực. " * 60)
    doc.add_heading("Chương Hai", level=1)
    doc.add_paragraph("Câu trả lời riêng biệt ở phần hai.")
    doc.save(path)
    pieces = chunks(path, size=300, overlap=40, fits=lambda text: len(text) < 180)
    assert {p["section_path"] for p in pieces} == {"Chương Một", "Chương Hai"}
    assert all(len(p["text"]) < 180 for p in pieces)
    assert len({p["chunk_id"] for p in pieces}) == len(pieces)


def test_spreadsheet_preserves_sheet_and_rows(tmp_path):
    from openpyxl import Workbook

    path = tmp_path / "source.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "Điểm"
    sheet.append(["Tên", "Điểm"])
    sheet.append(["An", 9])
    book.save(path)
    pieces = chunks(path)
    assert pieces[1]["sheet_name"] == "Điểm" and pieces[1]["row_start"] == 2
    assert "An | 9" in pieces[1]["text"]
