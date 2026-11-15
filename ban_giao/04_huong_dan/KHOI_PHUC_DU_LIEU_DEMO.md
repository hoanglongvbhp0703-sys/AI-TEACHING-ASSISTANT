# Khôi phục demo từ bộ dữ liệu gửi riêng

Hệ thống **đã kết nối SQLite và Qdrant Local dạng file**, chưa sử dụng database server riêng như PostgreSQL hoặc Qdrant Server. Vì dữ liệu vận hành không nằm trên GitHub, người nhận source cần bổ sung bộ dữ liệu demo để đăng nhập bằng tài khoản đã cấp và hỏi đáp trên index có sẵn.

## Bộ dữ liệu gửi riêng

Nhận thêm `du_lieu_demo_rieng.zip` (khoảng 1 GB, có cache model). Giải nén vào `ban_giao/`, kết quả:

```text
ban_giao/du_lieu_demo_rieng/
  KHOI_PHUC_DEMO.py          # Công cụ khôi phục có sẵn trong ZIP
  demo_bundle.py            # Thư viện kiểm tra dữ liệu
  manifest.json             # Danh mục file và SHA-256
  TAI_KHOAN_DEMO.md          # Tài khoản nhân sự và mật khẩu demo
  README.txt
  data/
    gos.db                  # Hồ sơ, hash mật khẩu, lớp, tài liệu, ticket...
    qdrant/                 # Vector + nội dung chunk đã index
    uploads/                # Tài liệu gốc tương ứng database
    models/hub/             # BKAI + mMARCO đã cache
```

Đây là bản sao dữ liệu tại thời điểm xuất, có thể còn lịch sử hỏi đáp/ticket đã redact. Chỉ gửi cho người được phép dùng demo. Không push thư mục/ZIP này lên repository public. API key/.env của người bàn giao không được sao chép. Phiên đăng nhập cũ, quota đã dùng và các tác vụ chờ được làm sạch trên bản sao; tài khoản/hash mật khẩu được giữ nguyên.

## Các bước trên máy nhận

Tại root source, cài môi trường một lần:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

Giải nén ZIP như cấu trúc trên, rồi chạy:

```bash
python ban_giao/du_lieu_demo_rieng/KHOI_PHUC_DEMO.py
```

Script kiểm tra checksum, khôi phục vào `data/`, kiểm tra SQLite và đối chiếu Qdrant với manifest active. Script tạo `.env` nếu chưa có, để trống API key và Bot Token cho người nhận tự cấu hình. **Không cần chạy init_local.py hoặc load_demo_documents.py trước bước này.**

Mở `.env`, thêm API key riêng của người vận hành:

```dotenv
CLAUDE_BASE_URL=https://hhtechapi.net
CLAUDE_MODEL=claude-sonnet-4.6
CLAUDE_API_KEY=YOUR_PRIVATE_KEY
ZALO_BOT_ENABLED=true
ZALO_BOT_TOKEN=YOUR_PRIVATE_BOT_TOKEN
```

Sau đó:

```bash
python scripts/run_rag.py
```

- Portal: http://127.0.0.1:8002/portal
- Đăng nhập bằng tài khoản admin/giảng viên được cấp riêng. Khi mở snapshot cũ, backend chuyển sang schema v5 và loại bỏ tài khoản học viên; chỉ giữ tài khoản nhân sự.

Không cần tự cài database server, tạo lại tài khoản, upload/index lại tài liệu hoặc tải lại cache model đã kèm theo. Vẫn cần Internet để gọi LLM và Python/dependencies tương thích trên máy nhận. Không sao chép `.venv` macOS sang máy khác.

## Bảo vệ dữ liệu đang có

Restore từ chối ghi đè `data/` đã có file và giữ nguyên `.env` đang tồn tại. Nếu đã chạy init/demo trước đó, dùng source ở thư mục mới hoặc tự sao lưu/chuyển dữ liệu cũ trước khi restore. Không restore lên backend đang hoạt động.

Nếu giữ `.env` cũ, kiểm tra DATABASE_URL/UPLOAD_DIR/RAG_VECTOR_DIR/RAG_MODEL_CACHE trỏ đúng dữ liệu đã khôi phục; Bot Token phải thuộc bot cần kết nối. Đổi mật khẩu demo khi dùng ngoài buổi nghiệm thu.

Tùy chọn QA ở thư mục riêng:

```bash
python ban_giao/du_lieu_demo_rieng/KHOI_PHUC_DEMO.py --target-data-dir /tmp/gos-demo --env-file /tmp/gos-demo.env
```

`run_rag.py` mặc định đọc `.env` tại root; tùy chọn trên không tự chuyển cấu hình khi khởi động.
