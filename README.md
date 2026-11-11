# GOS AI Teaching Assistant

Bộ source được chia thành **20 PR nối tiếp**. Trong lúc chưa merge hết vào main, dùng nhánh `delivery/20-handover-documentation` để chạy bản demo đầy đủ. Kế hoạch và mô tả PR: `ban_giao/01_source_code/PULL_REQUESTS.md` (tính từ root repo).
Demo MVP trợ giảng: portal quản lý lớp/tài khoản/tài liệu/ticket và Mock Zalo hỏi đáp theo học liệu của từng lớp. Hai lớp mặc định: **Machine Learning** và **Google Sheets**.

**[Mở bộ bàn giao](ban_giao/README.md)** — kiến trúc, demo, tài liệu mẫu, Google Docs/hướng dẫn có ảnh, golden dataset, báo cáo kiểm thử, chi phí và điều kiện Zalo thật. Video không nằm trong lần bàn giao này.

## Chạy local từ source

Python >=3.11, Internet để cài thư viện/tải model lần đầu và gọi LLM. Môi trường đã kiểm thử: macOS/Python 3.14. Không yêu cầu cài Qdrant server hoặc frontend Node riêng.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python scripts/init_local.py
```

Script sinh `.env` với webhook secret/token riêng nếu chưa có. Mở `.env`, bổ sung key riêng của người vận hành:

```dotenv
CLAUDE_BASE_URL=https://hhtechapi.net
CLAUDE_MODEL=claude-sonnet-4.6
CLAUDE_API_KEY=YOUR_PRIVATE_KEY
```

Gateway phải hỗ trợ Anthropic Messages. Không thêm `/v1` vào base URL. Các cấu hình khác có trong `.env.example`; key thật không đưa vào repository.

Nạp dữ liệu khi server đang dừng, rồi khởi động:

```bash
python scripts/load_demo_documents.py
python scripts/run_rag.py
```

Lần nạp đầu tải BKAI/mMARCO (~1 GB cache đã quan sát), index 14 PDF ML và DOCX Sheets. Cần chờ tất cả active; nếu dùng dataset riêng có thể upload qua portal và cấp scope tương ứng.

- Portal: http://127.0.0.1:8002/portal
- Mock Zalo: http://127.0.0.1:9000
- Swagger: http://127.0.0.1:8002/docs

Lần đầu tạo admin trên portal, sau đó cấp đăng nhập cho giảng viên/học viên. Không có tài khoản/mật khẩu dùng chung trong source. Trong giả lập chọn ML/học viên rồi gửi `/hoi Các bước chính của thuật toán K-means là gì?`. Ctrl+C dừng cả hai server. Chỉ một backend sở hữu cùng Qdrant Local.

[Hướng dẫn từng bước và xử lý lỗi](ban_giao/04_huong_dan/CAI_DAT_VA_VAN_HANH.md).

## Kiến trúc và nghiệp vụ

FastAPI + SQLAlchemy Core + SQLite (migrations v4); HTML/CSS/JS; BKAI Vietnamese Bi-Encoder + Qdrant Local Top 10 + mMARCO Top 5 + Claude. Shared memory tối đa 5 cặp/30 phút và contextual query rewriting. Claude đọc toàn bộ Top 5, đánh giá bằng chứng và trả claims/citations; Backend xác minh quote/ACL/active version. Không dùng ngưỡng vector/rerank để chặn trước Claude.

Quyền tài liệu ở cấp document; giảng viên chọn tài liệu để thay file, giữ document_id và tự tăng version. Bản cũ phục vụ đến khi index bản mới thành công. Có SHA-256/reindex, revoke, quota 30 câu/ngày, webhook HMAC/dedup, worker lease/outbox/retry, handoff và FAQ được duyệt. STT học viên theo lớp; tài khoản dùng mật khẩu Argon2id/session hash. Danh sách tài khoản hỗ trợ tìm kiếm Unicode và lọc role; giả lập cập nhật metadata mỗi 5 giây.

## Kiểm thử và chất lượng

```bash
python -m pytest -q
python scripts/validate_schema.py
```

Báo cáo golden 40 câu ngày 11/11/2026: Recall@5 **file+trang** 80.77%; Answer Correctness 70.38%; Answerability F1 toàn luồng 84.44%. Faithfulness/Citation Faithfulness được model chấm 100% **chỉ trên 19 câu đã trả lời**, không phải bảo đảm toàn hệ thống. Có 3 lỗi structured output, 3 ca quote không khớp và injection tạo ticket thay vì blocked. Chi tiết và test case tại [báo cáo bàn giao](ban_giao/06_kiem_thu/BAO_CAO_KIEM_THU.md).

## Dữ liệu và phạm vi

`.gitignore` loại `.env`, dữ liệu vận hành trong `data/`, DB, logs, cache model, môi trường Python và thông tin đăng nhập. Không có DB dựng sẵn chứa hồ sơ thật; init + nạp học liệu tái tạo demo. Học liệu PDF được cung cấp cho bài demo, không được repo tự cấp lại giấy phép cho tài liệu bên thứ ba.

Đây là bản local MVP, chưa tích hợp Zalo thật và chưa cấu hình triển khai public. [Điều kiện triển khai, chi phí và Zalo](ban_giao/07_van_hanh/CHI_PHI_VA_ZALO.md). Các tài liệu lịch sử trong `docs/` có thể mô tả phạm vi/kiểm thử cũ; `ban_giao/` là hướng dẫn hiện hành.
