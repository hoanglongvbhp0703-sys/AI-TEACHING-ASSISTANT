# 01 — Đọc dự án và quyết định thiết kế

Phiên bản thiết kế 1.0 · 10/11/2026 · GOS Academy AI Teaching Assistant.

## 1. Nguồn đã đọc

| Nguồn trong workspace | Phạm vi đã đối chiếu | Tác động tới thiết kế |
|---|---|---|
| `GOS_Academy_De_bai_Test_AI_Agent_Ho_tro_Hoc_vien_Zalo.pdf`, 3 trang | Đề bài, 7 ca bắt buộc, thang điểm, bàn giao | Hai lớp độc lập; citation, handoff, log chi phí, webhook mock |
| `01_SRS_AI_Agent_RAG.pdf`, 6 trang, v1.1 | AG-01…20, AG-T01…14, metadata, versioning, memory | Qdrant Local; filter trước search; active versions; evidence gate |
| `02_SRS_Backend.pdf`, 8 trang, v1.1 | BE-01…28, BE-T01…18, schema logic, API | FastAPI/SQLite; quota; quyền; ticket/FAQ; jobs/recovery |
| `03_SRS_Frontend.pdf`, 5 trang, v1.1 | FE-01…14, FE-T01…13 | `/demo` hai tab; poll job; ticket/FAQ qua API |
| `GOS_Academy_Bo_tai_lieu_mau_gui_TTS_AI_Zalo/00_Huong_dan_su_dung_bo_hoc_lieu_mau.docx` | M-01…04 | Metadata `class_id`, `doc_id`, `section_id`, `version`; dữ liệu giả lập |
| Cùng thư mục: `01_Giao_trinh_Google_Sheets_KPI_Dashboard.docx` | GS-01…08 và bảng mẫu | Giữ bảng, công thức, mục; không biến bảng bài học thành bảng CRM hệ thống |
| Cùng thư mục: `02_Giao_trinh_AI_Automation_n8n.docx` | AUTO-01…10 | Chống trùng, credentials, quyền từng lớp, xử lý lỗi |
| Cùng thư mục: `03_FAQ_Quy_dinh_lop_hoc_GIA_LAP.docx` | COMMON-01…04, GS-CLASS-01…02, AUTO-CLASS-01…02 | Một file có nhiều phạm vi; cần scope ở cấp chunk |
| Cùng thư mục: `Tin_nhan_mo_phong_TTS.json` | E001…E008 | Fixture cũ cần chuẩn hóa về group/sender và thêm `/hoi` rõ ràng |

Không tìm thấy source code, repository Git, dependency manifest hay database sẵn có. Đây là thiết kế dựa trên đặc tả và học liệu, chưa phải tài liệu reverse-engineer từ ứng dụng đang chạy.

## 2. Phạm vi và thứ tự ưu tiên

1. Bảo toàn các quyết định `[CHỐT]` trong SRS v1.1 ngày 09/11/2026.
2. Dùng đề gốc để kiểm tra tính đầy đủ; các lựa chọn kỹ thuật rộng trong đề gốc không thay thế stack đã chốt trong SRS.
3. Những bổ sung như bảng ledger quota, manifest chunk, bảng cleanup, call-level cost được đánh dấu **[ĐX thiết kế]**. Chúng làm rõ độ bền dữ liệu, không thêm nghiệp vụ sản phẩm mới.

Đề gốc có hai mốc tiến độ 07–10 và 03–05 ngày ở hai vị trí; tài liệu này không suy ra deadline triển khai. SRS dùng ví dụ `AI01/GS01`, còn học liệu dùng `AUTO-N8N-01/GS-KPI-01`; chọn **mã học liệu làm class ID chuẩn**, hai tên ngắn chỉ là nhãn demo, không tạo thêm hai lớp.

## 3. Bản đồ nghiệp vụ

