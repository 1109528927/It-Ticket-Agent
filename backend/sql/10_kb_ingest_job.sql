-- 知识库多格式入库任务（PDF/DOCX/MD/图片）
-- MySQL 脚本；也可用 srcipts/create_tables.py 按模型建表（PostgreSQL 友好）

CREATE TABLE IF NOT EXISTS kb_ingest_job (
  id INT NOT NULL AUTO_INCREMENT,
  category VARCHAR(20) NOT NULL,
  title VARCHAR(200) NOT NULL,
  filename VARCHAR(255) NOT NULL,
  stored_path VARCHAR(512) NOT NULL,
  ext VARCHAR(16) NOT NULL,
  enable_ocr TINYINT NOT NULL DEFAULT 0,
  status VARCHAR(20) NOT NULL DEFAULT 'pending',
  error_message TEXT NULL,
  article_id INT NULL,
  chunk_count INT NOT NULL DEFAULT 0,
  created_by INT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at DATETIME NULL,
  PRIMARY KEY (id),
  KEY idx_kb_ingest_status (status),
  KEY idx_kb_ingest_created (created_at)
);
