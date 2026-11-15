# Từ điển dữ liệu SQLite v5

Định nghĩa hiện hành; namespace tích hợp mới là `zalo_bot`. Quyền chat theo lớp, không có hồ sơ học viên.

## access_scopes

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `scope_type` | TEXT | Có | — |
| `course_id` | TEXT | Không | — |
| `class_id` | TEXT | Không | — |

## audit_logs

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `request_id` | TEXT | Có | — |
| `actor_user_id` | TEXT | Không | — |
| `action` | TEXT | Có | — |
| `entity_type` | TEXT | Có | — |
| `entity_id` | TEXT | Có | — |
| `change_redacted_json` | TEXT | Có | — |
| `created_at` | TEXT | Có | — |

## auth_sessions

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `user_id` | TEXT | Có | — |
| `token_hash` | TEXT | Có | — |
| `created_at` | TEXT | Có | — |
| `expires_at` | TEXT | Có | — |
| `revoked_at` | TEXT | Không | — |
| `class_id` | TEXT | Không | — |

## classes

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `course_id` | TEXT | Có | — |
| `name` | TEXT | Có | — |
| `bot_enabled` | INTEGER | Có | — |
| `status` | TEXT | Có | — |
| `created_at` | TEXT | Có | — |
| `updated_at` | TEXT | Có | — |

## cleanup_jobs

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `document_version_id` | TEXT | Có | — |
| `cleanup_kind` | TEXT | Có | — |
| `status` | TEXT | Có | — |
| `attempts` | INTEGER | Có | — |
| `max_attempts` | INTEGER | Có | — |
| `lease_token` | TEXT | Không | — |
| `lease_expires_at` | TEXT | Không | — |
| `next_attempt_at` | TEXT | Có | — |
| `error_code` | TEXT | Không | — |
| `created_at` | TEXT | Có | — |
| `finished_at` | TEXT | Không | — |

## conversation_sessions

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `class_id` | TEXT | Có | — |
| `group_binding_id` | TEXT | Có | — |
| `status` | TEXT | Có | — |
| `started_at` | TEXT | Có | — |
| `last_hoi_at` | TEXT | Có | — |
| `expires_at` | TEXT | Có | — |

## courses

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `name` | TEXT | Có | — |
| `status` | TEXT | Có | — |
| `created_at` | TEXT | Có | — |
| `updated_at` | TEXT | Có | — |

## daily_usage

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `usage_key` | TEXT | Có | 1 |
| `local_date` | TEXT | Có | 2 |
| `accepted_count` | INTEGER | Có | — |
| `updated_at` | TEXT | Có | — |

## document_access

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `document_id` | TEXT | Có | 1 |
| `scope_id` | TEXT | Có | 2 |
| `granted_by` | TEXT | Có | — |
| `created_at` | TEXT | Có | — |

## document_chunks

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `point_id` | TEXT | Có | 1 |
| `document_id` | TEXT | Có | — |
| `document_version_id` | TEXT | Có | — |
| `chunk_id` | TEXT | Có | — |
| `scope_id` | TEXT | Có | — |
| `section_id` | TEXT | Không | — |
| `section_path` | TEXT | Không | — |
| `topic` | TEXT | Có | — |
| `page` | INTEGER | Không | — |
| `sheet_name` | TEXT | Không | — |
| `row_start` | INTEGER | Không | — |
| `row_end` | INTEGER | Không | — |
| `content_sha256` | TEXT | Có | — |
| `created_at` | TEXT | Có | — |
| `indexed_at` | TEXT | Không | — |

## document_versions

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `document_id` | TEXT | Có | — |
| `version` | INTEGER | Có | — |
| `source_version` | TEXT | Không | — |
| `sha256` | TEXT | Có | — |
| `file_path` | TEXT | Có | — |
| `original_filename` | TEXT | Có | — |
| `mime_type` | TEXT | Có | — |
| `file_size_bytes` | INTEGER | Có | — |
| `status` | TEXT | Có | — |
| `extraction_config_json` | TEXT | Có | — |
| `parser_version` | TEXT | Không | — |
| `embedding_model` | TEXT | Không | — |
| `vector_size` | INTEGER | Không | — |
| `chunk_count` | INTEGER | Có | — |
| `point_count` | INTEGER | Có | — |
| `change_note` | TEXT | Không | — |
| `uploaded_by` | TEXT | Có | — |
| `uploaded_at` | TEXT | Có | — |
| `indexed_at` | TEXT | Không | — |
| `activated_at` | TEXT | Không | — |
| `error_code` | TEXT | Không | — |

