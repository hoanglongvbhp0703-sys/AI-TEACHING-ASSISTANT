# Upload, tiến trình index/RAG và log vận hành

Cập nhật 11/11/2026. Không đổi schema database; dùng stage/counters có sẵn của ingestion_jobs và audit call trong rag_run_attempts.

## Sự cố unit1.pdf đã xử lý

File `unit1.pdf` (1.637.505 byte), tài liệu “Xd chương trình dịch bài 1”, đã được lưu nhưng job index đầu tiên thất bại với `embedding_unconfigured`, tài liệu còn draft và chưa có active_version_id.

Kiểm tra runtime thấy hai backend dùng chung SQLite:

- Cổng 8000: backend cũ, health báo schema v1, RAG unconfigured, background_jobs=true.
- Cổng 8002: bộ RAG đang dùng, health báo schema v3, RAG ready.

Worker cũ lấy job của backend mới rồi gọi UnconfiguredRAG.index. Đã dừng riêng backend cũ PID 20246, giữ hệ thống 8002/giả lập 9000. Retry source đã lưu, không upload lại, không đổi document_id/version: job mới succeeded, version active, 25 chunks và 25 points.

Kiểm chứng lưu trong `data/exports/upload-recovery-report.json`. Lỗi cũ có trong ingestion_jobs; log console cũ chưa được ghi file nên không tuyên bố có thể khôi phục đầy đủ terminal trước đó.

## Chống hai worker lấy chung database

- Worker có RAG jobs bật nhưng backend chưa ready không lấy job index/event/outbox.
- Khi start worker, lấy exclusive file lock cạnh SQLite (`gos.worker.lock`). Backend khác dùng cùng database sẽ báo lỗi khởi động rõ ràng thay vì chạy thêm worker.
- Lock tự được giải phóng khi process kết thúc; không xóa lockfile thủ công trong lúc server còn chạy. Đây là chốt local một process, không phải distributed job scheduler.

## Tiến trình tải tài liệu

Frontend dùng XMLHttpRequest upload progress, hiển thị phần trăm byte thực tế đã truyền. Upload 100% chỉ có nghĩa request body đã truyền xong; Backend vẫn cần kiểm tra định dạng và lưu nguồn.

Sau HTTP 202, frontend poll GET `/api/v1/ingestion-jobs/{id}` mỗi giây để hiển thị:

1. Đọc nội dung file.
2. Tách đoạn theo cấu trúc và tokenizer.
3. Embedding theo batch 16: số chunk đã xử lý / tổng chunk.
4. Upsert Qdrant theo batch 64: số point đã lưu / tổng point.
5. Verify số lượng/metadata/query mẫu.
6. Activate trong transaction, sau đó mới hiển thị 100% sẵn sàng.

Phần trăm index được tính theo trọng số công đoạn và counters thực, **không phải ước lượng thời gian còn lại**. Không có timer tự tăng phần trăm. Khi lỗi giữ mức dừng và hiển thị error_code; queued bắt đầu 0%, succeeded là 100%.

Panel vẫn tồn tại khi đóng modal/chuyển màn hình. SessionStorage chỉ giữ job_id để tiếp tục theo dõi sau reload, Backend vẫn kiểm tra quyền tài liệu. Logout hủy monitor và xóa job theo dõi. Chi tiết tài liệu có Xem tiến trình và Thử index lại; retry dùng source đã lưu, không tạo version mới.

PDF quá lớn/sai định dạng hoặc mất kết nối hiển thị lỗi ngay, kèm request_id nếu Backend đã nhận request. `/health` trả max_upload_bytes để kiểm tra giới hạn phía UI. PDF scan không có text vẫn cần OCR; không tự coi ảnh là văn bản đã index.

## Tiến trình RAG

GET `/api/v1/events/{event_key}` bổ sung progress, vẫn kiểm tra user/lớp hiện hành. Tiến trình được suy ra từ event, rag_run_attempts và outbox:

| Bước | Phần trăm theo công đoạn |
|---|---:|
| Chờ xử lý | 0 |
| Chuẩn bị quyền/memory | 10 |
| Query embedding | 25 |
| Retrieval có filter | 40 |
| Rerank Top 5 | 55 |
| Evidence gate | 65 |
| Model sinh câu trả lời | 75 |
| Xác minh citation | 90 |
| Gửi callback | 95 |
| Đã nhận/gửi phản hồi | 100 |

Những bước nhanh có thể không hiện đủ từng bước giữa hai lần polling. 100% nghĩa vòng xử lý/phản hồi hoàn tất; handoff hoặc phản hồi lỗi kỹ thuật không đồng nghĩa AI đã trả lời thành công.

Giả lập proxy trạng thái bằng adapter token ở server, trả progress chỉ trong lịch sử đúng group. Không đưa token xuống frontend. Callback thành công cập nhật 100%; đổi nhóm vẫn xóa view và bỏ response cũ về chậm.

## Log ghi ở đâu

- `data/logs/backend.log`: upload được lưu, stage/counters index, lỗi index, provider stage/call ID, request bị từ chối và request_id, trạng thái callback.
- `data/logs/simulator.log`: kết quả gửi webhook và nhận callback.
- QA hoặc cấu hình SQLite ở thư mục khác: log nằm trong `logs/` cạnh file database đó; run_rag truyền cấu hình đường dẫn cho process giả lập.
- Mỗi file tối đa 5 MB, giữ thêm 3 bản xoay vòng. Log nằm trong data/ đã được Git ignore.

Không ghi request body, mật khẩu, header API key hoặc raw exception payload. Formatter che các secret đã cấu hình; log lỗi dùng mã ổn định, loại exception và ID thay vì nội dung file/câu hỏi. Log không thay thế các hàng job/audit bền vững trong SQLite.

Xem log sau khi khởi động lại server để nạp code mới:

```sh
.venv/bin/python scripts/run_rag.py
```

Terminal khác:

```sh
tail -f data/logs/backend.log data/logs/simulator.log
```

## Kiểm tra

96 kiểm thử tự động và 18 kiểm tra DDL. Chromium QA trên database/Qdrant cô lập với model double có độ trễ, không dùng API key Claude: PDF sai định dạng hiện error_code/request_id; PDF hợp lệ có tiến trình truyền file và index/counters; lỗi index hiện rõ và retry source thành công; RAG hiển thị generate rồi nhận callback; log không chứa mật khẩu hoặc nội dung file lỗi.

Kết quả: `data/exports/upload-rag-progress-browser-check.json`; ảnh `upload-index-progress-qa.png` và `rag-progress-qa.png`. Bản unit1.pdf thật được worker BKAI của hệ thống hiện tại index thành công; việc thử giao diện với double chỉ kiểm tra cơ chế tiến trình, không phải đánh giá lại chất lượng RAG.
