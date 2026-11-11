# 08 — API Backend đã triển khai

Ngày cập nhật: **10/11/2026** · FastAPI 0.162.2 · SQLAlchemy Core 2.0.57 · SQLite schema v1.

**Cập nhật MVP 11/11/2026:** hiện có **51 API**, schema v3 **30 bảng**, đăng nhập mật khẩu và quản lý tài liệu ở cấp toàn file. Reindex: POST `/api/v1/documents/{document_id}/reindex`; giữ document_id, tự tăng version, hỗ trợ cùng SHA-256 với model/config mới. RAG thật đã triển khai; xem [kiến trúc RAG](../architecture/10-rag-implementation.md). Các thống kê dưới đây là lịch sử đợt API ban đầu; xem README để biết hiện trạng.

## 1. Trạng thái thực tế

- **37 endpoint nghiệp vụ** dưới `/api/v1`, cộng Swagger `/docs`, `/redoc` và OpenAPI `/openapi.json` tự sinh.
- Database thật `data/gos.db`: **28 bảng**, migration v1 và 13 user demo. File runtime và `.env` được gitignore.
- Đã chạy **50/50 test API** (25 ca nghiệp vụ và 25 ca webhook HMAC) trên database tạm và **18/18 test DDL**. HTTP local: health/auth/classes/OpenAPI/Swagger trả 200.
- Chưa viết giao diện `/demo`, embedding, reranker, LLM hoặc kết nối Qdrant thực. Đây là đợt triển khai **API Backend**, chưa hoàn tất toàn bộ MVP AI/RAG.
- Mặc định `UnconfiguredRAG`: không có tài liệu active → insufficient/handoff; index → failed với `embedding_unconfigured`, giữ source để retry; có active source nhưng chưa có model → error rõ ràng. Không tự đánh active hoặc dùng embedding/AI answer giả.

## 2. Khởi động và xác thực

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python scripts/init_local.py
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

`init_local.py` chỉ tạo `.env` khi chưa có, sinh token ngẫu nhiên, không in giá trị. File có quyền 0600. `AUTH_TOKENS_JSON` map token → user_id; API đọc user/role/is_active hiện hành từ DB. User mới không tự có token; đăng nhập local cần thêm mapping phía server và restart. Bản này chưa có login/password/JWT production.

Roles: **A**=admin, **T**=teacher có assignment, **S**=student, **V**=service adapter. Auth chung: `Authorization: Bearer <token>`. Webhook mặc định dùng HMAC-SHA256 qua `X-Webhook-Timestamp` và `X-Webhook-Signature`, không cần Bearer nhưng vẫn kiểm tra group/sender/enrollment. Mode `X-Webhook-Secret` cũ chỉ bật bằng `MOCK_WEBHOOK_AUTH_MODE=secret`; xem [thiết kế webhook](09-webhook-design.md). Môi trường chỉ hỗ trợ local/development/test.

Response nghiệp vụ:

```json
{"data": {}, "error": null, "request_id": "<UUID>"}
```

Lỗi:

```json
{"data": null, "error": {"code": "forbidden", "message": "..."}, "request_id": "<UUID>"}
```

`X-Request-ID` do server sinh; lỗi validation không echo raw input/secret header. List documents/tickets có items,total,limit,offset; limit tối đa 100. Danh sách seed nhỏ như courses/classes trả array. Chat polling dùng `after=<outbound_id>` và thứ tự insert SQLite ổn định, không dựa vào timestamp có thể trùng millisecond.

## 3. Danh sách endpoint và nhiệm vụ

### Danh tính, khóa học và lớp — 14 endpoint

| Method | Đường dẫn sau /api/v1 | Quyền | Nhiệm vụ |
|---|---|---|---|
| GET | `/auth/me` | User | User hiện tại, role và class_ids được phép |
| GET | `/users` | A | Danh sách người dùng có limit/offset |
| POST | `/users` | A | Tạo tài khoản nội bộ, không tự cấp token |
| PATCH | `/users/{user_id}` | A | Bật/tắt is_active; không tự khóa admin đang dùng |
| GET | `/courses` | T/A | Các khóa học trong phạm vi quản lý |
| POST | `/courses` | A | Tạo khóa học và canonical course scope |
| GET | `/classes` | S/T/A | Các lớp tham gia/phụ trách; admin xem tất cả |
| POST | `/classes` | A | Tạo lớp thuộc khóa học và canonical class scope |
| PATCH | `/classes/{class_id}/bot` | A | Bật/tắt bot theo lớp |
| GET | `/classes/{class_id}/members` | T/A | Xem thành viên lớp có quyền, có limit/offset |
| PUT | `/classes/{class_id}/members/{student_id}` | A | Thêm/cập nhật enrollment active/suspended/left |
| PUT | `/classes/{class_id}/teachers/{teacher_id}` | A | Phân công hoặc ngừng phân công giảng viên |
| POST | `/group-bindings` | A | Gắn nhóm mock với lớp; không rebind nhóm đã tạo |
| POST | `/external-identities` | A | Gắn external sender với user, có cờ bot identity |

