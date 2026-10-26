USE it_ticket;

CREATE TABLE IF NOT EXISTS `ticket_action` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `ticket_id` INT NOT NULL,
  `proposer_id` INT NOT NULL,
  `action_type` VARCHAR(40) NOT NULL,
  `reason` VARCHAR(500) NOT NULL,
  `payload` TEXT NULL COMMENT 'JSON 字符串',
  `status` VARCHAR(20) NOT NULL DEFAULT 'pending',
  `execution_status` VARCHAR(40) NULL,
  `execution_result` TEXT NULL,
  `create_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_ticket_action_ticket` (`ticket_id`),
  KEY `idx_ticket_action_pending` (`ticket_id`, `status`),
  CONSTRAINT `fk_ticket_action_ticket`
    FOREIGN KEY (`ticket_id`) REFERENCES `ticket` (`id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_ticket_action_proposer`
    FOREIGN KEY (`proposer_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
