# Kết nối Zalo Bot

Tạo bot bằng Zalo Bot Creator, lưu Bot Token vào `.env`, bật ZALO_BOT_ENABLED=true.
Chạy `python scripts/run_rag.py`. Một backend ở cổng 8002 chạy portal, worker RAG và poller.
Không đăng ký webhook đồng thời với polling. Nếu bot đã có webhook, backend dừng khởi động
poller để tránh tự thay đổi cấu hình nhận tin của bot.

Nhắn riêng bot hoặc tag/reply trong nhóm. Backend bỏ tag tên bot ở đầu câu, không yêu cầu
`/hoi`. Admin chọn **Kết nối Zalo → Gắn lớp** một lần cho mỗi cuộc chat. Người mới trong
nhóm không phải tạo tài khoản. Chat chưa gắn lớp không được truy xuất học liệu.

File `app/integrations/zalo_bot.py` dùng HTTP client tới Bot API, chuẩn hóa IncomingEvent
và gọi EventService. EventService xử lý chống trùng, quyền lớp, quota, RAG và handoff.
Worker gửi outbox qua sendMessage, xác nhận thành công từ nội dung API trước khi ghi sent.
Khóa poller ngăn nhiều tiến trình cùng bot trên một máy; khóa worker bảo vệ một DB.

Log ở `data/logs/backend.log`: zalo_bot_started, zalo_bot_received, zalo_poll_failed, zalo_send.
Không in token hoặc đường dẫn HTTP chứa token. `/api/v1/health` có zalo_bot_running.

Polling chưa bảo đảm replay khi chết giữa lúc nhận và ghi DB. API gửi tin chưa có bảo đảm
exactly-once khi mất ACK. Triển khai nhiều máy cần thêm hạ tầng khóa, monitoring và backup.
