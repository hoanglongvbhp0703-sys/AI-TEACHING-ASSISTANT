# Cài đặt và vận hành

Hướng dẫn hiện hành dùng Zalo Bot qua polling và tài khoản admin/giảng viên.

1. Cài Python >=3.11, tạo `.venv`, chạy `python -m pip install -e '.[test]'`.
2. Chạy `python scripts/init_local.py` nếu chưa có DB/config. Không ghi đè dữ liệu đã khôi phục.
3. Điền Claude API key và ZALO_BOT_TOKEN vào `.env`; bật ZALO_BOT_ENABLED=true.
4. Khi backend đang dừng, chạy `python scripts/load_demo_documents.py` nếu cần nạp tài liệu mẫu. Lần đầu tải model mất thời gian.
5. Chạy `python scripts/run_rag.py`. Một backend tại cổng 8002 phục vụ portal, RAG và Bot.
6. Mở http://127.0.0.1:8002/portal. Tạo admin đầu tiên hoặc dùng tài khoản được bàn giao riêng. Admin cấp đăng nhập giảng viên, quản lý lớp và tài liệu.
7. Mở Zalo Bot Creator, nhắn riêng bot hoặc mời bot vào nhóm. Trong nhóm, tag/reply bot để Zalo chuyển sự kiện. Không bắt buộc `/hoi`.
8. Admin vào **Kết nối Zalo → Gắn lớp**, chọn lớp. Mỗi nhóm làm một lần, không đăng ký người gửi.
9. Gửi câu hỏi mới, kiểm tra trả lời có nguồn. Câu thiếu căn cứ tạo ticket; giảng viên phản hồi trên portal và backend gửi lại Zalo.

## Thành phần

| Thành phần | Nhiệm vụ |
|---|---|
| Portal/Auth | Tài khoản nhân sự và quyền quản trị lớp |
| Zalo Bot adapter | Polling, chuẩn hóa sự kiện và sendMessage |
| EventService | Chống trùng, quyền chat/lớp, quota và lưu xử lý |
| SQLite | Tài khoản nhân sự, lớp, tài liệu, job, memory, ticket, outbox, audit |
| Ingestion | Parse/chunk/embed/upsert; index xong mới đổi active version |
| Memory/Rewriter | Ngữ cảnh nhóm và câu hỏi độc lập trước retrieval |
| BKAI/Qdrant/mMARCO | Encode, lọc quyền và active version, chọn Top 5 |
| Claude/Citation | Đánh giá bằng chứng, soạn trả lời, xác minh quote/source |
| Outbox | Kiểm tra lại quyền, gọi API Zalo và retry có giới hạn |

## Log và lỗi

```bash
tail -f data/logs/backend.log
```

- `access_denied`: chat chưa gắn lớp, lớp ngừng hoạt động hoặc bot lớp bị tắt.
- `insufficient_evidence`: nguồn chưa đủ để trả lời; xem ticket.
- `quote_not_in_source`/`invalid_model_output`: lỗi kiểm chứng/định dạng, không tự suy đoán câu trả lời.
- `zalo_send_failed`: API chưa xác nhận gửi thành công; xem outbox và token/hạn mức.
- Không nhận tin nhóm: kiểm tra bot đã vào nhóm và người gửi đã tag/reply bot.
- Có webhook đăng ký sẵn: polling từ chối chạy; chọn đúng một cơ chế nhận tin.
- Cổng 8002 hoặc Qdrant đang bị giữ: dừng đúng backend cũ, không mở hai process cùng dữ liệu.

Ctrl+C dừng hệ thống. Giữ `data/` để giữ dữ liệu; backup nhất quán SQLite/Qdrant/uploads khi app dừng. Không sao chép riêng file SQLite trong khi đang ghi WAL. Hướng dẫn khôi phục: [KHOI_PHUC_DU_LIEU_DEMO.md](KHOI_PHUC_DU_LIEU_DEMO.md).

Google Docs được dẫn ở [GOOGLE_DOCS.md](GOOGLE_DOCS.md); tài liệu trong repository là bản kỹ thuật được cập nhật cùng code.
