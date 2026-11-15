# Mô hình v5: chỉ tài khoản nhân sự, chat được phân quyền theo lớp

## Cách dùng

1. Chạy backend như cũ: `.venv/bin/python scripts/run_rag.py`.
2. Người dùng nhắn riêng bot hoặc tag/reply bot trong nhóm Zalo.
3. Admin mở Portal → **Kết nối Zalo** → **Gắn lớp**, chọn Machine Learning hoặc Google Sheets.
4. Gửi câu hỏi mới. Tất cả người gửi trong cuộc chat đã gắn lớp được sử dụng bot.

Không đăng ký học viên, không chọn STT, không gắn người gửi vào tài khoản và không cần
gắn lại khi người khác hỏi trong cùng nhóm. Nhóm mới chưa có liên kết lớp vẫn bị từ chối.
Backend không suy đoán lớp từ nội dung câu hỏi. Mỗi chat chỉ gắn một lớp; nếu chọn nhầm
và muốn đổi sang lớp khác, API hiện báo conflict để không trộn lịch sử của hai lớp.

## Quyền và dữ liệu

- Tài khoản đăng nhập: admin và giảng viên. Tài khoản `service` chỉ dành cho tích hợp nội bộ.
- Schema v5 bỏ vai trò student, bảng enrollments, hồ sơ/credential/session/identity học viên.
- Lịch sử câu hỏi, RAG, ticket và tài liệu được giữ lại. FK từ lịch sử tới học viên cũ
  được đưa về NULL; ticket dùng requester_user_id nullable, không còn student_id bắt buộc.
- Quyền bot: group_bindings liên kết `(platform, external_group_id)` với class_id.
  Lớp và liên kết phải active, bot của lớp phải bật. Kiểm tra lại lúc nhận, xử lý và gửi.
- Retrieval vẫn giới hạn theo scope tài liệu và active version của lớp. Không có quyền
  đọc lớp khác dù người dùng yêu cầu trong prompt.
- Memory vẫn dùng lớp + group binding, tối đa 5 cặp/30 phút; hai nhóm cùng lớp không
  chia sẻ memory. Người trong cùng nhóm dùng shared memory.
- Quota/rate limit vẫn theo người gửi, dùng hash của platform + raw sender ID; không
  tạo user hoặc enrollment tự động. Mức hiện tại 30 câu/ngày, rate limit theo cấu hình.
- Các sự kiện cũ không tự được chạy lại sau khi cấp quyền. Gửi tin mới để thử.
- Ticket tự động từ RAG/handoff và trả lời giảng viên hoạt động theo cuộc chat, không
  cần học viên tồn tại. Sender ID vẫn ở event để truy vết, không phải tài khoản đăng nhập.

## API và giao diện

- `POST /api/v1/integrations/zalo-bot/bindings` chỉ nhận `{class_id, chat_id}`.
- Inbox hiển thị cuộc chat/người gửi, lớp và kết quả; nút **Gắn lớp**.
- Bỏ API members, roster, student quota và portal support-requests dành cho học viên.
- Bỏ đăng nhập, tạo tài khoản và các màn hình học viên. Giữ tài khoản nhân sự, phân công
  giảng viên, tài liệu, ticket/FAQ, báo cáo.
  `/hoi`; Zalo Bot nhắn riêng trực tiếp hoặc tag/reply trong nhóm.

## Chuyển đổi và khôi phục

Trước nâng cấp phải dừng backend cũ. Migration giữ khóa worker, tạo bản sao SQLite
`data/gos.pre-v5.db` (chứa dữ liệu cũ, không đưa Git), dựng DB v5 và kiểm tra foreign keys
trước khi thay DB nguồn. Nếu dựng schema/copy dữ liệu thất bại, DB gốc chưa bị thay.
Quota được quy đổi từ reservation lịch sử sang sender key để giữ lượt đã dùng.

Muốn khôi phục phải dừng toàn bộ backend, dùng lại code v4 cùng bản DB pre-v5; không
đưa DB v5 chạy với code v4. Qdrant và file học liệu không bị thay bởi migration này.
ZIP bàn giao cũ chưa được đóng lại theo v5. Tài liệu trước v5 chỉ mang tính lịch sử.

Kiểm thử gồm migration có lịch sử học viên/ticket/quota, nhiều người mới cùng nhóm,
nhóm chưa gắn lớp, bot bị tắt, phân quyền giảng viên, cô lập memory, quota đồng thời,
citation/active version, outbox, handoff và đăng nhập nhân sự.
