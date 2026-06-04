-- =============================================================================
-- FinTerminal — Migration 004: ETL cache improvements
-- Suporte à arquitetura database-first com ETL desacoplado
-- Adiciona colunas de auditoria + tabelas de cache de preços e macro
-- =============================================================================

-- 1. Novas colunas em fundamentals_cache para auditoria de qualidade
ALTER TABLE fundamentals_cache
ADD COLUMN IF NOT EXISTS data_source     TEXT    DEFAULT 'legacy',
ADD COLUMN IF NOT EXISTS data_quality    INT     DEFAULT 50 CHECK (data_quality BETWEEN 0 AND 100),
ADD COLUMN IF NOT EXISTS last_validated  TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS raw_json        JSONB;

-- 2. Tabela de cache de preços (evita chamadas repetidas ao yfinance)
CREATE TABLE IF NOT EXISTS price_cache (
    ticker       TEXT PRIMARY KEY,
    preco        NUMERIC(12,4),
    var_1d       NUMERIC(8,4),
    var_1m       NUMERIC(8,4),
    var_12m      NUMERIC(8,4),
    volume       BIGINT,
    max_52s      NUMERIC(12,4),
    min_52s      NUMERIC(12,4),
    rsi_14       NUMERIC(6,2),
    data_coleta  DATE NOT NULL DEFAULT CURRENT_DATE,
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_price_cache_data  ON price_cache(data_coleta DESC);
CREATE INDEX IF NOT EXISTS idx_price_cache_ticker ON price_cache(ticker);

-- 3. Tabela de cache de indicadores macroeconômicos
CREATE TABLE IF NOT EXISTS macro_cache (
    indicator    TEXT PRIMARY KEY,
    value        NUMERIC(12,4),
    label        TEXT,
    unit         TEXT DEFAULT '',
    source       TEXT DEFAULT '',
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_macro_cache_updated ON macro_cache(updated_at DESC);

-- 4. Tabela de log de execuções do ETL
CREATE TABLE IF NOT EXISTS etl_log (
    id           BIGSERIAL PRIMARY KEY,
    job_name     TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'running',
    tickers_ok   INT DEFAULT 0,
    tickers_fail INT DEFAULT 0,
    started_at   TIMESTAMPTZ DEFAULT NOW(),
    finished_at  TIMESTAMPTZ,
    error_msg    TEXT
);

CREATE INDEX IF NOT EXISTS idx_etl_log_job ON etl_log(job_name, started_at DESC);
