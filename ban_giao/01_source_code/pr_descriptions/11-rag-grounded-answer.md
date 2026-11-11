## Mục đích

Qdrant Top10/Top5, scope/active version, đánh giá toàn bộ nguồn và xác minh citation.

## Phạm vi

- `app/rag/backend.py`
- `app/rag/local_backend.py`
- `app/rag/provider.py`
- `docs/architecture/10-rag-implementation.md`
- `docs/architecture/16-claude-content-evidence.md`

## Phụ thuộc và kiểm tra

Đây là PR 11/20 trong chuỗi bàn giao, base `delivery/10-parsing-local-models`. Các module được lắp ghép dần; không tuyên bố mọi nhánh trung gian là app chạy độc lập. Bản đầy đủ đã đạt 130 test, 18 kiểm tra DDL và kiểm tra nạp corpus/UI; bằng chứng nằm ở PR 20. Sau PR 14 có thể kiểm tra app assembly; sau PR 17–19 chạy tập test tương ứng.

## Bảo mật và dữ liệu

Không đưa .env, API key, DB vận hành, logs hoặc model cache vào Git. Học liệu demo và dữ liệu golden là dữ liệu được chọn để bàn giao.

## Merge

Review theo thứ tự 01 → 20. Sau khi PR trước đã merge vào main, đổi base PR kế tiếp sang main rồi merge bằng merge commit để giữ chuỗi commit; tránh merge nhầm vào nhánh phụ. PR được chuẩn bị dạng draft để review trước.
