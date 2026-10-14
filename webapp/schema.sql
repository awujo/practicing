-- Fallback copy of db/schema.sql (used only when db/schema.sql is missing). Keep the two files identical
-- apart from these header lines (tests/test_review_fixes.py checks it).
CREATE TABLE IF NOT EXISTS bias (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  pair          VARCHAR(16)  NOT NULL,
  story         CHAR(1)      NOT NULL,              -- M / W / D
  side          VARCHAR(4)   NOT NULL,              -- BUY / SELL
  status        VARCHAR(16)  NOT NULL,              -- TAPPED / CONFIRMED / TARGET_HIT / INVALIDATED / ENDED_FLIP / CANCELLED
  level_kind    VARCHAR(8)   NULL,                  -- A / V / OC / flip
  level         DOUBLE       NULL,
  point_b       DOUBLE       NULL,
  target        DOUBLE       NULL,
  invalidation  DOUBLE       NULL,
  tap_time      DATETIME     NOT NULL,              -- UTC, start of the origin-TF tap candle
  confirm_time  DATETIME     NULL,                  -- UTC
  no_trade      TINYINT(1)   NOT NULL DEFAULT 0,   -- 1 = do not trade (e.g. D story while M and W disagree)
  no_trade_reason VARCHAR(64) NULL,                 -- why (e.g. "M/W conflict")
  rule          VARCHAR(32)  NULL,                  -- standard / sweep_start / flip / alignment / cadjpy (+overlap)
  end_reason    VARCHAR(200) NULL,                  -- why the story ended (target / invalidated / flip ...)
  breakout_time DATETIME     NULL,                  -- UTC, open of the confirm-TF candle that broke point B
  next_day      TINYINT(1)   NULL,                  -- Next Day Rule: 1 = breakout after the rejection candle closed
  retrace       TINYINT(1)   NULL,                  -- 1 = closed back beyond B later on the breakout day (warning)
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
  model       VARCHAR(16)  NOT NULL DEFAULT 'continuation',  -- entry model: continuation / qmr
  entry       DOUBLE       NULL,
  stop        DOUBLE       NULL,
  tp1         DOUBLE       NULL,
  tp2         DOUBLE       NULL,
  status      VARCHAR(16)  NOT NULL DEFAULT 'PENDING',  -- PENDING / APPROVED / TRIGGERED / MISSED / CANCELLED, then paper outcome TP1_HIT / TP2_HIT / SL_HIT / EXPIRED
  created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  alerted_at  DATETIME     NULL,
  filled_at   DATETIME     NULL,                  -- UTC start of the H1 bar that filled the limit (paper)
  result_r    DOUBLE       NULL,                  -- paper R, TP1 variant (exit at TP1 / stop / timeout)
  result_r_tp2 DOUBLE      NULL,                  -- paper R, TP2 variant (hold for TP2), NULL until resolved
  hit_price   DOUBLE       NULL,                  -- level the status names (stop / TP1 / TP2 / timeout close)
  closed_at   DATETIME     NULL,                  -- UTC start of the H1 bar where tracking ended
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

-- entries.model came later: add it to an existing table (MySQL 8 has no ADD COLUMN IF NOT EXISTS).
-- Idempotent: the ALTER only runs when the column is missing, otherwise a no-op DO 0 runs.
SET @slk_add_model = (SELECT IF(COUNT(*) = 0,
  'ALTER TABLE entries ADD COLUMN model VARCHAR(16) NOT NULL DEFAULT ''continuation'' AFTER side',
  'DO 0') FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'entries' AND COLUMN_NAME = 'model');
PREPARE slk_add_model_stmt FROM @slk_add_model;
EXECUTE slk_add_model_stmt;
DEALLOCATE PREPARE slk_add_model_stmt;
