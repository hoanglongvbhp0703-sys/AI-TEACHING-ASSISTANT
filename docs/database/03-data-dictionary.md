# 03 — Từ điển dữ liệu SQLite

Tài liệu cột của **30 bảng** trong [DDL thiết kế](schema.sqlite.sql). Cấu trúc, NULL/default/PK/FK/index được đối chiếu trực tiếp bằng SQLite PRAGMA; mô tả nghiệp vụ theo SRS và bản thiết kế. Nếu thay DDL cần cập nhật tài liệu này cùng migration.

`Bắt buộc` = NOT NULL; `—` ở default nghĩa ứng dụng phải điền hoặc để NULL theo cột. ID/timestamp không có default ẩn. PK ghép hiển thị vị trí trong khóa. CHECK/enum, partial index và DEFERRABLE xem DDL; index UNIQUE không có nghĩa nullable field bắt buộc.

Các trường `*_redacted` và `*_json` không tự che dữ liệu bằng SQL; service chịu trách nhiệm redaction/shape validation. Mọi timestamp UTC cố định; local_date theo ngày Việt Nam.

## 1. `users`

Một role/tài khoản cho MVP; auth demo bằng token config, không có password/token trong bảng.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `display_name` | TEXT | Bắt buộc | — | — | Tên hiển thị; không dùng làm khóa định danh. |
| `role` | TEXT | Bắt buộc | — | — | Vai trò; users là quyền tài khoản, messages là vai trò trong hội thoại. |
| `is_active` | INTEGER | Bắt buộc | 1 | — | Còn hiệu lực (1) hoặc ngừng sử dụng (0). |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |
| `updated_at` | TEXT | Bắt buộc | — | — | Thời điểm cập nhật UTC, ứng dụng tự điền. |

## 2. `courses`

Khóa học chứa nhiều lớp; không tạo course COMMON từ nhãn học liệu.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `name` | TEXT | Bắt buộc | — | — | Tên khóa học/lớp. |
| `status` | TEXT | Bắt buộc | 'active' | — | Trạng thái; tập giá trị và transition xem thiết kế/DDL. |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |
| `updated_at` | TEXT | Bắt buộc | — | — | Thời điểm cập nhật UTC, ứng dụng tự điền. |

## 3. `classes`

