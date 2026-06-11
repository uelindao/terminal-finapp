-- ── Tabela principal de cache de API ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS api_cache (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    ticker      TEXT        NOT NULL,
    provider    TEXT        NOT NULL,   -- 'alpha_vantage' | 'fmp' | 'brapi' | 'yfinance'
    endpoint    TEXT        NOT NULL,   -- 'INCOME_STATEMENT' | 'BALANCE_SHEET' | etc
    periodo     TEXT,                   -- '2024-Q3' para trimestrais, NULL para snapshots
    data        JSONB       NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_cache UNIQUE (ticker, provider, endpoint, periodo)
);

-- Índices para performance
CREATE INDEX IF NOT EXISTS idx_cache_ticker
    ON api_cache (ticker, provider, endpoint);

CREATE INDEX IF NOT EXISTS idx_cache_updated
    ON api_cache (updated_at);

-- Trigger de atualização automática do updated_at
CREATE OR REPLACE FUNCTION fn_update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_updated_at ON api_cache;
CREATE TRIGGER trg_updated_at
    BEFORE UPDATE ON api_cache
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

-- Tabela de controle de rate limit por chave de API
CREATE TABLE IF NOT EXISTS api_key_usage (
    id          UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    provider    TEXT        NOT NULL,
    api_key_hash TEXT       NOT NULL,   -- hash da chave (não a chave em si)
    data_uso    DATE        NOT NULL DEFAULT CURRENT_DATE,
    n_requests  INT         NOT NULL DEFAULT 0,
    CONSTRAINT uq_key_uso UNIQUE (provider, api_key_hash, data_uso)
);

-- Row Level Security: permite acesso público ao cache
ALTER TABLE api_cache     ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_key_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "allow_all_cache" ON api_cache
    FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "allow_all_key_usage" ON api_key_usage
    FOR ALL USING (true) WITH CHECK (true);

-- Comentários
COMMENT ON TABLE api_cache IS
    'Cache persistente de dados de APIs externas para o FinTerminal';
COMMENT ON COLUMN api_cache.periodo IS
    'NULL para snapshots. Formato YYYY-QN para trimestrais (ex: 2024-Q3)';

-- ── Coluna de qualidade do dado (0-100) ──────────────────────────────────
-- % de campos críticos preenchidos no momento da coleta ETL.
-- Rodar manualmente no Supabase SQL Editor antes do próximo ETL.

ALTER TABLE IF EXISTS health_scores
    ADD COLUMN IF NOT EXISTS data_quality_pct REAL;

ALTER TABLE IF EXISTS fundamentals_cache
    ADD COLUMN IF NOT EXISTS data_quality_pct REAL;

COMMENT ON COLUMN health_scores.data_quality_pct IS
    'Percentual (0-100) de campos críticos preenchidos no momento da coleta. Null = não medido.';
COMMENT ON COLUMN fundamentals_cache.data_quality_pct IS
    'Idem health_scores.';
