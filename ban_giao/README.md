# Bộ bàn giao — GOS AI Teaching Assistant

Bộ source được chia thành **20 PR nối tiếp**. Trong lúc chưa merge hết vào main, dùng nhánh `delivery/20-handover-documentation` để chạy bản demo đầy đủ. Kế hoạch và mô tả PR: `ban_giao/01_source_code/PULL_REQUESTS.md` (tính từ root repo).
Ngày đóng gói: **12/11/2026**. Phạm vi: demo local với **Machine Learning** và **Google Sheets**. Video được loại khỏi lần bàn giao này theo yêu cầu.

| Mục yêu cầu | Sản phẩm |
|---|---|
| 1. Source code, README, cấu hình | Mã nguồn ở root repository, [hướng dẫn source](01_source_code/README.md), [`.env.example`](../.env.example) |
| 2. Kiến trúc, dữ liệu, phân quyền | [Kiến trúc hệ thống](02_kien_truc/KIEN_TRUC.md), [Mermaid](02_kien_truc/architecture.mmd) |
| 3. Demo, tài liệu mẫu, dữ liệu kiểm thử | [Kịch bản demo](03_demo/README.md), `03_demo/tai_lieu_mau/`, [golden 40 câu](03_demo/GOS_IT3190_Golden_Dataset_40.jsonl), 14 PDF trong `Machine Learning copy/` |
| 4. Google Docs, hướng dẫn và ảnh | [Hướng dẫn có ảnh](04_huong_dan/CAI_DAT_VA_VAN_HANH.md), [Google Docs](04_huong_dan/GOOGLE_DOCS.md) |
| 6. Báo cáo kiểm thử, lỗi, cải thiện | [Báo cáo](06_kiem_thu/BAO_CAO_KIEM_THU.md), kết quả CSV/JSON/JUnit cùng thư mục |
| 7. Chi phí và điều kiện Zalo thật | [Đề xuất vận hành](07_van_hanh/CHI_PHI_VA_ZALO.md) |

## Chạy từ source mới

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
python scripts/init_local.py
```

Điền `CLAUDE_API_KEY` của người vận hành trong `.env`. Dùng `CLAUDE_BASE_URL=https://hhtechapi.net`, `CLAUDE_MODEL=claude-sonnet-4.6` với gateway đã kiểm thử. Endpoint phải tương thích Anthropic Messages; key không được ghi trong tài liệu hay commit.

Nạp tài liệu trước khi khởi động server (lần đầu cần Internet để tải embedding/reranker):

```bash
python scripts/load_demo_documents.py
python scripts/run_rag.py
```

Portal: http://127.0.0.1:8002/portal. Giả lập: http://127.0.0.1:9000. Lần đầu tạo admin trên portal; không có mật khẩu chung để bàn giao. Người xem chỉ cần tài khoản do admin cấp nếu demo được vận hành trên máy của người bàn giao.

## Giới hạn nghiệm thu

RAG đã chạy thật; còn lỗi structured output, quote và xử lý injection/handoff được ghi trong báo cáo. Các điểm Faithfulness 100% là ước lượng có điều kiện trên các câu đã trả lời, không phải chất lượng tuyệt đối. Chưa tích hợp Zalo thật, chưa có cấu hình production public. Bộ bàn giao không chứa `.env`, DB vận hành, file upload riêng, model cache hoặc log.

Các bản thiết kế cũ trong `docs/` giữ lịch sử; tài liệu ở thư mục này là hướng dẫn bàn giao hiện hành. Golden chi tiết được chấm ngày 11/11/2026; kiểm thử tự động được chạy lại khi đóng gói.
