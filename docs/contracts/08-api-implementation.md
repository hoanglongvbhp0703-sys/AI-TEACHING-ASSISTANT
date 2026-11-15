# API hiện hành

Hợp đồng đầy đủ trong [openapi.json](openapi.json), cũng có tại `/docs` khi backend chạy.

- Auth: thiết lập admin đầu tiên, đăng nhập, đăng xuất, đổi mật khẩu, hồ sơ giảng viên.
- Identity/classes: tài khoản nhân sự, khóa học/lớp, phân công giảng viên, bật/tắt bot.
- Zalo Bot: inbox sự kiện và gắn chat với lớp, chỉ admin cấu hình.
- Documents: upload, ACL, phiên bản, reindex/revoke, job/progress/retry.
- Events: trạng thái xử lý của một sự kiện, kiểm tra quyền nhân sự trước khi xem.
- Tickets/FAQ: phân công, trả lời, đóng ticket và duyệt FAQ vào học liệu.
- Reports/health: thống kê xử lý, usage model và tình trạng backend/worker/poller.

Mọi payload qua DTO validation; API staff kiểm tra quyền ở backend. Tài khoản học viên,
ghi danh và portal học viên đã được loại bỏ ở v5.
