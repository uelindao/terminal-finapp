-- =============================================================================
-- FinTerminal — Schema inicial para Supabase (PostgreSQL)
-- Execute este arquivo no Supabase Dashboard → SQL Editor
-- =============================================================================

-- Função utilitária para atualizar updated_at automaticamente
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- USUÁRIOS
-- =============================================================================
CREATE TABLE IF NOT EXISTS users (
    id           BIGSERIAL PRIMARY KEY,
    username     TEXT NOT NULL UNIQUE,
    senha_hash   TEXT NOT NULL,
    nome         TEXT DEFAULT '',
    email        TEXT DEFAULT '',
    is_admin     BOOLEAN DEFAULT FALSE,
    ultimo_login TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_is_admin  ON users(is_admin);

CREATE OR REPLACE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- =============================================================================
-- WATCHLISTS (coleções)
-- =============================================================================
CREATE TABLE IF NOT EXISTS watchlists (
    id        BIGSERIAL PRIMARY KEY,
    user_id   BIGINT NOT NULL,
    nome      TEXT NOT NULL,
    descricao TEXT DEFAULT '',
    cor       TEXT DEFAULT '#FF9900',
    icone     TEXT DEFAULT '⭐',
    padrao    BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists(user_id);

CREATE OR REPLACE TRIGGER trg_watchlists_updated_at
    BEFORE UPDATE ON watchlists
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- =============================================================================
-- ITENS DA WATCHLIST  (era "watchlist" no SQLite)
-- =============================================================================
CREATE TABLE IF NOT EXISTS watchlist_items (
    id           BIGSERIAL PRIMARY KEY,
    ticker       TEXT NOT NULL,
    nome         TEXT DEFAULT '',
    mercado      TEXT DEFAULT '',
    notas        TEXT DEFAULT '',
    user_id      BIGINT NOT NULL,
    watchlist_id BIGINT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (ticker, user_id, watchlist_id)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_items_user_id      ON watchlist_items(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_ticker       ON watchlist_items(ticker);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_id ON watchlist_items(watchlist_id);

CREATE OR REPLACE TRIGGER trg_watchlist_items_updated_at
    BEFORE UPDATE ON watchlist_items
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- =============================================================================
-- PORTFÓLIOS
-- =============================================================================
CREATE TABLE IF NOT EXISTS portfolios (
    id        BIGSERIAL PRIMARY KEY,
    user_id   BIGINT NOT NULL,
    nome      TEXT NOT NULL,
    descricao TEXT DEFAULT '',
    cor       TEXT DEFAULT '#FF9900',
    icone     TEXT DEFAULT '💼',
    padrao    BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_portfolios_user_id ON portfolios(user_id);

CREATE OR REPLACE TRIGGER trg_portfolios_updated_at
    BEFORE UPDATE ON portfolios
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- =============================================================================
-- POSIÇÕES DE PORTFÓLIO  (era "portfolio_pesos" no SQLite)
-- =============================================================================
CREATE TABLE IF NOT EXISTS portfolio_positions (
    id           BIGSERIAL PRIMARY KEY,
    ticker       TEXT NOT NULL,
    peso         NUMERIC,
    preco_medio  NUMERIC,
    quantidade   NUMERIC,
    user_id      BIGINT NOT NULL,
    portfolio_id BIGINT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (ticker, user_id, portfolio_id)
);

CREATE INDEX IF NOT EXISTS idx_portfolio_positions_user_id      ON portfolio_positions(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_positions_ticker       ON portfolio_positions(ticker);
CREATE INDEX IF NOT EXISTS idx_portfolio_positions_portfolio_id ON portfolio_positions(portfolio_id);

CREATE OR REPLACE TRIGGER trg_portfolio_positions_updated_at
    BEFORE UPDATE ON portfolio_positions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- =============================================================================
-- HEALTH SCORES
-- =============================================================================
CREATE TABLE IF NOT EXISTS health_scores (
    id            BIGSERIAL PRIMARY KEY,
    ticker        TEXT NOT NULL UNIQUE,
    score         NUMERIC,
    alertas_venda TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_health_scores_ticker ON health_scores(ticker);

CREATE OR REPLACE TRIGGER trg_health_scores_updated_at
    BEFORE UPDATE ON health_scores
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- =============================================================================
-- CACHE DE FUNDAMENTOS  (era "fundamentos_cache" no SQLite)
-- =============================================================================
CREATE TABLE IF NOT EXISTS fundamentals_cache (
    id         BIGSERIAL PRIMARY KEY,
    ticker     TEXT NOT NULL UNIQUE,
    dados_json TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fundamentals_cache_ticker ON fundamentals_cache(ticker);

CREATE OR REPLACE TRIGGER trg_fundamentals_cache_updated_at
    BEFORE UPDATE ON fundamentals_cache
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- =============================================================================
-- DIÁRIO DE DECISÕES  (era "decisoes" no SQLite)
-- =============================================================================
CREATE TABLE IF NOT EXISTS decision_log (
    id             BIGSERIAL PRIMARY KEY,
    ticker         TEXT,
    tipo           TEXT,
    data_decisao   TEXT,
    preco_decisao  NUMERIC,
    quantidade     NUMERIC,
    tese           TEXT,
    resultado      TEXT,
    data_resultado TEXT,
    user_id        BIGINT DEFAULT 1,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_decision_log_user_id ON decision_log(user_id);
CREATE INDEX IF NOT EXISTS idx_decision_log_ticker  ON decision_log(ticker);

CREATE OR REPLACE TRIGGER trg_decision_log_updated_at
    BEFORE UPDATE ON decision_log
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- =============================================================================
-- HISTÓRICO DE RELATÓRIOS  (era "relatorios_enviados" no SQLite)
-- =============================================================================
CREATE TABLE IF NOT EXISTS report_history (
    id                BIGSERIAL PRIMARY KEY,
    user_id           BIGINT DEFAULT 1,
    tipo              TEXT DEFAULT 'semanal',
    tickers_incluidos TEXT,
    status            TEXT DEFAULT 'enviado',
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_report_history_user_id ON report_history(user_id);

CREATE OR REPLACE TRIGGER trg_report_history_updated_at
    BEFORE UPDATE ON report_history
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();


-- =============================================================================
-- ALERTAS
-- =============================================================================
CREATE TABLE IF NOT EXISTS alerts (
    id         BIGSERIAL PRIMARY KEY,
    ticker     TEXT,
    tipo       TEXT,
    threshold  NUMERIC,
    user_id    BIGINT DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_ticker  ON alerts(ticker);


-- =============================================================================
-- CACHE DE ANÁLISE IA  (era "cache_analise_ia" no SQLite)
-- =============================================================================
CREATE TABLE IF NOT EXISTS ai_analysis_cache (
    id         BIGSERIAL PRIMARY KEY,
    ticker     TEXT,
    tipo       TEXT,
    conteudo   TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ai_analysis_cache_ticker ON ai_analysis_cache(ticker);


-- =============================================================================
-- COMPARAÇÕES SALVAS  (era "comparacoes_salvas" no SQLite)
-- =============================================================================
CREATE TABLE IF NOT EXISTS saved_comparisons (
    id         BIGSERIAL PRIMARY KEY,
    nome       TEXT NOT NULL,
    tickers    TEXT NOT NULL,
    user_id    BIGINT DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_saved_comparisons_user_id ON saved_comparisons(user_id);


-- =============================================================================
-- NOTA SOBRE ROW LEVEL SECURITY (RLS)
-- =============================================================================
-- Este app usa a service_role key no backend (st.secrets["SUPABASE_KEY"]),
-- que ignora RLS por padrão. O isolamento de dados por usuário é feito
-- via filtros user_id no Python.
--
-- Se quiser ativar RLS para segurança adicional:
--   ALTER TABLE users ENABLE ROW LEVEL SECURITY;
--   -- (repita para cada tabela)
-- E configure policies adequadas para a service_role.
-- =============================================================================
