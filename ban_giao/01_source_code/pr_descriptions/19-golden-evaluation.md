## Mục đích

Evaluator model thật, phép tính metric, kiểm tra judge và báo cáo golden.

## Phạm vi

- `docs/architecture/17-content-evidence-evaluation.md`
- `docs/architecture/18-golden-it3190-evaluation.md`
- `docs/testing/11-rag-machine-learning-results.md`
- `docs/testing/14-rag-runtime-diagnosis.md`
- `scripts/compare_content_evidence.py`
- `scripts/evaluate_golden.py`
- `scripts/evaluate_rag.py`
- `scripts/golden_metrics.py`
- `tests/unit/test_golden_judge.py`
- `tests/unit/test_golden_metrics.py`

## Phụ thuộc và kiểm tra

Đây là PR 19/20 trong chuỗi bàn giao, base `delivery/18-rag-regression-tests`. Các module được lắp ghép dần; không tuyên bố mọi nhánh trung gian là app chạy độc lập. Bản đầy đủ đã đạt 130 test, 18 kiểm tra DDL và kiểm tra nạp corpus/UI; bằng chứng nằm ở PR 20. Sau PR 14 có thể kiểm tra app assembly; sau PR 17–19 chạy tập test tương ứng.

## Bảo mật và dữ liệu

Không đưa .env, API key, DB vận hành, logs hoặc model cache vào Git. Học liệu demo và dữ liệu golden là dữ liệu được chọn để bàn giao.

## Merge

Review theo thứ tự 01 → 20. Sau khi PR trước đã merge vào main, đổi base PR kế tiếp sang main rồi merge bằng merge commit để giữ chuỗi commit; tránh merge nhầm vào nhánh phụ. PR được chuẩn bị dạng draft để review trước.
