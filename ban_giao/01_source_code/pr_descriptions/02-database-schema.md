## Mục đích

Schema v1–v4, seed hai lớp, kết nối DB, tài liệu dữ liệu và kiểm tra DDL.

## Phạm vi

- `app/db/migrations/versions/0001_initial.sql`
- `app/db/migrations/versions/0002_authentication.sql`
- `app/db/migrations/versions/0003_class_rosters.sql`
- `app/db/migrations/versions/0004_query_rewriting.sql`
- `app/db/seed.py`
- `app/db/session.py`
- `docs/database/02-database-design.md`
- `docs/database/03-data-dictionary.md`
- `docs/database/04-authentication.md`
- `docs/database/schema.sqlite.sql`
- `docs/testing/schema-validation-results.md`
- `scripts/init_local.py`
- `scripts/validate_schema.py`

## Phụ thuộc và kiểm tra

Đây là PR 02/20 trong chuỗi bàn giao, base `delivery/01-project-foundation`. Các module được lắp ghép dần; không tuyên bố mọi nhánh trung gian là app chạy độc lập. Bản đầy đủ đã đạt 130 test, 18 kiểm tra DDL và kiểm tra nạp corpus/UI; bằng chứng nằm ở PR 20. Sau PR 14 có thể kiểm tra app assembly; sau PR 17–19 chạy tập test tương ứng.

## Bảo mật và dữ liệu

Không đưa .env, API key, DB vận hành, logs hoặc model cache vào Git. Học liệu demo và dữ liệu golden là dữ liệu được chọn để bàn giao.

## Merge

Review theo thứ tự 01 → 20. Sau khi PR trước đã merge vào main, đổi base PR kế tiếp sang main rồi merge bằng merge commit để giữ chuỗi commit; tránh merge nhầm vào nhánh phụ. PR được chuẩn bị dạng draft để review trước.
