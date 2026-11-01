-- 自动化业务配置（单行 id=1）；客服端可改，调度每次唤醒先读这张表
-- PostgreSQL；也可用 srcipts/create_tables.py 按模型建表

CREATE TABLE IF NOT EXISTS automation_config (
  id INTEGER PRIMARY KEY DEFAULT 1,
  enable_backlog_draft BOOLEAN NOT NULL DEFAULT TRUE,
  enable_sla_sweep BOOLEAN NOT NULL DEFAULT TRUE,
  enable_triage_on_create BOOLEAN NOT NULL DEFAULT TRUE,
  backlog_schedule_mode VARCHAR(20) NOT NULL DEFAULT 'interval',
  backlog_interval_minutes INTEGER NOT NULL DEFAULT 60,
  backlog_daily_time VARCHAR(8) NOT NULL DEFAULT '02:00',
  cron_expression VARCHAR(64) NULL,
  sla_interval_minutes INTEGER NOT NULL DEFAULT 15,
  skip_high_risk BOOLEAN NOT NULL DEFAULT FALSE,
  auto_send_simple_reply BOOLEAN NOT NULL DEFAULT FALSE,
  backlog_categories TEXT NULL,
  last_backlog_run_at TIMESTAMP NULL,
  last_sla_run_at TIMESTAMP NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO automation_config (id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;