Action admin ghi audit. ID course/class/user chỉ nhận chữ Latin, số, underscore và hyphen; không dùng user ID làm filesystem path.

### Webhook, mock chat và quota — 6 endpoint

| Method | Đường dẫn sau /api/v1 | Quyền | Nhiệm vụ |
|---|---|---|---|
| POST | `/webhooks/mock-zalo` | HMAC, hoặc mode secret cũ | Verify raw body/timestamp, validate, resolve quyền, dedup và reserve quota trước ACK |
| POST | `/mock/events` | A/V, mock enabled | Phát event demo qua cùng handler webhook |
| GET | `/mock/groups` | User, mock enabled | Xem nhóm có quyền; service xem các nhóm local |
| GET | `/mock/groups/{group_id}/messages` | Có quyền nhóm/V | Poll outbound đã sent, citation/ticket_id và next_cursor |
| GET | `/events/{event_key}` | Chủ event/T có lớp/A/V | Theo dõi queued/processing/completed/failed/ignored/rejected |
| GET | `/students/{student_id}/quota` | S chính chủ/A | used/remaining/limit=30/local_date/reset_at |

Webhook chuẩn theo SRS, chỉ nhận mock_zalo; timestamp phải có timezone. Các trường class_id, role hoặc allowed scopes ngoài schema trả 422. Duplicate trả 200 + duplicate_ignored/cùng event_key; queued mới trả 202. Denied/ignored trả 200 kèm outcome để không kích thích delivery retry vô ích.

Quota 30/ngày tổng mọi lớp, ngày Việt Nam; throttle mặc định 5/phút. Hoàn reservation khi quyền mất trước xử lý. Kết quả RAG/ticket/blocked hoặc lỗi sau khi pipeline bắt đầu giữ một lượt; retry không tính thêm.

Polling hiện trả **outbound đã gửi mock**; tin chat thường giữ phía trình duyệt. Câu hỏi /hoi lưu nội bộ nhưng chưa có endpoint xuất toàn bộ user-question history; UI có thể giữ bubble đã gửi trong state.

### Tài liệu và ingestion — 7 endpoint

| Method | Đường dẫn sau /api/v1 | Quyền | Nhiệm vụ |
|---|---|---|---|
| GET | `/documents` | T/A | Tìm title/topic, lọc class, phân trang theo quyền |
| POST | `/documents` | T/A | Upload source, tạo document/version/job, trả 202 |
| GET | `/documents/{document_id}` | T/A có mọi scope | Metadata, phạm vi, lịch sử versions |
| POST | `/documents/{document_id}/versions` | T/A có quyền | Upload bản thay thế; hash/config giống bản active trả 200 unchanged |
| DELETE | `/documents/{document_id}` | T/A có quyền | Revoke active pointer, cancel ingestion, queue cleanup mọi version |
| GET | `/ingestion-jobs/{job_id}` | T/A có quyền | Trạng thái job/version/document_state và mã lỗi an toàn |
| POST | `/ingestion-jobs/{job_id}/retry` | T/A có quyền | Retry version failed, ngăn job cạnh tranh/stale version |

Upload multipart: file, title, topic, scope_ids (JSON array string), extraction_config (JSON object string tùy chọn), source_code, source_version. Ví dụ scope_ids: `["class:GS-KPI-01"]`. Update version nhận file, change_note và extraction_config tùy chọn.

Giới hạn mặc định: file 10 MB, request 11 MB, ZIP expanded 50 MB. Chấp nhận PDF/DOCX/XLSX/FAQ JSON và kiểm tra định dạng nội dung. FAQ JSON là object hoặc array các object question/answer không rỗng. File dùng path UUID server sinh. Mọi chunk dùng toàn bộ scope của tài liệu, không có phân quyền theo chương; teacher chỉ quản lý course-level khi phụ trách mọi lớp active bị ảnh hưởng. Chưa có endpoint đổi ACL hoặc sửa title/topic tài liệu đã tạo.

### Ticket và FAQ — 8 endpoint

| Method | Đường dẫn sau /api/v1 | Quyền | Nhiệm vụ |
|---|---|---|---|
| GET | `/tickets` | T/A | List theo class/status và phân trang |
| GET | `/tickets/{ticket_id}` | T/A có lớp | Chi tiết ticket/evidence/reply |
| POST | `/tickets/{ticket_id}/assign` | T/A có lớp | Giao teacher active thuộc lớp, kiểm tra revision |
| POST | `/tickets/{ticket_id}/answer` | Teacher được giao/A | Lưu official reply/outbox, trả 202; answered sau mock send |
| POST | `/tickets/{ticket_id}/close` | T/A có lớp | Đóng ticket answered, kiểm tra revision |
| POST | `/tickets/{ticket_id}/faq-draft` | T/A có lớp/scope | Tạo một FAQ nháp từ ticket answered/closed |
| GET | `/faqs/{faq_id}` | T/A có quyền | Xem approval và trạng thái document |
| POST | `/faqs/{faq_id}/approve` | T/A có quyền | Duyệt, sinh source JSON/document/version/job; lặp approve không tạo trùng |

