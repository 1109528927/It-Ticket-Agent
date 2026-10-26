-- 助手对话落库：full 进模型；progress 只给人看；summary 超长压缩用
CREATE TABLE IF NOT EXISTS chat_message (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  ticket_id BIGINT NULL,
  user_id BIGINT NOT NULL,
  role VARCHAR(16) NOT NULL,
  content TEXT NOT NULL,
  kind VARCHAR(16) NOT NULL DEFAULT 'full',
  create_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_chat_ticket (ticket_id),
  INDEX idx_chat_user (user_id),
  INDEX idx_chat_kind (kind)
);
