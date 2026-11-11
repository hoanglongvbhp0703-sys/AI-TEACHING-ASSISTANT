# 05 — Hợp đồng dữ liệu và transaction

Các quy tắc transaction dưới đây là **[ĐX thiết kế triển khai]** để thỏa SRS; chưa phải source code service đã có. Tên cột khớp DDL SQLite.

## 1. Mock ingress và adapter fixture

```json
{
  "event_id": "E001",
  "platform": "mock_zalo",
  "group_id": "ZGROUP_GS01",
  "sender_id": "HV_GS_01",
  "sent_at": "2026-11-09T19:30:00+07:00",
  "is_bot_message": false,
  "message": {
    "type": "text",
    "text": "/hoi IMPORTRANGE có đồng bộ ghi chú ô với bình luận không?",
    "reply_to_event_id": null
  }
}
```

Seed đề xuất: course `GS_KPI` → class `GS-KPI-01` → group `ZGROUP_GS01`; course `AI_AUTO` → class `AUTO-N8N-01` → group `ZGROUP_AI01`. Sender IDs giữ như JSON gốc. Tạo 8 student identities/enrollments tương ứng; thêm một student cả hai lớp để thử quota tổng, hai teacher và một admin. Tên/ID user nội bộ do seed quản lý, không cần trùng external_sender_id.

`/webhooks/mock-zalo`: secret header mô phỏng, schema chặt, platform do adapter ràng buộc. `/mock/events`: local-only, chỉ cho chọn nhóm/người seed; gọi cùng event handler. Không cho nhận `allowed_scopes` hoặc xác nhận quyền dựa trên `class_id` client gửi. HTTP 202 chỉ sau khi event đã commit vào DB. Duplicate trả 2xx cùng event_key/status, không enqueue việc mới.

Match command sau trim theo `^/hoi(?:\s+|$)`, case-sensitive theo đề xuất. `/hoiabc`, `Hello /hoi`, tin thường và bot message không vào RAG/quota/memory. `/hoi` rỗng trả validation_notice, không quota. Nếu lưu metadata ignored events, không lưu normal-chat text. Nếu loại sớm trước DB thì report không tuyên bố đã đếm mọi tin nhận.

## 2. RAG trusted input/output

Backend tạo request chứa request_id, event_key, class_id, group_id, question đã xử lý dữ liệu nhạy cảm, allowed_scope_ids, active_document_version_ids, memory 5 lượt tối đa. Mỗi turn memory có event_key, question, answer; khi chuyển thành prompt mới flatten thành cặp user/assistant. Group_id trong contract SRS là external group; nội bộ luôn giữ thêm group_binding_id đã resolve.

Output duy nhất một trong: `answered`, `insufficient_evidence`, `blocked`, `error`. Citation chứa document_id, document_version_id, chunk_id, point_id nội bộ, title, page hoặc section_path, evidence_excerpt. `answered` bắt buộc evidence.sufficient=true và ít nhất một citation hợp lệ; insufficient không mở rộng kiến thức từ Internet. Usage của provider được ghi từng call; latency logical run không bằng tổng latency từng stage khi có overlap.

## 3. Atomic event + quota

### A. Đăng ký và tiếp nhận

1. Xác thực adapter, validate DTO/body size, loại bot/tin không kích hoạt. Redact trước persistence/logs/prompt; không chỉ dựa vào model để che secrets.
2. `BEGIN IMMEDIATE`; INSERT event với UNIQUE(platform,external_event_id). Nếu xung đột, đọc event cũ và kết thúc; nếu payload hash khác, ghi security event rồi vẫn không xử lý lần hai.
3. Resolve group/identity từ DB và kiểm tra user active, student, membership active, class active, bot enabled. Nếu policy từ chối, event rejected + outcome, có thể tạo policy_notice nếu nhóm resolve được; không quota.
4. Kiểm tra throttle 5 câu/phút cấu hình được theo server accepted_at trên mọi lớp của user. Quota ngày và throttle là hai chính sách khác nhau.
5. Upsert daily_usage(user_id,local_date) count=0. Chỉ tăng khi `accepted_count < 30`, INSERT reservation reserved PK event_key, đặt event.accepted_at/status queued. Nếu không tăng được, event rejected/quota_exceeded, commit policy_notice, không RAG.
6. Commit. Chỉ sau commit mới ACK 202. Không chờ model trong write transaction.