assign nhận teacher_id + revision; answer nhận answer + revision; close nhận revision. FAQ draft nhận scope_id + topic. Answer lặp cùng nội dung trả reply cũ; nội dung khác sau official reply trả 409. FAQ approved chưa vào RAG tới khi version active.

### Báo cáo và vận hành — 2 endpoint

| Method | Đường dẫn sau /api/v1 | Quyền | Nhiệm vụ |
|---|---|---|---|
| GET | `/reports/summary` | T/A | Tổng event/accepted/outcomes/ticket/ingestion, p50/p95, usage/cost |
| GET | `/health` | Public local | Ứng dụng, SQLite/schema, background jobs, readiness RAG |

Report nhận from/to có timezone, khoảng `[from,to)`, mặc định 30 ngày, tối đa 366 ngày; class_id tùy chọn luôn kiểm tra quyền. Cost tách question/ingestion; NULL được tính vào unknown_cost_calls. Chỉ phản ánh call rows model adapter thực sự ghi; mặc định chưa có AI usage thật.

## 4. Mã và migration

- app/main.py: lifespan, middleware body limit/request_id, error handlers, routers và health.
- app/api/deps.py: Bearer auth, role checks, envelope.
- app/api/routes/{identity,webhooks,events,documents,tickets,reports}.py: 36 endpoint; health ở main.
- app/integrations/mock_zalo_adapter.py: xác minh chữ ký/timestamp trước parse JSON; helper ký raw body.
- app/services/: access/event/quota/memory/document/ticket/outbound validation.
- app/repositories/store.py: SQL tham số hóa, audit/security helpers; service giữ transaction.
- app/db/session.py: SQLAlchemy Core engine, BEGIN IMMEDIATE, migration SQL v1; chưa dùng Alembic hoặc ORM classes viết tay.
- app/db/seed.py: idempotent seed, không reset bot/membership đã sửa.
- app/jobs/runner.py: runner tuần tự trong process, persisted claims/lease/fencing, mock send và cleanup retry.
- app/rag/backend.py và schemas.py: protocol, unconfigured implementation và trusted I/O.
- app/rag/parsers/files.py: validation upload; **chưa phải ingestion parser đầy đủ headings/tables/chunks**.

Schema lưu user_version=1 trong migration đầu tiên; database có bảng mà chưa có version sẽ bị từ chối tự nâng cấp. Folder design trước đó là kế hoạch, không phải mọi file có ký hiệu (*) đều đã triển khai.

## 5. Hợp đồng RAG adapter — đã có LocalRAG thực thi

Implement RAGBackend Python và truyền `create_app(settings,backend=...)`; không thêm public endpoint cho FE tự chọn scope:

1. index(version,path,scopes,config) thực sự parse/chunk/embed/upsert/verify Qdrant rồi trả manifest. Point ID dùng app.jobs.runner.point_id; metadata có section/page/hash/embedding_model/vector_size. Worker kiểm tra ACL toàn tài liệu và CAS trước activation.
2. answer(context) filter scopes + active versions **trước search**, rerank/evidence/generate; trả RAGResult với retrieved_point_ids và citations thật. Backend kiểm tra nguồn trước commit và mock send.
3. cleanup(document_id,version_id) xóa theo cả document/version; close() đóng tài nguyên. Giữ manifest/citation SQLite cho audit.
4. Ghi từng provider call vào rag_run_attempts, kể cả started/failed/unknown, model/usage/cost snapshot; không log secret/raw prompt. Adapter chịu trách nhiệm timeout và tổng thời gian **nhỏ hơn lease 120 giây**, hoặc cần bổ sung lease renewal trước khi dùng tác vụ dài. Chưa cưỡng bức dừng được Python adapter treo.

Test double chỉ ở tests/conftest.py; runtime không import/dùng nó. Chưa nghiệm thu model/Qdrant/Recall@k/grounding, Zalo thật, nhiều process; chưa có retention/orphan sweeper hoặc auth production. Validation file thành công không đồng nghĩa index thành công.

## 6. Kiểm tra

```sh
.venv/bin/python -m pytest -q
python3 scripts/validate_schema.py
.venv/bin/python scripts/smoke_local.py
.venv/bin/python -m ruff check app tests scripts
```

Kết quả: **50 API tests pass**, **18 DDL tests pass**, 5 đường dẫn HTTP chỉ đọc trả 200. Runtime foreign_key_check rỗng, integrity_check=ok. TestClient có một cảnh báo deprecation Starlette/httpx, không có test failure. Test dùng database/clock tạm và test-only backend để xác minh nghiệp vụ, không thay thế nghiệm thu AI.

Tham chiếu: [FastAPI dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/), [SQLAlchemy transactions](https://docs.sqlalchemy.org/en/20/core/connections.html). Quyền và nghiệp vụ dựa trên các SRS của workspace.


Bổ sung phân quyền lớp: GET `/auth/options`, GET `/mock/catalog` (adapter/admin), PUT `/classes/{id}/roster` (admin), prefix `/api/v1`. Login nhận role/class_id và xác minh phía server; class members có STT. [Chi tiết](../architecture/12-class-access-and-rosters.md).
