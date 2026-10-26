-- 设备 / 网络类处理清单：客服勾选完才能标记解决
CREATE TABLE IF NOT EXISTS ticket_checklist (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  ticket_id INT NOT NULL,
  item_key VARCHAR(40) NOT NULL,
  label VARCHAR(200) NOT NULL,
  checked TINYINT NOT NULL DEFAULT 0,
  create_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_ticket_item (ticket_id, item_key),
  KEY idx_checklist_ticket (ticket_id),
  CONSTRAINT fk_checklist_ticket
    FOREIGN KEY (ticket_id) REFERENCES ticket (id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
