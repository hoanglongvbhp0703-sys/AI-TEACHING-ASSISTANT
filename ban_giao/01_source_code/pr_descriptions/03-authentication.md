## Mục đích

Mật khẩu Argon2id, phiên đăng nhập, phân quyền role và redaction.

## Phạm vi

- `app/api/deps.py`
- `app/api/routes/auth.py`
- `app/core/passwords.py`
- `app/core/runtime_logging.py`
- `app/core/security.py`
- `app/schemas/auth.py`
- `app/services/auth_service.py`

## Phụ thuộc và kiểm tra

Đây là PR 03/20 trong chuỗi bàn giao, base `delivery/02-database-schema`. Các module được lắp ghép dần; không tuyên bố mọi nhánh trung gian là app chạy độc lập. Bản đầy đủ đã đạt 130 test, 18 kiểm tra DDL và kiểm tra nạp corpus/UI; bằng chứng nằm ở PR 20. Sau PR 14 có thể kiểm tra app assembly; sau PR 17–19 chạy tập test tương ứng.

## Bảo mật và dữ liệu

Không đưa .env, API key, DB vận hành, logs hoặc model cache vào Git. Học liệu demo và dữ liệu golden là dữ liệu được chọn để bàn giao.

## Merge

Review theo thứ tự 01 → 20. Sau khi PR trước đã merge vào main, đổi base PR kế tiếp sang main rồi merge bằng merge commit để giữ chuỗi commit; tránh merge nhầm vào nhánh phụ. PR được chuẩn bị dạng draft để review trước.
