-- Bishop infrastructure only. Never create or migrate the Kevin bot's tables.
CREATE TABLE IF NOT EXISTS bishop_settings (
    k VARCHAR(128) NOT NULL PRIMARY KEY,
    v TEXT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS bishop_runs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    job VARCHAR(64) NOT NULL,
    planned_at DATETIME NULL,
    started_at DATETIME NOT NULL,
    finished_at DATETIME NULL,
    ok TINYINT(1) NULL,
    note MEDIUMTEXT NULL,
    INDEX bishop_runs_job_started (job, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
