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
  session     VARCHAR(8) NOT NULL DEFAULT 'UNKNOWN', -- ASIA/LDN/NY/SYDNEY/UNKNOWN (recorded, never filtered - owner decision Q2)
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
  session      VARCHAR(8) NOT NULL DEFAULT 'UNKNOWN', -- copied from signal; per-session backtest reporting (owner decision Q2)
  placed_at    TIMESTAMP NULL,
  closed_at    TIMESTAMP NULL,
  pnl          DOUBLE NULL,
  pnl_rr       DOUBLE NULL,               -- realized R multiple of risk; per-pair/per-session stats key
  UNIQUE KEY uq_trade_signal (signal_id),
  KEY idx_trades (symbol, placed_at),
  KEY idx_trades_session (session, status)
) ENGINE=InnoDB;

-- Idempotent ALTERs for databases created by the pre-2026-10-11 schema.
-- MySQL has no "ADD COLUMN IF NOT EXISTS"; run.py applies these via information_schema checks.
-- @migrate: signals.session, trades.session, trades.pnl_rr

CREATE TABLE IF NOT EXISTS settings (
  k         VARCHAR(64) PRIMARY KEY,
  v         TEXT NOT NULL,
  is_secret TINYINT(1) NOT NULL DEFAULT 0,   -- secret values stored AES-encrypted (Stage 5 key)
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Defaults chosen so the pipeline runs end-to-end; owner can change any of these.
INSERT IGNORE INTO settings (k, v, is_secret) VALUES
  ('risk_pct',        '0.5', 0),   -- owner FINAL decision: editable setting, not a rule (backtest may sweep it)
  ('max_open_trades', '2',   0),   -- owner FINAL decision: editable setting
  ('min_rr',          '2.0', 0),   -- owner FINAL decision: editable setting for backtest sweeps
  ('sessions',        'ALL', 0),   -- owner FINAL decision Q2: NO session restriction; session recorded per signal/trade
  ('session_filter',  'off', 0),   -- reserved switch; stays off until the backtest proves a filter earns its keep
  ('kill_switch',     'off', 0),
  ('auto_mode',       'off', 0),   -- off = Telegram confirm button required before any order
  ('pairs',           'USDJPY,EURGBP,CADJPY,USDCHF,EURAUD,AUDCAD,NZDJPY,GBPUSD', 0), -- start set; Stage 2 syncs ALL IC Markets cTrader pairs (owner FINAL decision Q3)
  ('pair_filter',     'off', 0),   -- no pre-filtering: bot covers every synced pair; backtest reports per pair
  ('score_threshold_strong', '70', 0),
  ('score_threshold_weak',   '50', 0),
  ('w_bias','25',0),('w_level','20',0),('w_structure','20',0),('w_series','15',0),('w_model','15',0),('w_session','5',0),  -- Q5 proposed (citations in STRATEGY.md); w_session = score bonus only, NOT a filter; backtest validates all weights
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
