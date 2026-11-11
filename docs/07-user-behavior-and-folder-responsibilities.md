# Báo cáo hành vi người dùng và nhiệm vụ từng folder

Hiện đã có **schema 28 bảng và khung thư mục**, kèm 18 kiểm tra schema đạt. Backend và giao diện chưa được triển khai. Dưới đây là hành vi hệ thống dự kiến khi viết code theo thiết kế này.

**1. Từng loại người dùng sẽ làm gì?**

Hệ thống có ba vai trò con người và một vai trò kỹ thuật:

| Vai trò | Phạm vi hoạt động |
|---|---|
| **Học viên — Student** | Hỏi bot trong nhóm lớp mình tham gia, nhận câu trả lời hoặc thông báo chuyển giảng viên |
| **Giảng viên — Teacher** | Quản lý tài liệu và xử lý yêu cầu hỗ trợ của những lớp được phân công |
| **Quản trị viên — Admin** | Quản lý khóa học, lớp, thành viên, giảng viên, bot và quyền truy cập |
| **Tài khoản dịch vụ — Service** | Tiếp nhận sự kiện qua adapter đã xác thực; chạy các tác vụ hệ thống trong phạm vi được cấp |

**Hành vi của học viên**

| Hành động | Hệ thống xử lý | Dữ liệu liên quan |
|---|---|---|
| Gửi tin nhắn thông thường | Hiển thị trong mô phỏng; không gọi AI, không tính quota, không đưa vào memory | Không cần lưu nội dung vào database |
| Gửi `/hoi` nhưng thiếu câu hỏi | Trả hướng dẫn nhập đúng cú pháp; không tính lượt | `webhook_events`, `outbound_messages` nếu ghi nhận sự kiện |
| Gửi `/hoi <câu hỏi>` | Xác minh nhóm, danh tính, thành viên lớp và trạng thái bot | `group_bindings`, `external_identities`, `enrollments`, `classes` |
| Câu hỏi được tiếp nhận | Giữ một lượt quota, xác định phiên hội thoại và truy xuất đúng học liệu | `daily_usage`, `quota_reservations`, `conversation_sessions`, `messages` |
| Có đủ bằng chứng | Nhận câu trả lời tiếng Việt kèm tài liệu và mục/trang nguồn | `rag_runs`, `rag_citations`, `outbound_messages` |
| Không đủ bằng chứng | Nhận thông báo đã chuyển giảng viên cùng mã ticket | `support_tickets`, `outbound_messages` |
| Hỏi tiếp trong cùng nhóm | Bot dùng tối đa 5 lượt hỏi–đáp gần nhất; các học viên cùng nhóm dùng chung ngữ cảnh | `conversation_sessions`, `messages` |
| Không có câu hỏi mới quá 30 phút | Câu hỏi tiếp theo bắt đầu phiên ngữ cảnh mới | `conversation_sessions` |
| Đã dùng đủ 30 câu/ngày | Câu tiếp theo bị từ chối; quota tính tổng trên tất cả lớp của học viên | `daily_usage` |
| Webhook gửi lại cùng event | Hệ thống trả kết quả nhận diện trùng; không tính thêm lượt hoặc tạo thêm phản hồi | `webhook_events` |
| Yêu cầu tiết lộ API key hoặc vượt quyền | Nhận phản hồi từ chối an toàn; ghi nhận sự kiện bảo mật | `security_events` |

Học viên chỉ nhận kiến thức thuộc lớp mình và nguồn chung đã được cấp quyền. Học viên không được upload học liệu chính thức, duyệt FAQ hoặc tự chọn phạm vi truy xuất.

**Hành vi của giảng viên**