## documents

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `title` | TEXT | Có | — |
| `topic` | TEXT | Có | — |
| `source_code` | TEXT | Không | — |
| `source_kind` | TEXT | Có | — |
| `status` | TEXT | Có | — |
| `active_version_id` | TEXT | Không | — |
| `revision` | INTEGER | Có | — |
| `created_by` | TEXT | Có | — |
| `created_at` | TEXT | Có | — |
| `updated_at` | TEXT | Có | — |
| `deleted_at` | TEXT | Không | — |
| `deleted_by` | TEXT | Không | — |
| `delete_reason` | TEXT | Không | — |

## external_identities

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `user_id` | TEXT | Có | — |
| `platform` | TEXT | Có | — |
| `external_sender_id` | TEXT | Có | — |
| `is_bot` | INTEGER | Có | — |
| `is_active` | INTEGER | Có | — |
| `created_at` | TEXT | Có | — |

## faq_entries

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `source_ticket_id` | TEXT | Có | — |
| `question_redacted` | TEXT | Có | — |
| `approved_answer_redacted` | TEXT | Có | — |
| `topic` | TEXT | Có | — |
| `scope_id` | TEXT | Có | — |
| `status` | TEXT | Có | — |
| `document_id` | TEXT | Không | — |
| `created_by` | TEXT | Có | — |
| `approved_by` | TEXT | Không | — |
| `created_at` | TEXT | Có | — |
| `updated_at` | TEXT | Có | — |
| `approved_at` | TEXT | Không | — |

## group_bindings

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `class_id` | TEXT | Có | — |
| `platform` | TEXT | Có | — |
| `external_group_id` | TEXT | Có | — |
| `display_name` | TEXT | Có | — |
| `is_active` | INTEGER | Có | — |
| `created_at` | TEXT | Có | — |

## ingestion_jobs

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `document_version_id` | TEXT | Có | — |
| `status` | TEXT | Có | — |
| `stage` | TEXT | Có | — |
| `attempts` | INTEGER | Có | — |
| `max_attempts` | INTEGER | Có | — |
| `chunks_indexed` | INTEGER | Có | — |
| `points_indexed` | INTEGER | Có | — |
| `lease_token` | TEXT | Không | — |
| `lease_expires_at` | TEXT | Không | — |
| `next_attempt_at` | TEXT | Có | — |
| `error_code` | TEXT | Không | — |
| `error_message_redacted` | TEXT | Không | — |
| `created_at` | TEXT | Có | — |
| `started_at` | TEXT | Không | — |
| `finished_at` | TEXT | Không | — |

## messages

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `session_id` | TEXT | Có | — |
| `event_key` | TEXT | Có | — |
| `class_id` | TEXT | Có | — |
| `group_binding_id` | TEXT | Có | — |
| `sender_user_id` | TEXT | Không | — |
| `role` | TEXT | Có | — |
| `message_kind` | TEXT | Có | — |
| `text_redacted` | TEXT | Có | — |
| `memory_eligible` | INTEGER | Có | — |
| `status` | TEXT | Có | — |
| `created_at` | TEXT | Có | — |

## outbound_messages

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `event_key` | TEXT | Có | — |
| `class_id` | TEXT | Có | — |
| `group_binding_id` | TEXT | Có | — |
| `message_kind` | TEXT | Có | — |
| `reply_to_external_event_id` | TEXT | Có | — |
| `text_redacted` | TEXT | Có | — |
| `citations_json` | TEXT | Có | — |
| `ticket_id` | TEXT | Không | — |
| `ticket_reply_id` | TEXT | Không | — |
| `status` | TEXT | Có | — |
| `attempts` | INTEGER | Có | — |
| `max_attempts` | INTEGER | Có | — |
| `lease_token` | TEXT | Không | — |
| `lease_expires_at` | TEXT | Không | — |
| `next_attempt_at` | TEXT | Có | — |
| `external_message_id` | TEXT | Không | — |
| `created_at` | TEXT | Có | — |
| `sent_at` | TEXT | Không | — |
| `error_code` | TEXT | Không | — |

## quota_reservations

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `event_key` | TEXT | Có | 1 |
| `usage_key` | TEXT | Có | — |
| `local_date` | TEXT | Có | — |
| `status` | TEXT | Có | — |
| `reserved_at` | TEXT | Có | — |
| `charged_at` | TEXT | Không | — |
| `released_at` | TEXT | Không | — |
| `release_reason` | TEXT | Không | — |

## rag_citations

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `rag_run_id` | TEXT | Có | — |
| `ordinal` | INTEGER | Có | — |
| `point_id` | TEXT | Có | — |
| `title_snapshot` | TEXT | Có | — |
| `page` | INTEGER | Không | — |
| `section_path` | TEXT | Không | — |
| `evidence_excerpt_redacted` | TEXT | Có | — |
| `created_at` | TEXT | Có | — |

