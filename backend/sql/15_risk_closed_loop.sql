-- 风险分级自动化闭环：工单状态扩展字段 + 夜班置信度 / 反馈 SLA 配置
-- PostgreSQL；也可用 srcipts/create_tables.py 按模型建表

-- ticket：升级标记（员工说「还不行」或 SLA 升级时置 1，前端高亮）
ALTER TABLE ticket
  ADD COLUMN IF NOT EXISTS escalate INTEGER NOT NULL DEFAULT 0;

-- automation_config：夜间高置信自动结案、等反馈催办天数
ALTER TABLE automation_config
  ADD COLUMN IF NOT EXISTS enable_night_auto_resolve BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE automation_config
  ADD COLUMN IF NOT EXISTS night_confidence_threshold DOUBLE PRECISION NOT NULL DEFAULT 0.8;

ALTER TABLE automation_config
  ADD COLUMN IF NOT EXISTS enable_feedback_sla BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE automation_config
  ADD COLUMN IF NOT EXISTS feedback_idle_days INTEGER NOT NULL DEFAULT 3;

COMMENT ON COLUMN ticket.escalate IS '1=需人工升级关注；0=正常';
COMMENT ON COLUMN automation_config.enable_night_auto_resolve IS '夜班：非高危且置信度达标时可 auto_reply 并置 auto_resolved';
COMMENT ON COLUMN automation_config.night_confidence_threshold IS '夜班自动结案置信度门槛，默认 0.8';
COMMENT ON COLUMN automation_config.enable_feedback_sla IS '扫描 waiting_feedback 超时催办 / 意图结案';
COMMENT ON COLUMN automation_config.feedback_idle_days IS 'waiting_feedback 超过 N 天未更新则催办';
