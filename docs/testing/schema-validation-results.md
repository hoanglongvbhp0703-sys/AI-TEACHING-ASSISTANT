# Kết quả kiểm tra DDL thiết kế

Ngày chạy: **10/11/2026**. Lệnh: `python3 scripts/validate_schema.py`. SQLite: **3.53.4**. Kết quả thực tế: **18/18 kiểm tra đạt**; mọi database thử có `PRAGMA foreign_key_check` rỗng và `PRAGMA integrity_check = ok`.

| Phạm vi đã chạy | Kết quả |
|---|---|
| Khởi tạo đủ 28 bảng, bật foreign keys | Đạt |
| Chặn tham chiếu user không tồn tại | Đạt |
| Dedup theo external event ID, không dedup theo text | Đạt |
| Chặn rebind nhóm và event gắn sai class | Đạt |
| Scope phải có tài nguyên thật và ID canonical | Đạt |
| Active version phải cùng document | Đạt |
| Version failed không thay bản active; rollback giữ V1 | Đạt |
| Chuyển active/revoke trong transaction; chỉ một active version | Đạt |
| Hash lặp được phép restore; version number trùng bị chặn | Đạt |
| Chunk scope ngoài document_access bị chặn | Đạt |
| Chỉ một ingestion job live/version | Đạt |
| Message không ghép session lớp khác; chỉ một open session/group/class | Đạt |
| Một ticket/run/bot_result mỗi event, teacher_answer riêng | Đạt |
| Reservation duy nhất; hoàn quota có điều kiện đúng một lần; CHECK 0…30 | Đạt |
| Hai connection tranh lượt thứ 30: một nhận, một bị từ chối | Đạt |
| FAQ approved phải có actor/document/timestamp | Đạt |
| Provider call giữ cost unknown=NULL, có một owner, call_key duy nhất | Đạt |
| JSON sai/enum ngoài tập bị chặn | Đạt |

Kiểm tra thêm: các link tài liệu nội bộ trỏ đúng tệp; hai JSON fixture parse thành công; thư mục `data/` chưa có database hoặc file runtime, chỉ có `.gitkeep`.

Giới hạn: script chạy DDL và SQL pattern minh họa trên database tạm. Chưa có service implementation, FastAPI endpoints, Qdrant integration, model calls hay UI để kiểm thử. Các kết quả trên không xác nhận chất lượng retrieval/grounding, quyền runtime, redaction, crash recovery hoặc thời gian đáp ứng. Kế hoạch những phần đó nằm trong [ma trận nghiệm thu](06-acceptance-matrix.md).