Các bước 2–5 nằm cùng write transaction ngắn. Chính sách denied/ignored trả 2xx ở webhook kèm outcome, tránh adapter retry vô nghĩa; API quản trị/quota trực tiếp có thể dùng HTTP 429 theo SRS. DB bận hết timeout và chưa commit: trả retriable error, không khẳng định accepted.

### B. Claim và xử lý

1. Runner claim queued/due hoặc processing lease hết hạn; conditional UPDATE status/lease_token/lease_expires_at/attempts trong transaction. Một `lease_token` mới cho mỗi lần claim là fencing token.
2. Kiểm tra lại enrollment/bot/class; nếu quyền đã mất trước RAG thì reject + release quota. Mọi completion UPDATE phải khớp lease_token hiện hành.
3. Trong transaction khác: tạo/lấy session theo server time và `/hoi` tiếp nhận, ghi question idempotent; tạo logical rag_runs nếu chưa có; đổi reservation reserved → charged ngay trước bắt đầu pipeline RAG. Snapshot scope/version chỉ sau auth check.
4. Gọi RAG ngoài DB transaction; ghi provider call bắt đầu/kết thúc. Không retry provider vô hạn. Timeout cho một attempt phải ngắn hơn lease hoặc phải renew lease khi đang chạy; giá trị cụ thể chốt sau đo model. Stale runner không được ghi kết quả/đổi quota/outbound; provider có thể vẫn bill call trước đó, nên không xóa call log.
5. Khi kết quả về, transaction ngắn: kiểm tra lease, quyền và version/citation hiện hành; ghi result, citations, assistant message/ticket, outbox và completed/failed. UNIQUE ticket/run/message_kind ngăn tác động lặp.

### C. Chính sách quota và lỗi

- Insufficient/ticket, answered, blocked sau tiếp nhận, hoặc model lỗi sau lúc pipeline RAG bắt đầu: charged một lượt. Retry cùng event không tính lại.
- Lỗi hạ tầng hoặc thu hồi quyền **trước khi pipeline bắt đầu**: release reservation bằng conditional UPDATE `WHERE status='reserved'`; chỉ khi đổi được một hàng mới giảm daily_usage. Release dùng local_date đã lưu, kể cả qua ngày mới.
- Nếu event thất bại sau khi charge, không tự release rồi chạy lại cùng event miễn phí. User có thể gửi event mới nếu muốn hỏi lại. Đây là cách cụ thể hóa SRS “lỗi trước xử lý không tính/được bù”.
- Counter và ledger có thể lệch nếu ghi SQL ngoài service; có truy vấn reconciliation `accepted_count = COUNT(reservations WHERE status IN ('reserved','charged'))` mỗi user/date. Không sửa counter thủ công để reset quota.

## 4. Session và memory

Trong `BEGIN IMMEDIATE`, lấy session open của class/group. Nếu server_now > expires_at, đổi expired rồi tạo session mới; đúng bằng 30 phút vẫn thuộc session cũ theo điều kiện `>30 phút` của SRS. Update last_hoi_at và expires_at=server_now+30min khi nhận một `/hoi` hợp lệ mới; retry event không gia hạn session lần hai.

Mỗi event giữ một question + một assistant response cuối; lấy tối đa 5 interaction **đã đủ cặp**, committed, memory_eligible và đúng session, theo thời gian rồi đảo về chronological. Loại tương tác chưa xong/blocked/error; response handoff có thể tham gia. Nếu citation của answer cũ nay revoked/superseded hoặc scope không còn hợp lệ, bỏ turn đó khỏi prompt. Memory không được dùng để giữ kiến thức cũ vượt active-version gate. Ticket trả lời muộn không tự mở/gia hạn session đã hết.

## 5. Upload và chuyển phiên bản

