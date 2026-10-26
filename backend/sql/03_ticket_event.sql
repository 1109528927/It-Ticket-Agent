USE it_ticket;

CREATE TABLE IF NOT EXISTS `ticket_event` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `ticket_id` INT NOT NULL,
  `actor_id` INT NOT NULL,
  `event_type` VARCHAR(30) NOT NULL,
  `detail` TEXT NULL,
  `create_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  PRIMARY KEY (`id`),
  KEY `idx_ticket_event_ticket` (`ticket_id`),
  CONSTRAINT `fk_ticket_event_ticket`
    FOREIGN KEY (`ticket_id`) REFERENCES `ticket` (`id`)
    ON DELETE CASCADE,
  CONSTRAINT `fk_ticket_event_actor`
    FOREIGN KEY (`actor_id`) REFERENCES `user` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
