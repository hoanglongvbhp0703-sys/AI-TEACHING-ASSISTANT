# Demo bằng Zalo Bot thật

1. Chạy `python scripts/run_rag.py`, đăng nhập portal tại cổng 8002.
2. Kiểm tra học liệu Machine Learning/Google Sheets đã active.
3. Nhắn riêng bot hoặc tag bot trong nhóm; gắn chat với đúng lớp trên portal.
4. Hỏi `Các bước của K-means là gì?` trong lớp Machine Learning; kiểm tra câu trả lời và trích dẫn.
5. Hỏi nội dung ngoài tài liệu để kiểm tra chuyển giảng viên.
6. Giảng viên phản hồi ticket; kiểm tra câu trả lời về đúng chat Zalo.
7. Dùng một nhóm lớp khác để xác minh tài liệu và memory được tách biệt.
8. Thay phiên bản tài liệu: bản cũ phục vụ đến khi bản mới index xong, sau đó chỉ active version được truy xuất.

Golden dataset và tài liệu mẫu đi kèm dùng để đánh giá RAG; chạy evaluator trên dữ liệu cô lập, không dùng tài khoản thật để phát tin kiểm thử hàng loạt.
