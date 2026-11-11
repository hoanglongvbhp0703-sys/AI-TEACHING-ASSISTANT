# Source code

Mã nguồn chạy trực tiếp từ root repository, không nhân bản vào thư mục bàn giao.

| Đường dẫn | Nhiệm vụ |
|---|---|
| `app/api/routes/` | API tài khoản, lớp, tài liệu, sự kiện, webhook, ticket |
| `app/services/` | Nghiệp vụ, ACL, shared memory, quota, phiên đăng nhập |
| `app/rag/` | Parse/chunk, model local, retrieval, rewriting, Claude và citation |
| `app/jobs/runner.py` | Worker ingestion, outbox callback, retry/lease và cleanup |
| `app/db/` | SQLite, migrations v1–v4, seed hai lớp |
| `app/static/` | Portal và Mock Zalo bằng HTML/CSS/JS |
| `scripts/` | Khởi tạo, chạy demo, nạp học liệu, kiểm thử/đánh giá |
| `tests/` | Unit/integration, gồm test double được ghi rõ |
| `docs/` | Thiết kế chi tiết và các quyết định triển khai theo giai đoạn |

Python yêu cầu >=3.11 theo `pyproject.toml`. Môi trường phát triển đã kiểm thử dùng Python 3.14 trên macOS; khả năng cài wheel của torch phụ thuộc nền tảng. Không yêu cầu cài riêng PostgreSQL, Redis, Qdrant server hoặc Node để chạy demo. Qdrant ở chế độ local.

`.gitignore` loại `.env`, database, logs, `.venv`, cache, thông tin đăng nhập và video. `.env.example` chỉ là mẫu; nên chạy `init_local.py` để sinh secret/token riêng thay vì sử dụng file mẫu với secret trống.
