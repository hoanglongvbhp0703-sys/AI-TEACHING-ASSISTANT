# Phân quyền lớp, vai trò đăng nhập và danh sách học viên

Cập nhật 11/11/2026, schema v3. Các quy tắc RAG trước đây vẫn giữ: ACL toàn tài liệu, active version do Backend quyết định.

## Nguyên nhân tin ML xuất hiện dưới nhóm Google Sheets

Giả lập lưu lịch sử của mọi nhóm trong RAM, nhưng GET `/api/mock/messages` trước đây trả tất cả. Frontend không lọc theo nhóm đang chọn và không chặn phản hồi polling cũ về chậm. Vì vậy cùng event `ZGROUP_ML01` xuất hiện trong màn hình GS; JSON trace cũng có thể giữ dữ liệu nhóm trước.

Đã sửa cả API và UI:

- GET `/api/mock/messages?group_id=...` chỉ trả lịch sử của đúng nhóm. Không có API trả toàn bộ nhóm cho giao diện chat; query mặc định là GS để tương thích demo cũ.
- Retry phải mang cùng `group_id`; không tìm lại event của nhóm khác.
- Đổi nhóm xóa ngay feed/payload/receipt/callback/steps. Frontend lọc lại group và bỏ các response cũ theo sequence + group; polling không được vẽ lại nội dung của nhóm đã rời.
- Callback ký HMAC còn phải khớp event và group gốc; không thể chuyển callback ML sang GS.

Ảnh ban đầu là lỗi hiển thị lịch sử. Kiểm tra database cho thấy cả 14 tài liệu Machine Learning chỉ có scope `class:ML-DEMO-01`, không được cấp cho GS. Kiểm thử còn xác nhận Backend không cho sender sai lớp chạy RAG, không dùng memory lớp khác và Qdrant lọc scope/active trước search ngay cả khi vector hai lớp giống hệt nhau.

## Đăng nhập

Lần đầu vẫn phải khởi tạo một admin. Sau đó màn hình có chọn vai trò:

| Vai trò | Cách chọn hồ sơ | Quyền |
|---|---|---|
| Admin | Username + mật khẩu | Tạo hồ sơ, cấp credential, quản lý lớp và phân công |
| Giảng viên | Chọn tên hồ sơ đã được admin cấp đăng nhập + mật khẩu | Chỉ các lớp có teacher_assignment active |
| Học viên | Chọn lớp → Học viên STT → mật khẩu | Session giới hạn trong lớp được chọn; cần enrollment active |

Chọn role không tự cấp quyền: backend so sánh với `users.role`. Chọn sai role, lớp không có enrollment hoặc tài khoản bị khóa đều không tạo phiên. Danh sách tên giảng viên chỉ có hồ sơ active đã được cấp credential bởi admin; không có đăng ký giảng viên công khai.

GET `/api/v1/auth/options?role=teacher` cung cấp tên/username cho picker local. Role student trả metadata lớp và hồ sơ đánh số theo lớp. Không trả password/hash/token. Học viên chưa có credential được hiển thị nhưng không chọn để đăng nhập được; admin dùng **Tài khoản → Cấp đăng nhập**. Không tạo mật khẩu mặc định từ STT.

Session học viên do picker tạo lưu `auth_sessions.class_id`; Backend kiểm tra enrollment/class còn active trên mỗi request và giới hạn `/classes`, group messages, support requests và các API lớp theo session. Đổi mật khẩu giữ giới hạn lớp. API login cũ không truyền role vẫn tương thích và chỉ nhận các lớp thực sự đăng ký của tài khoản; không thể chọn role để vượt enrollment.

## Metadata lớp và STT

Nguồn quyền là metadata trong SQLite: `classes`, `group_bindings`, `enrollments`, `teacher_assignments`, `external_identities`. Không đoán lớp từ tên người, tên file hoặc nội dung câu hỏi.

- `enrollments.student_number` là số nguyên dương, unique trong từng lớp.
- Khi ghi enrollment mới, trigger cấp MAX(student_number)+1 trong transaction. Một học viên học hai lớp có thể có STT khác nhau ở mỗi lớp.
- Migration backfill hồ sơ cũ theo joined_at/user_id, không đổi user_id, membership hay credential cũ.
- STT đã cấp được giữ nguyên khi tạm dừng/quay lại lớp. Không dùng vị trí trang/pagination làm STT và không lấy thứ tự UUID để hiển thị.
- POST `/api/v1/classes` nhận `student_count` tùy chọn (0–500). Admin khai báo 49 thì tạo đủ 49 hồ sơ `Học viên 1`…`Học viên 49`, enrollment và identity cho lớp đó.
- PUT `/api/v1/classes/{id}/roster` với `{"student_count":49}` đồng bộ sĩ số tối thiểu theo metadata cho lớp có sẵn. Cùng sĩ số thì idempotent, tăng sĩ số thì cấp STT tiếp theo, giảm xuống dưới số hồ sơ hiện có bị từ chối để tránh xóa lịch sử. Tạm dừng học viên quản lý riêng.
- Form **Tạo lớp → Sĩ số theo metadata** và **Chi tiết lớp → Sĩ số từ metadata** gọi các API trên. Số 49 chỉ là ví dụ, không tự tạo 49 người cho các lớp hiện có khi chưa khai báo metadata đó.

Các hồ sơ học viên sinh từ metadata chưa có mật khẩu; admin cấp đăng nhập theo quy trình hiện có. STT và mã lớp là định danh hiển thị, không phải bằng chứng xác thực.

## Giả lập lấy danh sách từ Backend

Backend GET `/api/v1/mock/catalog` chỉ dành cho service adapter/admin. Simulator dùng adapter token ở server để gọi, rồi trả metadata tối thiểu qua `/api/mock/catalog`: group/class, sĩ số, sender và nhãn `Học viên N`. Mỗi học viên xuất hiện một lần dù có nhiều external identity. Token không đưa xuống JavaScript.

Dropdown nhóm và học viên không còn hardcode GS/ML demo. Đổi nhóm lấy roster tương ứng từ catalog đã tải. Số thứ tự là của enrollment lớp đó, không dùng tên hoặc số toàn hệ thống. Giả lập vẫn là công cụ local để giả danh người gửi kiểm thử; Backend webhook độc lập kiểm tra sender → identity → enrollment → group/class, không tin lựa chọn của UI.

## Schema và kiểm tra

Migration `0003_class_rosters.sql`: thêm `enrollments.student_number` và `auth_sessions.class_id`, unique index và trigger cấp/giữ STT. Tổng 30 bảng, 308 cột. Đã sao lưu database thật trước migration; hash tất cả giá trị cột cũ khớp trước/sau, foreign_key_check không có lỗi.

- 91 test tự động; 18 kiểm tra DDL.
- Chromium QA cô lập ở `/private/tmp/gos-class-access-qa`, không dùng key Claude hoặc dữ liệu nghiệp vụ thật: admin tạo lớp 49 qua form; chọn tên giảng viên; chọn lớp/STT49 đăng nhập; kiểm tra API sai lớp; GS/ML tách lịch sử; giữ response ML về chậm rồi đổi sang GS để kiểm tra race.
- Báo cáo: `data/exports/class-access-browser-check.json`; ảnh `class-student-49-qa.png`, `class-chat-isolation-qa.png`.

Cần khởi động lại backend và simulator để nạp code mới; dùng `scripts/run_rag.py`, sau đó refresh cả portal và chat.
