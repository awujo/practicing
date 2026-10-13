-- Fallback schema (used only when db/schema.sql is missing). Idempotent.
CREATE TABLE IF NOT EXISTS bias (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  pair VARCHAR(16) NOT NULL,
  story VARCHAR(1) NOT NULL,
  side VARCHAR(4) NOT NULL,
  status VARCHAR(16) NOT NULL,
  level_kind VARCHAR(16),
  level DOUBLE,
  point_b DOUBLE,
  target DOUBLE,
  invalidation DOUBLE,
  tap_time DATETIME NOT NULL,
  confirm_time DATETIME NULL,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_bias (pair, story, tap_time)
);

CREATE TABLE IF NOT EXISTS entries (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  bias_id BIGINT,
  pair VARCHAR(16) NOT NULL,
  tf VARCHAR(4),
  side VARCHAR(4),
  entry DOUBLE,
  stop DOUBLE,
  tp1 DOUBLE,
  tp2 DOUBLE,
  status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  alerted_at DATETIME NULL,
  FOREIGN KEY (bias_id) REFERENCES bias(id)
);

CREATE TABLE IF NOT EXISTS orders (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  entry_id BIGINT,
  client_order_id VARCHAR(64) NOT NULL,
  ctrader_position_id BIGINT NULL,
  volume DOUBLE,
  status VARCHAR(16),
  opened_at DATETIME NULL,
  closed_at DATETIME NULL,
  pnl DOUBLE NULL,
  UNIQUE KEY uq_client_order (client_order_id)
);

CREATE TABLE IF NOT EXISTS settings (
  k VARCHAR(64) PRIMARY KEY,
  v TEXT
);

CREATE TABLE IF NOT EXISTS runs (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  job VARCHAR(32) NOT NULL,
  planned_at DATETIME NULL,
  started_at DATETIME NULL,
  finished_at DATETIME NULL,
  ok TINYINT(1) NULL,
  note TEXT
);
