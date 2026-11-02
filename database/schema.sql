-- =============================================================================
-- FinTerminal — schema da base local (SQLite)
--
-- Fonte única do schema: consolida as antigas migrations do Supabase e as tabelas
-- que só existiam no painel (price_history, dividend_history, alert_*, etc.).
-- Aplicado automaticamente por database/local_db.py; é idempotente.
--
-- Os tipos abaixo têm significado para o adaptador (lidos via PRAGMA table_info):
--   TIMESTAMPTZ  texto ISO-8601 em UTC, sempre no formato canônico
--                2026-01-31T12:00:00.000000+00:00 (comparável como string)
--   BOOLEAN      0/1 no disco, True/False para o Python
--   JSON         json.dumps na escrita, json.loads na leitura
-- =============================================================================

-- ── Dados pessoais (não reconstruíveis) ─────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id                  INTEGER PRIMARY KEY,
    username            TEXT NOT NULL UNIQUE,
    senha_hash          TEXT NOT NULL,
    nome                TEXT DEFAULT '',
    email               TEXT DEFAULT '',
    is_admin            BOOLEAN DEFAULT 0,
    onboarding_completo BOOLEAN DEFAULT 0,
    ultimo_login        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    updated_at          TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);

CREATE TABLE IF NOT EXISTS user_sessions (
    id         INTEGER PRIMARY KEY,
    token      TEXT NOT NULL UNIQUE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at);

CREATE TABLE IF NOT EXISTS user_settings (
    id              INTEGER PRIMARY KEY,
    user_id         INTEGER NOT NULL UNIQUE,
    ai_provider     TEXT DEFAULT 'deepseek',
    ai_api_key_enc  TEXT,
    ai_model        TEXT DEFAULT 'deepseek-chat',
    moeda_base      TEXT DEFAULT 'BRL',
    benchmark       TEXT DEFAULT 'IBOV',
    alert_threshold INTEGER DEFAULT 40,
    created_at      TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    updated_at      TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);

CREATE TABLE IF NOT EXISTS user_kv (
    user_id INTEGER NOT NULL,
    chave   TEXT NOT NULL,
    valor   TEXT NOT NULL,
    PRIMARY KEY (user_id, chave)
);