## rag_run_attempts

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `rag_run_id` | TEXT | Không | — |
| `ingestion_job_id` | TEXT | Không | — |
| `stage` | TEXT | Có | — |
| `attempt_no` | INTEGER | Có | — |
| `call_key` | TEXT | Có | — |
| `provider` | TEXT | Có | — |
| `model` | TEXT | Có | — |
| `status` | TEXT | Có | — |
| `input_tokens` | INTEGER | Không | — |
| `output_tokens` | INTEGER | Không | — |
| `estimated_cost_usd_micros` | INTEGER | Không | — |
| `pricing_snapshot_json` | TEXT | Có | — |
| `provider_request_id` | TEXT | Không | — |
| `started_at` | TEXT | Có | — |
| `finished_at` | TEXT | Không | — |
| `error_code` | TEXT | Không | — |

## rag_runs

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `event_key` | TEXT | Có | — |
| `status` | TEXT | Có | — |
| `allowed_scopes_json` | TEXT | Có | — |
| `active_versions_json` | TEXT | Có | — |
| `memory_event_keys_json` | TEXT | Có | — |
| `evidence_sufficient` | INTEGER | Không | — |
| `evidence_reason_redacted` | TEXT | Không | — |
| `latency_ms` | INTEGER | Không | — |
| `started_at` | TEXT | Có | — |
| `finished_at` | TEXT | Không | — |
| `error_code` | TEXT | Không | — |
| `query_rewrite_json` | TEXT | Có | — |

## security_events

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `event_key` | TEXT | Không | — |
| `request_id` | TEXT | Có | — |
| `actor_user_id` | TEXT | Không | — |
| `reason_code` | TEXT | Có | — |
| `severity` | TEXT | Có | — |
| `details_redacted_json` | TEXT | Có | — |
| `created_at` | TEXT | Có | — |

## support_tickets

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `event_key` | TEXT | Có | — |
| `class_id` | TEXT | Có | — |
| `group_binding_id` | TEXT | Có | — |
| `requester_user_id` | TEXT | Không | — |
| `question_redacted` | TEXT | Có | — |
| `reason_code` | TEXT | Có | — |
| `evidence_summary_redacted` | TEXT | Không | — |
| `status` | TEXT | Có | — |
| `assignee_id` | TEXT | Không | — |
| `revision` | INTEGER | Có | — |
| `created_at` | TEXT | Có | — |
| `updated_at` | TEXT | Có | — |
| `answered_at` | TEXT | Không | — |
| `closed_at` | TEXT | Không | — |

## teacher_assignments

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `teacher_id` | TEXT | Có | 1 |
| `class_id` | TEXT | Có | 2 |
| `is_active` | INTEGER | Có | — |
| `assigned_at` | TEXT | Có | — |

## ticket_replies

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `ticket_id` | TEXT | Có | — |
| `teacher_id` | TEXT | Có | — |
| `answer_redacted` | TEXT | Có | — |
| `created_at` | TEXT | Có | — |

## user_credentials

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `user_id` | TEXT | Có | 1 |
| `username` | TEXT | Có | — |
| `password_hash` | TEXT | Có | — |
| `failed_attempts` | INTEGER | Có | — |
| `locked_until` | TEXT | Không | — |
| `last_login_at` | TEXT | Không | — |
| `password_changed_at` | TEXT | Có | — |
| `created_at` | TEXT | Có | — |
| `updated_at` | TEXT | Có | — |

## users

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `id` | TEXT | Có | 1 |
| `display_name` | TEXT | Có | — |
| `role` | TEXT | Có | — |
| `is_active` | INTEGER | Có | — |
| `created_at` | TEXT | Có | — |
| `updated_at` | TEXT | Có | — |

## webhook_events

| Cột | Kiểu | Bắt buộc | Khóa chính |
|---|---|---|---|
| `event_key` | TEXT | Có | 1 |
| `request_id` | TEXT | Có | — |
| `platform` | TEXT | Có | — |
| `external_event_id` | TEXT | Có | — |
| `raw_group_id` | TEXT | Có | — |
| `raw_sender_id` | TEXT | Có | — |
| `group_binding_id` | TEXT | Không | — |
| `class_id` | TEXT | Không | — |
| `user_id` | TEXT | Không | — |
| `question_redacted` | TEXT | Không | — |
| `payload_sha256` | TEXT | Có | — |
| `reply_to_external_event_id` | TEXT | Không | — |
| `status` | TEXT | Có | — |
| `outcome_code` | TEXT | Không | — |
| `accepted_at` | TEXT | Không | — |
| `processing_started_at` | TEXT | Không | — |
| `attempts` | INTEGER | Có | — |
| `max_attempts` | INTEGER | Có | — |
| `lease_token` | TEXT | Không | — |
| `lease_expires_at` | TEXT | Không | — |
| `next_attempt_at` | TEXT | Có | — |
| `sent_at` | TEXT | Có | — |
| `received_at` | TEXT | Có | — |
| `completed_at` | TEXT | Không | — |
| `error_code` | TEXT | Không | — |
