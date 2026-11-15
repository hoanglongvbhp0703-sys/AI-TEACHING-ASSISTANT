# Database hiện hành

SQLite v5 lưu trong `data/gos.db`; DDL tại [schema.sqlite.sql](schema.sqlite.sql).
Qdrant Local lưu vector/text riêng tại `data/qdrant`, file gốc trong `data/uploads`.

Có 29 bảng: tài khoản nhân sự và session/credentials, courses/classes/teacher assignments,
group bindings, access scopes, tài liệu/phiên bản/quyền/chunk manifest, ingestion/cleanup,
sự kiện/quota/memory, RAG audit/citation, ticket/reply/FAQ, outbox và audit/security.
Không còn vai trò student hoặc bảng enrollments. Một số trường user ID nullable giữ dấu
vết nhân sự trong lịch sử; quyền hỏi của Zalo chỉ dựa trên liên kết chat và lớp.

Daily usage và reservation dùng usage_key từ platform/sender, không phải tài khoản đăng
nhập. Ticket không bắt buộc requester_user_id. External message ID là ID do Zalo xác nhận.

Migration v5 tạo bản sao `.pre-v5.db`, kiểm tra toàn vẹn/khóa ngoại trước khi thay DB.
SQLite là DB thực lưu trong file, không phải dữ liệu văn bản thay thế DB.