CREATE TABLE IF NOT EXISTS chat_portfolio_historico (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL,
    portfolio_id INTEGER NOT NULL,
    role         TEXT NOT NULL,
    conteudo     TEXT NOT NULL,
    criado_em    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS watchlists (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    nome       TEXT NOT NULL,
    descricao  TEXT DEFAULT '',
    cor        TEXT DEFAULT '#FF9900',
    icone      TEXT DEFAULT '⭐',
    padrao     BOOLEAN DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    updated_at TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_watchlists_user_id ON watchlists(user_id);

CREATE TABLE IF NOT EXISTS watchlist_items (
    id           INTEGER PRIMARY KEY,
    ticker       TEXT NOT NULL,
    nome         TEXT DEFAULT '',
    mercado      TEXT DEFAULT '',
    notas        TEXT DEFAULT '',
    tag          TEXT DEFAULT 'geral',
    user_id      INTEGER NOT NULL,
    watchlist_id INTEGER NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    updated_at   TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    UNIQUE (ticker, user_id, watchlist_id)
);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_user_id      ON watchlist_items(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_items_watchlist_id ON watchlist_items(watchlist_id);

CREATE TABLE IF NOT EXISTS portfolios (
    id         INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    nome       TEXT NOT NULL,
    descricao  TEXT DEFAULT '',
    cor        TEXT DEFAULT '#FF9900',
    icone      TEXT DEFAULT '💼',
    padrao     BOOLEAN DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    updated_at TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_portfolios_user_id ON portfolios(user_id);

CREATE TABLE IF NOT EXISTS portfolio_positions (
    id           INTEGER PRIMARY KEY,
    ticker       TEXT NOT NULL,
    peso         NUMERIC,
    preco_medio  NUMERIC,
    quantidade   NUMERIC,
    user_id      INTEGER NOT NULL,
    portfolio_id INTEGER NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    updated_at   TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    UNIQUE (ticker, user_id, portfolio_id)
);
CREATE INDEX IF NOT EXISTS idx_portfolio_positions_user_id      ON portfolio_positions(user_id);
CREATE INDEX IF NOT EXISTS idx_portfolio_positions_portfolio_id ON portfolio_positions(portfolio_id);

CREATE TABLE IF NOT EXISTS portfolio_targets (
    id           INTEGER PRIMARY KEY,
    portfolio_id INTEGER NOT NULL,
    ticker       TEXT NOT NULL,
    peso_alvo    NUMERIC,
    updated_at   TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    UNIQUE (portfolio_id, ticker)
);

CREATE TABLE IF NOT EXISTS decision_log (
    id             INTEGER PRIMARY KEY,
    ticker         TEXT,
    tipo           TEXT,
    data_decisao   TEXT,
    preco_decisao  NUMERIC,
    quantidade     NUMERIC,
    tese           TEXT,
    resultado      TEXT,
    data_resultado TEXT,
    user_id        INTEGER DEFAULT 1,
    created_at     TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    updated_at     TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_decision_log_user_id ON decision_log(user_id, tipo);
CREATE INDEX IF NOT EXISTS idx_decision_log_ticker  ON decision_log(ticker);

CREATE TABLE IF NOT EXISTS report_history (
    id                INTEGER PRIMARY KEY,
    user_id           INTEGER DEFAULT 1,
    tipo              TEXT DEFAULT 'semanal',
    tickers_incluidos TEXT,
    status            TEXT DEFAULT 'enviado',
    created_at        TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    updated_at        TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);

CREATE TABLE IF NOT EXISTS alerts (
    id         INTEGER PRIMARY KEY,
    ticker     TEXT,
    tipo       TEXT,
    threshold  NUMERIC,
    user_id    INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);

CREATE TABLE IF NOT EXISTS alert_config (
    id        INTEGER PRIMARY KEY,
    user_id   INTEGER NOT NULL,
    ticker    TEXT NOT NULL,
    threshold INTEGER,
    ativo     BOOLEAN DEFAULT 1,
    UNIQUE (user_id, ticker)
);

CREATE TABLE IF NOT EXISTS alert_log (
    id           INTEGER PRIMARY KEY,
    user_id      INTEGER NOT NULL,
    ticker       TEXT NOT NULL,
    score        INTEGER,
    threshold    INTEGER,
    disparado_em TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_alert_log_user ON alert_log(user_id, ticker, disparado_em);

CREATE TABLE IF NOT EXISTS saved_comparisons (
    id         INTEGER PRIMARY KEY,
    nome       TEXT NOT NULL,
    tickers    TEXT NOT NULL,
    user_id    INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);

-- ── Histórico acumulado (não reconstruível: nasce da coleta ao longo do tempo) ──

CREATE TABLE IF NOT EXISTS health_score_history (
    id           INTEGER PRIMARY KEY,
    ticker       TEXT NOT NULL,
    score        INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    calculado_em TIMESTAMPTZ NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    UNIQUE (ticker, calculado_em)
);

CREATE TABLE IF NOT EXISTS macro_observations (
    id                   INTEGER PRIMARY KEY,
    observacao_hash      TEXT NOT NULL UNIQUE,
    serie_id             TEXT NOT NULL,
    referencia_em        TEXT NOT NULL,
    disponivel_em        TIMESTAMPTZ NOT NULL,
    coletado_em          TIMESTAMPTZ NOT NULL,
    valor                REAL NOT NULL,
    fonte                TEXT NOT NULL,
    unidade              TEXT NOT NULL,
    disponibilidade_base TEXT NOT NULL,
    vintage_base         TEXT NOT NULL DEFAULT 'observada_na_coleta'
);
CREATE INDEX IF NOT EXISTS idx_macro_obs_conhecidas
    ON macro_observations(serie_id, coletado_em DESC, referencia_em DESC);

-- Append-only: uma revisão é uma nova linha, nunca uma alteração da anterior.
CREATE TRIGGER IF NOT EXISTS macro_observations_sem_update
    BEFORE UPDATE ON macro_observations
BEGIN
    SELECT RAISE(ABORT, 'macro_observations e append-only; registre uma nova versao');
END;
CREATE TRIGGER IF NOT EXISTS macro_observations_sem_delete
    BEFORE DELETE ON macro_observations
BEGIN
    SELECT RAISE(ABORT, 'macro_observations e append-only; registre uma nova versao');
END;

CREATE TABLE IF NOT EXISTS earnings_revisions (
    ticker                 TEXT NOT NULL,
    setor                  TEXT,
    eps_estimate           REAL,
    eps_estimate_30d_atras REAL,
    delta_pct              REAL,
    revisao_positiva       BOOLEAN,
    capturado_em           TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    PRIMARY KEY (ticker, capturado_em)
);
CREATE INDEX IF NOT EXISTS idx_er_setor ON earnings_revisions(setor);

CREATE TABLE IF NOT EXISTS alertas_disparados (
    id             INTEGER PRIMARY KEY,
    user_id        INTEGER,
    ticker         TEXT NOT NULL,
    tipo           TEXT NOT NULL,
    valor_atual    REAL,
    valor_anterior REAL,
    delta          REAL,
    mensagem       TEXT,
    disparado_em   TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    visualizado    BOOLEAN DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alertas_ticker_tipo ON alertas_disparados(ticker, tipo, disparado_em DESC);

CREATE TABLE IF NOT EXISTS ai_analyses (
    id                    TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    tipo                  TEXT NOT NULL,
    ticker                TEXT,
    user_id               INTEGER,
    modo                  TEXT,
    modelo                TEXT,
    conteudo              TEXT NOT NULL,
    contexto_hash         TEXT,
    health_score_snapshot INTEGER,
    created_at            TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    expires_at            TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ai_analyses_lookup ON ai_analyses(tipo, ticker, user_id, modo, expires_at DESC);
CREATE INDEX IF NOT EXISTS ix_ai_analyses_expires ON ai_analyses(expires_at);

CREATE TABLE IF NOT EXISTS ai_analysis_cache (
    id         INTEGER PRIMARY KEY,
    ticker     TEXT,
    tipo       TEXT,
    conteudo   TEXT,
    created_at TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_ai_analysis_cache_ticker ON ai_analysis_cache(ticker, tipo, created_at DESC);

-- ── Dados de mercado (donos: ETL; reconstruíveis) ───────────────────────────

-- WITHOUT ROWID agrupa as barras por ticker no disco: leitura por ativo é sequencial.
CREATE TABLE IF NOT EXISTS price_history (
    ticker TEXT NOT NULL,
    data   TEXT NOT NULL,
    open   REAL,
    high   REAL,
    low    REAL,
    close  REAL,
    volume INTEGER,
    PRIMARY KEY (ticker, data)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_price_history_data ON price_history(data);

CREATE TABLE IF NOT EXISTS dividend_history (
    ticker         TEXT NOT NULL,
    data_pagamento TEXT NOT NULL,
    valor          REAL,
    tipo           TEXT,
    PRIMARY KEY (ticker, data_pagamento)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS price_cache (
    ticker      TEXT PRIMARY KEY,
    preco       REAL,
    var_1d      REAL,
    var_1m      REAL,
    var_12m     REAL,
    volume      INTEGER,
    max_52s     REAL,
    min_52s     REAL,
    rsi_14      REAL,
    data_coleta TEXT NOT NULL DEFAULT CURRENT_DATE,
    updated_at  TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);

CREATE TABLE IF NOT EXISTS fundamentals_cache (
    id               INTEGER PRIMARY KEY,
    ticker           TEXT NOT NULL UNIQUE,
    dados_json       TEXT,
    data_source      TEXT DEFAULT 'legacy',
    data_quality     INTEGER DEFAULT 50,
    data_quality_pct REAL,
    last_validated   TIMESTAMPTZ,
    raw_json         TEXT,
    created_at       TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    updated_at       TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);

CREATE TABLE IF NOT EXISTS health_scores (
    id               INTEGER PRIMARY KEY,
    ticker           TEXT NOT NULL UNIQUE,
    score            NUMERIC,
    alertas_venda    TEXT,
    data_quality_pct REAL,
    created_at       TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    updated_at       TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);

CREATE TABLE IF NOT EXISTS macro_cache (
    indicator  TEXT PRIMARY KEY,
    value      REAL,
    label      TEXT,
    unit       TEXT DEFAULT '',
    source     TEXT DEFAULT '',
    updated_at TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);

CREATE TABLE IF NOT EXISTS macro_snapshots (
    origem      TEXT PRIMARY KEY,
    payload     TEXT NOT NULL,
    n_linhas    INTEGER,
    n_colunas   INTEGER,
    data_inicio TEXT,
    data_fim    TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);

CREATE TABLE IF NOT EXISTS fear_greed_cache (
    market      TEXT PRIMARY KEY,
    score       INTEGER NOT NULL,
    label       TEXT NOT NULL,
    componentes JSON DEFAULT '{}',
    updated_at  TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);

CREATE TABLE IF NOT EXISTS earnings_dates (
    ticker       TEXT PRIMARY KEY,
    proxima_data TEXT,
    fonte        TEXT,
    updated_at   TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now'))
);

CREATE TABLE IF NOT EXISTS earnings_calendar (
    ticker        TEXT NOT NULL,
    data_earnings TEXT NOT NULL,
    periodo       TEXT,
    PRIMARY KEY (ticker, data_earnings)
);

CREATE TABLE IF NOT EXISTS api_cache (
    id         TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    ticker     TEXT NOT NULL,
    provider   TEXT NOT NULL,
    endpoint   TEXT NOT NULL,
    periodo    TEXT,
    data       JSON NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    UNIQUE (ticker, provider, endpoint, periodo)
);

CREATE TABLE IF NOT EXISTS api_key_usage (
    id           TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    provider     TEXT NOT NULL,
    api_key_hash TEXT NOT NULL,
    data_uso     TEXT NOT NULL DEFAULT CURRENT_DATE,
    n_requests   INTEGER NOT NULL DEFAULT 0,
    UNIQUE (provider, api_key_hash, data_uso)
);

CREATE TABLE IF NOT EXISTS etl_log (
    id           INTEGER PRIMARY KEY,
    job_name     TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'running',
    tickers_ok   INTEGER DEFAULT 0,
    tickers_fail INTEGER DEFAULT 0,
    started_at   TIMESTAMPTZ DEFAULT (strftime('%Y-%m-%dT%H:%M:%f000+00:00', 'now')),
    finished_at  TIMESTAMPTZ,
    error_msg    TEXT
);
CREATE INDEX IF NOT EXISTS idx_etl_log_job ON etl_log(job_name, started_at DESC);
