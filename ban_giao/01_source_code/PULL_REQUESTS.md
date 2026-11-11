# Kế hoạch 20 Pull Request

20 PR draft nối tiếp; mỗi PR chỉ chứa nhóm thay đổi của nó so với nhánh trước. Nhánh main khởi tạo bằng .gitignore; app đầy đủ có trên nhánh PR 20 cho tới khi merge hết chuỗi. Chưa tự merge thay người review.

| PR | Nội dung | Nhánh | Số file |
|---|---|---|---:|
| 01 | Cấu hình dự án và bộ khung Python | `delivery/01-project-foundation` | 43 |
| 02 | Schema SQLite và migrations | `delivery/02-database-schema` | 13 |
| 03 | Đăng nhập và bảo vệ thông tin | `delivery/03-authentication` | 7 |
| 04 | Tài khoản, lớp và metadata học viên | `delivery/04-accounts-classes` | 5 |
| 05 | Quản lý tài liệu và phiên bản | `delivery/05-document-management` | 4 |
| 06 | Webhook và xác thực kênh giả lập | `delivery/06-webhook-security` | 5 |
| 07 | Xử lý sự kiện, quota và shared memory | `delivery/07-event-memory-quota` | 3 |
| 08 | Handoff, ticket, FAQ và outbox | `delivery/08-tickets-outbound` | 4 |
| 09 | Worker bền vững và retry | `delivery/09-durable-worker` | 1 |
| 10 | Parsing, chunking và model local | `delivery/10-parsing-local-models` | 2 |
| 11 | Retrieval và Claude trả lời có căn cứ | `delivery/11-rag-grounded-answer` | 5 |
| 12 | Query rewriting và tiến trình xử lý | `delivery/12-rewrite-progress` | 5 |
| 13 | Giao diện portal theo vai trò | `delivery/13-portal-frontend` | 3 |
| 14 | Giả lập Zalo và lắp ghép API | `delivery/14-simulator-api-assembly` | 7 |
| 15 | Lệnh khởi động và ví dụ webhook | `delivery/15-demo-launchers` | 8 |
| 16 | Học liệu và công cụ dựng demo | `delivery/16-sample-materials` | 19 |
| 17 | Kiểm thử Backend và luồng nghiệp vụ | `delivery/17-backend-integration-tests` | 10 |
| 18 | Kiểm thử parser và RAG | `delivery/18-rag-regression-tests` | 4 |
| 19 | Golden evaluation và metric | `delivery/19-golden-evaluation` | 10 |
| 20 | Hoàn thiện bộ bàn giao và hướng dẫn | `delivery/20-handover-documentation` | 51 |

Mô tả cụ thể ở `pr_descriptions/`; manifest cho công cụ là `pull_requests.json`. Review/merge theo thứ tự. Sau khi merge PR trước vào main, retarget PR kế tiếp sang main; dùng merge commit để giữ quan hệ cha–con. Trạng thái tạo PR thật phải đối chiếu GitHub, không suy ra từ việc có manifest local.
