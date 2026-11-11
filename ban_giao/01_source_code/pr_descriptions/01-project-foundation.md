## Mục đích

pyproject, cấu hình môi trường mẫu, kiểu dữ liệu chung và cấu trúc package.

## Phạm vi

- `.env.example`
- `app/__init__.py`
- `app/api/__init__.py`
- `app/api/routes/.gitkeep`
- `app/api/routes/__init__.py`
- `app/core/.gitkeep`
- `app/core/__init__.py`
- `app/core/clock.py`
- `app/core/config.py`
- `app/core/errors.py`
- `app/db/__init__.py`
- `app/db/migrations/__init__.py`
- `app/db/migrations/versions/.gitkeep`
- `app/db/migrations/versions/__init__.py`
- `app/db/models/.gitkeep`
- `app/db/models/__init__.py`
- `app/integrations/.gitkeep`
- `app/integrations/__init__.py`
- `app/jobs/.gitkeep`
- `app/jobs/__init__.py`
- `app/rag/__init__.py`
- `app/rag/evaluation/.gitkeep`
- `app/rag/evaluation/__init__.py`
- `app/rag/parsers/.gitkeep`
- `app/rag/parsers/__init__.py`
- `app/rag/prompts/.gitkeep`
- `app/rag/schemas.py`
- `app/repositories/.gitkeep`
- `app/repositories/__init__.py`
- `app/repositories/store.py`
- `app/schemas/.gitkeep`
- `app/schemas/__init__.py`
- `app/schemas/common.py`
- `app/services/.gitkeep`
- `app/services/__init__.py`
- `app/static/.gitkeep`
- `examples/events/.gitkeep`
- `examples/faq/.gitkeep`
- `pyproject.toml`
- `tests/acceptance/.gitkeep`
- `tests/fixtures/.gitkeep`
- `tests/integration/.gitkeep`
- `tests/unit/.gitkeep`

## Phụ thuộc và kiểm tra

Đây là PR 01/20 trong chuỗi bàn giao, base `main`. Các module được lắp ghép dần; không tuyên bố mọi nhánh trung gian là app chạy độc lập. Bản đầy đủ đã đạt 130 test, 18 kiểm tra DDL và kiểm tra nạp corpus/UI; bằng chứng nằm ở PR 20. Sau PR 14 có thể kiểm tra app assembly; sau PR 17–19 chạy tập test tương ứng.

## Bảo mật và dữ liệu

Không đưa .env, API key, DB vận hành, logs hoặc model cache vào Git. Học liệu demo và dữ liệu golden là dữ liệu được chọn để bàn giao.

## Merge

Review theo thứ tự 01 → 20. Sau khi PR trước đã merge vào main, đổi base PR kế tiếp sang main rồi merge bằng merge commit để giữ chuỗi commit; tránh merge nhầm vào nhánh phụ. PR được chuẩn bị dạng draft để review trước.
