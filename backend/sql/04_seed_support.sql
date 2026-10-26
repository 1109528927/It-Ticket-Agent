USE it_ticket;

INSERT INTO `user` (`username`, `password`, `employee_no`, `role`)
SELECT 'support', '$2b$12$zjrpBSH6IFf5Lx0mOo3igO.7yGqYDqrpwA.lWzx/qqeJsZKMUjNrO', 'S0001', 'support'
WHERE NOT EXISTS (SELECT 1 FROM `user` WHERE `username` = 'support');
