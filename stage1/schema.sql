-- Stage 1 schema: Kevin King SLK bot (Aiven MySQL, defaultdb)
-- Idempotent: safe to re-run. No secrets here - DB URL lives in GitHub Secrets only.

CREATE TABLE IF NOT EXISTS pairs (
  symbol     VARCHAR(16) PRIMARY KEY,      -- e.g. USDJPY
  enabled    TINYINT(1) NOT NULL DEFAULT 1,
  bias_tf    VARCHAR(4)  NOT NULL DEFAULT 'D',   -- storyline TF (W/D/H4)
  entry_tf   VARCHAR(4)  NOT NULL DEFAULT 'H1',  -- confirmation TF below bias TF
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS candles (
  symbol   VARCHAR(16) NOT NULL,
  tf       VARCHAR(4)  NOT NULL,   -- W D H4 H1 M15
  t        DATETIME    NOT NULL,   -- candle open time, UTC
  o DOUBLE NOT NULL, h DOUBLE NOT NULL, l DOUBLE NOT NULL, c DOUBLE NOT NULL,
  tick_volume BIGINT NOT NULL DEFAULT 0,
  fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (symbol, tf, t),
  KEY idx_candles_lookup (symbol, tf, t)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS bias (
  id         BIGINT AUTO_INCREMENT PRIMARY KEY,
  symbol     VARCHAR(16) NOT NULL,
  tf         VARCHAR(4)  NOT NULL,
  direction  ENUM('bullish','bearish','neutral') NOT NULL,
  reason     TEXT NOT NULL,               -- cites STRATEGY.md rule + swing levels
  key_levels JSON NULL,                   -- [{type,price,fresh,status}]
  computed_at DATETIME NOT NULL,
  UNIQUE KEY uq_bias (symbol, tf, computed_at),
  KEY idx_bias_latest (symbol, tf, computed_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS signals (
  id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  symbol      VARCHAR(16) NOT NULL,
  tf          VARCHAR(4)  NOT NULL,
  side        ENUM('buy','sell') NOT NULL,
  model       ENUM('A-breakout-retest','B-QMRO') NOT NULL,
  entry       DOUBLE NOT NULL,
  stop        DOUBLE NOT NULL,
  target      DOUBLE NOT NULL,
  rr          DOUBLE NOT NULL,
  score       DOUBLE NULL,
  reasons     TEXT NULL,                  -- storyline chain that produced this signal
  status      ENUM('alerted','confirmed','rejected','expired') NOT NULL DEFAULT 'alerted',
  bar_t       DATETIME NOT NULL,          -- candle the signal completed on (no look-ahead)
  created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_signals (symbol, created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS trades (
  id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  signal_id    BIGINT NOT NULL,            -- one order per signal = idempotency guard
  symbol       VARCHAR(16) NOT NULL,
  side         ENUM('buy','sell') NOT NULL,
  units        DOUBLE NOT NULL,
  entry        DOUBLE NOT NULL,
  stop         DOUBLE NOT NULL,
  target       DOUBLE NOT NULL,
  ctrader_order_id  VARCHAR(64) NULL,
  ctrader_position_id VARCHAR(64) NULL,
  status       ENUM('pending_confirm','sent','filled','rejected','closed') NOT NULL DEFAULT 'pending_confirm',
  placed_at    TIMESTAMP NULL,
  closed_at    TIMESTAMP NULL,
  pnl          DOUBLE NULL,
  UNIQUE KEY uq_trade_signal (signal_id),
  KEY idx_trades (symbol, placed_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS settings (
  k         VARCHAR(64) PRIMARY KEY,
  v         TEXT NOT NULL,
  is_secret TINYINT(1) NOT NULL DEFAULT 0,   -- secret values stored AES-encrypted (Stage 5 key)
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Defaults chosen so the pipeline runs end-to-end; owner can change any of these.
INSERT IGNORE INTO settings (k, v, is_secret) VALUES
  ('risk_pct',        '0.5', 0),   -- UNCONFIRMED (open Q1): placeholder until owner sets it
  ('max_open_trades', '2',   0),   -- UNCONFIRMED (open Q1)
  ('min_rr',          '2.0', 0),   -- UNCONFIRMED (open Q4)
  ('sessions',        'LDN,NY', 0),-- UNCONFIRMED (open Q2)
  ('kill_switch',     'off', 0),
  ('auto_mode',       'off', 0),   -- off = Telegram confirm button required before any order
  ('ctrader_access_token',  '', 1),
  ('ctrader_refresh_token', '', 1);

CREATE TABLE IF NOT EXISTS runs (
  id            BIGINT AUTO_INCREMENT PRIMARY KEY,
  run_id        VARCHAR(64) NOT NULL,        -- GitHub Actions run id
  started_planned DATETIME(3) NULL,          -- when the external timer fired the dispatch
  started_actual  DATETIME(3) NULL,          -- first line of business logic in the runner
  delay_seconds DOUBLE NULL,                 -- started_actual - started_planned (cron-drift metric)
  minutes_used  DOUBLE NULL,
  ok            TINYINT(1) NOT NULL DEFAULT 1,
  note          VARCHAR(255) NULL,
  INDEX idx_runs (started_actual)
) ENGINE=InnoDB;
