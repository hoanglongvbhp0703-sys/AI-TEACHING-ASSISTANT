# Vận hành và tích hợp Zalo

Bản hiện tại dùng Zalo Bot Platform qua polling, không yêu cầu OA Access Token cho kênh này. Bot Token do người vận hành tạo trong Bot Creator. Trong nhóm, dùng tag/reply để nền tảng chuyển tin tới bot; backend nhận tin và áp dụng liên kết chat/lớp.

## Chi phí và nguồn lực

- BKAI, mMARCO và Qdrant Local chạy trên máy chủ của người vận hành; cần RAM/CPU và dung lượng cho model, vector và uploads.
- Claude qua gateway tính phí theo tài khoản và model của người vận hành. Backend ghi token usage, call audit và chi phí biết được; không gán giá giả khi chưa có bảng giá.
- Hạn mức và phí Bot Platform cần kiểm tra trong tài khoản Zalo lúc sử dụng. Không mặc định mọi quyền, nhóm hoặc lượng tin đều miễn phí.
- Quota 30 câu/ngày/người gửi và rate limit không phải trần chi phí tiền tệ. Cần ngân sách theo ngày/tháng và cảnh báo trước khi vận hành rộng.

## Điều kiện vận hành

Một backend sở hữu SQLite/Qdrant và một poller cho bot trên máy. Polling không cần URL HTTPS công khai. Đưa portal lên mạng cần TLS, quản lý secret, giới hạn truy cập và monitoring. Triển khai nhiều máy cần thiết kế khóa phân tán/hàng đợi và kho dữ liệu phù hợp; chưa có kiểm thử tải 20 lớp đồng thời.

Giữ nguyên phân quyền tài liệu/active version ở backend. Kiểm tra lại quyền trước khi gửi, hạn chế log nhạy cảm và diễn tập backup/restore. API gửi tin có thể phát trùng khi mất ACK sau khi nền tảng đã nhận; chưa có bảo đảm exactly-once.

Adapter OA/GMF là một hướng tích hợp riêng, hiện chưa triển khai. Nếu đơn vị chọn OA, cần xác nhận OA, quyền App, cơ chế token và điều kiện dịch vụ theo tài liệu Zalo tương ứng; không thay Bot Token bằng User Access Token.
