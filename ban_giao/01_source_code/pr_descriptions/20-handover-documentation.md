## Mục đích

README, kiến trúc, Google Docs/ảnh, kết quả kiểm thử, chi phí và kế hoạch 20 PR.

## Phạm vi

- `README.md`
- `app/api/routes/webhooks.py`
- `ban_giao/01_source_code/PUBLICATION_CHECK.json`
- `ban_giao/01_source_code/PULL_REQUESTS.md`
- `ban_giao/01_source_code/README.md`
- `ban_giao/01_source_code/pr_descriptions/01-project-foundation.md`
- `ban_giao/01_source_code/pr_descriptions/02-database-schema.md`
- `ban_giao/01_source_code/pr_descriptions/03-authentication.md`
- `ban_giao/01_source_code/pr_descriptions/04-accounts-classes.md`
- `ban_giao/01_source_code/pr_descriptions/05-document-management.md`
- `ban_giao/01_source_code/pr_descriptions/06-webhook-security.md`
- `ban_giao/01_source_code/pr_descriptions/07-event-memory-quota.md`
- `ban_giao/01_source_code/pr_descriptions/08-tickets-outbound.md`
- `ban_giao/01_source_code/pr_descriptions/09-durable-worker.md`
- `ban_giao/01_source_code/pr_descriptions/10-parsing-local-models.md`
- `ban_giao/01_source_code/pr_descriptions/11-rag-grounded-answer.md`
- `ban_giao/01_source_code/pr_descriptions/12-rewrite-progress.md`
- `ban_giao/01_source_code/pr_descriptions/13-portal-frontend.md`
- `ban_giao/01_source_code/pr_descriptions/14-simulator-api-assembly.md`
- `ban_giao/01_source_code/pr_descriptions/15-demo-launchers.md`
- `ban_giao/01_source_code/pr_descriptions/16-sample-materials.md`
- `ban_giao/01_source_code/pr_descriptions/17-backend-integration-tests.md`
- `ban_giao/01_source_code/pr_descriptions/18-rag-regression-tests.md`
- `ban_giao/01_source_code/pr_descriptions/19-golden-evaluation.md`
- `ban_giao/01_source_code/pr_descriptions/20-handover-documentation.md`
- `ban_giao/01_source_code/pull_requests.json`
- `ban_giao/02_kien_truc/KIEN_TRUC.md`
- `ban_giao/02_kien_truc/architecture.mmd`
- `ban_giao/04_huong_dan/CAI_DAT_VA_VAN_HANH.md`
- `ban_giao/04_huong_dan/GOOGLE_DOCS.md`
- `ban_giao/04_huong_dan/images/01-khoi-tao-admin.png`
- `ban_giao/04_huong_dan/images/02-hai-lop.png`
- `ban_giao/04_huong_dan/images/03-tim-tai-khoan.png`
- `ban_giao/04_huong_dan/images/04-gia-lap.png`
- `ban_giao/06_kiem_thu/BAO_CAO_KIEM_THU.md`
- `ban_giao/06_kiem_thu/bootstrap-check.json`
- `ban_giao/06_kiem_thu/browser-check.json`
- `ban_giao/06_kiem_thu/golden_results.csv`
- `ban_giao/06_kiem_thu/golden_summary.json`
- `ban_giao/06_kiem_thu/pytest-output.txt`
- `ban_giao/06_kiem_thu/pytest-results.xml`
- `ban_giao/06_kiem_thu/schema-validation.txt`
- `ban_giao/06_kiem_thu/test-cases.csv`
- `ban_giao/06_kiem_thu/test-cases.txt`
- `ban_giao/07_van_hanh/CHI_PHI_VA_ZALO.md`
- `ban_giao/README.md`
- `docs/07-user-behavior-and-folder-responsibilities.md`
- `docs/architecture/01-project-review.md`
- `docs/architecture/04-folder-structure.md`
- `docs/contracts/05-processing-contracts.md`
- `docs/testing/06-acceptance-matrix.md`

## Phụ thuộc và kiểm tra

Đây là PR 20/20 trong chuỗi bàn giao, base `delivery/19-golden-evaluation`. Các module được lắp ghép dần; không tuyên bố mọi nhánh trung gian là app chạy độc lập. Bản đầy đủ đã đạt 130 test, 18 kiểm tra DDL và kiểm tra nạp corpus/UI; bằng chứng nằm ở PR 20. Sau PR 14 có thể kiểm tra app assembly; sau PR 17–19 chạy tập test tương ứng.

## Bảo mật và dữ liệu

Không đưa .env, API key, DB vận hành, logs hoặc model cache vào Git. Học liệu demo và dữ liệu golden là dữ liệu được chọn để bàn giao.

## Merge

Review theo thứ tự 01 → 20. Sau khi PR trước đã merge vào main, đổi base PR kế tiếp sang main rồi merge bằng merge commit để giữ chuỗi commit; tránh merge nhầm vào nhánh phụ. PR được chuẩn bị dạng draft để review trước.
