USE it_ticket;

CREATE TABLE IF NOT EXISTS `kb_article` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `category` VARCHAR(20) NOT NULL,
  `title` VARCHAR(200) NOT NULL,
  `content` TEXT NOT NULL,
  `create_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_kb_category` (`category`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO `kb_article` (`category`, `title`, `content`)
SELECT * FROM (
  SELECT 'account' AS category, '忘记域密码' AS title,
    '1. 核实员工工号与姓名\n2. 确认近期无异常登录\n3. 在系统提出重置密码\n4. 等客服确认后通知员工改密' AS content
  UNION ALL SELECT 'account', '邮箱无法登录',
    '1. 确认账号未被锁定\n2. 检查是否改过密码未同步\n3. 必要时提出重置密码\n4. 确认后告知员工'
  UNION ALL SELECT 'device', '打印机连不上',
    '1. 确认打印机通电联网\n2. 检查驱动与默认打印机\n3. 重启打印后台服务\n4. 仍不行则登记设备报修'
  UNION ALL SELECT 'device', '电脑蓝屏重启',
    '1. 记录蓝屏代码与时间\n2. 排查最近安装的软件驱动\n3. 建议安全模式排查\n4. 硬件怀疑则开设备单'
  UNION ALL SELECT 'network', '办公网断连',
    '1. 确认网线或 WiFi 信号\n2. 换网口或重连 WiFi\n3. 查 IP 与网关是否正常\n4. 大面积故障升级网络组'
  UNION ALL SELECT 'network', 'VPN 连不上',
    '1. 确认账号未过期\n2. 检查客户端版本\n3. 换网络环境重试\n4. 仍失败则重置 VPN 凭据（需确认）'
  UNION ALL SELECT 'permission', '申请系统权限',
    '1. 确认岗位与所需权限组\n2. 主管是否已口头同意\n3. 提出变更权限并写明权限组\n4. 客服确认后再开通'
  UNION ALL SELECT 'permission', '误开权限要收回',
    '1. 核实应保留与应撤销的权限\n2. 提出变更权限\n3. 确认后收回多余权限\n4. 通知申请人结果'
) AS seed
WHERE NOT EXISTS (SELECT 1 FROM `kb_article` LIMIT 1);
