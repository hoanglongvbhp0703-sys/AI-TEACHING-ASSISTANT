# GOS AI Teaching Assistant

Trợ giảng dùng **Zalo Bot thật**, portal quản trị và RAG theo tài liệu của từng lớp. Hai lớp demo: Machine Learning và Google Sheets.

## Chạy local

Yêu cầu Python >=3.11; cần Internet khi cài thư viện/tải model lần đầu và gọi Claude.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python scripts/init_local.py
```

Điền cấu hình riêng vào `.env`:

```dotenv
CLAUDE_BASE_URL=https://hhtechapi.net
CLAUDE_MODEL=claude-sonnet-4.6
CLAUDE_API_KEY=<key riêng>
ZALO_BOT_ENABLED=true
ZALO_BOT_TOKEN=<token từ Bot Creator>
```

Gateway phải tương thích Anthropic Messages. Giữ key/token ở backend, không đưa vào Git.

Khi backend đang dừng, nạp học liệu lần đầu rồi chạy:

```bash
python scripts/load_demo_documents.py
python scripts/run_rag.py
```

- Portal: http://127.0.0.1:8002/portal
- API Docs: http://127.0.0.1:8002/docs
- Một tiến trình FastAPI chạy portal, worker RAG và polling Zalo Bot. Ctrl+C để dừng.

Tạo admin ở lần chạy đầu, cấp tài khoản giảng viên, quản lý tài liệu và phân công lớp.
Nhắn riêng bot hoặc tag/reply bot trong nhóm. Admin vào **Kết nối Zalo → Gắn lớp** một lần cho mỗi chat/nhóm. Người trong nhóm được hỏi đúng tài liệu lớp đó; không cần tài khoản học viên và không cần `/hoi`. Nhóm chưa gắn lớp chưa được truy xuất tài liệu.

## Kiến trúc

FastAPI + SQLite v5 + HTML/CSS/JS. BKAI embedding → Qdrant Top 10 theo scope/active version → mMARCO Top 5 → Claude đánh giá toàn bộ nguồn và soạn câu trả lời → backend xác minh trích dẫn → outbox gọi Zalo sendMessage. Thiếu căn cứ tạo ticket để giảng viên hỗ trợ. Memory dùng chung trong mỗi nhóm, tối đa 5 cặp/30 phút; contextual query rewriting đặt trước embedding.

Quyền tài liệu ở cấp document. Giữ document_id, tự tăng version; bản cũ chỉ ngừng phục vụ sau khi bản mới index thành công. Có SHA-256/reindex, quota theo ID người gửi, chống trùng sự kiện, worker lease/retry và kiểm tra lại quyền trước gửi.

Chi tiết: [kiến trúc](ban_giao/02_kien_truc/KIEN_TRUC.md), [Zalo Bot](docs/architecture/19-zalo-bot-integration.md), [quyền theo lớp](docs/architecture/20-class-scoped-chat.md), [bộ bàn giao](ban_giao/README.md).

## Kiểm thử

```bash
ZALO_BOT_ENABLED=false python -m pytest -q
python scripts/validate_schema.py
```

Kiểm thử tự động thay riêng các dịch vụ bên ngoài bằng test doubles; không gửi tin đến người dùng thật. Chất lượng RAG phải được đánh giá riêng bằng golden dataset. Báo cáo lịch sử 40 câu: Recall@5 file+trang 80.77%, Correctness 70.38%, Answerability F1 84.44%; Faithfulness/Citation Faithfulness 100% chỉ trên 19 câu đã trả lời, không bảo đảm toàn hệ thống.

## Dữ liệu và vận hành

`.env`, DB, uploads, logs, model cache và gói dữ liệu riêng không đưa Git. SQLite là database thực, lưu trong file `data/gos.db`; Qdrant Local nằm trong `data/qdrant/`. Log: `data/logs/backend.log`.

Bản hiện tại dành cho local. Polling Zalo không cần URL HTTPS công khai; triển khai nhiều máy cần thiết kế khóa poller/worker, bảo vệ portal, backup, monitoring và ngân sách API. Chưa triển khai adapter OA/GMF. Học liệu demo không được repo tự cấp lại giấy phép cho tài liệu bên thứ ba.
