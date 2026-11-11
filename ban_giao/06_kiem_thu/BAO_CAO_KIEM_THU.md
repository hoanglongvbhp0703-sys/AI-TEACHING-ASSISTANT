# Báo cáo kiểm thử và lỗi tồn đọng

Đợt đóng gói 12/11/2026. Kiểm thử tự động được chạy lại trên database tạm; kết quả thực tế nằm ở `pytest-results.xml`, `schema-validation.txt` và danh sách node IDs `test-cases.txt`. Không chạy lại các request Claude trong golden khi đóng gói; kết quả model thật dưới đây là lượt đã lưu ngày 11/11/2026.

## 1. Phạm vi và bằng chứng

- Unit/integration: auth, role/ACL, lớp/roster, search tài khoản, webhook/dedup/quota, memory/rewriter, version/reindex/revoke, ingestion, outbox/retry, ticket/FAQ, progress/logging, parser và công thức metric.
- Các test dùng model/gateway double được ghi rõ trong fixtures; không coi chúng là benchmark BKAI/Claude thật.
- `golden_summary.json`, `golden_results.csv`: model thật BKAI/Qdrant/mMARCO/Claude Sonnet 4.6, 40 câu golden, nhóm `ZGROUP_ML01`, lớp `ML-DEMO-01`, 14 PDF và 594 chunks. Metadata 40/40 event và nguồn đúng scope/active đã được kiểm tra.
- `bootstrap-check.json`: kiểm tra mới nạp corpus bằng script bàn giao trên thư mục riêng; không dùng DB vận hành. Screenshot hướng dẫn là UI QA, không làm bằng chứng cho điểm RAG.

## 2. Kết quả golden

| Metric | Kết quả | Định nghĩa |
|---|---:|---|
| Recall@5 file + trang | 80.77% | 21/26 nhãn file/page có trong Top 5; gold_chunk_ids rỗng nên chưa là chunk-recall chuẩn |
| Answer Correctness | 70.38% | Mean semantic fact-F1 trên 26 câu dương, không trả lời/lỗi = 0 |
| Faithfulness | 100% | 55/55 claims có hỗ trợ trong Top 5, chỉ trên 19 câu đã trả lời |
| Citation Faithfulness | 100% | 57/57 cặp claim–source hỗ trợ đúng, chỉ trên 19 câu đã trả lời |
| Answerability F1 toàn luồng | 84.44% | TP19, FP0, FN7, TN14; answered là dự đoán dương |
| Khớp answer/handoff/blocked | 67.5% | 27/40 hành vi đúng nhãn |

Chấm ngữ nghĩa bằng Claude ở request riêng, cùng model với generator. Correctness = `2*matched/(2*matched+missing+incorrect)`. Không đếm từ giống nhau. Hai quote cùng chunk trong một claim là một citation edge. Nhãn judge đã được kiểm tra coverage và tính nhất quán; vẫn cần người chấm độc lập. Không dùng reference/history để chứng minh Faithfulness. Backend kiểm tra quote tồn tại là kiểm tra riêng với entailment ngữ nghĩa.

Trạng thái: 19 answered, 18 insufficient_evidence, 3 error, 0 blocked. Ba lỗi kỹ thuật gồm 012/015/035; F1 toàn luồng vẫn tính đủ 40. Ca âm có lỗi kỹ thuật không được coi là đã từ chối an toàn. Nếu chỉ xét 37 ca không lỗi thì F1=88.37%, đây là metric có điều kiện.

## 3. Lỗi tồn đọng và hướng cải thiện

| ID / nhóm | Thực tế | Hướng ưu tiên |
|---|---|---|
| 012 K-fold, 015 KNN hỏi tiếp, 035 encoded injection | invalid_model_output | Ổn định structured output/schema; phân loại lỗi, retry có giới hạn và theo dõi token |
| 014 KNN, 017 Random Forest, 023 kernel trick | quote_not_in_source | Cải thiện quote nguyên văn với PDF dính chữ; không nới phép cho citation bịa |
| 002/015/021/038/039 | Top 5 thiếu trang golden | Đo recall với paraphrase/hỏi tiếp/wrapper; gold phải bao phủ nguồn liên quan hợp lệ |
| 031/032/033/034/037 | Handoff tạo ticket thay vì blocked | Phân biệt injection và thiếu dữ liệu nghiệp vụ; không chặn nhầm câu học thuật lành tính |
| 038/039 | Directive giả làm giảm retrieval, câu lành tính chưa được trả lời | Làm rõ truy vấn học thuật và kiểm thử adversarial, giữ ACL cứng |
| Parser PDF | Text-only, hạn chế hình/sơ đồ/scan | Đánh giá OCR/multimodal riêng với test set phù hợp |
| Chi phí/vận hành | Có token ledger/quota, chưa hard budget tiền | Ngưỡng ngân sách, cảnh báo, giá cache, đối soát provider |

## 4. Tái chạy

```bash
python -m pytest -q
python scripts/validate_schema.py
```

Nạp PDF và dừng server trước khi chạy evaluator snapshot như hướng dẫn trong `03_demo/README.md`. Đánh giá model thật có chi phí; report mới phải ghi model/config/dataset/metadata, không gộp với lượt cũ. Sau khi sửa lỗi nên dùng thêm holdout và người chấm, tránh chỉ tuning theo 40 câu golden.

Video không nằm trong lần bàn giao này. Bộ báo cáo là bằng chứng kiểm thử local, chưa thay thế nghiệm thu tải, production security hoặc Zalo thật.
