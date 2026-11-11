# Đối chiếu các câu /hoi bị chặn và sửa query context

Kiểm tra ngày 11/11/2026 bằng event/call audit trong SQLite và snapshot Qdrant local. Không suy số lần gọi provider từ số callback hoặc HTTP 202.

## Từng trường hợp người dùng cung cấp

| Event | User/lớp | Kết quả thực tế |
|---|---|---|
| `c11b80ea...` | HV_AUTO_01 / AUTO-N8N-01 | Có embedding/rerank; nguồn được cấp là unit1.pdf của lớp AUTO, không phải 14 PDF ML. Chuyển giảng viên là đúng theo quyền hiện có. |
| `294e9940...` | HV_GS_01 / GS-KPI-01 | Quota exceeded, không tạo rag_run, không gọi embedding/LLM. |
| `a1f2b90b...` | HV_GS_02 / GS-KPI-01 | Có rag_run nhưng snapshot active_versions rỗng; không embedding/rerank/LLM. |
| `448e240b...` | HV_GS_01 / ML-DEMO-01 | Quota exceeded, không vào RAG; đây là ảnh thông báo hết lượt. |
| `e537d341...` | ML-DEMO-STUDENT / ML-DEMO-01 | Có 14 active versions và embedding/rerank. Câu `thuât toán hồi quy là gì` bị gate loại; không gọi LLM. |
| `a03818e0...` | ML-DEMO-STUDENT / ML-DEMO-01 | Có 14 active versions và embedding/rerank, nhưng query bị ghép sai câu hồi quy trước đó; không gọi LLM. |

Snapshot Qdrant có **594 points** thuộc 14 active version được cấp cho ML; dữ liệu đã index thực sự, không chỉ có hồ sơ metadata SQLite. Tái hiện trên snapshot riêng, không mở Qdrant path đang được server giữ và không dùng quota thật.

## Lỗi query context đã tìm và sửa

Code cũ ghép câu hỏi trước vào mọi câu ngắn hơn 12 từ. Điều đó làm câu hỏi mới bị lệch chủ đề:

| Truy vấn tái hiện | Best rerank |
|---|---:|
| `thuật toán hồi quy là gì`, không memory | 0.08906 |
| `thuât toán hồi quy là gì`, không memory | 0.04302 |
| `Machine Learning là gì`, không ghép câu trước | 0.99830 |
| `thuât toán hồi quy là gì` + `Machine Learning là gì` | 0.02917 |

Ngưỡng strong cũ là 0.05. Câu gõ sai bị loại sát ngưỡng; câu ML mới bị ghép hồi quy rồi rơi dưới ngưỡng dù đúng tài liệu có đáp án.

Đã đổi sang chỉ mở rộng query khi có dấu hiệu hỏi tiếp: “nó”, “thuật toán đó”, “mô hình này”, “cho em ví dụ”, “giải thích thêm”… Câu hỏi độc lập giữ nguyên. Memory vẫn được đưa cho LLM để hiểu hội thoại, nhưng không phải nguồn bằng chứng. Đây là heuristic ngôn ngữ MVP; các câu tiếp nối mơ hồ chưa có giải quyết đại từ bằng model riêng.

## Evidence gate ba nhánh

- Có active source và best rerank >= 0.05: đưa Top 5 cho LLM như trước.
- Điểm trong vùng xét lại (mặc định >= 0.02) và cosine của ứng viên đầu >= 0.35: cho LLM đánh giá đủ bằng chứng thay vì kết luận thiếu ngay. Model vẫn phải trả claims kèm quote nguyên văn; Backend kiểm tra source/citation trước khi phát.
- Không có nguồn đúng quyền, không có ứng viên hoặc điểm quá yếu: handoff, không gọi provider.

Không hạ ngưỡng vô điều kiện, không bỏ filter lớp/active version. Các ngưỡng xét lại là cấu hình MVP, chưa được hiệu chuẩn trên tập dữ liệu độc lập lớn. Thêm log `rag_evidence_decision` với event/run ID, số active version, số ứng viên, best_rerank, threshold, decision; không ghi nội dung câu hỏi hoặc PDF vào log.

Cấu hình mới: `RAG_REVIEW_SCORE_FLOOR=0.02`, `RAG_REVIEW_VECTOR_FLOOR=0.35`. Model embedding/index không đổi nên không cần reindex.

## Quota bị bộ thử tự động sử dụng

30 reservation của HV_GS_01 ngày 11/11/2026 được xác định chính xác là hai lượt chạy bộ 15 câu của agent, trong khoảng UTC 10/11 19:46–19:49. Đã kiểm tra mỗi câu xuất hiện đúng hai lần, sao lưu DB rồi chuyển riêng các reservation đó sang released với lý do `exclude_agent_evaluation_correction`, giảm used 30 → 0 và ghi audit. Giữ nguyên event, model-call logs, charged_at và các dữ liệu nghiệp vụ; không reset quota của người dùng khác hoặc xóa câu hỏi thật.

Đánh giá đầy đủ bằng `scripts/evaluate_rag.py` nay mặc định dùng `data/rag-evaluation` riêng và tài khoản ML-EVAL-STUDENT. `--data-dir` cho phép chọn thư mục riêng khác. `--import-only` vẫn nạp corpus vào DB được cấu hình để phục vụ thao tác nhập tài liệu, không chạy câu hỏi; các request đánh giá có prefix request_id `evaluation-` để nhận biết.

Các event đã bị quota chặn vẫn giữ nguyên kết quả cũ để bảo đảm idempotency. Sau khởi động lại, gửi **tin mới/event ID mới**, không bấm gửi lại event quota_exceeded cũ để mong nó chạy lại RAG.

## Tiến trình không đánh đồng callback với RAG

Callback nghiệp vụ được ký HMAC kèm `processing`: outcome_code, retrieval_called, llm_called và label. Quota/rate limit/quyền bị chặn trả 0%, ghi rõ chưa vào RAG. Trả lời có LLM và chuyển giảng viên được phân biệt. GET event progress cũng có kết quả tương ứng. Callback kết nối thuần vẫn có trạng thái nhận phản hồi nhưng không tuyên bố đã chạy RAG.

## Kiểm tra sau sửa

- 109 test tự động: câu hỏi mới không thừa hưởng chủ đề cũ; câu hỏi tiếp nối vẫn dùng memory; nguồn sát ngưỡng được xét lại; nguồn quá yếu không gọi provider; callback quota có percent=0, retrieval_called=false, llm_called=false.
- Chạy thật trên snapshot với Sonnet 4.6: `thuât toán hồi quy là gì` trả answered với nguồn L3 trang 5; `Machine Learning là gì` sau câu hồi quy trả answered với 3 citations. Không sử dụng quota live cho hai ca xác minh.
- Kết quả: `data/exports/rag-current-query-diagnosis.json`, `rag-query-fix-live-check.json`, `evaluation-quota-correction.json`.

Cần khởi động lại `scripts/run_rag.py` để Python nạp logic mới. Dữ liệu đang active được giữ nguyên; không cần tải lại 14 PDF.
