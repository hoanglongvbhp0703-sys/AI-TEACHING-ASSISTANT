# 06 — Ma trận nghiệm thu và trạng thái kiểm chứng

Script `python3 scripts/validate_schema.py` kiểm tra **bản thiết kế DDL**, không có FastAPI/RAG đang chạy. Các ca BE/AG/FE dưới đây là kế hoạch cần thực thi sau khi triển khai; không đánh dấu pass dựa trên việc đọc tài liệu.

| Nhóm | Ca gốc | Invariant/đầu ra cần kiểm chứng | Nơi triển khai test |
|---|---|---|---|
| Kích hoạt | BE-T01/02, FE-T01/02, AG-17 | Tin thường/`/hoiabc` không RAG/quota/memory; `/hoi` rỗng có hướng dẫn | unit command + API |
| Dedup | BE-T03/04/17, FE-T06 | Hai delivery đồng thời cùng ID chỉ một tác động; text giống nhưng ID khác vẫn 2 câu | SQLite/API concurrency |
| Quota | BE-T05/06/18, FE-T13 | 30 tổng mọi lớp; câu 31 bị chặn; retry/hoàn đúng một lần | quota transaction + clock |
| Quyền | BE-T07/08, AG-T04, FE-T04/13 | Class giả không cấp quyền, bot OFF, teacher ngoài lớp bị chặn | API + retrieval filter |
| Memory | BE-T09/10, AG-T10/11/12, FE-T03/07 | Hai student cùng nhóm chia sẻ; nhóm khác tách; TTL và 5 cặp hoàn chỉnh | memory service + fake clock |
| Parser | AG-T01/02/03 | PDF page; DOCX heading/bảng; XLSX/FAQ giữ cặp, không bịa page | parser fixtures |
| RAG | AG-T05/06, BE-T13, FE-T05 | Đủ căn cứ mới answered; thiếu/học phí thành ticket | golden set + thủ công |
| FAQ nhiều lớp | AUTO-06, AG-09 | COMMON chung, GS-CLASS/AUTO-CLASS không lẫn dù cùng file | Qdrant payload/filter test |
| Version | BE-T11/12, AG-T07/08/13, FE-T08/09/10/11 | V2 fail giữ V1; cùng hash unchanged; V2 active chỉ V2 được retrieve | integration DB/Qdrant/file |
| Revoke race | AG-T14, FE-T12 | Revoke lúc generate/outbox pending không phát citation cũ | kiểm soát barrier giữa stages |
| Ticket/FAQ | BE-T14 | Assign/answer/close đúng quyền; approve mới ingestion; failed FAQ chưa active | API + outbox |
| Bảo mật | BE-T15, AG-T09 | Prompt injection blocked; không secret trong prompt/DB/logs | redaction + model stub + review |
| Persistence | BE-T16, AG-05 | Restart giữ DB/index/files; reclaim job lease; không mất 202 accepted | kill/restart integration |
| Chi phí | BE-22, AG-16/19 | Mọi call/retry có usage/cost hoặc unknown; report không nhân bản theo citations | report fixtures |
| UI | FE-T07…12, FE-01…14 | Một trang hai tab, select đúng document, polling terminal, auth Backend | browser/manual |

## Những ca bổ sung từ bản thiết kế

1. FK active_version của document A không được trỏ version document B.
2. Point có scope chưa nằm trong document_access phải bị từ chối; parser chưa gán section scope phải fail.
3. Hai request quota ở count=29 chỉ một request được nhận; counter = reservation reserved+charged.
4. Retry sau 00:00 Việt Nam vẫn tham chiếu quota ngày cũ; request mới dùng ngày mới.
5. Revoke ACL/citation source phải loại memory turn chứa câu trả lời cũ khỏi prompt.
6. Provider call timeout không biết usage phải hiện unknown, không ghi cost=0 để giả rẻ.
7. Hai teacher answer đồng thời chỉ một reply chính thức/outbound, người còn lại nhận 409 hoặc kết quả cũ.
8. Lease hết hạn runner cũ hoàn thành muộn không được ghi ticket/outbound hoặc activate version.
9. Hash file giống nhưng scope mapping khác không bị trả unchanged.
10. Ingestion đang chạy mà document bị revoke không được activate lại khi job hoàn tất.

## Báo cáo sau triển khai

Ghi test ID, dataset/version/model/config, thời điểm chạy, kết quả thực tế, bằng chứng, latency/token/cost, lỗi và giới hạn. Tách kết quả **schema validation** khỏi **API integration**, **retrieval benchmark**, **grounding review** và **UI demo**. SRS AG-T05 cần câu so sánh RAG/Fine-tuning đủ bằng chứng; nếu học liệu thực tế không chứa cả hai vế thì kết quả đúng là handoff, không sửa kỳ vọng thành trả lời không có nguồn.

Các tệp `.gitkeep` trong tests chỉ giữ cấu trúc; không đại diện các ca trên đã được viết hoặc thực thi.
