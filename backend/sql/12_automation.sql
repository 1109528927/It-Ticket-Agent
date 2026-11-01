-- 工单自动化：助手草稿落库、跑批报告、单票处理结果
-- PostgreSQL；也可用 srcipts/create_tables.py 按模型建表

CREATE TABLE IF NOT EXISTS ticket_assistant_draft (
  ticket_id BIGINT PRIMARY KEY REFERENCES ticket(id),
  draft_type VARCHAR(32) NOT NULL DEFAULT 'reply',
  content TEXT NOT NULL,
  meta_json TEXT NULL,
  source VARCHAR(40) NOT NULL DEFAULT 'batch',
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS automation_job_run (
  id BIGSERIAL PRIMARY KEY,
  job_type VARCHAR(40) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'running',
  trigger_source VARCHAR(20) NOT NULL DEFAULT 'cron',
  summary_json TEXT NULL,
  error_message TEXT NULL,
  started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at TIMESTAMP NULL
);

CREATE TABLE IF NOT EXISTS automation_ticket_result (
  id BIGSERIAL PRIMARY KEY,
  run_id BIGINT NOT NULL REFERENCES automation_job_run(id) ON DELETE CASCADE,
  ticket_id BIGINT NOT NULL REFERENCES ticket(id),
  action VARCHAR(40) NOT NULL,
  success BOOLEAN NOT NULL DEFAULT TRUE,
  detail TEXT NULL,
  create_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_auto_result_run ON automation_ticket_result(run_id);
CREATE INDEX IF NOT EXISTS idx_auto_result_ticket ON automation_ticket_result(ticket_id);
CREATE INDEX IF NOT EXISTS idx_auto_job_started ON automation_job_run(started_at DESC);
