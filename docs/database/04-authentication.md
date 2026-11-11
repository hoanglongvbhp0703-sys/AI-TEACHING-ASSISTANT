# Tài khoản và đăng nhập — migration v2

Schema v1 có bảng `users` chứa hồ sơ/vai trò nhưng chưa có username, password hay phiên đăng nhập. `conversation_sessions` là phiên hội thoại, không dùng đăng nhập.

V2 thêm `user_credentials` (9 cột) và `auth_sessions` (6 cột): tổng 30 bảng, 306 cột. Chi tiết tại [từ điển dữ liệu](03-data-dictionary.md), [DDL](schema.sqlite.sql) và migration `app/db/migrations/versions/0002_authentication.sql`. Migration giữ nguyên 28 bảng nghiệp vụ và chạy tự động khi khởi động backend.

## Hành vi người dùng

1. Khi chưa có admin được cấp credential: màn hình khởi tạo admin xuất hiện. Cấp thông tin cho hồ sơ admin hiện có; nếu database chưa có admin thì tạo mới. Khởi tạo chỉ thành công một lần.
2. Admin đăng nhập, vào Tài khoản để cấp/đặt lại đăng nhập cho giảng viên cũ, hoặc tạo hồ sơ mới kèm username/password. Chỉ admin có quyền cấp credential. Người dùng API vẫn có thể tạo hồ sơ chưa có credential; hồ sơ này chưa đăng nhập bằng mật khẩu được.
3. Giảng viên nhập username/password và nhận quyền nghiệp vụ theo `users.role`, không tự chọn vai trò. Quyền lớp vẫn kiểm tra tại backend.
4. Mỗi người đổi mật khẩu bằng mật khẩu hiện tại. Phiên đang dùng được thay mới, các phiên cũ bị thu hồi. Admin đặt lại mật khẩu người khác cũng thu hồi các phiên cũ. Tài khoản bị khóa không truy cập được.
5. Đăng xuất thu hồi phiên trong database và xóa cookie. Khởi động lại backend không làm mất phiên còn hiệu lực.

## Quy tắc lưu trữ

Username chữ thường, duy nhất, 3–64 ký tự ASCII gồm chữ/số/dấu chấm/gạch dưới/gạch ngang. Mật khẩu 15–128 ký tự, giữ nguyên khoảng trắng; không có mật khẩu mặc định. Argon2id sử dụng memory_cost=65536 KiB, time_cost=3, parallelism=4. API không trả hash hoặc mật khẩu; log/audit không lưu các giá trị đó.

Token phiên ngẫu nhiên 32 byte, database chỉ lưu SHA-256. Cookie HttpOnly, SameSite=Strict, thời hạn 8 giờ. Bản này phục vụ HTTP localhost nên cookie Secure=false; chưa cấu hình triển khai production. Sai 5 lần khóa đăng nhập 15 phút; phản hồi không tiết lộ tài khoản có tồn tại hay không.

Bearer token cho tích hợp local cũ vẫn là cơ chế riêng do người vận hành cấu hình trong `.env`; đổi mật khẩu web không thu hồi token tích hợp. RAG giữ nguyên trạng thái tắt trong portal.

## API

| Method / đường dẫn (prefix /api/v1) | Nhiệm vụ |
|---|---|
| GET /auth/status | Kiểm tra có cần khởi tạo admin |
| POST /auth/setup | Khởi tạo admin lần đầu và mở phiên |
| POST /auth/login | Kiểm tra username/password và mở phiên |
| POST /auth/logout | Thu hồi phiên và xóa cookie |
| POST /auth/password | Đổi mật khẩu cá nhân, cấp phiên mới |
| PUT /users/{id}/credentials | Admin cấp hoặc đặt lại username/password |

Các route `/demo/accounts` và `/demo/session` đã gỡ. Mở `/docs` để xem hợp đồng request/response.

Tham khảo: [argon2-cffi](https://argon2-cffi.readthedocs.io/en/stable/howto.html), [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).


Cập nhật v3: có role/profile picker; giảng viên do admin cấp hồ sơ, học viên chọn lớp + STT, vẫn cần mật khẩu. Phiên học viên từ picker lưu class_id và kiểm tra lại enrollment. [Thiết kế phân quyền lớp và roster](../architecture/12-class-access-and-rosters.md).
