-- Agent 每轮可观测记账：工具名、检索条数、是否 HITL、粗算 token
-- MySQL 脚本；也可用 srcipts/create_tables.py 按模型建表

CREATE TABLE IF NOT EXISTS agent_turn_log (
  id BIGINT NOT NULL AUTO_INCREMENT,
  user_id BIGINT NOT NULL,
  ticket_id BIGINT NULL,
  role VARCHAR(20) NOT NULL,
  tools_json TEXT NOT NULL,
  kb_hit_count INT NOT NULL DEFAULT 0,
  hitl TINYINT NOT NULL DEFAULT 0,
  input_tokens INT NOT NULL DEFAULT 0,
  output_tokens INT NOT NULL DEFAULT 0,
  create_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_agent_turn_user (user_id),
  KEY idx_agent_turn_ticket (ticket_id),
  KEY idx_agent_turn_created (create_at)
);