Không thêm teacher_id; nhiều giảng viên qua teacher_assignments.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `course_id` | TEXT | Bắt buộc | — | FK → courses.id | Khóa học sở hữu hoặc được cấp phạm vi. |
| `name` | TEXT | Bắt buộc | — | — | Tên khóa học/lớp. |
| `bot_enabled` | INTEGER | Bắt buộc | 1 | — | Cờ cho phép bot xử lý /hoi trong lớp. |
| `status` | TEXT | Bắt buộc | 'active' | — | Trạng thái; tập giá trị và transition xem thiết kế/DDL. |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |
| `updated_at` | TEXT | Bắt buộc | — | — | Thời điểm cập nhật UTC, ứng dụng tự điền. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(course_id)` → `courses(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(course_id)`.

## 4. `enrollments`

Mỗi học viên có thể tham gia nhiều lớp; role/status cần service kiểm tra.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `user_id` | TEXT | Bắt buộc | — | PK(1); FK → users.id | Người dùng nội bộ đã resolve; quota theo user trên mọi lớp. |
| `class_id` | TEXT | Bắt buộc | — | PK(2); FK → classes.id | Lớp nội bộ đã xác thực. |
| `status` | TEXT | Bắt buộc | 'active' | — | Trạng thái; tập giá trị và transition xem thiết kế/DDL. |
| `joined_at` | TEXT | Bắt buộc | — | — | Thời điểm học viên tham gia lớp. |
| `updated_at` | TEXT | Bắt buộc | — | — | Thời điểm cập nhật UTC, ứng dụng tự điền. |

**Bổ sung migration v3:** `student_number` INTEGER dương, unique cùng class_id, trigger cấp tăng dần trong lớp; không đổi sau khi đã cấp. Đây là STT học viên theo enrollment, không phải user_id.

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(class_id)` → `classes(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(user_id)` → `users(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(class_id, status)`.

## 5. `teacher_assignments`

Nhiều teacher/lớp, nhiều lớp/teacher; role được kiểm tra ở service.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `teacher_id` | TEXT | Bắt buộc | — | PK(1); FK → users.id | Giảng viên nội bộ; service kiểm tra role và assignment. |
| `class_id` | TEXT | Bắt buộc | — | PK(2); FK → classes.id | Lớp nội bộ đã xác thực. |
| `is_active` | INTEGER | Bắt buộc | 1 | — | Còn hiệu lực (1) hoặc ngừng sử dụng (0). |
| `assigned_at` | TEXT | Bắt buộc | — | — | Thời điểm phân công giảng viên. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(class_id)` → `classes(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(teacher_id)` → `users(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(class_id, is_active)`.

## 6. `group_bindings`

MVP không rebind class sau khi tạo; trigger chặn đổi class_id. External group unique trong platform.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `class_id` | TEXT | Bắt buộc | — | FK → classes.id | Lớp nội bộ đã xác thực. |
| `platform` | TEXT | Bắt buộc | — | — | Namespace adapter, MVP là mock_zalo; không nhận namespace tùy ý từ client. |
| `external_group_id` | TEXT | Bắt buộc | — | — | ID nhóm bên nền tảng, UNIQUE cùng platform. |
| `display_name` | TEXT | Bắt buộc | — | — | Tên hiển thị; không dùng làm khóa định danh. |
| `is_active` | INTEGER | Bắt buộc | 1 | — | Còn hiệu lực (1) hoặc ngừng sử dụng (0). |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(class_id)` → `classes(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(class_id, is_active)`.
- UNIQUE `(id, class_id)`.
- UNIQUE `(platform, external_group_id)`.

## 7. `external_identities`

Một external sender trong namespace platform chỉ map một user.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `user_id` | TEXT | Bắt buộc | — | FK → users.id | Người dùng nội bộ đã resolve; quota theo user trên mọi lớp. |
| `platform` | TEXT | Bắt buộc | — | — | Namespace adapter, MVP là mock_zalo; không nhận namespace tùy ý từ client. |
| `external_sender_id` | TEXT | Bắt buộc | — | — | ID người gửi bên nền tảng, UNIQUE cùng platform. |
| `is_bot` | INTEGER | Bắt buộc | 0 | — | Danh tính bot cần bỏ qua để ngăn vòng lặp. |
| `is_active` | INTEGER | Bắt buộc | 1 | — | Còn hiệu lực (1) hoặc ngừng sử dụng (0). |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(user_id)` → `users(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(user_id)`.
- UNIQUE `(platform, external_sender_id)`.

## 8. `access_scopes`

[ĐX] Scope có FK thật. CHECK bảo đảm đúng một tài nguyên và ID canonical.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `scope_type` | TEXT | Bắt buộc | — | — | course hoặc class; đúng một trong course_id/class_id được điền. |
| `course_id` | TEXT | Cho phép | — | FK → courses.id | Khóa học sở hữu hoặc được cấp phạm vi. |
| `class_id` | TEXT | Cho phép | — | FK → classes.id | Lớp nội bộ đã xác thực. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(class_id)` → `classes(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(course_id)` → `courses(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

## 9. `documents`

Active pointer FK ghép cùng document, DEFERRABLE. Chỉ dùng active pointer để cấp version hiện hành.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1); FK → document_versions.document_id | ID nội bộ bất biến, ứng dụng sinh. |
| `title` | TEXT | Bắt buộc | — | — | Tiêu đề tài liệu hiển thị/tìm kiếm; tên trùng vẫn là tài liệu khác nếu document_id khác. |
| `topic` | TEXT | Bắt buộc | — | — | Chủ đề để quản lý/tìm kiếm; chunk có thể có topic cụ thể hơn document. |
| `source_code` | TEXT | Cho phép | — | — | Mã tài liệu nguồn, ví dụ DOC-GS-01; không phải khóa dedup file. |
| `source_kind` | TEXT | Bắt buộc | — | — | file từ upload hoặc faq từ bản duyệt giảng viên. |
| `status` | TEXT | Bắt buộc | 'draft' | — | Trạng thái; tập giá trị và transition xem thiết kế/DDL. |
| `active_version_id` | TEXT | Cho phép | — | FK → document_versions.id | Version duy nhất được phép retrieval; NULL khi draft/revoked. |
| `revision` | INTEGER | Bắt buộc | 0 | — | Số revision tăng khi thay đổi, dùng optimistic concurrency/CAS. |
| `created_by` | TEXT | Bắt buộc | — | FK → users.id | Actor tạo tài nguyên. |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |
| `updated_at` | TEXT | Bắt buộc | — | — | Thời điểm cập nhật UTC, ứng dụng tự điền. |
| `deleted_at` | TEXT | Cho phép | — | — | Thời điểm thu hồi tài liệu; không đồng nghĩa file đã bị xóa. |
| `deleted_by` | TEXT | Cho phép | — | FK → users.id | Actor thu hồi tài liệu. |
| `delete_reason` | TEXT | Cho phép | — | — | Lý do thu hồi tùy chọn, đã loại thông tin nhạy cảm. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(id, active_version_id)` → `document_versions(document_id, id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(deleted_by)` → `users(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(created_by)` → `users(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(topic, status, updated_at)`.

## 10. `document_access`

Whitelist scope tối đa tài liệu; không cấp mọi scope này cho mọi chunk một cách mặc định.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `document_id` | TEXT | Bắt buộc | — | PK(1); FK → documents.id | Tài liệu logic cố định qua nhiều version. |
| `scope_id` | TEXT | Bắt buộc | — | PK(2); FK → access_scopes.id | Canonical scope course:<id> hoặc class:<id>; FK access_scopes hoặc document_access. |
| `granted_by` | TEXT | Bắt buộc | — | FK → users.id | Actor cấp phạm vi tài liệu. |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(granted_by)` → `users(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(scope_id)` → `access_scopes(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(document_id)` → `documents(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(scope_id, document_id)`.

## 11. `document_versions`

File/config bất biến theo version. Không UNIQUE hash để cho phép restore nội dung cũ bằng version mới.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `document_id` | TEXT | Bắt buộc | — | FK → documents.id | Tài liệu logic cố định qua nhiều version. |
| `version` | INTEGER | Bắt buộc | — | — | Số phiên bản tăng dần trong một document, bắt đầu từ 1. |
| `source_version` | TEXT | Cho phép | — | — | Nhãn phiên bản từ học liệu gốc, ví dụ TEST-1.0; khác số version hệ thống. |
| `sha256` | TEXT | Bắt buộc | — | — | SHA-256 bytes file gốc, 64 ký tự hex do ứng dụng kiểm tra. |
| `file_path` | TEXT | Bắt buộc | — | — | Đường dẫn tương đối an toàn trong uploads, do server sinh; không nhận path tùy ý. |
| `original_filename` | TEXT | Bắt buộc | — | — | Tên gốc chỉ để hiển thị/audit; không dùng tạo đường dẫn. |
| `mime_type` | TEXT | Bắt buộc | — | — | MIME thực được kiểm tra; PDF/DOCX/XLSX/FAQ JSON theo parser. |
| `file_size_bytes` | INTEGER | Bắt buộc | — | — | Kích thước file không âm, đơn vị byte. |
| `status` | TEXT | Bắt buộc | 'queued' | — | Trạng thái; tập giá trị và transition xem thiết kế/DDL. |
| `extraction_config_json` | TEXT | Bắt buộc | '{}' | — | JSON model/parser/chunk parameters đã được xác thực; bất biến theo version. Không chứa ACL theo chương trong MVP. |
| `parser_version` | TEXT | Cho phép | — | — | Định danh parser/config release để tái lập ingestion. |
| `embedding_model` | TEXT | Cho phép | — | — | Embedding space/model đã dùng để index; không trộn trong collection. |
| `vector_size` | INTEGER | Cho phép | — | — | Số chiều vector theo model thực; NULL trước khi xác định. |
| `chunk_count` | INTEGER | Bắt buộc | 0 | — | Số logical chunks của version; không đếm lặp theo scope. |
| `point_count` | INTEGER | Bắt buộc | 0 | — | Số vector points/chunk-scope pairs của version. |
| `change_note` | TEXT | Cho phép | — | — | Mô tả thay đổi version do giảng viên cung cấp. |
| `uploaded_by` | TEXT | Bắt buộc | — | FK → users.id | Actor upload; role và scope được service kiểm tra. |
| `uploaded_at` | TEXT | Bắt buộc | — | — | Thời điểm nhận upload UTC. |
| `indexed_at` | TEXT | Cho phép | — | — | Thời điểm index/verify hoàn thành UTC; NULL khi chưa hoàn tất. |
| `activated_at` | TEXT | Cho phép | — | — | Thời điểm chuyển active UTC; NULL nếu chưa được kích hoạt. |
| `error_code` | TEXT | Cho phép | — | — | Mã lỗi ổn định; không lưu traceback/secret thô. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(uploaded_by)` → `users(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(document_id)` → `documents(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- UNIQUE `(document_id)` WHERE status='active'.
- UNIQUE `(document_id, id)`.
- UNIQUE `(document_id, version)`.

## 12. `document_chunks`

[ĐX] Một hàng/point/chunk-scope pair; full content và vector ở Qdrant. Giữ hàng sau vector cleanup để audit citation.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `point_id` | TEXT | Bắt buộc | — | PK(1) | UUID deterministic của một version/chunk/scope trong Qdrant, cũng là provenance ID. |
| `document_id` | TEXT | Bắt buộc | — | FK → document_access.document_id, document_versions.document_id | Tài liệu logic cố định qua nhiều version. |
| `document_version_id` | TEXT | Bắt buộc | — | FK → document_versions.id | ID version bất biến, không phải version number. |
| `chunk_id` | TEXT | Bắt buộc | — | — | ID logical chunk trong version, nhiều scope có thể chung chunk_id. |
| `scope_id` | TEXT | Bắt buộc | — | FK → document_access.scope_id | Canonical scope course:<id> hoặc class:<id>; FK access_scopes hoặc document_access. |
| `section_id` | TEXT | Cho phép | — | — | Mã mục nguồn, ví dụ GS-02, COMMON-01. |
| `section_path` | TEXT | Cho phép | — | — | Chuỗi heading/chương/mục gốc, không bịa khi không xác định. |
| `topic` | TEXT | Bắt buộc | — | — | Chủ đề để quản lý/tìm kiếm; chunk có thể có topic cụ thể hơn document. |
| `page` | INTEGER | Cho phép | — | — | Số trang PDF nguồn, bắt đầu 1; NULL nếu không có trang thực. |
| `sheet_name` | TEXT | Cho phép | — | — | Tên sheet XLSX khi có. |
| `row_start` | INTEGER | Cho phép | — | — | Dòng bắt đầu trong sheet, 1-based; NULL nếu không áp dụng. |
| `row_end` | INTEGER | Cho phép | — | — | Dòng cuối trong sheet, >= row_start khi được điền. |
| `content_sha256` | TEXT | Bắt buộc | — | — | Hash nội dung chunk đã normalize để kiểm tra đồng bộ, 64 ký tự. |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |
| `indexed_at` | TEXT | Cho phép | — | — | Thời điểm index/verify hoàn thành UTC; NULL khi chưa hoàn tất. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(document_id, scope_id)` → `document_access(document_id, scope_id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(document_id, document_version_id)` → `document_versions(document_id, id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(document_version_id, scope_id)`.
- UNIQUE `(document_version_id, chunk_id, scope_id)`.

## 13. `ingestion_jobs`

Một live job/version bằng partial unique; job mới chỉ sau terminal. Retry cần lease/fencing.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `document_version_id` | TEXT | Bắt buộc | — | FK → document_versions.id | ID version bất biến, không phải version number. |
| `status` | TEXT | Bắt buộc | 'queued' | — | Trạng thái; tập giá trị và transition xem thiết kế/DDL. |
| `stage` | TEXT | Bắt buộc | 'parse' | — | Bước pipeline/call; có query_rewrite, query_embed, rerank, generate, ingestion_embed. |
| `attempts` | INTEGER | Bắt buộc | 0 | — | Số lần runner claim/thử xử lý, bắt đầu 0. |
| `max_attempts` | INTEGER | Bắt buộc | 3 | — | Giới hạn retry dương; mặc định thiết kế 3. |
| `chunks_indexed` | INTEGER | Bắt buộc | 0 | — | Số logical chunks đã ghi/verify theo tiến độ. |
| `points_indexed` | INTEGER | Bắt buộc | 0 | — | Số points đã ghi/verify; có thể lớn hơn logical chunks. |
| `lease_token` | TEXT | Cho phép | — | — | Fencing token mỗi lần claim; completion chỉ được ghi nếu token khớp. |
| `lease_expires_at` | TEXT | Cho phép | — | — | Hạn lease UTC; job đang chạy cần renew hoặc timeout trước hạn. |
| `next_attempt_at` | TEXT | Bắt buộc | — | — | Thời điểm sớm nhất runner được claim/retry UTC. |
| `error_code` | TEXT | Cho phép | — | — | Mã lỗi ổn định; không lưu traceback/secret thô. |
| `error_message_redacted` | TEXT | Cho phép | — | — | Mô tả lỗi đã che thông tin nhạy cảm cho teacher/operator. |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |
| `started_at` | TEXT | Cho phép | — | — | Thời điểm bắt đầu UTC. |
| `finished_at` | TEXT | Cho phép | — | — | Thời điểm kết thúc UTC, NULL khi chưa terminal. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(document_version_id)` → `document_versions(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(status, next_attempt_at)`.
- UNIQUE `(document_version_id)` WHERE status IN ('queued','processing').

## 14. `cleanup_jobs`

[ĐX] Một job/version/kind; retry bằng UPDATE cùng job, không tạo hàng trùng.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `document_version_id` | TEXT | Bắt buộc | — | FK → document_versions.id | ID version bất biến, không phải version number. |
| `cleanup_kind` | TEXT | Bắt buộc | — | — | Dọn vectors hoặc file; file cleanup chỉ bật khi chốt retention. |
| `status` | TEXT | Bắt buộc | 'queued' | — | Trạng thái; tập giá trị và transition xem thiết kế/DDL. |
| `attempts` | INTEGER | Bắt buộc | 0 | — | Số lần runner claim/thử xử lý, bắt đầu 0. |
| `max_attempts` | INTEGER | Bắt buộc | 3 | — | Giới hạn retry dương; mặc định thiết kế 3. |
| `lease_token` | TEXT | Cho phép | — | — | Fencing token mỗi lần claim; completion chỉ được ghi nếu token khớp. |
| `lease_expires_at` | TEXT | Cho phép | — | — | Hạn lease UTC; job đang chạy cần renew hoặc timeout trước hạn. |
| `next_attempt_at` | TEXT | Bắt buộc | — | — | Thời điểm sớm nhất runner được claim/retry UTC. |
| `error_code` | TEXT | Cho phép | — | — | Mã lỗi ổn định; không lưu traceback/secret thô. |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |
| `finished_at` | TEXT | Cho phép | — | — | Thời điểm kết thúc UTC, NULL khi chưa terminal. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(document_version_id)` → `document_versions(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(status, next_attempt_at)`.
- UNIQUE `(document_version_id, cleanup_kind)`.

## 15. `webhook_events`

Durable queue và dedup; raw_* chỉ là external identifier, không lưu nguyên HTTP body.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `event_key` | TEXT | Bắt buộc | — | PK(1) | ID event nội bộ; dedup ngoại vi là cặp platform/external_event_id. |
| `request_id` | TEXT | Bắt buộc | — | — | Correlation ID truy vết request; không chứa credentials. |
| `platform` | TEXT | Bắt buộc | — | — | Namespace adapter, MVP là mock_zalo; không nhận namespace tùy ý từ client. |
| `external_event_id` | TEXT | Bắt buộc | — | — | Event ID ổn định từ adapter; giữ nguyên qua delivery retry. |
| `raw_group_id` | TEXT | Bắt buộc | — | — | ID nhóm bên ngoài để lookup; raw ở đây là định danh, không phải raw payload. |
| `raw_sender_id` | TEXT | Bắt buộc | — | — | ID sender bên ngoài để lookup; không phải dữ liệu xác thực. |
| `group_binding_id` | TEXT | Cho phép | — | FK → group_bindings.id | ID nội bộ của quan hệ nhóm–lớp; FK ghép đảm bảo lớp khớp. |
| `class_id` | TEXT | Cho phép | — | FK → group_bindings.class_id, classes.id | Lớp nội bộ đã xác thực. |
| `user_id` | TEXT | Cho phép | — | FK → users.id | Người dùng nội bộ đã resolve; quota theo user trên mọi lớp. |
| `question_redacted` | TEXT | Cho phép | — | — | Câu hỏi đã che dữ liệu nhạy cảm; không lưu toàn bộ chat thường. |
| `payload_sha256` | TEXT | Bắt buộc | — | — | Hash payload đã canonicalize, phát hiện event ID cũ có body khác; không lưu body thô. |
| `reply_to_external_event_id` | TEXT | Cho phép | — | — | ID tin nguồn bên nền tảng; có thể không tồn tại nội bộ. |
| `status` | TEXT | Bắt buộc | 'queued' | — | Trạng thái; tập giá trị và transition xem thiết kế/DDL. |
| `outcome_code` | TEXT | Cho phép | — | — | Kết quả nghiệp vụ: answered/insufficient_evidence/blocked/quota_exceeded/...; service dùng constants. |
| `accepted_at` | TEXT | Cho phép | — | — | Thời điểm server tiếp nhận quota; NULL nếu ignored/rejected trước quota. |
| `processing_started_at` | TEXT | Cho phép | — | — | Thời điểm runner bắt đầu xử lý event UTC. |
| `attempts` | INTEGER | Bắt buộc | 0 | — | Số lần runner claim/thử xử lý, bắt đầu 0. |
| `max_attempts` | INTEGER | Bắt buộc | 3 | — | Giới hạn retry dương; mặc định thiết kế 3. |
| `lease_token` | TEXT | Cho phép | — | — | Fencing token mỗi lần claim; completion chỉ được ghi nếu token khớp. |
| `lease_expires_at` | TEXT | Cho phép | — | — | Hạn lease UTC; job đang chạy cần renew hoặc timeout trước hạn. |
| `next_attempt_at` | TEXT | Bắt buộc | — | — | Thời điểm sớm nhất runner được claim/retry UTC. |
| `sent_at` | TEXT | Bắt buộc | — | — | webhook: thời điểm nguồn gửi (tham khảo); outbound: lúc mock lưu thành công; đều chuẩn UTC. |
| `received_at` | TEXT | Bắt buộc | — | — | Thời điểm server nhận event UTC, không lấy từ client làm đồng hồ hệ thống. |
| `completed_at` | TEXT | Cho phép | — | — | Thời điểm event kết thúc UTC. |
| `error_code` | TEXT | Cho phép | — | — | Mã lỗi ổn định; không lưu traceback/secret thô. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(group_binding_id, class_id)` → `group_bindings(id, class_id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(user_id)` → `users(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(class_id)` → `classes(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(class_id, received_at)`.
- INDEX `(user_id, accepted_at)`.
- INDEX `(status, next_attempt_at)`.
- UNIQUE `(event_key, class_id, group_binding_id)`.
- UNIQUE `(platform, external_event_id)`.

## 16. `daily_usage`

Counter quota tổng mọi lớp/người/ngày; cập nhật cùng reservation trong transaction.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `user_id` | TEXT | Bắt buộc | — | PK(1); FK → users.id | Người dùng nội bộ đã resolve; quota theo user trên mọi lớp. |
| `local_date` | TEXT | Bắt buộc | — | PK(2) | Ngày quota tại Asia/Ho_Chi_Minh, YYYY-MM-DD; reservation giữ ngày này khi retry. |
| `accepted_count` | INTEGER | Bắt buộc | 0 | — | Số reservation reserved+charged, giới hạn 0..30; không gồm released. |
| `updated_at` | TEXT | Bắt buộc | — | — | Thời điểm cập nhật UTC, ứng dụng tự điền. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(user_id)` → `users(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

## 17. `quota_reservations`

[ĐX] Ledger một reservation/event; chống tính lại/hoàn lại. Counter consistency do transaction service.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `event_key` | TEXT | Bắt buộc | — | PK(1); FK → webhook_events.event_key | ID event nội bộ; dedup ngoại vi là cặp platform/external_event_id. |
| `user_id` | TEXT | Bắt buộc | — | FK → daily_usage.user_id | Người dùng nội bộ đã resolve; quota theo user trên mọi lớp. |
| `local_date` | TEXT | Bắt buộc | — | FK → daily_usage.local_date | Ngày quota tại Asia/Ho_Chi_Minh, YYYY-MM-DD; reservation giữ ngày này khi retry. |
| `status` | TEXT | Bắt buộc | — | — | Trạng thái; tập giá trị và transition xem thiết kế/DDL. |
| `reserved_at` | TEXT | Bắt buộc | — | — | Thời điểm giữ một lượt quota. |
| `charged_at` | TEXT | Cho phép | — | — | Thời điểm bắt đầu RAG và xác nhận tính lượt. |
| `released_at` | TEXT | Cho phép | — | — | Thời điểm hoàn reservation trước khi bắt đầu RAG. |
| `release_reason` | TEXT | Cho phép | — | — | Lý do hoàn lượt đã được chuẩn hóa/che dữ liệu. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(user_id, local_date)` → `daily_usage(user_id, local_date)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(event_key)` → `webhook_events(event_key)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(user_id, local_date, status)`.

## 18. `conversation_sessions`

Một open session/class/group bằng partial unique index; TTL kiểm tra ở service.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `class_id` | TEXT | Bắt buộc | — | FK → group_bindings.class_id | Lớp nội bộ đã xác thực. |
| `group_binding_id` | TEXT | Bắt buộc | — | FK → group_bindings.id | ID nội bộ của quan hệ nhóm–lớp; FK ghép đảm bảo lớp khớp. |
| `status` | TEXT | Bắt buộc | 'open' | — | Trạng thái; tập giá trị và transition xem thiết kế/DDL. |
| `started_at` | TEXT | Bắt buộc | — | — | Thời điểm bắt đầu UTC. |
| `last_hoi_at` | TEXT | Bắt buộc | — | — | Thời điểm server tiếp nhận /hoi mới nhất trong session; retry không gia hạn lần hai. |
| `expires_at` | TEXT | Bắt buộc | — | — | last_hoi_at + 30 phút; app quyết định expired khi now lớn hơn hạn. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(group_binding_id, class_id)` → `group_bindings(id, class_id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- UNIQUE `(class_id, group_binding_id)` WHERE status='open'.
- UNIQUE `(id, class_id, group_binding_id)`.

## 19. `messages`

FK ghép bảo đảm event và session cùng group/class; một message/event/kind. Lấy 5 cặp hoàn chỉnh ở service.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `session_id` | TEXT | Bắt buộc | — | FK → conversation_sessions.id | Session chung nhóm/lớp chứa interaction. |
| `event_key` | TEXT | Bắt buộc | — | FK → webhook_events.event_key | ID event nội bộ; dedup ngoại vi là cặp platform/external_event_id. |
| `class_id` | TEXT | Bắt buộc | — | FK → webhook_events.class_id, conversation_sessions.class_id | Lớp nội bộ đã xác thực. |
| `group_binding_id` | TEXT | Bắt buộc | — | FK → webhook_events.group_binding_id, conversation_sessions.group_binding_id | ID nội bộ của quan hệ nhóm–lớp; FK ghép đảm bảo lớp khớp. |
| `sender_user_id` | TEXT | Cho phép | — | FK → users.id | User cho question/teacher reply; NULL cho bot/system. |
| `role` | TEXT | Bắt buộc | — | — | Vai trò; users là quyền tài khoản, messages là vai trò trong hội thoại. |
| `message_kind` | TEXT | Bắt buộc | — | — | Loại tin nội bộ; enum messages và outbound khác nhau, xem DDL. |
| `text_redacted` | TEXT | Bắt buộc | — | — | Nội dung hiển thị/memory sau khi che dữ liệu nhạy cảm. |
| `memory_eligible` | INTEGER | Bắt buộc | 0 | — | Service cho phép đưa vào cửa sổ memory; vẫn kiểm tra đủ cặp, ACL và citation hiện hành. |
| `status` | TEXT | Bắt buộc | 'committed' | — | Trạng thái; tập giá trị và transition xem thiết kế/DDL. |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(event_key, class_id, group_binding_id)` → `webhook_events(event_key, class_id, group_binding_id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(session_id, class_id, group_binding_id)` → `conversation_sessions(id, class_id, group_binding_id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(sender_user_id)` → `users(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(session_id, created_at, id)`.
- UNIQUE `(event_key, message_kind)`.

## 20. `support_tickets`

Một ticket/event insufficient; FK ghép group/class, service kiểm tra student/assignee.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `event_key` | TEXT | Bắt buộc | — | FK → webhook_events.event_key | ID event nội bộ; dedup ngoại vi là cặp platform/external_event_id. |
| `class_id` | TEXT | Bắt buộc | — | FK → webhook_events.class_id | Lớp nội bộ đã xác thực. |
| `group_binding_id` | TEXT | Bắt buộc | — | FK → webhook_events.group_binding_id | ID nội bộ của quan hệ nhóm–lớp; FK ghép đảm bảo lớp khớp. |
| `student_id` | TEXT | Bắt buộc | — | FK → users.id | Học viên tạo câu hỏi cần hỗ trợ; service đối chiếu event.user_id. |
| `question_redacted` | TEXT | Bắt buộc | — | — | Câu hỏi đã che dữ liệu nhạy cảm; không lưu toàn bộ chat thường. |
| `reason_code` | TEXT | Bắt buộc | — | — | Mã lý do handoff/security, không dùng đoạn lỗi thô. |
| `evidence_summary_redacted` | TEXT | Cho phép | — | — | Tóm tắt vì sao thiếu căn cứ để giảng viên xử lý, đã che dữ liệu. |
| `status` | TEXT | Bắt buộc | 'open' | — | Trạng thái; tập giá trị và transition xem thiết kế/DDL. |
| `assignee_id` | TEXT | Cho phép | — | FK → users.id | Giảng viên được giao ticket, NULL khi chưa giao; service kiểm tra assignment. |
| `revision` | INTEGER | Bắt buộc | 0 | — | Số revision tăng khi thay đổi, dùng optimistic concurrency/CAS. |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |
| `updated_at` | TEXT | Bắt buộc | — | — | Thời điểm cập nhật UTC, ứng dụng tự điền. |
| `answered_at` | TEXT | Cho phép | — | — | Lúc phản hồi giảng viên đã gửi thành công qua mock. |
| `closed_at` | TEXT | Cho phép | — | — | Thời điểm đóng ticket, NULL trước khi đóng. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(event_key, class_id, group_binding_id)` → `webhook_events(event_key, class_id, group_binding_id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(assignee_id)` → `users(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(student_id)` → `users(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(class_id, status, created_at)`.
- UNIQUE `(event_key)`.

## 21. `ticket_replies`

[ĐX MVP] Một câu trả lời chính thức/ticket; mở rộng thread cần migration.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `ticket_id` | TEXT | Bắt buộc | — | FK → support_tickets.id | Ticket liên quan. |
| `teacher_id` | TEXT | Bắt buộc | — | FK → users.id | Giảng viên nội bộ; service kiểm tra role và assignment. |
| `answer_redacted` | TEXT | Bắt buộc | — | — | Câu trả lời chính thức của giảng viên đã che thông tin nhạy cảm. |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(teacher_id)` → `users(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(ticket_id)` → `support_tickets(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- UNIQUE `(ticket_id)`.

## 22. `faq_entries`

Approval không có nghĩa indexed. Usability suy ra từ document active pointer, không có cờ indexed trùng.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `source_ticket_id` | TEXT | Bắt buộc | — | FK → support_tickets.id | Ticket nguồn của FAQ, một đề xuất/ticket trong MVP. |
| `question_redacted` | TEXT | Bắt buộc | — | — | Câu hỏi đã che dữ liệu nhạy cảm; không lưu toàn bộ chat thường. |
| `approved_answer_redacted` | TEXT | Bắt buộc | — | — | Nội dung đề xuất/đã duyệt của FAQ; chỉ được index sau approval. |
| `topic` | TEXT | Bắt buộc | — | — | Chủ đề để quản lý/tìm kiếm; chunk có thể có topic cụ thể hơn document. |
| `scope_id` | TEXT | Bắt buộc | — | FK → access_scopes.id | Canonical scope course:<id> hoặc class:<id>; FK access_scopes hoặc document_access. |
| `status` | TEXT | Bắt buộc | 'draft' | — | Trạng thái; tập giá trị và transition xem thiết kế/DDL. |
| `document_id` | TEXT | Cho phép | — | FK → documents.id | Tài liệu logic cố định qua nhiều version. |
| `created_by` | TEXT | Bắt buộc | — | FK → users.id | Actor tạo tài nguyên. |
| `approved_by` | TEXT | Cho phép | — | FK → users.id | Actor duyệt FAQ; bắt buộc khi status approved. |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |
| `updated_at` | TEXT | Bắt buộc | — | — | Thời điểm cập nhật UTC, ứng dụng tự điền. |
| `approved_at` | TEXT | Cho phép | — | — | Thời điểm duyệt FAQ; không đồng nghĩa indexed_at. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(approved_by)` → `users(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(created_by)` → `users(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(document_id)` → `documents(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(scope_id)` → `access_scopes(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(source_ticket_id)` → `support_tickets(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- UNIQUE `(document_id)`.
- UNIQUE `(source_ticket_id)`.

## 23. `outbound_messages`

Một outbound/event/kind. Bot answer/handoff/blocked/error cùng dùng bot_result.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `event_key` | TEXT | Bắt buộc | — | FK → webhook_events.event_key | ID event nội bộ; dedup ngoại vi là cặp platform/external_event_id. |
| `class_id` | TEXT | Bắt buộc | — | FK → webhook_events.class_id | Lớp nội bộ đã xác thực. |
| `group_binding_id` | TEXT | Bắt buộc | — | FK → webhook_events.group_binding_id | ID nội bộ của quan hệ nhóm–lớp; FK ghép đảm bảo lớp khớp. |
| `message_kind` | TEXT | Bắt buộc | — | — | Loại tin nội bộ; enum messages và outbound khác nhau, xem DDL. |
| `reply_to_external_event_id` | TEXT | Bắt buộc | — | — | ID tin nguồn bên nền tảng; có thể không tồn tại nội bộ. |
| `text_redacted` | TEXT | Bắt buộc | — | — | Nội dung hiển thị/memory sau khi che dữ liệu nhạy cảm. |
| `citations_json` | TEXT | Bắt buộc | '[]' | — | Snapshot danh sách citation đã validate để FE hiển thị; không nhận từ client. |
| `ticket_id` | TEXT | Cho phép | — | FK → support_tickets.id | Ticket liên quan. |
| `ticket_reply_id` | TEXT | Cho phép | — | FK → ticket_replies.id | Reply giảng viên nguồn của outbound, UNIQUE nếu có. |
| `status` | TEXT | Bắt buộc | 'pending' | — | Trạng thái; tập giá trị và transition xem thiết kế/DDL. |
| `attempts` | INTEGER | Bắt buộc | 0 | — | Số lần runner claim/thử xử lý, bắt đầu 0. |
| `max_attempts` | INTEGER | Bắt buộc | 3 | — | Giới hạn retry dương; mặc định thiết kế 3. |
| `lease_token` | TEXT | Cho phép | — | — | Fencing token mỗi lần claim; completion chỉ được ghi nếu token khớp. |
| `lease_expires_at` | TEXT | Cho phép | — | — | Hạn lease UTC; job đang chạy cần renew hoặc timeout trước hạn. |
| `next_attempt_at` | TEXT | Bắt buộc | — | — | Thời điểm sớm nhất runner được claim/retry UTC. |
| `external_message_id` | TEXT | Cho phép | — | — | Mock dùng outbound ID; adapter thật bổ sung ID nền tảng khi hợp lệ. |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |
| `sent_at` | TEXT | Cho phép | — | — | webhook: thời điểm nguồn gửi (tham khảo); outbound: lúc mock lưu thành công; đều chuẩn UTC. |
| `error_code` | TEXT | Cho phép | — | — | Mã lỗi ổn định; không lưu traceback/secret thô. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(event_key, class_id, group_binding_id)` → `webhook_events(event_key, class_id, group_binding_id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(ticket_reply_id)` → `ticket_replies(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(ticket_id)` → `support_tickets(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(status, next_attempt_at)`.
- INDEX `(group_binding_id, created_at, id)`.
- UNIQUE `(event_key, message_kind)`.
- UNIQUE `(ticket_reply_id)`.

## 24. `rag_runs`

Một logical run/event; retries ghi provider call mới, không thêm logical run.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `event_key` | TEXT | Bắt buộc | — | FK → webhook_events.event_key | ID event nội bộ; dedup ngoại vi là cặp platform/external_event_id. |
| `status` | TEXT | Bắt buộc | 'running' | — | Trạng thái; tập giá trị và transition xem thiết kế/DDL. |
| `allowed_scopes_json` | TEXT | Bắt buộc | — | — | Snapshot array scope IDs Backend đã cấp cho run, không tự tạo quyền mới. |
| `active_versions_json` | TEXT | Bắt buộc | — | — | Snapshot array version IDs active khi retrieval, phải recheck trước send. |
| `memory_event_keys_json` | TEXT | Bắt buộc | '[]' | — | Snapshot các event tạo memory window, không sao chép toàn lịch sử vào run. |
| `evidence_sufficient` | INTEGER | Cho phép | — | — | Kết luận gate 0/1; NULL nếu chưa có kết quả. |
| `evidence_reason_redacted` | TEXT | Cho phép | — | — | Giải thích gate ở dạng an toàn, không lưu chain-of-thought/raw prompt. |
| `latency_ms` | INTEGER | Cho phép | — | — | Độ trễ logical run, đơn vị millisecond không âm. |
| `started_at` | TEXT | Bắt buộc | — | — | Thời điểm bắt đầu UTC. |
| `finished_at` | TEXT | Cho phép | — | — | Thời điểm kết thúc UTC, NULL khi chưa terminal. |
| `error_code` | TEXT | Cho phép | — | — | Mã lỗi ổn định; không lưu traceback/secret thô. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(event_key)` → `webhook_events(event_key)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- UNIQUE `(event_key)`.

**Bổ sung v4:** `query_rewrite_json` TEXT NOT NULL DEFAULT `{}`, CHECK json_valid; chứa câu gốc/câu độc lập đã che secret, relation, used_turn_ids và trạng thái rewrite.

## 25. `rag_run_attempts`

[ĐX] Mỗi provider call một hàng, kể cả query embedding/reranking/ingestion/retry. Đúng một owner run hoặc job.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `rag_run_id` | TEXT | Cho phép | — | FK → rag_runs.id | Logical RAG run/event; NULL chỉ khi provider call thuộc ingestion. |
| `ingestion_job_id` | TEXT | Cho phép | — | FK → ingestion_jobs.id | Job sở hữu ingestion embedding call; exclusive với rag_run_id. |
| `stage` | TEXT | Bắt buộc | — | — | Bước pipeline/call; có query_rewrite, query_embed, rerank, generate, ingestion_embed. |
| `attempt_no` | INTEGER | Bắt buộc | — | — | Số thứ tự call/retry trong stage, bắt đầu 1; call_key định danh từng call/batch. |
| `call_key` | TEXT | Bắt buộc | — | — | Idempotency cho log nội bộ, không tự bảo đảm provider không tính phí hai lần. |
| `provider` | TEXT | Bắt buộc | — | — | Nhà cung cấp embedding/rerank/LLM thực tế. |
| `model` | TEXT | Bắt buộc | — | — | Model ID thực tế tại thời điểm gọi. |
| `status` | TEXT | Bắt buộc | — | — | Trạng thái; tập giá trị và transition xem thiết kế/DDL. |
| `input_tokens` | INTEGER | Cho phép | — | — | Tokens đầu vào biết được; NULL khi không có usage. |
| `output_tokens` | INTEGER | Cho phép | — | — | Tokens đầu ra biết được; NULL khi không có usage, 0 nếu biết là không phát sinh. |
| `estimated_cost_usd_micros` | INTEGER | Cho phép | — | — | Chi phí ước tính integer micro-USD; NULL là chưa biết, không phải miễn phí. |
| `pricing_snapshot_json` | TEXT | Bắt buộc | '{}' | — | Đơn giá/đơn vị/currency/as-of dùng tính cost để đối chiếu về sau. |
| `provider_request_id` | TEXT | Cho phép | — | — | ID request do provider trả về nếu có, không phải API key. |
| `started_at` | TEXT | Bắt buộc | — | — | Thời điểm bắt đầu UTC. |
| `finished_at` | TEXT | Cho phép | — | — | Thời điểm kết thúc UTC, NULL khi chưa terminal. |
| `error_code` | TEXT | Cho phép | — | — | Mã lỗi ổn định; không lưu traceback/secret thô. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(ingestion_job_id)` → `ingestion_jobs(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(rag_run_id)` → `rag_runs(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(ingestion_job_id)`.
- INDEX `(rag_run_id, stage, attempt_no)`.
- UNIQUE `(call_key)`.

## 26. `rag_citations`

[ĐX] Provenance FK vào manifest + snapshot để giữ nguồn khi vector cũ bị dọn.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `rag_run_id` | TEXT | Bắt buộc | — | FK → rag_runs.id | Logical RAG run/event; NULL chỉ khi provider call thuộc ingestion. |
| `ordinal` | INTEGER | Bắt buộc | — | — | Thứ tự citation trong response, bắt đầu 1. |
| `point_id` | TEXT | Bắt buộc | — | FK → document_chunks.point_id | UUID deterministic của một version/chunk/scope trong Qdrant, cũng là provenance ID. |
| `title_snapshot` | TEXT | Bắt buộc | — | — | Tên tài liệu tại thời điểm phát câu trả lời. |
| `page` | INTEGER | Cho phép | — | — | Số trang PDF nguồn, bắt đầu 1; NULL nếu không có trang thực. |
| `section_path` | TEXT | Cho phép | — | — | Chuỗi heading/chương/mục gốc, không bịa khi không xác định. |
| `evidence_excerpt_redacted` | TEXT | Bắt buộc | — | — | Đoạn dẫn chứng ngắn được phép hiển thị, đã che thông tin nhạy cảm. |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(point_id)` → `document_chunks(point_id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(rag_run_id)` → `rag_runs(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- UNIQUE `(rag_run_id, ordinal)`.

## 27. `security_events`

Không lưu secret; event_key có thể NULL trước khi resolve/auth event.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `event_key` | TEXT | Cho phép | — | FK → webhook_events.event_key | ID event nội bộ; dedup ngoại vi là cặp platform/external_event_id. |
| `request_id` | TEXT | Bắt buộc | — | — | Correlation ID truy vết request; không chứa credentials. |
| `actor_user_id` | TEXT | Cho phép | — | FK → users.id | Actor nội bộ; NULL nếu request chưa xác thực hoặc tác vụ hệ thống. |
| `reason_code` | TEXT | Bắt buộc | — | — | Mã lý do handoff/security, không dùng đoạn lỗi thô. |
| `severity` | TEXT | Bắt buộc | — | — | Mức info/warning/error của sự kiện bảo mật. |
| `details_redacted_json` | TEXT | Bắt buộc | '{}' | — | JSON thông tin truy vết tối thiểu, không secret/raw payload. |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(actor_user_id)` → `users(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.
- `(event_key)` → `webhook_events(event_key)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(created_at, reason_code)`.

## 28. `audit_logs`

[ĐX] Audit nghiệp vụ, khác security log và access log.

| Cột | Kiểu | NULL | Default | Khóa / tham chiếu | Ý nghĩa |
|---|---|---|---|---|---|
| `id` | TEXT | Bắt buộc | — | PK(1) | ID nội bộ bất biến, ứng dụng sinh. |
| `request_id` | TEXT | Bắt buộc | — | — | Correlation ID truy vết request; không chứa credentials. |
| `actor_user_id` | TEXT | Cho phép | — | FK → users.id | Actor nội bộ; NULL nếu request chưa xác thực hoặc tác vụ hệ thống. |
| `action` | TEXT | Bắt buộc | — | — | Tên hành động audit: document.activate, faq.approve, class.bot.update, ... |
| `entity_type` | TEXT | Bắt buộc | — | — | Loại tài nguyên được audit; tham chiếu đa loại không có FK. |
| `entity_id` | TEXT | Bắt buộc | — | — | ID tài nguyên lịch sử; không bị xóa khi tài nguyên archive/revoke. |
| `change_redacted_json` | TEXT | Bắt buộc | '{}' | — | Diff/audit metadata đã lọc, không đưa raw file hoặc credentials. |
| `created_at` | TEXT | Bắt buộc | — | — | Thời điểm tạo UTC. |

Khóa ngoại (các cột trên cùng dòng là một khóa ghép):

- `(actor_user_id)` → `users(id)`; ON UPDATE NO ACTION, ON DELETE NO ACTION.

Indexes/unique ngoài primary key:

- INDEX `(entity_type, entity_id, created_at)`.


## 29. `user_credentials`

Mỗi hồ sơ `users` có tối đa một tài khoản đăng nhập. Hồ sơ chưa được cấp đăng nhập không có dòng ở đây.

| Cột | Ý nghĩa |
|---|---|
| user_id | PK, FK đến users.id |
| username | Tên đăng nhập duy nhất, chuẩn hóa chữ thường, 3–64 ký tự |
| password_hash | Hash Argon2id, không lưu mật khẩu gốc |
| failed_attempts | Số lần đăng nhập sai trong đợt hiện tại |
| locked_until | Thời điểm hết khóa tạm thời, có thể NULL |
| last_login_at | Lần đăng nhập thành công gần nhất, có thể NULL |
| password_changed_at | Lần cấp/đổi mật khẩu gần nhất |
| created_at | Thời điểm cấp tài khoản |
| updated_at | Thời điểm sửa thông tin đăng nhập |

## 30. `auth_sessions`

| Cột | Ý nghĩa |
|---|---|
| id | PK của phiên đăng nhập |
| user_id | FK đến users.id |
| token_hash | SHA-256 của token ngẫu nhiên, UNIQUE; token gốc chỉ nằm trong cookie |
| created_at | Thời điểm mở phiên |
| expires_at | Thời điểm hết hạn, sau 8 giờ |
| revoked_at | Thời điểm thu hồi, NULL khi chưa thu hồi |
| class_id | FK classes.id, NULL cho phiên không giới hạn lớp; phiên học viên từ picker được giới hạn trong lớp chọn |

Index `ix_auth_sessions_user_expires(user_id,expires_at)` hỗ trợ quản lý phiên theo người dùng.
