## Mục đích

Mock Zalo, metadata cập nhật, routes portal/report và app lifecycle.

## Phạm vi

- `app/api/routes/portal.py`
- `app/api/routes/reports.py`
- `app/main.py`
- `app/simulator.py`
- `app/static/mock_zalo.html`
- `docs/contracts/08-api-implementation.md`
- `docs/contracts/openapi.json`

## Phụ thuộc và kiểm tra

Đây là PR 14/20 trong chuỗi bàn giao, base `delivery/13-portal-frontend`. Các module được lắp ghép dần; không tuyên bố mọi nhánh trung gian là app chạy độc lập. Bản đầy đủ đã đạt 130 test, 18 kiểm tra DDL và kiểm tra nạp corpus/UI; bằng chứng nằm ở PR 20. Sau PR 14 có thể kiểm tra app assembly; sau PR 17–19 chạy tập test tương ứng.

## Bảo mật và dữ liệu

Không đưa .env, API key, DB vận hành, logs hoặc model cache vào Git. Học liệu demo và dữ liệu golden là dữ liệu được chọn để bàn giao.

## Merge

Review theo thứ tự 01 → 20. Sau khi PR trước đã merge vào main, đổi base PR kế tiếp sang main rồi merge bằng merge commit để giữ chuỗi commit; tránh merge nhầm vào nhánh phụ. PR được chuẩn bị dạng draft để review trước.
