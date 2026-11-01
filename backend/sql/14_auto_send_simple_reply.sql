-- 夜班无人值守：简单单可自动发送回复（高危仍只起草）
-- PostgreSQL

ALTER TABLE automation_config
  ADD COLUMN IF NOT EXISTS auto_send_simple_reply BOOLEAN NOT NULL DEFAULT FALSE;
