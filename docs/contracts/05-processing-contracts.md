# Hợp đồng xử lý

Zalo Bot adapter lấy getUpdates, chuẩn hóa IncomingEvent rồi gọi EventService nội bộ.
Không có API công khai nhận sự kiện tùy ý. IncomingEvent chỉ chấp nhận platform zalo_bot.

Event ID duy nhất theo bot/chat/message. Chat phải gắn lớp active và bot lớp bật. Người gửi
được định danh từ API Zalo, không tự chọn lớp bằng prompt. Tin do bot gửi bị bỏ qua.
Quota theo hash platform + sender ID. Lưu event và quota trước khi worker xử lý model.

Worker lấy memory của nhóm, rewrite câu hỏi, retrieval theo scope/active version, rerank và
Claude đánh giá bằng chứng. Backend xác minh citation; lỗi hoặc thiếu nguồn tạo ticket.
Outbox kiểm tra lại quyền trước gọi sendMessage và retry có giới hạn. Trả lời giảng viên
cũng đi cùng outbox về chat gốc. Không đánh dấu sent chỉ dựa trên HTTP 200.