| Khối | Chức năng | SQLite | Ngoài SQLite |
|---|---|---|---|
| Người dùng/lớp | Student/Teacher/Admin/Service; nhiều lớp/người | users, courses, classes, enrollments, teacher_assignments | Demo tokens trong môi trường |
| Tích hợp | Nhóm và sender bên ngoài → danh tính nội bộ | group_bindings, external_identities, webhook_events | Mock adapter |
| Quota/memory | 30 câu/ngày; 5 lượt; TTL 30 phút | daily_usage, quota_reservations, conversation_sessions, messages | Không có Redis |
| Học liệu | Upload, tìm tên/chủ đề, version, thu hồi | access_scopes, documents, document_access, document_versions, document_chunks | uploads, Qdrant |
| RAG | Retrieve/rerank/evidence/generate/validate | rag_runs, rag_run_attempts, rag_citations | Embedding/reranker/LLM adapters |
| Handoff | Open → assigned → answered → closed | support_tickets, ticket_replies | Mock outbound |
| FAQ | Draft → approved → ingestion | faq_entries, documents, document_versions | FAQ JSON do server sinh |
| Độ bền | Retry/lease, cleanup, outbox | ingestion_jobs, cleanup_jobs, outbound_messages | Runner trong một process |
| Truy vết | Metrics, chi phí, lỗi, thay đổi quyền/tài liệu | security_events, audit_logs và các bảng nghiệp vụ | JSON logs đã che dữ liệu |

## 4. Các điểm phải làm rõ khi triển khai

### Quyền khóa học và FAQ chung

Không có khóa học tên `COMMON` để học viên tự tham gia. `COMMON` trong học liệu chỉ là nhãn nội dung. COMMON-01…04 có thể được cấp `class:GS-KPI-01` và `class:AUTO-N8N-01`; các mục GS-CLASS chỉ có scope lớp GS; AUTO-CLASS chỉ có scope lớp AUTO. Nếu sau này dùng scope khóa học, Backend phải kiểm tra quyền **toàn bộ ảnh hưởng** trước khi teacher cấp scope đó.

### File FAQ nhiều phạm vi

`document_access` cấp quyền cho toàn bộ tài liệu trong MVP. Mọi chunk kế thừa tất cả scope của tài liệu; section/page chỉ dùng trích dẫn. Không dùng section_scopes. Nội dung có quyền khác nhau phải tách thành tài liệu riêng. Qdrant adapter vẫn tạo point cho mỗi cặp chunk + scope, còn active version do Backend quyết định.

### Input JSON mẫu khác hợp đồng webhook

JSON gốc có `class_id`, `sender_id`, `received_at` và câu hỏi chưa có `/hoi`. Một script fixture tin cậy sẽ map class → group từ seed, sender → external identity, `received_at` → `sent_at`; thêm `/hoi ` để chạy ca hỏi đáp. Giữ nguyên JSON gốc. Endpoint webhook vẫn resolve class từ group trong DB; không lấy class từ payload để cấp quyền.

### Quy trình cập nhật, concurrency và quota

- SQLite, Qdrant và filesystem không có một transaction chung. Index trước, đổi active pointer sau; cleanup có retry. SQLite quyết định nguồn nào được phép dùng.
- Claim event và quota bằng transaction ngắn; không giữ write transaction lúc gọi model.
- `quota_reservations` chống tăng lại khi event retry, đồng thời cho phép hoàn quota đúng một lần nếu lỗi trước khi bắt đầu RAG. Lỗi sau khi RAG đã bắt đầu vẫn giữ một lượt theo chính sách đề xuất được mô tả trong hợp đồng xử lý.
- Một logical RAG run/event nhưng có nhiều provider call; cần ghi cả các lần retry để không hụt thống kê chi phí.
- Ticket chỉ chuyển `answered` khi phản hồi giảng viên đã được Mock Sender lưu thành công.

### Quyền và auth MVP

`role` đơn trên user được backend kiểm tra, không tin role từ UI. Admin cấp hồ sơ và credential cho giảng viên; học viên có enrollment và STT theo lớp, đăng nhập bằng picker lớp/STT cùng mật khẩu. Giả lập lấy roster từ metadata server; webhook kiểm tra identity/enrollment độc lập. Xem [thiết kế phân quyền lớp](12-class-access-and-rosters.md).

### Quy tắc nhóm đã có lịch sử

**[ĐX thiết kế]** Không rebind một `group_binding` sang lớp khác trong MVP. Giữ UNIQUE(platform, external_group_id), đánh dấu inactive khi dừng nhóm. Để tái sử dụng cùng external group cho lớp mới trong tương lai cần mô hình binding có khoảng hiệu lực và resolve theo thời điểm nhận; không sửa class_id khiến lịch sử đổi lớp.

## 5. Đầu ra lần thiết kế này

Tài liệu schema + ERD + từ điển cột; DDL SQLite; hợp đồng Qdrant/file/API; mô tả transaction và recovery; khung thư mục thật; script kiểm tra thiết kế. Không coi các placeholder là mã nguồn đã triển khai; kiểm thử nghiệp vụ API/RAG vẫn cần thực hiện khi viết ứng dụng.
