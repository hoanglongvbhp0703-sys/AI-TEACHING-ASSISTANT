## Mục đích

Auth, tài khoản/lớp, webhook, tài liệu, ticket và giả lập.

## Phạm vi

- `tests/conftest.py`
- `tests/integration/test_account_catalog.py`
- `tests/integration/test_api.py`
- `tests/integration/test_class_access.py`
- `tests/integration/test_connection_demo.py`
- `tests/integration/test_document_mvp.py`
- `tests/integration/test_password_auth.py`
- `tests/integration/test_portal.py`
- `tests/integration/test_progress_and_logging.py`
- `tests/integration/test_webhooks.py`

## Phụ thuộc và kiểm tra

Đây là PR 17/20 trong chuỗi bàn giao, base `delivery/16-sample-materials`. Các module được lắp ghép dần; không tuyên bố mọi nhánh trung gian là app chạy độc lập. Bản đầy đủ đã đạt 130 test, 18 kiểm tra DDL và kiểm tra nạp corpus/UI; bằng chứng nằm ở PR 20. Sau PR 14 có thể kiểm tra app assembly; sau PR 17–19 chạy tập test tương ứng.

## Bảo mật và dữ liệu

Không đưa .env, API key, DB vận hành, logs hoặc model cache vào Git. Học liệu demo và dữ liệu golden là dữ liệu được chọn để bàn giao.

## Merge

Review theo thứ tự 01 → 20. Sau khi PR trước đã merge vào main, đổi base PR kế tiếp sang main rồi merge bằng merge commit để giữ chuỗi commit; tránh merge nhầm vào nhánh phụ. PR được chuẩn bị dạng draft để review trước.
