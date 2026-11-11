# Demo và dữ liệu mẫu

Hai lớp được seed: Google Sheets và Machine Learning. Bộ 14 PDF ML giữ trong `Machine Learning copy/ML-P1` và `ML-P2`; đây là học liệu người dùng cung cấp, không phải phần mềm được cấp một giấy phép mới trong repo. `tai_lieu_mau/google_sheets_demo.docx` là tài liệu Sheets demo. `faq_machine_learning.json` là mẫu FAQ để thử luồng đọc/index, không dùng thay nhãn golden.

Nạp bằng `python scripts/load_demo_documents.py` khi backend đang dừng. Script tạo metadata/index qua DocumentService và worker, cấp ML PDF cho lớp ML, DOCX cho lớp GS. Lần nạp lại dùng cùng source_code/document_id; không tự đoán tài liệu thay thế dựa vào tên/nội dung. Script có thể mất thời gian tải model và index; không gọi Claude để sinh đáp án trong bước index.

## Kịch bản thao tác

1. Tạo admin đầu tiên tại portal. Vào Tài khoản tạo giảng viên; vào chi tiết lớp phân công giảng viên.
2. Tài khoản có thể tìm theo tên/mã/username và lọc vai trò. Khi cần học viên mới, tạo tài khoản rồi thêm vào lớp, hoặc tăng sĩ số theo metadata. Cấp mật khẩu riêng nếu học viên cần đăng nhập portal.
3. Trong Mock Zalo, chọn ML và học viên của ML, gửi `/hoi Các bước chính của thuật toán K-means là gì?`. Mong muốn: answered kèm nguồn/trang, nếu có đủ bằng chứng hợp lệ.
4. Gửi `/hoi Học phí chính thức của khóa này hiện nay là bao nhiêu?`. Học liệu kỹ thuật không có biểu phí hiện hành: mong muốn handoff, không bịa.
5. Giảng viên vào Yêu cầu hỗ trợ, nhận/phản hồi; học viên xem phản hồi trong giả lập hoặc mục hỗ trợ tương ứng.
6. Chuyển sang Google Sheets, hỏi `/hoi Hàm SUM dùng để làm gì?`. Chỉ dùng nguồn được cấp cho GS; không hiện lịch sử chat ML.
7. Gửi lại cùng event ID bằng nút trong giả lập: không phát sinh một lượt nghiệp vụ mới.
8. Tạo lớp mới nếu cần, nhập sĩ số, sau đó vào chi tiết lớp → Liên kết nhóm. Giả lập cập nhật catalog mỗi 5 giây. Giảng viên không nằm trong selector người gửi học viên.

## Golden dataset

`GOS_IT3190_Golden_Dataset_40.jsonl` có 26 câu answerable, 14 câu âm/injection, gồm 2 history fixtures. File/trang golden dựa trên PDF gốc; `gold_chunk_ids` đang trống. Không trộn tài liệu GS vào scope ML để chạy bộ này.

Sau khi nạp PDF và dừng server để tạo snapshot nhất quán, có thể đánh giá lại bằng lệnh dưới đây. Lệnh gọi Claude cho RAG và chấm ngữ nghĩa, có phát sinh chi phí; dùng snapshot/output mới cho mỗi lượt. `--resume` tiếp tục lượt bị gián đoạn.

```bash
python scripts/evaluate_golden.py ban_giao/03_demo/GOS_IT3190_Golden_Dataset_40.jsonl --snapshot data/golden-handover-run --output data/exports/golden-handover-run.json
```

Không cần bàn giao DB cũ. Báo cáo và kết quả từng câu của lượt đã chạy được xuất trong `06_kiem_thu/`.

Demo local có thể gọi LLM tính phí. Để dừng, Ctrl+C ở terminal chạy `run_rag.py`. Giữ data/ để tiếp tục phiên sau; không chạy nhiều backend cùng mở Qdrant Local.