1. Auth teacher/admin, kiểm tra tất cả scopes bị ảnh hưởng; kiểm tra extension/MIME/size/content, safe path. Stream vào staging và tính SHA-256; không tin filename làm path.
2. Giảng viên chọn document_id khi cập nhật; không dò tên/nội dung để đoán tài liệu thay thế. Backend tự tăng MAX(version)+1 trong transaction, giữ document_id. Nếu trùng hash active và cấu hình xử lý không đổi: trả `unchanged`. Khi RAG tắt, so với bản lưu mới nhất. Cấu hình thay đổi vẫn tạo version mới. POST /documents/{document_id}/reindex luôn tạo version mới từ file nguồn mới nhất, kể cả hash/config không đổi.
3. Atomic move file vào version directory bằng tên server sinh. Transaction ngắn tạo document draft/version queued/job. Nếu crash trước DB commit, file mồ côi chưa được phép truy xuất; staging/orphan sweeper chỉ dọn sau kiểm tra DB và thời gian an toàn.
4. Runner claim job; parse/chunk theo cấu trúc. Mọi chunk kế thừa toàn bộ scope từ document_access. Không có ACL cấp chương; section_id/section_path chỉ là metadata trích dẫn. Manifest thiếu scope của bất kỳ chunk nào bị từ chối. Lưu manifest, upsert deterministic points. Model/parse errors → job failed + version failed, active cũ giữ nguyên.
5. Verify số logical chunks/points, metadata, model/dimension và retrieval mẫu; đánh ready. Sau đó mở transaction, kiểm tra document chưa revoked, revision/old_active đúng giá trị khi bắt đầu job và job lease vẫn hợp lệ.
6. Trong cùng transaction: đổi old version active → superseded; UPDATE document active_version_id=new, status=active, revision+1; đổi new ready → active, timestamps; job succeeded; INSERT cleanup job old vectors. Thứ tự này thỏa unique active và trigger verified. Commit là thời điểm đổi nguồn hiệu lực.
7. Cleanup vectors với filter **document_id AND document_version_id**; không dọn version đang active. File cleanup mặc định chưa chạy. Mất điện sau Qdrant upsert nhưng trước activate thì job retry cùng point IDs; metadata SQLite vẫn quyết định bản dùng được.

Nếu document bị revoke trong khi indexing, job bị cancelled, new version không được activate; dọn points sau. Nếu CAS revision thất bại, không để job cũ tự activate lại sau một version mới hơn. Không retry bằng cách bỏ kiểm tra revision.

## 6. Revoke và phát câu trả lời

Revoke transaction: status revoked, active_version_id=NULL, revision+1, deleted metadata/audit; version active → revoked; tạo cleanup jobs cho mọi version còn points; cancel ingestion live. Sau commit, retrieval không cấp version đó dù vector chưa xóa.

Trước khi tạo **và trước khi chuyển outbox sang sent**, kiểm tra ACL, class/member và mọi citation.version vẫn active. Với Mock Sender, kiểm tra và ghi sent cùng write transaction để khóa race với revoke/version switch. Nếu stale, không phát câu trả lời cũ; cho pipeline bounded re-retrieval một lần trong cùng event/quota/run với call logs mới; nếu vẫn stale/thiếu, tạo ticket và một bot_result thông báo handoff. Không tạo thêm logical run hoặc thêm lượt quota.

Không thể xóa nội dung người dùng đã đọc trước thời điểm revoke; bảo đảm ở đây là ngăn **phát mới** từ nguồn đã thu hồi. Zalo thật trong tương lai cần mô tả giới hạn giữa thời điểm kiểm tra và network send, cùng idempotency theo khả năng API; DB dedup không tự bảo đảm exactly-once qua mạng.

## 7. Ticket, FAQ và mock outbound

- Insufficient: INSERT ticket UNIQUE event, handoff message + bot_result outbox cùng transaction với run result.
- Assign: teacher thuộc lớp/admin; conditional UPDATE revision/status open/assigned. Không cho gán user chỉ có role teacher nhưng không assignment phù hợp.
- Answer: tạo ticket_reply idempotent; lưu teacher_answer outbox nhưng giữ ticket assigned/open cho tới Mock Sender xác nhận sent. Retry cùng ticket trả reply cũ, không ghi đè nội dung bằng request khác; nội dung khác sau answer trả 409 trong MVP.
- Mock Sender: transaction kiểm tra quyền + insert/show message + status sent + ticket answered/answered_at. `external_message_id` có thể dùng outbound ID; không giả ID Zalo thật.
- Close chỉ khi answered; trạng thái đóng không xóa lịch sử. FAQ draft từ ticket đã answered/closed; approval check phạm vi, tạo snapshot source.json cùng document/access/version/job. Lặp approve trả document/job đã có, không sinh bản trùng.
- Failed ingestion FAQ không hủy câu trả lời giảng viên đã gửi; FAQ approved nhưng chưa usable cho tới active. Revoke FAQ đồng thời revoke document; không chỉ đổi cờ FAQ.

## 8. Recovery khi restart

