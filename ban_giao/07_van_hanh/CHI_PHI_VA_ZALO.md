# Chi phí vận hành và điều kiện tích hợp Zalo thật

Cập nhật 12/11/2026. Tài liệu này là mô hình dự toán và danh sách điều kiện kỹ thuật, không phải báo giá của gateway hoặc cam kết phí Zalo.

## 1. Các khoản chi

| Khoản | Local demo | Demo trên server |
|---|---|---|
| Backend/SQLite/Qdrant | Máy đang có, điện và dung lượng | Chi phí máy chủ H, lưu trữ và backup B |
| BKAI/mMARCO | CPU local, tải/cache model | CPU/RAM của server, cần benchmark tải thực |
| Claude/gateway | Theo token request thực tế | Theo token, bao gồm query rewrite và câu bị từ chối sau retrieval |
| Domain/TLS/giám sát | Không bắt buộc cho localhost | Domain, TLS/reverse proxy, monitoring theo phương án vận hành |
| Zalo | Giả lập, không gọi API Zalo | Điều kiện quyền/gói dịch vụ/phí được xác nhận riêng với Zalo |
| Bảo trì | Sửa lỗi tồn đọng, cập nhật học liệu | Theo dõi, backup/restore, cập nhật bảo mật và chi phí nhân sự |

Không có GPU bắt buộc trong demo hiện tại. Cache đã quan sát gần 1 GB, chưa tính Python/torch, PDF và index. Lựa chọn cấu hình máy chủ cần đo cold-start, RAM, độ trễ và số request đồng thời; bản này chưa có số liệu tải để cam kết cấu hình/SLA.

## 2. Công thức token và ngân sách

Gọi P_in/P_out là giá USD cho một triệu token do **gateway đang dùng** báo; H/B/Z là các chi phí tháng tương ứng. Với I/O token tháng:

`C_total = H + B + Z + I/1_000_000 × P_in + O/1_000_000 × P_out`

Nếu có giá cache read/write khác, phải tách usage theo từng nhóm và áp đúng giá. Ledger hiện cộng input/cache usage vào input tổng; không nên gọi kết quả tính một đơn giá là hóa đơn chính xác. Giá Anthropic công khai cũng không mặc nhiên là giá của hhtechapi.net.

Lượt golden 40 câu đã ghi 42 request (40 generate + 2 rewrite), tổng 491,092 input và 8,770 output token do provider trả. Không gồm các request judge dùng để đánh giá chất lượng. Đây là số đo của một bộ câu hỏi, không phải token cố định cho mọi câu.

Minh họa ngoại suy giữ nguyên đặc điểm bộ đó:

| Số câu/tháng | Input ước lượng | Output ước lượng | Chi phí LLM theo đơn giá triệu token |
|---|---:|---:|---|
| 1,000 | 12.2773 triệu | 0.21925 triệu | 12.2773 × P_in + 0.21925 × P_out |
| 3,000 | 36.8319 triệu | 0.65775 triệu | 36.8319 × P_in + 0.65775 × P_out |
| 10,000 | 122.773 triệu | 2.1925 triệu | 122.773 × P_in + 2.1925 × P_out |

History, chiều dài chunk, model, tỷ lệ rewrite và chính sách provider có thể thay đổi các số này đáng kể. Index dùng model local nên không dùng token Claude; đánh giá golden/judge là chi phí kiểm thử riêng.

## 3. Kiểm soát đã có và cần bổ sung

Đã có quota 30 câu/ngày/người trên mọi lớp, rate limit, max output token, ledger call/stage/usage, trạng thái unknown khi không xác định usage, dedup và outbox tránh nhân bản nghiệp vụ.

Trước public deployment cần: ngân sách cứng theo ngày/tháng và cảnh báo, giới hạn concurrency/timeout tổng, đối soát invoice và giá cache, circuit breaker khi provider lỗi, bảo vệ endpoints giả lập/setup, secret manager, monitoring và backup/restore có diễn tập. Quota 30 câu không phải trần chi phí tiền tệ. Không mở public bằng cách chỉ bind 0.0.0.0; Settings hiện có giới hạn môi trường local và callback localhost.

## 4. Điều kiện Zalo thật

Cần chọn đúng sản phẩm chính thức: OA một-một hay nhóm chat GMF theo quyền ứng dụng được cấp. Không giả định nhóm Zalo cá nhân bất kỳ có cùng API/quyền với Mock Zalo.

Các bước:

1. Có OA/ứng dụng đúng yêu cầu, quản trị viên chịu trách nhiệm và quyền API được duyệt cho use case; kiểm tra hạn mức/gói dịch vụ hiện hành.
2. Cấp quyền liên kết OA–ứng dụng, quản lý access/refresh token, quy trình xoay vòng và thu hồi.
3. Có URL webhook HTTPS public, TLS hợp lệ, kiểm tra chữ ký Zalo theo đúng tài liệu của loại sự kiện. HMAC mock hiện tại không được dùng như chữ ký Zalo.
4. Viết adapter chuyển payload Zalo (sender, recipient/group, msg_id, event_name, timestamp) sang normalized event; dùng msg_id/dedup key ổn định.
5. Ánh xạ ID người dùng/nhóm thật vào lớp và enrollment do admin xác thực; lời tự xưng admin trong chat không cấp quyền.
6. Viết outbound adapter gọi endpoint Zalo chính thức, kiểm tra giới hạn tin nhắn/quyền gửi, retry/backoff/idempotency và xử lý token hết hạn.
7. Kiểm thử sandbox/nhóm được cấp quyền, callback loop chống tin bot, revoke membership, timeout, thay đổi active version và giảng viên phản hồi.
8. Hoàn thiện bảo mật, logging/redaction, chính sách dữ liệu cá nhân và nghiệm thu prompt injection trước khi phục vụ học viên thật.

Backend nghiệp vụ có thể tái sử dụng; phần mock webhook, chữ ký, định danh, outbound callback và local URL phải được thay/điều chỉnh. Repository hiện chưa cài adapter Zalo thật.

## 5. Tài liệu chính thức đã đối chiếu

- [Zalo Developers — danh mục OA, webhook, nhóm chat GMF](https://developers.zalo.me/docs).
- [Zalo OA — khởi tạo ứng dụng và cấp quyền](https://oa.zalo.me/home/documents/guides/Khoi-tao-ung-dung-va-cap-quyen_117071366476220195).
- [Zalo Developers — sự kiện người dùng gửi tin nhắn](https://stc-developers.zdn.vn/docs/v2/official-account/webhook/tin-nhan/su-kien-nguoi-dung-gui-tin-nhan).

Tài liệu Zalo có thể thay đổi. Đối chiếu lại quyền, chữ ký, hạn mức và biểu phí trên cổng chính thức tại thời điểm tích hợp; không dùng giả định chi phí trong demo để cam kết vận hành.