| Hành động | Hệ thống xử lý | Dữ liệu liên quan |
|---|---|---|
| Tìm tài liệu theo tên/chủ đề | Trả danh sách tài liệu giảng viên có quyền quản lý | `documents`, `document_access`, `teacher_assignments` |
| Thêm tài liệu | Lưu file, tạo tài liệu/version và job ingestion | `documents`, `document_versions`, `ingestion_jobs` |
| Chọn phạm vi tài liệu | Kiểm tra quyền đối với lớp hoặc khóa học bị ảnh hưởng | `access_scopes`, `document_access` |
| Thay tài liệu bằng file mới | Tạo version mới; bản cũ tiếp tục hoạt động trong lúc index | `document_versions`, `ingestion_jobs` |
| Upload thành công và index hoàn tất | Chuyển active pointer sang version mới; lên lịch dọn vector cũ | `documents`, `document_versions`, `cleanup_jobs` |
| Index version mới thất bại | Thấy trạng thái lỗi; bản cũ vẫn được sử dụng | `ingestion_jobs`, `document_versions` |
| Upload lại file không đổi | Nhận kết quả `unchanged`, nếu metadata và phạm vi cũng không đổi | `document_versions` |
| Xóa/thu hồi tài liệu | Ngừng cho bot sử dụng ngay; việc dọn vector thực hiện sau | `documents`, `cleanup_jobs`, `audit_logs` |
| Nhận và phân công ticket | Xem câu hỏi, lý do chuyển hỗ trợ và người phụ trách | `support_tickets` |
| Trả lời ticket | Lưu câu trả lời và phát phản hồi về đúng nhóm | `ticket_replies`, `outbound_messages` |
| Đóng ticket | Hoàn tất yêu cầu sau khi đã trả lời | `support_tickets` |
| Đưa câu trả lời vào FAQ | Tạo bản nháp, duyệt rồi đưa qua ingestion | `faq_entries`, các bảng tài liệu và job |

**Trả lời ticket chưa tự động trở thành kiến thức của bot.** Giảng viên phải duyệt FAQ; nguồn đó chỉ được truy xuất sau khi index và kích hoạt thành công.

Theo SRS, giao diện MVP chỉ có tab quản lý tài liệu. Ticket, FAQ và báo cáo được thao tác qua API/Swagger hoặc script demo.

**Hành vi của quản trị viên**

| Hành động | Dữ liệu thay đổi |
|---|---|
| Tạo khóa học và lớp | `courses`, `classes` |
| Thêm người dùng, đặt vai trò và trạng thái | `users` |
| Gắn danh tính người gửi bên ngoài với user nội bộ | `external_identities` |
| Thêm hoặc ngừng quyền tham gia lớp của học viên | `enrollments` |
| Phân công giảng viên | `teacher_assignments` |
| Gắn nhóm chat với lớp | `group_bindings` |
| Bật/tắt bot theo lớp | `classes.bot_enabled` |
| Quản lý học liệu chung nhiều lớp | `document_access` và các bảng tài liệu |
| Xem số câu hỏi, ticket, lỗi, token và chi phí | Tổng hợp từ các bảng event, RAG, ticket và provider call |
| Kiểm tra thay đổi và sự kiện bảo mật | `audit_logs`, `security_events` |

MVP dùng dữ liệu seed và token cấu hình cho demo; chưa thiết kế màn hình đăng ký, quên mật khẩu hoặc quản trị tài khoản hoàn chỉnh.

**Hành vi của tài khoản dịch vụ và tác vụ nền**

Adapter tiếp nhận sự kiện sau khi xác thực nguồn gửi. Các runner nội bộ tiếp tục xử lý event, index tài liệu, gửi phản hồi mock và dọn vector. Khi ứng dụng khởi động lại, runner quét các công việc chưa hoàn tất để phục hồi; retry vẫn giữ nguyên định danh nghiệp vụ để tránh tạo tác động trùng.

Luồng tổng thể là:

```text
Học viên gửi /hoi
    → xác thực người và lớp
    → kiểm tra quota
    → lấy ngữ cảnh đúng nhóm
    → tìm học liệu đang active
    → tạo và kiểm tra câu trả lời
    → trả lời có nguồn / chuyển giảng viên / từ chối an toàn
    → lưu kết quả, chi phí và trạng thái
```

**2. Từng folder có nhiệm vụ gì?**

Các folder dưới đây đã được tạo. Phần lớn đang là khung rỗng để triển khai.

| Folder cấp gốc | Nhiệm vụ |
|---|---|
| `app/` | Chứa toàn bộ mã ứng dụng Backend, RAG và giao diện demo |
| `scripts/` | Các lệnh phục vụ khởi tạo, seed, demo, đánh giá và backup; hiện có script kiểm tra schema |
| `tests/` | Kiểm thử ứng dụng sau khi triển khai |
| `docs/` | Tài liệu kiến trúc, database, hợp đồng xử lý và nghiệm thu |
| `examples/` | Ví dụ dữ liệu đầu vào và cấu hình phạm vi, không chứa bí mật |
| `data/` | Dữ liệu phát sinh lúc ứng dụng chạy; được loại khỏi Git |
| `GOS_Academy_Bo_tai_lieu_mau_gui_TTS_AI_Zalo/` | Học liệu và tin nhắn mẫu gốc, được giữ nguyên |

