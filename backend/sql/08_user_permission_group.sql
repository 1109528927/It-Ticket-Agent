-- 第二版：业务权限组（与 role 登录身份分开）
ALTER TABLE `user`
  ADD COLUMN `permission_group` VARCHAR(64) NULL DEFAULT NULL
  COMMENT '业务权限组，客服确认变更后写入'
  AFTER `role`;
