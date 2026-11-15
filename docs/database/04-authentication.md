# Đăng nhập và quyền nhân sự

Portal dùng tài khoản admin/giảng viên do backend quản lý. Lần đầu thiết lập admin, sau đó
admin tạo hồ sơ và cấp credential giảng viên. Mật khẩu lưu Argon2id, session token lưu hash,
cookie HttpOnly/SameSite; có khóa tạm khi đăng nhập sai và thu hồi session khi đổi mật khẩu.

Role phía giao diện không cấp quyền. Backend kiểm tra role và teacher_assignments ở mỗi
API quản trị tài liệu/lớp/ticket. Bot Token chỉ dùng trong backend, không phải mật khẩu portal.

Quyền hỏi qua Zalo dựa trên chat gắn lớp, không có tài khoản học viên. Xem
[quyền theo lớp](../architecture/20-class-scoped-chat.md).