| Điểm crash | Dữ liệu bền vững | Cách phục hồi |
|---|---|---|
| Sau event/quota commit, trước chạy RAG | queued + reserved | Startup scan/due runner claim; không tăng quota lại |
| Sau RAG bắt đầu, trước completion | processing + charged + run/call started | Lease reclaim; ghi unknown call nếu usage không biết; bounded retry |
| Sau result/ticket/outbox commit | completed/failed + outbox | Chỉ send pending, không chạy RAG lại |
| Sau upsert một phần Qdrant | version indexing, job lease | Upsert cùng point IDs, verify lại |
| Sau chuyển active, trước cleanup | pointer mới, cleanup queued | Chạy cleanup old version; không ảnh hưởng retrieval mới |
| Sau tạo file, trước DB commit | File không có version row | Sweeper kiểm tra orphan; không index tự động |

Mọi runner có max attempts/backoff/next_attempt_at; exhausted chuyển failed và ghi error đã che. Manual retry ingestion dùng lại version/file, tạo job mới khi job cũ terminal; partial unique ngăn hai live jobs/version. BackgroundTasks đơn thuần không phải durable queue. Throttle dùng accepted_at trong SQLite; nhiều process về sau cần cơ chế phù hợp hơn.

## 9. API → dịch vụ → bảng

Prefix `/api/v1`; envelope `{data,error,request_id}`; danh sách có limit/cursor; thời gian ISO UTC. Request thay đổi có auth; query theo lớp phải intersect quyền phía server.

| Endpoint | Service | Dữ liệu chính |
|---|---|---|
| POST /webhooks/mock-zalo, /mock/events | event/access/quota | webhook_events, identity/group, daily_usage/reservations |
| GET /mock/groups/{group_id}/messages | access/outbound | messages/outbound, chỉ nhóm có quyền |
| GET /auth/me, /courses, /classes, /classes/{id}/members | access | users/enrollments/assignments |
| PATCH /classes/{id}/bot | access/admin | classes, audit_logs |
| GET /students/{id}/quota | quota | daily_usage/reservations, local reset_at |
| GET/POST /documents; GET/DELETE /documents/{id} | document/access | document/access/versions/jobs/audit |
| POST /documents/{id}/versions | document | source/version/ingestion |
| GET /ingestion-jobs/{id}; POST /{id}/retry | document/jobs | ingestion_jobs/version |
| GET /tickets, /tickets/{id}; POST /{id}/assign,/answer,/close | ticket | tickets/replies/outbound/audit |
| POST /tickets/{id}/faq-draft; POST /faqs/{id}/approve | faq | faq/document/access/version/job |
| GET /reports/summary?from=&to= | report | events/runs/calls/tickets/jobs |
| GET /health | health | DB connection + Qdrant lifecycle/storage readiness |

POST upload trả 202 + document_id/version_id/job_id, không hiển thị thành công trước activation. GET job có `status` nội bộ và `document_state` cho FE (`queued/indexing/active/failed/revoked`); `unchanged` là kết quả request upload, không là job kéo dài. Dev mock phải tắt khi APP_ENV khác local/development. Không thêm endpoint public để FE gọi RAG với scope tự chọn.


### Cấu hình và reindex MVP

`extraction_config` chỉ nhận `embedding_model`, `parser_revision`, `chunk_size` (64–32768), `chunk_overlap` (0 <= overlap < size, cần khai báo size). Không nhận `section_scopes` hoặc khóa không xác định. Bỏ cấu hình khi cập nhật thì kế thừa cấu hình nguồn; truyền cấu hình thì thay thế toàn bộ. Reindex cần teacher/admin có quyền tất cả scope, không nhận số version thủ công. Reindex bản revoked hoặc khi RAG tắt bị từ chối; job đang chạy thì trả 409. SHA-256 là hash file, không phải định danh model/config. Model yêu cầu được chuyển cho backend index và xác minh bằng metadata manifest trước khi activate. Index test dùng backend giả lập trong test, không triển khai model/vector thật.

MVP cấp quyền toàn tài liệu: nếu cần các lớp xem các chương khác nhau, giảng viên tách thành các tài liệu riêng và cấp quyền riêng trước khi upload. Tài liệu nhiều scope cho phép mọi scope xem toàn bộ tài liệu. Dữ liệu section_scopes lịch sử không còn là chính sách cấp quyền; source/config của version cũ vẫn giữ nguyên để đối chiếu, version mới không kế thừa khóa đó.
