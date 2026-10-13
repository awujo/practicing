-- Fallback copy of db/schema.sql (used only when db/schema.sql is missing). Keep the two files identical
-- apart from these header lines (tests/test_review_fixes.py checks it).
CREATE TABLE IF NOT EXISTS bias (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  pair          VARCHAR(16)  NOT NULL,
  story         CHAR(1)      NOT NULL,              -- M / W / D
  side          VARCHAR(4)   NOT NULL,              -- BUY / SELL
  status        VARCHAR(16)  NOT NULL,              -- TAPPED / CONFIRMED / TARGET_HIT / INVALIDATED / CANCELLED
  level_kind    VARCHAR(8)   NULL,                  -- A / V / OC / flip
  level         DOUBLE       NULL,
  point_b       DOUBLE       NULL,
  target        DOUBLE       NULL,
  invalidation  DOUBLE       NULL,
  tap_time      DATETIME     NOT NULL,              -- UTC, start of the origin-TF tap candle
  confirm_time  DATETIME     NULL,                  -- UTC
  updated_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uq_bias (pair, story, tap_time),
  KEY ix_bias_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS entries (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  bias_id     BIGINT       NULL,
  pair        VARCHAR(16)  NOT NULL,
  tf          VARCHAR(4)   NULL,
  side        VARCHAR(4)   NULL,
  entry       DOUBLE       NULL,
  stop        DOUBLE       NULL,
  tp1         DOUBLE       NULL,
  tp2         DOUBLE       NULL,
  status      VARCHAR(16)  NOT NULL DEFAULT 'PENDING',  -- PENDING / TRIGGERED / MISSED / CANCELLED
  created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  alerted_at  DATETIME     NULL,
  KEY ix_entries_bias (bias_id),
  CONSTRAINT fk_entries_bias FOREIGN KEY (bias_id) REFERENCES bias(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS orders (
  id                   BIGINT AUTO_INCREMENT PRIMARY KEY,
  entry_id             BIGINT       NULL,
  client_order_id      VARCHAR(64)  NOT NULL,
  ctrader_position_id  BIGINT       NULL,
  volume               DOUBLE       NULL,
  status               VARCHAR(16)  NULL,
  opened_at            DATETIME     NULL,
  closed_at            DATETIME     NULL,
  pnl                  DOUBLE       NULL,
  UNIQUE KEY uq_client_order (client_order_id),
  KEY ix_orders_entry (entry_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS settings (
  k  VARCHAR(64) PRIMARY KEY,
  v  TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS runs (
  id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  job          VARCHAR(32)  NOT NULL,
  planned_at   DATETIME     NULL,
  started_at   DATETIME     NULL,
  finished_at  DATETIME     NULL,
  ok           TINYINT(1)   NULL,
  note         TEXT         NULL,
  KEY ix_runs_job (job, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- defaults (never overwrite values the user already set)
INSERT IGNORE INTO settings (k, v) VALUES
  ('kill_switch', 'off'),
  ('auto_trade', 'off'),
  ('risk_pct', '0.5'),
  ('stories', 'D,W,M');
