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

-- Nota: inclinação da curva US (T10Y-T2Y, T10Y-T3M) é persistida em macro_cache
-- via upsert_macro como linhas key-value (indicator='slope_10y_2y_pp' etc.),
-- não como colunas separadas. A série histórica é lida do snapshot fred_global
-- (colunas DGS10/DGS2/DGS3MO). Por isso nenhum ALTER TABLE é necessário aqui.

-- ── Earnings Revisions (revisões de EPS por setor) ───────────────────────────
-- Rodar manualmente no Supabase SQL Editor antes do próximo ETL.
CREATE TABLE IF NOT EXISTS earnings_revisions (
    ticker TEXT NOT NULL,
    setor TEXT,
    eps_estimate REAL,
    eps_estimate_30d_atras REAL,
    delta_pct REAL,
    revisao_positiva BOOLEAN,
    capturado_em TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (ticker, capturado_em)
);
CREATE INDEX IF NOT EXISTS idx_er_setor ON earnings_revisions(setor);
CREATE INDEX IF NOT EXISTS idx_er_capturado ON earnings_revisions(capturado_em DESC);

-- ── Alertas Disparados (Trilha 4.3 — alertas inteligentes por mudança) ───────
-- Rodar manualmente no Supabase SQL Editor antes do próximo recalc_health_scores.
CREATE TABLE IF NOT EXISTS alertas_disparados (
    id SERIAL PRIMARY KEY,
    user_id INTEGER,
    ticker TEXT NOT NULL,
    tipo TEXT NOT NULL,             -- 'queda_score_7d' | 'salto_dy_30d' | 'variacao_semanal'
    valor_atual REAL,
    valor_anterior REAL,
    delta REAL,
    mensagem TEXT,
    disparado_em TIMESTAMPTZ DEFAULT now(),
    visualizado BOOLEAN DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_alertas_user ON alertas_disparados(user_id, disparado_em DESC);
CREATE INDEX IF NOT EXISTS idx_alertas_ticker_tipo ON alertas_disparados(ticker, tipo, disparado_em DESC);

COMMENT ON TABLE alertas_disparados IS 'Alertas inteligentes detectados pelo motor utils/alertas_mudanca.py — disparos de mudança (queda de score, salto DY, variação semanal). Anti-duplicata: pula se já há registro do mesmo (ticker, tipo) nas últimas 24h.';
