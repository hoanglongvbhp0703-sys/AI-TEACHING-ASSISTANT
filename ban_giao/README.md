# Bộ bàn giao — GOS AI Teaching Assistant

**GitHub:** https://github.com/hoanglongvbhp0703-sys/AI-TEACHING-ASSISTANT

Bản local hiện hành dùng Zalo Bot thật, RAG theo lớp và portal admin/giảng viên. Những thay đổi local chưa tự được push lên repository.

| Nội dung | Tài liệu |
|---|---|
| Source và cấu hình | [README nguồn](01_source_code/README.md), [cấu hình mẫu](../.env.example) |
| Kiến trúc và quyền lớp | [Kiến trúc](02_kien_truc/KIEN_TRUC.md), [Mermaid](02_kien_truc/architecture.mmd) |
| Demo và dữ liệu | [Kịch bản](03_demo/README.md), tài liệu mẫu và golden dataset trong `03_demo/` |
| Cài đặt, vận hành | [Hướng dẫn](04_huong_dan/CAI_DAT_VA_VAN_HANH.md), [khôi phục](04_huong_dan/KHOI_PHUC_DU_LIEU_DEMO.md) |
| Video | `05_video/202611122100.mp4`, bản ghi lịch sử trước cập nhật code hiện hành |
| Kiểm thử | [Báo cáo](06_kiem_thu/BAO_CAO_KIEM_THU.md), kết quả tự động trong cùng thư mục |
| Điều kiện vận hành | [Vận hành và Zalo](07_van_hanh/CHI_PHI_VA_ZALO.md) |

Chạy `python scripts/run_rag.py`; portal ở http://127.0.0.1:8002/portal. Một backend phục vụ portal, RAG và polling Bot. Cấu hình Claude API key và ZALO_BOT_TOKEN riêng trong `.env`. Mỗi chat/nhóm được admin gắn lớp một lần; không cần tạo học viên.

Dữ liệu riêng, `.env`, model cache và logs không nằm trong Git. Gói dữ liệu riêng được gửi ngoài GitHub. Golden metrics là kết quả lịch sử, không phải bằng chứng rằng mọi câu trả lời hiện tại đều đúng.