Các PDF yêu cầu hiện vẫn nằm tại thư mục gốc để đối chiếu.

**Bên trong `app/`**

| Folder | Nhiệm vụ và giới hạn trách nhiệm |
|---|---|
| `app/api/` | Lớp tiếp nhận HTTP: xác thực request, validate dữ liệu, gọi service và trả response |
| `app/api/routes/` | Chia endpoint theo nhóm: webhook, mock, tài liệu, lớp, ticket, FAQ, reports và health |
| `app/core/` | Cấu hình môi trường, bảo mật, che dữ liệu nhạy cảm, logging, lỗi chung và đồng hồ hệ thống |
| `app/db/` | Thiết lập kết nối SQLite và cấu hình SQLAlchemy |
| `app/db/models/` | Khai báo ORM tương ứng với 28 bảng |
| `app/db/migrations/` | Quản lý thay đổi cấu trúc database qua từng phiên bản |
| `app/db/migrations/versions/` | Mỗi file là một migration cụ thể, ví dụ tạo schema ban đầu hoặc thêm cột |
| `app/repositories/` | Chứa truy vấn database: tìm, thêm, cập nhật dữ liệu; service quyết định lúc commit |
| `app/schemas/` | Định nghĩa dữ liệu request/response API, tách khỏi ORM models |
| `app/services/` | Chứa quy tắc nghiệp vụ: quyền lớp, quota, memory, tài liệu, ticket, FAQ và outbound |
| `app/integrations/` | Kết nối với thành phần bên ngoài: mock Zalo, Qdrant, filesystem và nhà cung cấp model |
| `app/rag/` | Pipeline ingestion và hỏi đáp: chunking, retrieval, reranking, evidence gate, generation, citation |
| `app/rag/parsers/` | Đọc PDF, DOCX, XLSX và FAQ; giữ cấu trúc bảng, heading, trang/mục |
| `app/rag/prompts/` | Lưu prompt dùng cho sinh câu trả lời và kiểm tra bằng chứng |
| `app/rag/evaluation/` | Đánh giá retrieval, độ đúng nguồn, tỷ lệ handoff, latency và chi phí |
| `app/jobs/` | Chạy công việc đã lưu bền vững: xử lý event, ingestion, cleanup, retry và recovery |
| `app/static/` | HTML/CSS/JS của trang `/demo`, gồm hai tab chat giả lập và tài liệu |

Điểm phân chia quan trọng: **API nhận yêu cầu → service quyết định nghiệp vụ → repository đọc/ghi database**. RAG nhận phạm vi do Backend cấp; không tự mở quyền lớp hoặc tự tạo ticket.

**Bên trong `tests/`**

| Folder | Nhiệm vụ |
|---|---|
| `tests/unit/` | Kiểm tra từng phần nhỏ: nhận diện `/hoi`, tính ngày quota, parser, redaction |
| `tests/integration/` | Kiểm tra các thành phần phối hợp: API–database, database–Qdrant, upload–ingestion |
| `tests/acceptance/` | Kiểm tra toàn luồng theo các ca BE/AG/FE trong SRS |
| `tests/fixtures/` | File mẫu nhỏ, dữ liệu đầu vào và kết quả kỳ vọng dùng cho test |

**Bên trong `docs/`**

| Folder | Nhiệm vụ |
|---|---|
| `docs/architecture/` | Báo cáo đọc dự án, các quyết định thiết kế và cấu trúc folder |
| `docs/database/` | Schema, ERD, từ điển 291 cột và DDL SQLite |
| `docs/contracts/` | Hợp đồng dữ liệu, transaction, trạng thái xử lý và recovery |
| `docs/testing/` | Ma trận nghiệm thu và kết quả kiểm tra thực tế |

**Bên trong `examples/` và `data/`**

| Folder | Nhiệm vụ |
|---|---|
| `examples/events/` | Tin nhắn mẫu đã chuyển về hợp đồng webhook thống nhất |
| `examples/faq/` | Ví dụ mapping từng mục FAQ sang lớp được phép truy xuất |
| `data/qdrant/` | Vector và payload chunk của Qdrant Local |
| `data/uploads/` | File nguồn bất biến, phân theo document/version |
| `data/staging/` | File tạm đang upload hoặc kiểm tra trước khi lưu chính thức |
| `data/exports/` | Báo cáo hoặc dữ liệu xuất phục vụ demo/bàn giao |

Database nghiệp vụ dự kiến nằm tại `data/gos.db`. Hiện chưa tạo database chạy thật trong thư mục này.
